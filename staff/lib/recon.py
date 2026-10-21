"""
WitP-AE 侦察与航母邻近判定

指挥官指出的两条原则（本模块据此实现）：
1. **侦察不能靠运气**：十二局从未发现敌航母 = 侦察链有缺陷，必须
   ①有可执行的搜索命令（比例 + 搜索扇面），②搜索力量专职化、不摊薄。
2. **「当己方头顶出现日军舰载机时，说明日军航母就在附近了」**：
   敌舰载机出现在我方阵位上空/对舰攻击中，是**敌航母邻近的可靠线索**，
   此时应当**加强机动与空中侦察、按战局寻找打击机会，而不是一味退让**。

⚠️ 识别纪律：零战 A6M2 陆基/舰载通用，**单凭 A6M2 不足以断定舰载机**；
   必须出现 **D3A（九九舰爆/Val）或 B5N（九七舰攻/Kate）** 才算舰载攻击机证据。
   同理 G3M/G4M（Nell/Betty）是陆基，绝不当作航母线索。
"""
import math
import os
import re
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from .hex_math import hex_distance

GAME_SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
STATE_DIR = os.path.join(READER_DIR, "state")

# 舰载攻击机型号（唯一可靠的「舰载机」证据）
CARRIER_ATTACK_RE = re.compile(r"\b(?:D3A\d?|B5N\d?|B6N\d?|B7A\d?|D4Y\d?)\b", re.IGNORECASE)
# 舰载战斗机（辅证，单独不作数）
CARRIER_FIGHTER_RE = re.compile(r"\b(?:A6M[2-9]\d?|A7M\d?)\b", re.IGNORECASE)
# 陆基机型（用于排除误判）
LAND_BASED_RE = re.compile(r"\b(?:G3M\d?|G4M\d?|Ki-\d+|A6M2\s+Zero\s+x)\b", re.IGNORECASE)

ROLE_REMOTE = "远程搜索核心"
ROLE_CV_SCOUT = "舰载专职侦察"
ROLE_FLOAT = "近距/反潜"
ROLE_LAND = "陆基搜索"


def compass_bearing(h1: Tuple[int, int], h2: Tuple[int, int]) -> int:
    """罗盘方位角（000=北, 090=东, 180=南, 270=西）。y 轴向南为正。"""
    dx = h2[0] - h1[0]
    dy = h2[1] - h1[1]
    deg = math.degrees(math.atan2(dx, -dy))
    return int(deg) % 360


def bearing_arc(center: int, width: int = 90) -> Tuple[int, int]:
    """以 center 为中心的扇面起止角。"""
    half = width // 2
    return (center - half) % 360, (center + half) % 360


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return __import__("json").load(f)
    except Exception:
        return None


def _dates_back(date_str: str, n: int) -> List[str]:
    m = re.match(r"(\d{2})/(\d{2})/(\d{2})", str(date_str or ""))
    if not m:
        return []
    mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        d = datetime(2000 + yy, mm, dd)
    except ValueError:
        return []
    return [(d - timedelta(days=i)).strftime("%y%m%d") for i in range(n)]


