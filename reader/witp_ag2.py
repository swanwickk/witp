"""witp_ag2.py — 航空队双副本写入（引擎真正采纳的那份）

★★ 关键发现（2026-10-18）★★
  航空队在内存里有**两份**结构副本：
    copyA  0x59904e8 起（基址 0x598f4f8 + 6*680）—— 只影响界面显示
    copyB  0xbba0c20 起（基址 0xbba0000 附近）      —— **引擎存盘时读这份**

  只改 copyA → 界面变但过回合后存档不变（假成功）
  改 copyB   → 过回合后存档里就是新值（真成功）

  TF 只有一份，所以 TF 改完就生效。这是 TF 与 AG 的关键区别。

自动定位 copyB 的方法：
  用 copyA 已知的 (primary, maxPlanes, upgradeTo) 特征，
  在内存里找**另一处**同样特征的结构，那就是 copyB。

用法:
  python3 witp_ag2.py set <ag> <field> <value>
  python3 witp_ag2.py list
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

AG_SZ = 680

AG_OFF = {
    "baseID":       (40,  "u16"),
    "reinforceBase": (42, "u16"),
    "primary":      (44,  "u8"),
    "secondary":    (46,  "u8"),
    "targetID":     (48,  "u16"),
    "targetX":      (192, "u16"),
    "targetY":      (196, "u16"),
    "alt":          (212, "u16"),
    "maxPlanes":    (245, "u8"),
    "upgradeTo":    (308, "u16"),
    "agrUpgrade":   (370, "u16"),
    "pctCAP":       (560, "u8"),
    "pctLRCAP":     (561, "u8"),
    "pctASW":       (562, "u8"),
    "pctSearch":    (563, "u8"),
    "pctTrain":     (564, "u8"),
    "pctRest":      (565, "u8"),
    "aswArcStart":  (628, "u8"),
    "aswArcEnd":    (629, "u8"),
    "navArcStart":  (630, "u8"),
    "navArcEnd":    (631, "u8"),
}
FMT = {"u8": "<B", "u16": "<H", "u32": "<I"}


def pid_of():
    # ★ 按 WINEPREFIX 精确匹配（与 witp_obj.game_pid 同一实现）。
    # 旧实现硬编码 b"wine-witp-mcp"，主实例(:98)下会失联。
    from witp_mem import game_pid as _precise
    return _precise()


def save_ag(save, slot):
    c = pwsfile.read_container(save)
    for r in c["records"]:
        if r["u_len"] == 20400680:
            b = slot * AG_SZ
            d = r["data"][b:b + AG_SZ]
            return {
                "primary": d[44],
                "maxPlanes": d[245],
                "upgradeTo": struct.unpack_from("<H", d, 308)[0],
            }
    return None


def find_both(pid, ag, sig):
    """返回 (copyA_addr, copyB_addr)。sig 来自存档。"""
    mp, prim, up = sig["maxPlanes"], sig["primary"], sig["upgradeTo"]
    hits = []
    for s, e, perm, name in memrw.regions(pid):
        if "rw" not in perm or (e - s) < (1 << 20):
            continue
        fd = memrw.open_mem(pid)
        b = memrw.read_mem(pid, s, e - s, fd)
        os.close(fd)
        if not b:
            continue
        n = len(b)
        for off in range(0, n - AG_SZ, 1):
            if b[off + 245] != mp or b[off + 44] != prim:
                continue
            if struct.unpack_from("<H", b, off + 308)[0] != up:
                continue
            hits.append(s + off)
    if not hits:
        return None, None
    # 取地址最小/最大的两个（实测 copyA 在低地址段、copyB 在高地址段）
    hits.sort()
    if len(hits) == 1:
        return hits[0], None
    return hits[0], hits[-1]


def get(pid, addr, field):
    off, kind = AG_OFF[field]
    d = memrw.read_mem(pid, addr + off, 2)
    if not d:
        return None
    return struct.unpack_from(FMT[kind], d, 0)[0]


def set_field(pid, addr, field, value):
    off, kind = AG_OFF[field]
    return memrw.write_mem(pid, addr + off, struct.pack(FMT[kind], value))


if __name__ == "__main__":
    pid = pid_of()
    if not pid:
        print("游戏未运行")
        sys.exit(1)
    cmd = sys.argv[1]
    save = os.environ.get("WITP_SAVE")
    if not save:
        print("需要 WITP_SAVE")
        sys.exit(1)

    ag = int(sys.argv[2])
    sig = save_ag(save, ag)
    if not sig:
        print(f"存档里没有 AG{ag}")
        sys.exit(1)
    print(f"AG{ag} 存档特征: {sig}")

    a, b = find_both(pid, ag, sig)
    print(f"copyA={a if a is None else hex(a)}  copyB={b if b is None else hex(b)}")
    if a is None:
        sys.exit(1)

    if cmd == "list":
        for nm, addr in (("copyA", a), ("copyB", b)):
            if addr:
                print(f"  {nm}: " + " ".join(
                    f"{k}={get(pid,addr,k)}" for k in
                    ("primary", "maxPlanes", "pctCAP", "pctSearch")))
    elif cmd == "set":
        field, val = sys.argv[3], int(sys.argv[4])
        for nm, addr in (("copyA", a), ("copyB", b)):
            if not addr:
                continue
            old = get(pid, addr, field)
            ok = set_field(pid, addr, field, val)
            print(f"  {nm}: {field} {old} -> {get(pid,addr,field)} (ok={ok})")
