#!/usr/bin/env python3
"""通过 VNC(RFB) 协议向 Xvnc 发送**键盘**事件。

背景：WitP-AE 是 DirectDraw/DirectInput 老游戏，Wine 不认 xdotool 的 XTEST 注入
（实测 E / I 等快捷键完全无反应）；VNC 事件由 Xvnc 以“真实设备”路径注入，
游戏能正常响应。本脚本与 witp_vncclick97.py 同一通道，只发 KeyEvent。

用法:
    witp_vnckey97.py <keysym> [keysym2 ...]
    witp_vnckey97.py --shift e        # 带 Shift
    witp_vnckey97.py --text hello      # 逐字符发送

keysym 采用 X11 名称（e / i / Return / Escape / F5 / space / 1 ...）。
"""
import os
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = int(os.environ.get("WITP_VNC_PORT", "5901"))

# 常用 keysym 表（X11 键码）
KEYSYMS = {
    "Return": 0xFF0D, "Enter": 0xFF0D, "Escape": 0xFF1B, "Tab": 0xFF09,
    "BackSpace": 0xFF08, "space": 0x0020, "Delete": 0xFFFF,
    "Up": 0xFF52, "Down": 0xFF54, "Left": 0xFF51, "Right": 0xFF53,
    "Home": 0xFF50, "End": 0xFF57, "Page_Up": 0xFF55, "Page_Down": 0xFF56,
    "F1": 0xFFBE, "F2": 0xFFBF, "F3": 0xFFC0, "F4": 0xFFC1,
    "F5": 0xFFC2, "F6": 0xFFC3, "F7": 0xFFC4, "F8": 0xFFC5,
    "F9": 0xFFC6, "F10": 0xFFC7, "F11": 0xFFC8, "F12": 0xFFC9,
}


def keysym_of(name):
    if name in KEYSYMS:
        return KEYSYMS[name]
    if len(name) == 1:
        return ord(name)
    raise ValueError(f"未知 keysym: {name}")


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
    if n_types == 0:
        raise RuntimeError("服务器拒绝：无可用安全类型")
    types = recv_exact(sock, n_types)
    if 1 not in types:
        raise RuntimeError(f"服务器不支持 None 认证: {list(types)}")
    sock.sendall(bytes([1]))
    if ver >= b"RFB 003.008":
        res = recv_exact(sock, 4)
        if struct.unpack(">I", res)[0] != 0:
            raise RuntimeError("SecurityResult 非 0")
    sock.sendall(bytes([1]))
    head = recv_exact(sock, 24)
    w, h = struct.unpack(">HH", head[:4])
    name_len = struct.unpack(">I", head[20:24])[0]
    if name_len:
        recv_exact(sock, name_len)
    return w, h


def key_event(sock, keysym, down=True):
    """KeyEvent: type=4, down-flag(1B), padding(2B), keysym(4B)"""
    sock.sendall(struct.pack(">BBHI", 4, 1 if down else 0, 0, keysym))


def send_key(sock, keysym, hold=0.05, gap=0.12):
    key_event(sock, keysym, True)
    time.sleep(hold)
    key_event(sock, keysym, False)
    time.sleep(gap)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    mode = "keys"
    if args[0] in ("--shift", "--text"):
        mode = args[0][2:]
        args = args[1:]
        if not args:
            print("缺少参数")
            return 1

    sock = socket.create_connection((HOST, PORT), timeout=10)
    try:
        w, h = handshake(sock)
        sent = []
        if mode == "shift":
            # Shift 键 keysym = 0xFFE1
            for name in args:
                key_event(sock, 0xFFE1, True)
                time.sleep(0.04)
                send_key(sock, keysym_of(name))
                key_event(sock, 0xFFE1, False)
                time.sleep(0.1)
                sent.append("Shift+" + name)
        elif mode == "text":
            for ch in " ".join(args):
                send_key(sock, keysym_of(ch), gap=0.06)
                sent.append(ch)
        else:
            for name in args:
                send_key(sock, keysym_of(name))
                sent.append(name)
        print(f"OK keys sent={sent} framebuffer={w}x{h}")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
