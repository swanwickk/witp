"""find_step.py — 静态搜索「imul $N」指令，定位某步长数组的访问代码

原理：
  x86 里按步长索引结构是 `imul $0x98,%eax,%eax`（152）这类指令，
  编码为 69 /r id（imul r32, r/m32, imm32），字节序列 `69 C0 98 00 00 00`。
  在 .text 里搜这个模式即可找到所有「按该步长索引」的位置，
  再反汇编那里就能看出读/写了哪些字段。

用法:
  python3 find_step.py 0x98          # Pilot 152
  python3 find_step.py 0x1d0         # 464
"""
import re
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")

TEXT_FOFF = 0x1000
TEXT_VMA = 0x401000
TEXT_SIZE = 0x406b7c


def disasm_at(va, n=40):
    r = subprocess.run(["objdump", "-d", "-j", ".text",
                        f"--start-address={hex(va)}",
                        f"--stop-address={hex(va + n)}", GAME],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if re.match(r"\s+[0-9a-f]+:", l)]


def main():
    step = int(sys.argv[1], 16)
    data = open(GAME, "rb").read()
    body = data[TEXT_FOFF:TEXT_FOFF + TEXT_SIZE]

    hits = []
    # imul r32, r/m32, imm32 : 69 /r id
    # reg 字段为 0..7，modrm 形如 0xC0|(reg<<3)|reg
    for reg in range(8):
        modrm = 0xC0 | (reg << 3) | reg
        pat = bytes([0x69, modrm]) + struct.pack("<I", step)
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            hits.append(TEXT_VMA + i)
            pos = i + 1

    print(f"imul ${step:#x} ({step}) 命中 {len(hits)} 处\n")

    # 对每处反汇编 30 字节，看随后的绝对地址访问
    for va in hits[:30]:
        lines = disasm_at(va, 30)
        txt = " | ".join(l.split("\t")[-1].strip() for l in lines[:5])
        print(f"{va:#x}: {txt}")

    # 收集附近出现的 0x1a1/0x7f7/0xda2 等基址引用
    print("\n附近引用的数据地址（前 30 处）:")
    seen = {}
    for va in hits:
        lines = disasm_at(va, 40)
        for l in lines:
            m = re.search(r"0x(1a1|7f7|da2|252|375|6d4|3f0|598|bba|6da|457|b2a|cf1|ea7|e8a)[0-9a-f]{4}", l)
            if m:
                addr = int("0x" + m.group(0)[2:], 16)
                seen.setdefault(addr, va)
    for addr, va in sorted(seen.items())[:30]:
        print(f"  {addr:#x}  (见 @{va:#x})")


if __name__ == "__main__":
    main()
