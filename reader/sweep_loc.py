"""sweep_loc.py — 批量探测 Loc 记录里的命令字段

思路：把一批候选偏移各改成"明显的非默认值"，一次性写入存档，
载入游戏后用 OCR 对比基线截图，找出哪些界面文字变了。

用法：
  python3 sweep_loc.py <base.pws> <out.pws> <slotid> <off1,off2,...> <val>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container
from pwspack import pack_container

LOC_REC = 21096000
LOC_SZ = 1172


def main():
    base, out = sys.argv[1], sys.argv[2]
    slot = int(sys.argv[3])
    offs = [int(x) for x in sys.argv[4].split(",")]
    val = int(sys.argv[5]) if len(sys.argv) > 5 else 1

    c = read_container(base)
    rec = next(r for r in c["records"] if len(r["data"]) == LOC_REC)
    blk = bytearray(rec["data"])
    o = slot * LOC_SZ
    before = [(off, blk[o + off]) for off in offs]
    for off in offs:
        blk[o + off] = val
    rec["data"] = bytes(blk)
    print(f"槽{slot} 改: " + ", ".join(f"off{a}:{b}->{val}" for a, b in before))
    try:
        pack_container(c["records"], out, keep_lengths=True)
        print("saved", out)
    except Exception as e:
        print("FAIL:", e)


if __name__ == "__main__":
    main()
