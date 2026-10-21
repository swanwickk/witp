"""find_save_io.py — 定位读档核心 IO 调用点

思路：
  读档必然调用 CreateFileA/ReadFile（KERNEL32），且文件名以 .pws 结尾。
  存档的写档函数会调用 CreateFileA + WriteFile。

  我们从 IAT 找出这些 API 的地址，再全 .text 搜 `call *0xADDR`，
  得到所有 IO 调用点；再结合上下文（附近是否有 .pws 字符串引用）筛选。

输出：读档/写档候选函数入口。
"""
import re
import struct
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")


def parse_iat():
    """返回 {api_name: iat_rva}"""
    data = open(GAME, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dd = opt + (96 if magic == 0x10B else 112)
    imp_rva = struct.unpack_from("<I", data, dd + 8)[0]

    secs = []
    so = opt + opt_size
    for i in range(nsec):
        o = so + i * 40
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        secs.append((vaddr, vsize, raddr, rsize))

    def rva2off(rva):
        for vaddr, vsize, raddr, rsize in secs:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        return None

    out = {}
    off = rva2off(imp_rva)
    idx = 0
    while True:
        o = off + idx * 20
        ilt, ts, fc, name_rva, iat = struct.unpack_from("<IIIII", data, o)
        if name_rva == 0:
            break
        thunk_rva = ilt if ilt else iat
        toff = rva2off(thunk_rva)
        j = 0
        while True:
            val = struct.unpack_from("<I", data, toff + j * 4)[0]
            if val == 0:
                break
            if not (val & 0x80000000):
                hoff = rva2off(val)
                s = data[hoff + 2:data.index(b"\0", hoff + 2)].decode("ascii", "replace")
                out[s] = iat + j * 4
            j += 1
        idx += 1
    return out


def main():
    iat = parse_iat()
    print("关注的 API IAT 地址:")
    want = ["CreateFileA", "ReadFile", "WriteFile", "SetFilePointer",
            "CloseHandle", "GetFileSize", "GlobalAlloc", "LocalAlloc"]
    addr_of = {}
    for w in want:
        if w in iat:
            va = iat[w] + 0x400000
            addr_of[w] = va
            print(f"  {w:<16} IAT={iat[w]:#x}  VA={va:#x}")
    print()

    data = open(GAME, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    so = pe + 24 + opt_size
    secs = []
    for i in range(nsec):
        o = so + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode()
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        secs.append((name, vaddr, vsize, raddr, rsize))
    t = [s for s in secs if s[0] == ".text"][0]
    _n, tvma, tsize, tfoff, _r = t
    body = data[tfoff:tfoff + tsize]

    # `ff 15 xx xx xx xx` = call *imm32
    for api, va in addr_of.items():
        pat = b"\xff\x15" + struct.pack("<I", va)
        hits = []
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            hits.append(tvma + i)
            pos = i + 1
        print(f"{api}: {len(hits)} 处调用")
        if api in ("CreateFileA", "ReadFile", "WriteFile") and hits:
            for h in hits[:12]:
                print(f"   {h:#x}")
    return addr_of


if __name__ == "__main__":
    main()
