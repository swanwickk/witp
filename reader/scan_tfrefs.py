"""scan_tfrefs.py — 静态扫描 exe 中所有引用 TF 数组基址的指令

原理：
  x86 指令形如 `mov 0x1a14XXX(%eax),%cx`，
  其中 disp32 就是绝对地址（当没有基址寄存器时为绝对寻址）。
  我们直接在 .text 里搜「0x1a14xxxx 范围的 4 字节小端」，
  每命中一次就反汇编那 16 字节，看它读的是哪个偏移。

这完全不需要运行游戏、不需要界面操作 —— 纯静态。

用法:
  python3 scan_tfrefs.py            # 扫 0x1a14000-0x1a15000
  python3 scan_tfrefs.py 0x1a14000 0x1a15000
"""
import re
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")


def sections():
    r = subprocess.run(["objdump", "-h", GAME], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) >= 7 and p[0].isdigit():
            try:
                out.append((p[1], int(p[2], 16), int(p[3], 16), int(p[5], 16)))
            except ValueError:
                pass
    return out


def disasm_at(va, n=40):
    r = subprocess.run(["objdump", "-d", "-j", ".text",
                        f"--start-address={hex(va)}",
                        f"--stop-address={hex(va + n)}", GAME],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if re.match(r"\s+[0-9a-f]+:", l)]


def main():
    lo = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x1a14000
    hi = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x1a15000
    data = open(GAME, "rb").read()
    secs = sections()
    text = [s for s in secs if s[0] == ".text"][0]
    _n, size, vma, foff = text
    body = data[foff:foff + size]

    hits = []
    for addr in range(lo, hi):
        pat = struct.pack("<I", addr)
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            hits.append((vma + i, addr))
            pos = i + 1

    print(f"扫描 {lo:#x}-{hi:#x}：命中 {len(hits)} 处\n")

    # 按「被引用的地址」分组，反推偏移
    groups = {}
    for va, addr in hits:
        groups.setdefault(addr, []).append(va)

    BASE_CAND = [0x1a143ac, 0x1a14ae0, 0x1a144c2, 0x1a144cb, 0x1a144f1]
    for addr in sorted(groups):
        offs = {b: addr - b for b in BASE_CAND}
        print(f"地址 {addr:#x}  被 {len(groups[addr])} 条指令引用")
        for b, o in offs.items():
            if 0 <= o < 0x1d0:
                print(f"    若基址={b:#x} → TF 偏移 {o} ({o:#x})")
        for va in groups[addr][:3]:
            for l in disasm_at(va - 6, 18):
                print("      " + l.strip())
        print()


if __name__ == "__main__":
    main()
