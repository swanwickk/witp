"""locate_pilot.py — 定位 Pilot 运行时数组

存档 PILOT 记录：15200000 字节 = 152B × 100000 槽
槽内 off0 是 u16 值（如 0x029e=670），off4 是递增 ID。

定位法：
  用 off4 的递增 ID（稀有）作锚，检查 152 步长上是否连续。
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
    print(f"PID={pid}")

    # 找几个有特征的槽：off4 是大整数
    cands = []
    for s in range(1, 2000):
        b = s * PL
        v4 = struct.unpack_from("<I", d, b + 4)[0]
        v0 = struct.unpack_from("<H", d, b)[0]
        if 1000 < v4 < 200000 and v0 > 0:
            cands.append((s, v0, v4))
        if len(cands) >= 6:
            break
    print(f"锚槽: {cands}")

    # 搜 v4 在内存的位置
    for slot, v0, v4 in cands[:3]:
        pat = struct.pack("<I", v4)
        found = []
        for st, en, perm, name in memrw.regions(pid):
            if "rw" not in perm or (en - st) < (1 << 20):
                continue
            fd = memrw.open_mem(pid)
            b = memrw.read_mem(pid, st, en - st, fd)
            os.close(fd)
            if not b:
                continue
            pos = 0
            while True:
                i = b.find(pat, pos)
                if i < 0:
                    break
                found.append(st + i)
                pos = i + 1
                if len(found) > 15:
                    break
        print(f"  slot{slot} v4={v4}: {len(found)} 处 {[hex(a) for a in found[:5]]}")
        for a in found[:5]:
            base = a - 4 - slot * PL
            print(f"      推基址={base:#x}")


if __name__ == "__main__":
    main()
