"""locate_tf_real.py — 在真实数据区里用组合判据定位 TF 结构

关键修正（相比之前所有尝试）：
  1. 通道用 /proc/pid/mem（gdb 会对未映射页静默返回全零）
  2. 扫描范围用 /proc/pid/maps 里的**实际可写段**，不猜区间
  3. 判据只用**非零稀有值**，避免零字节假命中
  4. 附加判据：结构内应出现合理范围的 mission(1..25)、speed(0..3)

存档 TF7 特征：flagship=91 home=992 mission=15 speed=3 loadState=99
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556


def pid_of():
    import os
    best = None
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                best = max(best or 0, int(c))
        except OSError:
            pass
    return best


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
    print(f"TF{slot}: flagship={fl} home={home} mission={mission} speed={speed}")

    pid = pid_of()
    print(f"PID={pid}")

    # 只扫大的可写匿名段
    targets = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" in perm and (e - s) >= 4 * 1024 * 1024 and not name:
            targets.append((s, e))
    print(f"候选数据段 {len(targets)} 个，共 "
          f"{sum(e-s for s,e in targets)//1024//1024}MB")

    fd = memrw.open_mem(pid)
    fl_pat = struct.pack("<I", fl)
    results = []
    try:
        for s, e in targets:
            blob = memrw.read_mem(pid, s, e - s, fd)
            if not blob:
                continue
            pos = 0
            while True:
                i = blob.find(fl_pat, pos)
                if i < 0:
                    break
                pos = i + 1
                # 假设 flagship 在结构内偏移 o，结构起点 = i-o
                # 只试存档已知的几个偏移，要求 mission/speed 同时合理
                for o in (44, 40, 42, 46, 48, 52, 56, 60, 64, 68):
                    st = i - o
                    if st < 0 or st + SSZ > len(blob):
                        continue
                    m = blob[st + 349] if st + 349 < len(blob) else 255
                    sp = blob[st + 354] if st + 354 < len(blob) else 255
                    h = struct.unpack_from("<H", blob, st + 54)[0] if st + 56 <= len(blob) else 0
                    hits = 0
                    if m == mission:
                        hits += 1
                    if sp == speed:
                        hits += 1
                    if h == home:
                        hits += 1
                    if hits >= 2:
                        results.append((hits, s + st, o, m, sp, h))
    finally:
        import os
        os.close(fd)

    results.sort(reverse=True)
    print(f"\n命中>=2 共 {len(results)} 处:")
    for hits, addr, o, m, sp, h in results[:12]:
        print(f"  {addr:#010x} 命中{hits} flagship_off={o} "
              f"mission={m} speed={sp} home={h}")


if __name__ == "__main__":
    main()
