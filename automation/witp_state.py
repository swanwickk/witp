#!/usr/bin/env python3
"""
witp_state.py —— 统一状态机（一次性根治"残留状态污染"）

═══ 为什么需要它 ═══
本轮调试中反复出现的失败模式（每次都要重新排查）：
  · 上一次运行留下 TF 主面板开着（ui_state='main'）
    ⇒ 本次的小地图点击**完全无效**（视野不动，实测）
  · 上一次留下编队列表（ui_state='list'）
    ⇒ 本次 read_moveto 打不开列表 / to_map 误判
  · 各函数各自用不同判据、不同 Escape 次数 ⇒ 有的清干净有的没有

根因：**没有任何一处负责把 UI 恢复干净**，全靠各调用点自觉。

═══ 设计 ═══
  ensure_map()     回到地图态；失败**抛异常**（绝不带脏状态继续）
  assert_map()     前置断言
  read_moveto(tf)  T 列表读 moveto，**失败重试后仍失败即抛异常**
  mm_click_hex()   小地图精定位（点红框内像素把视野送到目标格）
  read_center_hex() 主面板锚点法读视野中心格
  set_dest_here()  当前视野下设目的地

═══ 已实测确立的常量 ═══
小地图（用户澄清：小地图=全太平洋；红框=剧本限制区；黄框=当前视野）：
    红框(可点区) x[939,964] y[715,744]；框外点击被忽略
    映射 mm(941,717)↔hex(100,116)，横向 1.909 mm-px/格，纵向 0.694 mm-px/格
主地图：
    W = H = 37.0 px/格（沿单轴逐点实测，4/4 帧一致）
    锚点 (287,274)，窗口中心 (512,384)
    TF 列表行 y：TF14=247 TF15=261 TF16=275 TF17=289 TF18=303
"""
import os
import re
import subprocess
import sys
import time

os.environ.setdefault("DISPLAY", ":98")
sys.path.insert(0, "/root/.hermes/profiles/witp/workspace")
sys.path.insert(0, "/root/.hermes/profiles/witp/witp-agent/lib")

import executor as ex      # noqa: E402
import tfpanel as TP       # noqa: E402
import setdest14 as SD     # noqa: E402

WS = "/root/.hermes/profiles/witp/workspace"

RED = (939, 964, 715, 744)
MM_REF = (941, 717)
HEX_REF = (100, 116)
K_X = 1.909
K_Y = 0.694

W = H = 37.0
CENTER = (512, 384)
ANCHOR = (287, 274)
CLICK_X = (70, 980)
CLICK_Y = (60, 690)
TF_Y = {"TF14": 247, "TF15": 261, "TF16": 275,
        "TF17": 289, "TF18": 303}


class StateError(RuntimeError):
    """UI 状态无法恢复到可操作地图态。"""


