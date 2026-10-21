"""witp_ag.py — 航空队运行时内存读写（零键鼠）

★★ 实测确认（2026-10-18）★★
  基址  0x598f4f8   （会漂移，每次现场重定位）
  步长  680         （= 存档 PWSAirGroup 记录长度）
  索引  = 航空队槽号（与存档一致）
  验证  2699/2716 完全吻合（99.4%），余下 17 个是游戏内实时改动

字段偏移（运行时与存档**一致**，已交叉验证）：
  40  baseID        u16  驻地基地
  42  reinforceBaseID u16 转场目标
  44  primary       u8   主任务
  46  secondary     u8   次任务
  48  targetID      u16
  192 targetX       u16
  196 targetY       u16
  212 alt           u16  高度（是 u16！）
  245 maxPlanes     u8   编制数
  308 upgradeTo     u16  机型 ID
  370 agrUpgrade    u16
  560 pctCAP        u8
  561 pctLRCAP      u8
  562 pctASW        u8
  563 pctSearch     u8
  564 pctTrain      u8
  565 pctRest       u8
  628 aswArcStart   u8
  629 aswArcEnd     u8
  630 navArcStart   u8
  631 navArcEnd     u8

用法:
  python3 witp_ag.py list
  python3 witp_ag.py show <ag>
  python3 witp_ag.py set <ag> <field> <value>
"""
import os
import struct
import sys

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


def game_pid():
    # ★ 按 WINEPREFIX 精确匹配（与 witp_obj.game_pid 同一实现），见 witp_mem.game_pid
    from witp_mem import game_pid as _precise
    return _precise()


def rw_regions(pid, min_size=1 << 20):
    import re
    out = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s*(.*)", line)
            if not m:
                continue
            s, e = int(m.group(1), 16), int(m.group(2), 16)
            if "rw" in m.group(3) and (e - s) >= min_size and not m.group(4).strip():
                out.append((s, e))
    return out


def _read(pid, addr, n):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.read(fd, n)
    except OSError:
        return None
    finally:
        os.close(fd)


def _write(pid, addr, data):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.write(fd, data) == len(data)
    except OSError:
        return False
    finally:
        os.close(fd)


def find_ag_base(pid, expect):
    """expect: {ag槽号: (primary, maxPlanes, upgradeTo)}，至少 8 个吻合才认。"""
    if not expect:
        return None
    for _ in range(2):
        for slot, (prim, mp, up) in list(expect.items())[:6]:
            for s, e in rw_regions(pid):
                fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
                try:
                    os.lseek(fd, s, os.SEEK_SET)
                    blob = os.read(fd, e - s)
                except OSError:
                    continue
                finally:
                    os.close(fd)
                if not blob:
                    continue
                # 用 maxPlanes(u8)+primary(u8) 定位：先找 off245
                for off in range(0, len(blob) - AG_SZ, 1):
                    if blob[off + 245] != mp or blob[off + 44] != prim:
                        continue
                    if struct.unpack_from("<H", blob, off + 308)[0] != up:
                        continue
                    base = off - slot * AG_SZ
                    if base < 0:
                        continue
                    ok = 0
                    for s2, (p2, m2, u2) in expect.items():
                        o = base + s2 * AG_SZ
                        if 0 <= o < len(blob) - AG_SZ:
                            if (blob[o + 245] == m2 and blob[o + 44] == p2
                                    and struct.unpack_from("<H", blob, o + 308)[0] == u2):
                                ok += 1
                    if ok >= 8:
                        return s + base
    return None


def get(pid, base, ag, field):
    off, kind = AG_OFF[field]
    d = _read(pid, base + ag * AG_SZ + off, 2)
    if not d:
        return None
    return struct.unpack_from(FMT[kind], d, 0)[0]


def set_field(pid, base, ag, field, value):
    off, kind = AG_OFF[field]
    return _write(pid, base + ag * AG_SZ + off, struct.pack(FMT[kind], value))


def occupied(pid, base):
    out = []
    for ag in range(1, 30001):
        if get(pid, base, ag, "maxPlanes"):
            out.append(ag)
    return out


if __name__ == "__main__":
    pid = game_pid()
    if not pid:
        print("游戏未运行")
        sys.exit(1)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    save = os.environ.get("WITP_SAVE")
    if not save:
        print("需要 WITP_SAVE")
        sys.exit(1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pwsfile
    c = pwsfile.read_container(save)
    expect = {}
    for r in c["records"]:
        if r["u_len"] == 20400680:
            d = r["data"]
            for s in range(30001):
                b = s * AG_SZ
                if d[b + 245] == 0 and d[b + 44] == 0:
                    continue
                expect[s] = (d[b + 44], d[b + 245],
                             struct.unpack_from("<H", d, b + 308)[0])
            break
    base = find_ag_base(pid, expect)
    if base is None:
        print("定位失败")
        sys.exit(1)
    print(f"PID={pid}  AG基址={base:#x} 步长={AG_SZ}")

    if cmd == "list":
        occ = occupied(pid, base)
        print(f"占用 {len(occ)} 个")
        for ag in occ[:25]:
            print(f"  AG{ag:<5} primary={get(pid,base,ag,'primary'):<3} "
                  f"maxPlanes={get(pid,base,ag,'maxPlanes'):<4} "
                  f"CAP={get(pid,base,ag,'pctCAP'):<3} "
                  f"Search={get(pid,base,ag,'pctSearch'):<3} "
                  f"baseID={get(pid,base,ag,'baseID')}")
    elif cmd == "show":
        ag = int(sys.argv[2])
        for k in AG_OFF:
            print(f"  {k:<14} = {get(pid,base,ag,k)}")
    elif cmd == "set":
        ag, field, val = int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
        old = get(pid, base, ag, field)
        ok = set_field(pid, base, ag, field, val)
        print(f"AG{ag}.{field}: {old} -> {get(pid,base,ag,field)} (ok={ok})")
