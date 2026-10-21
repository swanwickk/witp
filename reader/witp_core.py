#!/usr/bin/env python3
"""witp_core.py — WitP-AE 存档「纯 Python」读层（不依赖游戏 DLL / Wine / 32 位解释器）

逆向依据见 pwsfile.py / witp_orders.py 顶部注释。结构体布局复用
pywitpaescraper/pwsdll.py 的 ctypes 定义（在 64 位下 sizeof 与 32 位一致，已核对）。

对外 API：
    load(save_path) -> GameState
    GameState.summary()            中文态势摘要（dict）
    GameState.tf(slot_or_flagship) 编队
    GameState.airgroups(...)       航空队
    GameState.bases(...)           基地
    GameState.ground_units(...)    地面部队
    GameState.ships(...)           舰船
"""
import ctypes
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "pywitpaescraper"))

from pwsfile import read_container          # noqa: E402
import pwsdll as P                          # noqa: E402

TF_SIZE = ctypes.sizeof(P.PWSTaskGroup)
AG_SIZE = ctypes.sizeof(P.PWSAirGroup)
LOC_SIZE = ctypes.sizeof(P.PWSLocation)
SHIP_SIZE = ctypes.sizeof(P.PWSShip)

MISSION_CN = {
    "AIRCOMBAT": "空战（航母编队）", "SURFACE": "水面战", "BOMBARDMENT": "炮击",
    "FASTTRANSPORT": "快速运输", "TRANSPORT": "运输", "REPLENISHMENT": "海上补给",
    "MINELAYING": "布雷", "SUBPATROL": "潜艇巡逻", "SUBMINELAYING": "潜艇布雷",
    "SUBTRANSPORT": "潜艇运输", "CARGO": "货运", "AIRTRANSPORT": "空运",
    "CVESCORT": "航母护航", "AMPHIB": "两栖登陆", "ASWCOMBAT": "反潜",
    "PTBOAT": "鱼雷艇", "TANKER": "油船", "MINESWEEPING": "扫雷",
    "LANDINGCRAFT": "登陆艇", "SUPPORT": "支援", "LOCALMINESWEEPING": "局部扫雷",
    "ESCORT": "护航",
}
MISSION_BY_CODE = {v.value: v.name for v in P.TaskForceMission}

# 航空队主任务码（实测映射：1=机场攻击 3=对海攻击 6=护航/CAP 8=海上搜索 9=反潜 16=侦察）
AIR_MISSION_CN = {
    1: "机场攻击", 2: "港口攻击", 3: "对海攻击", 4: "对地攻击", 5: "扫场",
    6: "护航/CAP", 7: "远程护航", 8: "海上搜索", 9: "反潜巡逻", 10: "补给运输",
    11: "城市攻击", 12: "训练", 13: "休整", 14: "夜间搜索", 16: "侦察",
}

NATION_CN = {
    "JAPAN": "日本", "IJARMY": "日本陆军", "IJNAVY": "日本海军",
    "USNAVY": "美国海军", "USARMY": "美国陆军", "USMARINES": "美国陆战队",
    "AUSTRALIAN": "澳大利亚", "NZ": "新西兰", "BRITISH": "英国",
    "DUTCH": "荷兰", "CHINESE": "中国", "SOVIET": "苏联",
}


def _cstr(raw):
    return raw.split(b"\x00")[0].decode("latin1", "replace").strip()


