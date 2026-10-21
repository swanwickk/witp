#!/usr/bin/env python3
"""`set-dest` v7（2026-10-03）：**小地图定视野中心 → 反推目标像素 → 精点闭环**。

═══ 为什么不再依赖顶栏探针 ═══
实测：一旦有对象被选中（例如点过小地图/开过面板），**顶栏显示的是"选中对象所在格"**，
不再随地图点击变化 ⇒ 顶栏无法作视野探针（四个探针会读出同一个值）。

═══ 改用小地图做基准（实测成立）═══
· 选点模式下点小地图 → **视野跳到该处并居中**，同时把目的地设为该格。
· 于是「目的地读数 = 视野中心格」，这是**精确**的基准（不用顶栏）。
· 由视野中心 C 反推任意格的屏幕像素：px = 512 + (X - Cx)*W，py = 384 + (X - Cy)*H。
· 为绕开面板遮挡（面板占 x150..870 / y185..560），跳转时**故意把视野中心放到目标以南
  约 7 格**，让目标落在上带 y≈100 处再精点。
· 闭环用**目的地回读**修正（观测量 = 像素↔格的精确对应），不再需要任何视野探针。

小地图映射（初值，实测 4 点最小二乘）：hx ≈ -232.2 + 0.367*mx；hy ≈ -1140.1 + 1.733*my
每次点击都得到一个新的 (mx,my)→hex 样本，用于在线修正该映射。
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
BAND_TOP, BAND_BOT = 100, 600
VIEW_CX, VIEW_CY = 512, 384        # 视野中心像素
W_DEF, H_DEF = 40.0, 38.4          # 实测 px/格
MM = (893, 664, 1021, 765)         # 小地图边界
FOCUS_PT = (950, 60)


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def _onscreen(x, y):
    return 10 <= x <= WIN_W - 10 and 36 <= y <= 640


class MiniMapMap:
    """小地图像素 ↔ 世界格 的线性模型（在线学习）。"""

    def __init__(self):
        self.samples = []          # [(mx,my,hx,hy)]

    def add(self, mx, my, hx, hy):
        self.samples.append((mx, my, hx, hy))

    def _fit(self, k_out, k_in):
        if len(self.samples) < 2:
            return None
        n = len(self.samples)
        xs = [s[k_in] for s in self.samples]
        ys = [s[k_out] for s in self.samples]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        den = sum((xs[i] - mx) ** 2 for i in range(n))
        if abs(den) < 1e-9:
            return None
        b = num / den
        return b, my - b * mx

    def pixel(self, hx, hy):
        fx = self._fit(0, 2) if len(self.samples) >= 2 else None   # mx = f(hx)
        fy = self._fit(1, 3) if len(self.samples) >= 2 else None   # my = f(hy)
        if fx:
            mx = fx[0] * hx + fx[1]
        else:
            mx = (hx + 232.2) / 0.367
        if fy:
            my = fy[0] * hy + fy[1]
        else:
            my = (hy + 1140.1) / 1.733
        mx = max(MM[0] + 2, min(MM[2] - 2, mx))
        my = max(MM[1] + 2, min(MM[3] - 2, my))
        return int(round(mx)), int(round(my))


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
        c.save("/tmp/_v7_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v7_loc.png", "stdout", "--psm", "7"],
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


def mm_jump(tf_id, mx, my, log=print):
    """选点模式下点小地图 → 视野跳到该处并居中，目的地 = 该格。"""
    by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if by is None:
        log("    ✗ 面板打不开")
        return False
    _vnc(bx, by)
    time.sleep(2.0)
    _vnc(mx, my)
    time.sleep(3.2)
    return True


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v7：小地图定中心+精点闭环）===")
    mm = MiniMapMap()
    center = None
    px = py = None

    # ── 阶段1：用小地图把视野中心放到「目标以南 ~7 格」，让目标落在上带 ──
    aim_y = ty + 7
    for i in range(4):
        mx, my = mm.pixel(tx, aim_y)
        log(f"  [{i+1}] 小地图跳转 aim=({tx},{aim_y}) → 像素({mx},{my})")
        if not mm_jump(tf_id, mx, my, log=log):
            return False, None
        d = read_dest_any(tf_id, log=log)
        log(f"        跳后目的地读数（=视野中心）{d}")
        if not d:
            continue
        mm.add(mx, my, d[0], d[1])
        center = d
        px = VIEW_CX + (tx - center[0]) * W_DEF
        py = VIEW_CY + (ty - center[1]) * H_DEF
        log(f"        由中心反推目标像素 ({px:.0f},{py:.0f})")
        if _onscreen(px, py) and not _blocked(px, py):
            break
        # 落在面板里 → 调整 aim（把中心再往南挪，使目标更靠上）
        if py > PANEL[3]:
            aim_y += 5
        elif py < 36:
            aim_y -= 5
        elif _blocked(px, py):
            aim_y += 4

    if center is None or px is None:
        log("  ✗ 无法建立基准")
        return False, None
    if not (_onscreen(px, py) and not _blocked(px, py)):
        log(f"  ✗ 目标像素({px:.0f},{py:.0f})仍不可点")
        return False, None
    px, py = int(px), int(py)

    # ── 阶段2：精点 + 用目的地回读闭环修正 ──
    for attempt in range(5):
        by, bx = TP.open_tf_panel(tf_id, log=(log if attempt == 0 else
                                              (lambda *a: None)))
        if by is None:
            log("  ✗ 面板打不开")
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
            # 由「点(px,py) 得到 got」反推新的视野中心，再重算目标像素
            center = (got[0] - (px - VIEW_CX) / W_DEF,
                      got[1] - (py - VIEW_CY) / H_DEF)
            px = VIEW_CX + (tx - center[0]) * W_DEF
            py = VIEW_CY + (ty - center[1]) * H_DEF
            px, py = int(px), int(py)
            log(f"        反推中心 {tuple(round(v,1) for v in center)} → 新像素 ({px},{py})")
            if not (_onscreen(px, py) and not _blocked(px, py)):
                log("  ✗ 修正后像素不可点，回到阶段1")
                mm.add(*mm.pixel(tx, ty + 7), got[0], got[1])
                aim_y = got[1] + 7
                mx, my = mm.pixel(tx, aim_y)
                if not mm_jump(tf_id, mx, my, log=log):
                    return False, None
                d2 = read_dest_any(tf_id, log=log)
                if d2:
                    center = d2
                    px = int(VIEW_CX + (tx - center[0]) * W_DEF)
                    py = int(VIEW_CY + (ty - center[1]) * H_DEF)
                    log(f"        重跳后中心 {center} → 像素 ({px},{py})")
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 108
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 130
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
