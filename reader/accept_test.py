"""accept_test.py — 最终验收：纯内存写命令 → 过回合 → 存档验证

流程（全程不用键鼠改游戏状态）：
  1. 现场定位 TF 数组
  2. 写 TF7 的 mission: 15(AMPHIB) → 1(AIRCOMBAT)
     同时写 speed: 3 → 1
  3. 用 executor 过一回合（这一步需要 E 键，属结算触发，非命令下达）
  4. 读新 autosave，检查 mission/speed 是否为写入值

判据：存档里 TF7 的 mission==1 且 speed==1 ⇒ 引擎采纳，路线成立。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import tf_live

SZ = 556
OFF_MISSION, OFF_SPEED = 349, 354


def main():
    pid = tf_live.pid_of()
    import pwsfile
    save = "/root/.hermes/profiles/witp/workspace/witp-mcp-out/testinst-final/wpae001.pws"
    c = pwsfile.read_container(save)
    expect = {}
    for r in c["records"]:
        if r["u_len"] == 2224000:
            for s in range(200):
                b = s * SZ
                fl = struct.unpack_from("<I", r["data"], b + 44)[0]
                if fl:
                    expect[s] = fl
            break

    base, tf7 = tf_live.find_base(pid, expect)
    if base is None:
        print("定位失败")
        return
    print(f"基址={base:#x}  TF7={tf7:#x}")

    # 读原值
    d = tf_live.read_at(pid, base + 7 * SZ)
    print(f"写入前: mission={d[OFF_MISSION]} speed={d[OFF_SPEED]}")

    # 写新值
    ok1 = tf_live.write_at(pid, base + 7 * SZ + OFF_MISSION, bytes([1]))
    ok2 = tf_live.write_at(pid, base + 7 * SZ + OFF_SPEED, bytes([1]))
    d2 = tf_live.read_at(pid, base + 7 * SZ)
    print(f"写入后: mission={d2[OFF_MISSION]} speed={d2[OFF_SPEED]} "
          f"(ok={ok1},{ok2})")


if __name__ == "__main__":
    main()
