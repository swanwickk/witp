"""mem_verify.py — 用反汇编得到的基址直接读运行时 TF 结构

反汇编证据（0x640250 处，imul $0x1d0 + 绝对地址）：
    mov 0x1a143ac(%eax),%cx   ; TF 数组基址，读到的是 home port (u16)
    mov 0x1a144cb(%eax),%cl   ; offset 0x11F=287
    mov 0x1a144f1(%eax),%dl   ; offset 0x145=325
    imul $0x1d0               ; 步长 464

之前记录的 0x1a14ae0 是错的（偏 0x734）。

用法:
  python3 mem_verify.py            # 读 slot 0..5 的多个候选字段
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe

BASE = 0x1a143ac
SZ = 0x1d0

# 反汇编直接给出的偏移
KNOWN = {0x00: ("home_port?", "u16"), 0x11F: ("f287", "u8"), 0x145: ("f325", "u8")}

# 存档里已验证的偏移（若运行时与存档同构，这些应该对得上）
SAVE_KNOWN = {44: "flagship", 54: "home", 349: "mission", 354: "speed",
              369: "routing", 448: "tolerance", 355: "maxReact", 350: "loadState"}


def pid():
    return mem_probe.game_pid() if hasattr(mem_probe, "game_pid") else None


def read_tf_slot(p, slot, n=0x1d0):
    return mem_probe.gdb_read(p, BASE + slot * SZ, n)


def main():
    p = None
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        env = f"/proc/{cand}/environ"
        try:
            if b"wine-witp-mcp" in open(env, "rb").read():
                p = int(cand)
                break
        except OSError:
            pass
    if not p:
        print("找不到测试实例进程")
        return
    print(f"PID={p}  基址={BASE:#x}  步长={SZ:#x}")

    for slot in range(6):
        data = read_tf_slot(p, slot)
        if not data or len(data) < 0x1d0:
            print(f"slot{slot}: 读取失败")
            continue
        print(f"\n=== slot {slot} ===")
        for off, (name, kind) in KNOWN.items():
            if kind == "u16":
                v = struct.unpack_from("<H", data, off)[0]
            else:
                v = data[off]
            print(f"  off {off:#05x} {name:<12} = {v}")
        print("  存档偏移对照:")
        for off, name in SAVE_KNOWN.items():
            if kind_u8 := (off < 0x1d0):
                v8 = data[off]
                v16 = struct.unpack_from("<H", data, off)[0]
                print(f"    off {off:<4} {name:<10} u8={v8:<4} u16={v16}")
        # 名字区
        name_bytes = data[0x1a8:0x1d0]
        s = "".join(chr(c) if 32 <= c < 127 else "." for c in name_bytes).strip(".")
        print(f"  off 0x1a8.. 文本: {s[:40]!r}")


if __name__ == "__main__":
    main()
