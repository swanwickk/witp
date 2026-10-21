"""find_leader_sweep.py — 暴力扫 TF 结构，找出哪个字段是 leaderID

方法：
  1. 记录 TF1 当前指挥官名（从 Leader 数组反查）
  2. 对 TF 结构 0..556 的每个 u16 位置，写入一个已知将领 ID
  3. 立即读回，若某字段让「TF1 指挥官名」变化 → 找到 leaderID

但读「当前指挥官名」需要知道映射。改用更直接判据：
  TF 结构里，写 leader ID 后**过回合仍在**的字段，且值域 1..20000，
  且各 TF 值不同 → 候选。

本脚本先做「各 TF 值不同且在 1..20000」的精确枚举。
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import witp_obj

TF = 0x6da5148
SZ = 556


def main():
    pid = witp_obj.game_pid()
    tfs = {}
    for tf in range(1, 40):
        d = witp_obj._read(pid, TF + tf * SZ, SZ)
        if d and struct.unpack_from("<I", d, 44)[0]:
            tfs[tf] = d
    print(f"占用 TF {len(tfs)} 个\n")

    print("各 TF 都有值、且值互不相同的 u16（leaderID 候选）:")
    for off in range(0, 554, 2):
        vals = {tf: struct.unpack_from("<H", d, off)[0] for tf, d in tfs.items()}
        nz = [v for v in vals.values() if v]
        if len(nz) < len(tfs) * 0.8:
            continue
        if not all(1 <= v <= 20000 for v in nz):
            continue
        if len(set(nz)) < len(nz) * 0.7:
            continue
        # 排除已知字段
        if off in (44, 54, 320, 322, 328, 348, 350, 354, 356, 358,
                   360, 361, 362, 364, 366, 368, 370, 372, 374,
                   376, 378, 380, 382, 384, 386, 390, 392, 396,
                   398, 400, 448, 484, 486, 488):
            continue
        print(f"  off{off}: {dict(list(vals.items())[:6])}")


if __name__ == "__main__":
    main()
