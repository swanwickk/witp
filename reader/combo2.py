"""combo2.py — 只用非零字段做组合定位（排除零值假命中）

教训：routing/tolerance/maxReact 值为 0，任何零字节位置都会"命中"，
      导致 42 处假阳性。必须只用**非零且稀有**的值。

本次用 TF7 的非零字段：
  flagship=91, home=992, mission=15, speed=3, loadState=99
且要求 mission/speed 落在 0..25 / 0..3 合理范围。

判据：至少 4 个非零字段在固定相对偏移同时命中，且结构起点 464 对齐。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe
import pwsfile

SSZ = 556


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

    fl = struct.unpack_from("<I", d, 44)[0]
    home = struct.unpack_from("<H", d, 54)[0]
    mission = d[349]
    speed = d[354]
    load = d[350]
    print(f"TF{slot}: flagship={fl} home={home} mission={mission} "
          f"speed={speed} loadState={load}")

    pid = pid_of()
    if not pid:
        print("找不到进程")
        return
    lo, hi = 0x1000000, 0x2600000
    blob = mem_probe.gdb_read(pid, lo, hi - lo)
    print(f"已读 {len(blob)//1024//1024}MB")

    # 关键：以 loadState=99 和 mission=15 的组合为主特征
    # 先找 loadState 的所有出现
    results = []
    for off_load in range(0, 556):
        # 假设 loadState 在结构内偏移 off_load
        # 那 mission(off 349) 的相对差是 349-off_load
        for i in range(len(blob)):
            if blob[i] != load:
                continue
            start = i - off_load
            if start < 0 or start + 556 > len(blob):
                continue
            hits = []
            if blob[start + 349] == mission:
                hits.append("mission")
            if blob[start + 354] == speed:
                hits.append("speed")
            if struct.unpack_from("<I", blob, start + 44)[0] == fl:
                hits.append("flagship")
            if struct.unpack_from("<H", blob, start + 54)[0] == home:
                hits.append("home")
            if len(hits) >= 3:
                results.append((len(hits), lo + start, off_load, hits))
    results.sort(reverse=True)
    print(f"\n命中>=3 共 {len(results)} 处（off_load = loadState 的结构内偏移假设）")
    seen = set()
    for n, addr, offl, hits in results[:15]:
        key = (offl, tuple(hits))
        print(f"  {addr:#010x} 命中{n}: {','.join(hits)}  (off_load={offl})")


if __name__ == "__main__":
    main()
