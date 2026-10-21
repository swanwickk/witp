"""gui_cal.py — 通用 GUI 标定器：基线存档 → GUI 操作 → 新存档 → 差分

用法:
  python3 gui_cal.py --baseline A.pws --act "click 300 330" --out B.pws

设计要点：
  ★ 存档必须由 GAME 自己写，不能用外部拷贝，否则差分不到运行时状态。
    这里用游戏内 SAVE 菜单（Esc → save），或直接复制当前 autosave。
  ★ 最省事的做法：GUI 操作前先手动存一档、操作后再存一档，然后调用
    diffcal.py 比对。本脚本只负责"操作"和"存档"两步的自动化。
"""
import argparse
import os
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
DISP = os.environ.get("WITP_DISPLAY", ":97")
SAVE = ("/root/.wine-witp-mcp/prefix/drive_c/1108r9/"
        "War in the Pacific Admiral's Edition/SAVE")


def xdo(*args, wait=0.0):
    subprocess.run(["xdotool", *args], capture_output=True,
                   env=dict(os.environ, DISPLAY=DISP))
    if wait:
        time.sleep(wait)


def win_id():
    r = subprocess.run(["xdotool", "search", "--name", "War in the Pacific"],
                       capture_output=True, text=True,
                       env=dict(os.environ, DISPLAY=DISP))
    ids = [l for l in r.stdout.strip().split("\n") if l]
    return ids[-1] if ids else None


def click(x, y, wait=1.5):
    w = win_id()
    xdo("mousemove", "--window", w, str(x), str(y), wait=0.35)
    xdo("click", "--window", w, "1", wait=wait)


def rclick(x, y, wait=1.5):
    w = win_id()
    xdo("mousemove", "--window", w, str(x), str(y), wait=0.35)
    xdo("click", "--window", w, "3", wait=wait)


def key(k, wait=1.2):
    w = win_id()
    xdo("key", "--window", w, k, wait=wait)


def shot(p="/tmp/_cal.png"):
    subprocess.run(["import", "-window", "root", "-crop", "1024x768+0+0",
                    "+repage", p], capture_output=True,
                   env=dict(os.environ, DISPLAY=DISP))
    return p


def save_slot(slot, wait_file=25):
    """在游戏内存档到指定槽位，返回存档路径。

    实测序列：Esc → SAVE GAME 按钮 → 列表选槽 → SELECT SAVE GAME → 等文件稳定
    """
    path = os.path.join(SAVE, "wpae%03d.pws" % slot)
    before = os.path.getmtime(path) if os.path.exists(path) else 0

    key("Escape", 2.0)
    # 顶部工具栏的 SAVE 按钮位置（实测在左上角第一个图标）
    click(28, 16, 2.5)
    time.sleep(1.5)
    # 存档槽行 y = 123 + 16*slot（实测）
    y = 123 + 16 * slot
    click(400, y, 1.2)
    click(336, 565, 3.0)     # SELECT SAVE GAME
    # 可能弹覆盖确认
    time.sleep(1.0)
    click(508, 422, 2.0)

    # 等文件写稳
    last = -1
    for _ in range(int(wait_file * 2)):
        time.sleep(0.5)
        if os.path.exists(path):
            sz = os.path.getsize(path)
            if sz == last and sz > 100000 and os.path.getmtime(path) != before:
                return path
            last = sz
    return path if os.path.exists(path) else None


def parse_action(s):
    """'click 300 330' / 'rclick 500 400' / 'key t' / 'sleep 3'"""
    parts = s.split()
    op = parts[0]
    if op in ("click", "rclick"):
        return lambda: click(int(parts[1]), int(parts[2]),
                             float(parts[3]) if len(parts) > 3 else 1.5)
    if op == "key":
        return lambda: key(parts[1], float(parts[2]) if len(parts) > 2 else 1.2)
    if op == "sleep":
        return lambda: time.sleep(float(parts[1]))
    raise SystemExit("未知动作: " + s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--do", nargs="*", default=[], help="依次执行的动作")
    ap.add_argument("--shot", default=None, help="最后截一张图")
    a = ap.parse_args()
    for s in a.do:
        print("执行:", s)
        parse_action(s)()
    if a.shot:
        print("截图:", shot(a.shot))
