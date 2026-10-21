"""iat_lookup.py — 解析 PE 导入表，查某个 IAT 地址对应哪个导入函数

用途：反汇编里看到 `call *0x808064` 时，需要知道它实际调用的是哪个 API，
      才能判断那段代码在做什么（读文件/分配内存/…）。

用法: python3 iat_lookup.py 0x808064 [0x808068 ...]
"""
import struct
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")


def main():
    data = open(GAME, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0"
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    # PE32: 导入表目录在 opt+96
    dd = opt + (96 if magic == 0x10B else 112)
    imp_rva, imp_sz = struct.unpack_from("<II", data, dd + 8)  # index 1

    secs = []
    so = opt + opt_size
    for i in range(nsec):
        o = so + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        secs.append((name, vaddr, vsize, raddr, rsize))

    def rva2off(rva):
        for name, vaddr, vsize, raddr, rsize in secs:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        return None

    print(f"导入表 RVA={imp_rva:#x}\n")
    # 调用方通常给 VA（0x808064），导入表用 RVA（0x408064）
    targets = []
    for a in (sys.argv[1:] or ["0x808064"]):
        v = int(a, 16)
        targets.append(v - 0x400000 if v >= 0x400000 else v)

    off = rva2off(imp_rva)
    idx = 0
    while True:
        o = off + idx * 20
        ilt, ts, fc, name_rva, iat = struct.unpack_from("<IIIII", data, o)
        if name_rva == 0:
            break
        dll_off = rva2off(name_rva)
        dll = data[dll_off:data.index(b"\0", dll_off)].decode("ascii", "replace")
        print(f"[{idx}] {dll}  IAT_RVA={iat:#x}")

        # 遍历该 DLL 的 thunk
        thunk_rva = ilt if ilt else iat
        toff = rva2off(thunk_rva)
        j = 0
        while True:
            val = struct.unpack_from("<I", data, toff + j * 4)[0]
            if val == 0:
                break
            slot = iat + j * 4
            if val & 0x80000000:
                fname = f"Ordinal#{val & 0xFFFF}"
            else:
                hoff = rva2off(val)
                hint = struct.unpack_from("<H", data, hoff)[0]
                s = data[hoff + 2:data.index(b"\0", hoff + 2)].decode("ascii", "replace")
                fname = s
            mark = "  ★" if slot in targets else ""
            if slot in targets or idx == 0 and j < 3:
                print(f"      {slot:#x} -> {fname}{mark}")
            j += 1
        idx += 1


if __name__ == "__main__":
    main()
