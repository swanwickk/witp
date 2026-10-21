"""winmsg3.py — 诊断 + 投递：确认窗口是否收到消息

步骤：
  1. 列出游戏进程的所有顶层窗口（含不可见）
  2. 检查哪个窗口是真正的消息接收者（GetForegroundWindow / 有输入焦点）
  3. 尝试三种投递：PostMessage(hwnd) / SendMessage(hwnd) / PostMessage(child)
  4. 报告每次投递的返回值
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102


def get_pid_of_window(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def all_windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        out.append({
            "hwnd": hwnd, "title": buf.value, "cls": cls.value,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "pid": get_pid_of_window(hwnd),
        })
        return True

    user32.EnumWindows(_cb, 0)
    return out


def child_windows(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(h, buf, n + 2)
        out.append({"hwnd": h, "cls": cls.value, "title": buf.value,
                    "visible": bool(user32.IsWindowVisible(h))})
        return True

    user32.EnumChildWindows(hwnd, _cb, 0)
    return out


def main():
    wins = all_windows()
    game = [w for w in wins if "War in the Pacific" in w["title"]]
    print("== game windows ==")
    for w in game:
        print("  hwnd=%s pid=%s visible=%s cls=%s title=%s" % (
            w["hwnd"], w["pid"], w["visible"], w["cls"], w["title"]))

    if not game:
        print("ok=False error=no-game-window")
        return 1

    pid = game[0]["pid"]
    print("\n== same-pid windows ==")
    for w in wins:
        if w["pid"] == pid and w["hwnd"] != game[0]["hwnd"]:
            print("  hwnd=%s visible=%s cls=%s title=%s" % (
                w["hwnd"], w["visible"], w["cls"], w["title"]))

    fg = user32.GetForegroundWindow()
    print("\nforeground_hwnd=%s" % fg)
    print("foreground_is_game=%s" % (fg == game[0]["hwnd"]))

    print("\n== child windows ==")
    for c in child_windows(game[0]["hwnd"]):
        print("  hwnd=%s cls=%s visible=%s title=%s" % (
            c["hwnd"], c["cls"], c["visible"], c["title"]))

    # 投递测试
    hwnd = game[0]["hwnd"]
    print("\n== post test (key=t) ==")
    vk, scan = ord("T"), user32.MapVirtualKeyW(ord("T"), 0)
    down = 1 | (scan << 16)
    up = down | (1 << 30) | (1 << 31)

    r1 = user32.PostMessageW(hwnd, WM_KEYDOWN, vk, down)
    e1 = ctypes.get_last_error()
    print("PostMessage WM_KEYDOWN -> ret=%s err=%s" % (r1, e1))
    time.sleep(0.05)
    r2 = user32.PostMessageW(hwnd, WM_KEYUP, vk, up)
    print("PostMessage WM_KEYUP   -> ret=%s err=%s" % (r2, ctypes.get_last_error()))

    # 也试试 WM_SYSKEYDOWN 与 WM_COMMAND
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_COMMAND = 0x0111
    WM_CHAR = 0x0102
    r5 = user32.PostMessageW(hwnd, WM_CHAR, ord("t"), down)
    print("PostMessage WM_CHAR    -> ret=%s" % r5)
    r6 = user32.PostMessageW(hwnd, WM_SYSKEYDOWN, vk, down)
    print("PostMessage WM_SYSKEY  -> ret=%s" % r6)
    # 键盘消息之外：试试 WM_ACTIVATE 刷新焦点状态
    WM_ACTIVATE = 0x0006
    r7 = user32.PostMessageW(hwnd, WM_ACTIVATE, 1, 0)
    print("PostMessage WM_ACTIVATE-> ret=%s" % r7)

    print("ok=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
