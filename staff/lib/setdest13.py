#!/usr/bin/env python3
"""`set-dest` v13（2026-10-03 定稿）：**真实机制 + 视野外目标用 Jump Map 摇杆**。

═══ 真实机制（v12 已实测确立）═══
  点 `Set TF Destination` 箭头 → **面板关闭** → 点地图任意像素 → 目的地设定、
  面板重开并显示新目的地。⇒ **选格时全屏可点，无遮挡**。

═══ 由此得到的两个原语 ═══
  · `pick_hex(px,py)`：点箭头→点像素→回读目的地 = **该像素对应的格**
    ⇒ 它既是"设点"也是"视野探针"（不需要顶栏、不需要面板大字）。
  · 两个不同像素的 pick_hex 结果 ⇒ 直接解出 W、H。

═══ 视野外目标 ═══
  目标像素出屏时，用右下角 Jump Map 当**方向摇杆**（它是局部地图、每次点击后
  重新居中，故只能按方向偏移着点），把视野挪过去，再用 pick_hex 复核。
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
PROBE_A, PROBE_B = (300, 120), (700, 600)
FOCUS_PT = (950, 60)
MM = (893, 664, 1021, 765)
MM_CX = (MM[0] + MM[2]) // 2          # 957
MM_CY = (MM[1] + MM[3]) // 2          # 714
# ★实测重标定★ 由「偏移(-54,+48) → 视野实际移动(-12,+35)格」反推：
#   x: 54/12 ≈ 4.5 px/格 ; y: 48/35 ≈ 1.37 px/格
#   （先前用的 9.0/2.57 偏大一倍，导致摇杆过冲、在两点间来回跳）
PX_PER_HEX_X = 4.5
PX_PER_HEX_Y = 1.37
W_DEF, H_DEF = 40.0, 37.0


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.7):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


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
        c.save("/tmp/_v13_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v13_loc.png", "stdout", "--psm", "7"],
                            capture_output=True)
        got = parse_list_location(rr.stdout.decode(errors="replace"))
        if got:
            return got
        time.sleep(0.6)
    return None


def read_dest_any(tf_id, log=None):
    """读目的地。★优先读面板★（点完像素后面板会立刻重开并显示新目的地），
    列表只作兜底 —— 实测列表回读偶尔给出陈旧值，会把标定算坏。"""
    from collections import Counter
    lab = TP.find_dest_label()
    if lab is not None:
        seen = []
        for _ in range(3):
            v = TP.read_panel_hex(tries=2, log=None)
            if v:
                seen.append(v)
        if seen:
            got = Counter(seen).most_common(1)[0][0]
            if log:
                log(f"    面板回读 = {got}")
            return got
    got = read_dest_from_list(tf_id, log=log)
    if got and log:
        log(f"    列表回读 = {got}")
    return got


def pick_hex(tf_id, px, py, log=None):
    """★核心原语★ 点箭头（面板关闭）→ 点像素（面板重开）→ 读回 = 该像素对应的格。

    ★可验证前置条件★ 点箭头后必须确认**面板确实关闭**（ui_state=='map'），
      否则说明箭头没点中，随后的像素点击会打在面板上 → 读到陈旧值
      （实测因此解出 H=-12.3 这种荒谬比例）。
    """
    by = None
    for _t in range(3):
        by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if by is not None:
            break
        time.sleep(1.2)
    if by is None:
        if log:
            log("    ✗ 面板打不开")
        return None
    # 点箭头 → 必须进入"面板已关闭"的选格模式
    ok_mode = False
    for _t in range(3):
        _vnc(bx, by)
        time.sleep(1.6)
        if TP.ui_state() == "map":
            ok_mode = True
            break
        # 面板还在 → 可能刚才那一下落在了别处，重新取按钮再点
        e = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if e[0] is None:
            return None
        bx = e[1]
        by = e[0]
    if not ok_mode:
        if log:
            log("    ✗ 未能进入选格模式（面板未关闭）")
        return None
    # 点像素 → 面板重开并显示新目的地 ⇒ **只信面板回读**
    #   （列表回退会给出陈旧值，实测把标定算成 H=-240）
    for _t in range(3):
        _vnc(int(px), int(py))
        time.sleep(2.6)
        from collections import Counter
        seen = []
        for _ in range(3):
            v = TP.read_panel_hex(tries=2, log=None)
            if v:
                seen.append(v)
        if seen:
            got = Counter(seen).most_common(1)[0][0]
            if log:
                log(f"    面板回读 = {got}")
            return got
        # 面板读不到 → 重新进选格模式再点一次
        e = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if e[0] is None:
            return None
        bx, by = e[1], e[0]
        _vnc(bx, by)
        time.sleep(1.6)
        if TP.ui_state() != "map":
            continue
    return None


def _hash():
    import hashlib
    return hashlib.md5(TP._shot().tobytes()).hexdigest()[:12]


def arrow_nudge(dy_cells, log=None):
    """方向键纵向微调视野（每次 2 格），**逐次校验**（前几次常被吞）。
    ★方向★ 按 up → 视野北移 → 中心格 y 减小 → 目标像素 y **增大**。
    """
    key = "up" if dy_cells > 0 else "down"
    n = max(1, int(round(abs(dy_cells) / 2)))
    done = 0
    for _ in range(n):
        for _t in range(3):
            b = _hash()
            _key(key, pace=0.8)
            if _hash() != b:
                done += 2
                break
    if log:
        log(f"    方向键{key}×{done // 2}（≈{done} 格）")
    return done


def mm_joystick(tf_id, dx_hex, dy_hex, log=None):
    """Jump Map 方向摇杆：按目标方向偏移点击，把视野挪过去。返回新视野中心估计。"""
    dx = int(max(-62, min(62, dx_hex * PX_PER_HEX_X)))
    dy = int(max(-48, min(48, dy_hex * PX_PER_HEX_Y)))
    if abs(dx) < 3 and abs(dy) < 3:
        dx = 4 if dx_hex > 0 else -4
        dy = 4 if dy_hex > 0 else -4
    mx, my = MM_CX + dx, MM_CY + dy
    if log:
        log(f"    JumpMap 摇杆偏移({dx:+d},{dy:+d}) → 点({mx},{my})")
    # ★注意★ 点小地图后面板**不会**自动重开（与点地图不同）⇒ 需手动重开再读。
    by = None
    for _t in range(3):
        by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if by is not None:
            break
        time.sleep(1.2)
    if by is None:
        return None
    for _t in range(3):
        _vnc(bx, by)
        time.sleep(1.6)
        if TP.ui_state() == "map":
            break
    else:
        return None
    _vnc(mx, my)
    time.sleep(3.0)
    e = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if e[0] is None:
        return None
    from collections import Counter
    seen = []
    for _ in range(3):
        v = TP.read_panel_hex(tries=2, log=None)
        if v:
            seen.append(v)
    if seen:
        got = Counter(seen).most_common(1)[0][0]
        if log:
            log(f"    摇杆后面板回读 = {got}")
        return got
    return None


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v13）===")
    # ── 锚点：**单探针 + 已知比例** ──
    #   ★为什么不再用两点解比例★ 实测每个探针都有一定概率读到陈旧值，
    #   两点解比例只要一个坏点就整体报废（实测出现过 W=200/H=None、H=-20.9、
    #   W=50/H=16 等各种坏解）。而比例本身已多次实测稳定在 W≈40、H≈37，
    #   故直接采用已知比例，只用**一个**探针定锚点，再用闭环修正 —— 读数次数减半。
    W, H = 40.0, 37.0
    anchor = None
    for _t in range(4):
        got = pick_hex(tf_id, *PROBE_A, log=log)
        log(f"  锚点探针 点{PROBE_A} → {got}")
        if got:
            anchor = (PROBE_A, got)
            break
    if anchor is None:
        log("  ✗ 锚点探针失败")
        return False, None
    anchors = [anchor]
    log(f"  ✓ 使用已知比例 W={W} H={H} px/格，锚点 {anchor}")

    base_px, base_h = min(anchors,
                          key=lambda a: abs(a[1][0] - tx) + abs(a[1][1] - ty))
    for attempt in range(8):
        px = int(base_px[0] + (tx - base_h[0]) * W)
        py = int(base_px[1] + (ty - base_h[1]) * H)
        if not (8 <= px <= WIN_W - 8 and 34 <= py <= WIN_H - 8):
            # 目标出屏：先看差多远
            rows_off = 0
            if py < 34:
                rows_off = (34 - py) / H
            elif py > WIN_H - 8:
                rows_off = (py - (WIN_H - 8)) / H
            if 0 < rows_off <= 14:
                # ★小偏差 → 方向键精调★（每次 2 格、逐次校验）
                #   Jump Map 是量化跳转（实测最小步长约 30 格），小偏差用它必然过冲。
                log(f"  [{attempt+1}] 目标像素({px},{py})出屏 {rows_off:.0f} 格 → 方向键精调")
                TP.reset_to_map(log=None)
                _vnc(*FOCUS_PT)
                time.sleep(0.8)
                arrow_nudge(rows_off, log=log)
                continue
            log(f"  [{attempt+1}] 目标像素({px},{py})出屏 {rows_off:.0f} 格 → JumpMap 粗跳")
            err_x = tx - base_h[0]
            err_y = ty - base_h[1]
            d = mm_joystick(tf_id, err_x, err_y, log=log)
            log(f"        摇杆后回读 {d}")
            if not d:
                continue
            dx = int(max(-62, min(62, err_x * PX_PER_HEX_X)))
            dy = int(max(-48, min(48, err_y * PX_PER_HEX_Y)))
            base_px, base_h = (MM_CX + dx, MM_CY + dy), d
            continue
        got = pick_hex(tf_id, px, py, log=log)
        log(f"  [{attempt+1}] 点({px},{py}) → 回读 {got}")
        if got == (tx, ty):
            log("  ✓ 确认命中")
            return True, got
        if not got:
            continue
        base_px, base_h = (px, py), got
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    _tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    _tx = int(sys.argv[2]) if len(sys.argv) > 2 else 116
    _ty = int(sys.argv[3]) if len(sys.argv) > 3 else 128
    ok, h = set_tf_dest(_tf, _tx, _ty)
    print("RESULT", ok, h)
