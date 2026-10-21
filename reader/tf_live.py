"""tf_live.py — 每次调用都重新定位 TF 数组（地址会随游戏内操作漂移）

★ 关键教训：TF 数组地址**不稳定**。
  实测 0xcf7510c 在几分钟后失效（游戏重新分配）。
  所以任何缓存基址的做法都会失败 —— 必须每次现场定位。

定位算法（已 12/12 验证）：
  1. 用 TF 名称表确认索引（名称表 20 字节/条，索引=TF号）
  2. 在可写大段里搜 flagship 值，反推基址，要求多个 TF 同时吻合

  但更快更稳的办法：搜 TF7 的 currentLoad（稀有值）+ flagship，
  得到 TF7 结构地址 A，则基址 = A - 7*556。
  然后立刻用 TF1..TF12 的 flagship 交叉验证基址是否成立。
  验证不过就重试（地址可能又变了）。
"""
import os
import struct
import sys
import time

SZ = 556
OFF_FLAG, OFF_HOME, OFF_MISSION = 44, 54, 349
OFF_LOAD, OFF_SPEED = 56, 354


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def regions_rw(pid, min_size=1 << 20):
    out = []
    with open(f"/proc/{pid}/maps") as f:
        import re
        for line in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s*(.*)", line)
            if not m:
                continue
            s, e = int(m.group(1), 16), int(m.group(2), 16)
            if "rw" in m.group(3) and (e - s) >= min_size and not m.group(4).strip():
                out.append((s, e))
    return out


def find_base(pid, expect=None, tries=3):
    """返回 (base, tf7_addr)；失败返回 (None, None)

    expect: {tf号: flagship}，用于交叉验证
    """
    expect = expect or {}
    for attempt in range(tries):
        fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)
        try:
            for s, e in regions_rw(pid):
                try:
                    os.lseek(fd, s, os.SEEK_SET)
                    blob = os.read(fd, e - s)
                except OSError:
                    continue
                if not blob:
                    continue
                # 用 expect 里的一个已知 flagship 定位
                for tf, fl in list(expect.items())[:1]:
                    pat = struct.pack("<I", fl)
                    pos = 0
                    while True:
                        i = blob.find(pat, pos)
                        if i < 0:
                            break
                        pos = i + 1
                        st = i - OFF_FLAG
                        base = st - tf * SZ
                        if base < 0:
                            continue
                        # 交叉验证：至少 5 个 TF 的 flagship 吻合
                        ok = 0
                        for t2, f2 in expect.items():
                            off = base + t2 * SZ + OFF_FLAG
                            if 0 <= off < len(blob) - 4:
                                if struct.unpack_from("<I", blob, off)[0] == f2:
                                    ok += 1
                        if ok >= 5:
                            return s + base, s + st
        finally:
            os.close(fd)
        time.sleep(1)
    return None, None


def read_at(pid, addr, n=SZ):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.read(fd, n)
    except OSError:
        return None
    finally:
        os.close(fd)


def write_at(pid, addr, data):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.write(fd, data) == len(data)
    except OSError as e:
        print("写入失败:", e)
        return False
    finally:
        os.close(fd)


if __name__ == "__main__":
    pid = pid_of()
    print(f"PID={pid}")
    # 需要 expect：从存档读
    import pwsfile
    save = sys.argv[1] if len(sys.argv) > 1 else None
    expect = {}
    if save:
        c = pwsfile.read_container(save)
        for r in c["records"]:
            if r["u_len"] == 2224000:
                for s in range(200):
                    b = s * SZ
                    fl = struct.unpack_from("<I", r["data"], b + OFF_FLAG)[0]
                    if fl:
                        expect[s] = fl
                break
    print(f"expect {len(expect)} 个 TF")
    base, tf7 = find_base(pid, expect)
    print(f"基址={base if base is None else hex(base)}  TF7={tf7 if tf7 is None else hex(tf7)}")
