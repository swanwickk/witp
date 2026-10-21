"""find_xref.py — 在 exe 中静态搜索「引用了某个地址」的指令

原理：
  x86 里引用字符串常量通常是 `push $0x82c750` / `mov $0x82c750,%eax`，
  立即数以 4 字节小端出现。直接在文件里搜这个 4 字节模式即可找到所有引用点，
  完全不需要运行游戏、不需要任何界面操作。

用法:
  python3 find_xref.py 0x82c750 0x82c764
"""
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")

# PE 节表：从 objdump 拿各节的 VA/文件偏移，才能把文件偏移换成 VA
def sections():
    r = subprocess.run(["objdump", "-h", GAME], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) >= 7 and p[0].isdigit():
            # Idx Name Size VMA LMA FileOff Algn
            try:
                name = p[1]
                size = int(p[2], 16)
                vma = int(p[3], 16)
                foff = int(p[5], 16)
                out.append((name, size, vma, foff))
            except ValueError:
                pass
    return out


def find(addrs):
    data = open(GAME, "rb").read()
    secs = sections()
    print("节表:")
    for n, s, v, f in secs:
        print(f"  {n:<10} size={s:#x} vma={v:#x} foff={f:#x}")
    print()

    for addr in addrs:
        pat = struct.pack("<I", addr)
        hits = []
        pos = 0
        while True:
            i = data.find(pat, pos)
            if i < 0:
                break
            # 文件偏移 → VA
            va = None
            for n, s, v, f in secs:
                if f <= i < f + s:
                    va = v + (i - f)
                    secname = n
                    break
            hits.append((i, va, secname if va else "?"))
            pos = i + 1
        print(f"=== {addr:#x} 的引用 ({len(hits)} 处) ===")
        for foff, va, sec in hits:
            print(f"  文件偏移 {foff:#08x}  →  VA {va if va else 0:#x}  [{sec}]")
        print()


if __name__ == "__main__":
    addrs = [int(a, 16) for a in sys.argv[1:]] or [0x82c750, 0x82c764]
    find(addrs)
