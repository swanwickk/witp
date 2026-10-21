"""witp_obj.py — WitP-AE 全部运行时对象的读写库（零键鼠）

═══════════════════════════════════════════════════════════════
★★ 全部基址/步长均为实测验证，每类都做了全量名称或字段核对 ★★
═══════════════════════════════════════════════════════════════

| 对象      | 主副本基址   | 镜像基址    | 步长 | 验证          |
|-----------|-------------|------------|------|---------------|
| TaskForce | 0x6da5148   | 无         | 556  | 27/27 flagship |
| AirGroup  | 0x598f4f8   | 0xbba0c20  | 680  | 2699/2716     |
| Location  | 0x4570c50   | 无         | 1172 | 90/116        |
| Ship      | 0x1a14378   | 0xb2adcb0  | 464  | 92/92 名称    |
| Leader    | 0x252b3f8   | 无         | 180  | 19943/19943   |
| ShipClass | 0x3755160   | 0xe8a8400  | 380  | 1646/1646     |
| Aircraft  | 0x6d44660   | 0xcf14658  | 396  | 554/554       |
| Device    | 0x3f0b460   | 0xea78208  | 236  | 1474/1474     |

★★ 副本规则（重要）★★
  AirGroup / Ship / ShipClass / Aircraft / Device 有**两份**副本。
  只改主副本 → 界面变但过回合后存档不变（假成功）。
  两份都改 → 引擎存盘采纳。
  TaskForce / Location / Leader 只有一份，改完立即生效。

★★ 验证结论 ★★
  Ship 改 repairPriority 1→4，过回合后存档 = 4 ✓
  TF / AG / LOC 三类均已过回合验证 ✓
"""
import os
import struct
import sys

import pathlib as _pl
READER = str(_pl.Path(__file__).resolve().parent)
if READER not in sys.path:
    sys.path.insert(0, READER)

import memrw
import pwsfile

# ── 对象表 ──────────────────────────────────────────────
OBJECTS = {
    "taskforce": {"ulen": 2224000, "sz": 556,  "base": 0x6da5148, "mirror": None},
    "airgroup":  {"ulen": 20400680, "sz": 680, "base": 0x598f4f8, "mirror": 0xbba0c20},
    "location":  {"ulen": 21096000, "sz": 1172, "base": 0x4570c50, "mirror": None},
    "ship":      {"ulen": 9280000, "sz": 464,  "base": 0x1a14378, "mirror": 0xb2adcb0},
    "leader":    {"ulen": 9000000, "sz": 180,  "base": 0x252b3f8, "mirror": None},
    "shipclass": {"ulen": 1900000, "sz": 380,  "base": 0x3755160, "mirror": 0xe8a8400},
    "aircraft":  {"ulen": 396000,  "sz": 396,  "base": 0x6d44660, "mirror": 0xcf14658},
    "device":    {"ulen": 472000,  "sz": 236,  "base": 0x3f0b460, "mirror": 0xea78208},
    # ★ 步长是 304（反汇编 imul $0x130 确认）；存档是 152 紧凑格式
    "pilot":     {"ulen": 15200000, "sz": 304, "base": 0x7f7faa8, "mirror": 0xda29500},
}

