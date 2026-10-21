"""
WitP-AE Hex Math and Coordinate Utilities
WitP uses standard hexagonal grid map where 1 hex = 40 nautical miles.
Provides coordinate transformations, hex distance, and reachable hex calculations.
"""
import math
from typing import List, Tuple, Dict, Any

HEX_NM = 40.0  # 1 hex = 40 nautical miles

def hex_distance(h1: Tuple[int, int], h2: Tuple[int, int]) -> int:
    """
    Calculate the hex grid distance between two hex coordinates (x1, y1) and (x2, y2).
    WitP uses an offset coordinate grid.
    Convert to cube coordinates:
      q = x
      r = y - (x - (x & 1)) // 2
      s = -q - r
    Distance = (abs(q1-q2) + abs(r1-r2) + abs(s1-s2)) // 2
    """
    x1, y1 = h1
    x2, y2 = h2
    
    q1 = x1
    r1 = y1 - (x1 - (x1 & 1)) // 2
    s1 = -q1 - r1
    
    q2 = x2
    r2 = y2 - (x2 - (x2 & 1)) // 2
    s2 = -q2 - r2
    
    return max(abs(q1 - q2), abs(r1 - r2), abs(s1 - s2))

def hex_to_nm(dist_hex: int) -> float:
    """Convert hex distance to nautical miles."""
    return float(dist_hex * HEX_NM)

def get_reachable_hexes(origin: Tuple[int, int], max_range_hex: int, map_bounds: Tuple[int, int, int, int] = (1, 1, 200, 200)) -> List[Tuple[int, int]]:
    """
    Return all hex coordinates within max_range_hex of origin, clamped to map_bounds (min_x, min_y, max_x, max_y).
    """
    ox, oy = origin
    min_x, min_y, max_x, max_y = map_bounds
    reachable = []
    
    for dx in range(-max_range_hex, max_range_hex + 1):
        for dy in range(-max_range_hex, max_range_hex + 1):
            tx = ox + dx
            ty = oy + dy
            if min_x <= tx <= max_x and min_y <= ty <= max_y:
                if hex_distance(origin, (tx, ty)) <= max_range_hex:
                    reachable.append((tx, ty))
    return reachable

def hex_to_screen_offset(base_screen: Tuple[int, int], base_hex: Tuple[int, int], target_hex: Tuple[int, int]) -> Tuple[int, int]:
    """
    Map coordinate to screen pixel offset based on probed WitP scale:
    cx = base_screen_x + (TX - HX) * 42.86
    cy = base_screen_y + (TY - HY) * 37.5
    """
    bx, by = base_screen
    hx, hy = base_hex
    tx, ty = target_hex
    
    cx = int(round(bx + (tx - hx) * 42.86))
    cy = int(round(by + (ty - hy) * 37.5))
    return cx, cy
