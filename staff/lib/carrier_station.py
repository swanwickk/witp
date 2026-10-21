"""
WitP-AE 航母前推位推荐（参谋部每回合按敌情给出，指挥层审核后执行）

设计原则（来自指挥官订正）：
  **三级优先级是层层递减的严格字典序。**「保航母」以「PM 未失守」为前提，
  是第一级的**从属考量**，**绝不是第一级的否决权**。
  因此本模块**不设固定红线**（此前的 100,138 硬线已废除），
  而是每回合按敌情算出「能打到目标、同时把已知风险标出来」的前推位，
  交指挥层审核。风险提示只报告、不自动拦截。

目标锚点（anchor）的取法：
  1. PM 仍属盟军且发现登陆迹象 → 锚点 = PM 本体（船团就在港外卸载）——第一级直接手段；
  2. PM 已失守        → 锚点 = 距 PM 最近的日军水面目击（转入攻击得分）；
  3. 否则              → 锚点 = 距 PM 8 格内的日军水面目击；无则无锚点。
"""
import re
from typing import Dict, Any, List, Optional, Tuple

from .hex_math import hex_distance, get_reachable_hexes
from . import theater

PM_HEX = (98, 130)
CV_STRIKE_RANGE = 4              # 舰载机对舰打击半径（格）

# ⚠️ 以下两个仅为**读层无数据时的兜底常量**，默认不参与计算。
#   指挥官原则（2026-09-25）：剧本每回合有随机性，对手未必按历史策略行动、也未必在历史位置部署。
#   故「敌岸基威胁锚点」与「我方退路锚点」一律由 bases.json 当场推导（lib/theater.py），
#   严禁把剧本地名（拉包尔/加斯马塔/汤斯维尔…）写死为主判据。
_FALLBACK_ENEMY_AIR_HEX = (106, 125)
_FALLBACK_FRIENDLY_BASE_HEX = (92, 144)


