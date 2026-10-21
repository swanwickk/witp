"""winmsg4.py — 用 GetKeyboardState 一致性验证 + 枚举窗口过程

关键实验：
  1. 记录窗口收到的消息数（用 SetWindowLongPtr 替换 WndProc 会破坏游戏，不采用）
  2. 改用 AttachThreadInput + SetFocus 确保输入路由
  3. 直接尝试 WM_COMMAND 各 ID
  4. 打印 GetGUIThreadInfo 焦点信息
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def find_game():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(h, b, n + 2)
            if "War in the Pacific" in b.value:
                out.append((h, b.value))
        return True

    user32.EnumWindows(_cb, 0)
    return out[0] if out else (None, None)


def main():
    hwnd, title = find_game()
    if not hwnd:
        print("ok=False error=no-window")
        return 1
    print("hwnd=%s title=%s" % (hwnd, title))

    tid = user32.GetWindowThreadProcessId(hwnd, None)
    print("window_thread_id=%s" % tid)
    print("current_thread_id=%s" % kernel32.GetCurrentThreadId())

    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = user32.GetGUIThreadInfo(tid, ctypes.byref(gti))
    print("GetGUIThreadInfo ok=%s" % ok)
    if ok:
        print("  flags=%s active=%s focus=%s capture=%s" % (
            gti.flags, gti.hwndActive, gti.hwndFocus, gti.hwndCapture))

    # 尝试 AttachThreadInput 后设焦点
    cur = kernel32.GetCurrentThreadId()
    att = user32.AttachThreadInput(cur, tid, True)
    print("AttachThreadInput=%s" % att)
    user32.SetFocus(hwnd)
    user32.SetActiveWindow(hwnd)
    time.sleep(0.3)
    ok2 = user32.GetGUIThreadInfo(tid, ctypes.byref(gti))
    if ok2:
        print("  after: active=%s focus=%s" % (gti.hwndActive, gti.hwndFocus))

    # 投递
    vk, scan = ord("T"), user32.MapVirtualKeyW(ord("T"), 0)
    down = 1 | (scan << 16)
    up = down | (1 << 30) | (1 << 31)
    print("PostMessage down=%s" % user32.PostMessageW(hwnd, 0x0100, vk, down))
    time.sleep(0.05)
    print("PostMessage up=%s" % user32.PostMessageW(hwnd, 0x0101, vk, up))

    user32.AttachThreadInput(cur, tid, False)
    print("ok=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
