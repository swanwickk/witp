"""probe_tf_base.py — 严格验证候选 TF 基址

判据（三重，必须同时满足）：
  1. 槽内偏移 424 附近应是 ASCII 编队名（如 "Shokaku"、"Kyou..."）
  2. 槽内应出现与存档一致的小整数（mission 1-25、speed 0-3）
  3. 空槽（0/13/19/26/27）应几乎全零

不满足任何一条 → 这个基址是假的。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe

SZ = 0x1d0
OCC = [1, 2, 3, 5, 7, 8, 14, 15]
EMPTY = [0, 13, 19, 26, 27]


def pid_of():
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{cand}/environ", "rb").read():
                return int(cand)
        except OSError:
            pass
    return None


def ascii_runs(data, minlen=4):
    out = []
    cur = []
    for i, b in enumerate(data):
        if 32 <= b < 127:
            cur.append((i, chr(b)))
        else:
            if len(cur) >= minlen:
                out.append((cur[0][0], "".join(c for _, c in cur)))
            cur = []
    if len(cur) >= minlen:
        out.append((cur[0][0], "".join(c for _, c in cur)))
    return out


def main():
    base = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x1976700
    pid = pid_of()
    if not pid:
        print("找不到测试实例")
        return
    print(f"PID={pid}  候选基址={base:#x}  步长={SZ}\n")

    for s in OCC[:6]:
        d = mem_probe.gdb_read(pid, base + s * SZ, SZ)
        if not d:
            print(f"slot{s}: 读失败")
            continue
        nz = sum(1 for b in d if b)
        runs = ascii_runs(d)
        runs.sort(key=lambda r: -len(r[1]))
        top = runs[:3]
        print(f"=== slot {s}  非零={nz}/{SZ} ===")
        for off, txt in top:
            print(f"    off {off:>3}: {txt!r}")
        # 前 32 字节
        print(f"    head: {d[:32].hex()}")

    print("\n=== 空槽对照（应几乎全零）===")
    for s in EMPTY:
        d = mem_probe.gdb_read(pid, base + s * SZ, SZ)
        if d:
            print(f"  slot{s}: 非零={sum(1 for b in d if b)}")


if __name__ == "__main__":
    main()
