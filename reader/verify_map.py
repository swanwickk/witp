"""verify_map.py — 用存档真实值反查运行时偏移

思路（纯静态 + 纯数据，不碰界面）：
  如果运行时偏移 X 对应存档偏移 Y，那么对同一批 TF：
    存档里 Y 位置的取值集合  ==  运行时 X 位置的取值集合（顺序一致）

本脚本：
  1. 从存档 TASKGROUP(556B×4000) 里，对每个候选存档偏移，
     取所有占用槽的值序列
  2. 从进程内存 TF(464B) 里，对每个候选运行时偏移，取同样的序列
  3. 求最长公共序列 / 完全相同，输出匹配对

用法:
  python3 verify_map.py <save.pws>
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe
import pwsfile

BASE = 0x1a143ac
RSZ = 0x1d0      # 运行时 464
SSZ = 556        # 存档 556

# 反汇编得到的运行时偏移（读写频繁 = 真字段）
RT_OFFS = [0x0, 0x12, 0x3a, 0x62, 0x76, 0x9e, 0xb2, 0xee, 0xf8, 0xfe,
           0x104, 0x116, 0x117, 0x118, 0x119, 0x11a, 0x11b, 0x11c, 0x11d,
           0x11e, 0x11f, 0x120, 0x121, 0x122, 0x124, 0x126, 0x144, 0x145]


def test_pid():
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{cand}/environ", "rb").read():
                return int(cand)
        except OSError:
            pass
    return None


def save_tf(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == 2224000:
            return r["data"]
    return None


def main():
    save_path = sys.argv[1]
    tf = save_tf(save_path)
    if not tf:
        print("存档里找不到 TASKGROUP")
        return
    slots = [s for s in range(200) if struct.unpack_from("<H", tf, s * SSZ + 44)[0] != 0]
    print(f"存档占用槽 {len(slots)} 个: {slots[:20]}")

    pid = test_pid()
    if not pid:
        print("测试实例未运行，只能输出存档侧取值")
        return
    print(f"PID={pid}\n")

    # 存档侧：每个候选偏移的值序列
    s_vals = {}
    for off in range(0, SSZ - 1):
        s_vals[off] = tuple(tf[s * SSZ + off] for s in slots)

    # 运行时侧
    r_vals = {}
    for off in RT_OFFS:
        try:
            data = [mem_probe.gdb_read(pid, BASE + s * RSZ + off, 1) for s in slots]
            if any(d is None for d in data):
                continue
            r_vals[off] = tuple(d[0] for d in data)
        except Exception:
            continue

    print("匹配结果（运行时偏移 → 存档偏移，值序列完全一致）:")
    hits = 0
    for roff, seq in sorted(r_vals.items()):
        if len(set(seq)) <= 1:
            continue   # 全同值，无法区分
        for soff, sseq in s_vals.items():
            if sseq == seq:
                print(f"  运行时 {roff:#05x}({roff}) → 存档 {soff}   "
                      f"值={seq[:8]}{'...' if len(seq) > 8 else ''}")
                hits += 1
    if hits == 0:
        print("  无完全匹配（可能需要按不同槽序对齐，或存档/运行时不同构）")


if __name__ == "__main__":
    main()
