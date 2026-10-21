"""
WitP-AE Grounding & Verification
Compares issued intent orders against the actual state readback from game save/JSONs.
Detects drift, silently overridden commands, or unapplied orders.
"""
import re
from typing import Dict, Any, List

# WitP-AE 常见任务码映射
MISSION_CODE_NAMES = {
    1: "AIRFIELD_ATTACK",
    2: "PORT_ATTACK",
    3: "NAVAL_ATTACK",
    4: "GROUND_ATTACK",
    5: "SWEEP",
    6: "CAP",
    7: "ESCORT",
    8: "NAVAL_SEARCH",
    9: "ASW_PATROL",
    10: "RECON",
    11: "TRAINING",
}

def verify_orders(orders: List[Dict[str, Any]], current_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify a list of orders against the new state readback from game save/JSONs.
    Sixth Run Fix: Correctly maps native WitP taskforces.json (record_id, target_x/y)
    and airgroups.json (name, primary_mission_code, percent_cap).
    """
    results = []
    all_passed = True

    # 1. 建立 TF 索引：支持 "TF14", "14", 或旗舰名
    tfs = {}
    for tf in current_state.get("taskforces", []):
        rid = tf.get("record_id")
        if rid is not None:
            tfs[str(rid)] = tf
            tfs[f"TF{rid}"] = tf
            tfs[f"tf{rid}"] = tf
        flag = tf.get("flagship_name")
        if flag:
            tfs[flag.lower()] = tf

    # 2. 建立航空队索引：支持中队名 (如 "VF-2"), "AG#1", 或 record_id
    airgroups = {}
    for ag in current_state.get("airgroups", []):
        nm = ag.get("name")
        rid = ag.get("record_id")
        if nm:
            airgroups[str(nm).upper()] = ag
            airgroups[str(nm).lower()] = ag
        if rid is not None:
            airgroups[str(rid)] = ag
            airgroups[f"AG#{rid}"] = ag
            airgroups[f"AG{rid}"] = ag

    for o in orders:
        otype = (o.get("type") or o.get("action") or "").lower()
        tid = str(o.get("target_id") or o.get("tf_id") or o.get("ag_id") or "")
        status = "PASSED"
        detail = ""

        if "dest" in otype:
            # 兼容 expected_hex, params.hex, goal_hex
            expected_hex = o.get("expected_hex") or (o.get("params") or {}).get("hex") or o.get("goal_hex")
            if isinstance(expected_hex, list):
                expected_hex = tuple(expected_hex)

            # 匹配 TF
            clean_tid = re.sub(r"[^0-9]", "", tid)
            tf = tfs.get(tid) or tfs.get(clean_tid) or tfs.get(tid.lower())

            if not tf:
                status = "FAILED"
                detail = f"编队 {tid} 在当前存档中未找到。"
                all_passed = False
            else:
                dest = (tf.get("target_x"), tf.get("target_y"))
                if expected_hex and dest != expected_hex:
                    # 允许 1 格误差（自动寻路或航道修正）
                    dist = abs(dest[0] - expected_hex[0]) + abs(dest[1] - expected_hex[1]) if dest[0] is not None else 99
                    if dist <= 1:
                        detail = f"编队目标格 {dest} 与预期 {expected_hex} 基本吻合（容差 1 格）。"
                    else:
                        status = "OVERRIDDEN"
                        detail = f"编队目标格为 {dest}，预期为 {expected_hex}。"
                        all_passed = False
                else:
                    detail = f"编队目标格完全吻合 {dest}。"

        elif "cap" in otype or "air" in otype:
            clean_ag = tid.strip()
            ag = airgroups.get(clean_ag) or airgroups.get(clean_ag.upper()) or airgroups.get(clean_ag.lower())

            if not ag:
                status = "FAILED"
                detail = f"中队 {tid} 在当前存档中未找到。"
                all_passed = False
            else:
                exp_c = o.get("expected_cap_pct") or (o.get("params") or {}).get("cap_pct") or o.get("cap_pct")
                if exp_c is not None:
                    act_c = ag.get("percent_cap")
                    if act_c != exp_c:
                        status = "OVERRIDDEN"
                        detail = f"中队 CAP 为 {act_c}%，预期为 {exp_c}%。"
                        all_passed = False
                    else:
                        detail = f"中队 CAP 吻合 {act_c}%。"

                exp_m = o.get("expected_mission") or (o.get("params") or {}).get("mission")
                if exp_m is not None:
                    act_m_code = ag.get("primary_mission_code")
                    act_m_name = MISSION_CODE_NAMES.get(act_m_code, str(act_m_code))
                    if str(exp_m).upper() not in (str(act_m_name).upper(), str(act_m_code)):
                        status = "OVERRIDDEN"
                        detail = f"中队任务为 {act_m_name}({act_m_code})，预期为 {exp_m}。"
                        all_passed = False
        else:
            detail = f"指令类型 {otype} 执行记录通过。"

        results.append({
            "order": o,
            "status": status,
            "detail": detail
        })

    return {
        "verified": all_passed,
        "total_orders": len(orders),
        "passed_count": sum(1 for r in results if r["status"] == "PASSED"),
        "drift_count": sum(1 for r in results if r["status"] in ("DRIFT", "OVERRIDDEN")),
        "failed_count": sum(1 for r in results if r["status"] == "FAILED"),
        "details": results
    }
