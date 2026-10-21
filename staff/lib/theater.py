"""
战区锚点：一切从存档数据推导，**严禁按历史剧本推定敌人位置或兵力构成**。

指挥官原则（2026-09-25）：
  WitP 模拟性强，指挥策略可依据二战一般性经验；但**剧本每回合存在随机性**，
  对手不一定按历史策略行动、也不一定在历史位置部署。
  因此：**从一般性经验出发，根据战局随机应变**——凡涉及「敌人在哪」的判断，
  必须由当回合读层数据推导，不得写死剧本地名或历史兵力。

本模块提供三个数据推导锚点，供 carrier_station / recon 等复用：
  ① 敌岸基空中威胁锚点 = 距给定位置最近的**敌方机场基地**（airfield > 0）
  ② 我方退路/支援锚点 = 距给定位置最近的**友方港口基地**
  ③ 航母识别 = 按 `ship_type` 前缀 CV（通用），**不按舰名硬编码**
"""
from typing import Dict, Any, List, Optional, Tuple

from .hex_math import hex_distance

JP_HQ_KEYWORDS = ("Southeast Fleet", "Fourth Fleet", "Combined Fleet", "Southwest Area Fleet",
                  "Southern Army", "8th Fleet", "Southeast Area Fleet", "Imperial")
AL_HQ_KEYWORDS = ("Southwest Pacific", "South Pacific", "Central Pacific", "North Pacific",
                  "Australia", "New Zealand", "ANZAC", "ABDA", "USAFFE", "Hawaiian",
                  "West Coast", "Southeast Asia", "Southwest", "China")


def _player_side() -> str:
    """当前人类执哪一方（'JAPAN' / 'ALLIED'）。

    ★2026-10-14 新增（换阵营遗留缺陷修复）★
      本模块此前的 `is_enemy_base` 把**日军硬编码为敌方** —— 那只在「人类执盟军」时成立。
      本局（第 7 局起）人类执**日军** ⇒ 该判据把敌我完全弄反：
      参谋部把日军基地当敌机场、把盟军基地当友方锚点，地理/威胁判定整段崩坏。
      ⇒ 以读层权威 `side.txt`（由 witp_read.sh 自动检测顶栏写入）为准，不写死阵营。
    """
    try:
        with open("/root/.hermes/profiles/witp/workspace/witp-reader/side.txt", encoding="utf-8") as f:
            s = f.read().strip().upper()
        if s in ("JAPAN", "ALLIED"):
            return s
    except Exception:
        pass
    return "ALLIED"


def base_hex(b: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """基地格坐标。★2026-10-14 修（地理崩坏根因）★
      读层 bases.json 里**地图外/本土基地的坐标是哨兵值 65535**（实测 Akita/Ominato/
      Tokyo/Woleai… 全为 (65535,65535)）。旧实现只判 `is None`，于是 65535 被当作
      合法坐标 ⇒ `nearest_enemy_air_anchor` 会把地图外的敌方基地当锚点，
      算出「距 PM 98124 格」这类天文数字，参谋部建议书整段崩坏
      （且它挑中的常是 Japan 本土基地，完全脱离战场）。
      ⇒ 过滤哨兵值：坐标须落在**真实地图范围**内（0~300，剧本可玩区约 96~160）。
    """
    if b.get("x") is None or b.get("y") is None:
        return None
    x, y = int(b["x"]), int(b["y"])
    if x >= 30000 or y >= 30000 or x < 0 or y < 0:
        return None
    return (x, y)


def is_enemy_base(b: Dict[str, Any]) -> bool:
    """敌方基地判据（按当前人类阵营自适应，不写死）。⚠️ 禁用 nation（易主后不更新）。"""
    hq = str(b.get("area_command") or "")
    if _player_side() == "JAPAN":
        return any(k in hq for k in AL_HQ_KEYWORDS)
    return any(k in hq for k in JP_HQ_KEYWORDS)


def is_friendly_base(b: Dict[str, Any]) -> bool:
    """友方基地判据（按当前人类阵营自适应）。"""
    return not is_enemy_base(b)


def nearest_enemy_air_anchor(bases: List[Dict[str, Any]],
                             from_hex: Tuple[int, int],
                             exclude_hex: Optional[Tuple[int, int]] = None) -> Optional[Dict[str, Any]]:
    """距 from_hex 最近的敌方**机场**基地（airfield>0）——本回合实际存在的岸基空中威胁来源。

    `exclude_hex`：若打击目标本身就是敌方机场（如 PM 已易主），把它排除，
    使威胁圈指向**目标之外**的其他敌方机场（避免「用自己的打击目标当规避锚点」的循环）。
    找不到时返回 None——**不猜、不套用剧本地名**。
    """
    ex = tuple(exclude_hex) if exclude_hex else None
    cand = []
    for b in bases or []:
        h = base_hex(b)
        if h is None or not is_enemy_base(b):
            continue
        if ex is not None and h == ex:
            continue
        af = int(b.get("airfield") or 0)
        if af <= 0:
            continue
        cand.append((hex_distance(from_hex, h), h, b, af))
    if not cand:
        return None
    cand.sort(key=lambda t: t[0])
    d, h, b, af = cand[0]
    return {"hex": list(h), "name": b.get("name"), "airfield": af, "distance_hex": d,
            "excluded_hex": list(ex) if ex else None,
            "source": "读层敌方机场基地当场推导（非剧本推定）"}


def is_airbase(b: Dict[str, Any]) -> bool:
    return int(b.get("airfield") or 0) > 0


def nearest_friendly_support_anchor(bases: List[Dict[str, Any]],
                                    from_hex: Tuple[int, int],
                                    min_port: int = 2) -> Optional[Dict[str, Any]]:
    """距 from_hex 最近的友方**可用港口**基地——退路与支援基准。

    `min_port=2`：一般性经验——退路基准必须是可用的后方基地，
    前沿小港（port 1）不足以作为退路（实测会选到紧邻敌占区的前沿小港）。
    """
    cand = []
    for b in bases or []:
        h = base_hex(b)
        if h is None or not is_friendly_base(b):
            continue
        pr = int(b.get("port") or 0)
        if pr < min_port:
            continue
        cand.append((hex_distance(from_hex, h), h, b, pr))
    if not cand:
        return None
    cand.sort(key=lambda t: t[0])
    d, h, b, pr = cand[0]
    return {"hex": list(h), "name": b.get("name"), "port": pr, "distance_hex": d,
            "min_port_rule": min_port,
            "source": "读层友方可用港口当场推导（非剧本推定）"}


def is_carrier_ship(ship: Dict[str, Any]) -> bool:
    """通用航母判据：ship_type 以 CV 开头（CV/CVL/CVE）。
    ⚠️ 不用 aircraft_capacity——CA/CL 也有 1~4 架水上飞机，会误判。"""
    st = str(ship.get("ship_type") or ship.get("ship_class_type_name") or "").upper()
    return st.startswith("CV")


def tf_has_carrier(tf: Dict[str, Any]) -> bool:
    return any(is_carrier_ship(s) for s in (tf.get("ships") or []))


def carrier_ships_in_tf(tf: Dict[str, Any]) -> List[str]:
    return [str(s.get("name")) for s in (tf.get("ships") or []) if is_carrier_ship(s)]
