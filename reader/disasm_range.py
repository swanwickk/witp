#!/usr/bin/env python3
"""disasm_range.py — 用 objdump 反汇编指定 VA 区间（自动处理路径中的单引号）"""
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")


def disasm(start, stop, filt=None):
    cmd = ["objdump", "-d", "-j", ".text",
           f"--start-address={hex(start)}",
           f"--stop-address={hex(stop)}", GAME]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    lines = r.stdout.splitlines()
    if filt:
        lines = [l for l in lines if any(f.lower() in l.lower() for f in filt)]
    return lines


if __name__ == "__main__":
    start = int(sys.argv[1], 16)
    stop = int(sys.argv[2], 16)
    filt = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    out = disasm(start, stop, filt)
    print("\n".join(out[:200]))
    print(f"\n[{len(out)} lines]")
