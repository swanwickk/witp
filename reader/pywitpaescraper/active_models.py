"""Active dataset models.

Relationship fields ending with ``_id`` are raw record IDs from PWS data and are
treated as array indices in the corresponding dataset.
Example: ``loaded_on_ship_id == 5`` means the airgroup is loaded on ``ships[5]``.
"""

from dataclasses import dataclass, field
from typing import Any


RecordId = int


@dataclass(slots=True)
class ActiveAirgroup:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    aircraft_id: int | None = None
    aircraft_name: str | None = None
    aircraft_type_name: str | None = None
    pilot_ids: list[int] = field(default_factory=list)
    pilot_names: list[str] = field(default_factory=list)
    current_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    target_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    stationed_at_base_id: int | None = None
    stationed_at_base_name: str | None = None
    at_base_type: int | None = None
    in_task_force_id: int | None = None
    loaded_on_ship_id: int | None = None
    loaded_on_ship_name: str | None = None
    stationed_on_ship_id: int | None = None
    stationed_on_ship_name: str | None = None
    loaded_as_cargo_on_ship_id: int | None = None
    loaded_as_cargo_on_ship_name: str | None = None


@dataclass(slots=True)
class ActiveShip:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    shipclass_name: str | None = None
    shipclass_type_name: str | None = None
    shipclass_nation_name: str | None = None
    shipclass_tonnage: int | None = None
    current_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    stationed_at_base_id: int | None = None
    stationed_at_base_name: str | None = None
    at_base_type: int | None = None
    in_task_force_id: int | None = None
    airgroup_ids: list[int] = field(default_factory=list)
    airgroup_names: list[str] = field(default_factory=list)
    loaded_ground_unit_id: int | None = None
    loaded_ground_unit_name: str | None = None
    loaded_airgroup_cargo_id: int | None = None
    loaded_airgroup_cargo_name: str | None = None


@dataclass(slots=True)
class ActiveGroundUnit:
    record_id: int
    current: Any = None
    unit_name: str | None = None
    unit_type_name: str | None = None
    arrive_day: int | None = None
    nation_name: str | None = None
    attached_hq_id: int | None = None
    attached_hq_name: str | None = None
    stationed_at_base_id: int | None = None
    stationed_at_base_name: str | None = None
    loaded_on_ship_id: int | None = None
    loaded_on_ship_name: str | None = None
    start_of_day_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    end_of_day_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    destination_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    at_base_type: int | None = None
    hq_kind: str | None = None


@dataclass(slots=True)
class ActiveTaskForce:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    flagship_name: str | None = None
    commander_name: str | None = None
    ships: list[dict[str, str | None]] = field(default_factory=list)
    start_of_day_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    end_of_day_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    target_position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})
    at_base_type: int | None = None


@dataclass(slots=True)
class ActiveBase:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    facmach_device_ids: list[int] = field(default_factory=list)
    facmach_device_names: list[str] = field(default_factory=list)
    port: int | None = None
    airfield: int | None = None
    ship_repair_points: int | None = None
    supply: int | None = None
    resources: int | None = None
    fuel: int | None = None
    runway_damage: int | None = None
    port_damage: int | None = None
    airfield_damage: int | None = None
    ground_unit_ids: list[int] = field(default_factory=list)
    air_group_ids: list[int] = field(default_factory=list)
    ship_ids: list[int] = field(default_factory=list)
    ground_unit_names: list[str] = field(default_factory=list)
    air_group_names: list[str] = field(default_factory=list)
    ship_names: list[str] = field(default_factory=list)
    stationed_ground_ids: list[int] = field(default_factory=list)
    stationed_ground_names: list[str] = field(default_factory=list)
    stationed_air_ids: list[int] = field(default_factory=list)
    stationed_air_names: list[str] = field(default_factory=list)
    stationed_port_ids: list[int] = field(default_factory=list)
    stationed_port_names: list[str] = field(default_factory=list)
    position: dict[str, int | None] = field(default_factory=lambda: {"x": None, "y": None})


@dataclass(slots=True)
class ActiveLeader:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    rank_name: str | None = None
    assigned_unit_type: str | None = None
    assigned_unit_id: int | None = None
    assigned_unit_name: str | None = None


@dataclass(slots=True)
class ActivePilot:
    record_id: int
    current: Any = None
    nation_name: str | None = None
    rank_name: str | None = None
    airgroup_id: int | None = None
    airgroup_name: str | None = None


@dataclass(slots=True)
class ActiveCombatReportHex:
    # Synthetic ID for aggregated combat report points.
    record_id: int
    position: dict[str, int]
    action_count: int = 0
    action_types: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    japanese_ships: list[str] = field(default_factory=list)
    allied_ships: list[str] = field(default_factory=list)
    event_lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ActiveThreatArea:
    # Synthetic ID for threat-map points inferred from spotting/SIGINT.
    record_id: int
    position: dict[str, int]
    threat_score: int = 0
    evidence_count: int = 0
    threat_types: list[str] = field(default_factory=list)
    source_categories: list[str] = field(default_factory=list)
    sample_texts: list[str] = field(default_factory=list)
    display_radius_hexes: float | None = None
    display_radius_source: str | None = None


@dataclass(slots=True)
class ActiveInvasionThreat:
    # Synthetic ID for base-centric invasion threat inferred from SIGINT.
    record_id: int
    threat_base_position: dict[str, int]
    threat_base_name: str
    invasion_force_units: list[str] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)
    evidence_count: int = 0