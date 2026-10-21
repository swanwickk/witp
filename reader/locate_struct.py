"""locate_struct.py — 通用运行时结构定位器

方法（已在 TF 上验证成功，这里泛化）：
  1. 从存档取某类记录的若干字段值（要选**稀有**的，如大整数）
  2. 在内存可写段里搜这个值
  3. 反推结构起点，要求**多个字段同时吻合**
  4. 试多个步长，看哪个能让多个实例同时对齐

用法:
  python3 locate_struct.py airgroup <save>
  python3 locate_struct.py location <save>
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile


def pid_of():
    import os
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def get_record(save, rtype, ulen):
    c = pwsfile.read_container(save)
    for r in c["records"]:
        if (r["id"] % 256) == rtype and r["u_len"] == ulen:
            return r["data"]
    return None


def blobs(pid, min_size=1 << 20):
    out = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < min_size:
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, s, e - s, fd)
        import os
        os.close(fd)
        if b:
            out.append((s, b))
    return out


def find_by_sig(pid, sig, rec_size, max_hits=50):
    """sig: {偏移: 值}，全部为 u32/u16 小端。

    返回 [(addr, 命中数)]，addr 为结构起点。
    """
    # 用最稀有的字段做锚点（值最大的那个）
    anchor_off = max(sig, key=lambda k: sig[k])
    anchor_val = sig[anchor_off]
    pat = struct.pack("<I", anchor_val) if anchor_val < 2**32 else None
    if pat is None:
        return []

    hits = []
    for base, blob in blobs(pid):
        pos = 0
        while True:
            i = blob.find(pat, pos)
            if i < 0:
                break
            pos = i + 1
            st = i - anchor_off
            if st < 0 or st + rec_size > len(blob):
                continue
            ok = 0
            for off, want in sig.items():
                if st + off + 4 <= len(blob):
                    if struct.unpack_from("<I", blob, st + off)[0] == want:
                        ok += 1
            if ok >= max(2, len(sig) - 1):
                hits.append((base + st, ok))
            if len(hits) > max_hits:
                return hits
    return hits


def main():
    kind = sys.argv[1]
    save = sys.argv[2]
    pid = pid_of()
    print(f"PID={pid}")

    if kind == "airgroup":
        d = get_record(save, 20, 20400680)
        AG = 680
        if not d:
            print("找不到 AIRGROUP 记录")
            return
        # 取 slot6（maxPlanes=27, pctCAP=30, primary=6）作特征
        for slot in (6, 5, 2):
            b = slot * AG
            sig = {
                40: struct.unpack_from("<I", d, b + 40)[0],
                44: struct.unpack_from("<I", d, b + 44)[0],
                245: struct.unpack_from("<I", d, b + 245)[0],
                560: struct.unpack_from("<I", d, b + 560)[0],
            }
            print(f"\nslot{slot} 特征: {sig}")
            hits = find_by_sig(pid, sig, AG)
            print(f"  命中 {len(hits)} 处")
            for a, ok in hits[:8]:
                print(f"    {a:#010x} 吻合{ok}/{len(sig)}")
                print(f"      推基址(slot{slot}): {a - slot*AG:#x}")

    elif kind == "location":
        d = get_record(save, 19, 21096000)
        LOC = 1172
        if not d:
            print("找不到 LOCATION 记录")
            return
        for slot in range(1, 12):
            b = slot * LOC
            x = struct.unpack_from("<H", d, b + 36)[0]
            y = struct.unpack_from("<H", d, b + 38)[0]
            if not (0 < x < 200 and 0 < y < 200):
                continue
            sig = {36: x, 38: y,
                   102: struct.unpack_from("<I", d, b + 102)[0]}
            hits = find_by_sig(pid, sig, LOC)
            if hits:
                print(f"\nslot{slot} (x={x},y={y}) 命中 {len(hits)}:")
                for a, ok in hits[:5]:
                    print(f"    {a:#010x} 吻合{ok} 推基址={a - slot*LOC:#x}")
                break


if __name__ == "__main__":
    main()