def _key(k, pace=0.9):
    subprocess.run(["python3", f"{WS}/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _click(px, py, act="click", pace=2.5):
    ox, oy = ex.get_window_offset()
    subprocess.run(["python3", f"{WS}/witp_vncclick.py",
                    str(int(px + ox)), str(int(py + oy)), act],
                   capture_output=True)
    time.sleep(pace)


def shot(p="/tmp/ws_state.png"):
    subprocess.run(["bash", "-c",
                    f"DISPLAY=:98 import -window root -crop 1024x768+0+0 {p}"],
                   capture_output=True)
    return p


def state():
    """当前 ui_state（异常时返回 '?'）。"""
    try:
        return TP.ui_state()
    except Exception:
        return "?"


def ensure_map(max_esc=12, log=None):
    """
    回到地图态。失败抛 StateError（**绝不静默继续**）。

    流程：reset_to_map → 循环 Escape 直到 ui_state=='map'。
    """
    try:
        TP.reset_to_map(log=None)
    except Exception:
        pass
    for i in range(max_esc):
        st = state()
        if st == "map":
            time.sleep(0.6)
            return True
        if log:
            log(f"      (清场第{i+1}次，当前 ui_state={st!r})")
        _key("Escape", 0.9)
    st = state()
    if st != "map":
        shot("/tmp/ws_blocked.png")
        raise StateError(f"无法回到地图态（ui_state={st!r}），"
                         f"截图 /tmp/ws_blocked.png")
    return True


def assert_map(where=""):
    st = state()
    if st != "map":
        shot("/tmp/ws_assert.png")
        raise StateError(f"{where}: 需要地图态，实际 ui_state={st!r}")
    return True


def read_dest(tf, tries=3, log=None):
    """
    读该 TF 的**当前目的地**（Destination 字段）。

    ★★v19-87 换通道★★
    历史脚本用「T 列表的 moveto 列」回读，但实测**当前列表视图没有该列**：
      表头 = TF Mission | Endure | Needed Max | CruiseMode | 4/C |
             Supply | Fuel | Troops | Control | Ships
      TF15 行 OCR = '15 Replenishment 7395 1280 611 10 9784 Human'
    完全没有 moveto/目的地信息。故该通道不可用（历史脚本写于列布局变化前）。

    改用**主面板 Destination 字段** —— tfpanel._panel_hex 读的就是它，
    本轮已反复验证可靠（多次 5/5 帧一致）。
    语义：读回的是「该 TF 当前的目的地格」；若未设过，等于其自身位置。

    失败即抛异常（不允许 None 流入后续计算）。
    """
    last = ""
    for i in range(tries):
        ensure_map(log=log)
        if not SD._enter_pick_mode(tf, log=None):
            last = "选格模式进不去"
            time.sleep(1.5)
            continue
        # 点锚点 → 读回该像素的格（此时面板里显示的 Destination 即本 TF 目的地）
        SD._vnc(*ANCHOR)
        reads = []
        for k in range(4):
            time.sleep(6.0 if k == 0 else 2.2)
            h = SD._panel_hex(log=None, tag="")
            if h:
                reads.append(h)
        ensure_map(log=log)
        if reads:
            a = reads[-1]
            for k in range(len(reads) - 1, 0, -1):
                if reads[k] == reads[k - 1]:
                    a = reads[k]
                    break
            return a
        last = "锚点回读为空"
        if log:
            log(f"      (read_dest 第{i+1}次失败：{last})")
        time.sleep(1.5)
    raise StateError(f"{tf} 目的地读取失败（{tries} 次）：{last}")


def read_center_hex(tf="TF15", log=None):
    """主面板锚点法读**视野中心**格。"""
    ensure_map(log=log)
    if not SD._enter_pick_mode(tf, log=None):
        raise StateError(f"无法进入选格模式（读视野中心）")
    SD._vnc(*ANCHOR)
    reads = []
    for i in range(4):
        time.sleep(6.0 if i == 0 else 2.2)
        h = SD._panel_hex(log=None, tag="")
        if h:
            reads.append(h)
    # ★v19-86★ 读完后必须**真正**回到 map。
    #   实测 read_center_hex 结束时状态是 'list'（面板关闭后残留列表态），
    #   而小地图点击**只在 map 态生效** ⇒ 后续 mm_click 全被吃掉，
    #   表现为"小地图点了但视野不动"。这是本轮最后一处状态污染。
    ensure_map(log=log)
    if not reads:
        raise StateError("锚点回读为空（读视野中心失败）")
    a = reads[-1]
    for i in range(len(reads) - 1, 0, -1):
        if reads[i] == reads[i - 1]:
            a = reads[i]
            break
    return (a[0] + round((CENTER[0] - ANCHOR[0]) / W),
            a[1] + round((CENTER[1] - ANCHOR[1]) / H))


def hex_to_mm(hx, hy):
    return (MM_REF[0] + (hx - HEX_REF[0]) * K_X,
            MM_REF[1] + (hy - HEX_REF[1]) * K_Y)


def mm_click_hex(tx, ty, clamp=True, log=None):
    """点小地图红框内像素，把视野送到目标格附近。返回实际点的像素。"""
    mmx, mmy = hex_to_mm(tx, ty)
    if not (RED[0] <= mmx <= RED[1] and RED[2] <= mmy <= RED[3]):
        if not clamp:
            raise StateError(f"目标 ({tx},{ty}) 映射到红框外 "
                             f"({mmx:.0f},{mmy:.0f})")
        mmx = max(RED[0], min(RED[1], mmx))
        mmy = max(RED[2], min(RED[3], mmy))
        if log:
            log(f"      ⚠ 超红框 → 钳到 ({mmx:.0f},{mmy:.0f})")
    ensure_map(log=log)
    _click(round(mmx), round(mmy), pace=3.0)
    if log:
        log(f"      小地图点 ({mmx:.0f},{mmy:.0f})")
    return mmx, mmy


def set_dest_here(tf, px, py, log=None):
    """在当前视野下点 (px,py) 设目的地。"""
    ensure_map(log=log)
    if not ex.open_tf_list(retries=3):
        raise StateError("T 列表打不开（设目的地）")
    _click(200, TF_Y[tf], "dblclick", pace=3.0)
    ox, oy = ex.get_window_offset()
    subprocess.run(["python3", f"{WS}/witp_vncclick.py",
                    str(534 + ox), str(204 + oy), "click"],
                   capture_output=True)
    time.sleep(2.2)
    _click(px, py, pace=3.0)
    _key("Escape", 2.0)


if __name__ == "__main__":
    print("=== witp_state 自检 ===")
    print("ui_state =", state())
    print("ensure_map →", ensure_map(log=print))
    print("ui_state =", state())
