"""verify_tf_arr.py — 验证候选 TF 数组基址（464 步长 + 多槽一致性）

两个候选命中点：
  0x0cf7606c  → 若 off44 是 flagship，基址 = 0x0cf76040
  0x06da607c  → 基址 = 0x06da6050

判据（必须能失败）：
  1. 按 464 步长，多个槽都应命中存档里对应 TF 的 flagship
  2. 空槽（0/13/19/26/27）的 flagship 应为 0
  3. 步长必须是 464（用相邻两个 TF 的地址差验证）
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556
RSZ = 464
OCC = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18,
       20, 21, 22, 23, 24, 25, 28, 29, 30]
EMPTY = [0, 13, 19, 26, 27]


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
    print(f"存档占用槽 {len(tfs)} 个")

    pid = pid_of()
    fd = memrw.open_mem(pid)

    for base in (0x0cf76040, 0x06da6050):
        print(f"\n=== 候选基址 {base:#x} ===")
        matched = 0
        total = 0
        for s in OCC:
            if s not in tfs:
                continue
            total += 1
            d = memrw.read_mem(pid, base + s * RSZ, RSZ, fd)
            if not d or len(d) < RSZ:
                print(f"  slot{s}: 读取失败")
                continue
            fl = struct.unpack_from("<I", d, 44)[0]
            hm = struct.unpack_from("<H", d, 54)[0]
            mi = d[349]
            exp = tfs[s]
            ok = (fl == exp[0] and hm == exp[1] and mi == exp[2])
            if ok:
                matched += 1
            if s <= 8 or not ok:
                mark = "✓" if ok else "✗"
                print(f"  slot{s:<3} {mark} mem=(fl={fl},home={hm},m={mi}) "
                      f"save=(fl={exp[0]},home={exp[1]},m={exp[2]})")
        print(f"  匹配 {matched}/{total}")

        # 空槽检查
        empties = []
        for s in EMPTY:
            d = memrw.read_mem(pid, base + s * RSZ + 44, 4, fd)
            if d:
                empties.append(struct.unpack("<I", d)[0])
        print(f"  空槽 flagship: {empties}  (应全为 0)")

    import os
    os.close(fd)


if __name__ == "__main__":
    main()
