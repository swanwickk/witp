"""locate_loc.py — 定位基地(Location)运行时结构

存档 PWSLocation 1172B，字段：
  off36  X  u16
  off38  Y  u16
  off102 prepTarget  u32
  off104 prep       u8
  off424 portExpand u32

定位策略：
  用 (X,Y) 组合 + prep 做锚，要求三字段同时吻合。
  X/Y 是 0-250 的小整数，单独不稀有，但 (X,Y) 相邻 + prep 组合后误报率大幅下降。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

LOC = 1172


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_locs(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == 21096000:
            d = r["data"]
            out = {}
            for s in range(18000):
                b = s * LOC
                x = struct.unpack_from("<H", d, b + 36)[0]
                y = struct.unpack_from("<H", d, b + 38)[0]
                if not (0 < x < 250 and 0 < y < 250):
                    continue
                out[s] = (x, y, d[b + 104],
                          struct.unpack_from("<H", d, b + 102)[0])
            return out
    return {}


def blobs(pid, min_size=1 << 20):
    out = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < min_size:
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, s, e - s, fd)
        os.close(fd)
        if b:
            out.append((s, b))
    return out


def main():
    save = sys.argv[1]
    locs = save_locs(save)
    print(f"存档基地 {len(locs)} 个")
    pid = pid_of()
    print(f"PID={pid}")

    # 选 prep 值非 0/100 的（更稀有）
    cands = {s: v for s, v in locs.items() if 0 < v[2] < 100}
    print(f"prep 介于 0-100 的 {len(cands)} 个")
    for s, v in list(cands.items())[:4]:
        print(f"  slot{s}: x={v[0]} y={v[1]} prep={v[2]} prepTarget={v[3]}")

    bs = blobs(pid)
    print(f"\n内存段 {len(bs)} 个")

    for slot, (x, y, prep, pt) in list(cands.items())[:3]:
        results = []
        for base, blob in bs:
            n = len(blob)
            for off in range(0, n - LOC, 2):
                if struct.unpack_from("<H", blob, off + 36)[0] != x:
                    continue
                if struct.unpack_from("<H", blob, off + 38)[0] != y:
                    continue
                if blob[off + 104] != prep:
                    continue
                if struct.unpack_from("<H", blob, off + 102)[0] != pt:
                    continue
                results.append(base + off)
        print(f"\nslot{slot} (x={x},y={y},prep={prep}) 三字段吻合: {len(results)} 处")
        for a in results[:6]:
            print(f"  {a:#010x}  推基址={a - slot*LOC:#x}")


if __name__ == "__main__":
    main()
