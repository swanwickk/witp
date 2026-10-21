#!/usr/bin/env python3
"""通过 VNC(RFB) 协议向 Xvnc 发送鼠标事件。

背景：WitP-AE 是 DirectDraw/DirectInput 老游戏，Wine 不认 xdotool 的 XTEST 注入事件
（部分界面点击完全丢失）；而 VNC 客户端（noVNC 网页）发出的事件由 Xvnc 以“真实设备”
路径注入，游戏能正常响应。本脚本复刻该路径。

用法:
    witp_vncclick.py <x> <y> [click|dblclick|move|rclick] [steps]
坐标 = 屏幕坐标（游戏坐标 + 窗口偏移）。
"""
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = 5902


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("连接被关闭")
        buf += chunk
    return buf


def handshake(sock):
    """RFB 3.x 握手（Xvnc 以 -SecurityTypes None 启动，无需认证）"""
    sock.sendall(b"RFB 003.008\n")
    ver = recv_exact(sock, 12)
    if not ver.startswith(b"RFB "):
        raise RuntimeError(f"非 RFB 响应: {ver!r}")
    n_types = recv_exact(sock, 1)[0]
    if n_types == 0:
        raise RuntimeError("服务器拒绝：无可用安全类型")
    types = recv_exact(sock, n_types)
    if 1 not in types:
        raise RuntimeError(f"服务器不支持 None 认证: {list(types)}")
    sock.sendall(bytes([1]))          # 选择 None
    # 3.8 起即使 None 也会返回 SecurityResult
    if ver >= b"RFB 003.008":
        if len(types) > 1 or True:
            res = recv_exact(sock, 4)
            if struct.unpack(">I", res)[0] != 0:
                raise RuntimeError("SecurityResult 非 0")
    sock.sendall(bytes([1]))          # ClientInit: shared=1
    # ServerInit: 2+2+16+4+name
    head = recv_exact(sock, 24)
    w, h = struct.unpack(">HH", head[:4])
    name_len = struct.unpack(">I", head[20:24])[0]
    if name_len:
        recv_exact(sock, name_len)
    return w, h


def pointer(sock, x, y, mask=0):
    """PointerEvent: type=5, button-mask(1B), x(2B), y(2B)"""
    sock.sendall(struct.pack(">BBHH", 5, mask, int(x), int(y)))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    tx, ty = int(sys.argv[1]), int(sys.argv[2])
    action = sys.argv[3] if len(sys.argv) > 3 else "click"
    steps = int(sys.argv[4]) if len(sys.argv) > 4 else 8

    sock = socket.create_connection((HOST, PORT), timeout=10)
    try:
        w, h = handshake(sock)
        tx = max(0, min(tx, w - 1))
        ty = max(0, min(ty, h - 1))
        # 从当前位置（不可知，用屏幕中心附近起步）逐步移动到目标，模拟真实鼠标轨迹
        if action != "move":
            # 先做一次较大幅度的“抖动”，确保游戏内部光标状态刷新
            pointer(sock, max(0, tx - 30), max(0, ty - 20), 0)
            time.sleep(0.05)
            for i in range(1, steps + 1):
                mx = max(0, tx - 30) + (tx - max(0, tx - 30)) * i // steps
                my = max(0, ty - 20) + (ty - max(0, ty - 20)) * i // steps
                pointer(sock, mx, my, 0)
                time.sleep(0.02)
        pointer(sock, tx, ty, 0)
        time.sleep(0.12)

        if action == "move":
            pass
        elif action == "click":
            pointer(sock, tx, ty, 1)      # 左键按下
            time.sleep(0.08)
            pointer(sock, tx, ty, 0)      # 释放
        elif action == "dblclick":
            for _ in range(2):
                pointer(sock, tx, ty, 1)
                time.sleep(0.05)
                pointer(sock, tx, ty, 0)
                time.sleep(0.05)
        elif action == "rclick":
            pointer(sock, tx, ty, 4)      # 右键 = bit2(4)
            time.sleep(0.08)
            pointer(sock, tx, ty, 0)
        else:
            raise ValueError(f"未知动作: {action}")
        time.sleep(0.1)
        print(f"OK {action} @({tx},{ty}) framebuffer={w}x{h}")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
