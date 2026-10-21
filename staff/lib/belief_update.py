"""
WitP-AE Qualitative Belief Model (Scenario-Agnostic / Universal)
Dynamically constructs theater threat zones based on actual intel, sightings, and threat areas
from threats.json, aoperationsreport.txt, and bases in any WitP scenario.
"""
import re
from typing import Dict, Any, List

def clean_threat_detail(raw_txt: str) -> str:
    """把 WitP 游戏引擎生成的原始英文战报/侦察文本转换为清晰中文化情报描述。"""
    if not raw_txt:
        return "常规警戒监测中"
    t = raw_txt.strip()

    dir_map = {
        "North": "北", "South": "南", "East": "东", "West": "西",
        "Northeast": "东北", "Northwest": "西北", "Southeast": "东南", "Southwest": "西南"
    }

    # 1. 跟踪定位（最高危机）
    m = re.search(r"(TF\s*\d+)\s+shadowed\s+by\s+Japanese\s+Float\s+Plane\s+at\s+([0-9,]+)\s+near\s+([^,]+)", t, re.I)
    if m:
        return f"⚠️ {m.group(1)} 在 {m.group(3).strip()} ({m.group(2)}) 被日军水上侦察机跟踪定位！"

    # 2. 登陆交战
    m = re.search(r"(Pre-Invasion|Invasion\s+Support)\s+action\s+off\s+([^\(]+)\s*\(([0-9,]+)\)", t, re.I)
    if m:
        act = "登陆支援作战" if "Support" in m.group(1) else "登陆前沿交战"
        return f"敌军逼近 {m.group(2).strip()} ({m.group(3)}) 展开{act}！"

    # 3. 观察哨目击
    m = re.search(r"Coastwatcher\s+sighting:\s*(\d+)\s+Japanese\s+ships?\s+at\s+([0-9,]+)\s+near\s+([^,]+?)\s*,\s*Speed\s+(\d+)\s*,\s*Moving\s+([A-Za-z]+)", t, re.I)
    if m:
        d_str = dir_map.get(m.group(5), m.group(5))
        return f"海岸观察哨：{m.group(3).strip()} ({m.group(2)}) 发现日舰 {m.group(1)} 艘，航向{d_str}，航速 {m.group(4)} 节"

    # 4. 空中侦察目击
    m = re.search(r"([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)\s+sighting\s+report:\s*(\d+)\s+Japanese\s+ships?\s+at\s+([0-9,]+)\s+near\s+([^,]+?)\s*,\s*Speed\s+(\d+)\s*,\s*Moving\s+([A-Za-z]+)", t, re.I)
    if m:
        d_str = dir_map.get(m.group(6), m.group(6))
        return f"{m.group(1)} 侦测报告：{m.group(4).strip()} ({m.group(3)}) 发现日舰 {m.group(2)} 艘，航向{d_str}，航速 {m.group(5)} 节"

    # 5. 潜艇目击报告
    m = re.search(r"([A-Za-z0-9\-]+)\s+reports\s+conning\s+tower\s+at\s+([0-9,\s]+)\s+near\s+([^,\.]+)", t, re.I)
    if m:
        return f"{m.group(1)} 巡逻机：{m.group(3).strip()} ({m.group(2).strip()}) 发现敌潜艇指挥塔"

    # 6. 无线电侦听
    m = re.search(r"Radio\s+transmissions\s+detected\s+at\s+([0-9,]+)", t, re.I)
    if m:
        return f"无线电侦听：在坐标 ({m.group(1)}) 截获敌军通信信号"

    return t


