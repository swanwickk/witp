"""find_loc_base.py — 由多个基地坐标反推 Location 数组基址

思路：
  已知一个结构起点 S0=0x45787ec，坐标 (106,125)。
  在存档里 (106,125) 出现在 slot27 和 slot34（多个基地同格）。
  但内存里 (106,125) 在 k=0 和 k=+7 都有，说明同一坐标被多处引用。

  更稳的办法：用**多个不同的坐标**同时验证。
  取存档里坐标互不相同的 5 个基地，在内存里搜各自的 (X,Y)，
  得到 5 个地址，若它们模 1172 同余，则基址 = 那个余数。
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


def main():
    save = sys.argv[1]
    locs = save_locs(save)
    pid = pid_of()

    # 取 8 个坐标互不相同的基地
    seen = set()
    picks = []
    for s, v in locs.items():
        if v[:2] in seen:
            continue
        seen.add(v[:2])
        picks.append((s, v))
        if len(picks) >= 8:
            break
    print("选取样本:")
    for s, v in picks:
        print(f"  slot{s}: ({v[0]},{v[1]}) prep={v[2]} pt={v[3]}")

    # 读全部可写段
    blobs = []
    for st, en, perm, name in memrw.regions(pid):
        if "rw" not in perm or (en - st) < (1 << 20):
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, st, en - st, fd)
        os.close(fd)
        if b:
            blobs.append((st, b))
    print(f"\n内存段 {len(blobs)} 个")

    # 对每个样本，找所有 (X,Y,prep,pt) 全吻合的位置
    hits = {}
    for s, (x, y, prep, pt) in picks:
        found = []
        for base, blob in blobs:
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
                found.append(base + off)
        hits[s] = found
        print(f"  slot{s} ({x},{y}): {len(found)} 处  {[hex(a) for a in found[:3]]}")

    # 统计：哪个基址能让最多样本的地址同余
    from collections import Counter
    cnt = Counter()
    for s, addrs in hits.items():
        for a in addrs:
            cnt[a - s * LOC] += 1
    print("\n候选基址（按样本吻合数排序）:")
    for b, c in cnt.most_common(8):
        print(f"  {b:#x}  吻合 {c}/{len(picks)} 个样本")


if __name__ == "__main__":
    main()
