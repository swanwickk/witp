#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""战略图跳转 + 选格设定 TF 目标（绕过小地图红框限制）。

流程：
  ① Ctrl+A 开战略图 → 点目标基地像素 → Esc 关图（视野已居中该区域）
  ② 开 TF 面板 → 点 Set TF Destination 箭头（面板关闭=选格模式）
  ③ 点屏幕正中 (512,384) ← 该像素对应「视野中心格」
  ④ 面板重开 → 读 Hex 回读核验
用法: python3 witp_setdest_strat.py TF6 98 130 [strat_px_x strat_px_y]
"""
import os
import subprocess
import sys
import time

os.environ.setdefault("DISPLAY", ":98")
sys.path.insert(0, "/root/.hermes/profiles/witp/witp-agent")
sys.path.insert(0, "/root/.hermes/profiles/witp/workspace")

from lib import tfpanel as TP           # noqa: E402
import lib.setdest14 as SD              # noqa: E402
from witp_stratjump import strat_jump   # noqa: E402


def main():
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF6"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 98
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 130
    sx = int(sys.argv[4]) if len(sys.argv) > 4 else 500
    sy = int(sys.argv[5]) if len(sys.argv) > 5 else 432

    print(f"=== strat set-dest {tf} → ({tx},{ty})，战略图点 ({sx},{sy}) ===")
    if not strat_jump(sx, sy, log=print):
        print("  ✗ 战略图跳转失败")
        return 1
    # 进选格模式 → 点屏幕正中 → 读回
    ok = SD._enter_pick_mode(tf, log=print)
    print(f"  进选格模式: {ok}")
    if not ok:
        print("  ✗ 未能进入选格模式")
        return 1
    SD._vnc(SD.VIEW_CX, SD.VIEW_CY)
    time.sleep(2.0)
    v = TP.read_panel_hex(tries=5, log=None)
    print(f"  → 面板回读目的地 = {v}（目标 {tx},{ty}）")
    SD._key("Escape", 0.8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
