"""
WitP-AE Fuel & Endurance Calculation Utilities
Computes fuel consumption, operational range, and safety margins for Task Forces.
"""
from typing import Dict, Any, List

def check_tf_fuel_margin(ships_in_tf: List[Dict[str, Any]], distance_hex: int, speed_knots: int = 15) -> Dict[str, Any]:
    """
    Evaluate if task force has sufficient fuel for a round trip or one-way transit.
    Standard consumption heuristic in WitP:
    - Cruising (12-15 kts): base endurance
    - Mission / Flank speed: consumption scales with (speed/cruise_speed)^2
    """
    total_fuel = 0
    max_fuel = 0
    lowest_endurance_pct = 100.0
    
    for s in ships_in_tf:
        cur_fuel = s.get("fuel", s.get("fuel_current", 1000))
        capacity = s.get("fuel_capacity", 1500)
        total_fuel += cur_fuel
        max_fuel += capacity
        if capacity > 0:
            pct = (cur_fuel / capacity) * 100.0
            if pct < lowest_endurance_pct:
                lowest_endurance_pct = pct

    # Approx 1 hex = 40 nm. At 15 knots, 40 nm takes 2.67 hours.
    hours_transit = (distance_hex * 40.0) / max(speed_knots, 1)
    days_transit = hours_transit / 24.0
    
    # Critical thresholds:
    # < 35% fuel: low warning
    # < 20% fuel: critical abort
    safe = lowest_endurance_pct > 35.0
    critical = lowest_endurance_pct < 20.0
    
    return {
        "safe": safe,
        "critical": critical,
        "lowest_ship_fuel_pct": round(lowest_endurance_pct, 1),
        "total_fuel": total_fuel,
        "max_fuel": max_fuel,
        "est_transit_days": round(days_transit, 1),
        "recommendation": "PROCEED" if safe else ("ABORT_REFUEL" if critical else "CAUTION_MONITOR")
    }
