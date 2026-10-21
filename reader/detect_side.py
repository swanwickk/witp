#!/usr/bin/env python3
"""从游戏顶栏自动判定当前是哪一方在玩（权威、无需手工配置）。

依据：顶栏左侧恒定显示 `JAPANESE PLAYER` 或 `ALLIED PLAYER`
（实测该字段存在且稳定；横跨窗口 x=150..700、y=0..26）。

输出（stdout，单行）：JAPAN / ALLIED / UNKNOWN
退出码：0 判定成功；1 未判定
"""
import os
import re
import subprocess
import sys

os.environ.setdefault("DISPLAY", ":98")
FB = "/tmp/_sidedetect.png"


def get_window_offset():
    try:
        out = subprocess.run(
            "DISPLAY=:98 xdotool search --name 'War in the Pacific'",
            shell=True, capture_output=True, timeout=5).stdout.decode()
        wid = out.strip().split("\n")[0]
        info = subprocess.run(f"DISPLAY=:98 xwininfo -id {wid}",
                              shell=True, capture_output=True, timeout=5).stdout.decode()
        # ★2026-10-11 修★ 本环境窗口恒为 (0,0)；旧代码找不到窗口时返回魔法值
        #   (188,150)，会让后续所有裁剪整体偏移 188/150 px ⇒ 读不到顶栏。
        ox, oy = 0, 0
        for ln in info.split("\n"):
            if "Absolute upper-left X:" in ln:
                ox = int(ln.split(":")[-1].strip())
            elif "Absolute upper-left Y:" in ln:
                oy = int(ln.split(":")[-1].strip())
        return ox, oy
    except Exception:
        return 0, 0


def detect(tries=3):
    from PIL import Image, ImageOps
    ox, oy = get_window_offset()
    for _ in range(tries):
        subprocess.run(["import", "-window", "root", FB], capture_output=True)
        try:
            im = Image.open(FB).crop((ox, oy, ox + 1024, oy + 768))
        except Exception:
            continue
        # ★2026-10-11 修★ 旧裁剪框 (100,0)-(760,26) 读不到 PLAYER 字段。
        #   实测该字段在**顶栏左半部**（x≈0..512 区段），且 psm11（稀疏文本）
        #   比 psm7 更稳（实测读出 `J&PANESE PLAYER`）。
        #   改为**整条顶栏 + 左半段**双候选、psm 顺序 11/7/6，并做形近容错。
        best = ""
        for box in ((0, 0, 512, 28), (0, 0, 1024, 28), (0, 0, 640, 28)):
            g = ImageOps.grayscale(im.crop(box))
            for sc in (3, 4):
                z = g.resize((g.width * sc, g.height * sc), Image.LANCZOS)
                z.save("/tmp/_sidebar.png")
                for psm in ("11", "7", "6"):
                    r = subprocess.run(["tesseract", "/tmp/_sidebar.png", "-",
                                        "--psm", psm], capture_output=True)
                    t = r.stdout.decode(errors="replace").upper()
                    if len(t) > len(best):
                        best = t
                    # 形近容错：JAPANESE 常被读成 J&PANESE / JAPANFSE；
                    # ALLIED 常被读成 ALIIED / ALLIFD
                    if re.search(r"J[&AP]{0,2}PAN", t) or "JAPAN" in t:
                        return "JAPAN"
                    if re.search(r"ALLI?E?D", t) or re.search(r"ALLIFD", t):
                        return "ALLIED"
        last = best
    return "UNKNOWN"


if __name__ == "__main__":
    s = detect()
    print(s)
    sys.exit(0 if s != "UNKNOWN" else 1)
