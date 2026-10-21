#!/usr/bin/env python3
"""`set-dest` v9（2026-10-03）：小地图定中心 → 方向键微调 → 主图精点。

═══ 三段式（全部基于实测）═══
① **小地图跳转**：选点模式下点小地图 → 视野**居中于该格**，且回读值就是该格
   （实测 (955,730)→(122,124)、(903,746)→(109,144)）。迭代 2~3 次即可让视野中心
   落在目标 ±3 格内。
② **方向键微调**：目标往往正好落在面板遮挡区（面板占屏幕中部 x150..870/y185..560）。
   方向键每次精确移 2 格，把它挪进「上带 y≈100」再点。
   ★实测★ 方向键前几次会被吞（焦点未就绪）⇒ 必须**逐次校验**（画面指纹变化）并重试。
   方向：按 down（视野南移）→ 固定像素处的 hex y 增大 → **目标的屏幕 y 减小**。
③ **精点 + 目的地回读闭环**：观测量 = 像素↔格的精确对应，用它修正视野中心再点。
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
VIEW_CX, VIEW_CY = 512, 384
W_DEF, H_DEF = 40.0, 38.4
MM = (893, 664, 1021, 765)
FOCUS_PT = (950, 60)
KEY_ROWS = 2                     # 方向键每次 2 格（实测）


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.75):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def _onscreen(x, y):
    return 10 <= x <= WIN_W - 10 and 36 <= y <= 640


def _hash():
    import hashlib
    return hashlib.md5(TP._shot().tobytes()).hexdigest()[:12]


def nudge(dx_cells, dy_cells, log=None):
    """方向键微调视野，**逐次校验**（前几次常被吞）。返回实际格数。"""
    plan = []
    if dy_cells:
        plan.append(("down" if dy_cells > 0 else "up", int(abs(dy_cells))))
    if dx_cells:
        plan.append(("right" if dx_cells > 0 else "left", int(abs(dx_cells))))
    done = 0
    for key, cells in plan:
        n = max(1, round(cells / KEY_ROWS))
        for _ in range(n):
            for _try in range(3):
                b = _hash()
                _key(key)
                if _hash() != b:
                    done += KEY_ROWS
                    break
    if log:
        log(f"    方向键微调完成（约 {done} 格）")
    return done


class MiniMapMap:
    def __init__(self):
        self.samples = []

    def add(self, mx, my, hx, hy):
        self.samples.append((mx, my, hx, hy))

    def _fit(self, k_out, k_in):
        n = len(self.samples)
        if n < 2:
            return None
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
        fx = self._fit(0, 2) if len(self.samples) >= 2 else None
        fy = self._fit(1, 3) if len(self.samples) >= 2 else None
        mx = (fx[0] * hx + fx[1]) if fx else (hx + 232.2) / 0.367
        my = (fy[0] * hy + fy[1]) if fy else (hy + 1140.1) / 1.733
        return (int(round(max(MM[0] + 2, min(MM[2] - 2, mx)))),
                int(round(max(MM[1] + 2, min(MM[3] - 2, my)))))


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
        c.save("/tmp/_v9_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v9_loc.png", "stdout", "--psm", "7"],
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
    """选点模式点小地图。★面板打开常因瞬时坏帧失败 ⇒ 重试 3 次★"""
    for _try in range(3):
        by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if by is not None:
            break
        time.sleep(1.2)
    else:
        if log:
            log("    ✗ 面板打不开（重试 3 次）")
        return False
    _vnc(bx, by)
    time.sleep(2.0)
    _vnc(mx, my)
    time.sleep(3.2)
    return True


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v9：小地图+方向键+精点）===")
    mm = MiniMapMap()
    center = None
    mx, my = mm.pixel(tx, ty)
    # ★只做 2 轮★ 实测小地图精度仅 ±5 格左右（像素改 4px 结果都不变），
    #   再多轮也不会收敛；粗跳到 ±5 格后交给「方向键微调 + 主图精点」。
    for i in range(2):
        log(f"  [{i+1}] 小地图粗跳 ({mx},{my})")
        TP.reset_to_map(log=None)
        if not mm_jump(tf_id, mx, my, log=log):
            log("    ✗ 面板打不开")
            return False, None
        d = read_dest_any(tf_id, log=log)
        log(f"        → 中心/目的地 {d}")
        if not d:
            continue
        mm.add(mx, my, d[0], d[1])
        center = d
        err_x, err_y = tx - d[0], ty - d[1]
        if abs(err_x) + abs(err_y) <= 2:
            break
        # ★按误差直接修正小地图像素★（一个样本不足以拟合，直接用已知斜率换算）
        #   实测斜率：x 方向 0.367 格/像素，y 方向 1.733 格/像素
        mx = int(round(max(MM[0] + 2, min(MM[2] - 2, mx + err_x / 0.367))))
        my = int(round(max(MM[1] + 2, min(MM[3] - 2, my + err_y / 1.733))))
        log(f"        误差 ({err_x},{err_y}) → 修正像素 ({mx},{my})")

    if center is None:
        log("  ✗ 未建立视野中心")
        return False, None

    for attempt in range(5):
        px = VIEW_CX + (tx - center[0]) * W_DEF
        py = VIEW_CY + (ty - center[1]) * H_DEF
        if not _onscreen(px, py) or _blocked(px, py):
            # ★目标被面板挡住/出界 → 用「小地图再瞄准」把视野中心挪到目标以南★
            #   原理：视野中心 = 小地图点击的回读值（精确）。把中心放到目标以南 ~7 格，
            #   目标就会出现在屏幕上带 y≈100 处（面板之外），即可精点。
            #   不再用方向键（实测该状态下连续 3 次重试仍零位移，不可靠）。
            want_center_y = ty + 7
            log(f"  [{attempt+1}] 像素({px:.0f},{py:.0f})不可点 → 小地图再瞄准"
                f"（中心移到 ({tx},{want_center_y})）")
            TP.reset_to_map(log=None)
            cmx, cmy = mm.pixel(tx, want_center_y)
            if not mm_jump(tf_id, cmx, cmy, log=log):
                log("    ✗ 面板打不开")
                return False, None
            d2 = read_dest_any(tf_id, log=log)
            log(f"        再瞄准后中心/目的地 {d2}")
            if not d2:
                continue
            mm.add(cmx, cmy, d2[0], d2[1])
            center = d2
            continue
        by, bx = TP.open_tf_panel(tf_id, log=(log if attempt == 0 else
                                              (lambda *a: None)))
        if by is None:
            log("  ✗ 面板打不开")
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
            log(f"        反推中心 {tuple(round(v,1) for v in center)}")
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 109
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
