"""find_arr_base.py — 由 TF7 结构地址反推数组基址并验证

已知：TF7 结构起点 = 0xcf76040（flagship 在 +44，实测命中 0xcf7606c）
若步长 464 且 slot 号即 TF 号，则基址 = 0xcf76040 - 7*464

验证判据（必须能失败）：
  对每个占用槽 s，检查 base + s*464 + 88 == 存档 flagship[s]
  且 base + s*464 + 98 == 存档 home[s]
  且 base + s*464 + 393 == 存档 mission[s]
  全部吻合才算找到。
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556
RSZ = 464
TF7_ADDR = 0xcf76040
TF7_SLOT = 7

OFF_FLAG = 88
OFF_HOME = 98
OFF_MISSION = 393


def pid_of():
    import os
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
    base = TF7_ADDR - TF7_SLOT * RSZ
    print(f"TF7 @ {TF7_ADDR:#x}, 推定基址 = {base:#x}\n")

    pid = pid_of()
    fd = memrw.open_mem(pid)

    ok = 0
    bad = []
    for s in sorted(tfs):
        d = memrw.read_mem(pid, base + s * RSZ, RSZ, fd)
        if not d or len(d) < RSZ:
            bad.append((s, "读失败"))
            continue
        fl = struct.unpack_from("<I", d, OFF_FLAG)[0]
        hm = struct.unpack_from("<H", d, OFF_HOME)[0]
        mi = d[OFF_MISSION]
        exp = tfs[s]
        if fl == exp[0] and hm == exp[1] and mi == exp[2]:
            ok += 1
        else:
            bad.append((s, f"mem=({fl},{hm},{mi}) save={exp}"))

    print(f"匹配 {ok}/{len(tfs)}")
    if bad:
        print("不匹配:")
        for s, why in bad[:10]:
            print(f"  slot{s}: {why}")
    else:
        print("★ 全部吻合 —— 基址正确")

    import os
    os.close(fd)


if __name__ == "__main__":
    main()
