"""locate_multi.py — 用多个 TF 各自的稀有载荷值定位，反推数组组织

做法：
  对存档里每个占用的 TF，取其 currentLoad（off56）作为特征值，
  在内存里搜「+56 等于该值 且 +88 等于该 TF 的 flagship」的位置。
  每个 TF 得到 1~2 个地址后，看这些地址之间是否构成等差数列。

这是纯数据驱动，不预设任何基址。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556


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
                if not fl:
                    continue
                out[s] = {
                    "flagship": fl,
                    "home": struct.unpack_from("<H", r["data"], b + 54)[0],
                    "mission": r["data"][b + 349],
                    "load": struct.unpack_from("<I", r["data"], b + 56)[0],
                    "endure": struct.unpack_from("<I", r["data"], b + 48)[0],
                }
            return out
    return {}


def main():
    save = sys.argv[1]
    tfs = save_tfs(save)

    pid = pid_of()
    # 一次性读所有大 rw 段
    blobs = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < 1024 * 1024:
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, s, e - s, fd)
        os.close(fd)
        if b:
            blobs.append((s, b))
    print(f"读入 {len(blobs)} 段，共 {sum(len(b) for _,b in blobs)//1024//1024}MB\n")

    found = {}
    for slot, f in sorted(tfs.items()):
        load = f["load"]
        if load == 0:
            continue
        pat = struct.pack("<I", load)
        hits = []
        for base, blob in blobs:
            pos = 0
            while True:
                i = blob.find(pat, pos)
                if i < 0:
                    break
                pos = i + 1
                st = i - 56
                if st < 0 or st + 464 > len(blob):
                    continue
                fl = struct.unpack_from("<I", blob, st + 88)[0]
                if fl == f["flagship"]:
                    hits.append(base + st)
        if hits:
            found[slot] = (load, hits)
            print(f"slot{slot:<3} load={load:<8} flagship={f['flagship']:<5} "
                  f"→ {len(hits)} 处: " + ", ".join(f"{h:#x}" for h in hits[:3]))

    print(f"\n共定位 {len(found)} 个 TF")
    addrs = sorted(a for _, hs in found.values() for a in hs)
    if len(addrs) > 3:
        diffs = [addrs[i + 1] - addrs[i] for i in range(len(addrs) - 1)]
        from collections import Counter
        print("地址差分布:", Counter(diffs).most_common(6))


if __name__ == "__main__":
    main()
