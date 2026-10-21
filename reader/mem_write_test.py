"""mem_write_test.py — 决定性实验：改内存 → 看界面是否响应

这是整条路线的验收判据。若成功，说明「不用键鼠操作游戏」成立。

实验设计（单变量、可回滚）：
  改 speed（off 398）：3 → 1
  界面上的 Speed 档位应该变化，或引擎结算时航速不同。

  更安全的实验：改 mission（off 393）：15(AMPHIB) → 1(AIRCOMBAT)
  界面 Mission 行应立刻变成 Air Combat —— 这是**立即可见**的判据。

先备份原值，改完截图核对，再恢复。
"""
import struct
import sys
import time

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

BASE = 0x0cf76040
TF7 = BASE + 7 * 0  # 注意：实测命中点在 0xcf7606c = start+44，
                     # 说明 0xcf76040 就是该 TF 的结构起点（不是数组基址+7*464）

OFF_MISSION = 393
OFF_SPEED = 398
OFF_LOADSTATE = 394


def pid_of():
    import os
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
    print(f"PID={pid}  结构起点={BASE:#x}")

    cur = memrw.read_mem(pid, BASE, 464, fd)
    print(f"当前 mission={cur[OFF_MISSION]} speed={cur[OFF_SPEED]} "
          f"loadState={cur[OFF_LOADSTATE]}")

    import os
    os.close(fd)


if __name__ == "__main__":
    main()
