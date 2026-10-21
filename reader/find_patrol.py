"""find_patrol.py — 定位 Patrol Zone 三个边界坐标

Patrol Zone 需要 3 个六角格（1/2/3），每个是 (x,y) 坐标对，值域 0-200。
特征：
  · 6 个 u16 字段（3 组 x,y）
  · 未设置时全 0
  · 静态代码里这些字段被成对读取（x 和 y 相邻或固定间隔）

做法：在 TF 结构 340-556 里找「全 0 且被成对引用」的位置。
"""
import re
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import witp_obj
import disasm_range

BASE = 0x6da5148
SZ = 556
GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/War in the Pacific Admiral Edition.exe")


def main():
    pid = witp_obj.game_pid()
    tfs = {}
    for tf in range(1, 40):
        d = witp_obj._read(pid, BASE + tf * SZ, SZ)
        if d and struct.unpack_from("<I", d, 44)[0]:
            tfs[tf] = d
    print(f"占用 TF {len(tfs)} 个")

    body = open(GAME, "rb").read()[0x1000:0x1000 + 0x406b7c]

    # 找 340-556 里「所有 TF 都为 0」的 u16 位置
    print("\n全 0 的 u16 偏移（步长 2）及其静态引用数:")
    cands = []
    for off in range(340, SZ - 2, 2):
        if not all(d[off] == 0 and d[off + 1] == 0 for d in tfs.values()):
            continue
        addr = BASE + off
        pat = struct.pack("<I", addr)
        cnt = 0
        pos = 0
        while True:
            i = body.find(pat, pos)
            if i < 0:
                break
            cnt += 1
            pos = i + 1
        if cnt:
            cands.append((off, cnt))

    for off, cnt in cands:
        # 检查相邻 u16 是否也被引用（成对坐标特征）
        nxt = [c for o, c in cands if o == off + 2]
        mark = " ★相邻成对" if nxt else ""
        print(f"  off{off:>3}: {cnt} 处引用{mark}")

    print("\n★ 连续成对的候选（Patrol Zone 3 组坐标）:")
    offs = [o for o, c in cands]
    runs = []
    cur = []
    for o in offs:
        if cur and o - cur[-1] != 2:
            if len(cur) >= 4:
                runs.append(cur)
            cur = []
        cur.append(o)
    if len(cur) >= 4:
        runs.append(cur)
    for r in runs:
        print(f"  off{r[0]}..{r[-1]} ({len(r)} 个 u16)")


if __name__ == "__main__":
    main()
