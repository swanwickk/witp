"""verify_ag.py — 验证航空队数组基址与字段偏移

候选：基址 0x598f4f8，步长 680（与存档记录长度一致）

判据：对存档里所有占用槽，检查内存同槽的
  off44 primary / off245 maxPlanes / off308 upgradeTo / off560 pctCAP
是否全部吻合。这是最严格的双向验证。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

AG = 680


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_ags(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == 20400680:
            d = r["data"]
            out = {}
            for s in range(30001):
                b = s * AG
                if d[b + 245] == 0 and d[b + 44] == 0:
                    continue
                out[s] = (d[b + 44], d[b + 245],
                          struct.unpack_from("<H", d, b + 308)[0],
                          d[b + 560], d[b + 563])
            return out
    return {}


def main():
    save = sys.argv[1]
    base = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x598f4f8
    ags = save_ags(save)
    print(f"存档航空队 {len(ags)} 个，基址={base:#x} 步长={AG}\n")

    pid = pid_of()
    fd = memrw.open_mem(pid)

    ok = 0
    bad = []
    for s in sorted(ags):
        d = memrw.read_mem(pid, base + s * AG, AG, fd)
        if not d or len(d) < AG:
            bad.append((s, "读失败"))
            continue
        mem = (d[44], d[245], struct.unpack_from("<H", d, 308)[0], d[560], d[563])
        if mem == ags[s]:
            ok += 1
        else:
            bad.append((s, f"mem={mem} save={ags[s]}"))

    print(f"完全吻合 {ok}/{len(ags)}")
    if bad:
        print(f"不吻合 {len(bad)} 个，前 8:")
        for s, why in bad[:8]:
            print(f"  slot{s}: {why}")
    else:
        print("★ 全部吻合 —— 基址与偏移正确")

    os.close(fd)


if __name__ == "__main__":
    main()
