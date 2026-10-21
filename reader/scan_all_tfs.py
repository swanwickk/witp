"""scan_all_tfs.py — 扫描数据区，找出所有 TF 结构实例

判据（严格）：
  结构起点 S 满足：
    · S+88 是 u32 flagship，落在 1..8000（舰船 ID 范围）
    · S+98 是 u16 home，落在 1..2000（基地 ID 范围）
    · S+393 是 u8 mission，落在 1..25
    · S+398 是 u8 speed，落在 0..3
  四条同时满足才认。单条太松，组合后误报率极低。

输出：所有命中地址 + 相邻地址差（看步长），并对照存档里的 TF 值。
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SSZ = 556
OFF_FLAG, OFF_HOME, OFF_MISSION, OFF_SPEED = 88, 98, 393, 398


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
    save_flags = {v[0]: k for k, v in tfs.items()}
    print(f"存档占用 {len(tfs)} 个 TF，flagship 集合已建")

    pid = pid_of()
    hits = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < 4 * 1024 * 1024:
            continue
        fd = memrw.open_mem(pid)
        blob = memrw.read_mem(pid, s, e - s, fd)
        import os
        os.close(fd)
        if not blob:
            continue
        n = len(blob)
        for off in range(0, n - 464, 2):
            fl = struct.unpack_from("<I", blob, off + OFF_FLAG)[0]
            if fl < 1 or fl > 8000:
                continue
            hm = struct.unpack_from("<H", blob, off + OFF_HOME)[0]
            if hm < 1 or hm > 2000:
                continue
            mi = blob[off + OFF_MISSION]
            if mi < 1 or mi > 25:
                continue
            sp = blob[off + OFF_SPEED]
            if sp > 3:
                continue
            hits.append((s + off, fl, hm, mi, sp))

    print(f"\n命中 {len(hits)} 个候选结构")
    # 按 flagship 与存档对照
    matched = [h for h in hits if h[1] in save_flags]
    print(f"其中 flagship 与存档对上的: {len(matched)}")
    for addr, fl, hm, mi, sp in matched[:30]:
        print(f"  {addr:#010x} flagship={fl:<5} home={hm:<5} "
              f"mission={mi:<3} speed={sp}  (存档 slot {save_flags[fl]})")

    # 相邻差
    addrs = sorted(a for a, *_ in matched)
    if len(addrs) > 2:
        diffs = [addrs[i + 1] - addrs[i] for i in range(len(addrs) - 1)]
        print(f"\n相邻地址差（前20）: {diffs[:20]}")


if __name__ == "__main__":
    main()
