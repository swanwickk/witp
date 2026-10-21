#!/usr/bin/env python3
"""VNC 组合键（Ctrl+A 等）。

witp_vnckey.py 只能发单键，无法发组合。手册 §4.2.6 的战略图开关正是
组合键：「pressing **Ctrl** and **A**」。

用法:
    witp_vnccombo.py <组合描述>
    组合描述用 '+' 连接，如 "ctrl+a"、"ctrl+shift+p"
特殊键名同 witp_vnckey.py（escape/up/left/f1...）。
"""
import socket
import struct
import sys
import time

HOST, PORT = "127.0.0.1", 5902

KEYSYMS = {
    "escape": 0xFF1B, "esc": 0xFF1B,
    "return": 0xFF0D, "enter": 0xFF0D,
    "tab": 0xFF09, "space": 0x0020,
    "backspace": 0xFF08, "delete": 0xFFFF,
    "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
    "home": 0xFF50, "end": 0xFF57,
    "pageup": 0xFF55, "pagedown": 0xFF56,
    "shift": 0xFFE1, "control": 0xFFE3, "ctrl": 0xFFE3, "alt": 0xFFE9,
}
for i in range(1, 13):
    KEYSYMS[f"f{i}"] = 0xFFBE + (i - 1)


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
        raise RuntimeError(f"不支持 None 认证: {list(types)}")
    sock.sendall(bytes([1]))
    if ver >= b"RFB 003.008":
        res = recv_exact(sock, 4)
        if struct.unpack(">I", res)[0] != 0:
            raise RuntimeError("SecurityResult 非 0")
    sock.sendall(bytes([1]))
    head = recv_exact(sock, 24)
    w, h = struct.unpack(">HH", head[:4])
    nlen = struct.unpack(">I", head[20:24])[0]
    if nlen:
        recv_exact(sock, nlen)
    return w, h


def key_event(sock, keysym, down):
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
    combo = sys.argv[1]
    parts = combo.split("+")
    syms = [resolve(p) for p in parts]

    sock = socket.create_connection((HOST, PORT), timeout=10)
    try:
        handshake(sock)
        # 全部按下 → 短暂停顿 → 全部释放
        for s in syms:
            key_event(sock, s, True)
            time.sleep(0.06)
        time.sleep(0.10)
        for s in reversed(syms):
            key_event(sock, s, False)
            time.sleep(0.06)
        time.sleep(0.15)
        print(f"OK combo: {combo}  → keysyms {syms}")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
