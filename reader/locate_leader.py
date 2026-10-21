"""locate_leader.py — 用指挥官名称定位 Leader 运行时结构

存档 LEADER/PILOT 记录 180B x 50000，槽1="Abe, Heisuke" 等。
名称是唯一字符串，误报率 0。

用法:
  python3 locate_leader.py <save> [--verify]
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

LD = 180


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_leaders(path):
    d = pwsfile.record_by_len(path, 9000000)
    out = {}
    if not d:
        return out
    for s in range(50000):
        b = s * LD
        nm = d[b:b + 30].split(b"\0")[0]
        if len(nm) < 4 or not all(32 <= c < 127 for c in nm):
            continue
        out[s] = nm.decode("ascii")
    return out


def main():
    save = sys.argv[1]
    leaders = save_leaders(save)
    print(f"存档指挥官 {len(leaders)} 个")
    for s, n in list(leaders.items())[:5]:
        print(f"  slot{s}: {n!r}")

    pid = pid_of()
    print(f"\nPID={pid}")

    names = [n for n in leaders.values() if len(n) >= 8][:6]
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
        print(f"  {nm!r}: {len(found)} 处 {[hex(a) for a in found[:3]]}")

    from collections import Counter
    cnt = Counter()
    for nm, addrs in hits.items():
        slot = [s for s, n in leaders.items() if n == nm][0]
        for a in addrs:
            cnt[a - slot * LD] += 1
    print("\n候选基址:")
    for b, c in cnt.most_common(6):
        print(f"  {b:#x}  吻合 {c} 个")

    # 验证最佳候选
    if cnt:
        base = cnt.most_common(1)[0][0]
        fd = memrw.open_mem(pid)
        ok = 0
        for s, nm in leaders.items():
            d = memrw.read_mem(pid, base + s * LD, 30, fd)
            if d and d.split(b"\0")[0].decode("ascii", "replace") == nm:
                ok += 1
        os.close(fd)
        print(f"\n最佳基址 {base:#x} 验证: {ok}/{len(leaders)} 名称吻合")


if __name__ == "__main__":
    main()
