#!/usr/bin/env python3
"""`set-dest` v10：**Jump Map 当场标定 → 把视野中心放到目标以南 → 上带精点**。

═══ 实测事实（决定设计）═══
· Jump Map（右下角小地图）是**局部地图**，不是全太平洋总览：
  实测某次它只覆盖 x109..123、y106..145，x 向 9.17 px/格、y 向 2.57 px/格。
  ⇒ **映射随视野变化，必须当场标定**（点两点读回即可拟合）。
· 它的 y 精度 ±1.3 格、x 精度 ±4.5 格。上带（y36..180）横跨全宽，
  故 x 误差无害 ⇒ **只要把视野中心放到目标以南约 7 格，目标就落进上带可点**。
· 选点模式下点 Jump Map：视野居中于该格 + 目的地设为该格（回读 = 视野中心）。
· 手册 4.2.5 的「拖拽滚地图」在 Wine 下实测无效（三种手势均不动）；
  面板也不能拖动。⇒ 唯一可靠的定位手段就是 Jump Map。
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
FOCUS_PT = (950, 60)
TOP_BAND_Y = 100                 # 上带目标落点


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
        c.save("/tmp/_v10_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v10_loc.png", "stdout", "--psm", "7"],
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
    """开面板 → 进选点模式 → 点 Jump Map → 回读（= 新视野中心）。"""
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


def calib_jumpmap(tf_id, log=print):
    """当场标定 Jump Map：返回 (hx = a + b*mx, hy = c + d*my) 或 None。"""
    samples = []
    for p in [(905, 690), (1005, 745), (1005, 690)]:
        TP.reset_to_map(log=None)
        d = mm_click(tf_id, p[0], p[1], log=log)
        if log:
            log(f"    标定点 {p} → {d}")
        if d:
            samples.append((p, d))
        if len(samples) >= 3:
            break
    if len(samples) < 2:
        return None

    def fit(k_out, k_in):
        n = len(samples)
        xs = [s[0][k_in] for s in samples]
        ys = [s[1][k_out] for s in samples]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        den = sum((xs[i] - mx) ** 2 for i in range(n))
        if abs(den) < 1e-9:
            return None
        b = num / den
        return b, my - b * mx

    fx = fit(0, 0)
    fy = fit(1, 1)
    if not fx or not fy:
        return None
    if log:
        log(f"    JumpMap 标定: hx={fx[1]:.1f}{fx[0]:+.3f}*mx  "
            f"hy={fy[1]:.1f}{fy[0]:+.3f}*my")
    return fx, fy


def mm_pixel_for(fx, fy, hx, hy):
    mx = (hx - fx[1]) / fx[0] if abs(fx[0]) > 1e-9 else MM[0]
    my = (hy - fy[1]) / fy[0] if abs(fy[0]) > 1e-9 else MM[1]
    return (int(round(max(MM[0] + 2, min(MM[2] - 2, mx)))),
            int(round(max(MM[1] + 2, min(MM[3] - 2, my)))))


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v10：JumpMap 定位）===")
    center = None
    px = py = None
    for round_i in range(3):
        cal = calib_jumpmap(tf_id, log=log)
        if cal is None:
            log("  ✗ JumpMap 标定失败")
            return False, None
        fx, fy = cal
        # 目标要落进上带 ⇒ 视野中心放到目标以南 (VIEW_CY-TOP_BAND_Y)/H 格
        off = (VIEW_CY - TOP_BAND_Y) / H_DEF          # ≈7.4 格
        cmx, cmy = mm_pixel_for(fx, fy, tx, ty + off)
        log(f"  [{round_i+1}] 把视野中心放到 ({tx},{ty + off:.0f}) → "
            f"JumpMap 像素 ({cmx},{cmy})")
        TP.reset_to_map(log=None)
        d = mm_click(tf_id, cmx, cmy, log=log)
        log(f"        → 实际视野中心 {d}")
        if not d:
            continue
        center = d
        px = VIEW_CX + (tx - center[0]) * W_DEF
        py = VIEW_CY + (ty - center[1]) * H_DEF
        log(f"        目标像素 ({px:.0f},{py:.0f})")
        if _onscreen(px, py) and not _blocked(px, py):
            break

    if center is None:
        return False, None
    for attempt in range(4):
        if not (_onscreen(px, py) and not _blocked(px, py)):
            log(f"  [{attempt+1}] 像素({px:.0f},{py:.0f})不可点 → 再定位")
            cal = calib_jumpmap(tf_id, log=lambda *a: None)
            if cal is None:
                return False, None
            fx, fy = cal
            off = (VIEW_CY - TOP_BAND_Y) / H_DEF
            cmx, cmy = mm_pixel_for(fx, fy, tx, ty + off)
            TP.reset_to_map(log=None)
            d = mm_click(tf_id, cmx, cmy, log=log)
            if not d:
                continue
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
        _vnc(int(px), int(py))
        time.sleep(3.0)
        got = read_dest_any(tf_id, log=log)
        log(f"  [{attempt+1}] 点({px:.0f},{py:.0f}) → 回读 {got}")
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
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 109
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
