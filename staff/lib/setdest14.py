#!/usr/bin/env python3
"""`set-dest` v15（2026-10-03 定稿）：**真实机制 + 边缘滚动（水平/垂直）闭环**。

═══ 机制（逐帧取证确立）═══
  · 点 `Set TF Destination` 箭头 → **面板立即关闭** → 点地图像素 → 目的地设定、面板重开。
    ⇒ 选格时全屏可点，**不存在面板遮挡**。
  · `pick_hex(px,py)`：既设点、回读值又 = 该像素对应格 ⇒ 也是视野探针。
  · 比例稳定 **W≈40、H≈37 px/格** ⇒ 单探针定锚点即可（两点解比例一坏点全废）。

═══ 可点击区域（实测，v15 关键修正）═══
  底栏/信息面板会**吞掉** y≥650 的点击（回读到上一次的旧值）⇒
  目标像素必须落在 y∈[40,620]、x∈[10,1014] 才算"真正可点"。
  v14 只判到 y≤760，导致把 (780,675) 误判为在屏内 → 点击被吞 → 回读旧值 → 不收敛。

═══ 滚视野（实测三铁律）═══
  ① 必须地图有焦点且**无任何面板开着**；面板开着时"只第一次有效、之后完全不动"。
     先 reset_to_map() 再点地图空白即恢复；把鼠标移出窗口再回来**不能**重新武装。
  ② 速率 ≈ **9~10 格/秒**。
  ③ 停上边缘→视野北移；停下边缘→视野南移；停左边缘→视野西移；停右边缘→视野东移。
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset            # noqa: E402
from lib import tfpanel as TP                        # noqa: E402
from lib.executor import _game_shot as _shot_to, _ocr  # noqa: E402
from PIL import Image                                # noqa: E402

import os as _os
_os.environ.setdefault("DISPLAY", ":98")

WIN_W, WIN_H = 1024, 768
VIEW_CX, VIEW_CY = 512, 384
# ★v17 比例：W≈37.5px/格、H≈36.7px/格 ★
#
# 【订正记录——务必先读，避免重犯】
#   v16 我曾据 8 点"标定"断定真值是 W=20/H=18.5，并称旧值 40/37 是 2 倍误差。
#   **那个结论是错的**：那 8 点里有大量**陈旧回读**（(105,145) 重复 3 次、
#   (105,143) 出现 2 次，都是面板未刷新的残留），我把陈旧值当成了真值。
#   v17 用**两点联合标定**（A=(300,120)→B=(600,450)，相距 300×330px）
#   重测，四轮结果完全一致：
#       A → (106,145)   B → (114,154)
#       Δpx=300/Δhx=8 ⇒ W=37.5      Δpy=330/Δhy=9 ⇒ H=36.7
#   且 9 点回代校验（理论 vs 实测）：
#       (180,416) 0,0   (300,120) 0,0   (600,450) 0,0   (240,138) 1,0
#       (200,231) 1,0   (200,324) 1,-1  (220,324) 1,-1  (260,45) 0,2
#       (220,231) 1,-5  ← 唯一大偏差，是 hex 纵向错列所致（非比例问题）
#   ⇒ 40/37 基本正确（实测 37.5/36.7 是整数舍入差）。
#
# ★方法论教训★ 测量出现"看似矛盾"的结果时，
#   先怀疑**测量链**（陈旧回读/OCR 污染），再怀疑模型。
#   我曾反过来否定可信的测量，代价是改坏比例并连锁失败。
# ★★v19-51 标定彻底订正★★（实测 4/4 帧稳定，非陈旧回读）
#   旧值 W=37.5 / H=36.7 来自 v19-10 的"两点标定"，
#   而那两点的回读**是陈旧的**（面板会返回上一次目的地的值）。
#   v19-51 用 readchk.py 沿单轴逐点实测（每点连读 4 帧，全部一致）：
#     x 方向（y=384 固定）: x=250→100, 287→101, 324→102  ⇒ W = 37.0
#     y 方向（x=400 固定）: y=274→139, 311→140, 348→141,
#                           385→142, 422→143, 459→144, 496→145 ⇒ H = 37.0
#   （y=200→137、y=237→133 这两点是 hex 纵向错列的边界异常，已剔除）
#   ⇒ **W = H = 37.0 px/格**
#   误差影响：旧的 H=36.7 在 11 格纵向距离上累积 ~3.5 格偏差，
#   这就是精点搜索长期不中的真正原因（不是回读陈旧，也不是判据错）。
#   新锚点：PROBE=(400,384) → Hex(103,142)（x/y 双向交叉验证一致）
W_USE, H_USE = 37.0, 37.0
# ★★v19-51 锚点改用实测交叉验证点★★
#   PROBE=(400,384) → Hex(103,142)
#   验证：x 扫描 y=384 得 x=250→100,287→101,324→102（线性 37px/格）
#         y 扫描 x=400 得 y=385→142
#         两方向在 (400,384) 交叉一致 ⇒ 该锚点可信。
#   旧锚点 (300,120)→(100,135) 来自陈旧回读，作废。
PROBE_A = (400, 384)
PROBE_B = (600, 450)        # 第二标定点（右下）
HEX_A = (103, 142)          # ★PROBE_A 对应的格（v19-51 实测）
FOCUS_PT = (700, 500)

# ★★v19-52 删除 v17 标定表 ★★
#   那 9 个"实测"像素→Hex 对全部基于旧的 W=37.5/H=36.7 与陈旧回读，
#   与 v19-51 实测（W=H=37.0，PROBE(400,384)→(103,142)）矛盾。
#   保留它会让 _cal_lookup 直接给出**错误**的命中像素，
#   绕过正确的两点标定 ⇒ 必须删除。
#   （历史教训：把污染数据写成"权威/确立"，害我绕了十几轮。）
_CAL = {}


def _cal_lookup(tx, ty):
    """标定表已于 v19-52 清空（数据污染）。永远返回 None。"""
    return None

# ★真正可点击的地图带（底栏 y≥650 会吞点击）★
CLICK_X_MIN, CLICK_X_MAX = 10, WIN_W - 10
CLICK_Y_MIN, CLICK_Y_MAX = 40, 620
MARGIN = 30              # ★_safe_xy 的四周安全余量（模块级，供选轴归一化共用）
# ★已知的鼠标当前位置（游戏窗口内坐标）。_move 的连续微移动需要起点，
#   点击通道也会改变它，故两处都要更新。初始按屏幕中心起算。
_CUR = [512, 384]

# ★v19-10 滚动标定（窗口锁 (0,0)、_move 偏移已修之后重测）★
#   停 3.0s → 位移 10 格  ⇒ 约 3.3 格/秒
#   ★但停 1.5s → 位移 0 格★  ← 这是「请求 -1 格时完全不动」的真因，
#   不是横向死区，而是**滚动存在约 1.5~2.5s 的起步延迟**：
#   停靠不足就完全不动，一旦启动就以高速滚出约 10 格/次。
#   ⇒ SCROLL_MIN_S 必须是**能触发滚动的最短时长**（实测 3.0s 安全），
#     否则小请求被夹到 1.5s = 等于没滚，表现为「横向死区」的假象。
#   ⇒ 小请求只能靠**多轮逼近**：每次至少滚 3s（会过冲），
#     再用闭环校正把目标拉回中央带。
SCROLL_HZ = 3.4
SCROLL_MIN_S = 3.0       # ★实测：低于 3.0s 完全不滚（起步延迟），不是 1.5s
SCROLL_MAX_S = 6.0       # 超过 6s 收益递减（加速），且过长易过冲
SCROLL_MIN_MOVE = 3      # ★单次滚动最小格数：不足 3 格干脆别滚（省时间）


def _vnc(px, py, act="click"):
    # 点击与移动走两个不同脚本，参数约定不同，勿混：
    #   witp_vncclick.py <abs_x> <abs_y> <action>
    #   witp_vncmove.py  <x> <y> <off_x> <off_y>
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)
    _CUR[0], _CUR[1] = px, py     # ★点击也会移动鼠标，_move 的微移动起点必须同步


def _move(px, py):
    """
    ★v19-8 关键修★ 必须像 _vnc 一样**加窗口偏移**。

    实测事故：窗口被 Wine 虚拟桌面锁到 (0,0) 后，`_move(512,2)`（北边缘）
    全部无效 —— 纵向滚动 2s/3s/5s 位移恒为 (0,0)。
    根因：`witp_vncmove.py` 的默认偏移是写死的旧窗口位置 (188,150)
    （v13~v18 期间窗口漂移时代的值），`_move` 又没传偏移，
    于是鼠标实际落在屏幕 (512+188, 2+150) = (700,152) —— 根本不在游戏窗口内，
    边缘滚动自然永不触发。
    而 `_vnc()`（点击通道）从一开始就走 `get_window_offset()`，
    所以「点击正常、纯移动失效」这个不对称现象一直存在却没人归因。

    ★v19-9★ 另加**连续微移动**：WitP 的边缘滚动靠「指针进入边缘带并持续停留」
    触发；VNC 的一次性 teleport 只产生一个 PointerEvent 位置跳变，
    游戏侧可能需要若干帧连续采样才进入滚动状态。
    故改为分 6 步滑向目标点，每步 60ms —— 实测这是让滚动真正触发的关键。
    """
    ox, oy = get_window_offset()
    sx, sy = _CUR[0], _CUR[1]
    if (sx, sy) != (px, py):
        steps = 6
        for i in range(1, steps + 1):
            ix = sx + (px - sx) * i / steps
            iy = sy + (py - sy) * i / steps
            subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                            str(int(ix)), str(int(iy)),
                            str(int(ox)), str(int(oy))], capture_output=True)
            time.sleep(0.06)
    else:
        subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                        str(int(px)), str(int(py)),
                        str(int(ox)), str(int(oy))], capture_output=True)
    _CUR[0], _CUR[1] = px, py


def _key(k, pace=0.7):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _onscreen(x, y):
    """★判据必须用"可点击带"，不是整个窗口★"""
    return CLICK_X_MIN <= x <= CLICK_X_MAX and CLICK_Y_MIN <= y <= CLICK_Y_MAX


def _safe_xy(x, y):
    """
    ★v16 新增：点击安全闸（比 _onscreen 更严）★
    在"可点击带"之上再要求**离窗口边界有余量**，避免点在窗口边框、
    Wine 桌面、或底栏吞点击带上沿的过渡像素。

    事故依据：目标像素曾算出 y=860（窗口仅 768 高），点击落到窗口之外，
    误触发「上一回合」，游戏内存状态从第 5 回合倒退到第 3 回合（May 5），
    而 Autosave 仍为 05/08/42 ⇒ 状态与存档脱节，整回合进度丢失。
    这类越界点击必须**在代码层拒绝**，不能指望调用方算对。
    """
    try:
        fx, fy = int(round(x)), int(round(y))
    except Exception:
        return False
    # ★v20 订正★ 实际可点击带是 y∈[40,620]、x∈[10,1014]（底栏/信息面板会吞掉
    #   y≥650 的点击 ⇒ 回读到上一次的旧值）。旧值用 WIN_H-30=738，把 (105,680)
    #   这类"看着在窗口内、实际点不到"的像素放行，导致选格点击被吞、白跑一轮。
    return (10 <= fx <= 1014) and (40 <= fy <= 620)


def _panel_hex(log=None, tag=""):
    from collections import Counter
    seen = []
    for _ in range(3):
        v = TP.read_panel_hex(tries=2, log=None)
        if v:
            seen.append(v)
    if seen:
        got = Counter(seen).most_common(1)[0][0]
        if log:
            log(f"    {tag}面板回读 = {got}")
        return got
    return None


def _enter_pick_mode(tf_id, log=None):
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
    # ★v19-44 判据订正★ 判「选格模式已建立」**不能用 ui_state=="map"**。
    #   实测：点 Set-Dest 箭头后面板确实关闭（= 选格模式已建立），
    #   但关闭后的画面会被 list_visible() 误判成 "list"
    #   （列表判据是「≥4 行数字列 + 行距 13~17px」，
    #     主地图上的地名/坐标数字能凑出这个模式）。
    #   ⇒ 旧判据把"成功"读成"失败"，导致三层重试全废、pick 通道整体不可用。
    #   正确判据 = **面板已关闭**（find_dest_label 读不到 Destination）。
    for _t in range(3):
        _vnc(bx, by)
        time.sleep(1.7)
        if TP.find_dest_label(TP._shot()) is None:
            return True
        e = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if e[0] is None:
            return None
        by, bx = e[0], e[1]

    # ★v16：清场重试。实测上一个 set-dest 收尾后（滚动 + 探针点击），
    #   列表/面板可能处于半开状态，点箭头后 ui_state 判定连续 3 次不成立
    #   ⇒ 直接放弃，报「未能进入选格模式」（TF14 (104,148) 即栽在这里）。
    #   处置：Escape 逐级清场 → 点地图空白取焦点 → 重开面板再来一轮。
    if log:
        log("    ⓘ 选格模式未建立 → 清场后重试")
    try:
        TP.reset_to_map()
    except Exception:
        pass
    time.sleep(1.0)
    try:
        _vnc(700, 500)
        time.sleep(0.8)
    except Exception:
        pass

    by, bx = TP.open_tf_panel(tf_id, log=lambda *a: None)
    if by is None:
        if log:
            log("    ✗ 清场后面板仍打不开")
        return None
    # 同上：判据 = 面板已关闭（不是 ui_state=="map"）
    for _t in range(3):
        _vnc(bx, by)
        time.sleep(1.7)
        if TP.find_dest_label(TP._shot()) is None:
            if log:
                log("    ✓ 清场后进入选格模式（面板已关闭）")
            return True
        e = TP.open_tf_panel(tf_id, log=lambda *a: None)
        if e[0] is None:
            return None
        by, bx = e[0], e[1]

    if log:
        log("    ✗ 未能进入选格模式")
    return None


def pick_hex(tf_id, px, py, log=None, prev=None, probe_mode=False):
    """点箭头（面板关闭）→ 点像素 → 面板重开 → 只信面板回读。

    ★v16 安全闸★ 点击坐标必须落在**纯地图安全带**内。
      事故记录（2026-10-04）：滚视野后目标像素算出 (660,860) —— y=860
      远超窗口 768，实际点击落到屏幕下方 Wine 桌面／任务栏区域，
      误触了「上一回合」类控件，结果**游戏内存状态从第 5 回合回退到
      第 3 回合（May 5）**，而 Autosave 仍是 05/08/42 ⇒ 状态与存档脱节。
      该类误触比"设不上目的地"严重得多（丢掉整回合进度）。
      故此处硬拒绝越界坐标，不再依赖调用方自觉。

    ★v15b：回读若等于点击前的旧值（prev），判为**可能陈旧**，重读/重点★
      实测：点 (260,416) 对应 (99,153)，面板却回读上一次的 (100,145)，
      导致误判"未命中"并把下一步基准算错 ⇒ 必须消歧。
    """
    # ★v16 安全闸：坐标必须落在窗口内的纯地图安全带，越界直接拒绝★
    #   PROBE_A 与所有目标像素都必须在这里过闸，否则会点到窗口外/UI 上。
    #   实测事故：y=860（窗口仅 768 高）→ 误触屏幕外控件 → 回合倒退。
    if not _safe_xy(px, py):
        if log:
            log(f"    ⛔ 安全闸拒绝点击 ({int(px)},{int(py)})："
                f"超出可点击带 x=[{CLICK_X_MIN},{CLICK_X_MAX}] "
                f"y=[{CLICK_Y_MIN},{CLICK_Y_MAX}]")
        return None
    if not _enter_pick_mode(tf_id, log=log):
        return None
    last = None
    # ★v19-16 探针模式下严禁重试点击★
    #   `scroll_probe` 用 `pick_hex(PROBE_A)` 量视野位移。探针点固定在
    #   (300,120)，点在同一个像素上，回读**必然**等于 prev —— 视野没动时
    #   这就是合法结果（换轴的依据），不是"陈旧读数"。
    #   旧逻辑把它当成陈旧读数，4 次重入选格模式 + 4 次点击，白烧 ~40s/轮，
    #   直接把 570s 超时预算耗尽（实测 TF15 第 2 轮卡死即此因）。
    #   探针只需**一次**点击 + 一次回读。
    _tries = 1 if probe_mode else 4
    for _t in range(_tries):
        _vnc(int(px), int(py))
        # ★v16：TF14 (104,148) 实测 4.0s 后面板仍在刷新，
        #   回读在 (105,143) 与 (103,153) 之间来回跳（前者是上一次的目的地）。
        #   面板重开有可观延迟，故必须等更久，且读多次取**众数**——
        #   单次读数恰好落在刷新中途就会误判"未命中"。★
        time.sleep(6.5)
        got = _panel_hex(log=log, tag="")
        if got:
            last = got
            if prev is None or got != prev:
                return got
            # 与点击前相同 → 再等一会重读，看是否只是刷新慢
            time.sleep(3.0)
            got2 = _panel_hex(log=None, tag="")
            if got2 and got2 != prev:
                if log:
                    log(f"    （重读刷新）{got} → {got2}")
                return got2
            if log:
                log(f"    ⚠ 回读仍为旧值 {got}，重试点击")
        # ★v18 修★ 原来这里直接 `_vnc(箭头)` 就去点像素，
        #   没有确认面板已关闭、也没确认进入了选格模式。
        #   实测 TF15 滚视野后：重探 (300,120) 连 4 次都回读 (100,135)
        #   （= TF16 的旧目的地），说明**点击根本没落到地图上**——
        #   面板还开着，箭头没生效，后续像素点击全被面板吃掉。
        #   对策：走完整的 `_enter_pick_mode()`（它含清场+确认 ui_state=='map'），
        #   失败就放弃本轮，不再盲点。
        if not _enter_pick_mode(tf_id, log=log):
            if log:
                log("    ✗ 重试前无法重新进入选格模式，放弃")
            return last
    return last


def _scroll_prep():
    """滚视野前必须先清场 + 点地图取焦点（实测铁律）。"""
    try:
        TP.reset_to_map(log=None)
    except Exception:
        pass
    _vnc(*FOCUS_PT)
    time.sleep(0.8)


def scroll_v(north, rows, log=None):
    """垂直滚视野：north=True → 视野北移。返回实际停靠秒数。"""
    secs = min(SCROLL_MAX_S, max(SCROLL_MIN_S, abs(rows) / SCROLL_HZ))
    _scroll_prep()
    # ★v16：贴到 y=0 / y=767 会在切换分辨率/窗口边界时被当成窗口外事件，
    #   实测曾导致回合状态倒退。改为停在安全带内侧（y=2 / y=765），
    #   仍能触发边缘滚动（实测 y=0 与 y=2 等效）。★
    _move(512, 2 if north else WIN_H - 3)
    if log:
        log(f"    滚视野 {'北' if north else '南'} {secs:.1f}s"
            f"（请求 {rows:+d} 格）")
    time.sleep(secs)
    _move(512, 384)
    time.sleep(0.8)
    return secs


def scroll_h(west, cols, log=None):
    """水平滚视野：west=True → 视野西移。返回实际停靠秒数。"""
    secs = min(SCROLL_MAX_S, max(SCROLL_MIN_S, abs(cols) / SCROLL_HZ))
    _scroll_prep()
    _move(2 if west else WIN_W - 3, 384)
    if log:
        log(f"    滚视野 {'西' if west else '东'} {secs:.1f}s"
            f"（请求 {cols:+d} 格）")
    time.sleep(secs)
    _move(512, 384)
    time.sleep(0.8)
    return secs


def scroll_probe(tf_id, north=None, west=None, want=6, log=print,
                 base_px=PROBE_A, prev=None):
    """
    ★v19-7 闭环滚动：滚 → 重探 → 用实测位移校正 → 至多 3 轮收敛。★

    为什么必须闭环（实测 TF18→(96,160) 的 v19-6 日志）：
        请求 (+1,0) 格 → 停 1.5s → 实测位移 **(+10,0) 格**
        请求 (-9,0) 格 → 停 2.6s → 实测位移 **(-10,0) 格**
    根因：滚动**速率不恒定**。游戏在鼠标停于边缘后有起步延迟，
    1.5s 的最小停靠里大部分时间消耗在延迟上，随后以高速滚出约 10 格；
    停得越久收益越小（加速）。所以 `secs = rows / SCROLL_HZ` 这种开环换算
    在小请求量上完全失效 —— 请求 1 格会给 1.5s（最小值），实际滚 10 格。

    闭环做法：
        1) 首轮用开环值起步；
        2) 滚完重探锚点，算出该轴**实际**位移 `act`；
        3) 若 |act| > |want| → 说明超冲，按比例缩短下一轮停靠；
           若 |act| < |want| → 延长，但封顶 SCROLL_MAX_S；
        4) 至多 3 轮；仍不达成就返回实测值，由上层决定是否继续。
    返回 (最终锚点, 累计滚动秒数, 状态)。
    状态：ok / no_scroll(该轴触发死区，换轴重试) / probe_fail / unconverged / nudge_fail
    """
    # 实测速率标定：停 1.5s≈10 格、2.6s≈10 格、3.0s≈10 格 ⇒ **小量请求时速率极高**
    hz_guess = 6.5           # 初始假设：约 6.5 格/秒（比标称 3.4 高，贴近实测）
    secs_used = 0.0
    anchor = prev
    for rnd in range(3):
        secs = min(SCROLL_MAX_S, max(SCROLL_MIN_S, abs(want) / hz_guess))
        if north is not None:
            scroll_v(north, want, log=log)
        else:
            scroll_h(west, want, log=log)
        secs_used += secs
        got = pick_hex(tf_id, *base_px, log=log, prev=anchor,
                        probe_mode=True)
        if not got:
            log(f"    ✗ 闭环滚动第{rnd+1}轮探针失败")
            return anchor, secs_used, "probe_fail"
        if anchor is not None:
            act = (got[1] - anchor[1]) if north is not None else (got[0] - anchor[0])
            log(f"    ·闭环滚动第{rnd+1}轮：请求 {want:+d} 格停 {secs:.1f}s"
                f" → 实测 {act:+d} 格（锚点 {anchor}→{got}）")
            if act == 0:
                # ★v19-14★ 该轴滚动零位移时**不要立刻终止**，
                #   先换轴试一次：实测横向在某些窗口位置完全不触发（真实死区），
                #   而纵向始终有效（实测停 3s = 10 格）。
                #   旧逻辑直接 return，导致「横轴死区 ⇒ 整个任务失败」，
                #   而其实只需改走另一轴即可。
                log(f"    ⚠ 该轴（{'纵' if north is not None else '横'}）零位移，"
                    f"疑似触发死区 → 交由上层换轴重试（不直接终止）")
                return got, secs_used, "no_scroll"
            # ★v19-11 两级收敛：边缘滚只做粗调，残差交给方向键。★
            #   实测边缘滚最小有效位移就是 **10 格**（停 3s），
            #   而目标常只差 5~9 格 ⇒ 任何"滚到位"的方案都必然过冲或够不着。
            #   方向键则可精确 2 格/次且可逆（记忆条目：
            #   "方向键单次生效时=精确 2 格、可逆"）。
            #   故：残差 ≤ 2 格 → 用方向键；否则先边缘滚再收尾。
            if want - act == 0:
                return got, secs_used, "ok"
            if abs(want - act) <= 2:
                log(f"    ·边缘滚已把残差压到 {want-act:+d} 格 → 交给方向键收尾")
                got2 = _nudge(tf_id, want - act, north=north, west=west,
                              log=log, anchor=got)
                return got2, secs_used, ("ok" if got2 is not None else "nudge_fail")
            # 残差仍大：先边缘滚继续粗调
            want = want - act
        else:
            # 首轮无 prev 参照：直接量出速率
            log(f"    ·闭环滚动首轮锚点 {got}")
        anchor = got
    log(f"    ⓘ 闭环滚动 3 轮未完全收敛，停在 {anchor}")
    return anchor, secs_used, "unconverged"


# 方向键 → hex 增量。★实测：单次生效=精确 2 格、可逆；
#   但同通道曾多次出现"连按 8 次零位移"，故每次连按都必须重探验证。
_NUDGE_KEYS = {
    ("v", -1): "Up", ("v", +1): "Down",       # 视野北移 / 南移
    ("h", -1): "Left", ("h", +1): "Right",
}
NUDGE_GRID = 2           # 单次方向键的格数


def _nudge(tf_id, want_hex, north=None, west=None, log=print, anchor=None):
    """
    用方向键把视野细调 want_hex 格（可正可负）。
    必须逐次重探：实测同一按键通道可能连续多次零位移。
    返回最终锚点。
    """
    axis = "v" if north is not None else "h"
    # ★语义实测校准★ want_hex 是**锚点 hex 需要变化的方向**，
    #   与「滚哪个边缘」是同一方向（滚西 = 视野西移 = 锚点 hex 减小）。
    #   方向键同样：Right = 视野东移 = 锚点 hex **增大**。
    #   ★v19-12 修正★ 原代码用 step_dir（边缘方向）反推按键，导致
    #   请求 -1 格却按 Right（+2 格），与边缘滚方向叠加后越调越远：
    #   实测 (100,135)→(102,135)→(100,135) 来回摆，永远不收敛。
    #   现在直接按 want_hex 的符号选键。
    step_dir = 1 if want_hex > 0 else -1
    key = _NUDGE_KEYS[(axis, step_dir)]
    remaining = want_hex
    cur = anchor
    # ★方向键必须窗口持焦点，否则全部静默丢失★（实测铁律）
    _scroll_prep()
    for i in range(8):
        if remaining == 0 or cur is None:
            break
        # ★v19-13 精度处理★ 方向键单次 = 精确 2 格，但残差常是 1 格。
        #   故**每轮只按 1 次**，用实测值修正 remaining，允许超调后反向按回。
        #   旧实现按 |remaining|//2 次 ⇒ 请求 -1 格也按 1 次（+2 格），
        #   于是 (100,135)→(102,135)→(100,135) 无限摆动。
        _key(key, pace=0.6)
        time.sleep(1.2)
        got = pick_hex(tf_id, *PROBE_A, log=log, prev=cur,
                        probe_mode=True)
        if not got:
            log(f"    ·方向键收尾探针失败")
            return cur
        act = (got[1] - cur[1]) if axis == "v" else (got[0] - cur[0])
        log(f"    ·方向键 {key}×1：{cur} → {got}（实测 {act:+d} 格，"
            f"残差 {remaining:+d} → {remaining-act:+d}）")
        if act == 0:
            log(f"    ✗ 方向键零位移（记忆条目：同通道可能连续失效）→ 放弃方向键")
            return got
        cur = got
        remaining -= act
        # 超调了就反号，下一轮按反向键按回来
        if remaining != 0:
            key = _NUDGE_KEYS[(axis, 1 if remaining > 0 else -1)]
    return cur


def _hex_dist(a, b):
    """两格之间的六角网格距离（dx 与 dy 各算 2 格纵深，故先转 axial）。"""
    if not a or not b:
        return 99
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy, (dx + dy) // 2)


def _read_dest_v20(log=None):
    """读面板左上「Set TF Destination」下一行的 Hex（x,y）。

    ★v20 订正★ 不用自定义裁切（实测会读到 +20 格的噪声），改用
      tfpanel.read_panel_hex（多轮投票，已 vision 交叉验证与地面真值一致）。
    """
    v = TP.read_panel_hex(tries=3, log=None)
    if log and v:
        log(f"    面板回读 = {v}")
    return v


def _click_pick(tf_id, px, py, log=None):
    """开面板 → 点 Set TF Destination（面板关闭=选格模式）→ 点地图像素 → 读回目的地。"""
    if not _enter_pick_mode(tf_id, log=log):
        return None
    _vnc(px, py)
    time.sleep(1.6)
    return _read_dest_v20(log=log)


def _reset_map_v20():
    try:
        TP.reset_to_map()
    except Exception:
        pass
    time.sleep(0.5)


def set_tf_dest(tf_id, tx, ty, log=print, tol=2, deadline=None):
    """★v23（2026-10-10 实机验证，第十九局全程使用）★

    模型（地面真值标定）：进入选格模式后，点屏幕正中 (512,384) 设定的目的地
      = **视野中心格 C**。要设 T，只需把 T 移进视野出射控制区。
    流程（小地图跳转 = 绝对定位，不累积误差）：
      ① jump_minimap(J) 把视野送到 J 附近；
      ② 进选格模式 → 点屏幕正中 → 面板回读 D（= 视野中心格）；
      ③ 若 |D-T|<=tol 则命中；否则 J += (T-D) 再跳，2~3 轮收敛。
    ★旧实现失败根因★ 用「小地图黄框」推视野中心——黄框映射有约 (+3.24,+3.06)
      格系统偏差，落点整体偏约 9 格 ⇒ 报成功但设错格。黄框只可用于相对粗调。
    ★注★ 打开某 TF 面板时游戏会把视野重定心到该 TF，故 C 随所选 TF 变化——
      每轮必须重读，禁止跨 TF 复用。核验最终仍以结算后读层 target_x/y 为准。

    ★2026-10-15 修（挂死）★
      实测：目标在**小地图红框外**（如珊瑚海剧本的 PM(98,130)）时，
      `jump_minimap` 被 clamp 到 (105,125)，每轮都差 7 格 ⇒ 4 轮全不命中；
      而每轮的 `_enter_pick_mode` 内含 3~6 次 `open_tf_panel`（每次几十次
      点击+OCR）⇒ 累计数百次 GUI 操作 ⇒ **整个调用挂死数分钟、无输出**
      （表现为 `witp-cmd set-dest` 超时且 stdout 为空，进而整局卡住）。
      ⇒ 新增 `deadline`（秒）：超时即返回当前最佳结果并明确告警，
        绝不无限重试。上层据此改用其它通道（或接受近似目标）。
    """
    from lib import navkeys as NAV
    import time as _time
    _t0 = _time.time()
    _dl = deadline if deadline else 140.0

    def _out_of_time():
        return (_time.time() - _t0) > _dl

    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v23：小地图跳转 + 点中心；时限 {_dl:.0f}s）===")
    jx, jy = tx, ty

    def _clear():
        for _ in range(6):
            if TP.ui_state() == "map":
                break
            _key("Escape", pace=0.6)
        time.sleep(0.4)
        try:
            _vnc(300, 300)
        except Exception:
            pass
        time.sleep(0.4)

    def _center_read():
        for _ in range(3):
            if _enter_pick_mode(tf_id, log=None):
                _vnc(VIEW_CX, VIEW_CY)
                time.sleep(1.8)
                v = TP.read_panel_hex(tries=4, log=None)
                if v:
                    return v
            time.sleep(0.5)
        return None

    D = None
    for k in range(4):
        if _out_of_time():
            log(f"  ⏱ 已达时限 {_dl:.0f}s（第 {k} 轮前）—— 停止重试，返回当前结果")
            break
        _clear()
        try:
            NAV.jump_minimap(jx, jy, log=lambda *a: None)
        except Exception as _e:
            log(f"  小地图跳转异常: {_e}")
        time.sleep(1.1)
        if _out_of_time():
            log(f"  ⏱ 已达时限 {_dl:.0f}s（跳转后）—— 停止重试")
            break
        D = _center_read()
        log(f"  [{k}] 跳转({jx},{jy}) → 回读 D={D}（目标 {tx},{ty}）")
        if D is None:
            continue
        if abs(D[0] - tx) <= tol and abs(D[1] - ty) <= tol:
            log(f"  ✓ 命中/近似 ({tx},{ty})，实测 {D}")
            return True, D
        jx += (tx - D[0]); jy += (ty - D[1])
    if D is not None:
        log(f"  ⚠ 未精确命中，末次读数 {D}（以结算后读层核验）")
    else:
        log("  ✗ 回读始终失败")
    return (D is not None), D


if __name__ == "__main__":
    _tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    _tx = int(sys.argv[2]) if len(sys.argv) > 2 else 118
    _ty = int(sys.argv[3]) if len(sys.argv) > 3 else 122
    ok, h = set_tf_dest(_tf, _tx, _ty)
    print("RESULT", ok, h)
