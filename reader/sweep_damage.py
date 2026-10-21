"""sweep_damage.py — 系统性扫描损伤字段

策略：每次写一个 4 字节区段（值 11,22,33,44），
     然后截图 OCR Shokaku 行的 Damage 四列，
     一旦出现非 0 就锁定该区段。

界面坐标（TF1 详情）：
  Shokaku 行 y=346
  Damage 四列 x 约 430-500
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, '/root/.hermes/profiles/witp/workspace/witp-reader')
import memrw, witp_obj

SH = 464
BASE = 0x1a14378
MIRROR = 0xb2adcb0
SHIP = 5

# 候选区段（全 0 的连续区）
SEGMENTS = [
    (34, 51), (65, 69), (80, 105), (119, 149), (155, 169),
    (177, 209), (215, 265), (270, 303), (305, 337),
    (339, 360), (362, 463),
]

DISP = ":97"


def shot(p="/tmp/_sw.png"):
    subprocess.run(["import", "-window", "root", "-crop", "1024x768+0+0",
                    "+repage", p], capture_output=True,
                   env=dict(os.environ, DISPLAY=DISP))
    return p


def ocr_damage_row():
    """OCR Shokaku 行的 Damage 区域，返回四个数字。"""
    subprocess.run(["convert", "/tmp/_sw.png", "-crop", "90x14+462+335",
                    "+repage", "-resize", "400%", "/tmp/_swz.png"],
                   capture_output=True)
    r = subprocess.run(["tesseract", "/tmp/_swz.png", "-", "--psm", "7"],
                       capture_output=True, text=True,
                       env=dict(os.environ, LANG="C.UTF-8"))
    return (r.stdout or "").strip()


def write_seg(pid, start, vals):
    for i, v in enumerate(vals):
        for base in (BASE, MIRROR):
            memrw.write_mem(pid, base + SHIP * SH + start + i, bytes([v]))


def clear_seg(pid, start, n):
    for i in range(n):
        for base in (BASE, MIRROR):
            memrw.write_mem(pid, base + SHIP * SH + start + i, bytes([0]))


if __name__ == "__main__":
    pid = witp_obj.game_pid()
    print(f"PID={pid}")
    print("基线 OCR:", ocr_damage_row())

    for (a, b) in SEGMENTS:
        n = min(4, b - a + 1)
        vals = [11, 22, 33, 44][:n]
        write_seg(pid, a, vals)
        time.sleep(0.5)
        shot()
        txt = ocr_damage_row()
        clear_seg(pid, a, n)
        print(f"off{a}-{a+n-1} 写{vals} -> OCR: {txt!r}")
        time.sleep(0.3)