# ── 字段表（全部实测）──────────────────────────────────
FIELDS = {
    # ★ TF：前段偏移与存档不同（endure/endureReq/fuel/load），mission 之后一致
    "taskforce": {
        "endure":     (4,   "u32"),
        "endureReq":  (8,   "u32"),
        "fuel":       (12,  "u32"),
        "load":       (28,  "u32"),
        "flagship":   (44,  "u32"),
        "home":       (54,  "u16"),
        "wpCount":    (320, "u16"),
        "wpAlloc":    (322, "u16"),
        "mission":    (349, "u8"),
        # ★ off350 是 loadState（99=空闲），不是 leaderID —— 上一轮误判已纠正
        "loadState":  (350, "u8"),
        # ★ off60 (u16) = 目的地/所在 Location ID
        #   0 = 海上；1..29 = 离图区（General Defence/Kwantung/…）；
        #   正常坐标基地如 992 = Rabaul
        #   ★ 写入离图区 ID 即实现 TF 离图移动（手册 6.2.10）
        "atBase":     (60,  "u16"),
        "docked":     (401, "u8"),
        "docked2":    (402, "u8"),
        # ★ off354/356/361 是计算出的当前速度；off362 才是速度档设置（可写）
        "speed":      (354, "u8"),
        "speedSetting": (362, "u8"),
        "maxReact":   (389, "u8"),
        # ★ routing（TF 路由安全等级）：off356，用 WITPloc003.csv TFRouting 列
        #   对运行内存 25 个 TF 交叉验证 25/25 精确命中。
        #   off361 只是引擎算出的镜像（24/25），不是命令源。
        "routing":    (356, "u8"),
        "tolerance":  (448, "u8"),
        # ★ TF Retirement（手册 6.9）：off388 u8，0=Retire Allowed，1=Remain on Station
        #   用 WITPloc003.csv 的 TFRetirement 列对 4 个存档 102 个 TF 样本交叉验证：
        #   第1回合 26/26 全中；第4/5回合有 3 个 TF 被引擎在航行中改写为 0。
        "retirement": (388, "u8"),
        # ★ Follow/Meet/Patrol（实测：写值过回合保留）
        #   off447: 0=未设置 1=Follow TF 2=Meet TF 3=Patrol Zone
        #   off486: u16 目标 TF 号（Follow/Meet 用）
        #   off364..375: 12 个 u16 = Patrol Zone 3 组坐标（每组 x,y）
        "followMode": (447, "u8"),
        "followTF":   (486, "u16"),
        "patrol1X":   (364, "u16"),
        "patrol1Y":   (366, "u16"),
        "patrol2X":   (368, "u16"),
        "patrol2Y":   (370, "u16"),
        "patrol3X":   (372, "u16"),
        "patrol3Y":   (374, "u16"),
    },
    # ★ 航空队：与存档一致
    "airgroup": {
        "baseID":        (40,  "u16"),
        "reinforceBase": (42,  "u16"),
        "delay":         (220, "i32"),   # arrival delay/sentinel, raw
        "delayReinforcement": (224, "u8"),
        "primary":       (44,  "u8"),
        "secondary":     (46,  "u8"),
        "targetX":       (192, "u16"),
        "targetY":       (196, "u16"),
        "alt":           (212, "u16"),
        "maxPlanes":     (245, "u8"),
        "upgradeTo":     (308, "u16"),
        "pctCAP":        (560, "u8"),
        "pctLRCAP":      (561, "u8"),
        "pctASW":        (562, "u8"),
        "pctSearch":     (563, "u8"),
        "pctTrain":      (564, "u8"),
        "pctRest":       (565, "u8"),
        "withdraw":      (392, "u32"),
        "delay2":         (396, "i32"),   # second delay field, raw; semantics scenario-dependent
        "aswArcStart":   (628, "u8"),
        "aswArcEnd":     (629, "u8"),
        "navArcStart":   (630, "u8"),
        "navArcEnd":     (631, "u8"),
    },
    # ★ 基地：与存档一致，扩建是 u8
    "location": {
        "name":            (0,   "str25"),
        "X":              (36,  "u16"),
        "Y":              (38,  "u16"),
        "prepTarget":     (102, "u16"),
        "arrive":         (42,  "u16"),   # entry Location ID; not a date
        "delay":          (564, "i32"),   # reinforcement/arrival delay or sentinel; raw
        "withdrawal":     (908, "u16"),   # candidate code (e.g. 10002), not YYMMDD
        "prep":           (104, "u8"),
        "combatMode":     (110, "u8"),
        # ★ off118 = 基地归属的 HQ/司令部编号（1..30，可写）
        "attachedHQ":    (118, "u16"),
        # ★ off124 = 司令部层级（Far East Command=14 … 5th Fleet=1）
        "cmdLevel":      (124, "u8"),
        # ★ off786 = 港口等级/容量等级（1..8）
        "portSize":      (786, "u8"),
        # ★ off128 (u32) = 该司令部的指挥官 leader ID（换将命令源）
        "leaderID":      (128, "u32"),
        "portExpand":     (424, "u8"),
        "airfieldExpand": (428, "u8"),
        "fortExpand":     (432, "u8"),
        "marchDir":       (651, "u8"),
        "marchLen":       (652, "u8"),
        "destX":          (662, "u16"),
        "destY":          (664, "u16"),
        "operationsMode": (906, "u16"),
    },
    # 舰船：名称在 0，20 字节
    "ship": {
        "name":           (0,   "str20"),
        "reinforcementDelay": (36, "i32"), # raw reinforcement delay/sentinel; not ship repair delay
        "arrivalPort":    (40,  "u16"),   # arrival Location ID
        "withdrawal":     (44,  "i32"),   # candidate date field; semantics require nonzero scenario validation
        "returnDate":     (48,  "i32"),   # candidate return date; semantics require validation
        "shipClass":      (26,  "u16"),
        "endurance":      (56,  "u16"),
        "fuel":           (58,  "u16"),
        "sysDamage":      (70,  "u16"),
        "fltDamage":      (72,  "u16"),
        "fireDamage":     (74,  "u16"),
        "engDamage":      (76,  "u16"),
        # ★ 损伤四值（实测：逐字节写→看界面列确认）
        "fireDamage":     (331, "u8"),
        "sysDamage":      (332, "u8"),
        "fltDamage":      (333, "u8"),
        "engDamage":      (335, "u8"),
        # ★ 舰船所属 TF/基地：14000+TF号 = 编队；1..14000 = 基地 Location ID
        #   实测：Myoko 14001→14007 过回合保留
        "locationID":     (62,  "u16"),
        # ★ off32 = TF 指挥官 leader ID（由 Location.off128 派生，只读）
        "leaderID":       (32,  "u32"),
        "repairPriority": (338, "u8"),
        "repairMode":     (339, "u8"),
        "tempAPConv":     (341, "u8"),
        "convDelay":      (344, "u8"),
        "upgrade":        (365, "u8"),
    },
    # 指挥官：名称在 0，24 字节
    "leader": {
        "name":         (0,  "str24"),
        "rank":         (25, "u8"),
        "skill":        (26, "u8"),   # ★CSV 逐列比对 1959/1959（2026-10-20 :97 实测）
        "morale":       (27, "u8"),
        "surfaceAction":(28, "u8"),
        "airAction":    (29, "u8"),
        "landAction":   (30, "u8"),
        "administration":(31,"u8"),
        "aggressiveness":(32,"u8"),
        "nationality":  (42, "u8"),
        # ★ off48 = 政治点（CSV PoliticalPoints 1959/1959 全中；旧标签 leadership 是错的）
        "politicalPoints": (48, "u8"),
        "commandsType": (49, "u8"),
    },
    # 舰级 / 机型 / 设备：名称在 0，40 字节
    # ★ 静态数据：名称 40B，off40=自身ID，off52=耐久(u16)，off56=航速
    "shipclass": {
        "name":     (0,  "str40"),
        "id":       (40, "u16"),
        "endurance": (52, "u16"),
        "speed":    (56, "u8"),
        "fuel":     (58, "u8"),
    },
    "aircraft":  {
        "name":     (0,  "str40"),
        # ★CSV WITPair003 逐列比对 231/231（2026-10-20 :97 实测）
        "type":       (25,  "u8"),
        "maxAltitude":(28,  "u16"),
        "maxSpeed":   (30,  "u16"),
        "cruiseSpeed":(32,  "u16"),
        "climbRate":  (34,  "u16"),
        "maneuver":   (36,  "u8"),
        "armour":     (40,  "u8"),
        "durability": (41,  "u8"),
        "maxLoad":    (182, "u16"),
        "availMonth": (184, "u8"),
        "availYear":  (185, "u8"),
        "buildRate":  (188, "u16"),
        "upgradeTo":  (192, "u16"),  # CSV UpgradeToUnitID
        "serviceRating": (229, "u8"),
        # off194 u16 全 0（本剧本无在研）；语义未确证，勿当研发进度用
    },
    # ★ off60 是 upgrade 目标设备 ID（99=无）；off62 是辅助字段
    "device":    {
        "name":     (0,  "str40"),
        "upgradeTo": (60, "u16"),
        "speed":    (52, "u16"),
        "penetration": (54, "u16"),
    },
    # 飞行员：304B/槽（存档 152 紧凑），无名称字段
    # 反汇编 0x429720-0x429a80 提取的读写字段：
    #   W(可写): 0, 12, 52, 92, 112, 256
    #   R(只读): 160, 161, 162, 185
    # 实测 off52 写入过回合保留（值域 0/1/2，任务状态码）
    "pilot": {
        "id":        (4,   "u32"),
        "status":    (52,  "u8"),   # ★可写：0/1/2 任务状态
        "field12":   (12,  "u8"),
        "field92":   (92,  "u8"),
        "exp":       (112, "u8"),   # 派生（写入不保留）
        "field256":  (256, "u8"),
        "read160":   (160, "u8"),   # 只读
        "read185":   (185, "u8"),   # 只读
    },
}

