#!/usr/bin/env python3
"""通过 VNC(RFB) 协议向 Xvnc 发送键盘事件。

背景：与 witp_vncclick.py 同理——WitP-AE 在 Wine 下不认 xdotool 的 XTEST 注入事件；
VNC 客户端注入的事件被当真实设备处理（用户在 noVNC 网页上操作一直正常）。

用法:
    witp_vnckey.py <键名> [<键名> ...]
键名: 单字符(a-z,0-9) / escape / return / tab / space / f1..f12 / up / down / left / right / 等
"""
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = 5902

# X11 keysym 表（常用键）
KEYSYMS = {
    "escape": 0xFF1B, "esc": 0xFF1B,
    "return": 0xFF0D, "enter": 0xFF0D,
    "tab": 0xFF09, "space": 0x0020,
    "backspace": 0xFF08, "delete": 0xFFFF,
    "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
    "home": 0xFF50, "end": 0xFF57,
    "pageup": 0xFF55, "pagedown": 0xFF56,
    "shift": 0xFFE1, "control": 0xFFE3, "alt": 0xFFE9,
}
for i in range(1, 13):
    KEYSYMS[f"f{i}"] = 0xFFBE + (i - 1)   # F1=0xFFBE … F12=0xFFC9


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
    n_types = recv_exact(sock, 1)[0]
    types = recv_exact(sock, n_types)
    if 1 not in types:
        raise RuntimeError(f"服务器不支持 None 认证: {list(types)}")
    sock.sendall(bytes([1]))
    if ver >= b"RFB 003.008":
        res = recv_exact(sock, 4)
        if struct.unpack(">I", res)[0] != 0:
            raise RuntimeError("SecurityResult 非 0")
    sock.sendall(bytes([1]))            # shared
    head = recv_exact(sock, 24)
    w, h = struct.unpack(">HH", head[:4])
    nlen = struct.unpack(">I", head[20:24])[0]
    if nlen:
        recv_exact(sock, nlen)
    return w, h


def key_event(sock, keysym, down):
    """KeyEvent: type=4, down-flag(1B), padding(2B), keysym(4B)"""
    sock.sendall(struct.pack(">BBHI", 4, 1 if down else 0, 0, keysym))


def resolve(name):
    n = name.lower()
    if n in KEYSYMS:
        return KEYSYMS[n]
    if len(name) == 1:
        return ord(name)
    raise ValueError(f"未知键名: {name}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    names = sys.argv[1:]
    sock = socket.create_connection((HOST, PORT), timeout=10)
    try:
        handshake(sock)
        for name in names:
            ks = resolve(name)
            key_event(sock, ks, True)
            time.sleep(0.08)
            key_event(sock, ks, False)
            time.sleep(0.12)
        print("OK keys: " + " ".join(names))
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
