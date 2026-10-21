"""map_tf_fields.py — 从一个函数区间里提取所有 TF(464B) 结构访问 → 偏移表

反汇编里访问 TF 结构的形式固定为：
    imul $0x1d0,%reg,%reg
    mov/movb/movzbl/movsbl  0x1a14XXX(%reg), ...
其中 0x1a14XXX - 0x1a143ac = 字段偏移。

本脚本把这段区间里所有这样的访问提取出来，按偏移排序，
并标出是读还是写、字节宽度。

用法:
  python3 map_tf_fields.py 0x63f000 0x641000
"""
import re
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")

BASE = 0x1a143ac
SZ = 0x1d0

# 匹配：地址: 字节  mnemonic 0x1a14XXX(%reg...),%dst   或   ... ,0x1a14XXX(%reg)
PAT_READ = re.compile(
    r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} )+\s*(mov|movb|movzbl|movsbl|movzwl|movswl|movw)"
    r"\s+0x([0-9a-f]+)\((%\w+)(?:,%\w+,\d)?\),")
PAT_WRITE = re.compile(
    r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} )+\s*(mov|movb|movw)"
    r"\s+(?:%[a-z0-9]+|\\\$0x[0-9a-f]+),\s*0x([0-9a-f]+)\((%\w+)")


def disasm(lo, hi):
    r = subprocess.run(["objdump", "-d", "-j", ".text",
                        f"--start-address={hex(lo)}",
                        f"--stop-address={hex(hi)}", GAME],
                       capture_output=True, text=True, timeout=300)
    return r.stdout.splitlines()


def main():
    lo = int(sys.argv[1], 16)
    hi = int(sys.argv[2], 16)
    lines = disasm(lo, hi)

    # 先收集 imul $0x1d0 之后的寄存器，用于确认这是 TF 索引寄存器
    tf_regs = set()
    for i, l in enumerate(lines):
        if "imul" in l and "$0x1d0," in l:
            m = re.search(r"imul\s+\$0x1d0,%(e\w+),%(e\w+)", l)
            if m:
                tf_regs.add("%" + m.group(2))

    reads, writes = {}, {}
    for l in lines:
        m = PAT_READ.match(l)
        if m:
            va, mn, disp, reg = int(m.group(1), 16), m.group(2), int(m.group(3), 16), m.group(4)
            if 0x1a14000 <= disp < 0x1a16000:
                off = disp - BASE
                reads.setdefault(off, []).append((va, mn, reg))
        m = PAT_WRITE.match(l)
        if m:
            va, mn, disp = int(m.group(1), 16), m.group(2), int(m.group(3), 16)
            if 0x1a14000 <= disp < 0x1a16000:
                off = disp - BASE
                writes.setdefault(off, []).append((va, mn))

    print(f"区间 {lo:#x}-{hi:#x}")
    print(f"imul $0x1d0 涉及的索引寄存器: {sorted(tf_regs)}\n")

    known = {0x11f: "f287", 0x145: "f325", 0x116: "loadState(350)?",
             0x00: "home?", 0x01: "?"}
    alloff = sorted(set(reads) | set(writes))
    print(f"{'偏移':>6} {'hex':>7} {'读':>4} {'写':>4}  说明")
    for off in alloff:
        if off < 0:
            continue
        r = len(reads.get(off, []))
        w = len(writes.get(off, []))
        note = known.get(off, "")
        print(f"{off:>6} {off:#7x} {r:>4} {w:>4}  {note}")
        for va, mn, reg in reads.get(off, [])[:2]:
            print(f"         读 @{va:#x} {mn} {reg}")
        for va, mn in writes.get(off, [])[:2]:
            print(f"         写 @{va:#x} {mn}")


if __name__ == "__main__":
    main()
