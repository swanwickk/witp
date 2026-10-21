#!/usr/bin/env python3
"""`set-dest` v6（2026-10-03）：**小地图粗跳 + 主地图精点**。

═══ 为什么这样分工（本轮实测）═══
· **右下角确实有小地图**（窗口坐标 x≈891..1023, y≈662..767，内有红框=当前视野）。
  在**选点模式**下点小地图 → **视野绝对跳转**（实测：从新喀里多尼亚跳到所罗门/
  俾斯麦群岛），且会设定目的地。这是"绝对定位"通道。
· 小地图分辨率很粗（132×105 px 覆盖整个太平洋）⇒ 一次点击只能到目标 **±1~3 格**，
  所以它只做**粗跳**，把目标拉进主视野。
· 主地图精度高（W≈40~45 px/格）⇒ 精点由主地图完成，用顶栏探针标定视野。
· 绝不再用"边缘滚动+重标定"（实测会南北振荡，永不收敛）。

═══ 小地图映射（实测标定）═══
  (955,730)→(122,124)  (965,735)→(122,134)
  (940,735)→(111,134)  (970,720)→(122,108)
  最小二乘： hx ≈ -232.2 + 0.367*mx ;  hy ≈ -1140.1 + 1.733*my
  （y 轴 ±1 格、x 轴 ±3 格；够粗跳用）
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset, read_bar_once   # noqa: E402
from lib import tfpanel as TP                             # noqa: E402
from PIL import Image                                     # noqa: E402

import os as _os
_os.environ.setdefault("DISPLAY", ":98")

WIN_W, WIN_H = 1024, 768
PANEL = (150, 185, 870, 560)
PROBES = [(300, 60), (700, 60), (100, 400), (950, 600)]
BAND_TOP, BAND_BOT = 90, 610

# 小地图（实测）
MM_X0, MM_Y0, MM_X1, MM_Y1 = 893, 664, 1021, 765
MM_A, MM_B = -232.2, 0.367      # hx = A + B*mx
MM_C, MM_D = -1140.1, 1.733     # hy = C + D*my
# 焦点用安全点（面板之外的地图空白处）
FOCUS_PT = (950, 60)


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _move(px, py):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                    str(int(px)), str(int(py))], capture_output=True)


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def _onscreen(x, y):
    return 10 <= x <= WIN_W - 10 and 36 <= y <= 640


def _fit_slope(pxs, hs, k):
    n = len(pxs)
    if n < 2:
        return None
    mx = sum(p[k] for p in pxs) / n
    mh = sum(h[k] for h in hs) / n
    num = sum((hs[i][k] - mh) * (pxs[i][k] - mx) for i in range(n))
    den = sum((hs[i][k] - mh) ** 2 for i in range(n))
    return None if den < 1e-9 else num / den


def _resid(pxs, hs, k, W):
    n = len(pxs)
    mx = sum(p[k] for p in pxs) / n
    mh = sum(h[k] for h in hs) / n
    return max(abs(pxs[i][k] - (mx + W * (hs[i][k] - mh))) for i in range(n))


def measure_view(log=print):
    """顶栏探针四点联合求解 → dict(W,H,anchors,resid)。"""
    from itertools import product
    from lib.hexbar import read_bar_votes
    if TP.ui_state() != "map":
        TP.reset_to_map(log=None)
    pxs, cands, prev = [], [], None
    for p in PROBES:
        v = {}
        for _try in range(3):
            _vnc(*p)
            time.sleep(1.2)
            v = read_bar_votes()
            if not v:
                continue
            top = sorted(v.items(), key=lambda kv: -kv[1])[0][0]
            if prev is None or top != prev:
                break
        if not v:
            log(f"  顶栏探针 {p} 无候选（读数失败）")
            continue
        top2 = sorted(v.items(), key=lambda kv: -kv[1])[:2]
        log(f"  顶栏探针 {p} 候选 {top2}")
        pxs.append(p)
        cands.append([t[0] for t in top2])
        prev = top2[0][0]
    if len(pxs) < 3:
        log(f"  ✗ 顶栏锚点不足（{len(pxs)}）")
        return None
    best = None
    for combo in product(*cands):
        W = _fit_slope(pxs, list(combo), 0)
        H = _fit_slope(pxs, list(combo), 1)
        if W is None or H is None:
            continue
        if not (15 <= abs(W) <= 90) or not (15 <= abs(H) <= 90):
            continue
        r = max(_resid(pxs, list(combo), 0, W), _resid(pxs, list(combo), 1, H))
        if best is None or r < best[0]:
            best = (r, W, H, list(combo))
    if best is None:
        log("  ✗ 无候选组合可拟合")
        return None
    r, W, H, hs = best
    log(f"  ✓ 视野标定 W={W:.2f} H={H:.2f} px/格 残差={r:.1f}px")
    for p, h in zip(pxs, hs):
        log(f"      {p} ↔ {h}")
    return {"W": W, "H": H, "anchors": list(zip(pxs, hs)), "resid": r}


def pixel_of(vw, tx, ty):
    base = min(vw["anchors"],
               key=lambda a: abs(a[1][0] - tx) + abs(a[1][1] - ty))
    return (base[0][0] + (tx - base[1][0]) * vw["W"],
            base[0][1] + (ty - base[1][1]) * vw["H"])


def minimap_pixel(hx, hy):
    """世界格 → 小地图像素（实测拟合）。"""
    mx = (hx - MM_A) / MM_B
    my = (hy - MM_C) / MM_D
    mx = max(MM_X0 + 2, min(MM_X1 - 2, mx))
    my = max(MM_Y0 + 2, min(MM_Y1 - 2, my))
    return int(round(mx)), int(round(my))


def minimap_jump(tf_id, hx, hy, log=print):
    """选点模式下点小地图 → 视野粗跳到目标附近（同时会设定目的地）。"""
    mx, my = minimap_pixel(hx, hy)
    log(f"  小地图粗跳：目标({hx},{hy}) → 小地图像素({mx},{my})")
    by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if by is None:
        log("    ✗ 面板打不开")
        return False
    _vnc(bx, by)
    time.sleep(2.0)
    _vnc(mx, my)
    time.sleep(3.2)
    return True


def parse_list_location(t):
    t2 = t.translate(str.maketrans({
        "i": "1", "l": "1", "I": "1", "|": "1", "!": "1",
        "O": "0", "o": "0", "Q": "0", "D": "0",
        "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2",
        "G": "6", "T": "7", "q": "9", "g": "9"}))
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
        c.save("/tmp/_v6_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v6_loc.png", "stdout", "--psm", "7"],
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


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v6：小地图粗跳+主图精点）===")
    vw = measure_view(log=log)
    if vw is None:
        log("  ✗ 视野标定失败")
        return False, None
    px, py = pixel_of(vw, tx, ty)
    px, py = int(px), int(py)
    if not (_onscreen(px, py) and not _blocked(px, py)):
        log(f"  目标像素({px},{py})不在可点带 → 用小地图粗跳")
        if not minimap_jump(tf_id, tx, ty, log=log):
            return False, None
        TP.reset_to_map(log=None)
        vw = measure_view(log=log)
        if vw is None:
            log("  ✗ 粗跳后标定失败")
            return False, None
        px, py = pixel_of(vw, tx, ty)
        px, py = int(px), int(py)
        log(f"  粗跳后目标像素 ({px},{py})")
    if not (_onscreen(px, py) and not _blocked(px, py)):
        log(f"  ✗ 目标像素({px},{py})仍不可点")
        return False, None

    for attempt in range(4):
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
            idx = min(range(len(vw["anchors"])),
                      key=lambda i: (abs(vw["anchors"][i][1][0] - tx)
                                     + abs(vw["anchors"][i][1][1] - ty)))
            vw["anchors"][idx] = ((px, py), got)
            px, py = pixel_of(vw, tx, ty)
            px, py = int(px), int(py)
            log(f"        锚点更新 → 新目标像素 ({px},{py})")
            if not (_onscreen(px, py) and not _blocked(px, py)):
                log("  ✗ 修正后目标像素不可点")
                return False, None
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 108
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 130
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
