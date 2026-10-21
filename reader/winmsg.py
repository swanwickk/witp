"""winmsg.py — 通过 Win32 消息向 WitP 引擎投递按键（不依赖截图/OCR/坐标点击）

原理：
  游戏窗口是标准 Win32 窗口。向它 PostMessage(WM_KEYDOWN/WM_KEYUP) 即可让引擎
  的消息循环收到按键——这是**进程间消息传递**，不是模拟物理键鼠、不读屏幕。

  比 XTEST/xdotool 可靠：不依赖窗口焦点、不需要 X 显示坐标、不受 Wine 输入法干扰。

用法：
  wine C:\\py32\\python.exe winmsg.py <keys>          # keys 如 "e" 或 "e,y"
  wine C:\\py32\\python.exe winmsg.py --list          # 列出候选窗口

输出：每行 key=value（ok=True / window=标题 / hwnd=句柄）
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

# 窗口标题特征（游戏主窗口标题随版本略有差异，用子串匹配）
TITLE_HINTS = ("War in the Pacific", "WITP", "Admiral")


def list_windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if any(h.lower() in title.lower() for h in TITLE_HINTS):
                out.append((hwnd, title))
        return True

    user32.EnumWindows(_cb, 0)
    return out


def find_game_window():
    cands = list_windows()
    # 优先"主窗口"（标题里带 War in the Pacific 且不含 "Autorun"）
    for hwnd, title in cands:
        if "war in the pacific" in title.lower():
            return hwnd, title
    if cands:
        return cands[0]
    return None, None


def post_key(hwnd, key):
    """投递单个字符键（按下+抬起）。"""
    vk = ord(key.upper())
    scan = user32.MapVirtualKeyW(vk, 0)
    lp = 1 | (scan << 16)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))
    time.sleep(0.05)
    return vk


def main():
    args = [a for a in sys.argv[1:]]
    if not args or args[0] == "--list":
        for hwnd, title in list_windows():
            print("hwnd=%s title=%s" % (hwnd, title))
        return 0

    hwnd, title = find_game_window()
    if not hwnd:
        print("ok=False error=no-game-window")
        return 1
    print("window=%s" % title)
    print("hwnd=%s" % hwnd)

    keys = []
    for a in args:
        if a.startswith("--"):
            continue
        keys.extend([c for c in a if c.strip()])

    for k in keys:
        vk = post_key(hwnd, k)
        print("sent=%s vk=%d" % (k, vk))
    print("ok=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
