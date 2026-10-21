"""标定进度记录（逐项追加，来自 GUI 差分实测）

格式：字段名 | 记录 | 偏移 | 变化 | 标定时间
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

S = ("/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral"
     + chr(39) + "s Edition/SAVE/")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrated.json")


def tf(path):
    return [x for x in read_container(path)["records"] if x["type"] == 70][0]["data"]


def loc(path):
    for r in read_container(path)["records"]:
        if len(r["data"]) == 21096000:
            return r["data"]


def diff_tf(a_path, b_path, slot=7):
    a, b = tf(a_path), tf(b_path)
    base = slot * 556
    out = []
    for o in range(556):
        if a[base + o] != b[base + o]:
            out.append((o, a[base + o], b[base + o]))
    return out


def diff_loc(a_path, b_path, only_slot=None):
    a, b = loc(a_path), loc(b_path)
    out = []
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            out.append((i // 1172, i % 1172, a[i], b[i]))
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    a, b = sys.argv[2], sys.argv[3]
    if mode == "tf":
        slot = int(sys.argv[4]) if len(sys.argv) > 4 else 7
        print(f"TF{slot} 差分 {os.path.basename(a)} -> {os.path.basename(b)}")
        for o, x, y in diff_tf(a, b, slot):
            print(f"  off {o:>3}: {x:>3} -> {y:<3}")
    else:
        rows = diff_loc(a, b)
        from collections import Counter
        c = Counter(s for s, _, _, _ in rows)
        print(f"Loc 差分 {os.path.basename(a)} -> {os.path.basename(b)}，受影响槽 {len(c)}")
        for s, n in c.most_common(20):
            offs = [(o, x, y) for sl, o, x, y in rows if sl == s][:6]
            print(f"  槽{s:>5} {n:>3}字节 {offs}")
