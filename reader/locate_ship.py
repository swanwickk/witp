"""locate_ship.py — 用舰船名称定位 Ship 运行时结构

★★ 关键：舰名是 ASCII 字符串，误报率为 0 ★★
  存档 SHIP 记录 464B，槽 5 = "Shokaku"、槽 6 = "Zuikaku"、槽 19 = "Shoho"。
  名称在记录偏移 0 处，纯 ASCII 可读。

定位法：
  在内存里搜 "Shokaku\0"，命中处若后面 464 步长内还有别的舰名，
  就是 Ship 数组。再用多艘舰名交叉验证。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SH = 464


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_ships(path):
    d = pwsfile.record_by_len(path, 9280000)
    if not d:
        return {}
    out = {}
    for s in range(20000):
        b = s * SH
        raw = d[b:b + 20]
        nm = raw.split(b"\0")[0]
        if len(nm) < 2 or not all(32 <= c < 127 for c in nm):
            continue
        out[s] = nm.decode("ascii")
    return out


def main():
    save = sys.argv[1]
    ships = save_ships(save)
    print(f"存档舰船 {len(ships)} 艘")
    for s, n in list(ships.items())[:8]:
        print(f"  slot{s}: {n!r}")

    pid = pid_of()
    print(f"\nPID={pid}")

    # 取几个名称做锚
    names = [n for n in ships.values() if len(n) >= 5][:6]
    print(f"锚名称: {names}")

    hits = {}
    for nm in names:
        pat = nm.encode() + b"\0"
        found = []
        for st, en, perm, name in memrw.regions(pid):
            if "rw" not in perm or (en - st) < (1 << 20):
                continue
            fd = memrw.open_mem(pid)
            b = memrw.read_mem(pid, st, en - st, fd)
            os.close(fd)
            if not b:
                continue
            pos = 0
            while True:
                i = b.find(pat, pos)
                if i < 0:
                    break
                found.append(st + i)
                pos = i + 1
                if len(found) > 20:
                    break
        hits[nm] = found
        print(f"  {nm!r}: {len(found)} 处 {[hex(a) for a in found[:4]]}")

    # 找同余：哪个基址能让多个舰名的地址满足 (addr - base) % 464 == slot*464
    from collections import Counter
    cnt = Counter()
    for nm, addrs in hits.items():
        slot = [s for s, n in ships.items() if n == nm][0]
        for a in addrs:
            cnt[a - slot * SH] += 1
    print("\n候选基址:")
    for b, c in cnt.most_common(6):
        print(f"  {b:#x}  吻合 {c} 艘")


if __name__ == "__main__":
    main()
