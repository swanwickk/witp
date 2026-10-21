"""sig_search.py — 用存档真实值在内存里搜运行时结构

原理（这是唯一不会自我欺骗的方法）：
  存档里 TF7 的旗舰 ID = 91、母港 = 992、任务 = 15（AMPHIB）、
  以及 11 个航路点坐标 (106,125)...(99,127)。
  运行时结构若与存档有对应关系，这些值必然以某种编码出现在内存里。

  更重要的是：**TF 名称字符串**（"MO Landing Force" 或 "Kyou..."）
  是天然的唯一标识，比数字可靠得多。

步骤：
  1. 从存档取 TF7 的旗舰/母港/任务/名称
  2. 在内存里搜这些值（u16/u32/ASCII 三种编码）
  3. 命中后回溯，看是否落在 464 步长结构里
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe
import pwsfile

SSZ = 556
SZ = 0x1d0


def pid_of():
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{cand}/environ", "rb").read():
                return int(cand)
        except OSError:
            pass
    return None


def save_tf(path, slot):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == 2224000:
            return r["data"][slot * SSZ:(slot + 1) * SSZ]
    return None


def main():
    save = sys.argv[1]
    slot = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    d = save_tf(save, slot)
    if not d:
        print("读存档失败")
        return
    flagship = struct.unpack_from("<I", d, 44)[0]
    home = struct.unpack_from("<H", d, 54)[0]
    mission = d[349]
    speed = d[354]
    print(f"存档 TF{slot}: flagship={flagship} home={home} mission={mission} speed={speed}")

    # 找名称：offsets 424 起（若存档也是）
    names = []
    for off in range(400, SSZ - 20):
        run = []
        for i in range(off, min(off + 24, SSZ)):
            if 32 <= d[i] < 127:
                run.append(chr(d[i]))
            else:
                break
        if len(run) >= 6:
            names.append((off, "".join(run)))
    print("存档内名称候选:", names[:5])

    pid = pid_of()
    if not pid:
        print("找不到进程")
        return

    # 搜旗舰 ID（u32 / u16）
    lo, hi = 0x1000000, 0x2600000
    blob = mem_probe.gdb_read(pid, lo, hi - lo)
    if not blob:
        print("内存读取失败")
        return
    print(f"已读 {len(blob)//1024//1024}MB 用于搜索")

    for val, label in ((flagship, "flagship"), (home, "home"), (mission, "mission")):
        for width, packer in ((4, "<I"), (2, "<H")):
            if width == 2 and val > 0xFFFF:
                continue
            pat = struct.pack(packer, val)
            hits = []
            pos = 0
            while len(hits) < 8:
                i = blob.find(pat, pos)
                if i < 0:
                    break
                hits.append(lo + i)
                pos = i + 1
            if hits:
                print(f"  {label}={val} (u{width*8}): {len(hits)} 命中 → "
                      + ", ".join(hex(h) for h in hits[:5]))

    # 搜名称
    for off, nm in names[:3]:
        pat = nm.encode()
        i = blob.find(pat)
        if i >= 0:
            print(f"  名称 {nm!r} 命中 @ {lo+i:#x}")


if __name__ == "__main__":
    main()
