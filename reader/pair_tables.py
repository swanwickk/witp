"""pair_tables.py — 名称表与记录表配对

已知：名称表起点 0x2de79c0，20 字节/条，索引 = TF 号。
     TF7 结构实测在 0xcf76040（flagship=91 验证通过）。

若记录表也是定长数组且同序，则：
     记录表基址 = 0xcf76040 - 7 * 步长

试不同步长，检查 slot1..slot7 的 flagship 是否与存档逐一吻合。
这是纯算术验证，不搜索、不猜测。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556
TF7_ADDR = 0x0cf76040
TF7_SLOT = 7


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_tfs(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == 2224000:
            out = {}
            for s in range(200):
                b = s * SSZ
                fl = struct.unpack_from("<I", r["data"], b + 44)[0]
                if fl:
                    out[s] = (fl, struct.unpack_from("<H", r["data"], b + 54)[0],
                              r["data"][b + 349])
            return out
    return {}


def main():
    save = sys.argv[1]
    tfs = save_tfs(save)
    pid = pid_of()
    fd = memrw.open_mem(pid)

    best = None
    # 试 200..1200 的各种步长
    for sz in range(200, 1201, 4):
        base = TF7_ADDR - TF7_SLOT * sz
        if base < 0:
            continue
        ok = 0
        tot = 0
        for s, exp in tfs.items():
            if s > 12:
                continue
            tot += 1
            d = memrw.read_mem(pid, base + s * sz + 88, 4, fd)
            if d and struct.unpack("<I", d)[0] == exp[0]:
                ok += 1
        if tot and ok >= 5:
            if best is None or ok > best[1]:
                best = (sz, ok, tot, base)
            print(f"步长={sz:<5} 基址={base:#x}  匹配 {ok}/{tot}")

    print()
    if best:
        sz, ok, tot, base = best
        print(f"★ 最佳: 步长={sz} 基址={base:#x} 匹配 {ok}/{tot}")
        print("\n逐槽核对:")
        for s in sorted(tfs)[:14]:
            d = memrw.read_mem(pid, base + s * sz, sz if sz <= 464 else 464, fd)
            if not d:
                print(f"  slot{s}: 读失败")
                continue
            fl = struct.unpack_from("<I", d, 88)[0] if len(d) > 92 else 0
            exp = tfs[s]
            mark = "✓" if fl == exp[0] else "✗"
            print(f"  slot{s:<3} {mark} mem_flagship={fl:<6} save={exp[0]}")
    else:
        print("未找到匹配步长")

    os.close(fd)


if __name__ == "__main__":
    main()
