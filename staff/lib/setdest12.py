#!/usr/bin/env python3
"""`set-dest` v12（2026-10-03 定稿）：**按游戏真实机制设定目的地**。

═══ 真实机制（实测逐帧取证，纠正此前错误结论）═══
  ① 打开编队详情界面（T 列表 → 双击行）
  ② 点 `Set TF Destination` 标题左侧箭头 → **面板立即关闭**，进入"选格"模式
     （实测：点后 find_dest_label=False、ui_state=map）
  ③ **在整张地图上点目标格** → 目的地设定，**面板自动重新打开**显示新目的地
     （实测：点地图后 ui_state=main）

⇒ **不存在"面板遮挡"问题** —— 选格时地图是完整的，任意像素都可点。
   此前"面板存活=True"的判断是错的（读到的是点地图之后面板重开的状态），
   由此错误地发明了"可点带/滚动/小地图摇杆"等一堆绕行方案，全部作废。

═══ 因此闭环极简 ═══
  用「点箭头 → 点像素 P → 读回 H」得到精确的 (像素↔格) 样本；
  两个样本解出比例；再迭代命中。全过程**不需要任何视野探针**。
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
# 探针像素：全屏可用（选格时面板已关闭）
PROBE_A, PROBE_B = (300, 120), (700, 600)
FOCUS_PT = (950, 60)


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
        c.save("/tmp/_v12_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v12_loc.png", "stdout", "--psm", "7"],
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


def pick_hex(tf_id, px, py, log=None):
    """★核心原语★ 点箭头（面板关闭）→ 点像素（面板重开）→ 读回目的地。"""
    by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if by is None:
        if log:
            log("    ✗ 面板打不开")
        return None
    _vnc(bx, by)                 # 进选格模式（面板关闭）
    time.sleep(1.6)
    _vnc(int(px), int(py))       # 点目标像素（面板重开）
    time.sleep(2.6)
    return read_dest_any(tf_id, log=log)


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v12：按真实机制）===")
    # ── 标定：两个探针样本 ──
    anchors = []
    for p in (PROBE_A, PROBE_B):
        got = pick_hex(tf_id, *p, log=log)
        log(f"  探针 点{p} → 目的地 {got}")
        if got:
            anchors.append((p, got))
    if len(anchors) < 2:
        log("  ✗ 探针不足，无法解比例")
        return False, None
    (pa, ha), (pb, hb) = anchors[0], anchors[1]
    W = H = None
    if hb[0] != ha[0]:
        W = (pb[0] - pa[0]) / (hb[0] - ha[0])
    if hb[1] != ha[1]:
        H = (pb[1] - pa[1]) / (hb[1] - ha[1])
    if W is None or H is None or not (15 <= abs(W) <= 90) or not (15 <= abs(H) <= 90):
        log(f"  ✗ 比例不合法 W={W} H={H}（锚点 {anchors}）")
        return False, None
    log(f"  ✓ 比例 W={W:.2f} H={H:.2f} px/格")

    base_px, base_h = min(anchors,
                          key=lambda a: abs(a[1][0] - tx) + abs(a[1][1] - ty))
    for attempt in range(6):
        px = base_px[0] + (tx - base_h[0]) * W
        py = base_px[1] + (ty - base_h[1]) * H
        px, py = int(px), int(py)
        if not (8 <= px <= WIN_W - 8 and 34 <= py <= WIN_H - 8):
            log(f"  [{attempt+1}] 目标像素({px},{py})超出屏幕（需先移动视野）")
            return False, None
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
    _tx = int(sys.argv[2]) if len(sys.argv) > 2 else 109
    _ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(_tf, _tx, _ty)
    print("RESULT", ok, h)
