"""find_leader_ref.py — 找「用 TF 字段索引 Leader 数组」的代码

Leader 数组：基址 0x252b3f8，步长 0xb4 (180)
TF 数组：基址 0x6da5148，步长 0x22c (556)

模式：
    imul $0x22c,%reg,%reg        ; TF 索引
    movzbl/movswl 0x6da5XXX(%reg) ; 读 TF 某字段 → leader 索引
    imul $0xb4,%reg,%reg         ; Leader 索引
    add  $0x252b3f8,%reg         ; Leader 基址

做法：搜所有 `imul $0xb4` 的位置，往前 40 字节内找 0x6da5XXX 引用。
"""
import re
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")
TF_BASE = 0x6da5148
TF_SZ = 0x22c


def disasm(lo, hi):
    r = subprocess.run(["objdump", "-d", "-j", ".text",
                        f"--start-address={hex(lo)}",
                        f"--stop-address={hex(hi)}", GAME],
                       capture_output=True, text=True)
    return r.stdout.splitlines()


def main():
    data = open(GAME, "rb").read()
    body = data[0x1000:0x1000 + 0x406b7c]

    # 找 imul $0xb4 的所有位置（69 /r imm32）
    hits = []
    for reg in range(8):
        modrm = 0xC0 | (reg << 3) | reg
        pat = bytes([0x69, modrm]) + struct.pack("<I", 0xb4)
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            hits.append(0x401000 + i)
            pos = i + 1
    print(f"imul $0xb4 (Leader 步长) 命中 {len(hits)} 处\n")

    found = {}
    for va in hits:
        lines = disasm(va - 64, va + 24)
        # 在附近找 TF 字段访问
        for l in lines:
            m = re.search(r"0x6da5([0-9a-f]{3})\(", l)
            if not m:
                continue
            off = int("0x6da5" + m.group(1), 16) - TF_BASE
            if 0 <= off < 556:
                found.setdefault(off, []).append(va)

    print(f"附近有 TF 字段访问的 leader 索引点：{len(found)} 个偏移")
    for off in sorted(found):
        print(f"  TF off{off:>3}: {len(found[off])} 处 → {[hex(v) for v in found[off][:4]]}")


if __name__ == "__main__":
    main()