class GameState:
    def __init__(self, path):
        self.path = str(path)
        c = read_container(self.path)
        self.records = c["records"]
        # ★按**解压长度**建索引，而不是按 type。
        # 实测：同一份存档被游戏重写后，航空队记录会从
        #   (id=65556,type=20) 变成 (id=1114401,type=33)，
        # 但解压长度恒为 20400680。只按 type 取会在某些存档上 KeyError。
        SIZE_KEY = {
            3000: "header", 99696: "scenario",
            9280000: "ships", 9000000: "leaders",
            20400680: "airgroups", 21096000: "locations",
            2224000: "taskgroups", 396000: "aircraft",
            472000: "devices", 1900000: "shipclasses",
        }
        self.by_type = {}
        for r in c["records"]:
            self.by_type.setdefault(r["type"], r)
        self.by_size = {}
        for r in c["records"]:
            key = SIZE_KEY.get(len(r["data"]))
            if key:
                self.by_size.setdefault(key, r)
        self._ships = None
        self._ags = None
        self._locs = None
        self._tfs = None

    def _blk(self, key):
        """按语义名取记录块（优先按解压长度，退回按 type 码）。"""
        r = self.by_size.get(key)
        if r is None:
            legacy = {"ships": 8, "airgroups": 20, "locations": 19,
                      "taskgroups": 70, "leaders": 21}.get(key)
            r = self.by_type.get(legacy) if legacy is not None else None
        if r is None:
            raise KeyError(f"存档缺少 {key} 记录（长度索引与 type 索引都没命中）")
        return r["data"]

    # ---------- 头部 / 回合 ----------
    @property
    def header(self):
        # 存档头记录 id 因存档类型而变（Autosave=550 / 手动存档=38 / PBEM=其它），
        # 但类型码固定为 38、解压后 3000 字节。
        r = next((x for x in self.records if x["type"] == 38 and x["u_len"] == 3000), None)
        return _cstr(r["data"]) if r else ""

    @property
    def scenario(self):
        r = next((x for x in self.records if len(x["data"]) == 99696), None)
        if not r:
            return ""
        i = r["data"].find(b"The ")
        return _cstr(r["data"][i:i + 80]) if i >= 0 else ""

    @property
    def turn(self):
        r = next((x for x in self.records if len(x["data"]) == 99696), None)
        if not r:
            return 0
        return struct.unpack_from("<H", r["data"], 30)[0]

    @property
    def vp(self):
        r = next((x for x in self.records if len(x["data"]) == 99696), None)
        if not r:
            return {}
        return {"japan": struct.unpack_from("<i", r["data"], 112)[0],
                "allied": struct.unpack_from("<i", r["data"], 120)[0]}

    # ---------- 编队 ----------
    @property
    def tfs(self):
        if self._tfs is None:
            blk = self._blk("taskgroups")
            out = []
            for slot in range(len(blk) // TF_SIZE):
                t = P.PWSTaskGroup.from_buffer_copy(blk[slot * TF_SIZE:(slot + 1) * TF_SIZE])
                if t.tfFlagship <= 0:
                    continue
                # 航路点：40 个 (u16 x,u16 y)，有效点数在 offset 320
                #   118 起点，(u16 x,u16 y) 每点；首点=当前格，末点=路径终点
                #   320 有效点数（游戏改写目的地时会同步更新）
                _n = struct.unpack_from("<H", blk, slot * TF_SIZE + 320)[0]
                _n = min(max(_n, 0), 40)
                wps = []
                for i in range(_n):
                    x, y = struct.unpack_from("<HH", blk,
                                              slot * TF_SIZE + 118 + i * 4)
                    if x == 0 and y == 0:
                        break
                    wps.append((x, y))
                # 目的基地 ID(offset 58)：引擎结算用的**命令源**；0=无基地目的地
                dest_base = struct.unpack_from("<H", blk, slot * TF_SIZE + 58)[0]
                mission = t.tfMission[0] if isinstance(t.tfMission, bytes) else t.tfMission
                name = MISSION_BY_CODE.get(mission, "?")
                out.append({
                    "slot": slot, "flagship_id": t.tfFlagship,
                    "home_port": t.tfHomePort, "mission_code": mission,
                    "mission": name, "mission_cn": MISSION_CN.get(name, name),
                    "speed": t.tfSpeed[0] if isinstance(t.tfSpeed, bytes) else t.tfSpeed,
                    "endurance": t.tfEndurance,
                    "waypoints": wps,
                    "position": wps[0] if wps else None,
                    "dest_base": dest_base or None,
                    "destination": wps[-1] if len(wps) > 1 else None,
                })
            self._tfs = out
        return self._tfs

    # ---------- 舰船 ----------
    @property
    def ships(self):
        if self._ships is None:
            blk = self._blk("ships")
            out = []
            for i in range(len(blk) // SHIP_SIZE):
                s = P.PWSShip.from_buffer_copy(blk[i * SHIP_SIZE:(i + 1) * SHIP_SIZE])
                nm = _cstr(s.name)
                if not nm:
                    continue
                out.append({
                    "id": i, "name": nm, "class_id": s.shipClass,
                    "tf": s.shipTF, "base": s.shipBase,
                    "sys_dmg": s.shipSysDmg[0], "float_dmg": s.shipFloatDmg[0],
                    "fire_dmg": s.shipFireDmg[0], "engine_dmg": s.shipEngineDmg[0],
                    "fuel": s.shipFuelLoaded, "supply": s.shipSupplyLoaded,
                    "ops": s.shipOps,
                    "repair_priority": s.shipRepairPriority[0],
                    "repair_mode": s.shipRepairMode[0],
                    "upgrade": s.shipUpgrade[0],
                })
            self._ships = out
        return self._ships

    def tf_ships(self, flagship_id):
        """按旗舰定位编队：先用 shipTF 字段把舰船分组（shipTF 是编队槽号+14000 之类，实测不可靠），
        退化为按地理位置+旗舰名匹配。这里返回与旗舰同 TF 字段的舰船。"""
        fl = next((s for s in self.ships if s["id"] == flagship_id), None)
        if not fl:
            return []
        return [s for s in self.ships if s["tf"] == fl["tf"] and fl["tf"]]

    # ---------- 航空队 ----------
    @property
    def airgroups(self):
        if self._ags is None:
            blk = self._blk("airgroups")
            out = []
            for i in range(len(blk) // AG_SIZE):
                a = P.PWSAirGroup.from_buffer_copy(blk[i * AG_SIZE:(i + 1) * AG_SIZE])
                nm = _cstr(a.groupname)
                if not nm:
                    continue
                out.append({
                    "slot": i, "name": nm, "base_id": a.baseID,
                    "primary_code": a.primaryMission,
                    "primary": AIR_MISSION_CN.get(a.primaryMission, str(a.primaryMission)),
                    "secondary_code": a.secondaryMission,
                    "target": (a.targetX, a.targetY) if (a.targetX or a.targetY) else None,
                    "cap": a.acPctCAP[0], "lrcap": a.acPctLRCAP[0],
                    "asw": a.acPctASW[0], "search": a.acPctSearch[0],
                    "train": a.acPctTrain[0], "rest": a.acPctRest[0],
                    "ready": a.acReady[0], "damaged": a.acDamaged[0],
                    "max": a.maxplanes[0],
                    "morale": a.pilotMorale[0], "exp": a.pilotExp[0],
                    "range": a.acRange, "alt": a.acAlt,
                    "search_arc": (a.acSearchNavStart[0], a.acSearchNavEnd[0]),
                    "asw_arc": (a.acSearchASWStart[0], a.acSearchASWEnd[0]),
                })
            self._ags = out
        return self._ags

    # ---------- 位置（基地 + 地面部队 + 指挥部）----------
    @property
    def locations(self):
        if self._locs is None:
            blk = self._blk("locations")
            out = []
            for i in range(len(blk) // LOC_SIZE):
                L = P.PWSLocation.from_buffer_copy(blk[i * LOC_SIZE:(i + 1) * LOC_SIZE])
                nm = _cstr(L.name)
                if not nm:
                    continue
                out.append({
                    "slot": i, "name": nm, "type": L.type, "owner": L.owner,
                    "x": L.X, "y": L.Y,
                    "port": L.port, "airfield": L.airfield, "fort": L.fort,
                    "port_sps": L.portSPS, "airfield_sps": L.airfieldSPS,
                    "port_expand": L.portExpand, "airfield_expand": L.airfieldExpand,
                    "fort_expand": L.fortExpand,
                    "supply": L.supply, "fuel": L.fuel, "resources": L.resources,
                    "oil": L.oil, "supply_needed": L.supplyNeeded,
                    "airgroup_stack": L.airgroupStack, "aircraft_stack": L.aircraftStack,
                    "av_squads": L.avSquads, "support_req": L.supportReq,
                    "support_total": L.supportTotal,
                    "exp": L.exp[0], "morale": L.morale[0], "fatigue": L.fatigue[0],
                    "march_dir": L.marchDir[0], "march_len": L.marchLen[0],
                    "dest": (L.destX, L.destY) if (L.destX or L.destY) else None,
                    "prep": L.prepPercent, "combat_mode": L.combatMode[0],
                    "prep_target": L.locNear,
                    "detection": L.detectionLevel[0],
                    "port_dmg": L.portDmg, "af_dmg": L.airfieldDmg,
                    "runway_dmg": L.runwayDmg,
                })
            self._locs = out
        return self._locs

    def bases(self):
        return [l for l in self.locations if l["type"] in (1, 5, 0) and l["x"] != 65535]

    def ground_units(self):
        # 地面部队记录与基地共用 PWSLocation 布局，但港口/机场/补给等字段对地面部队无意义
        # （实测会给出假值），只暴露行军相关字段。
        keys = ("slot", "name", "type", "owner", "x", "y", "exp", "morale",
                "fatigue", "march_dir", "march_len", "dest", "prep",
                "prep_target", "combat_mode", "detection")
        names = {0: "defend", 1: "bombardment", 2: "deliberate", 3: "shock"}
        rows = []
        for l in self.locations:
            if l["type"] in (0, 1, 4, 5, 12) or l["x"] == 65535:
                continue
            row = {k: l[k] for k in keys}
            row["combat_order"] = names.get(l["combat_mode"], str(l["combat_mode"]))
            rows.append(row)
        return rows

    def hqs(self):
        return [l for l in self.locations if l["type"] == 4]

    # ---------- 中文摘要 ----------
    def summary(self, side="ALLIED"):
        vp = self.vp
        return {
            "save": self.path,
            "header": self.header,
            "scenario": self.scenario,
            "turn": self.turn,
            "vp": vp,
            "counts": {
                "taskforces": len(self.tfs), "ships": len(self.ships),
                "airgroups": len(self.airgroups), "bases": len(self.bases()),
                "ground_units": len(self.ground_units()),
            },
            "sides": {
                "japan": sum(1 for l in self.locations if l["type"] == 1 and l["owner"] == 0),
                "allied": sum(1 for l in self.locations if l["type"] == 1 and l["owner"] == 1),
            },
        }

    def brief_cn(self):
        s = self.summary()
        lines = [
            f"存档：{Path(self.path).name}　{self.header}",
            f"剧本：{s['scenario']}　回合：{s['turn']}",
            f"比分：日军 {s['vp'].get('japan')} / 盟军 {s['vp'].get('allied')}",
            f"编队 {s['counts']['taskforces']}　舰船 {s['counts']['ships']}　"
            f"航空队 {s['counts']['airgroups']}　基地 {s['counts']['bases']}　"
            f"地面部队 {s['counts']['ground_units']}",
            "",
            "编队（槽/旗舰/任务/位置→目的地）：",
        ]
        for t in self.tfs:
            pos = t["position"] or ("?", "?")
            dst = t["destination"] or pos
            lines.append(f"  #{t['slot']:<3d} 旗舰 {t['flagship_id']:<6d} "
                         f"{t['mission_cn']:<10s} {pos} → {dst}")
        return "\n".join(lines)


def load(path):
    return GameState(path)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    g = load(a.save)
    if a.json:
        import json
        print(json.dumps(g.summary(), ensure_ascii=False, indent=1))
    else:
        print(g.brief_cn())
