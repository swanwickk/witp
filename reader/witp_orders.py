#!/usr/bin/env python3
"""witp_orders.py — WitP-AE 存档「命令层」逆向读写（纯 Python，不依赖游戏进程/DLL）

数据模型（实测，英文 1108r9，2026-10-17）：
  .pws = gzip( [u16 inst][u16 type][u32 A][u32 B][zlib(定长结构体数组)] * N )
  · type = 记录头第 3-4 字节低 4 位；大记录（type 1/8/19/20/21/22/27/31/32）的 A/B
    是引擎侧校验字段，**必须原样保留**；小记录（id<1000）A/B = 解压/压缩长度。
  · **每条记录的压缩流长度是引擎硬校验项**：改写数据后压缩长度变化 →
    pwsdll 报 "Restore size larger than expected" 并中断读档。
    → pwspack.compress_to_length() 用「空存储块填充」把压缩流长度精确调回原值。

可写命令字段（偏移取自 pywitpaescraper/pwsdll.py 的 ctypes 定义，已用游戏 DLL 回读验证）：
  编队 PWSTaskGroup(556B)
      44  tfFlagship(i32)   54  tfHomePort(u16)
      118 航路点数组：8 × (u16 x, u16 y)；首点=当前格，末点=目的地；空点=(0,0)
      349 tfMission(u8)     354 tfSpeed(u8)
  航空队 PWSAirGroup(680B)
      40  baseID(u16)   44 primaryMission(u16)  46 secondaryMission(u16)
      48  targetID(u16) 192 targetX(u16) 196 targetY(u16)
      560 acPctCAP  561 acPctLRCAP  562 acPctASW  563 acPctSearch
      564 acPctTrain 565 acPctRest   （u8 百分比）
  地面部队/基地 PWSLocation(1172B)
      36 X(u16) 38 Y(u16)  104 prepPercent(u16) 110 combatMode(u8)
      651 marchDir(u8) 652 marchLen(u8) 662 destX(u16) 664 destY(u16)
"""
import ctypes
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "pywitpaescraper"))

from pwsfile import read_container                     # noqa: E402
import pwspack                                          # noqa: E402
import pwsdll as P                                      # noqa: E402

TF_SIZE = ctypes.sizeof(P.PWSTaskGroup)                 # 556
AG_SIZE = ctypes.sizeof(P.PWSAirGroup)                  # 680
LOC_SIZE = ctypes.sizeof(P.PWSLocation)                 # 1172
SHIP_SIZE = ctypes.sizeof(P.PWSShip)                    # 464

TF_BLOCK = TF_SIZE * 4000                               # 2224000
AG_BLOCK = AG_SIZE * 30001
LOC_BLOCK = LOC_SIZE * 18000
SHIP_BLOCK = SHIP_SIZE * 20000

# PWSTaskGroup(556B) 命令字段偏移 —— 全部经引擎回读 + 存档差分双重验证
#   destBase=58  目的基地 Location ID（u16）；0 = 无基地目的地（纯海域航路）
#   wp=118       航路点数组起点，**40 个 (u16 x,u16 y) = 160 字节**（不是 8 个！）
#                首点=当前格，末非零点=路径终点；空点=(0,0)
#   mission=349  任务码（见 TaskForceMission）
#   speed=354    速度档 0=Cruise 1=Full 2=Max
TF_OFF = dict(flagship=44, home=54, destBase=58, wp=118, wpMax=40,
              wpCount=320, wpAlloc=322, mission=349, speed=354,
              # TFRouting 0=Normal 1=Safest 2=Safer 3=Direct
              # 实证：GUI 设 Safest → off369 由 0 变 1；改回 0 → 界面
              # "Safest Route Ordered" 文本消失
              routing=369,
              # Threat Tolerance 0=Normal 1=Low 2=High 3=Absolute
              # 实证：GUI 点 High → off448 由 0 变 2；置 3 → 界面 Absolute 绿色高亮
              tolerance=448,
              maxReact=355,
              # 装载/卸载状态（手册 6.3.3）：0=空闲 1=正在装载 99=空闲(备用)
              loadState=350)
