"""memrw.py — 通过 /proc/<pid>/mem 直接读写进程内存（内核通道，失败会明确报错）

为什么换掉 gdb：
  gdb 的 `dump binary memory` 在目标地址未映射时**静默写出全零文件**，
  与"读到了真实的零"无法区分 —— 这正是前面所有"内存全零"结论的根因。
  /proc/pid/mem 在未映射页上会返回 EIO，能明确区分"读不到"和"读到零"。

用法:
  python3 memrw.py read  <pid> <addr> <len>
  python3 memrw.py write <pid> <addr> <hexbytes>
  python3 memrw.py regions <pid>
  python3 memrw.py check <pid> <addr>          # 判定该地址是否可读
"""
import os
import re
import struct
import sys


def open_mem(pid):
    return os.open(f"/proc/{pid}/mem", os.O_RDWR)


def read_mem(pid, addr, length, fd=None):
    """返回 bytes；未映射页返回 None（不是零）。"""
    own = fd is None
    if own:
        fd = open_mem(pid)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.read(fd, length)
    except OSError:
        return None
    finally:
        if own:
            os.close(fd)


def write_mem(pid, addr, data):
    fd = open_mem(pid)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        n = os.write(fd, data)
        return n == len(data)
    except OSError as e:
        print(f"写入失败: {e}")
        return False
    finally:
        os.close(fd)


def regions(pid):
    """返回 [(start, end, perms, name)]，来自 /proc/pid/maps（内核权威）"""
    out = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s*(.*)", line)
            if m:
                out.append((int(m.group(1), 16), int(m.group(2), 16),
                            m.group(3), m.group(4).strip()))
    return out


def read_range(pid, lo, hi, chunk=1 << 20):
    """按已映射区间分段读，跳过未映射，返回 {start: bytes}"""
    segs = {}
    fd = open_mem(pid)
    try:
        for s, e, perm, name in regions(pid):
            if e <= lo or s >= hi:
                continue
            a = max(s, lo)
            b = min(e, hi)
            pos = a
            while pos < b:
                n = min(chunk, b - pos)
                d = read_mem(pid, pos, n, fd)
                if d:
                    segs[pos] = d
                    pos += len(d)
                else:
                    pos += n
    finally:
        os.close(fd)
    return segs


if __name__ == "__main__":
    cmd = sys.argv[1]
    pid = int(sys.argv[2])
    if cmd == "read":
        addr = int(sys.argv[3], 0)
        ln = int(sys.argv[4])
        d = read_mem(pid, addr, ln)
        print("None (未映射)" if d is None else d.hex())
    elif cmd == "write":
        addr = int(sys.argv[3], 0)
        data = bytes.fromhex(sys.argv[4])
        print("ok" if write_mem(pid, addr, data) else "fail")
    elif cmd == "regions":
        for s, e, p, n in regions(pid):
            if "rw" in p and (e - s) > 1000000:
                print(f"{s:#010x}-{e:#010x} {p} {(e-s)/1048576:7.1f}MB {n}")
    elif cmd == "check":
        addr = int(sys.argv[3], 0)
        d = read_mem(pid, addr, 16)
        print("可读" if d is not None else "不可读(未映射)", d.hex() if d else "")
