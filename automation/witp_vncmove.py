#!/usr/bin/env python3
"""VNC 鼠标移动（不点击）。用法: witp_vncmove.py <x> <y>  （游戏窗口内坐标）"""
import socket, struct, sys, time
HOST, PORT = "127.0.0.1", 5902

def recv_exact(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: raise ConnectionError("closed")
        b += c
    return b

def handshake(s):
    s.sendall(b"RFB 003.008\n")
    recv_exact(s, 12); n = recv_exact(s, 1)[0]; recv_exact(s, n)
    s.sendall(bytes([1])); recv_exact(s, 4)
    s.sendall(bytes([1]))
    h = recv_exact(s, 24)
    nl = struct.unpack(">I", h[20:24])[0]
    if nl: recv_exact(s, nl)

def main():
    x, y = int(sys.argv[1]), int(sys.argv[2])
    # ★2026-10-04 修★ 原默认值 (188,150) 是 v13~v18 窗口漂移时代的写死位置。
    #   调用方漏传偏移时，鼠标会落到一个完全错误的屏幕坐标，
    #   表现为「点击正常但边缘滚动永远不触发」——极难归因。
    #   现在缺省为 0（无偏移），且偏移必须由调用方从 get_window_offset() 显式传入。
    ox = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    oy = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    s = socket.create_connection((HOST, PORT), timeout=10)
    try:
        handshake(s)
        s.sendall(struct.pack(">BBHH", 5, 0, ox + x, oy + y))
        time.sleep(0.15)
        print(f"OK move ({ox+x},{oy+y})")
    finally:
        s.close()

main()
