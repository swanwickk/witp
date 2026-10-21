"""test_write.py — 改内存 mission 字段，验证界面是否响应

实验：TF7 mission 15(Amphibious) → 1(Air Combat)
判据：界面上 "Mission: Amphibious" 应变成 "Mission: Air Combat"
      若不变，说明结构不可写或读错了对象。

用法:
  python3 test_write.py set    <value>
  python3 test_write.py get
  python3 test_write.py restore
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

BASE = 0x0cf76040
OFF_MISSION = 393
BACKUP = "/tmp/tf7_mission.bak"


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
    fd = memrw.open_mem(pid)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"

    if cmd == "get":
        d = memrw.read_mem(pid, BASE + OFF_MISSION, 1, fd)
        print(f"mission = {d[0] if d else '?'}")
    elif cmd == "set":
        val = int(sys.argv[2])
        cur = memrw.read_mem(pid, BASE + OFF_MISSION, 1, fd)
        with open(BACKUP, "w") as f:
            f.write(str(cur[0]))
        ok = memrw.write_mem(pid, BASE + OFF_MISSION, bytes([val]))
        after = memrw.read_mem(pid, BASE + OFF_MISSION, 1, fd)
        print(f"原值={cur[0]} 写入={val} 成功={ok} 读回={after[0] if after else '?'}")
    elif cmd == "restore":
        if not os.path.exists(BACKUP):
            print("无备份")
        else:
            val = int(open(BACKUP).read().strip())
            memrw.write_mem(pid, BASE + OFF_MISSION, bytes([val]))
            after = memrw.read_mem(pid, BASE + OFF_MISSION, 1, fd)
            print(f"恢复为 {val}，读回={after[0] if after else '?'}")
    os.close(fd)


if __name__ == "__main__":
    main()