AG_OFF = dict(baseID=40, reinforceBaseID=42, primary=44, secondary=46, targetID=48,
              targetX=192, targetY=196,
              # 撤编日期（YYMMDD 编码，如 440710=1944-07-10）：引擎排定，只读
              withdraw=392, maxPlanes=245, upgradeTo=308,
              agrUpgrade=370, pctCAP=560, pctLRCAP=561,
              pctASW=562, pctSearch=563, pctTrain=564, pctRest=565,
              alt=212, navArcStart=630, navArcEnd=631,
              aswArcStart=628, aswArcEnd=629)
# PWSLocation(1172B) —— 命令字段
#   准备目标用 prepTarget(102)，行军目的地用 destX/destY(662/664)，两者不同：
#   · prepTarget 是 Location ID（基地），配 prep(104) 表示准备进度
#   · destX/destY 是六角坐标（行军）
#   实测：4th Fleet prep=100 prepTarget=981(Port Moresby)，dest=(0,0) —— 只做准备不行军。
LOC_OFF = dict(
    X=36, Y=38,
    prepTarget=102,      # u16 准备目标基地 Location ID（Future Objective，手册 8.2.1.4）
    prep=104,            # u16 准备度 %（对 prepTarget 的完成度）
    combatMode=110,      # u8  战斗命令 0=defend 1=bombardment 2=deliberate 3=shock
    portExpand=424, airfieldExpand=428, fortExpand=432,   # u16 扩建指令 0=停
    operationsMode=906,   # u16 Operations Mode（手册 8.2.1.1）
                          # 实证：GUI 把 11th Air Fleet 由 Combat 改 Move → off906 0→1；
                          #       改 4 → 界面 OpMode 列显示 Rest
    marchDir=651, marchLen=652,                            # u8  行军方向/长度
    destX=662, destY=664,                                  # u16 行军目的地（手册 8.3.1）
)


# PWSShip(464B) —— 修理/升级命令（手册 14.2.2）
SHIP_OFF = dict(
    repairPriority=338,   # u8 修理优先级
    repairMode=339,       # u8 修理模式（Shipyard/RepairShip/Pierside/…）
    upgrade=365,          # u8 升级开关
)


# 手册 8.2.1.2 Combat Orders 顺序 → 存档 combatMode(offset 110) 取值
# 实测证据：主实例 wpae012→wpae013 只做过界面 ground-order（Shock），
#   144th Infantry 与 Kure 3rd 的 offset110 均由 0 → 3，与枚举顺序一致。
COMBAT_ORDERS = {"defend": 0, "bombardment": 1, "deliberate": 2, "shock": 3}
COMBAT_ORDER_NAMES = {v: k for k, v in COMBAT_ORDERS.items()}

MISSION_NAMES = {v.value: v.name for v in P.TaskForceMission}


