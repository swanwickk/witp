> **AI First Research Notice**
> This repository — along with its companion [PyWITPAEUI](https://github.com/drwilliamroney/pywitpaeui) — is **100% built by GitHub Copilot** and constitutes a scientific test of the emerging *AI First* working pattern for software developers, conducted by **William N. Roney, ScD**. No human-authored source code was written; all design decisions, implementations, refactors, and repository operations were performed through natural-language instruction to the AI agent.

# PyWITPAEScraper

This project exports side-filtered game state and derived intel to JSON files.

## Requirements

- **32-bit Python 3** is required. The game's native DLL (`pwsdll.py`) uses `ctypes` to load a
  32-bit Windows DLL, which is incompatible with a 64-bit interpreter.
- Install a 32-bit Python 3 from <https://www.python.org/downloads/windows/> and ensure it is
  registered with the [Python Launcher for Windows](https://docs.python.org/3/using/windows.html#python-launcher-for-windows)
  so that `py -3-32` resolves correctly.
- Dependencies (see `requirements.txt`) are installed automatically by `run_scraper.bat`.

## How to Run

### Recommended: via `run_scraper.bat` (auto-bootstrap)

`run_scraper.bat` handles everything — it checks for a 32-bit interpreter (and attempts to
install one via `winget` if missing), creates a `.venv32` virtual environment, installs
dependencies, and then forwards all arguments to `pywitpaescraper.py`.

```bat
run_scraper.bat ^
  --dll-dir "C:\Matrix Games\War in the Pacific Admiral's Edition" ^
  --start-of-day-file "...\SAVE\wpae002.pws" ^
  --end-of-day-file   "...\SAVE\wpae000.pws" ^
  --allied ^
  --output-dir "...\SAVE\ALLIED"
```

Replace `--allied` with `--japan` for the Japanese side.

### Manual / advanced

If you prefer to manage the interpreter yourself, invoke `pywitpaescraper.py` directly with a
32-bit Python interpreter:

```bat
py -3-32 pywitpaescraper.py ^
  --dll-dir "C:\Matrix Games\War in the Pacific Admiral's Edition" ^
  --start-of-day-file "...\SAVE\wpae002.pws" ^
  --end-of-day-file   "...\SAVE\wpae000.pws" ^
  --allied ^
  --output-dir "...\SAVE\ALLIED"
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--dll-dir PATH` | Yes | Game installation directory containing the DLL files |
| `--start-of-day-file PATH` | Yes | Path to `wpae002.pws` (start-of-day save) |
| `--end-of-day-file PATH` | Yes | Path to `wpae000.pws` (end-of-day save) |
| `--allied` / `--japan` | Yes (one) | Side to export |
| `--output-dir PATH` | No | Output directory for JSON files (defaults to `ALLIED`/`JAPAN` under the save dir) |
| `--log-level LEVEL` | No | Logging verbosity: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL` |

## Output Files

The exporter writes these files to the selected output directory:

- `ships.json`
- `ground_units.json`
- `airgroups.json`
- `bases.json`
- `taskforces.json`
- `turn.json`
- `threats.json`

### JSON Convention

`*.json` dataset files use JSON arrays:

- One top-level array per file.
- Each array element is one record object.
- UTF-8 text, pretty-printed.

## Output JSON Schema Notes

Types below use this shorthand:

- `int`, `str`, `bool`, `null`
- `list[T]` for arrays
- `dict[str, T]` for objects

---

### ships.json

Top-level value is `list[dict]`, one ship record per item.

Common fields:

- `record_id: int`
- `name: str | null`
- `nation: str`
- `ship_class_id: int`
- `ship_class_name: str | null`
- `ship_class_type_name: str | null`
- `ship_class_tonnage: int`
- `aircraft_capacity: int`
- `troop_capacity: int`
- `cargo_capacity: int`
- `liquid_capacity: int`
- `leader_id: int | null`
- `leader_name: str | null`
- `leader_rank: str | null`
- `assigned_location_id: int`
- `assigned_location_name: str | null`
- `assigned_location_role: str | null`
- `assigned_hq_id: int | null`
- `assigned_hq_name: str | null`
- `base_chain_hq_id: int | null`
- `base_chain_hq_name: str | null`
- `local_fleet_hq_name: str | null`
- `local_fleet_hq_source_unit_id: int | null`
- `local_fleet_hq_source_unit_name: str | null`
- `local_fleet_hq_source_leader_name: str | null`
- `endurance: int`
- `endurance_per_day: int`
- `ship_base_id: int`
- `stationed_at_base_id: int | null`
- `stationed_at_base_name: str | null`
- `task_force_id: int | null`
- `x: int | null`
- `y: int | null`
- `loaded_ground_unit_id: int | null`
- `loaded_ground_unit_name: str | null`
- `loaded_airgroup_cargo_id: int | null`
- `loaded_airgroup_cargo_name: str | null`

Embedded structures:

- `airgroups: list[dict]`
  - item keys: `record_id`, `name`, `aircraft_id`, `aircraft_name`, `aircraft_type_name`, `aircraft_active`, `aircraft_max`
- `relations: dict`
  - `stationed_at_base: {id, name}`
  - `leader: {id, name, rank}`
  - `task_force: {id}`
  - `loaded_ground_unit: {id, name}`
  - `loaded_airgroup_cargo: {id, name}`
  - `stationed_airgroups: {ids, names}`

---

### ground_units.json

Top-level value is `list[dict]`, one ground-unit location-derived record per item.

Common fields:

- `record_id: int`
- `name: str | null`
- `nation: str`
- `unit_type_name: str`
- `leader_id: int | null`
- `leader_name: str | null`
- `leader_rank: str | null`
- `arrive_day: int`
- `prep_percent: int`
- `prep_target_id: int | null`
- `prep_target_name: str | null`
- `prep_target_x: int | null`
- `prep_target_y: int | null`
- `destination_x: int | null`
- `destination_y: int | null`
- `attached_hq_id: int | null`
- `attached_hq_name: str | null`
- `base_chain_hq_id: int | null`
- `base_chain_hq_name: str | null`
- `local_fleet_hq_name: str | null`
- `local_fleet_hq_source_unit_id: int | null`
- `local_fleet_hq_source_unit_name: str | null`
- `local_fleet_hq_source_leader_name: str | null`
- `effective_hq_id: int | null`
- `effective_hq_name: str | null`
- `effective_hq_source: str | null`
- `loaded_on_ship_id: int | null`
- `loaded_on_ship_name: str | null`
- `at_base_id: int | null`
- `stationed_at_base_id: int | null`
- `stationed_at_base_name: str | null`
- `unit_toe_id: int`
- `supplies_current: int`
- `supplies_needed: int`
- `total_load_cost_assigned: int`
- `total_load_cost_toe: int`
- `cargo_cost_assigned: int`
- `cargo_cost_toe: int`
- `troop_load_cost_assigned: int`
- `troop_load_cost_toe: int`
- `troop_cost_estimate: int`
- `troop_device_count: int`
- `equipment_device_count: int`
- `infantry_count: int`
- `infantry_count_toe: int`
- `vehicle_count: int`
- `vehicle_count_assigned: int`
- `gun_count: int`
- `gun_count_assigned: int`
- `engineer_count: int`
- `other_troops_estimate: int`
- `naval_support: int`
- `naval_support_required: int`
- `aviation_support: int`
- `aviation_support_required: int`
- `assigned_device_count: int`
- `toe_device_count: int`
- `start_of_day_x: int | null`
- `start_of_day_y: int | null`
- `end_of_day_x: int | null`
- `end_of_day_y: int | null`

Embedded structures:

- `device_type_breakdown: dict[str, int]`
- `device_details: list[dict]`
  - item keys: `device_id`, `device_name`, `device_type`, `device_load`, `device_troop_size`, `device_cargo_size`, `assigned`, `toe`
- `relations: dict`
  - `stationed_at_base: {id, name}`
  - `leader: {id, name, rank}`
  - `loaded_on_ship: {id, name}`
  - `attached_hq: {id, name}`

---

### airgroups.json

Top-level value is `list[dict]`, one airgroup record per item.

Common fields:

- `record_id: int`
- `name: str | null`
- `nation: str`
- `aircraft_id: int`
- `aircraft_name: str | null`
- `aircraft_type_name: str | null`
- `aircraft_range: int | null`
- `aircraft_active: int`
- `aircraft_damaged: int`
- `aircraft_max: int`
- `aircraft_being_repaired: int`
- `pilot_count_assigned: int`
- `pilot_ids: list[int]`
- `pilot_names: list[str]`
- `pilot_count_active: int`
- `pilot_count_available: int`
- `leader_id: int`
- `leader_name: str | null`
- `leader_rank: str | null`
- `assigned_hq_id: int | null`
- `assigned_hq_name: str | null`
- `local_air_hq_name: str | null`
- `local_air_hq_source_unit_id: int | null`
- `local_air_hq_source_unit_name: str | null`
- `local_fleet_hq_name: str | null`
- `local_fleet_hq_source_unit_id: int | null`
- `local_fleet_hq_source_unit_name: str | null`
- `primary_mission_code: int`
- `secondary_mission_code: int`
- `percent_cap: int`
- `percent_lrcap: int`
- `percent_asw: int`
- `percent_search: int`
- `percent_train: int`
- `percent_rest: int`
- `asw_arc_start: int | null` - ASW arc start in compass degrees when `percent_asw > 0`
- `asw_arc_end: int | null` - ASW arc end in compass degrees when `percent_asw > 0`
- `search_arc_start: int | null` - Search arc start in compass degrees when `percent_search > 0`
- `search_arc_end: int | null` - Search arc end in compass degrees when `percent_search > 0`
- `base_id: int`
- `stationed_at_base_id: int | null`
- `stationed_at_base_name: str | null`
- `rebase_target_base_id: int | null`
- `rebase_target_base_name: str | null`
- `rebase_target_x: int | null`
- `rebase_target_y: int | null`
- `is_rebasing: bool`
- `x: int | null`
- `y: int | null`
- `target_x: int | null`
- `target_y: int | null`
- `stationed_on_ship_id: int | null`
- `stationed_on_ship_name: str | null`
- `loaded_as_cargo_on_ship_id: int | null`
- `loaded_as_cargo_on_ship_name: str | null`
- `loaded_on_ship_id: int | null`
- `loaded_on_ship_name: str | null`

Embedded structures:

- `relations: dict`
  - `stationed_at_base: {id, name}`
  - `stationed_on_ship: {id, name}`
  - `loaded_as_cargo_on_ship: {id, name}`
  - `loaded_on_ship: {id, name}`
  - `leader: {id, name, rank}`
  - `pilots: {ids, names, count_assigned}`

---

### bases.json

Top-level value is `list[dict]`, one base record per item.

Common fields:

- `record_id: int`
- `name: str | null`
- `nation: str`
- `x: int`
- `y: int`
- `port: int`
- `airfield: int`
- `ship_repair: int`
- `ship_repair_capacity_tons: int`
- `supply: int`
- `supply_needed: int`
- `resources: int`
- `resources_needed: int`
- `oil: int`
- `oil_needed: int`
- `fuel: int`
- `fuel_needed: int`
- `docked_ship_count: int`
- `docked_tonnage_current: int`
- `docked_tonnage_capacity: int`
- `docked_cargo_capacity: int`
- `docked_troop_capacity: int`
- `runway_damage: int`
- `port_damage: int`
- `airfield_damage: int`
- `stationed_ground: list[dict]`
- `stationed_air: list[dict]`
- `stationed_port: list[dict]`
- `stationed_ground_ids: list[int]`
- `stationed_ground_names: list[str]`
- `stationed_air_ids: list[int]`
- `stationed_air_names: list[str]`
- `stationed_port_ids: list[int]`
- `stationed_port_names: list[str]`

Embedded structures:

- `relations: dict`
  - `stationed_ground: {ids, names}`
  - `stationed_air: {ids, names}`
  - `stationed_port: {ids, names}`

---

### taskforces.json

Top-level value is `list[dict]`, one task force record per item (only task forces with at least one side-valid ship are emitted).

Common fields:

- `record_id: int`
- `mission: str`
- `nation: str | null`
- `flagship_id: int`
- `flagship_name: str | null`
- `commander: str | null`
- `start_of_day_x: int | null`
- `start_of_day_y: int | null`
- `end_of_day_x: int | null`
- `end_of_day_y: int | null`
- `target_x: int | null`
- `target_y: int | null`
- `target_location_id: int | null`
- `ships: list[dict]`
  - item keys: `name`, `ship_type`, `ship_class_name`, `leader_name`

Embedded structures:

- `relations: dict`
  - `flagship: {id, name}`
  - `commander: {name}`
  - `ships: {names, leaders}`

---

### turn.json

Single JSON object:

- `game_date: str | null` (MM/DD/YY when extractable)
- `game_turn: int | null`
- `scenario_name: str | null`
- `header_comment: str` (present when available)

---

### threats.json

Single JSON object containing map threat products from Operations Report + SIGINT + combat report location evidence.

Carrier threat evidence from combat reports is emitted when either enemy carriers are present or an air attack's attacking aircraft are all enemy carrier-capable (resolved via aircraft records and side-aware nation filtering).

Top-level fields:

- `game_date: str | null`
- `game_turn: int | null`
- `scenario_name: str | null`
- `threat_areas: list[ThreatArea]`
- `sub_threat_areas: list[ThreatArea]`
- `surface_threat_areas: list[ThreatArea]`
- `carrier_threat_areas: list[ThreatArea]`
- `invasion_threat_areas: list[InvasionThreat]`

`ThreatArea` object:

- `record_id: int`
- `position: {x: int, y: int}`
- `threat_score: int`
- `evidence_count: int`
- `threat_types: list[str]` (example values: `sub`, `surface`, `carrier`)
- `source_categories: list[str]` (parser categories from operations/sigint)
- `sample_texts: list[str]` (trimmed evidence samples)

`InvasionThreat` object:

- `record_id: int`
- `threat_base_position: {x: int, y: int}`
- `threat_base_name: str`
- `invasion_force_units: list[str]` (unit strings with origin suffix when known)
- `evidence_texts: list[str]`
- `evidence_count: int`

## Stability Notes

- Field names are derived from current exporter code and may evolve as parsing improves.
- Consumers should tolerate unknown additional keys.
- `null` is common for unresolved IDs, names, or coordinates.
