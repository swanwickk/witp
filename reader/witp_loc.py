"""witp_loc.py — 基地(Location)运行时内存读写（零键鼠）

★★ 实测确认（2026-10-18）★★
  基址  0x4570c50   （会漂移，每次现场重定位）
  步长  1172        （= 存档 PWSLocation 记录长度）
  索引  = Location 槽号
  验证  已加载 116 个中 90 个坐标完全吻合；
        不吻合的 26 个全在 slot 14000+（TF 专用槽，非普通基地）

字段偏移（与存档一致）：
  36  X             u16
  38  Y             u16
  102 prepTarget    u16   准备目标基地 ID
  104 prep          u8    准备度 %
  110 combatMode    u8    0=defend 1=bombard 2=deliberate 3=shock
  424 portExpand    u32
  428 airfieldExpand u32
  432 fortExpand    u32
  651 marchDir      u8
  652 marchLen      u8
  662 destX         u16   行军目的地
  664 destY         u16
  906 operationsMode u16  0=strategic 1=move 2=combat 3=reserve 4=rest
"""
import os
import struct
import sys

LOC_SZ = 1172

LOC_OFF = {
    "X":              (36,  "u16"),
    "Y":              (38,  "u16"),
    "prepTarget":     (102, "u16"),
    "prep":           (104, "u8"),
    "combatMode":     (110, "u8"),
    # ★ 扩建是 u8（u32 读会串到相邻字段）
    "portExpand":     (424, "u8"),
    "airfieldExpand": (428, "u8"),
    "fortExpand":     (432, "u8"),
    "marchDir":       (651, "u8"),
    "marchLen":       (652, "u8"),
    "destX":          (662, "u16"),
    "destY":          (664, "u16"),
    "operationsMode": (906, "u16"),
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


_BASE_CACHE = {}

# ★ 实测已知基址（同一局内稳定）。find_loc_base 先验证它，失败才全量扫。
KNOWN_BASE = 0x4570c50


def find_loc_base(pid, expect):
    """expect: {loc槽号: (X,Y,prep,prepTarget)}，至少 6 个吻合才认。

    ★ 性能：先用上次成功的基址快速验证，不通过才全量扫。
      全量扫一次约 60-120 秒，无法每次调用都做。
    """
    if not expect:
        return None

    # 快速路径 0：已知基址单点验证（最快，~10ms）
    for cand in [KNOWN_BASE] + list(_BASE_CACHE.get(pid, [])):
        ok = 0
        for slot, (x, y, prep, pt) in list(expect.items())[:20]:
            d = _read(pid, cand + slot * LOC_SZ, LOC_SZ)
            if d and (struct.unpack_from("<H", d, 36)[0] == x
                      and struct.unpack_from("<H", d, 38)[0] == y):
                ok += 1
        if ok >= 6:
            if cand not in _BASE_CACHE.get(pid, []):
                _BASE_CACHE.setdefault(pid, []).insert(0, cand)
            return cand
    blobs = []
    for s, e in rw_regions(pid):
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        try:
            os.lseek(fd, s, os.SEEK_SET)
            b = os.read(fd, e - s)
        except OSError:
            continue
        finally:
            os.close(fd)
        if b:
            blobs.append((s, b))

    # 用样本反推候选基址
    from collections import Counter
    cnt = Counter()
    samples = list(expect.items())[:10]
    for slot, (x, y, prep, pt) in samples:
        for base, blob in blobs:
            n = len(blob)
            for off in range(0, n - LOC_SZ, 2):
                if struct.unpack_from("<H", blob, off + 36)[0] != x:
                    continue
                if struct.unpack_from("<H", blob, off + 38)[0] != y:
                    continue
                if blob[off + 104] != prep:
                    continue
                cnt[base + off - slot * LOC_SZ] += 1

    for cand, _score in cnt.most_common(5):
        ok = 0
        for slot, (x, y, prep, pt) in expect.items():
            d = _read(pid, cand + slot * LOC_SZ, LOC_SZ)
            if not d:
                continue
            if (struct.unpack_from("<H", d, 36)[0] == x
                    and struct.unpack_from("<H", d, 38)[0] == y):
                ok += 1
        if ok >= 6:
            _BASE_CACHE.setdefault(pid, []).insert(0, cand)
            return cand
    return None


def get(pid, base, loc, field):
    off, kind = LOC_OFF[field]
    d = _read(pid, base + loc * LOC_SZ + off, 4)
    if not d:
        return None
    return struct.unpack_from(FMT[kind], d, 0)[0]


def set_field(pid, base, loc, field, value):
    off, kind = LOC_OFF[field]
    return _write(pid, base + loc * LOC_SZ + off, struct.pack(FMT[kind], value))


if __name__ == "__main__":
    pid = game_pid()
    if not pid:
        print("游戏未运行")
        sys.exit(1)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    save = os.environ.get("WITP_SAVE")
    if not save:
        print("需要 WITP_SAVE")
        sys.exit(1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pwsfile
    d = pwsfile.record_by_len(save, 21096000)
    expect = {}
    if d:
        for s in range(18000):
            b = s * LOC_SZ
            x = struct.unpack_from("<H", d, b + 36)[0]
            y = struct.unpack_from("<H", d, b + 38)[0]
            if not (0 < x < 250 and 0 < y < 250):
                continue
            expect[s] = (x, y, d[b + 104],
                         struct.unpack_from("<H", d, b + 102)[0])
    base = find_loc_base(pid, expect)
    if base is None:
        print("定位失败")
        sys.exit(1)
    print(f"PID={pid}  LOC基址={base:#x} 步长={LOC_SZ}")

    if cmd == "show":
        loc = int(sys.argv[2])
        for k in LOC_OFF:
            print(f"  {k:<15} = {get(pid,base,loc,k)}")
    elif cmd == "set":
        loc, field, val = int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
        old = get(pid, base, loc, field)
        ok = set_field(pid, base, loc, field, val)
        print(f"LOC{loc}.{field}: {old} -> {get(pid,base,loc,field)} (ok={ok})")
    elif cmd == "find":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        for s in expect:
            if expect[s][:2] == (x, y):
                print(f"  slot{s}: {expect[s]}")
