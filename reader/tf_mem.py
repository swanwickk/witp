"""tf_mem.py — 运行时 TF 数组读写库（纯 /proc/pid/mem，无键鼠）

★★ 实测确定的真值（2026-10-18）★★
  基址  0xcf7510c
  步长  556   ← 与存档记录长度完全一致（不是 464）
  索引  = TF 号（名称表 0x2de79c0 也按 20 字节同序）
  字段偏移与存档一致：
    +44  flagship (u32)
    +54  home     (u16)
    +56  currentLoad (u32)
    +88? → 实为 +88 是 flagship 的错位读，正确是 +44

★★ 为什么之前一直失败 ★★
  1. gdb 的 dump binary memory 对未映射页**静默返回全零**，
     与"读到真实的零"无法区分 ⇒ 换成 /proc/pid/mem（未映射返回 EIO）
  2. 扫的 0x1000000-0x2600000 是未映射区，
     真实数据在 0x0085f000-0x0f0a7000
  3. 步长误当 464（那是另一套结构的步长），TF 记录步长 = 556

用法:
  python3 tf_mem.py list
  python3 tf_mem.py show <tf>
  python3 tf_mem.py set <tf> <field> <value>
"""
import os
import struct
import sys

BASE = 0xcf7510c
SZ = 556

# 与存档一致的偏移（已由 12/12 槽 flagship 吻合验证）
OFF = {
    "flagship": (44, "u32"),
    "home": (54, "u16"),
    "mission": (349, "u8"),
    "speed": (354, "u8"),
    "routing": (369, "u8"),
    "maxReact": (355, "u8"),
    "loadState": (350, "u8"),
    "tolerance": (448, "u8"),
    "load": (56, "u32"),
    "endure": (48, "u32"),
    "endureReq": (52, "u32"),
    "wpCount": (320, "u16"),
    "wpAlloc": (322, "u16"),
}

FMT = {"u8": "<B", "u16": "<H", "u32": "<I"}


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def _open():
    return os.open(f"/proc/{pid_of()}/mem", os.O_RDWR)


def read_tf(tf, fd=None):
    own = fd is None
    fd = fd or _open()
    try:
        os.lseek(fd, BASE + tf * SZ, os.SEEK_SET)
        return os.read(fd, SZ)
    except OSError:
        return None
    finally:
        if own:
            os.close(fd)


def get(tf, field, fd=None):
    off, kind = OFF[field]
    d = read_tf(tf, fd)
    if not d:
        return None
    return struct.unpack_from(FMT[kind], d, off)[0]


def set_field(tf, field, value, fd=None):
    off, kind = OFF[field]
    own = fd is None
    fd = fd or _open()
    try:
        os.lseek(fd, BASE + tf * SZ + off, os.SEEK_SET)
        os.write(fd, struct.pack(FMT[kind], value))
        return True
    except OSError as e:
        print("写入失败:", e)
        return False
    finally:
        if own:
            os.close(fd)


def occupied(fd=None):
    out = []
    for tf in range(1, 200):
        if get(tf, "flagship", fd):
            out.append(tf)
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if not pid_of():
        print("游戏未运行")
        return
    fd = _open()
    if cmd == "list":
        occ = occupied(fd)
        print(f"运行时 TF 数组基址={BASE:#x} 步长={SZ}")
        print(f"占用 TF: {occ}")
        for tf in occ[:20]:
            print(f"  TF{tf:<3} flagship={get(tf,'flagship',fd):<6} "
                  f"home={get(tf,'home',fd):<5} mission={get(tf,'mission',fd):<3} "
                  f"speed={get(tf,'speed',fd)}")
    elif cmd == "show":
        tf = int(sys.argv[2])
        d = read_tf(tf, fd)
        if not d:
            print("读失败")
            return
        print(f"TF{tf} @ {BASE+tf*SZ:#x}")
        for k in OFF:
            print(f"  {k:<12} = {get(tf,k,fd)}")
    elif cmd == "set":
        tf, field, val = int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
        old = get(tf, field, fd)
        ok = set_field(tf, field, val, fd)
        new = get(tf, field, fd)
        print(f"TF{tf}.{field}: {old} -> {new} (ok={ok})")
    os.close(fd)


if __name__ == "__main__":
    main()
