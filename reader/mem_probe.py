"""mem_probe.py — 在运行中的 WitP 进程内存里定位 PWSTaskGroup 数组

原理：TF 结构体 556 字节，已知 field 偏移。用"某 TF 的 flagship + home +
mission 三元组"做特征串，在堆区扫描，命中即为该 TF 的运行时地址。

用法（宿主机）：
  python3 mem_probe.py <pid> [pattern]
  python3 mem_probe.py <pid> --dump 0xADDR <len>
"""
import struct
import subprocess
import sys
import os


def gdb_read(pid, addr, length):
    """用 gdb 读进程内存。"""
    cmd = ["gdb", "-p", str(pid), "-batch",
           "-ex", f"dump binary memory /tmp/_mem.bin {hex(addr)} {hex(addr+length)}"]
    subprocess.run(cmd, capture_output=True, timeout=120)
    if os.path.exists("/tmp/_mem.bin"):
        data = open("/tmp/_mem.bin", "rb").read()
        os.remove("/tmp/_mem.bin")
        return data
    return b""


def gdb_write(pid, addr, data):
    """用 gdb 写进程内存。"""
    with open("/tmp/_patch.bin", "wb") as f:
        f.write(data)
    cmd = ["gdb", "-p", str(pid), "-batch",
           "-ex", f"restore /tmp/_patch.bin binary {hex(addr)}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    os.remove("/tmp/_patch.bin")
    return r.returncode == 0, (r.stdout or "")[-300:]


def regions(pid):
    r = subprocess.run(["gdb", "-p", str(pid), "-batch", "-ex", "info proc mappings"],
                       capture_output=True, text=True, timeout=120)
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].startswith("0x"):
            try:
                start = int(parts[0], 16)
                end = int(parts[1], 16)
                perm = parts[4]
                out.append((start, end, perm))
            except (ValueError, IndexError):
                pass
    return out


def scan(pid, pattern, max_scan_mb=600):
    """在可读区域里搜字节串。"""
    hits = []
    scanned = 0
    for start, end, perm in regions(pid):
        if "r" not in perm:
            continue
        size = end - start
        if size > 128 * 1024 * 1024:      # 跳过超大区
            continue
        scanned += size
        if scanned > max_scan_mb * 1024 * 1024:
            break
        data = gdb_read(pid, start, size)
        if not data:
            continue
        idx = data.find(pattern)
        while idx >= 0:
            hits.append(start + idx)
            idx = data.find(pattern, idx + 1)
            if len(hits) > 200:
                return hits
    return hits


if __name__ == "__main__":
    pid = int(sys.argv[1])
    if "--dump" in sys.argv:
        i = sys.argv.index("--dump")
        addr = int(sys.argv[i + 1], 16)
        ln = int(sys.argv[i + 2])
        d = gdb_read(pid, addr, ln)
        print(f"read {len(d)} bytes @ {hex(addr)}")
        for off in range(0, len(d), 16):
            chunk = d[off:off + 16]
            print(f"  {hex(addr+off)}  {chunk.hex(' ')}  " +
                  "".join(chr(c) if 32 <= c < 127 else "." for c in chunk))
        sys.exit(0)

    # 默认：搜 TF7 的 flagship=91 + home=992 + mission=15
    # 布局：off44 i32 flagship, off54 u16 home, off349 u8 mission
    if len(sys.argv) > 2 and sys.argv[2] == "auto":
        pat = struct.pack("<i", 91) + b"\x00" * 6 + struct.pack("<H", 992)
        print("搜索 TF7 flagship=91/home=992 前置特征…")
        hits = scan(pid, pat)
        print(f"命中 {len(hits)} 处")
        for h in hits[:10]:
            # 命中的是 off44，结构体基址 = h - 44
            base = h - 44
            d = gdb_read(pid, base, 556)
            if len(d) < 556:
                continue
            fl = struct.unpack_from("<i", d, 44)[0]
            home = struct.unpack_from("<H", d, 54)[0]
            miss = d[349]
            print(f"  base={hex(base)} flagship={fl} home={home} mission={miss} "
                  f"wp0={struct.unpack_from('<HH', d, 118)} cnt={struct.unpack_from('<H', d, 320)[0]}")
