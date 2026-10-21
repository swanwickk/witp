"""
搜索扇面（Search Arc）设置 —— 依 WitP-AE 手册 Ch 07 §7.0.2：

  "Search missions can be given an arc of 10-degree sectors to be searched.
   Planes in a group are assigned to a search one at a time from the start
   sector to the end sector. If there are more planes than sectors, then the
   process is repeated."

即：起始扇区(Start OGC) → 终止扇区(End OGC)，每扇区 10 度。
036 个扇区 = 360 度。扇面设置**独立于** Search 百分比：
Search=100 只是「有多少机去搜」，扇面决定「搜哪个方向」——两者都要设。

★ 本模块只负责「按钮坐标定位 + 点击 + 面板回读」，不含开列表/选行逻辑
  （那部分由 witp-cmd set-search 已有通道负责）。

坐标全部以 **游戏区 1024x768 内的像素** 表示，由 executor 的窗口偏移换算到屏幕。
"""
import os
import re
import subprocess
import time

os.environ.setdefault("DISPLAY", ":98")

import executor as EX

# ── 面板区块定位（待实机标定；先给出与 set-search 百分比按钮同一区块的推定值）──
# 依据：set-search 的 Search/ASW 百分比按钮已实测在 zero+90 / zero+111（zero=亮度簇零点）。
# 同区块内 Start/End OGC 按钮按「百分比按钮右侧同列」推定，实测后订正。
ARC_BTN_OFFSETS = {
    "start": None,   # 待标定：相对百分比按钮的 (dx, dy)
    "end": None,
    "reset": None,
}


def _shot(path="/tmp/_arc.png"):
    EX.vnc_shot(path) if hasattr(EX, "vnc_shot") else EX.shot(path)
    return path


def set_arc(ag_id: str, start_ogc: int, end_ogc: int, log=print) -> bool:
    """
    在**已打开该中队详情面板**的前提下，设置搜索扇面。
      start_ogc / end_ogc: 0..359，以 10 度为一个扇区编号（0=北，顺时针）。
    返回是否成功（True = 两端都点过且回读一致）。
    """
    assert 0 <= start_ogc <= 359 and 0 <= end_ogc <= 359, "OGC 必须在 0..359"
    log(f"[arc] {ag_id} 扇面 {start_ogc:03d} -> {end_ogc:03d}（每扇区 10 度）")
    # TODO(实测)：按钮坐标标定。标定前明确拒绝执行，不猜。
    if ARC_BTN_OFFSETS["start"] is None:
        log("[arc] ✗ 按钮坐标尚未标定，拒绝盲点（宁可不设，不设错方向）")
        return False
    return False
