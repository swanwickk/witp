"""find_tf_ref.py — 找 TF 结构里「指向另一个 TF」的字段

原理：
  Follow TF / Meet TF 必然在结构里存目标 TF 号。
  特征：值域 1-30（TF 号），且当前未设置时应该是 0。
  更可靠：在 TF 结构里找所有「值在 1..30 且当前为 0」的 u8/u16 位置，
  这些是 Follow/Meet 的候选。

再叠加静态证据：这些偏移必须出现在「读取后与 TF 号比较」的代码里。

用法:
  python3 find_tf_ref.py
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import witp_obj
import disasm_range
import re

BASE = 0x6da5148
SZ = 556


def main():
    pid = witp_obj.game_pid()
    print(f"PID={pid}")

    # 1. 收集所有占用 TF 的结构
    tfs = {}
    for tf in range(1, 40):
        d = witp_obj._read(pid, BASE + tf * SZ, SZ)
        if not d:
            continue
        fl = struct.unpack_from("<I", d, 44)[0]
        if fl:
            tfs[tf] = d
    print(f"占用 TF {len(tfs)} 个: {sorted(tfs)}")

    # 2. 找「在所有 TF 里都是 0」的偏移（Follow/Patrol 未设置时）
    print("\n所有 TF 都为 0 的偏移（前 60）:")
    zero_offs = []
    for off in range(340, SZ):
        if all(d[off] == 0 for d in tfs.values()):
            zero_offs.append(off)
    print(f"  {zero_offs[:60]}")
    print(f"  共 {len(zero_offs)} 个")

    # 3. 对这些偏移，查静态代码里是否有「与 1..30 比较」的引用
    print("\n候选（静态代码里有 1..30 比较的）:")
    data = open("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
                + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe",
                "rb").read()
    body = data[0x1000:0x1000 + 0x406b7c]

    for off in zero_offs:
        addr = BASE + off
        pat = struct.pack("<I", addr)
        hits = []
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            hits.append(0x401000 + i)
            pos = i + 1
        if not hits:
            continue
        # 反汇编看是否有 cmp $1..30
        cmp_hits = 0
        for h in hits[:6]:
            for l in disasm_range.disasm(h - 4, h + 24):
                m = re.search(r"cmp\s+\$0x([0-9a-f]+),", l)
                if m and 1 <= int(m.group(1), 16) <= 0x1e:
                    cmp_hits += 1
        if cmp_hits:
            print(f"  off{off}: 引用 {len(hits)} 处，其中 {cmp_hits} 处有 1..30 比较")


if __name__ == "__main__":
    main()
