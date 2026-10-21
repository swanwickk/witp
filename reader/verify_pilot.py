"""verify_pilot.py — 验证 Pilot 数组基址

判据：对存档所有飞行员槽，检查内存同槽的 off0 和 off4 是否吻合。
      152 字节步长，100000 槽。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

PL = 152


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def main():
    S = ("/root/.wine-witp-mcp/prefix/drive_c/1108r9/"
         "War in the Pacific Admiral's Edition/SAVE/wpae000.pws")
    d = pwsfile.record_by_len(S, 15200000)
    pid = pid_of()
    fd = memrw.open_mem(pid)

    # 收集有内容的槽
    slots = []
    for s in range(1, 100000):
        b = s * PL
        nz = sum(1 for x in d[b:b + PL] if x)
        if nz > 5:
            slots.append(s)
        if len(slots) >= 200:
            break
    print(f"存档有内容的飞行员槽: {len(slots)} 个（取前 200）")

    for base in (0x7f7faa8, 0xda29500):
        print(f"\n=== 基址 {base:#x} ===")
        ok = 0
        bad = []
        for s in slots:
            m = memrw.read_mem(pid, base + s * PL, PL, fd)
            if not m:
                bad.append(s)
                continue
            same = sum(1 for i in range(PL) if m[i] == d[s * PL + i])
            if same >= PL * 0.8:
                ok += 1
            else:
                bad.append(s)
        print(f"  吻合 {ok}/{len(slots)}")
        if bad:
            print(f"  不吻合 {len(bad)} 个，示例 {bad[:5]}")

    os.close(fd)


if __name__ == "__main__":
    main()
