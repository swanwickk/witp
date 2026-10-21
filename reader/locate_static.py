"""locate_static.py — 定位舰级/机型/设备等「静态数据」运行时数组

这些是剧本数据（不随回合变化），用名称字符串定位，误报率 0。

用法:
  python3 locate_static.py shipclass <save>
  python3 locate_static.py aircraft  <save>
  python3 locate_static.py device    <save>
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SPEC = {
    "shipclass": (1900000, 380),
    "aircraft":  (396000, 396),
    "device":    (472000, 236),
}


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_names(path, ulen, sz):
    d = pwsfile.record_by_len(path, ulen)
    out = {}
    if not d:
        return out
    for s in range(len(d) // sz):
        b = s * sz
        nm = d[b:b + 40].split(b"\0")[0]
        if len(nm) < 4 or not all(32 <= c < 127 for c in nm):
            continue
        out[s] = nm.decode("ascii")
    return out


def main():
    kind = sys.argv[1]
    save = sys.argv[2]
    ulen, sz = SPEC[kind]
    names = save_names(save, ulen, sz)
    print(f"{kind}: 存档 {len(names)} 条，记录 {sz}B")
    for s, n in list(names.items())[:4]:
        print(f"  slot{s}: {n!r}")

    pid = pid_of()
    anchors = [n for n in names.values() if len(n) >= 10][:6]
    print(f"\n锚: {anchors}")

    hits = {}
    for nm in anchors:
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
        print(f"  {nm!r}: {len(found)} 处")

    from collections import Counter
    cnt = Counter()
    for nm, addrs in hits.items():
        slot = [s for s, n in names.items() if n == nm][0]
        for a in addrs:
            cnt[a - slot * sz] += 1
    print("\n候选基址:")
    for b, c in cnt.most_common(5):
        print(f"  {b:#x}  吻合 {c}")

    if cnt:
        base = cnt.most_common(1)[0][0]
        fd = memrw.open_mem(pid)
        ok = 0
        for s, nm in names.items():
            d = memrw.read_mem(pid, base + s * sz, 40, fd)
            if d and d.split(b"\0")[0].decode("ascii", "replace") == nm:
                ok += 1
        os.close(fd)
        print(f"\n最佳基址 {base:#x}: {ok}/{len(names)} 名称吻合")


if __name__ == "__main__":
    main()
