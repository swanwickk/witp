"""find_tf_table.py — 由 TF 名称表反推 TF 记录表

发现：名称是 20 字节定长数组，TF7 名在索引 3。
     若 TF 记录也是定长数组且与名称同序，则 TF7 记录 = 基址 + 3*步长。

做法：
  1. 找到名称数组起点（第一个 TF 名之前）
  2. 枚举 464 步长候选基址，要求 base + 3*464 + 88 == 91（TF7 flagship）
  3. 再用其他 TF 的名称索引与 flagship 交叉验证
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

NAME_ADDR = 0x2de7a4c
NAME_SZ = 20
TF7_IDX = 3
TF7_FLAG = 91
SZ = 464


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
    fd = memrw.open_mem(pid)

    # 1. 找名称表起点：向前找连续 20 字节块
    start = NAME_ADDR
    while True:
        prev = memrw.read_mem(pid, start - NAME_SZ, NAME_SZ, fd)
        if not prev:
            break
        txt = prev.rstrip(b"\0")
        if txt and all(32 <= c < 127 for c in txt):
            start -= NAME_SZ
        else:
            break
    print(f"名称表起点 ≈ {start:#x}")

    # 2. 列出名称表
    names = []
    a = start
    for i in range(60):
        d = memrw.read_mem(pid, a + i * NAME_SZ, NAME_SZ, fd)
        if not d:
            break
        txt = d.rstrip(b"\0").decode("ascii", "replace")
        if not txt or not all(32 <= ord(c) < 127 for c in txt):
            break
        names.append((i, txt))
    print(f"名称表 {len(names)} 条:")
    for i, n in names[:12]:
        print(f"  [{i}] {n!r}")

    # 3. 找 TF 记录表：base + 3*464 + 88 == 91
    print("\n=== 搜索 TF 记录表基址 ===")
    target = TF7_FLAG
    cands = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < 1024 * 1024:
            continue
        blob = memrw.read_mem(pid, s, e - s, fd)
        if not blob:
            continue
        pat = struct.pack("<I", target)
        pos = 0
        while True:
            i = blob.find(pat, pos)
            if i < 0:
                break
            pos = i + 1
            # 假设这是 slot TF7_IDX 的 flagship
            b = s + i - 88 - TF7_IDX * SZ
            if b < s or b + 4 * SZ > s + len(blob):
                continue
            # 验证 slot0..3 都有合理 flagship
            good = 0
            for k in range(0, 8):
                off = (i - 88 - TF7_IDX * SZ) + k * SZ + 88
                if 0 <= off < len(blob) - 4:
                    v = struct.unpack_from("<I", blob, off)[0]
                    if 1 <= v <= 8000:
                        good += 1
            if good >= 4:
                cands.append((b, good))
    print(f"候选 {len(cands)} 个:")
    for b, g in cands[:10]:
        print(f"  {b:#010x}  连续合理槽={g}")

    os.close(fd)


if __name__ == "__main__":
    main()
