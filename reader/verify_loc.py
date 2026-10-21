"""verify_loc.py — 验证基地数组基址

由 0x4578810 (X=106) 推：结构起点 = 0x4578810 - 36 = 0x45787ec
但该处是 ASCII 文本，说明偏移不是 36。

实测：0x4578810 u16=106, 0x4578812 u16=125, 0x4578842 u16=992
  → 992 与存档 off102 的 prepTarget 吻合，106/125 与 off36/38 吻合
  → 若结构起点 S，则 S+36=0x4578810 ⇒ S=0x45787ec
  → 检查 S+102=0x4578856 是否 = 992

本脚本验证并扫全表。
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
    print(f"PID={pid}  存档基地 {len(locs)} 个")

    # 用 slot34 的命中点反推基址
    hit = 0x04578810          # X=106 的位置
    S = hit - 36
    base = S - 34 * LOC
    print(f"slot34 结构起点={S:#x}  推基址={base:#x}")

    fd = memrw.open_mem(pid)
    d = memrw.read_mem(pid, S, LOC, fd)
    print(f"验证 S+36={struct.unpack_from('<H',d,36)[0]} (期望 106)")
    print(f"     S+38={struct.unpack_from('<H',d,38)[0]} (期望 125)")
    print(f"     S+102={struct.unpack_from('<H',d,102)[0]} (期望 992)")
    print(f"     S+104={d[104]} (期望 77)")

    print("\n=== 全表验证 ===")
    ok = 0
    bad = []
    for s in sorted(locs):
        dd = memrw.read_mem(pid, base + s * LOC, LOC, fd)
        if not dd or len(dd) < LOC:
            bad.append((s, "读失败"))
            continue
        x = struct.unpack_from("<H", dd, 36)[0]
        y = struct.unpack_from("<H", dd, 38)[0]
        if (x, y) == (locs[s][0], locs[s][1]):
            ok += 1
        else:
            bad.append((s, f"mem=({x},{y}) save=({locs[s][0]},{locs[s][1]})"))

    print(f"坐标吻合 {ok}/{len(locs)}")
    for s, why in bad[:6]:
        print(f"  slot{s}: {why}")

    os.close(fd)


if __name__ == "__main__":
    main()
