"""find_tf_base.py — 用内存实况反推 TF 数组基址（不靠猜）

原理：
  反汇编已确认 TF 运行时步长 = 0x1d0 (464)。
  真实基址 B 满足：对每个占用的 TF 槽 s，B + s*464 处是一个有意义的结构。

判据（必须能失败）：
  存档里 TF 有 26 个占用槽 [1..12,14..18,20..25,28..30]，
  所以候选基址 B 必须让这些槽**大部分非零**，而空槽（0、13、19、26、27）**接近全零**。
  这是双向判据 —— 单看"非零"会被随机数据骗过。

做法：
  在 .data/.bss 区间里按 464 对齐扫描，对每个候选 B 计算
    score = (占用槽平均非零字节) - (空槽平均非零字节)
  取最高分。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe

SZ = 0x1d0
OCC = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18,
       20, 21, 22, 23, 24, 25, 28, 29, 30]
EMPTY = [0, 13, 19, 26, 27]


def pid_of():
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{cand}/environ", "rb").read():
                return int(cand)
        except OSError:
            pass
    return None


def nz(data):
    return sum(1 for b in data if b)


def main():
    pid = pid_of()
    if not pid:
        print("找不到测试实例")
        return
    print(f"PID={pid}")

    lo = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x1800000
    hi = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x1c00000

    # 一次大块读，减少 gdb 往返
    span = hi - lo
    print(f"扫描 {lo:#x}-{hi:#x} ({span//1024//1024}MB)...")
    blob = mem_probe.gdb_read(pid, lo, span)
    if not blob or len(blob) < span:
        print(f"读取不完整: {len(blob) if blob else 0}/{span}")
        return
    print("读取完成，开始按 464 对齐评分")

    results = []
    # 按 464 对齐，但起点要覆盖所有可能的相位
    for phase in range(0, SZ, 16):
        for base in range(phase, len(blob) - 31 * SZ, SZ):
            occ_scores = []
            emp_scores = []
            ok = True
            for s in OCC[:8]:
                off = base + s * SZ
                if off + SZ > len(blob):
                    ok = False
                    break
                occ_scores.append(nz(blob[off:off + SZ]))
            if not ok:
                continue
            for s in EMPTY[:4]:
                off = base + s * SZ
                if off + SZ > len(blob):
                    ok = False
                    break
                emp_scores.append(nz(blob[off:off + SZ]))
            if not ok:
                continue
            avg_o = sum(occ_scores) / len(occ_scores)
            avg_e = sum(emp_scores) / len(emp_scores) if emp_scores else 0
            score = avg_o - avg_e
            if score > 20:
                results.append((score, lo + base, avg_o, avg_e))

    results.sort(reverse=True)
    print(f"\n候选基址 (score>20) 共 {len(results)} 个，前 10:")
    for score, addr, ao, ae in results[:10]:
        print(f"  {addr:#010x}  score={score:7.1f}  占用槽均值={ao:6.1f}  空槽均值={ae:5.1f}")


if __name__ == "__main__":
    main()
