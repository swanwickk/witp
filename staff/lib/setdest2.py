#!/usr/bin/env python3
"""`witp-cmd set-dest` 的定稿实现（2026-09-28 重写）。

═══ 设计（全部来自本轮实测）═══

**唯一可靠的绝对坐标读数 = 顶栏 `Hex: x y`**
  · 用逐字符点阵模板匹配（见 lib/hexbar.py），实测 6/6 字符全对（dist≤8）。
  · tesseract 在该字体上系统性误读（`9`→`2`、`1`→`7`），已彻底不用于数字。

**已实测的点击行为**
  · **纯地图态点击地图 → 顶栏 Hex 立刻变成所点格**；且**点击不移动视野**
    （同一像素连点两轮，读数逐点完全一致：`(300,300)→(95,113)`、
    `(500,300)→(99,113)`、`(300,500)→(95,119)`）。
  · 因此标定就一步：点一个已知像素 → 读顶栏 → 得到 (像素↔格) 锚点。
  · 实测比例 **W≈50 px/格、H≈33.3 px/格**（由上述三点解出，且与
    「42px 提示窗」的估计不同 —— 以实测为准）。

**远程目标**
  · **视野边缘滚动有效**：鼠标停在窗口最外 1 像素（左 x=0 / 右 x=1023 /
    下 y=767）→ 视野持续平移；停 5s 即可产生明显位移（实测探针读数变化）。
  · 方向键同样有效（每次 2 格），但需要先确保地图焦点。
  · **先用边缘滚动把目标拉进视野，再点击设定** —— 不依赖方向键焦点状态机。
"""

import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset, read_bar_once   # noqa: E402
from lib import tfpanel as TP                             # noqa: E402

# 游戏窗口尺寸
WIN_W, WIN_H = 1024, 768
# 面板遮挡范围（实测）：x159..854 / y195..546 ⇒ 可点击的地图区域为四条边带
PANEL_BOX = (140, 170, 1010, 570)
EDGE_MARGIN = 26          # 距面板边缘至少这么远才算安全可点区


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _move(px, py):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                    str(int(px)), str(int(py))], capture_output=True)


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _hex_vote(n=3):
    """顶栏 Hex 多数投票（单帧偶发读不出，投票显著提升稳定性）。"""
    from collections import Counter
    seen = []
    for _ in range(n):
        h = read_bar_once()
        if h:
            seen.append(h)
        time.sleep(0.25)
    if not seen:
        return None
    return Counter(seen).most_common(1)[0][0]


def calibrate(log=print):
    """标定：(像素 ↔ 格) 的线性映射。

    实测点击不移动视野 ⇒ 只需两个锚点即可解出比例（W、H 正交）。
    返回 dict(px0,hex0,W,H) 或 None。
    """
    p1 = (300, 300)
    _vnc(*p1)
    time.sleep(1.5)
    h1 = _hex_vote(3)
    if h1 is None:
        log("  ⚠ 标定①顶栏读不出")
        return None
    p2 = (700, 300)
    _vnc(*p2)
    time.sleep(1.5)
    h2 = _hex_vote(3)
    if h2 is None:
        log("  ⚠ 标定②顶栏读不出")
        return None
    p3 = (300, 620)
    _vnc(*p3)
    time.sleep(1.5)
    h3 = _hex_vote(3)
    if h3 is None:
        log("  ⚠ 标定③顶栏读不出")
        return None
    dxp, dxh = p2[0] - p1[0], h2[0] - h1[0]
    dyp, dyh = p3[1] - p1[1], h3[1] - h1[1]
    if dxh == 0 or dyh == 0:
        log(f"  ⚠ 标定点未产生位移: {h1} {h2} {h3}")
        return None
    W = dxp / dxh
    H = dyp / dyh
    # 合理性闸门（实测 30~60 px/格；留宽到 20~80 容忍缩放）
    if not (20 <= abs(W) <= 80) or not (20 <= abs(H) <= 80):
        log(f"  ⚠ 比例不合理 W={W:.2f} H={H:.2f} → 弃用")
        return None
    log(f"  ✓ 标定: 点{p1}→{h1} 点{p2}→{h2} 点{p3}→{h3} ⇒ W={W:.2f} H={H:.2f} px/格")
    return {"px0": p1, "hex0": h1, "W": W, "H": H}


def pixel_of(cal, hx, hy):
    return (cal["px0"][0] + (hx - cal["hex0"][0]) * cal["W"],
            cal["px0"][1] + (hy - cal["hex0"][1]) * cal["H"])


def in_panel(x, y):
    return (PANEL_BOX[0] <= x <= PANEL_BOX[2] and PANEL_BOX[1] <= y <= PANEL_BOX[3])