class Save:
    """一份存档的可读写视图（只改内存，save() 才落盘）。"""

    def __init__(self, path):
        self.path = Path(path)
        self.c = read_container(self.path)
        self.records = [{"id": r["id"], "f2": r["f2"], "f3": r["f3"],
                         "extra": r["extra"], "data": r["data"],
                         "z_len": r["z_len"], "u_len": r["u_len"],
                         "comp": r["comp"], "filler_offsets": None}
                        for r in self.c["records"]]

    # ---- 记录定位 ----
    def rec(self, size):
        for r in self.records:
            if len(r["data"]) == size:
                return r
        return None

    @property
    def tf(self):
        return self.rec(TF_BLOCK)

    @property
    def ag(self):
        return self.rec(AG_BLOCK)

    @property
    def loc(self):
        return self.rec(LOC_BLOCK)

    @property
    def ships(self):
        return self.rec(SHIP_BLOCK)

    # ---- 读 ----
    def turn_info(self):
        hdr = next((r for r in self.records if r["id"] < 1000 and len(r["data"]) == 3000),
                   None)
        comment = ""
        if hdr:
            comment = hdr["data"].split(b"\x00")[0].decode("latin1", "replace").strip()
        scen = next((r for r in self.records if len(r["data"]) == 99696), None)
        name = ""
        if scen:
            i = scen["data"].find(b"The ")
            if i >= 0:
                name = scen["data"][i:i + 60].split(b"\x00")[0].decode("latin1")
        return {"comment": comment, "scenario": name}

    def tf_row(self, slot):
        b = self.tf["data"][slot * TF_SIZE:(slot + 1) * TF_SIZE]
        mission = b[TF_OFF["mission"]]
        return dict(slot=slot,
                    flagship=struct.unpack_from("<i", b, TF_OFF["flagship"])[0],
                    home=struct.unpack_from("<H", b, TF_OFF["home"])[0],
                    mission=mission,
                    mission_name=MISSION_NAMES.get(mission, "?"),
                    speed=b[TF_OFF["speed"]],
                    waypoints=self.tf_waypoints(slot))

    def set_tf_mission(self, slot, mission):
        """写 TF 任务码（TaskForceMission）。"""
        off = slot * TF_SIZE + TF_OFF["mission"]
        old = self.tf["data"][off]
        blk = bytearray(self.tf["data"])
        blk[off] = int(mission) & 0xFF
        self.tf["data"] = bytes(blk)
        return old

    # ── 航路点/目的地 ────────────────────────────────────────────
    # 语义（经"游戏自己设目的地"的存档差分确证，见 wpae001 vs wpae009）：
    #   118      路径点数组起点，(u16 x,u16 y) × 40
    #   320(u16) 路径**有效点数**（游戏改写目的地时会同步更新）
    #   322(u16) 数组容量（恒为 40 左右，勿动）
    #   58 (u16) 目的**基地** Location ID；目的地是非基地格时 = 0
    # ★关键：destBase 与路径点数必须一起改。只改 destBase 而留着旧路径，
    #   引擎会认为"路径已存在"而沿用旧终点（实测 wpae008 被覆盖回莫港）。

    def tf_waypoints(self, slot):
        """读有效路径点（按 offset 320 的有效点数截断）。"""
        blk = self.tf["data"]
        base = slot * TF_SIZE
        n = struct.unpack_from("<H", blk, base + TF_OFF["wpCount"])[0]
        n = min(max(n, 0), TF_OFF["wpMax"])
        pts = []
        for i in range(n):
            x, y = struct.unpack_from("<HH", blk, base + TF_OFF["wp"] + i * 4)
            pts.append((x, y))
        return pts

    def tf_dest_base(self, slot):
        """读目的基地 Location ID（0 = 目的地是非基地格）。"""
        return struct.unpack_from("<H", self.tf["data"],
                                  slot * TF_SIZE + TF_OFF["destBase"])[0]

    def set_tf_destination(self, slot, x, y, path=None, dest_base=None,
                           wp_alloc=None):
        """设置 TF 目的地 (x,y)。

        path: 完整路径点列表（含起点与终点）。给 None 时用 [(起点),(x,y)] 两点直线，
              这是最保守的写法——引擎会在下次结算时自行展开成实际航线。
        dest_base: 目标若是基地则传其 Location ID，否则传 0/None。
        """
        blk = bytearray(self.tf["data"])
        base = slot * TF_SIZE
        old = {"destBase": self.tf_dest_base(slot),
               "points": self.tf_waypoints(slot)}
        if path is None:
            cur = self.tf_waypoints(slot)
            start = cur[0] if cur else (x, y)
            path = [start] if start == (x, y) else [start, (x, y)]
        path = list(path)[:TF_OFF["wpMax"]]
        off = base + TF_OFF["wp"]
        # ★只写 len(path) 个点，**不动**其后的旧字节**。
        # 游戏自己设目的地时也是这样：有效点数 wpCount 之后全是上一版路径的残留，
        # 引擎只认前 wpCount 点。清尾会让数据熵变化、压缩长度更难回填，且无必要。
        for i, (px, py) in enumerate(path):
            struct.pack_into("<HH", blk, off + i * 4, px, py)
        # 320 = 有效点数；322 = 路径缓冲区已分配长度（游戏会同步收缩）。
        # 只改 320 而留着旧 322，引擎会按旧缓冲长度重算、把路径覆盖回去
        #（实测：322 仍为 36 时界面回退成旧的 Port Moresby 98,130）。
        struct.pack_into("<H", blk, base + TF_OFF["wpCount"], len(path))
        struct.pack_into("<H", blk, base + TF_OFF["wpAlloc"],
                         int(wp_alloc if wp_alloc is not None else len(path)))
        struct.pack_into("<H", blk, base + TF_OFF["destBase"],
                         int(dest_base or 0) & 0xFFFF)
        self.tf["data"] = bytes(blk)
        return {"old": old,
                "new": {"destBase": int(dest_base or 0), "points": path}}

    def set_ship_repair(self, ship_id, priority=None, mode=None, upgrade=None):
        """设置舰船修理优先级/模式/升级（手册 14.2.2）。

        ship_id: 舰船记录槽号（witp_core ships() 的 id 字段）
        priority: 修理优先级（1=Lowest … 4=Critical，实测默认 1）
        mode:     修理模式（0=默认/自动，其余见手册 14.2.3）
        upgrade:  是否允许升级 0/1
        """
        blk = bytearray(self.ships["data"])
        base = ship_id * SHIP_SIZE
        changes = {}
        for key, val in (("repairPriority", priority), ("repairMode", mode),
                         ("upgrade", upgrade)):
            if val is None:
                continue
            off = base + SHIP_OFF[key]
            old = blk[off]
            blk[off] = int(val) & 0xFF
            changes[key] = (old, val)
        self.ships["data"] = bytes(blk)
        return changes

    # ★撤回★ 早前把 Loc 槽14007 off685 当成 max_react，是**错误推论**：
    #   off685=5 时界面恰好显示 MaxReact:5，但写入 685=3 后界面仍显示 0，
    #   且游戏载入未修改该字节 ⇒ 685 不是 MaxReact。不要再写它。
    # Loc 表 14001-14030 确实是 TF 镜像记录（带名字），但命令字段位置仍待标定。

    def set_tf_routing(self, slot, routing=None, tolerance=None, max_react=None):
        """设置 TF 路由安全等级 / 威胁容忍度（手册 6.1.2.1.2）。

        routing:   0=Normal 1=Safest 2=Safer 3=Direct
        tolerance: 0=Normal 1=Low 2=High 3=Absolute
        两者均在 PWSTaskGroup(556B)，已实证。
        """
        out = {}
        if routing is None and tolerance is None and max_react is None:
            return out
        blk = bytearray(self.tf["data"])
        base = slot * TF_SIZE
        if routing is not None:
            old = blk[base + TF_OFF["routing"]]
            blk[base + TF_OFF["routing"]] = int(routing) & 0xFF
            out["routing"] = (old, routing)
        if tolerance is not None:
            old = blk[base + TF_OFF["tolerance"]]
            blk[base + TF_OFF["tolerance"]] = int(tolerance) & 0xFF
            out["tolerance"] = (old, tolerance)
        if max_react is not None:
            # 实证：GUI 把 MaxReact 0→6 后，PWSTaskGroup off355 由 0 变 6；
            # 改回 2 → 界面显示 Max React: 2
            old = blk[base + TF_OFF["maxReact"]]
            blk[base + TF_OFF["maxReact"]] = int(max_react) & 0xFF
            out["max_react"] = (old, max_react)
        self.tf["data"] = bytes(blk)
        return out

    def set_ag(self, slot, **kw):
        blk = bytearray(self.ag["data"])
        base = slot * AG_SIZE
        changes = {}
        # u8 字段（其余为 u16）
        # 只有这些是 u8；alt(212) 是 u16，不能放进来
        AG_U8 = {"pctCAP", "pctLRCAP", "pctASW", "pctSearch", "pctTrain",
                 "pctRest", "navArcStart", "navArcEnd",
                 "aswArcStart", "aswArcEnd", "maxPlanes", "upgradeTo",
                 "agrUpgrade"}
        for k, v in kw.items():
            if k not in AG_OFF or v is None:
                continue
            off = base + AG_OFF[k]
            if k in AG_U8:
                old = blk[off]
                blk[off] = int(v) & 0xFF
            else:
                old = struct.unpack_from("<H", blk, off)[0]
                struct.pack_into("<H", blk, off, int(v) & 0xFFFF)
            changes[k] = (old, v)
        self.ag["data"] = bytes(blk)
        return changes

    def set_tf_load(self, slot, action):
        """TF 装载/卸载（手册 6.3.3）。off350。

        action: "load" / "unload" / "stop" → 写 1 / 2 / 0
        实证：GUI 点 Load Supplies 后 off350 由 99 变 1，界面显示
        "loading supplies" 且出现 "Cancel Load Supplies"；改回 0 后
        Cargo Status 恢复 idle。
        """
        codes = {"stop": 0, "idle": 0, "load": 1, "unload": 2}
        k = str(action).lower()
        if k not in codes:
            raise ValueError(f"action 需为 {sorted(codes)}")
        blk = bytearray(self.tf["data"])
        off = slot * TF_SIZE + TF_OFF["loadState"]
        old = blk[off]
        blk[off] = codes[k]
        self.tf["data"] = bytes(blk)
        return {"loadState": (old, codes[k])}

    def set_ship_conversion(self, ship_id, convert=None, delay=None):
        """舰船改装（手册 14.1.2 Conversions）。

        convert: shipTempAPConv@341（u8，1=转换为 AP 等临时改装）
        delay:   shipConversionDelay@344（u16，改装剩余天数）
        """
        blk = bytearray(self.ships["data"])
        base = ship_id * SHIP_SIZE
        out = {}
        if convert is not None:
            old = blk[base + 341]
            blk[base + 341] = int(convert) & 0xFF
            out["tempAPConv"] = (old, convert)
        if delay is not None:
            old = struct.unpack_from("<H", blk, base + 344)[0]
            struct.pack_into("<H", blk, base + 344, int(delay) & 0xFFFF)
            out["conversionDelay"] = (old, delay)
        self.ships["data"] = bytes(blk)
        return out

    def set_ag_resize(self, slot, max_planes):
        """航空队编制数 Resize（手册 7.3）。maxPlanes@245。

        实证：EI-1 Daitai 19→24 后，CV Shokaku 舰载机面板显示
        "19 (3) x A6M2 Zero (24)"，括号内编制数变为 24。
        """
        return self.set_ag(slot, maxPlanes=max_planes)

    def set_ag_transfer(self, slot, target_base):
        """航空队转场（手册 7.2.3 Transfer）。

        写 reinforceBaseID(42) = 目标基地 Location ID。
        baseID(40) 保持不变，引擎据此判断"正在转场"（baseID != reinforceBaseID）。
        """
        return self.set_ag(slot, reinforceBaseID=target_base)

    def set_loc(self, slot, **kw):
        blk = bytearray(self.loc["data"])
        base = slot * LOC_SIZE
        changes = {}
        for k, v in kw.items():
            if k not in LOC_OFF or v is None:
                continue
            off = base + LOC_OFF[k]
            if k in ("combatMode", "marchDir", "marchLen"):
                old = blk[off]
                blk[off] = int(v) & 0xFF
            else:
                old = struct.unpack_from("<H", blk, off)[0]
                struct.pack_into("<H", blk, off, int(v) & 0xFFFF)
            changes[k] = (old, v)
        self.loc["data"] = bytes(blk)
        return changes

    def set_ground_order(self, slot, order=None, prep_target=None,
                         obj_x=None, obj_y=None, prep=None,
                         march_dir=None, march_len=None, operations_mode=None):
        """设置地面部队命令。

        order:     战斗命令 defend/bombardment/deliberate/shock（手册 8.2.1.2）
        prep_target: 准备目标基地 Location ID（手册 8.2.1.4 Future Objective）
        obj_x/y:   行军目的地六角格（手册 8.3.1）
        prep:      准备度 0-100（准备目标时的完成百分比）
        march_dir: 行军方向 0-8（手册 8.3.1 六角方向）
        march_len: 行军距离（格）
        任一参数为 None 表示不改。
        """
        kw = {}
        if order is not None:
            key = str(order).strip().lower()
            if key not in COMBAT_ORDERS:
                raise ValueError(f"未知战斗命令 {order}；可选 {sorted(COMBAT_ORDERS)}")
            kw["combatMode"] = COMBAT_ORDERS[key]
        if prep_target is not None:
            kw["prepTarget"] = prep_target
        if obj_x is not None:
            kw["destX"] = obj_x
        if obj_y is not None:
            kw["destY"] = obj_y
        if prep is not None:
            kw["prep"] = prep
        if march_dir is not None:
            kw["marchDir"] = march_dir
        if march_len is not None:
            kw["marchLen"] = march_len
        if operations_mode is not None:
            kw["operationsMode"] = operations_mode
        if not kw:
            raise ValueError("没有给出任何要修改的命令")
        return self.set_loc(slot, **kw)

    def set_base_build(self, slot, port_expand=None, airfield_expand=None,
                       fort_expand=None):
        """设置基地扩建指令（手册 9.4.2）：0=停止，1=扩建，其余值为施工进度%。"""
        return self.set_loc(slot, portExpand=port_expand,
                            airfieldExpand=airfield_expand,
                            fortExpand=fort_expand)

    # ---- 填充池（用于压缩长度微调；只写语义无关的空槽零区）----
    def _filler_for_tf(self):
        blk = self.tf["data"]
        offs = []
        for slot in range(len(blk) // TF_SIZE):
            if struct.unpack_from("<i", blk, slot * TF_SIZE + TF_OFF["flagship"])[0] > 0:
                continue
            base = slot * TF_SIZE
            offs.extend(range(base, base + TF_SIZE))
        return offs

    def _filler_for_loc(self):
        blk = self.loc["data"]
        offs = []
        for slot in range(len(blk) // LOC_SIZE):
            base = slot * LOC_SIZE
            if blk[base] != 0:          # 有名字 = 在用，跳过
                continue
            offs.extend(range(base, base + LOC_SIZE))
        return offs

    def _filler_for_ag(self):
        blk = self.ag["data"]
        offs = []
        for slot in range(len(blk) // AG_SIZE):
            base = slot * AG_SIZE
            if blk[base] != 0:
                continue
            offs.extend(range(base, base + AG_SIZE))
        return offs

    # ---- 落盘 ----
    def save(self, out_path):
        """写档。

        ★2026-10-18 更正★ 引擎**不校验压缩流长度**，只要求容器头 f3 与实际压缩流一致。
        实测：70 记录压缩长度 3458→3636（+178）后，原版 pwsdll.dll 与游戏本体均正常读档。
        因此现在默认 allow_len_change=True：先尝试回填（字节级一致最保险），
        回填失败就直接压缩并同步 f3 —— 不再因为"长度对不上"而失败。
        """
        for r in self.records:
            n = len(r["data"])
            if n == TF_BLOCK:
                r["filler_offsets"] = self._filler_for_tf()
                r["kind"] = "tf"
            elif n == AG_BLOCK:
                r["filler_offsets"] = self._filler_for_ag()
                r["kind"] = "ag"
            elif n == LOC_BLOCK:
                r["filler_offsets"] = self._filler_for_loc()
                r["kind"] = "loc"
            elif n == SHIP_BLOCK:
                r["kind"] = "ship"
        return pwspack.pack_container(self.records, out_path, allow_len_change=True)


def _cli():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--tf-list", action="store_true")
    ap.add_argument("--ag-list", action="store_true")
    ap.add_argument("--ships", action="store_true")
    ap.add_argument("--set-mission", nargs=2, metavar=("SLOT", "CODE"))
    ap.add_argument("--set-dest", nargs=3, metavar=("SLOT", "X", "Y"))
    ap.add_argument("--out")
    a = ap.parse_args()
    s = Save(a.save)
    print(s.turn_info())
    if a.tf_list:
        for r in s.tf_list():
            print(r)
    if a.ag_list:
        for r in s.ag_rows()[:20]:
            print(r)
    if a.ships:
        for r in s.ship_rows()[:20]:
            print(r)
    if a.set_mission or a.set_dest:
        if a.set_mission:
            print("mission", s.set_tf_mission(int(a.set_mission[0]), int(a.set_mission[1])))
        if a.set_dest:
            print("dest", s.set_tf_destination(int(a.set_dest[0]),
                                               int(a.set_dest[1]), int(a.set_dest[2])))
        out = a.out or "/tmp/witp_orders_out.pws"
        print("saved", s.save(out), out)


if __name__ == "__main__":
    _cli()
