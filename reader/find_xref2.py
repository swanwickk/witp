"""find_xref2.py — 正确版：字符串 VA 换算 + 交叉引用搜索

★ 之前的 bug：打印时没加 #x，把十进制当十六进制搜，所以 0 命中。
  .rdata: VMA 0x808000, FileOff 0x408000
  .data : VMA 0x851000, FileOff 0x451000
  .text : VMA 0x401000, FileOff 0x1000

用法:
  python3 find_xref2.py "Follow Task Force"
  python3 find_xref2.py --all
"""
import re
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")

SECS = [
    (".text", 0x406b7c, 0x401000, 0x1000),
    (".rdata", 0x489fa, 0x808000, 0x408000),
    (".data", 0xe000, 0x851000, 0x451000),
    (".rsrc", 0x48b38, 0xf0a7000, 0x45f000),
]


def off2va(off):
    for name, size, vma, foff in SECS:
        if foff <= off < foff + size:
            return vma + (off - foff), name
    return None, None


def find_string(s):
    data = open(GAME, "rb").read()
    pat = s.encode() + b"\x00"
    out = []
    pos = 0
    while True:
        i = data.find(pat, pos)
        if i < 0:
            break
        va, sec = off2va(i)
        if va:
            out.append((i, va, sec))
        pos = i + 1
    return out


def xref(va):
    """在 .text 里搜 `push $va` / `mov $va,%reg` 的 4 字节立即数"""
    data = open(GAME, "rb").read()
    body = data[0x1000:0x1000 + 0x406b7c]
    pat = struct.pack("<I", va)
    hits = []
    pos = 0
    while True:
        i = body.find(pat, pos)
        if i < 0:
            break
        hits.append(0x401000 + i)
        pos = i + 1
    return hits


def disasm_at(va, n=48):
    r = subprocess.run(["objdump", "-d", "-j", ".text",
                        f"--start-address={hex(va)}",
                        f"--stop-address={hex(va + n)}", GAME],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if re.match(r"\s+[0-9a-f]+:", l)]


def report(s):
    print(f"=== {s!r} ===")
    locs = find_string(s)
    if not locs:
        print("  字符串未找到")
        return
    for foff, va, sec in locs:
        print(f"  字符串 @ file {foff:#x}  VA {va:#x}  [{sec}]")
        hits = xref(va)
        print(f"    引用 {len(hits)} 处: {[hex(h) for h in hits[:6]]}")
        for h in hits[:3]:
            print(f"    --- 反汇编 @{h:#x} ---")
            for l in disasm_at(h - 8, 40)[:8]:
                print(f"      {l.strip()[:78]}")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--all":
        report(sys.argv[1])
    else:
        for s in ("Follow Task Force", "Meet Task Force", "Set Patrol Zone",
                  "Follow TF", "Meet TF", "Patrol Zone"):
            report(s)
