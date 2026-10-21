#!/usr/bin/env python3
"""VNC 拖拽（按住左键 + 多次 PointerEvent + 释放）。

用途：手册 Ch04 §4.2 明确「To scroll around the map, **drag the mouse
pointer** in any direction and the Tactical Map will shift with it」。
本脚本提供之前完全缺失的 **drag** 原语 —— 既有 witp_vncclick.py 只能
做瞬时点击，无法产生「按住-移动」序列，所以主地图滚动一直做不出来。

用法:
    witp_vncdrag.py <x0> <y0> <x1> <y1> [steps] [hold_ms]
坐标 = 屏幕绝对坐标（= 游戏窗口内坐标 + 窗口偏移）。
"""
import socket
import struct
import sys
import time

HOST, PORT = "127.0.0.1", 5902


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("连接被关闭")
        buf += chunk
    return buf


def handshake(sock):
    sock.sendall(b"RFB 003.008\n")
    ver = recv_exact(sock, 12)
    if not ver.startswith(b"RFB "):
        raise RuntimeError(f"非 RFB 响应: {ver!r}")
    n_types = recv_exact(sock, 1)[0]
    types = recv_exact(sock, n_types)
    if 1 not in types:
        raise RuntimeError(f"不支持 None 认证: {list(types)}")
    sock.sendall(bytes([1]))
    recv_exact(sock, 4)
    sock.sendall(bytes([1]))
    head = recv_exact(sock, 24)
    w, h = struct.unpack(">HH", head[:4])
    nl = struct.unpack(">I", head[20:24])[0]
    if nl:
        recv_exact(sock, nl)
    return w, h


def pointer(sock, x, y, mask=0):
    sock.sendall(struct.pack(">BBHH", 5, mask, int(x), int(y)))


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 1
    x0, y0, x1, y1 = (int(sys.argv[i]) for i in range(1, 5))
    steps = int(sys.argv[5]) if len(sys.argv) > 5 else 16
    hold_ms = int(sys.argv[6]) if len(sys.argv) > 6 else 30

    sock = socket.create_connection((HOST, PORT), timeout=10)
    try:
        w, h = handshake(sock)
        x0 = max(0, min(x0, w - 1)); y0 = max(0, min(y0, h - 1))
        x1 = max(0, min(x1, w - 1)); y1 = max(0, min(y1, h - 1))

        # 1) 先把指针挪到起点（不按键），让游戏刷新 hover 状态
        pointer(sock, x0, y0, 0)
        time.sleep(0.15)

        # 2) 左键按下
        pointer(sock, x0, y0, 1)
        time.sleep(0.12)

        # 3) 按住状态下逐步移动 —— 这才是游戏识别为「拖拽地图」的关键
        for i in range(1, steps + 1):
            mx = x0 + (x1 - x0) * i // steps
            my = y0 + (y1 - y0) * i // steps
            pointer(sock, mx, my, 1)
            time.sleep(hold_ms / 1000.0)

        # 4) 终点再停一下（游戏常在停下时才结算地图位移）
        time.sleep(0.15)

        # 5) 释放
        pointer(sock, x1, y1, 0)
        time.sleep(0.15)
        print(f"OK drag ({x0},{y0})→({x1},{y1}) steps={steps} "
              f"hold={hold_ms}ms framebuffer={w}x{h}")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
