"""winmsg2.py — Win32 消息投递（先激活窗口 + 同时发 WM_KEYDOWN/UP 与 WM_CHAR）

与 winmsg.py 的差别：
  · 先 SetForegroundWindow/ShowWindow 把窗口激活（部分引擎只在激活态处理按键）
  · 除 WM_KEYDOWN/WM_KEYUP 外补发 WM_CHAR（引擎可能读字符消息而非虚拟键）
  · 支持 --scan：枚举进程窗口与线程消息队列状态，判断是否卡住
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
SW_RESTORE = 9
TITLE_HINTS = ("War in the Pacific", "WITP", "Admiral")


def list_windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            t = buf.value
            if any(h.lower() in t.lower() for h in TITLE_HINTS):
                out.append((hwnd, t, bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows(_cb, 0)
    return out


def activate(hwnd):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    time.sleep(0.4)


def send_key(hwnd, ch, with_char=True):
    vk = ord(ch.upper())
    scan = user32.MapVirtualKeyW(vk, 0)
    down = 1 | (scan << 16)
    up = down | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, down)
    if with_char:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), down)
    time.sleep(0.06)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, up)
    time.sleep(0.06)
    return vk


def main():
    args = [a for a in sys.argv[1:]]
    if not args or args[0] == "--scan":
        for hwnd, t, vis in list_windows():
            print("hwnd=%s visible=%s title=%s" % (hwnd, vis, t))
        return 0

    wins = list_windows()
    if not wins:
        print("ok=False error=no-window")
        return 1
    hwnd, title, _ = wins[0]
    print("window=%s" % title)

    if "--activate" in args:
        activate(hwnd)
        print("activated=1")

    nockar = "--nochar" in args
    keys = []
    for a in args:
        if a.startswith("--"):
            continue
        keys.extend([c for c in a if c.strip()])

    for k in keys:
        vk = send_key(hwnd, k, with_char=not nockar)
        print("sent=%s vk=%d" % (k, vk))
    print("ok=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
