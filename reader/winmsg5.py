"""winmsg5.py — 枚举所有窗口（含不可见、含所有进程），找出真正的输入接收者

用途：WitP 主菜单是 DialogBoxParamA 模态对话框，可能有独立 HWND；
      直接向主窗口 PostMessage 不会路由到对话框。
"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def enum_all():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(h, b, n + 2)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        out.append({
            "hwnd": h, "title": b.value, "cls": cls.value,
            "vis": bool(user32.IsWindowVisible(h)),
            "enabled": bool(user32.IsWindowEnabled(h)),
            "pid": pid.value,
        })
        return True

    user32.EnumWindows(_cb, 0)
    return out


def main():
    wins = enum_all()
    # 找游戏进程 pid
    game = [w for w in wins if "War in the Pacific" in w["title"]]
    if not game:
        print("ok=False error=no-game")
        return 1
    pid = game[0]["pid"]
    print("game_pid=%d  game_hwnd=%s" % (pid, game[0]["hwnd"]))
    print("foreground=%s" % user32.GetForegroundWindow())

    print("\n== pid windows ==")
    for w in wins:
        if w["pid"] == pid:
            print("  hwnd=%-8s vis=%-5s en=%-5s cls=%-20s title=%s" % (
                w["hwnd"], w["vis"], w["enabled"], w["cls"], w["title"]))

    print("\n== visible windows ==")
    for w in wins:
        if w["vis"]:
            print("  pid=%-6s hwnd=%-8s cls=%-20s title=%s" % (
                w["pid"], w["hwnd"], w["cls"], w["title"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