def carrier_aircraft_contacts(save_dir: Optional[str] = None,
                              turn_date: Optional[str] = None,
                              days: int = 6,
                              bounds: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
    """扫描战报，找出日军**舰载攻击机**出现的战斗，作为敌航母邻近线索。

    bounds: 可选 (x0, y0, x1, y1) 地图包围盒；给了就丢弃盒外的伪坐标
            （实测参谋部曾据伪坐标报「敌航母 (13,42)」并建议开往 (17,44)）。
    """
    save_dir = save_dir or GAME_SAVE_DIR
    dates = _dates_back(turn_date or "", days)
    hits: List[Dict[str, Any]] = []
    if not dates:
        return {"detected": False, "note": "无法确定游戏日期，未扫描战报（不猜）", "hits": []}

    for d in dates:
        for pat in (f"combatreport_{d}.txt", f"aoperationsreport_{d}.txt"):
            path = os.path.join(save_dir, pat)
            if not os.path.exists(path):
                continue
            try:
                # 路径含单引号（Admiral's Edition）→ 必须双引号，否则 iconv 静默失败
                txt = subprocess.run(f'iconv -f GBK -t UTF-8 "{path}"',
                                     shell=True, capture_output=True, text=True,
                                     timeout=30).stdout
            except Exception:
                continue
            blocks = re.split(r"-{20,}", txt)
            for blk in blocks:
                if not CARRIER_ATTACK_RE.search(blk):
                    continue
                # ★2026-09-26 修复★ 必须真的是「**日军**舰载机在行动」才算敌航母线索。
                #   旧实现只看区块里出现了舰载机型号，实测把「我方 SBD 攻击日军潜艇」
                #   （`SBD-3 Dauntless from VS-5 attacking a Type KD7 class SS at ...`）
                #   误判为「敌航母目击」，进而让参谋部报出「敌航母 (13,42)」这种垃圾情报。
                if "Japanese aircraft" not in blk:
                    continue
                title = ""
                for ln in blk.strip().splitlines():
                    ln = ln.strip()
                    if ln and ("attack" in ln.lower() or "sighting" in ln.lower()
                               or "combat" in ln.lower() or "raid" in ln.lower()):
                        title = ln
                        break
                # ★2026-09-26 修复★ 坐标解析两处 bug：
                #   ① 旧写法 re.search(r"(\d{2,3}),(\d{2,3})", blk) 会抓区块里**第一个**
                #      「数字,数字」——实测把高度 "18,000 feet"、炮战 "7,000 yards" 误当坐标，
                #      产出地图外垃圾坐标（参谋部曾据此报「敌航母 (13,42)」并建议开往 (17,44)，
                #      距我航母 139 格）。正确做法：**只从标题行**取，且必须形如 " at HH,HH"。
                #   ② 必须做边界合理性闸门：坐标要落在 1..199 且（若给了 bounds）在地图范围内。
                hex_m = None
                for _ln in blk.strip().splitlines()[:8]:
                    _m = re.search(r"\bat\s+(\d{1,3})\s*,\s*(\d{1,3})\b", _ln)
                    if _m:
                        _x, _y = int(_m.group(1)), int(_m.group(2))
                        if 1 <= _x <= 199 and 1 <= _y <= 199:
                            if bounds is None or (
                                    bounds[0] <= _x <= bounds[2] and bounds[1] <= _y <= bounds[3]):
                                hex_m = _m
                        break
                # ★2026-09-26 关键修正★ 必须判明「这次攻击打的是谁」——
                #   战报里 "Air attack on TF, near X at H" 的 H 是**被攻击方**所在格。
                #   若该块含 "Allied Ships"，说明**挨打的是我们**，H 是**我方位置**，
                #   绝不能当成敌航母位置（实测因此把约克城挨打的 (108,138) 误报成
                #   "敌航母在 (108,138)"，进而让参谋部建议朝自己所在处『前出打击』）。
                #   只有含 "Japanese Ships" 的块（我方空袭打中敌舰）H 才是敌舰位置。
                on_us = "Allied Ships" in blk
                hits.append({
                    "file": pat,
                    "date": d,
                    "title": title or blk.strip().splitlines()[0][:80],
                    "hex": [int(hex_m.group(1)), int(hex_m.group(2))] if hex_m else None,
                    "types": sorted(set(m.upper() for m in CARRIER_ATTACK_RE.findall(blk))),
                    "on_us": on_us,
                    "meaning": ("我方在该格遭敌舰载机攻击 → 敌航母在**该格约 5 格内**，"
                                "该格是**我方位置**，不可当作敌航母坐标" if on_us else
                                "我方在该格击中敌舰 → 该格是**敌舰位置**"),
                })
    # 去重（同文件同标题同坐标）
    uniq, seen = [], set()
    for h in hits:
        k = (h["file"], h["title"], tuple(h["hex"] or []))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)

    return {
        "detected": bool(uniq),
        "hits": uniq,
        "note": (f"发现 {len(uniq)} 处日军舰载攻击机活动——敌航母必在附近"
                 if uniq else "本回合窗口内未发现日军舰载攻击机活动"),
        "discipline": "仅以 D3A/B5N 等舰载攻击机为证据；A6M2 单独不作数，G3M/G4M 为陆基须排除",
    }


