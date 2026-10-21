"""locate_ag.py — 定位航空队运行时结构

存档字段（680B 记录，实测）：
  off44  primary    u8   主任务
  off245 maxPlanes  u8   编制数
  off308 upgradeTo  u16  机型 ID（603=A6M2）
  off560 pctCAP     u8   CAP 百分比
  off563 pctSearch  u8   搜索百分比

定位策略：
  用「off245=27 且 off560=30」这种**稀有组合**做锚，
  然后在候选地址上验证 off44/off308 是否也吻合。
  最后试各种步长，看哪个能让多个航空队同时对齐。
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
                mp = d[b + 245]
                prim = d[b + 44]
                if mp == 0 and prim == 0:
                    continue
                out[s] = {
                    "primary": prim,
                    "maxPlanes": mp,
                    "upgradeTo": struct.unpack_from("<H", d, b + 308)[0],
                    "pctCAP": d[b + 560],
                    "pctSearch": d[b + 563],
                    "alt": struct.unpack_from("<H", d, b + 212)[0],
                }
            return out
    return {}


def blobs(pid, min_size=1 << 20):
    out = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < min_size:
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, s, e - s, fd)
        os.close(fd)
        if b:
            out.append((s, b))
    return out


def main():
    save = sys.argv[1]
    ags = save_ags(save)
    print(f"存档航空队 {len(ags)} 个")
    pid = pid_of()
    print(f"PID={pid}\n")

    # 选特征明显的（pctCAP>0 或 pctSearch>0）
    cands = {s: v for s, v in ags.items()
             if v["pctCAP"] > 0 or v["pctSearch"] > 0}
    print(f"带百分比的 {len(cands)} 个，取前 3 个做锚:")
    for s, v in list(cands.items())[:3]:
        print(f"  slot{s}: {v}")

    bs = blobs(pid)
    print(f"\n内存段 {len(bs)} 个，共 {sum(len(b) for _,b in bs)//1024//1024}MB")

    for slot, v in list(cands.items())[:3]:
        # 锚：maxPlanes(u8) + pctCAP(u8) 组合
        results = []
        for base, blob in bs:
            n = len(blob)
            for off in range(0, n - AG, 2):
                if blob[off + 245] != v["maxPlanes"]:
                    continue
                if blob[off + 560] != v["pctCAP"]:
                    continue
                if blob[off + 44] != v["primary"]:
                    continue
                if struct.unpack_from("<H", blob, off + 308)[0] != v["upgradeTo"]:
                    continue
                results.append(base + off)
        print(f"\nslot{slot} 四字段全吻合: {len(results)} 处")
        for a in results[:6]:
            print(f"  {a:#010x}  推基址={a - slot*AG:#x}")


if __name__ == "__main__":
    main()
