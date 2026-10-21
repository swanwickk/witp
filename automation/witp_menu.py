#!/usr/bin/env python3
"""WitP-AE 菜单导航器 —— 用 OCR 词框定位按钮，绝不复用固定坐标。

铁律（来自本会话 9 次游戏退出的教训）：
  ① 每换一屏必须先截图，再按 OCR 找到的**文字位置**点击；
  ② 严禁复用固定坐标（主菜单 / 存档菜单 / 载入菜单布局各不相同）；
  ③ 未截图确认的屏上，**禁止点击 y > 690 的区域**（右下角是退出/返回类控件）。

用法：
  python3 witp_menu.py list                 # 列出当前屏的 OCR 词与坐标
  python3 witp_menu.py find "LOAD A SAVED GAME"
  python3 witp_menu.py click "LOAD A SAVED GAME" [--allow-danger]
  python3 witp_menu.py clickxy X Y [--allow-danger]
  python3 witp_menu.py shot                 # 只截图并打印识别到的屏名
"""
import os
import re
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
SHOT = "/tmp/witp_shot.png"
ENV = dict(os.environ, DISPLAY=":98", WINEPREFIX="/root/.wine-witp", HOME="/root")
VNC_CLICK = f"{WS}/witp_vncclick.py"
DANGER_Y = 690  # y 超过此值视为退出/返回危险区


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, env=ENV)


def offset():
    """游戏窗口在屏幕上的偏移 (ox, oy)。无名窗口按几何特征兜底。"""
    wid = sh("xdotool search --name 'War in the Pacific' | head -1").stdout.strip()
    brd = (0, 0)
    if not wid:
        r2 = sh(r"xwininfo -root -children | grep -E '^\s+0x[0-9a-f]+'")
        for line in r2.stdout.splitlines():
            m = re.search(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
            if m and 1020 <= int(m.group(1)) <= 1032 and 764 <= int(m.group(2)) <= 792:
                wid = line.split()[0]
                if int(m.group(1)) > 1024:
                    brd = (1, 20)
                break
    if not wid:
        return None
    r3 = sh(f"xwininfo -id {wid}")
    ox = oy = None
    for l in r3.stdout.splitlines():
        if "Absolute upper-left X" in l:
            ox = int(l.split()[-1])
        if "Absolute upper-left Y" in l:
            oy = int(l.split()[-1])
    if ox is None or oy is None:
        return None
    return ox + brd[0], oy + brd[1]


def shot():
    off = offset()
    if not off:
        print("[nav] ✗ 找不到游戏窗口")
        return False
    ox, oy = off
    sh("import -window root /tmp/_full.png")
    sh(f"convert /tmp/_full.png -crop 1024x768+{ox}+{oy} +repage {SHOT}")
    wh = sh(f"identify -format '%wx%h' {SHOT}").stdout.strip()
    if wh != "1024x768":
        print(f"[nav] ✗ 截图尺寸异常 {wh}")
        return False
    return True


def words(scale=200):
    """OCR 词框 → [(text, x, y, w, h)]，坐标已换算回 1024x768。"""
    sh(f"convert {SHOT} -resize {scale}% -colorspace Gray -normalize /tmp/_g.png")
    r = sh("tesseract /tmp/_g.png - --psm 11 tsv")
    out = []
    for line in r.stdout.splitlines()[1:]:
        p = line.split("\t")
        if len(p) < 12:
            continue
        txt = p[11].strip()
        if not txt:
            continue
        try:
            x, y, w, h = int(p[6]), int(p[7]), int(p[8]), int(p[9])
        except ValueError:
            continue
        k = 100.0 / scale
        out.append((txt, x * k, y * k, w * k, h * k))
    return out


def find(phrase, ws=None):
    """在 OCR 词里找短语（连续同行匹配），返回中心点 (x, y) 或 None。"""
    ws = ws if ws is not None else words()
    want = [t.upper() for t in phrase.split()]
    n = len(want)
    for i in range(len(ws) - n + 1):
        seg = ws[i:i + n]
        if all(seg[j][0].upper().strip(".,;:!|") == want[j] for j in range(n)):
            ys = [s[2] for s in seg]
            if max(ys) - min(ys) > 12:  # 不在同一行
                continue
            x0 = min(s[1] for s in seg)
            x1 = max(s[1] + s[3] for s in seg)
            y0 = min(s[2] for s in seg)
            y1 = max(s[2] + s[4] for s in seg)
            return (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return None


def click(x, y, mode="click", allow_danger=False):
    if y > DANGER_Y and not allow_danger:
        print(f"[nav] ⛔ 拒绝点击 y={y:.0f}（>{DANGER_Y} 危险区，右下角是退出/返回控件）。"
              f"确需点击请加 --allow-danger")
        return False
    off = offset()
    if not off:
        print("[nav] ✗ 找不到游戏窗口")
        return False
    ox, oy = off
    sh(f"python3 {VNC_CLICK} {int(x) + ox} {int(y) + oy} {mode}")
    print(f"[nav] ✓ {mode} 游戏坐标({int(x)},{int(y)}) → 屏幕({int(x)+ox},{int(y)+oy})")
    return True


def screen_name(ws):
    txt = " ".join(t for t, *_ in ws).upper()
    if "FINAL SCORE" in txt or "VICTORY LEVEL" in txt:
        return "终局比分屏"
    if "SAVE GAME" in txt or "SELECT SAVE GAME" in txt:
        return "存档菜单"
    if "LOAD" in txt and "GAME" in txt:
        return "载入菜单"
    if "MAIN MENU SCREEN" in txt or "SCENARIO SELECTION" in txt:
        return "主菜单"
    if "PREFERENCES" in txt:
        return "主菜单"
    return "未知/地图"


def main():
    args = sys.argv[1:]
    if not args or args[0] == "shot":
        if not shot():
            return 1
        ws = words()
        print(f"[nav] 当前屏：{screen_name(ws)}   （OCR 词数 {len(ws)}）")
        return 0
    if args[0] == "list":
        if not shot():
            return 1
        ws = words()
        print(f"[nav] 当前屏：{screen_name(ws)}")
        for t, x, y, w, h in ws:
            tag = "  ⛔危险区" if y > DANGER_Y else ""
            print(f"   {t:<22} 中心≈({x + w/2:.0f},{y + h/2:.0f}){tag}")
        return 0
    if args[0] == "find":
        if not shot():
            return 1
        p = find(args[1])
        print(f"[nav] {'找到 ' + str(tuple(round(v) for v in p)) if p else '未找到'} 「{args[1]}」")
        return 0 if p else 1
    if args[0] == "click":
        if not shot():
            return 1
        ws = words()
        p = find(args[1], ws)
        if not p:
            print(f"[nav] ✗ 当前屏（{screen_name(ws)}）上找不到「{args[1]}」")
            return 1
        return 0 if click(p[0], p[1], allow_danger="--allow-danger" in args) else 1
    if args[0] == "clickxy":
        return 0 if click(float(args[1]), float(args[2]),
                          allow_danger="--allow-danger" in args) else 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
