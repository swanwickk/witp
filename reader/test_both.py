"""test_both.py — 同时修改两份 TF 结构副本，验证哪份才是命令源

实测：运行时 TF7 结构存在两份完全相同的拷贝
  copyA 0x0cf76040
  copyB 0x06da6050
只改 copyA 时界面无变化 ⇒ 界面/引擎读的是另一份，或两者都是镜像。

本脚本同时改两份，再看界面。
"""
import os
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

COPIES = [0x0cf76040, 0x06da6050]
OFF_MISSION = 393
OFF_SPEED = 398


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def main():
    pid = pid_of()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"
    off = OFF_MISSION if len(sys.argv) < 3 or sys.argv[2] == "mission" else OFF_SPEED
    fd = memrw.open_mem(pid)

    if cmd == "get":
        for b in COPIES:
            d = memrw.read_mem(pid, b + off, 1, fd)
            print(f"  {b:#x} off{off} = {d[0] if d else '?'}")
    elif cmd == "set":
        val = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        for b in COPIES:
            old = memrw.read_mem(pid, b + off, 1, fd)
            ok = memrw.write_mem(pid, b + off, bytes([val]))
            new = memrw.read_mem(pid, b + off, 1, fd)
            print(f"  {b:#x}: {old[0]} -> {new[0]} (ok={ok})")
    os.close(fd)


if __name__ == "__main__":
    main()
