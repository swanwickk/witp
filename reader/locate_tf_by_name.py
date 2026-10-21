"""locate_tf_by_name.py — 用 TF 名称字符串定位结构

关键洞察：
  上面所有数值判据都会误报，因为小整数组合太常见。
  但 **TF 名称字符串**（"MO Landing Force"）是唯一的，误报率为 0。

  而结构内一定有名称字段。先从 TF7 结构里找出名称在哪，
  再用它反推定位方法。
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


def main():
    pid = pid_of()
    fd = memrw.open_mem(pid)
    d = memrw.read_mem(pid, TF7, SZ, fd)

    print("=== 结构内 ASCII 段 ===")
    cur = []
    for i, b in enumerate(d):
        if 32 <= b < 127:
            cur.append((i, chr(b)))
        else:
            if len(cur) >= 3:
                print(f"  off {cur[0][0]:>3}: {''.join(c for _, c in cur)!r}")
            cur = []
    if len(cur) >= 3:
        print(f"  off {cur[0][0]:>3}: {''.join(c for _, c in cur)!r}")

    # 结构外前后 200 字节找名称
    print("\n=== 结构外前后找名称 ===")
    for delta in (-256, 464, 464 + 256):
        a = TF7 + delta
        d2 = memrw.read_mem(pid, a, 256, fd)
        if not d2:
            continue
        runs = []
        cur = []
        for i, b in enumerate(d2):
            if 32 <= b < 127:
                cur.append((i, chr(b)))
            else:
                if len(cur) >= 5:
                    runs.append((cur[0][0], "".join(c for _, c in cur)))
                cur = []
        if len(cur) >= 5:
            runs.append((cur[0][0], "".join(c for _, c in cur)))
        if runs:
            print(f"  {a:#x}: {runs[:5]}")

    # 全内存搜 "MO Landing Force"
    print("\n=== 全内存搜 'MO Landing Force' ===")
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < 1024 * 1024:
            continue
        b = memrw.read_mem(pid, s, e - s, fd)
        if not b:
            continue
        i = b.find(b"MO Landing Force")
        if i >= 0:
            print(f"  命中 @ {s+i:#x}  (所在段 {s:#x})")

    os.close(fd)


if __name__ == "__main__":
    main()
