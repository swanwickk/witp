"""gui_commands.py — 通过界面操作设置"纯运行时"字段（不进存档的那些）

适用：Follow TF / Meet TF / TFRetirement —— 实测这些字段 GUI 改完存盘零差异，
      是纯运行时状态，只能通过界面设置。

设计：所有函数都做"读状态 → 点击 → 再读状态"闭环，返回 (ok, 实际状态)。
坐标与色值来自实测（1024x768）。
"""
import os
import subprocess
import time

from PIL import Image
import gui_state

WS = "/root/.hermes/profiles/witp/workspace"
PORT = os.environ.get("WITP_VNC_PORT", "5901")
DISP = os.environ.get("WITP_DISPLAY", ":97")

# ── 实测坐标 ─────────────────────────────────
RETIRE_TEXT_Y = 278        # Retirement 文字行（可点）
TF_LIST_FIRST_Y = 246      # TF 列表首行
TF_LIST_ROW_H = 14


def _sh(cmd, **kw):
    kw.setdefault("text", True)
    return subprocess.run(cmd, capture_output=True,
                          env=dict(os.environ, DISPLAY=DISP), **kw)


def click(x, y, act="click", wait=0.5):
    _sh(["python3", f"{WS}/witp_vncclick2.py", str(x), str(y), act])
    time.sleep(wait)


def key(k, wait=0.7):
    _sh(["python3", f"{WS}/witp_vnckey2.py", k])
    time.sleep(wait)


def shot(path="/tmp/_gui.png"):
    _sh(["import", "-window", "root", path])
    return Image.open(path).convert("RGB")


def retirement_state(im=None):
    """返回 'allowed' / 'remain' / 'unknown'（OCR 文字匹配）。"""
    st, _txt = gui_state.retirement_state(im)
    return st


def open_tf(tf_slot):
    key("Escape", 1.0)
    key("t", 3.0)
    y = TF_LIST_FIRST_Y + TF_LIST_ROW_H * (tf_slot - 1)
    click(250, y, wait=1.0)
    click(250, y, wait=4.5)
    return shot()


def set_retirement(tf_slot, target):
    """target: 'remain' | 'allowed'。返回 (ok, 实际状态)。"""
    want = "remain" if target in ("remain", "station") else "allowed"
    im = open_tf(tf_slot)
    cur = retirement_state(im)
    if cur == want:
        return True, cur
    for _ in range(4):
        # 点文字行切换（实测 y=278 命中率最高）
        click(400, 288, wait=2.5)
        cur = retirement_state()
        if cur == want:
            return True, cur
    return False, cur


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        print(set_retirement(int(sys.argv[1]), sys.argv[2]))
    else:
        print("retirement:", retirement_state())


def set_follow(tf_slot, target_tf=None):
    """设置 Follow Task Force（需进入 Routing 子面板）。

    步骤：开 TF 面板 → 点 Set TF Routing(533,228) → 点 Follow 行 → 地图选目标 TF
    实测：该功能需要目标 TF 在视野内，且面板层级较深，成功率不稳定。
    返回 (ok, 说明)。
    """
    open_tf(tf_slot)
    click(533, 228, wait=4.0)      # Set TF Routing
    # 记录当前截图供人工核对
    im = shot()
    im.save("/tmp/follow_before.png")
    click(180, 337, wait=3.0)      # Follow Task Force 行
    im2 = shot()
    im2.save("/tmp/follow_after.png")
    return False, "需人工在地图上点选目标 TF（见 /tmp/follow_after.png）"


def clear_destination(tf_slot):
    """清除 TF 目的地（Patrol Zone 的前置条件）。

    实测：主 TF 面板没有 Clear Destination，只能在 Set TF Destination
    之后的选格地图模式里右键取消。
    """
    open_tf(tf_slot)
    click(533, 200, wait=4.0)      # Set TF Destination 进入选格
    click(500, 400, "rclick", wait=3.0)   # 右键取消，清空
    return True, "right-click cancel"
