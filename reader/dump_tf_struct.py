"""dump_tf_struct.py — 完整 dump 运行时 TF 结构并对照界面已知值

已知对照（界面 OCR 得到）：
  TF7 = MO Landing Force, Amphibious, 16 ships
  Current Load: 46544 of 58251
  Fuel: 237/21(10)
  Guns: 153(100)  AAA: 672(100)  ASW: 7(100)
  CDR: RADM Inano S.  Leadership 73  Inspiration 66
  Float Planes: 1
  存档: flagship=91 home=992 mission=15 speed=3

从 0xcf7606c 往回推到结构起点，然后逐 2/4 字节列出所有非零字段，
标注哪些能与上面已知值对上。
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

HIT = 0x0cf7606c        # flagship=91 所在（实测）

# 界面已知值，用于反查偏移
KNOWN = {
    1700: "endurance?", 840: "enduranceReq?", 46544: "currentLoad",
    58251: "maxLoad", 91: "flagship", 992: "home", 15: "mission",
    153: "guns", 672: "aaa", 7: "asw", 73: "leadership", 66: "inspiration",
    237: "fuel", 21: "fuelReq", 1: "floatPlanes", 3: "speed",
}


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

    # flagship 在结构内偏移 44（与存档一致，已由 combo 命中证明）
    start = HIT - 44
    print(f"结构起点推定: {start:#x}\n")

    d = memrw.read_mem(pid, start, 464, fd)
    if not d or len(d) < 464:
        print("读取失败")
        return

    print("=== 非零字节分布（按 4 字节对齐列出 u32 / u16）===")
    for off in range(0, 464, 2):
        v16 = struct.unpack_from("<H", d, off)[0]
        v32 = struct.unpack_from("<I", d, off)[0] if off + 4 <= 464 else None
        if v16 == 0:
            continue
        tag = ""
        if v32 in KNOWN:
            tag = f"  ★u32={KNOWN[v32]}"
        elif v16 in KNOWN:
            tag = f"  ★u16={KNOWN[v16]}"
        if tag:
            print(f"  off={off:>4} u16={v16:<7} u32={v32}{tag}")

    print("\n=== 全部非零偏移（紧凑）===")
    nz = [(o, d[o]) for o in range(464) if d[o]]
    print(f"  共 {len(nz)} 个非零字节")
    print("  " + " ".join(f"{o}:{v}" for o, v in nz[:60]))

    print("\n=== 结构尾部（可能有名称）===")
    tail = d[380:464]
    txt = "".join(chr(c) if 32 <= c < 127 else "." for c in tail)
    print(f"  {txt!r}")

    import os
    os.close(fd)


if __name__ == "__main__":
    main()
