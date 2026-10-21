"""verify_pilot2.py — 用 304 步长验证 Pilot 数组

关键修正：
  反汇编实测 `imul $0x130` (304) + `0x7f7faa8` = Pilot 数组
  之前的 152 是巧合（304 = 152×2，两个 152 块恰好都"看起来对"）

存档是 152 字节紧凑格式，内存是 304 字节完整结构。
所以不能按索引直接对齐 —— 需要用 off4 的 ID 匹配。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw, pwsfile

PL_MEM = 304
PL_SAVE = 152
BASE = 0x7f7faa8


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
    S = ("/root/.wine-witp-mcp/prefix/drive_c/1108r9/"
         "War in the Pacific Admiral's Edition/SAVE/wpae000.pws")
    d = pwsfile.record_by_len(S, 15200000)
    fd = memrw.open_mem(pid)

    # 取存档里有内容的槽（off4 是 ID）
    save_ids = {}
    for s in range(1, 20000):
        b = s * PL_SAVE
        nz = sum(1 for x in d[b:b + PL_SAVE] if x)
        if nz > 5:
            save_ids[s] = struct.unpack_from("<I", d, b + 4)[0]
        if len(save_ids) >= 100:
            break
    print(f"存档有内容槽: {len(save_ids)}")

    # 内存侧按 304 读，建立 id → 内存值 的映射
    mem_by_id = {}
    for s in range(0, 3000):
        m = memrw.read_mem(pid, BASE + s * PL_MEM, PL_MEM, fd)
        if not m:
            continue
        mid = struct.unpack_from("<I", m, 4)[0]
        if mid:
            mem_by_id[mid] = m

    print(f"内存有 ID 的槽: {len(mem_by_id)}")

    # 用 ID 匹配
    ok = 0
    bad = []
    for s, sid in list(save_ids.items())[:100]:
        if sid not in mem_by_id:
            continue
        m = mem_by_id[sid]
        sv = d[s * PL_SAVE:(s + 1) * PL_SAVE]
        # 比较前 152 字节
        same = sum(1 for i in range(PL_SAVE) if m[i] == sv[i])
        if same >= PL_SAVE * 0.85:
            ok += 1
        else:
            bad.append((s, sid, same))
    print(f"\n按 ID 匹配: {ok} 个吻合 (>=85%)")
    if bad:
        print(f"不吻合 {len(bad)} 个: {bad[:5]}")

    os.close(fd)


if __name__ == "__main__":
    main()
