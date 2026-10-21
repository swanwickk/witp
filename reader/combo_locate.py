"""combo_locate.py — 组合判据定位运行时 TF 结构

单个值会到处命中，但**多个字段同时满足固定相对偏移**的概率极低。
这是唯一不会自我欺骗的判据。

做法：
  1. 从存档取 TF7 的若干字段值（flagship/home/mission/speed/loadState）
  2. 在内存里找所有出现 flagship 的位置 P
  3. 对每个 P，检查 P - off_flagship + off_X 处是否等于对应字段值
  4. 若某偏移假设下多个字段同时命中 → 该结构即运行时 TF，偏移假设成立

这样连偏移都是**搜出来的**，不是我猜的。
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

    # 取存档字段（已知偏移）
    fields = {
        "flagship": struct.unpack_from("<I", d, 44)[0],
        "home": struct.unpack_from("<H", d, 54)[0],
        "mission": d[349],
        "speed": d[354],
        "routing": d[369],
        "tolerance": d[448],
        "maxReact": d[355],
        "loadState": d[350],
    }
    print("存档 TF%d 字段: %s" % (slot, fields))

    pid = pid_of()
    if not pid:
        print("找不到进程")
        return

    lo, hi = 0x1000000, 0x2600000
    blob = mem_probe.gdb_read(pid, lo, hi - lo)
    print(f"已读 {len(blob)//1024//1024}MB")

    # 找 flagship 的所有出现
    fl = fields["flagship"]
    pat = struct.pack("<I", fl)
    cands = []
    pos = 0
    while True:
        i = blob.find(pat, pos)
        if i < 0:
            break
        cands.append(i)
        pos = i + 1
        if len(cands) > 400:
            break
    print(f"flagship={fl} 出现 {len(cands)} 处")

    # 对每个候选，假设它是结构内 off 44（存档同偏移），
    # 则结构起点 = P - 44；检查其它字段在存档同偏移处是否也匹配
    best = []
    for P in cands:
        start = P - 44
        if start < 0 or start + 464 > len(blob):
            continue
        hit = 1   # flagship 本身
        detail = ["flagship"]
        # 存档偏移直接映射
        if blob[start + 54:start + 56] == struct.pack("<H", fields["home"]):
            hit += 1
            detail.append("home")
        if blob[start + 349] == fields["mission"]:
            hit += 1
            detail.append("mission")
        if blob[start + 354] == fields["speed"]:
            hit += 1
            detail.append("speed")
        if blob[start + 369] == fields["routing"]:
            hit += 1
            detail.append("routing")
        if blob[start + 448] == fields["tolerance"]:
            hit += 1
            detail.append("tolerance")
        if blob[start + 355] == fields["maxReact"]:
            hit += 1
            detail.append("maxReact")
        if hit >= 3:
            best.append((hit, lo + start, detail))

    best.sort(reverse=True)
    print(f"\n多字段同时命中 (>=3) 共 {len(best)} 处:")
    for hit, addr, detail in best[:10]:
        print(f"  {addr:#010x}  命中{hit}个: {','.join(detail)}")


if __name__ == "__main__":
    main()
