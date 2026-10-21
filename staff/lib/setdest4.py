#!/usr/bin/env python3
"""`set-dest` 定稿 v3：**用 T 列表的 Location 列做回读**，不依赖面板反复开关。

═══ 为什么换回读通道 ═══
实测：在选点模式下点完地图，**面板会自动关闭**（设点动作完成即退出），
于是"每轮再回读面板"要重新开面板（T + 双击行，10~15s，且中途易被其它
列表/子面板干扰）——这是此前所有不稳定的主因。
而 **T 列表的 Location 列**本身就写着目的地（实测 OCR 得 `moveto 104,150`），
且 T 列表**一个键就能开/关**，是最省事、最独立的回读通道。

═══ 流程 ═══
  1. 开一次主面板，用 2~3 个探针解出 (像素↔格) 的 W、H 与锚点。
  2. 由锚点算目标像素；被面板挡住/超出视野 → 滚视野后重开面板重探一次。
  3. 进选点模式 → 点目标像素（点完面板自动关，属正常）。
  4. **读 T 列表的 Location 列**核验；不符则以实测落点修正锚点重试。
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset            # noqa: E402
from lib import tfpanel as TP                        # noqa: E402
from PIL import Image, ImageOps                      # noqa: E402

import os as _os
_os.environ.setdefault("DISPLAY", ":98")

WIN_W, WIN_H = 1024, 768
PANEL = (150, 185, 870, 560)
# 实测映射（顶部/底部地图带）：(300,120)↔(106,145)、(300,640)↔(105,159)、
#   (700,120)↔(115,145) ⇒ W≈40~44 px/格、H≈37 px/格
PROBES = [(300, 120), (300, 640), (700, 120), (300, 640)]
LIST_LOC_BOX = (700, 0, 1024, 0)      # x 范围；y 由行位置给


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


def px_reachable(x, y, tol=6):
    return (tol <= x <= WIN_W - tol and 32 <= y <= WIN_H - 10)


def read_dest_from_list(tf_id, log=None):
    """读 T 列表里该编队的 Location 列，解析 `moveto x,y`。返回 (x,y) 或 None。"""
    from lib.setdest import find_tf_row
    r = find_tf_row(tf_id, log=None)
    if r is None:
        _key("t")
        time.sleep(3.2)
        r = find_tf_row(tf_id, log=None)
    if r is None:
        return None
    im = TP._shot()
    c = im.crop((690, r - 9, 1024, r + 9))
    c = c.resize((c.width * 6, c.height * 6), Image.LANCZOS)
    c.save("/tmp/_v3_loc.png")
    rr = subprocess.run(["tesseract", "/tmp/_v3_loc.png", "stdout", "--psm", "7"],
                        capture_output=True)
    t = rr.stdout.decode(errors="replace")
    nums = re.findall(r"\d{2,3}", t)
    if len(nums) >= 2:
        x, y = int(nums[-2]), int(nums[-1])
        if log:
            log(f"    列表自述: {t.strip()!r} → ({x},{y})")
        if 10 <= x <= 250 and 10 <= y <= 250:
            return (x, y)
    if log:
        log(f"    列表解析失败: {t.strip()!r}")
    return None


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v3：列表回读）===")
    # ── 1. 开主面板并标定 ──
    by, bx0 = TP.open_tf_panel(tf_id, log=log)
    if by is None:
        log("  ✗ 未能打开编队详情面板")
        return False, None

    def ensure_panel():
        """确保主面板在（返回 (y, x_button) 或 None）。"""
        lab = TP.find_dest_label()
        if lab is not None:
            return lab[2], int(lab[0]) - 45
        return TP.open_tf_panel(tf_id, log=lambda *a: None)

    def read_panel_hex_vote(tries=3, log=None):
        """面板 Hex 多数投票。

        ★实测★ 面板大字虽稳，仍会**单字形误读**（`145` 读成 `115`）。
          该误读会把比例解坏（实测解出 H=11.8 px/格并导致后续振荡）。
          故读 3 次取众数；无众数则取末次。
        """
        from collections import Counter
        seen = []
        for _ in range(3):
            v = TP.read_panel_hex(tries=2, log=None)
            if v:
                seen.append(v)
        if not seen:
            return None
        cnt = Counter(seen)
        best, n = cnt.most_common(1)[0]
        if n >= 2:
            return best
        return seen[-1]

    def probe_px(px, py, before, tries=3):
        """点地图像素并回读面板 Hex。

        ★核心修复（陈旧值陷阱）★ 实测：若未真正进入选点模式，
          面板 Hex 行**不会刷新**，会把旧值当本次读数返回。
          ⚠ 用「与上一个探针的值比较」是不够的 —— 实测滚动后第一个探针
            读到 (106,115)、第二个却读回过期值 (105,159)（与上探针不同，
            却被当成有效读数），最终解出 H=11.8 这种荒谬值。
          ⇒ **必须与「进入选点模式后、点击前」那一刻的值比较**：
            点完若数值没变，就是没进模式/没生效，重试；宁判失败不采信。
        """
        for _ in range(tries):
            e = ensure_panel()
            if e is None:
                return None
            _by, _bx = e
            _vnc(_bx, _by)                       # 进选点模式
            time.sleep(2.0)
            pre = read_panel_hex_vote()          # 点击前的面板值（投票）
            _vnc(int(px), int(py))               # 点地图像素
            time.sleep(2.6)
            got = read_panel_hex_vote()
            if got and got != pre:
                return got
            log(f"      ⚠ ({px},{py}) 点击前后均为 {got}（疑未进选点模式）→ 重试")
            time.sleep(0.6)
        return None

    def calibrate():
        """跑一遍探针并解出 (W, H, anchors)。返回 (W,H,anchors) 或 None。"""
        _anchors, _prev = [], None
        for (px, py) in PROBES:
            got = probe_px(px, py, _prev)
            log(f"  探针 点({px},{py}) → 面板 {got}")
            if got:
                _anchors.append(((px, py), got))
                _prev = got
            if len(_anchors) >= 3:
                break
        if len(_anchors) < 2:
            return None

        def _slope(vk, hk):
            best = None
            for i in range(len(_anchors)):
                for j in range(i + 1, len(_anchors)):
                    (pa, ha), (pb, hb) = _anchors[i], _anchors[j]
                    dh = hb[hk] - ha[hk]
                    if abs(dh) < 2:
                        continue
                    v = (pb[vk] - pa[vk]) / dh
                    if best is None or abs(dh) > best[0]:
                        best = (abs(dh), v)
            return best[1] if best else None

        def _scale_median(vk, hk):
            """★中位数法★ 逐对求比例取中位数，再剔除偏离中位数 >25% 的对后平均。
            实测：单个错读锚点会让「取 |Δh| 最大那对」的策略解出荒谬比例
            （H=11.8 px/格），中位数对单个离群点稳健。"""
            vals = []
            for i in range(len(_anchors)):
                for j in range(i + 1, len(_anchors)):
                    (pa, ha), (pb, hb) = _anchors[i], _anchors[j]
                    dh = hb[hk] - ha[hk]
                    if abs(dh) < 2:
                        continue
                    vals.append((pb[vk] - pa[vk]) / dh)
            if not vals:
                return None
            vals.sort()
            med = vals[len(vals) // 2]
            keep = [v for v in vals
                    if med == 0 or abs(v - med) <= 0.25 * abs(med)]
            if not keep:
                keep = vals
            return sum(keep) / len(keep)

        _W, _H = _scale_median(0, 0), _scale_median(1, 1)
        if _W is None or _H is None:
            return None
        if not (15 <= abs(_W) <= 90) or not (15 <= abs(_H) <= 90):
            log(f"  ✗ 比例不合法 W={_W} H={_H}")
            return None
        # ★一致性校验★ 用解出的 W、H 预测每个锚点，剔除残差 >3 格的离群点后重解。
        if len(_anchors) >= 3:
            p0, h0 = _anchors[0]
            def _resid(a):
                """★以「格」为单位算残差★（此前用像素阈值 3*W/3*H，
                在 H 被解小的时候容差也跟着变小/变大，判不准）。"""
                dx = (a[0][0] - p0[0]) / _W - (a[1][0] - h0[0])
                dy = (a[0][1] - p0[1]) / _H - (a[1][1] - h0[1])
                return max(abs(dx), abs(dy))
            good = [a for a in _anchors if _resid(a) <= 3.0]
            if 2 <= len(good) < len(_anchors):
                log(f"  ⚠ 剔除离群锚点 {len(_anchors) - len(good)} 个后重解")
                _anchors = good
                _W, _H = _slope(0, 0), _slope(1, 1)
                if _W is None or _H is None or not (15 <= abs(_W) <= 90) \
                        or not (15 <= abs(_H) <= 90):
                    log(f"  ✗ 重解后比例仍不合法 W={_W} H={_H}")
                    return None
        log(f"  ✓ 比例 W={_W:.2f} H={_H:.2f} px/格（锚点 {len(_anchors)}）")
        return _W, _H, _anchors

    cal = calibrate()
    if cal is None:
        log("  ✗ 标定失败，放弃")
        return False, None
    W, H, anchors = cal

    base_px, base_h = min(anchors, key=lambda ah: abs(ah[1][0] - tx) + abs(ah[1][1] - ty))

    # ── 2. 迭代：算像素 → 点 → 读列表核验 → 修正 ──
    for i in range(12):
        want = (base_px[0] + (tx - base_h[0]) * W,
                base_px[1] + (ty - base_h[1]) * H)
        if not px_reachable(*want) or _blocked(*want):
            # ★选方向与落点带★（实测：上边缘 y=0 与下边缘 y=767 都能触发滚动；
            #   向北滚 → 内容下移；向南滚 → 内容上移）
            #   目标在视野上方/被上部遮挡 → 向北滚，让它从「上带」进入(y≈100)
            #   目标在视野下方/被下部遮挡 → 向南滚，让它从「下带」进入(y≈620)
            if want[1] < 370:
                desire, road = 100.0, "north"
            else:
                desire, road = 620.0, "south"
            log(f"  [{i+1}] 像素({want[0]:.0f},{want[1]:.0f})不可点/被挡 → "
                f"{'向北' if road=='north' else '向南'}滚，落到 y≈{desire:.0f}")
            TP.reset_to_map(log=None)
            for _ in range(3):
                if TP.ui_state() == "map":
                    break
                TP.reset_to_map(log=None)
            _vnc(950, 640)          # 地图右下空白区取焦点（面板之外）
            time.sleep(0.8)
            secs = min(4.0, max(1.8, abs(desire - want[1]) / H / 10.5))
            if road == "north":
                _move(WIN_W // 2, 0)          # 上边缘（实测 y=0 有效）
            else:
                _move(WIN_W // 2, WIN_H - 1)  # 下边缘
            time.sleep(secs)
            _move(WIN_W // 2, WIN_H // 2)
            time.sleep(0.8)
            # ★滚动后必须**重新完整标定**★ 实测：单个探针给出的锚点与随后
            #   点击的落点自相矛盾（解出 1.2 px/格这种荒谬值），导致来回振荡。
            cal = calibrate()
            if cal is None:
                log("    ⚠ 滚后重标定失败")
                return False, None
            W, H, anchors = cal
            base_px, base_h = min(
                anchors, key=lambda ah: abs(ah[1][0] - tx) + abs(ah[1][1] - ty))
            continue
        # 进选点模式 → 点目标像素（带"陈旧值"重试）
        got = None
        for attempt in range(3):
            e = ensure_panel()
            if e is None:
                log("    ⚠ 面板重开失败")
                return False, None
            _by, _bx = e
            _vnc(_bx, _by)
            time.sleep(2.0)
            _vnc(int(want[0]), int(want[1]))
            time.sleep(2.8)
            log(f"  [{i+1}] 已点({want[0]:.0f},{want[1]:.0f}) → 读列表核验")
            got = read_dest_from_list(tf_id, log=(log if attempt == 0 else None))
            if got == (tx, ty) or (got is not None and got != base_h):
                break
            log(f"      ⚠ 列表值 {got} 未变（疑未进选点模式）→ 重试点击")
        if got == (tx, ty):
            log(f"  ✓ 列表确认目的地 = {got}")
            return True, got
        if got is None:
            continue
        base_px, base_h = want, got
        log(f"        修正锚点: ({want[0]:.0f},{want[1]:.0f}) ↔ {got}")
    log("  ✗ 未确认（以结算后读层为准）")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 104
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