def update_belief_map(current_belief: Dict[str, Any], daily_intel: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically update threat zones based on scenario intel without hardcoding specific theaters.
    Supports both native threats.json (with threat_areas, position, sample_texts)
    and external contact dictionaries.
    """
    regions = current_belief.get("regions", {})
    contacts = daily_intel.get("contacts", [])
    scenario_name = daily_intel.get("scenario_name", "Pacific Theater")
    
    # If no regions yet, populate based on contacts or key sectors
    if not regions:
        named = []
        for c in (contacts or []):
            # 兼容 native threats.json 的 position: {x, y}
            pos = c.get("position") or {}
            px = pos.get("x") if isinstance(pos, dict) else None
            py = pos.get("y") if isinstance(pos, dict) else None
            
            # 兼容传统 coords / hex
            coords = c.get("coords") or c.get("hex")
            if not coords and px is not None and py is not None:
                coords = f"{px},{py}"

            samples = c.get("sample_texts") or []
            txt = samples[0] if samples else (c.get("detail") or c.get("name") or str(c))

            c_name = c.get("name") or c.get("area")
            if not c_name and txt:
                loc_m = re.search(r"near\s+([A-Za-z\s/]+?)(?:,|\.|$|\s+speed)", txt, re.IGNORECASE)
                if not loc_m:
                    loc_m = re.search(r"at\s+([A-Za-z\s/]+?)(?:\s*\(\d|,\s*\d|\.|$|\s+speed)", txt, re.IGNORECASE)
                c_name = loc_m.group(1).strip() if loc_m else None

            if c_name or coords or txt:
                named.append((c_name or "前沿", coords, txt, c))

        if named:
            for idx, (c_name, coords, txt, c) in enumerate(named[:16]):
                blob = (str(txt) + " " + str(c)).lower()
                types = c.get("threat_types", []) if isinstance(c, dict) else []
                
                # 提取舰船数量
                ship_count = 1
                cnt_m = re.search(r"(\d+)\s+Japanese\s+ships?", blob)
                if cnt_m:
                    try:
                        ship_count = int(cnt_m.group(1))
                    except Exception:
                        pass

                clean_txt = clean_threat_detail(txt)

                # 智能威胁分级：避免全盘“高危”通货膨胀
                if "carrier" in types or "carrier" in blob or "cv" in blob or "kido" in blob:
                    type_str = "敌航母打击群"
                    lvl = "HIGH"
                    score = 4
                elif "shadowed" in blob:
                    type_str = "我方编队被定位"
                    lvl = "HIGH"
                    score = 4
                elif "pre-invasion" in blob or "invasion support" in blob or "landing" in blob:
                    type_str = "敌登陆突击群"
                    lvl = "HIGH"
                    score = 4
                elif "invasion" in types or "transport" in blob or "convoy" in blob or ship_count >= 6:
                    type_str = "敌主力水面舰队" if ship_count >= 6 else "敌运输船团"
                    lvl = "HIGH" if ship_count >= 6 else "MEDIUM"
                    score = 4 if ship_count >= 6 else 3
                elif "surface" in types or "cruiser" in blob or "destroyer" in blob or "warship" in blob:
                    type_str = "敌水面舰队"
                    lvl = "MEDIUM" if ship_count >= 2 else "LOW"
                    score = 3 if ship_count >= 2 else 2
                elif "sub" in types or "submarine" in blob or "conning tower" in blob or "periscope" in blob:
                    type_str = "敌潜艇目击"
                    lvl = "MEDIUM"
                    score = 2
                elif "radio" in blob:
                    type_str = "敌通信信号"
                    lvl = "LOW"
                    score = 1
                else:
                    type_str = "敌情接触点"
                    lvl = "LOW"
                    score = 1

                label = f"{type_str} [{c_name}]"
                if coords:
                    label += f" ({coords})"

                regions[f"ZONE_{idx+1}"] = {
                    "name": label,
                    "level": lvl,
                    "score": score,
                    "detail": clean_txt,
                    "coords": coords
                }
        else:
            # Universal baseline zones for the Pacific
            regions = {
                "FRONT_LINE": {"name": "前沿交战接触线", "level": "HIGH", "score": 4, "detail": "重点海空对抗与防空警戒区域"},
                "CONVOY_LANES": {"name": "交通线与后勤航道", "level": "MEDIUM", "score": 2, "detail": "防潜反潜巡逻与护航走廊"},
                "REAR_BASES": {"name": "后方基地群与集结港", "level": "LOW", "score": 1, "detail": "安全补给、整备与战备就位区"}
            }

    # Update threat scores with fresh daily contacts
    for c in contacts:
        desc = str(c).lower()
        if "carrier" in desc or "cv" in desc or "kido butai" in desc:
            for r in regions.values():
                if any(k in desc for k in [r["name"].lower()]):
                    r["level"] = "HIGH"
                    r["score"] = 4
                    r["detail"] = "确认遭遇敌方正规航空母舰编队"
                    break

    # Normalize levels strictly
    for r in regions.values():
        sc = r.get("score", 1)
        if sc >= 4:
            r["level"] = "HIGH"
        elif sc >= 2:
            r["level"] = "MEDIUM"
        else:
            r["level"] = "LOW"

    return {
        "scenario_name": scenario_name,
        "turn_date": daily_intel.get("date", "unknown"),
        "regions": regions
    }