FMT = {"u8": "<B", "u16": "<H", "u32": "<I", "i32": "<i", "i16": "<h",
       "str20": "str20", "str24": "str24", "str25": "str25"}

# ★TF 任务枚举（手册 6.1.1.1，实测验证）
TF_MISSION = {
    1: "AIRCOMBAT", 2: "SURFACE", 3: "BOMBARDMENT", 4: "FASTTRANSPORT",
    5: "TRANSPORT", 6: "REPLENISHMENT", 7: "MINELAYING", 8: "SUBPATROL",
    9: "SUBMINELAYING", 10: "SUBTRANSPORT", 11: "CARGO",
    13: "AIRTRANSPORT", 14: "CVESCORT", 15: "AMPHIB", 16: "ASWCOMBAT",
    17: "PTBOAT", 18: "TANKER", 19: "MINESWEEPING", 20: "LANDINGCRAFT",
    22: "SUPPORT", 23: "LOCALMINESWEEPING", 25: "ESCORT",
}
TF_MISSION_R = {v: k for k, v in TF_MISSION.items()}


# ★航空任务码表（2026-10-19 静态反汇编 + 过回合实测确认）
# 来源：内存中的任务名指针表 @0x85406c（12 项）
# 验证：码 8/9/10/12/13 过回합保留；11 需配合目标格
AG_MISSION = {
    1:  "AIRFIELD_ATTACK",
    2:  "PORT_ATTACK",
    3:  "NAVAL_ATTACK",
    4:  "GROUND_ATTACK",
    5:  "SWEEP",
    6:  "ESCORT",
    7:  "RECON",
    8:  "NAVAL_SEARCH",
    9:  "ASW_PATROL",
    10: "SUPPLY_TRANSPORT",
    11: "TROOP_TRANSPORT",
    16: "TRAINING",
}
AG_MISSION_R = {v: k for k, v in AG_MISSION.items()}



