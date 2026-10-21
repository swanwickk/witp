"""scan_unique.py — 用稀有值组合精确定位 TF 结构实例

教训：flagship/home/mission/speed 都是小整数，组合后仍有 4 万误报。
必须用**大且稀有**的值：TF7 的载荷 46544、续航 1700/840。

判据：结构内同时满足
  +56 == 46544 (currentLoad)
  +48 == 1700  (endurance)
  +88 == 91    (flagship)
三条同时成立 → 几乎不可能是巧合。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

# TF7 实测特征
SIG = {56: 46544, 48: 1700, 88: 91}


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def main():
    pid = pid_of()
    print(f"PID={pid}")
    hits = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < 1024 * 1024:
            continue
        fd = memrw.open_mem(pid)
        blob = memrw.read_mem(pid, s, e - s, fd)
        os.close(fd)
        if not blob:
            continue
        n = len(blob)
        pat = struct.pack("<I", SIG[56])
        pos = 0
        while True:
            i = blob.find(pat, pos)
            if i < 0:
                break
            pos = i + 1
            start = i - 56
            if start < 0 or start + 464 > n:
                continue
            ok = True
            for off, want in SIG.items():
                if off == 88:
                    got = struct.unpack_from("<I", blob, start + off)[0]
                else:
                    got = struct.unpack_from("<I", blob, start + off)[0]
                if got != want:
                    ok = False
                    break
            if ok:
                hits.append(s + start)

    print(f"\n精确命中 {len(hits)} 处:")
    for h in hits:
        print(f"  {h:#010x}")
    if len(hits) >= 2:
        print("\n相邻差:", [hits[i + 1] - hits[i] for i in range(len(hits) - 1)])


if __name__ == "__main__":
    main()
