"""mem_diff.py — 内存差分：抓两次快照，找出变化的字节

用于定位"纯运行时状态"字段（如 TFRetirement）：
  1. 抓快照 A
  2. 游戏里改一个设置
  3. 抓快照 B
  4. 差分 → 变化的位置就是该字段
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mem_probe as M


def regions(pid, min_mb=1, max_mb=200):
    out = []
    for start, end, perm in M.regions(pid):
        if "r" not in perm or "w" not in perm:
            continue
        size = end - start
        if size < min_mb * 1024 * 1024 or size > max_mb * 1024 * 1024:
            continue
        out.append((start, end))
    return out


def snapshot(pid, tag, top=8):
    """把可写区内前 top 个最大区域存到 /tmp/memdump_<tag>.bin"""
    rs = regions(pid)
    rs.sort(key=lambda t: t[1] - t[0], reverse=True)
    manifest = []
    for i, (start, end) in enumerate(rs[:top]):
        data = M.gdb_read(pid, start, end - start)
        p = f"/tmp/memdump_{tag}_{i}.bin"
        open(p, "wb").write(data)
        manifest.append((start, p, len(data)))
        print(f"  [{i}] {hex(start)} {len(data)}B -> {p}")
    with open(f"/tmp/memdump_{tag}.idx", "w") as f:
        for start, p, n in manifest:
            f.write(f"{start} {p} {n}\n")
    return manifest


def diff(tag_a, tag_b):
    ia = [l.split() for l in open(f"/tmp/memdump_{tag_a}.idx")]
    ib = [l.split() for l in open(f"/tmp/memdump_{tag_b}.idx")]
    print(f"{'地址':<14}{'变化字节数':>10}  样例")
    total = 0
    for (sa, pa, na), (sb, pb, nb) in zip(ia, ib):
        a = open(pa, "rb").read()
        b = open(pb, "rb").read()
        if len(a) != len(b):
            continue
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if not diffs:
            continue
        total += len(diffs)
        show = [(hex(int(sa, 16) + i), a[i], b[i]) for i in diffs[:6]]
        print(f"{sa:<14}{len(diffs):>10}  {show}")
    print(f"\n合计变化 {total} 字节")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "snap":
        pid = int(sys.argv[2])
        snapshot(pid, sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 8)
    else:
        diff(sys.argv[2], sys.argv[3])