def game_pid():
    """找当前实例的游戏进程。

    ★ 实例选择必须用 WITP_INSTANCE 指定的 WINEPREFIX 精确匹配，
      不能用 "wine-witp" 模糊匹配 —— 同一台机器上可能同时跑着
      主实例(:98, /root/.wine-witp) 和测试实例(:97, /root/.wine-witp-mcp)，
      模糊匹配会选错，导致读写到另一个实例的内存。
    """
    import os as _os
    # Separate game-process routing from the prefix used for helper DLLs.
    # WITP_INSTANCE is authoritative when it contains a Wine drive_c path;
    # WITP_WINEPREFIX may intentionally point at a different helper prefix.
    want = _os.environ.get("WITP_GAME_WINEPREFIX", "")
    if not want:
        inst = _os.environ.get("WITP_INSTANCE", "")
        for marker in ("/drive_c", "/game"):
            if marker in inst:
                want = inst.split(marker)[0]
                break
    if not want:
        want = _os.environ.get("WITP_WINEPREFIX") or _os.environ.get("WINEPREFIX") or ""
    cands = []
    for c in _os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            env = open(f"/proc/{c}/environ", "rb").read()
        except OSError:
            continue
        if b"WINEPREFIX=" not in env:
            continue
        if want:
            pref = b"WINEPREFIX=" + want.encode() + b"\0"
            if pref not in env:
                continue
        else:
            if b"wine-witp" not in env:
                continue
        cands.append(int(c))
    if not cands:
        return None
    return max(cands)


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


def addrs(kind):
    """返回 [(标签, 地址)]，含镜像（若有）"""
    o = OBJECTS[kind]
    out = [("main", o["base"])]
    if o["mirror"]:
        out.append(("mirror", o["mirror"]))
    return out


