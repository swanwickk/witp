"""probe_array.py — 探测 TF7 所在的 464 步长数组边界与索引

做法：
  从 TF7 地址出发，向两侧按 464 步进，看哪些位置存在"像 TF 的结构"。
  像 TF 的判据（放宽但仍严格）：
    · flagship 在 1..8000 且 != 0
    · home 在 1..2000 且 != 0
  记录连续区间的起止，得出数组范围；再算 TF7 在区间内的序号。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

TF7 = 0x0cf76040
SZ = 464


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def looks_like_tf(d):
    if not d or len(d) < 464:
        return None
    fl = struct.unpack_from("<I", d, 88)[0]
    hm = struct.unpack_from("<H", d, 98)[0]
    mi = d[393]
    if 1 <= fl <= 8000 and 1 <= hm <= 2000 and 1 <= mi <= 25:
        return (fl, hm, mi)
    return None


def main():
    pid = pid_of()
    fd = memrw.open_mem(pid)

    print("向负方向探测:")
    neg = []
    for k in range(1, 40):
        a = TF7 - k * SZ
        r = looks_like_tf(memrw.read_mem(pid, a, SZ, fd))
        if r:
            neg.append((k, a, r))
            print(f"  k=-{k:<3} {a:#010x} {r}")
    print(f"  负方向命中 {len(neg)} 个")

    print("\n向正方向探测:")
    pos = []
    for k in range(1, 40):
        a = TF7 + k * SZ
        r = looks_like_tf(memrw.read_mem(pid, a, SZ, fd))
        if r:
            pos.append((k, a, r))
            print(f"  k=+{k:<3} {a:#010x} {r}")
    print(f"  正方向命中 {len(pos)} 个")

    os.close(fd)


if __name__ == "__main__":
    main()
