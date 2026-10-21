#!/usr/bin/env python3
"""`set-dest` v11：**Jump Map 当方向摇杆（相对定位）→ 上带精点**。

═══ 为什么是"相对"而不是"绝对" ═══
实测：Jump Map 是**局部地图**，且**每次点击后都会重新居中到新视野**。
所以"某个固定像素 ↔ 某个固定格"的关系**不成立**（实测三个相差 100px 的点击
读回同一个格 122,108 —— 因为每次点击后地图重新居中，映射漂移了）。
⇒ 只能用**相对**用法：以 Jump Map 中心像素为"原点"，向目标方向偏移若干像素点击，
   视野就朝那个方向移动；偏移量按实测比例换算（y 向 2.57 px/格、x 向约 9 px/格）。
每次点击的读回值 = 新的视野中心 ⇒ 天然形成闭环，迭代逼近。
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset            # noqa: E402
from lib import tfpanel as TP                        # noqa: E402
from PIL import Image                                # noqa: E402

import os as _os
_os.environ.setdefault("DISPLAY", ":98")

WIN_W, WIN_H = 1024, 768
PANEL = (150, 185, 870, 560)
VIEW_CX, VIEW_CY = 512, 384
W_DEF, H_DEF = 40.0, 38.4
MM = (893, 664, 1021, 765)
MM_CX = (MM[0] + MM[2]) // 2          # 957
MM_CY = (MM[1] + MM[3]) // 2          # 714
PX_PER_HEX_Y = 2.57
PX_PER_HEX_X = 9.0
FOCUS_PT = (950, 60)
TOP_BAND_Y = 100


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.7):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def _onscreen(x, y):
    return 10 <= x <= WIN_W - 10 and 36 <= y <= 640


OCR_FIX = str.maketrans({
    "i": "1", "l": "1", "I": "1", "|": "1", "!": "1",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2",
    "G": "6", "T": "7", "q": "9", "g": "9"})


def parse_list_location(t):
    t2 = t.translate(OCR_FIX)
    m = re.search(r"(?:mve\s*t0|mvet0|m0vet0|mv\s*t0|mve\s*t)"
                  r"\D{0,3}(\d{2,3})\D{1,3}(\d{2,3})", t2)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        if 10 <= x <= 250 and 10 <= y <= 250:
            return (x, y)
    return None


def read_dest_from_list(tf_id, log=None, tries=2):
    from lib.setdest import find_tf_row
    for _ in range(tries):
        r = find_tf_row(tf_id, log=None)
        if r is None:
            TP.reset_to_map(log=None)
            _vnc(*FOCUS_PT)
            time.sleep(0.8)
            _key("t")
            time.sleep(3.2)
            r = find_tf_row(tf_id, log=None)
        if r is None:
            continue
        im = TP._shot()
        c = im.crop((690, r - 9, 1024, r + 9))
        c = c.resize((c.width * 6, c.height * 6), Image.LANCZOS)
        c.save("/tmp/_v11_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v11_loc.png", "stdout", "--psm", "7"],
                            capture_output=True)
        got = parse_list_location(rr.stdout.decode(errors="replace"))
        if got:
            return got
        time.sleep(0.6)
    return None


def read_dest_any(tf_id, log=None):
    from collections import Counter
    got = read_dest_from_list(tf_id, log=log)
    if got:
        return got
    by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if by is None:
        return None
    seen = []
    for _ in range(3):
        v = TP.read_panel_hex(tries=2, log=None)
        if v:
            seen.append(v)
    return Counter(seen).most_common(1)[0][0] if seen else None


def mm_click(tf_id, mx, my, log=None):
    by = None
    for _try in range(3):
        by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if by is not None:
            break
        time.sleep(1.2)
    if by is None:
        if log:
            log("    ✗ 面板打不开（3 次）")
        return None
    _vnc(bx, by)
    time.sleep(2.0)
    _vnc(mx, my)
    time.sleep(3.2)
    return read_dest_any(tf_id, log=log)


def probe_center(tf_id, log=None):
    """以 Jump Map 中心像素点击 = 不动视野，只读回当前视野中心。"""
    TP.reset_to_map(log=None)
    return mm_click(tf_id, MM_CX, MM_CY, log=log)


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v11：JumpMap 摇杆）===")
    want_cy = ty + (VIEW_CY - TOP_BAND_Y) / H_DEF      # 中心应在目标以南约 7.4 格
    center = probe_center(tf_id, log=log)
    log(f"  起点视野中心 {center}")
    if center is None:
        return False, None

    for i in range(6):
        err_x = tx - center[0]
        err_y = want_cy - center[1]
        log(f"  [{i+1}] 中心 {center} 需移 ({err_x:+.0f},{err_y:+.0f}) 格")
        if abs(err_y) <= 2 and abs(err_x) <= 3:
            break
        dx = int(max(-62, min(62, err_x * PX_PER_HEX_X)))
        dy = int(max(-48, min(48, err_y * PX_PER_HEX_Y)))
        mx, my = MM_CX + dx, MM_CY + dy
        log(f"        摇杆偏移 ({dx:+d},{dy:+d}) → 点 ({mx},{my})")
        TP.reset_to_map(log=None)
        d = mm_click(tf_id, mx, my, log=log)
        log(f"        → 新中心 {d}")
        if not d:
            break
        center = d

    # ── 精点 ──
    px = int(VIEW_CX + (tx - center[0]) * W_DEF)
    py = int(VIEW_CY + (ty - center[1]) * H_DEF)
    log(f"  目标像素 ({px},{py})")
    for attempt in range(4):
        if not (_onscreen(px, py) and not _blocked(px, py)):
            log(f"  [{attempt+1}] 像素({px},{py})不可点 → 微调中心")
            err_y = want_cy - center[1]
            dy = int(max(-48, min(48, err_y * PX_PER_HEX_Y)))
            if abs(dy) < 3:
                dy = 6 if py > PANEL[3] else -6
            TP.reset_to_map(log=None)
            d = mm_click(tf_id, MM_CX, MM_CY + dy, log=log)
            if not d:
                break
            center = d
            px = int(VIEW_CX + (tx - center[0]) * W_DEF)
            py = int(VIEW_CY + (ty - center[1]) * H_DEF)
            continue
        by, bx = TP.open_tf_panel(tf_id, log=(log if attempt == 0 else
                                              (lambda *a: None)))
        if by is None:
            return False, None
        _vnc(bx, by)
        time.sleep(2.0)
        _vnc(px, py)
        time.sleep(3.0)
        got = read_dest_any(tf_id, log=log)
        log(f"  [{attempt+1}] 点({px},{py}) → 回读 {got}")
        if got == (tx, ty):
            log("  ✓ 确认命中")
            return True, got
        if got:
            center = (got[0] - (px - VIEW_CX) / W_DEF,
                      got[1] - (py - VIEW_CY) / H_DEF)
            px = int(VIEW_CX + (tx - center[0]) * W_DEF)
            py = int(VIEW_CY + (ty - center[1]) * H_DEF)
            log(f"        反推中心 {tuple(round(v,1) for v in center)} → 像素 ({px},{py})")
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    _tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    _tx = int(sys.argv[2]) if len(sys.argv) > 2 else 109
    _ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(_tf, _tx, _ty)
    print("RESULT", ok, h)