def get(pid, kind, idx, field):
    o = OBJECTS[kind]
    off, t = FIELDS[kind][field]
    d = _read(pid, o["base"] + idx * o["sz"] + off, 40)
    if not d:
        return None
    if t.startswith("str"):
        n = int(t[3:])
        return d[:n].split(b"\0")[0].decode("ascii", "replace")
    return struct.unpack_from(FMT[t], d, 0)[0]


def set_field(pid, kind, idx, field, value):
    """写字段。有镜像的类自动两份都写。"""
    o = OBJECTS[kind]
    off, t = FIELDS[kind][field]
    if t.startswith("str"):
        raise ValueError("名称字段不建议写")
    results = {}
    all_ok = True
    for label, base in addrs(kind):
        a = base + idx * o["sz"] + off
        ok = _write(pid, a, struct.pack(FMT[t], value))
        back = get_from(pid, base, kind, idx, field)
        results[label] = {"addr": hex(a), "new": back, "ok": ok}
        if back != value:
            all_ok = False
    return all_ok, results


def get_from(pid, base, kind, idx, field):
    o = OBJECTS[kind]
    off, t = FIELDS[kind][field]
    d = _read(pid, base + idx * o["sz"] + off, 40)
    if not d:
        return None
    if t.startswith("str"):
        n = int(t[3:])
        return d[:n].split(b"\0")[0].decode("ascii", "replace")
    return struct.unpack_from(FMT[t], d, 0)[0]


def occupied(pid, kind):
    """列出有内容的索引。判据：名称非空 或 关键字段非零。"""
    o = OBJECTS[kind]
    out = []
    total = o["ulen"] // o["sz"]
    for i in range(1, total):
        if kind in ("ship", "leader", "shipclass", "aircraft", "device"):
            d = _read(pid, o["base"] + i * o["sz"], 40)
            if not d:
                continue
            nm = d.split(b"\0")[0]
            if len(nm) >= 2 and all(32 <= c < 127 for c in nm):
                out.append(i)
        elif kind == "pilot":
            d = _read(pid, o["base"] + i * o["sz"], 12)
            if d and struct.unpack_from("<I", d, 4)[0]:
                out.append(i)
        elif kind == "location":
            # 基地：坐标有效（非 0、非 65535）即算占用
            d = _read(pid, o["base"] + i * o["sz"], 40)
            if d:
                x = struct.unpack_from("<H", d, 36)[0]
                y = struct.unpack_from("<H", d, 38)[0]
                if 0 < x < 250 and 0 < y < 250:
                    out.append(i)
        else:
            if get(pid, kind, i, "flagship" if kind == "taskforce" else "maxPlanes"):
                out.append(i)
    return out


def find_by_name(pid, kind, name):
    """按名称找索引（名称唯一）。"""
    o = OBJECTS[kind]
    total = o["ulen"] // o["sz"]
    nlen = int(FIELDS[kind]["name"][1][3:])
    for i in range(1, total):
        d = _read(pid, o["base"] + i * o["sz"], nlen)
        if d and d.split(b"\0")[0].decode("ascii", "replace") == name:
            return i
    return None


if __name__ == "__main__":
    pid = game_pid()
    if not pid:
        print("游戏未运行")
        sys.exit(1)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    kind = sys.argv[2] if len(sys.argv) > 2 else "ship"
    print(f"PID={pid}  对象={kind}  主基址={OBJECTS[kind]['base']:#x}")

    if cmd == "list":
        occ = occupied(pid, kind)
        print(f"占用 {len(occ)} 个")
        for i in occ[:20]:
            print(f"  [{i}] {get(pid,kind,i,'name')!r}")
    elif cmd == "show":
        i = int(sys.argv[3])
        for f in FIELDS[kind]:
            print(f"  {f:<16} = {get(pid,kind,i,f)}")
    elif cmd == "find":
        nm = sys.argv[3]
        print(f"索引 = {find_by_name(pid, kind, nm)}")
    elif cmd == "set":
        i, f, v = int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
        ok, res = set_field(pid, kind, i, f, v)
        print(f"{kind}[{i}].{f} = {v}: ok={ok}")
        for k, r in res.items():
            print(f"  {k}: {r}")