def clamp_clickable(x, y):
    """把像素夹到「可见且不被面板遮挡」的位置。返回 None 表示夹不出来。"""
    if in_panel(x, y):
        # 优先上移/下移出面板
        for cand in ((x, PANEL_BOX[1] - EDGE_MARGIN),
                     (x, PANEL_BOX[3] + EDGE_MARGIN)):
            if 0 <= cand[1] <= WIN_H - 8:
                return cand
        return None
    if x < 4 or y < 30 or x > WIN_W - 4 or y > WIN_H - 4:
        return None
    return (x, y)


def scroll_visible(cal, tx, ty, log=print, max_rounds=6):
    """用视野边缘滚动把目标拉进可点击区。返回是否已在可点区。"""
    for r in range(max_rounds):
        px, py = pixel_of(cal, tx, ty)
        if clamp_clickable(px, py) and 4 <= px <= WIN_W - 4 and 30 <= py <= WIN_H - 4:
            return True
        # 决定滚动方向：需要目标的像素向窗口中心靠
        cx, cy = 500, 380
        hx, hy = None, None
        if px < 4:
            _move(0, int(min(max(py, 40), WIN_H - 40)))
            hx = "左"
        elif px > WIN_W - 4:
            _move(WIN_W - 1, int(min(max(py, 40), WIN_H - 40)))
            hx = "右"
        elif py < 30:
            _move(500, 0)
            hy = "上"
        elif py > WIN_H - 4:
            _move(500, WIN_H - 1)
            hy = "下"
        else:
            # 只是被面板挡住 → 先试着滚到面板外
            _move(500, WIN_H - 1 if py < 450 else 0)
            hy = "下/上"
        log(f"    滚视野({hx or hy}) …")
        time.sleep(3.2)
        _move(512, 384)
        time.sleep(0.6)
        # 重新标定（滚动后锚点失效）
        c2 = calibrate(log=lambda *a: None)
        if c2:
            cal.update(c2)
        else:
            log("    ⚠ 滚动后重标定失败")
            return False
    return False


def set_tf_dest(tf_id, tx, ty, log=print):
    """设 TF 目的地为 (tx,ty)。返回 (ok, 面板读回值)。"""
    log(f"=== set-dest {tf_id} → Hex({tx},{ty}) ===")
    # ── 1. 地图态标定 ──
    by, bx = TP.find_dest_button()
    if by is not None:
        # 面板开着会挡住地图大半，先退到地图
        _key("escape")
        time.sleep(1.2)
    cal = calibrate(log=log)
    if cal is None:
        log("  ✗ 标定失败，放弃（不做无根据的点击）")
        return False, None

    # ── 2. 把目标拉进可点击区（必要时滚动视野）──
    scroll_visible(cal, tx, ty, log=log)

    # ── 3. 开面板 → 进选点模式 → 点目标格 → 读回 ──
    for i in range(6):
        px, py = pixel_of(cal, tx, ty)
        click = clamp_clickable(px, py)
        if click is None:
            log(f"  [{i+1}] 目标像素({px:.0f},{py:.0f})不可点 → 再滚一轮")
            if not scroll_visible(cal, tx, ty, log=log):
                log("  ✗ 无法把目标拉进可点区")
                return False, None
            continue
        by, bx = TP.open_tf_panel(tf_id, log=(log if i == 0 else (lambda *a: None)))
        if by is None:
            log("  ✗ 未能打开编队详情面板")
            return False, None
        # 进选点模式（一次性）：每次都重新点按钮
        _vnc(bx, by)
        time.sleep(2.3)
        _vnc(int(click[0]), int(click[1]))
        time.sleep(2.8)
        # 读回
        by2 = TP.find_dest_button()[0]
        got = TP.read_panel_hex(log=None) if by2 else None
        log(f"  [{i+1}] 点({click[0]:.0f},{click[1]:.0f}) → 面板 {got}")
        if got is None:
            # 面板可能被关掉（=已设定）。重开面板再读
            by3, _ = TP.open_tf_panel(tf_id, log=lambda *a: None)
            if by3:
                got = TP.read_panel_hex(log=None)
                log(f"        重开面板读回 = {got}")
        if got == (tx, ty):
            log(f"  ✓ 面板确认目的地 = {got}")
            # 复位：重标定一次（因为点地图可能改了视野）
            _key("escape")
            time.sleep(1.0)
            return True, got
        if got:
            # 用实测落点修正标定
            cal["px0"] = click
            cal["hex0"] = got
            log(f"        用实测落点修正锚点: {click} ↔ {got}")
        else:
            if by2 is None:
                log("        面板已关闭且读不回 —— 以结算后读层为准")
                return False, None
    log("  ✗ 未在面板确认（以结算后读层为准）")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 140
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
