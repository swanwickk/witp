"""verify_loc2.py — 验证 Location 数组基址 0x4570c50

判据：对存档所有基地，检查内存同槽 (X,Y) 是否吻合。
      允许"存档有但内存未加载"（如远离战区的基地），
      但**内存有数据的槽必须与存档一致**。
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
    base = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x4570c50
    locs = save_locs(save)
    pid = pid_of()
    fd = memrw.open_mem(pid)

    print(f"基址={base:#x} 步长={LOC}  存档基地 {len(locs)} 个\n")

    ok = 0
    loaded = 0
    bad = []
    for s in sorted(locs):
        d = memrw.read_mem(pid, base + s * LOC, LOC, fd)
        if not d or len(d) < LOC:
            continue
        x = struct.unpack_from("<H", d, 36)[0]
        y = struct.unpack_from("<H", d, 38)[0]
        if x == 65535 and y == 65535:
            continue          # 内存里未加载
        loaded += 1
        if (x, y) == (locs[s][0], locs[s][1]):
            ok += 1
        else:
            bad.append((s, f"mem=({x},{y}) save=({locs[s][0]},{locs[s][1]})"))

    print(f"内存已加载 {loaded} 个，其中坐标吻合 {ok}")
    if bad:
        print(f"不吻合 {len(bad)}:")
        for s, why in bad[:8]:
            print(f"  slot{s}: {why}")
    elif loaded:
        print("★ 已加载的全部吻合")

    os.close(fd)


if __name__ == "__main__":
    main()