def build_search_plan(airgroups: List[Dict[str, Any]],
                      bases: List[Dict[str, Any]],
                      threat_areas: List[Dict[str, Any]],
                      contacts: Optional[Dict[str, Any]] = None,
                      pm_hex: Tuple[int, int] = (98, 130)) -> Dict[str, Any]:
    """为每个具备搜索能力的中队指派搜索比例与扇面（专职化，不摊薄）。"""
    contacts = contacts or {}

    def _is_enemy_base(b: Dict[str, Any]) -> bool:
        """敌方基地判据（★2026-10-14 修：按当前阵营自适应，不再把日军硬编码为敌方）★
        复用 theater.is_enemy_base —— 它读 `witp-reader/side.txt` 决定人类执哪一方。
        旧实现把日军指挥部一律当敌方，本局人类执日军时敌我完全弄反
        （搜索主轴会指向自己的拉包尔基地）。"""
        if b.get("x") is None or b.get("y") is None:
            return False
        try:
            from .theater import is_enemy_base as _teb
            return _teb(b)
        except Exception:
            hq = str(b.get("area_command") or "")
            return any(k in hq for k in ("Southeast Fleet", "Fourth Fleet", "Combined Fleet",
                                         "Southwest Area Fleet", "Southern Army", "8th Fleet"))

    enemy_bases = [b for b in (bases or []) if _is_enemy_base(b)]

    def _axis_for(here: Tuple[int, int]) -> Optional[Dict[str, Any]]:
        """为某位置选搜索主轴：敌方基地按「威胁度 = 六角距离 − 2×机场等级」排序取最优。
        有机场的敌方基地才真正威胁我们，故给机场加权（避免把无机场的孤立小岛当主轴）。"""
        cand = []
        for b in enemy_bases:
            d = hex_distance(here, (int(b["x"]), int(b["y"])))
            af = int(b.get("airfield") or 0)
            cand.append((d - af * 2, d, b))
        if not cand:
            return None
        cand.sort(key=lambda t: (t[0], t[1]))
        _, d, b = cand[0]
        return {"hex": [int(b["x"]), int(b["y"])], "name": b.get("name"),
                "airfield": int(b.get("airfield") or 0), "distance_hex": d}

    def _theater_axis() -> Optional[Dict[str, Any]]:
        """战区主轴 = 从 PM（一级目标）看最近的**敌方机场基地**方位——珊瑚海剧本即拉包尔方向。
        **排除 PM 本身**：PM 是一级目标/争夺点，不是搜索轴线；敌方的空中威胁来自其后方的支援机场。"""
        with_af = [b for b in enemy_bases
                   if int(b.get("airfield") or 0) > 0
                   and (int(b["x"]), int(b["y"])) != tuple(pm_hex)]
        if not with_af:
            return None
        b = min(with_af, key=lambda x: hex_distance(pm_hex, (int(x["x"]), int(x["y"]))))
        d = hex_distance(pm_hex, (int(b["x"]), int(b["y"])))
        brg = compass_bearing(pm_hex, (int(b["x"]), int(b["y"])))
        s, e = bearing_arc(brg, 90)
        return {"hex": [int(b["x"]), int(b["y"])], "name": b.get("name"),
                "bearing": brg, "bearing_text": f"{brg:03d}°", "arc_start": s, "arc_end": e,
                "distance_hex": d,
                "text": f"自 PM 看 {brg:03d}°（{b.get('name')}，机场{int(b.get('airfield') or 0)}级，"
                        f"距 {d} 格）——本战区敌方空中威胁的主攻轴线"}

    assignments: List[Dict[str, Any]] = []
    for a in airgroups or []:
        if (a.get("aircraft_active") or 0) <= 0:
            continue
        nm = str(a.get("name") or "")
        ty = str(a.get("aircraft_type_name") or a.get("aircraft_name") or "").upper()
        base = a.get("stationed_at_base_name")
        ship = a.get("stationed_on_ship_name")
        hx = a.get("x") if a.get("x") is not None else a.get("target_x")
        hy = a.get("y") if a.get("y") is not None else a.get("target_y")
        if hx is None or hy is None:
            continue
        here = (int(hx), int(hy))

        # 角色判定
        if "PBY" in ty or "CATALINA" in ty or nm.upper().startswith("VP"):
            role, nav, asw = ROLE_REMOTE, 100, 0
        elif nm.upper().startswith("VS") or ("SBD" in ty and ship):
            role, nav, asw = ROLE_CV_SCOUT, 100, 0
        elif ty in ("FP", "FLOAT") or nm.upper().startswith(("VCS", "SOC", "OS2U")):
            role, nav, asw = ROLE_FLOAT, 50, 50
        elif "B-17" in ty or "B-24" in ty or "LB" in ty:
            role, nav, asw = ROLE_LAND, 50, 25
        else:
            continue

        # 主轴：优先指向「敌舰载机接触点」（最强线索），否则指向最近的敌方基地
        axis_hex, axis_src = None, ""
        if contacts.get("hits"):
            h = next((x for x in contacts["hits"] if x.get("hex")), None)
            if h:
                axis_hex, axis_src = tuple(h["hex"]), f"敌舰载机接触 {h['file']}"
        if axis_hex is None and threat_areas:
            t = next((x for x in threat_areas if (x.get("position") or {}).get("x") is not None), None)
            if t:
                axis_hex, axis_src = (t["position"]["x"], t["position"]["y"]), "日军目击报告"
        if axis_hex is None:
            ax = _axis_for(here)
            if ax:
                axis_hex, axis_src = ((ax["hex"][0], ax["hex"][1]),
                                      f"敌方基地 {ax.get('name')}"
                                      f"（机场{ax.get('airfield')}级，距 {ax.get('distance_hex')} 格）")

        if axis_hex is None:
            assignments.append({
                "ag": nm, "type": ty, "role": role, "nav_search": nav, "asw_search": asw,
                "arc_start": None, "arc_end": None, "axis": None,
                "note": "无可参照敌情，暂不设扇面（全向搜索）",
            })
            continue

        brg = compass_bearing(here, axis_hex)
        s, e = bearing_arc(brg, 90)
        assignments.append({
            "ag": nm, "type": ty, "role": role,
            "nav_search": nav, "asw_search": asw,
            "arc_start": s, "arc_end": e,
            "axis": {"hex": list(axis_hex), "bearing": brg, "source": axis_src,
                     "bearing_text": f"{brg:03d}°"},
            "note": f"扇面 {s:03d}°→{e:03d}°（指向 {brg:03d}°，{axis_src}）",
        })

    ctrl = next((x for x in assignments if x["role"] == ROLE_REMOTE), None)
    return {
        "requires_review": True,
        "assignments": assignments,
        "summary": (f"共 {len(assignments)} 个中队执行搜索；远程核心 "
                    f"{sum(1 for x in assignments if x['role'] == ROLE_REMOTE)} 个、"
                    f"舰载专职侦察 {sum(1 for x in assignments if x['role'] == ROLE_CV_SCOUT)} 个、"
                    f"近距/反潜 {sum(1 for x in assignments if x['role'] == ROLE_FLOAT)} 个"),
        "principal_axis": ctrl["axis"] if ctrl else None,
        "theater_axis": _theater_axis(),
        "doctrine": "侦察专职化：PBY=远程核心 100%、VS=舰载专职侦察 100%、VCS=近距/反潜 50/50；"
                    "扇面按敌情方位角设定，禁止无扇面全向摊薄。",
        "note": "本方案为参谋部建议，指挥层审核后下达（需 witp-cmd set-search 通道）。",
    }