def _sighting_positions(threat_areas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for a in threat_areas or []:
        types = set(a.get("threat_types") or [])
        if not (types & {"surface", "carrier", "invasion"}):
            continue
        pos = a.get("position") or {}
        if pos.get("x") is None or pos.get("y") is None:
            continue
        out.append({
            "hex": (int(pos["x"]), int(pos["y"])),
            "score": a.get("threat_score", 0),
            "text": (a.get("sample_texts") or [""])[0],
            "kinds": types,
        })
    return out


def _pick_anchor(pm: Dict[str, Any], sightings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    owner = pm.get("owner")
    level1_active = pm.get("level1_active")

    # ① PM 未失守 + 登陆迹象 → 锚点就是 PM 本体
    if level1_active:
        _el = "盟军" if theater._player_side() == "JAPAN" else "日军"
        return {"hex": PM_HEX, "desc": f"PM 港外{_el}船团（登陆进行中，第一级直接目标）",
                "evidence": pm.get("landing_evidence") or "", "score": 99}

    # ②/③ 取距 PM 最近的敌方水面目击
    cand = [s for s in sightings
            if hex_distance(s["hex"], PM_HEX) <= 8 or "Moresby" in (s["text"] or "")]
    if not cand:
        return None
    cand.sort(key=lambda s: (hex_distance(s["hex"], PM_HEX), -s["score"]))
    best = cand[0]
    # ★2026-10-14 修：文案按当前阵营自适应（不再写死「对日军」）★
    _enemy_label = "盟军" if theater._player_side() == "JAPAN" else "日军"
    if owner == "japan":
        desc = f"PM 已失守，转入对{_enemy_label}水面目标的机会打击"
    else:
        desc = f"距 PM {hex_distance(best['hex'], PM_HEX)} 格的{_enemy_label}水面编队"
    return {"hex": best["hex"], "desc": desc, "evidence": best["text"], "score": best["score"]}


def _score_candidate(hex_: Tuple[int, int], anchor: Tuple[int, int],
                     enemy_air: Optional[Dict[str, Any]] = None,
                     friendly: Optional[Dict[str, Any]] = None) -> Tuple[float, List[str]]:
    """越低越好；返回 (代价, 说明)。

    威胁锚点（敌方机场）与退路锚点（我方港口）均为**数据推导**；
    仅当读层无 bases 数据时才退回兜底常量，并在说明里明确标注来源。
    """
    cost, notes = 0.0, []
    eh = tuple(enemy_air["hex"]) if enemy_air else _FALLBACK_ENEMY_AIR_HEX
    e_name = (enemy_air or {}).get("name") or "兜底常量"
    e_src = (enemy_air or {}).get("source") or "剧本常量回退（读层无 base 数据）"
    d_e = hex_distance(hex_, eh)

    if d_e <= 5:
        cost += 100
        notes.append(f"距敌方机场 {e_name} 仅 {d_e} 格——处于岸基轰炸圈内"
                     f"（第七局 Lexington 即因此类站位战沉）｜锚点来源：{e_src}")
    elif d_e <= 7:
        cost += 25
        notes.append(f"距敌方机场 {e_name} {d_e} 格——贴近岸基轰炸圈边缘｜锚点来源：{e_src}")

    # 偏向开阔侧与我方一侧：锚点以东（x 更大）与以南（y 更大）为优。
    #   理由：锚点是打击目标，取其后方开阔水域便于隐蔽接敌并有退路；
    #   取到目标以西则可能钻进狭窄水域（第七局 Lexington 教训）。
    cost += max(0, (anchor[0] + 1) - hex_[0]) * 2.0    # 越往西越差
    cost += max(0, (anchor[1] + 1) - hex_[1]) * 1.5    # 越往北越差
    # 偏向靠近我方支援基地（退路）
    fh = tuple(friendly["hex"]) if friendly else _FALLBACK_FRIENDLY_BASE_HEX
    cost += hex_distance(hex_, fh) * 0.4
    return cost, notes


def recommend_carrier_station(pm: Dict[str, Any],
                              threat_areas: List[Dict[str, Any]],
                              carrier_positions: Optional[List[Dict[str, Any]]] = None,
                              strike_range: int = CV_STRIKE_RANGE,
                              bases: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """返回参谋部建议的航母前推位。requires_review 恒为 True（指挥层审核后执行）。

    `bases` 传入读层 bases.json → 敌岸基威胁锚点与我方退路锚点**当场推导**，
    不由剧本地名推定（指挥官原则：剧本每回合有随机性，对手未必在历史位置）。
    """
    carrier_positions = carrier_positions or []
    sightings = _sighting_positions(threat_areas)
    anchor = _pick_anchor(pm, sightings)

    # 数据推导锚点：以 PM（一级目标）为参照取最近的敌方机场与我方港口
    #   exclude：若打击锚点本身就是敌方机场（PM 易主后即如此），把它从规避锚点中排除，
    #   否则会把「自己的打击目标」当成规避对象，形成逻辑循环。
    _ex = tuple(anchor["hex"]) if anchor else None
    enemy_air = theater.nearest_enemy_air_anchor(bases or [], PM_HEX, exclude_hex=_ex)
    friendly = theater.nearest_friendly_support_anchor(bases or [], PM_HEX)
    _target_is_airbase = bool(anchor) and any(
        base_hex == _ex and theater.is_airbase(b)
        for b in (bases or []) if (base_hex := theater.base_hex(b)) is not None)

    out: Dict[str, Any] = {
        "requires_review": True,
        "strike_range_hex": strike_range,
        "fixed_red_line": None,          # 明确：不再设固定红线
        "carrier_tf_positions": [
            {"tf": c.get("tf"), "hex": list(c.get("hex") or [])} for c in carrier_positions
        ],
        "doctrine_ref": "零·第一级（死守 PM）；第二级为从属考量，无权否决第一级",
        "risk_notes": [],
    }

    if not anchor:
        out.update({
            "mode": "无敌情·常规待机",
            "hex": None,
            "anchor": None,
            # ★修复★ 无敌情分支也必须输出锚点字段——否则下游读不到，
            #   会误报「锚点来源：剧本常量回退（读层无 base 数据）」，与事实不符。
            "enemy_air_anchor": enemy_air,
            "friendly_support_anchor": friendly,
            "distance_to_enemy_air_hex": (hex_distance(PM_HEX, tuple(enemy_air["hex"]))
                                          if enemy_air else None),
            "anchor_derivation": ("敌岸基威胁与我方退路锚点均由读层 bases.json 当场推导"
                                  if enemy_air else
                                  "⚠️ 读层无敌方机场数据，已回退兜底常量（非剧本推定结果）"),
            "strike_target_is_enemy_airbase": _target_is_airbase,
            "rationale": (f"未发现值得前推打击的{'盟军' if theater._player_side() == 'JAPAN' else '日军'}水面目标。"
                          "本回合不强行前推，由指挥层决定是否仅维持 CAP 与侦察。"),
        })
        if enemy_air:
            out["risk_notes"].append(
                f"敌方机场锚点（数据推导）：{enemy_air.get('name')}（{enemy_air.get('airfield')} 级，"
                f"距 PM {enemy_air.get('distance_hex')} 格）—— 前推位须避开其轰炸圈")
        if friendly:
            out["risk_notes"].append(
                f"我方退路基准（数据推导）：{friendly.get('name')}（港口 {friendly.get('port')} 级，"
                f"距 PM {friendly.get('distance_hex')} 格）")
        return out

    ah = anchor["hex"]
    # 候选：距锚点恰好 strike_range 格的格（次日即可打击）
    cands = [h for h in get_reachable_hexes(ah, strike_range) if hex_distance(h, ah) == strike_range]
    scored = []
    for h in cands:
        c, n = _score_candidate(h, ah, enemy_air, friendly)
        scored.append((c, h, n))
    scored.sort(key=lambda t: t[0])
    best_cost, best_hex, best_notes = scored[0]

    mode = "守港打击位" if pm.get("level1_active") else (
        "机会打击位" if pm.get("owner") == "japan" else "前推打击位")

    out.update({
        "mode": mode,
        "hex": list(best_hex),
        "anchor": {"hex": list(ah), "desc": anchor["desc"], "evidence": anchor.get("evidence", "")},
        "distance_to_anchor_hex": hex_distance(best_hex, ah),
        "distance_to_pm_hex": hex_distance(best_hex, PM_HEX),
        "distance_to_enemy_air_hex": hex_distance(best_hex, tuple(enemy_air["hex"])) if enemy_air
                                     else hex_distance(best_hex, _FALLBACK_ENEMY_AIR_HEX),
        "enemy_air_anchor": enemy_air,
        "friendly_support_anchor": friendly,
        "anchor_derivation": ("敌岸基威胁与我方退路锚点均由读层 bases.json 当场推导"
                              if enemy_air else
                              "⚠️ 读层无敌方机场数据，已回退兜底常量（非剧本推定结果）"),
        "strike_target_is_enemy_airbase": _target_is_airbase,
        "internal_risk_score": round(best_cost, 1),
        "station_risk_notes": best_notes,
        "alternatives": [
            {"hex": list(h), "risk_score": round(c, 1), "notes": n}
            for c, h, n in scored[1:4]
        ],
        "rationale": (
            f"按敌情：{anchor['desc']}（({ah[0]},{ah[1]})）。"
            f"取距其 {strike_range} 格的前推位 ({best_hex[0]},{best_hex[1]})，次日即可实施打击；"
            f"该位不依固定红线判定，而是按岸基威胁与退路方向当场计算。"
        ),
    })

    # 风险清单（只报告，不拦截）——威胁锚点为本回合实际推导，非剧本推定
    d_e = out["distance_to_enemy_air_hex"]
    e_lbl = (enemy_air or {}).get("name") or "兜底常量"
    out["risk_notes"].append(
        f"前推位距敌方机场 {e_lbl} {d_e} 格："
        + ("⚠️ 在岸基轰炸圈内，须确认第一级收益是否值得承担该风险" if d_e <= 5
           else "贴近岸基轰炸圈边缘，须保持高 CAP" if d_e <= 7
           else "在岸基轰炸圈外"))
    if _target_is_airbase:
        out["risk_notes"].append(
            "⚠️ 打击目标本身即为敌方机场（PM 已易主）——该处岸基反击不可避免，"
            "须以高 CAP 与快速进出承受；此风险**不计入**规避锚点，否则无法执行第一级/机会打击。")
    cv_sightings = [s for s in sightings if "carrier" in s["kinds"]]
    out["risk_notes"].append(
        "已发现敌航母目击：" + "；".join(f"({s['hex'][0]},{s['hex'][1]}) {s['text']}" for s in cv_sightings)
        if cv_sightings else
        "本回合无敌航母目击。**不预设敌方兵力构成**（剧本每回合有随机性，"
        "对手未必按历史策略或历史位置行动）——一律以当回合侦察确认的情报为准；无情报则保持搜索，不做无谓规避。")
    out["risk_notes"].append(
        "本条为参谋部建议，**不自动纠偏**；按严格字典序，第二级（保航母）无权否决第一级（死守 PM），"
        "前推位由指挥层审核后执行。")
    return out


# ============================================================================
# 日军航母「机会打击」判定
#
# 指挥官指令：「当有机会打击日军航母时，应当毫不犹豫抓住机会进行攻击。」
# 因此本函数一旦判定**存在机会**，verdict 恒为「立即出击」，不给犹豫留出口：
#   - 不再以「保航母」为由规避（那是把第二级当成了第一级的否决权）；
#   - 打击位取「距敌航母 ≤ 舰载机打击半径」且**最便于我舰当下即刻到位**的格，
#     而不是先退再说。
# 与 D3.7（发现敌航母当天先手出击）同源；第五局约克城「未撤未打」当场战沉即为反面教训。
# ============================================================================
CARRIER_NAME_KW = ("shokaku", "zuikaku", "shoho", "zuiho", "junyo", "hiryu", "soryu",
                   "akagi", "kaga", "ryujo", "翔鹤", "瑞鹤", "翔凤", "龙骧", "飞龙", "苍龙")
CARRIER_TEXT_RE = re.compile(
    r"\b(?:CVB|CVE|CVL|CV)\b|\bCARRIER\b(?!\s+AIRCRAFT)|翔鹤|瑞鹤|翔凤|龙骧|飞龙|苍龙|"
    r"SHOKAKU|ZUIKAKU|SHOHO|ZUIHO|RYUJO", re.IGNORECASE)


def _collect_carrier_intel(threat_areas: List[Dict[str, Any]],
                           carrier_threat_areas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """汇总敌航母目击。①读层 carrier_threat_areas（权威）②兜底：对目击文本做关键词命中。"""
    intel: List[Dict[str, Any]] = []

    for a in carrier_threat_areas or []:
        pos = a.get("position") or {}
        if pos.get("x") is None or pos.get("y") is None:
            continue
        intel.append({"hex": (int(pos["x"]), int(pos["y"])),
                      "text": (a.get("sample_texts") or [""])[0],
                      "src": "读层航母威胁区"})

    for a in threat_areas or []:
        txt = " ".join(a.get("sample_texts") or [])
        low = txt.lower()
        # 接受三类证据：①读层已分类为 carrier 的条目（权威）②文本命中舰载机/舰名关键词
        classified = "carrier" in [str(t).lower() for t in (a.get("threat_types") or [])]
        if not (classified or CARRIER_TEXT_RE.search(txt) or any(k in low for k in CARRIER_NAME_KW)):
            continue
        pos = a.get("position") or {}
        if pos.get("x") is None or pos.get("y") is None:
            continue
        h = (int(pos["x"]), int(pos["y"]))
        if not any(i["hex"] == h for i in intel):
            intel.append({"hex": h, "text": txt or "（读层分类为航母威胁）",
                          "src": "读层分类 carrier" if classified else "目击文本关键词命中"})
    return intel


def detect_carrier_opportunity(pm: Dict[str, Any],
                               threat_areas: List[Dict[str, Any]],
                               carrier_threat_areas: Optional[List[Dict[str, Any]]] = None,
                               carrier_positions: Optional[List[Dict[str, Any]]] = None,
                               strike_range: int = CV_STRIKE_RANGE,
                               bases: Optional[List[Dict[str, Any]]] = None,
                               own_cv: int = 0, enemy_groups: int = 0) -> Dict[str, Any]:
    """判定是否存在打击日军航母的机会，并给出「立即出击」的打击位。
    威胁规避锚点由 bases 数据推导，**不按剧本推定敌人位置**。"""
    carrier_positions = carrier_positions or []
    seen = _collect_carrier_intel(threat_areas, carrier_threat_areas or [])
    enemy_air = theater.nearest_enemy_air_anchor(bases or [], PM_HEX)

    out: Dict[str, Any] = {
        "requires_review": True,
        "doctrine_ref": "零·第三级（机会打击：毫不犹豫）+ D3.7（发现即先手出击）",
        "strike_range_hex": strike_range,
        "level1_tension": False,
        "risk_notes": [],
    }

    if not seen:
        out.update({
            "detected": False,
            "verdict": "本回合无敌航母情报——保持扇面侦察，不做无谓规避。",
            "enemy_carrier_hex": None,
            "strike_hex": None,
            "rationale": "无目击证据不作猜测（感知即真相）。",
        })
        return out

    # ★2026-09-26 关键修正★ 先剔除「与我方航母同格/邻格」的目击 —— 那必然是我们自己。
    #   战报里"我方在该格遭敌舰载机攻击"也被读层归成了 carrier 接触（display_radius_source
    #   = "carrier-aircraft"），而我方自身位置距自身 0 格、按"距我最近"排序永远第一，
    #   于是把约克城挨打的 (108,138) 当成了敌航母，参谋部据此建议"前出打击"——打自己。
    if carrier_positions:
        seen = [i for i in seen
                if min(hex_distance(i["hex"], c["hex"]) for c in carrier_positions) >= 2]
        if not seen:
            out.update({
                "detected": True, "proximity_only": True,
                "enemy_carrier_hex": None, "strike_hex": None, "verdict":
                "敌航母在我方附近活动（舰载机已到我头顶），但**确切位置未知** —— "
                "不得据此前出打击，须待侦察确认后再定。",
                "rationale": "所有接触点都与我方航母同格/邻格，属「我方遭袭」而非「发现敌舰」；"
                             "剔除后无有效敌位置（不猜）。",
            })
            return out

    # 多个目击时，取距我方航母最近者（最可能成为当下机会）
    def _d_to_own(h):
        return min([hex_distance(h, c["hex"]) for c in carrier_positions] or [99])

    seen.sort(key=lambda i: _d_to_own(i["hex"]))
    tgt = seen[0]
    eh = tgt["hex"]

    # 打击位：距敌航母 ≤ strike_range，且**最便于我舰即刻到位**（不先退）
    cands = [h for h in get_reachable_hexes(eh, strike_range) if hex_distance(h, eh) == strike_range]
    scored = []
    for h in cands:
        c = 0.0
        _eh = tuple(enemy_air["hex"]) if enemy_air else _FALLBACK_ENEMY_AIR_HEX
        d_rb = hex_distance(h, _eh)
        if d_rb <= 5:
            c += 100
        elif d_rb <= 7:
            c += 25
        c += max(0, (PM_HEX[0] + 1) - h[0]) * 1.5
        c += _d_to_own(h) * 1.0                              # 越便于当下到位越优
        scored.append((c, h))
    scored.sort(key=lambda t: t[0])
    best = scored[0][1]
    d_own = _d_to_own(best)

    out.update({
        "detected": True,
        # ★2026-09-26★ 裁定必须带兵力意识：机会存在 ≠ 应当无条件出击。
        #   实测教训：1 艘航母对 2 组敌航母时仍输出"立即出击"，与同屏的
        #   carrier_balance_warning 自相矛盾，指挥层照抄即酿成 1v2 强行突击。
        "verdict": ("立即出击（抓住机会，不犹豫）"
                    if (not own_cv or own_cv >= enemy_groups) else
                    f"机会存在但**兵力失衡**（我方航母 {own_cv} 艘 vs 敌方推定 {enemy_groups} 组）"
                    f"—— 依 D3.6「单航母不可突入已确认的敌双航母打击半径」，"
                    f"须先过代价评估（见 carrier_balance_warning），**不得无条件出击**"),
        "balance": {"own_cv": own_cv, "enemy_groups": enemy_groups,
                    "imbalanced": bool(own_cv and enemy_groups and own_cv < enemy_groups)},
        "enemy_carrier_hex": list(eh),
        "enemy_carrier_evidence": tgt["text"],
        "enemy_carrier_intel_source": tgt["src"],
        "strike_hex": list(best),
        "distance_strike_to_enemy_cv_hex": hex_distance(best, eh),
        "distance_own_cv_to_strike_hex": d_own,
        "distance_strike_to_pm_hex": hex_distance(best, PM_HEX),
        "alternatives": [{"hex": list(h), "cost": round(c, 1)} for c, h in scored[1:4]],
        "rationale": (
            f"敌航母目击于 ({eh[0]},{eh[1]})（{tgt['src']}: {tgt['text'][:60]}）。"
            f"打击位取 ({best[0]},{best[1]})：距敌航母 {strike_range} 格（舰载机出击半径内），"
            f"距我航母当前 {d_own} 格——优先选「当下就能到位」的位置，而不是先规避再图后计。"
            f"按指挥官指令：有机会即毫不犹豫出击。"
        ),
    })

    if pm.get("level1_active"):
        out["level1_tension"] = True
        out["risk_notes"].append(
            "⚠️ 此刻 PM 正遭登陆（第一级进行中）。舰载机打击敌航母同时可削弱其登陆掩护，"
            "故本次出击**与第一级同向**；但若两者海域相隔过远，请复核是否需分兵。")
    out["risk_notes"].append(
        "本打击位与「避险」方向相反：参谋部不会因「保航母」而建议放弃打击机会——"
        "第二级是以 PM 未失守为前提的从属考量，无权否决更高目标。")
    return out
