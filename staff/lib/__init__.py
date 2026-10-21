"""
WitP-AE Self-Iterating Agent Core Library
"""
from .hex_math import hex_distance, hex_to_nm, get_reachable_hexes
from .fuel_calc import check_tf_fuel_margin
from .option_builder import build_tf_destination_options, build_airgroup_mission_options
from .verify import verify_orders
from .belief_update import update_belief_map
from .perception import capture_state
from . import executor

__all__ = [
    "hex_distance",
    "hex_to_nm",
    "get_reachable_hexes",
    "check_tf_fuel_margin",
    "build_tf_destination_options",
    "build_airgroup_mission_options",
    "verify_orders",
    "update_belief_map",
    "capture_state",
    "executor",
]
