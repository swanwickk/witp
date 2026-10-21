"""
WitP-AE Option Builder
Enumerates valid tactical choices for units (TF destinations, Airgroup missions, CAP percentages).
Produces closed choice lists ready for System 1 (Kev-0.8B) evaluation.
"""
from typing import Dict, Any, List, Tuple
from .hex_math import hex_distance, get_reachable_hexes

# Standard WitP Air Mission Codes
AIR_MISSIONS = {
    "AIRFIELD_ATTACK": 1,
    "PORT_ATTACK": 2,
    "NAVAL_ATTACK": 3,
    "GROUND_ATTACK": 4,
    "SWEEP": 5,
    "CAP": 6,
    "ESCORT": 7,
    "NAVAL_SEARCH": 8,
    "ASW_PATROL": 9,
    "RECON": 10,
    "TRAINING": 11,
}

def build_tf_destination_options(tf_id: str, current_hex: Tuple[int, int], candidate_goals: List[Tuple[int, int]], speed_knots: int = 15) -> Dict[str, Any]:
    """
    Enumerate target hex options for a Task Force based on strategic goals and cruising speed.
    """
    options = []
    # 1 day movement at 15 knots = 360 nm = ~9 hexes
    max_step_hex = max(1, int(round((speed_knots * 24) / 40.0)))
    
    for g in candidate_goals:
        dist = hex_distance(current_hex, g)
        if dist <= max_step_hex:
            options.append({
                "hex": f"({g[0]},{g[1]})",
                "coord": g,
                "dist_hex": dist,
                "note": f"Direct move to destination ({dist} hexes)"
            })
        else:
            # Intermediate waypoint towards goal
            # Direction vector
            dx = g[0] - current_hex[0]
            dy = g[1] - current_hex[1]
            scale = max_step_hex / max(dist, 1)
            wx = int(round(current_hex[0] + dx * scale))
            wy = int(round(current_hex[1] + dy * scale))
            options.append({
                "hex": f"({wx},{wy})",
                "coord": (wx, wy),
                "dist_hex": max_step_hex,
                "note": f"Advance towards goal ({g[0]},{g[1]}) waypoint"
            })
            
    # Always include 'HOLD' option
    options.append({
        "hex": f"({current_hex[0]},{current_hex[1]})",
        "coord": current_hex,
        "dist_hex": 0,
        "note": "Hold current position"
    })
    
    return {
        "tf_id": tf_id,
        "current_hex": current_hex,
        "options": options,
        "choice_labels": [opt["hex"] for opt in options]
    }

def build_airgroup_mission_options(ag_type: str, current_mission: str = "NAVAL_ATTACK") -> Dict[str, Any]:
    """
    Enumerate allowed missions for an airgroup based on type (Fighter, Dive Bomber, Torpedo Bomber, Patrol).
    """
    t = ag_type.upper()
    valid_missions = []
    
    if "VF" in t or "FIGHTER" in t:
        valid_missions = ["CAP", "ESCORT", "SWEEP", "TRAINING"]
    elif "VB" in t or "BOMBER" in t or "VS" in t or "SCOUT" in t:
        valid_missions = ["NAVAL_ATTACK", "NAVAL_SEARCH", "PORT_ATTACK", "AIRFIELD_ATTACK", "TRAINING"]
    elif "VT" in t or "TORPEDO" in t:
        valid_missions = ["NAVAL_ATTACK", "PORT_ATTACK", "ASW_PATROL", "TRAINING"]
    elif "PATROL" in t or "VP" in t or "PBY" in t:
        valid_missions = ["NAVAL_SEARCH", "ASW_PATROL", "RECON", "TRAINING"]
    else:
        valid_missions = ["NAVAL_ATTACK", "NAVAL_SEARCH", "CAP", "TRAINING"]
        
    return {
        "ag_type": ag_type,
        "current_mission": current_mission,
        "allowed_missions": valid_missions,
        "cap_levels": [0, 20, 40, 60, 80, 100] if ("VF" in t or "FIGHTER" in t) else [0]
    }