def carrier_proximity(contacts: Dict[str, Any],
                      own_positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """把「敌舰载机接触」升级为「敌航母邻近」判定 + 应对指导。"""
    own_positions = own_positions or []
    hits = [h for h in (contacts.get("hits") or []) if h.get("hex")]
    if not hits:
        return {
            "proximity": False,
            "verdict": "无敌舰载机接触——无可推定的敌航母位置（不猜）",
            "guidance": "维持扇面搜索；PBY 与舰载侦察机按搜索方案专职出动。",
        }

    pts = [tuple(h["hex"]) for h in hits]
    # 推定敌航母在当前接触点周边（舰载机作战半径内）
    def _d(h):
        return min([abs(h[0] - p[0]) + abs(h[1] - p[1]) for p in pts] or [99])

    nearest_own = None
    if own_positions:
        nearest_own = min(own_positions, key=lambda c: _d(tuple(c["hex"])))

    return {
        "proximity": True,
        "verdict": "⚠️ 敌航母邻近：我方头顶/近旁已出现日军舰载攻击机",
        "contact_hexes": [list(p) for p in pts],
        "evidence": [f"{h['file']}｜{h['title'][:70]}｜机型 {'/'.join(h['types'])}" for h in hits[:4]],
        "inferred_carrier_search_radius_hex": 6,
        "nearest_own_unit": ({"tf": nearest_own.get("tf"), "hex": list(nearest_own["hex"])}
                             if nearest_own else None),
        "guidance": (
            "**加强机动与空中侦察，按战局寻找打击机会——不得一味退让。**"
            "①立即把搜索扇面对准接触点方位（PBY/VS 拉到 100% 搜索）；"
            "②航母机动至可对接触点周边 6 格内实施打击的位置（见 carrier_opportunity）；"
            "③CAP 保持高位防止被先手打掉。"
        ),
        "risk_note": "推定位置是「舰载机作战半径」的估算，非确切坐标；须以侦察确认为准后方可全力突击。",
    }
