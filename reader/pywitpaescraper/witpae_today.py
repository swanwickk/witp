import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import TypeVar

import ctypes

from active_models import (
    ActiveAirgroup,
    ActiveBase,
    ActiveCombatReportHex,
    ActiveGroundUnit,
    ActiveInvasionThreat,
    ActiveLeader,
    ActivePilot,
    ActiveShip,
    ActiveTaskForce,
    ActiveThreatArea,
)
from pwsdll import (
    PWSDll,
    PWSHeader,
    PWSMinefieldInfo,
    PWSScenInfo,
    RecType,
    Nationality,
    Fate,
    Side,
    TaskForceMission,
    DeviceType,
    LocationType,
)
from pwsdll import (
    PWSAircraftInfo,
    PWSAirGroupInfo,
    PWSDeviceInfo,
    PWSLeaderInfo,
    PWSLocationInfo,
    PWSPilotInfo,
    PWSShipInfo,
    PWSShipClassInfo,
    PWSTaskGroupInfo,
)
from pwsdll import (
    aircraft_type_to_name,
    decode_aircraft_attrib_flags,
    decode_hq_kind,
    location_type_to_name,
    is_task_force_location_type,
    location_record_role,
    rank_to_name,
    ship_class_type_to_name,
)
import parse_combat_events
import parse_combat_report
import parse_operations_report
import parse_sigint


LOGGER = logging.getLogger("pywitpae.witpae_today")
T = TypeVar("T")


class WITPAE_Today:
    def __init__(self, dll_dir: Path, start_of_day_file: Path, end_of_day_file: Path, side: str) -> None:
        self._pws = PWSDll(dll_dir)
        self.side = side  # "ALLIED" or "JAPAN"
        self.start_of_day_file = start_of_day_file
        self.end_of_day_file = end_of_day_file
        self._intel_cache_path: Path | None = None
        self._intel_cache: dict = {"unit_origins": {}}
        self._start_day_game_date: str | None = None
        self._end_day_game_date: str | None = None
        self.active_airgroups: list[ActiveAirgroup] = []
        self.active_ships: list[ActiveShip] = []
        self.active_ground_units: list[ActiveGroundUnit] = []
        self.active_task_forces: list[ActiveTaskForce] = []
        self.active_bases: list[ActiveBase] = []
        self.active_leaders: list[ActiveLeader] = []
        self.active_pilots: list[ActivePilot] = []
        self.active_combat_reports: list[ActiveCombatReportHex] = []
        self.active_threat_areas: list[ActiveThreatArea] = []
        self.active_sub_threat_areas: list[ActiveThreatArea] = []
        self.active_surface_threat_areas: list[ActiveThreatArea] = []
        self.active_carrier_threat_areas: list[ActiveThreatArea] = []
        self.active_invasion_threat_areas: list[ActiveInvasionThreat] = []
        # Log file results — populated after PWS loading
        self.combat_events: parse_combat_events.CombatEventsLog | None = None
        self.combat_report: parse_combat_report.CombatReportLog | None = None
        self.operations_report: parse_operations_report.OperationsReportLog | None = None
        self.sigint: parse_sigint.SigintLog | None = None
        self.start_day_rec_type = self.load_day(start_of_day_file)
        # local patch (ekko): the upstream sample validation hard-codes USS Enterprise / Nimitz,
        # which do not exist in small scenarios such as Coral Sea — allow skipping it.
        import os as _os

        _validate = _os.environ.get("WITP_SKIP_SAMPLE_VALIDATION") != "1"
        self.end_day_rec_type = self.load_day(end_of_day_file, validate_samples=_validate)
        self._log_aircombat_taskforces(start_of_day_file, end_of_day_file)
        base_name = "Pearl Harbor" if side != "JAPAN" else "Tokyo"
        self._log_base_dump(end_of_day_file, base_name)
        self._load_log_files(end_of_day_file.parent)

    @staticmethod
    def _append_unique(items: list[str], incoming: list[str]) -> None:
        seen = set(items)
        for value in incoming:
            if value in seen:
                continue
            items.append(value)
            seen.add(value)

    def _build_active_combat_reports(self) -> None:
        self.active_combat_reports = []
        if self.combat_report is None:
            return

        by_xy: dict[tuple[int, int], ActiveCombatReportHex] = {}
        next_id = 0
        for action in self.combat_report.actions:
            if action.coordinates is None:
                continue
            x, y = action.coordinates
            key = (x, y)
            entry = by_xy.get(key)
            if entry is None:
                entry = ActiveCombatReportHex(record_id=next_id, position={"x": x, "y": y})
                by_xy[key] = entry
                next_id += 1

            entry.action_count += 1
            if action.action_type and action.action_type not in entry.action_types:
                entry.action_types.append(action.action_type)
            if action.location and action.location not in entry.locations:
                entry.locations.append(action.location)
            self._append_unique(entry.japanese_ships, action.japanese_ships)
            self._append_unique(entry.allied_ships, action.allied_ships)
            self._append_unique(entry.event_lines, action.event_lines)

        self.active_combat_reports = sorted(by_xy.values(), key=lambda v: v.action_count, reverse=True)
        LOGGER.info("[active-combat] aggregated_hexes=%s", len(self.active_combat_reports))

    def _build_active_threat_areas(self) -> None:
        self.active_threat_areas = []
        self.active_sub_threat_areas = []
        self.active_surface_threat_areas = []
        self.active_carrier_threat_areas = []
        self.active_invasion_threat_areas = []

        # Signals that imply hostile intent/movement/spotting and should contribute
        # to a map threat area when coordinates are present.
        weight_by_category = {
            "attack_plan": 5,
            "ship_movement": 4,
            "unit_location": 3,
            "coastwatcher": 4,
            "air_sighting": 3,
            "detection_event": 3,
            "sub_detection": 4,
            "task_force_event": 3,
            "task_force_coordination": 3,
            "transfer_event": 3,
            "auto_convoy": 2,
            "contact_report": 3,
            "radio_detection": 2,
            "combat_sub_involvement": 4,
            "combat_surface_involvement": 3,
            "combat_carrier_involvement": 5,
        }

        by_xy: dict[tuple[int, int], ActiveThreatArea] = {}
        next_id = 0

        def classify_threat_type(category: str, text: str) -> str:
            txt = text.upper()
            if category == "sub_detection" or " SUBMARINE" in txt or " SS " in f" {txt} ":
                return "sub"
            if re.search(r"\bCVL?\b|\bCVE\b|\bCARRIER\b", txt):
                return "carrier"
            return "surface"

        def upsert_threat(
            x: int,
            y: int,
            category: str,
            text: str,
            threat_type: str,
            display_radius_hexes: float | None = None,
            display_radius_source: str | None = None,
        ) -> None:
            nonlocal next_id
            key = (x, y)
            area = by_xy.get(key)
            if area is None:
                area = ActiveThreatArea(record_id=next_id, position={"x": x, "y": y})
                by_xy[key] = area
                next_id += 1

            area.evidence_count += 1
            area.threat_score += weight_by_category.get(category, 1)
            if threat_type not in area.threat_types:
                area.threat_types.append(threat_type)
            if category not in area.source_categories:
                area.source_categories.append(category)
            if text and text not in area.sample_texts and len(area.sample_texts) < 8:
                area.sample_texts.append(text)
            if threat_type == "carrier" and display_radius_hexes is not None:
                if display_radius_source == "enemy-carrier":
                    area.display_radius_hexes = float(display_radius_hexes)
                    area.display_radius_source = display_radius_source
                elif area.display_radius_source != "enemy-carrier":
                    if area.display_radius_hexes is None or float(display_radius_hexes) < float(area.display_radius_hexes):
                        area.display_radius_hexes = float(display_radius_hexes)
                        area.display_radius_source = display_radius_source

        if self.operations_report is not None:
            for event in self.operations_report.events:
                if event.coordinates is None:
                    continue
                if event.category == "other":
                    continue
                threat_type = classify_threat_type(event.category, event.text)
                display_radius_hexes = None
                display_radius_source = None
                upsert_threat(
                    event.coordinates[0],
                    event.coordinates[1],
                    event.category,
                    event.text,
                    threat_type,
                    display_radius_hexes=display_radius_hexes,
                    display_radius_source=display_radius_source,
                )

        # Add threat evidence from combat report locations.
        # Rules:
        # - sub: any combat at location involving SS/submarines
        # - surface: any combat at location involving ships
        # - carrier: enemy carrier ship is spotted OR an air attack where all
        #   attacking aircraft are enemy carrier-capable types
        snapshot = self._load_snapshot(self.end_of_day_file)
        aircrafts = snapshot.get("aircrafts", [])

        def norm_alnum(text: str) -> str:
            return re.sub(r"[^a-z0-9]", "", text.casefold())

        japanese_nations = {int(Nationality.IJARMY), int(Nationality.IJNAVY)}

        def is_enemy_aircraft_nation(nation_value: int) -> bool:
            if self.side == "JAPAN":
                return nation_value not in japanese_nations and nation_value != int(Nationality.NONATIONALITY)
            return nation_value in japanese_nations

        enemy_carrier_aircraft_ranges: dict[str, int] = {}
        for aircraft in aircrafts:
            ac_name = str(aircraft.get("name") or "").strip()
            if not ac_name:
                continue
            ac_nation = int(aircraft.get("nation", int(Nationality.NONATIONALITY)))
            if not is_enemy_aircraft_nation(ac_nation):
                continue
            normalized = norm_alnum(ac_name)
            if normalized:
                if bool(aircraft.get("carrier_capable", False)):
                    range_normal = int(aircraft.get("range_normal") or 0)
                    if range_normal > 0:
                        current_range = enemy_carrier_aircraft_ranges.get(normalized)
                        if current_range is None or range_normal < current_range:
                            enemy_carrier_aircraft_ranges[normalized] = range_normal
        enemy_carrier_plane_name_set = set(enemy_carrier_aircraft_ranges)

        carrier_ship_pattern = re.compile(r"\b(?:CVB|CVE|CVL|CV)\b")
        direct_carrier_reference_pattern = re.compile(r"\b(?:CVB|CVE|CVL|CV)\b|\bCARRIER\b(?!\s+AIRCRAFT)", re.IGNORECASE)
        ss_pattern = re.compile(r"\bSS\b|\bSUBMARINE\b")
        attacking_line_pattern = re.compile(
            r"^\s*\d+\s*x\s+(?P<aircraft>.+?)\s+(?:bombing|launching|strafing|sweeping|attacking)\b",
            re.IGNORECASE,
        )

        def attacking_aircraft_from_action(action: parse_combat_report.CombatAction) -> list[str]:
            names: list[str] = []
            in_attacking_block = False
            for raw_line in action.raw_lines:
                stripped = raw_line.strip()
                if not stripped:
                    if in_attacking_block:
                        break
                    continue

                if stripped.upper() == "AIRCRAFT ATTACKING:":
                    in_attacking_block = True
                    continue

                if not in_attacking_block:
                    continue

                match = attacking_line_pattern.match(stripped)
                if match:
                    aircraft_name = match.group("aircraft").strip()
                    if aircraft_name:
                        names.append(aircraft_name)
                    continue

                # Stop once next major section starts.
                if stripped.endswith(":"):
                    break

            return names

        def carrier_radius_from_aircraft_names(aircraft_names: list[str]) -> float | None:
            matched_ranges = [
                enemy_carrier_aircraft_ranges[normalized_name]
                for normalized_name in (norm_alnum(name) for name in aircraft_names)
                if normalized_name in enemy_carrier_aircraft_ranges
            ]
            if not matched_ranges:
                return None
            return float(min(matched_ranges))

        def carrier_radius_from_text(text: str) -> tuple[float | None, str | None]:
            if direct_carrier_reference_pattern.search(text):
                return 6.0, "enemy-carrier"

            normalized_text = norm_alnum(text)
            matched_ranges = [
                aircraft_range
                for aircraft_name, aircraft_range in enemy_carrier_aircraft_ranges.items()
                if aircraft_name in normalized_text
            ]
            if matched_ranges:
                return float(min(matched_ranges)), "carrier-aircraft"
            return None, None

        base_xy_by_normalized_name: dict[str, tuple[int, int]] = {}
        for (base_x, base_y), base_name in snapshot.get("base_names_by_xy", {}).items():
            normalized_base_name = norm_alnum(base_name)
            if normalized_base_name:
                base_xy_by_normalized_name[normalized_base_name] = (int(base_x), int(base_y))

        base_name_keys_by_length = sorted(base_xy_by_normalized_name.keys(), key=len, reverse=True)

        def infer_action_coordinates(action: parse_combat_report.CombatAction) -> tuple[int, int] | None:
            if action.coordinates is not None:
                return action.coordinates

            for candidate in (action.location or "", action.title, action.subtitle or ""):
                normalized_candidate = norm_alnum(candidate)
                if not normalized_candidate:
                    continue
                for normalized_base_name in base_name_keys_by_length:
                    if normalized_base_name in normalized_candidate:
                        return base_xy_by_normalized_name[normalized_base_name]

            return None

        if self.combat_report is not None:
            for action in self.combat_report.actions:
                coordinates = infer_action_coordinates(action)
                if coordinates is None:
                    continue

                x, y = coordinates
                own_ships = action.allied_ships if self.side == "ALLIED" else action.japanese_ships
                enemy_ships = action.japanese_ships if self.side == "ALLIED" else action.allied_ships
                any_ships = bool(action.japanese_ships or action.allied_ships)

                combined_lines = [
                    action.title,
                    action.subtitle or "",
                    *action.japanese_ships,
                    *action.allied_ships,
                    *action.event_lines,
                ]
                combined_text = " ".join(part for part in combined_lines if part).strip()
                combined_text_upper = combined_text.upper()
                action_type_upper = (action.action_type or "").upper()

                has_sub_involvement = bool(
                    ss_pattern.search(combined_text_upper)
                    or any("SS " in f" {ship.upper()} " for ship in action.japanese_ships)
                    or any("SS " in f" {ship.upper()} " for ship in action.allied_ships)
                )

                has_enemy_carrier_ship = any(
                    carrier_ship_pattern.search(ship.upper()) is not None
                    for ship in enemy_ships
                )
                has_carrier_spotted_in_combat = has_enemy_carrier_ship

                is_air_attack_action = (
                    "AIR ATTACK" in action_type_upper
                    or "AIR ATTACK" in combined_text_upper
                )

                attacking_aircraft_names = attacking_aircraft_from_action(action)
                normalized_attacking_aircraft_names = [
                    norm_alnum(name) for name in attacking_aircraft_names if norm_alnum(name)
                ]
                has_all_enemy_carrier_planes = bool(normalized_attacking_aircraft_names) and all(
                    attacking_name in enemy_carrier_plane_name_set
                    for attacking_name in normalized_attacking_aircraft_names
                )
                has_air_attack_with_enemy_carrier_plane = is_air_attack_action and has_all_enemy_carrier_planes
                carrier_display_radius_hexes = None
                carrier_display_radius_source = None
                if has_enemy_carrier_ship:
                    carrier_display_radius_hexes = 6.0
                    carrier_display_radius_source = "enemy-carrier"
                elif has_air_attack_with_enemy_carrier_plane:
                    carrier_display_radius_hexes = carrier_radius_from_aircraft_names(attacking_aircraft_names)
                    carrier_display_radius_source = "carrier-aircraft"

                if has_sub_involvement:
                    upsert_threat(
                        x,
                        y,
                        "combat_sub_involvement",
                        action.title,
                        "sub",
                    )

                if any_ships or own_ships or enemy_ships:
                    upsert_threat(
                        x,
                        y,
                        "combat_surface_involvement",
                        action.title,
                        "surface",
                    )

                if has_carrier_spotted_in_combat or has_air_attack_with_enemy_carrier_plane:
                    upsert_threat(
                        x,
                        y,
                        "combat_carrier_involvement",
                        action.title,
                        "carrier",
                        display_radius_hexes=carrier_display_radius_hexes,
                        display_radius_source=carrier_display_radius_source,
                    )

        if self.sigint is not None:
            for event in self.sigint.events:
                if event.coordinates is None:
                    continue
                if event.category == "other":
                    continue
                threat_type = classify_threat_type(event.category, event.text)
                display_radius_hexes = None
                display_radius_source = None
                if threat_type == "carrier":
                    display_radius_hexes, display_radius_source = carrier_radius_from_text(event.text)
                upsert_threat(
                    event.coordinates[0],
                    event.coordinates[1],
                    event.category,
                    event.text,
                    threat_type,
                    display_radius_hexes=display_radius_hexes,
                    display_radius_source=display_radius_source,
                )

        self.active_threat_areas = sorted(by_xy.values(), key=lambda v: v.threat_score, reverse=True)
        self.active_sub_threat_areas = [a for a in self.active_threat_areas if "sub" in a.threat_types]
        self.active_surface_threat_areas = [a for a in self.active_threat_areas if "surface" in a.threat_types]
        self.active_carrier_threat_areas = [a for a in self.active_threat_areas if "carrier" in a.threat_types]

        # Build base-centric invasion threats from SIGINT ground-unit planning lines.
        # Uses target base coordinates and retains invasion force origin as "from x,y".
        if self.sigint is not None:

            def norm_name(name: str) -> str:
                return re.sub(r"[^a-z0-9]", "", name.casefold())

            base_xy_by_name: dict[str, tuple[int, int, str]] = {}
            for loc in snapshot.get("locations", []):
                if loc.get("role") != "base":
                    continue
                nm = str(loc.get("name") or "").strip()
                if not nm:
                    continue
                base_xy_by_name[norm_name(nm)] = (int(loc["x"]), int(loc["y"]), nm)

            unit_origin_xy: dict[str, tuple[int, int]] = {}
            cache_origins: dict[str, list[int]] = self._intel_cache.setdefault("unit_origins", {})
            for event in self.sigint.events:
                if event.category != "unit_location":
                    continue
                if not event.subject or event.coordinates is None:
                    continue
                unit_origin_xy[event.subject] = event.coordinates
                cache_origins[norm_name(event.subject)] = [event.coordinates[0], event.coordinates[1]]

            # Include last known origins from historical cache.
            for unit_key, xy in cache_origins.items():
                if not isinstance(xy, list) or len(xy) != 2:
                    continue
                try:
                    x, y = int(xy[0]), int(xy[1])
                except (TypeError, ValueError):
                    continue
                unit_origin_xy[unit_key] = (x, y)

            # Fallback origins from current known ground-unit locations in PWS.
            ground_origin_xy_by_name: dict[str, tuple[int, int]] = {}
            for loc in snapshot.get("locations", []):
                if loc.get("role") != "ground_unit":
                    continue
                nm = str(loc.get("name") or "").strip()
                if not nm:
                    continue
                ground_origin_xy_by_name[norm_name(nm)] = (int(loc["x"]), int(loc["y"]))

            invasion_by_base: dict[tuple[int, int], ActiveInvasionThreat] = {}
            next_invasion_id = 0
            for event in self.sigint.events:
                if event.category != "attack_plan":
                    continue
                if not event.location:
                    continue

                target = base_xy_by_name.get(norm_name(event.location))
                if target is None:
                    continue

                bx, by, base_name = target
                key = (bx, by)
                threat = invasion_by_base.get(key)
                if threat is None:
                    threat = ActiveInvasionThreat(
                        record_id=next_invasion_id,
                        threat_base_position={"x": bx, "y": by},
                        threat_base_name=base_name,
                    )
                    invasion_by_base[key] = threat
                    next_invasion_id += 1

                threat.evidence_count += 1
                if event.text and event.text not in threat.evidence_texts and len(threat.evidence_texts) < 12:
                    threat.evidence_texts.append(event.text)

                unit_name = (event.subject or "UNKNOWN_UNIT").strip()
                origin = unit_origin_xy.get(unit_name)
                if origin is None:
                    origin = unit_origin_xy.get(norm_name(unit_name))
                if origin is None:
                    origin = ground_origin_xy_by_name.get(norm_name(unit_name))
                if origin is not None:
                    cache_origins[norm_name(unit_name)] = [origin[0], origin[1]]
                if origin is None:
                    unit_with_origin = f"{unit_name} from None,None"
                else:
                    unit_with_origin = f"{unit_name} from {origin[0]},{origin[1]}"
                if unit_with_origin not in threat.invasion_force_units:
                    threat.invasion_force_units.append(unit_with_origin)

            self.active_invasion_threat_areas = sorted(
                invasion_by_base.values(),
                key=lambda t: (t.evidence_count, len(t.invasion_force_units)),
                reverse=True,
            )

        LOGGER.info("[active-threat] threat_hexes=%s", len(self.active_threat_areas))
        LOGGER.info(
            "[active-threat] sub=%s surface=%s carrier=%s invasion=%s",
            len(self.active_sub_threat_areas),
            len(self.active_surface_threat_areas),
            len(self.active_carrier_threat_areas),
            len(self.active_invasion_threat_areas),
        )

    def _load_intel_cache(self, log_dir: Path) -> None:
        self._intel_cache_path = log_dir / f"intel_cache_{self.side.lower()}.json"
        self._intel_cache = {"unit_origins": {}}
        if self._intel_cache_path.exists():
            try:
                data = json.loads(self._intel_cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._intel_cache = data
                    self._intel_cache.setdefault("unit_origins", {})
            except Exception as exc:
                LOGGER.warning("[intel-cache] Failed to load %s: %s", self._intel_cache_path, exc)

    def _save_intel_cache(self) -> None:
        if self._intel_cache_path is None:
            return
        try:
            self._intel_cache_path.write_text(
                json.dumps(self._intel_cache, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as exc:
            LOGGER.warning("[intel-cache] Failed to save %s: %s", self._intel_cache_path, exc)

    @staticmethod
    def _decode_cstr(raw: bytes) -> str:
        # local patch (ekko): the CN scenario data stores names in GBK; try GBK before ASCII
        # so Chinese names come through instead of U+FFFD replacement characters.
        if isinstance(raw, (bytes, bytearray)):
            b = bytes(raw)
            for enc in ("gbk", "ascii"):
                try:
                    return b.decode(enc).strip("\x00").strip()
                except UnicodeDecodeError:
                    continue
            return b.decode("ascii", errors="replace").strip("\x00").strip()
        return str(raw).strip("\x00").strip()

    @staticmethod
    def _as_int(cval) -> int:
        if isinstance(cval, (bytes, bytearray)):
            return cval[0]
        return int(cval)

    @staticmethod
    def _arc_byte_to_compass_degrees(value: int) -> int:
        raw = max(0, min(36, int(value)))
        return raw * 10

    @classmethod
    def _mission_arc_fields(cls, percent: int, start: int, end: int) -> tuple[int | None, int | None]:
        if int(percent) <= 0:
            return None, None
        return cls._arc_byte_to_compass_degrees(start), cls._arc_byte_to_compass_degrees(end)

    @staticmethod
    def _enum_name(value: int, enum_type) -> str:
        try:
            return enum_type(value).name
        except ValueError:
            return f"UNKNOWN({value})"

    @staticmethod
    def _code_name(prefix: str, value: int) -> str:
        return f"{prefix}_{value}"

    @staticmethod
    def _ship_repair_mode_to_state(value: int) -> str:
        # Observed AE repair mode values.
        mode_map = {
            0: "readiness",
            1: "pier",
            2: "shipyard",
            3: "repair ship",
            4: "drydock",
        }
        return mode_map.get(int(value), f"unknown({int(value)})")

    def _find_name_index(
        self,
        records,
        target: str,
        allow_partial: bool = False,
    ) -> tuple[int | None, str | None]:
        target_lower = target.lower()
        for idx, record in enumerate(records):
            name = self._decode_cstr(record.name)
            if not name:
                continue
            name_lower = name.lower()
            if (allow_partial and target_lower in name_lower) or (not allow_partial and target_lower == name_lower):
                return idx, name
        return None, None

    def _log_sample_result(self, label: str, wanted: str, result: tuple[int | None, str | None]) -> bool:
        idx, actual = result
        if idx is None:
            LOGGER.error("[sample-check] FAIL %s: '%s' not found", label, wanted)
            return False
        LOGGER.info("[sample-check] PASS %s: wanted='%s' found_index=%s found_name='%s'", label, wanted, idx, actual)
        return True

    def _dump_ship(self, idx: int, ship, shipclass_info) -> None:
        d = self._decode_cstr
        sc = shipclass_info.shipclass[ship.shipClass] if shipclass_info else None
        ship_name = d(ship.name)
        ship_nation = self._enum_name(self._as_int(ship.nation), Nationality)
        class_name = "UNKNOWN_CLASS"
        class_type = "UNKNOWN_CLASS_TYPE"
        tonnage = 0
        if sc:
            class_name = d(sc.name)
            class_type = ship_class_type_to_name(self._as_int(sc.type))
            class_nation = self._enum_name(self._as_int(sc.nation), Nationality)
            tonnage = sc.tonnage
            LOGGER.info("%s %s is a %s %s of %s tons.",
                        ship_nation, ship_name, class_name, class_type, tonnage)
            LOGGER.info("[ship-detail] index=%s name='%s'", idx, ship_name)
            LOGGER.info("  nation=%s  class_id=%s", ship_nation, ship.shipClass)
            LOGGER.info("  class_name='%s'  class_type=%s  class_nation=%s  tonnage=%s",
                        class_name, class_type, class_nation, tonnage)
            LOGGER.info("  max_spd=%s  cruise_spd=%s  endurance=%s  durability=%s",
                        self._as_int(sc.maxSpd), self._as_int(sc.cruiseSpd), sc.endurance, sc.durability)
            LOGGER.info("  belt_armor=%s  deck_armor=%s  tower_armor=%s",
                        sc.beltArmor, sc.deckArmor, sc.towerArmor)
        else:
            LOGGER.info("%s %s is a %s %s of %s tons.",
                        ship_nation, ship_name, class_name, class_type, tonnage)
            LOGGER.info("[ship-detail] index=%s name='%s'", idx, ship_name)
            LOGGER.info("  nation=%s  class_id=%s", ship_nation, ship.shipClass)
        LOGGER.info("  ship_speed=%s  ship_endurance=%s  ship_base=%s  ship_tf=%s",
                    self._as_int(ship.shipSpeed), ship.shipEndurance, ship.shipBase, ship.shipTF)
        LOGGER.info("  fire_dmg=%s  sys_dmg=%s  float_dmg=%s  engine_dmg=%s",
                    self._as_int(ship.shipFireDmg), self._as_int(ship.shipSysDmg),
                    self._as_int(ship.shipFloatDmg), self._as_int(ship.shipEngineDmg))
        LOGGER.info("  repair_delay=%s  conversion_delay=%s  scuttled=%s",
                    ship.shipRepairDelay, ship.shipConversionDelay, self._as_int(ship.shipScuttled))

    def _dump_pilot(self, idx: int, pilot, airgroup_name: str) -> None:
        d = self._decode_cstr
        pilot_name = d(pilot.name)
        pilot_rank = rank_to_name(self._as_int(pilot.rank))
        pilot_fate = self._enum_name(self._as_int(pilot.fate), Fate)
        LOGGER.info("%s %s is %s with the %s and has %s kills.",
                    pilot_rank, pilot_name, pilot_fate, airgroup_name, pilot.kills)
        LOGGER.info("[pilot-detail] index=%s name='%s'", idx, d(pilot.name))
        LOGGER.info("  rank=%s  exp=%s  fatigue=%s  fate=%s  wound=%s",
                    rank_to_name(self._as_int(pilot.rank)), self._as_int(pilot.exp), self._as_int(pilot.fatigue),
                    pilot_fate, self._as_int(pilot.wound))
        LOGGER.info("  kills=%s  missions=%s  delay=%s",
                    pilot.kills, pilot.missions, pilot.delay)
        pilot_nation = self._enum_name(self._as_int(pilot.nationality), Nationality)
        pilot_type = aircraft_type_to_name(self._as_int(pilot.type))
        LOGGER.info("  nationality=%s  agrp=%s  type=%s",
                    pilot_nation, pilot.agrp, pilot_type)
        LOGGER.info("  skills: air=%s navB=%s navT=%s navS=%s recN=%s asw=%s tran=%s",
                    self._as_int(pilot.air), self._as_int(pilot.navB), self._as_int(pilot.navT), self._as_int(pilot.navS),
                    self._as_int(pilot.recN), self._as_int(pilot.asw), self._as_int(pilot.tran))
        LOGGER.info("  skills: grndB=%s lowN=%s lowG=%s staf=%s defN=%s",
                    self._as_int(pilot.grndB), self._as_int(pilot.lowN), self._as_int(pilot.lowG),
                    self._as_int(pilot.staf), self._as_int(pilot.defN))

    def _dump_leader(self, idx: int, leader) -> None:
        d = self._decode_cstr
        LOGGER.info("[leader-detail] index=%s name='%s'", idx, d(leader.name))
        leader_nation = self._enum_name(self._as_int(leader.nation), Nationality)
        leader_type = self._code_name("LEADER_TYPE", self._as_int(leader.type))
        LOGGER.info("  rank=%s  nation=%s  type=%s  delay=%s  pol_points=%s",
                    rank_to_name(self._as_int(leader.rank)), leader_nation,
                    leader_type, leader.delay, self._as_int(leader.polPoints))
        LOGGER.info("  leadership=%s  inspiration=%s  naval=%s  air=%s  land=%s  admin=%s  aggression=%s",
                    self._as_int(leader.leadership), self._as_int(leader.inspiration), self._as_int(leader.naval),
                    self._as_int(leader.air), self._as_int(leader.land), self._as_int(leader.admin),
                    self._as_int(leader.aggression))

    @staticmethod
    def _set_by_id(items: list[T], record_id: int, value: T) -> None:
        if record_id < 0:
            return
        if record_id >= len(items):
            items.extend([None] * (record_id + 1 - len(items)))
        items[record_id] = value

    @staticmethod
    def _get_by_id(items: list[T], record_id: int) -> T | None:
        if record_id < 0 or record_id >= len(items):
            return None
        return items[record_id]

    @staticmethod
    def _taskforce_id_from_ship_tf(ship_tf_value: int) -> int | None:
        # In observed saves, shipTF is a location-style ID where TF ids are offset by 14000.
        # Fall back to raw value for direct-id layouts.
        if ship_tf_value >= 14000:
            return ship_tf_value - 14000
        if ship_tf_value >= 0:
            return ship_tf_value
        return None

    def _nation_allowed(self, nation_value: int) -> bool:
        """Return True if nation_value belongs to the active side.

        --ALLIED: all non-IJA/IJN nationalities
        --JAPAN : IJARMY and IJNAVY only
        """
        japan_nations = {int(Nationality.IJARMY), int(Nationality.IJNAVY)}
        if self.side == "JAPAN":
            return nation_value in japan_nations
        return nation_value not in japan_nations

    def _minefield_side_allowed(self, side_value: int) -> bool:
        if self.side == "JAPAN":
            return side_value == int(Side.JAPAN)
        return side_value == int(Side.ALLIED)

    def _load_snapshot(self, day_file: Path, mode: int = 0) -> dict:
        snapshot = {
            "gameday": None,
            "game_date": None,
            "scenario_name": None,
            "header_comment": None,
            "taskgroups": [],
            "ships": [],
            "shipclasses": [],
            "leaders": [],
            "pilots": [],
            "airgroups": [],
            "aircrafts": [],
            "devices": [],
            "minefields": [],
            "locations": [],
            "locations_xy": {},
            "base_names_by_xy": {},
        }
        ctx = self._pws.new_context(RecType.SCENARIO)
        open_result = self._pws.pws_open_file(ctx, str(day_file), mode)
        if open_result == 0:
            raise RuntimeError(f"PWSOpenFile failed for {day_file} with code {open_result}")

        # PWSOpenFile can populate the first record immediately (typically HEADER).
        if ctx.PWSid == RecType.HEADER and ctx.PWSaddress.header:
            header = ctypes.cast(ctx.PWSaddress.header, ctypes.POINTER(PWSHeader)).contents
            snapshot["header_comment"] = self._decode_cstr(header.comment)
            timestamp_text = self._decode_cstr(header.timestamp)
            snapshot["game_date"] = (
                self._extract_mmddyy(snapshot["header_comment"])
                or self._extract_mmddyy(timestamp_text)
            )

        while True:
            self._pws.pws_get_next_item(ctx)
            if ctx.PWSopened == -1:
                break
            if ctx.PWSid == RecType.TASKFORCE and ctx.PWSaddress.taskgroups:
                taskgroups = ctypes.cast(
                    ctx.PWSaddress.taskgroups, ctypes.POINTER(PWSTaskGroupInfo)
                ).contents
                snapshot["taskgroups"] = [
                    {
                        "tfMission": self._as_int(tf.tfMission),
                        "tfFlagship": int(tf.tfFlagship),
                        "tfHomePort": int(tf.tfHomePort),
                    }
                    for tf in taskgroups.taskgroup
                ]
            elif ctx.PWSid == RecType.HEADER and ctx.PWSaddress.header:
                header = ctypes.cast(ctx.PWSaddress.header, ctypes.POINTER(PWSHeader)).contents
                snapshot["header_comment"] = self._decode_cstr(header.comment)
                timestamp_text = self._decode_cstr(header.timestamp)
                snapshot["game_date"] = (
                    self._extract_mmddyy(snapshot["header_comment"])
                    or self._extract_mmddyy(timestamp_text)
                )
            elif ctx.PWSid == RecType.SCENARIO and ctx.PWSaddress.sceninfo:
                sceninfo = ctypes.cast(ctx.PWSaddress.sceninfo, ctypes.POINTER(PWSScenInfo)).contents
                snapshot["gameday"] = int(sceninfo.gameturn)
                snapshot["scenario_name"] = self._decode_cstr(sceninfo.scenario)
                # ★2026-09-29 新增★ 胜负判定所需的权威比分就在结构里，原实现**丢弃**了
                #   （只取 gameday / scenario）→ 终局无法从存档核验胜负，只能靠游戏
                #   画面一闪而过的结算屏（实测被 end-turn 的连按 SPACE 跳过）。
                #   现一并导出：VP 比分 + 陆战损失计数。
                snapshot["japan_vp"] = int(sceninfo.japanVP)
                snapshot["allied_vp"] = int(sceninfo.alliedVP)
                snapshot["japan_lcu_loss"] = int(sceninfo.japanLCULoss)
                snapshot["allied_lcu_loss"] = int(sceninfo.alliedLCULoss)
            elif ctx.PWSid == RecType.SHIP and ctx.PWSaddress.ships:
                ships = ctypes.cast(ctx.PWSaddress.ships, ctypes.POINTER(PWSShipInfo)).contents
                snapshot["ships"] = [
                    {
                        "name": self._decode_cstr(ship.name),
                        "nation": self._as_int(ship.nation),
                        "shipClass": int(ship.shipClass),
                        "shipLeader": int(ship.shipLeader),
                        "shipDelay": int(ship.shipDelay),
                        "shipEndurance": int(ship.shipEndurance),
                        "shipBase": int(ship.shipBase),
                        "shipTF": int(ship.shipTF),
                        "shipUnitLoaded": int(ship.shipUnitLoaded),
                        "shipFireDmg": self._as_int(ship.shipFireDmg),
                        "shipSysDmg": self._as_int(ship.shipSysDmg),
                        "shipFloatDmg": self._as_int(ship.shipFloatDmg),
                        "shipEngineDmg": self._as_int(ship.shipEngineDmg),
                        "shipRepairMode": self._as_int(ship.shipRepairMode),
                        "shipRepairPriority": self._as_int(ship.shipRepairPriority),
                    }
                    for ship in ships.ship
                ]
            elif ctx.PWSid == RecType.SHIPCLASS and ctx.PWSaddress.shipclasses:
                shipclasses = ctypes.cast(
                    ctx.PWSaddress.shipclasses, ctypes.POINTER(PWSShipClassInfo)
                ).contents
                snapshot["shipclasses"] = [
                    {
                        "name": self._decode_cstr(shipclass.name),
                        "type": self._as_int(shipclass.type),
                        "tonnage": int(shipclass.tonnage),
                        "capacity": int(shipclass.capacity),
                        "troopCapacity": int(shipclass.troopCapacity),
                        "cargoCapacity": int(shipclass.cargoCapacity),
                        "liquidCapacity": int(shipclass.liquidCapacity),
                    }
                    for shipclass in shipclasses.shipclass
                ]
            elif ctx.PWSid == RecType.LEADER and ctx.PWSaddress.leaders:
                leaders = ctypes.cast(ctx.PWSaddress.leaders, ctypes.POINTER(PWSLeaderInfo)).contents
                snapshot["leaders"] = [
                    {
                        "name": self._decode_cstr(leader.name),
                        "rank": self._as_int(leader.rank),
                        "arriveDay": int(leader.delay),
                    }
                    for leader in leaders.leader
                ]
            elif ctx.PWSid == RecType.PILOT and ctx.PWSaddress.pilots:
                pilots = ctypes.cast(ctx.PWSaddress.pilots, ctypes.POINTER(PWSPilotInfo)).contents
                snapshot["pilots"] = [
                    {
                        "name": self._decode_cstr(pilot.name),
                        "rank": self._as_int(pilot.rank),
                        "arriveDay": int(pilot.delay),
                        "airgroupID": int(pilot.agrp),
                        "nation": self._as_int(pilot.nationality),
                    }
                    for pilot in pilots.pilot
                ]
            elif ctx.PWSid == RecType.AIRGROUP and ctx.PWSaddress.airgroups:
                airgroups = ctypes.cast(ctx.PWSaddress.airgroups, ctypes.POINTER(PWSAirGroupInfo)).contents
                snapshot["airgroups"] = [
                    {
                        "name": self._decode_cstr(ag.groupname),
                        "nation": self._as_int(ag.nation),
                        "acType": int(ag.acType),
                        "leaderID": int(ag.leaderID),
                        "hqID": int(ag.hqID),
                        "baseID": int(ag.baseID),
                        "reinforceBaseID": int(ag.reinforceBaseID),
                        "primaryMission": int(ag.primaryMission),
                        "pilotMorale": self._as_int(ag.pilotMorale),
                        "pilotExp": self._as_int(ag.pilotExp),
                        "secondaryMission": int(ag.secondaryMission),
                        "targetX": int(ag.targetX),
                        "targetY": int(ag.targetY),
                        "acReady": self._as_int(ag.acReady),
                        "acDamaged": self._as_int(ag.acDamaged),
                        "acMaintained": self._as_int(ag.acMaintained),
                        "acPercent": self._as_int(ag.acPercent),
                        "maxplanes": self._as_int(ag.maxplanes),
                        "pilotsAvail": int(ag.pilotsAvail),
                        "pilotsActive": int(ag.pilotsActive),
                        "acPctCAP": self._as_int(ag.acPctCAP),
                        "acPctLRCAP": self._as_int(ag.acPctLRCAP),
                        "acPctASW": self._as_int(ag.acPctASW),
                        "acPctSearch": self._as_int(ag.acPctSearch),
                        "acPctTrain": self._as_int(ag.acPctTrain),
                        "acPctRest": self._as_int(ag.acPctRest),
                        "acSearchASWStart": self._as_int(ag.acSearchASWStart),
                        "acSearchASWEnd": self._as_int(ag.acSearchASWEnd),
                        "acSearchNavStart": self._as_int(ag.acSearchNavStart),
                        "acSearchNavEnd": self._as_int(ag.acSearchNavEnd),
                        "delay": int(ag.delay),
                    }
                    for ag in airgroups.airgroup
                ]
            elif ctx.PWSid == RecType.AIRCRAFT and ctx.PWSaddress.aircrafts:
                aircrafts = ctypes.cast(ctx.PWSaddress.aircrafts, ctypes.POINTER(PWSAircraftInfo)).contents
                decoded_aircrafts = []
                for ac in aircrafts.aircraft:
                    attrib_value = self._as_int(ac.attrib)
                    attrib_flags = decode_aircraft_attrib_flags(attrib_value)
                    decoded_aircrafts.append(
                        {
                            "name": self._decode_cstr(ac.name),
                            "type": self._as_int(ac.type),
                            "nation": self._as_int(ac.nation),
                            "range_normal": self._as_int(ac.rangeNormal),
                            "attrib": attrib_value,
                            "carrier_capable": attrib_flags["carrier_capable"],
                            "heavy_bomber_capable": attrib_flags["heavy_bomber"],
                            "medium_bomber_capable": attrib_flags["medium_bomber"],
                            "light_bomber_capable": attrib_flags["light_bomber"],
                            "amphibian_capable": attrib_flags["amphibian"],
                            "attack_bomber_capable": attrib_flags["attack_bomber"],
                            "float_plane_capable": attrib_flags["float_plane"],
                            "reserved_bit_7_set": attrib_flags["reserved_bit_7"],
                            "attrib_flags": attrib_flags,
                        }
                    )
                snapshot["aircrafts"] = decoded_aircrafts
            elif ctx.PWSid == RecType.DEVICE and ctx.PWSaddress.devices:
                devices = ctypes.cast(ctx.PWSaddress.devices, ctypes.POINTER(PWSDeviceInfo)).contents
                snapshot["devices"] = [
                    {
                        "name": self._decode_cstr(dev.name),
                        "type": int(dev.type),
                        "load": int(dev.load),
                        "troop_size": int(dev.load)
                        if int(dev.type) in {int(DeviceType.SQUAD), int(DeviceType.ENGR)}
                        else 0,
                        "cargo_size": 0
                        if int(dev.type) in {int(DeviceType.SQUAD), int(DeviceType.ENGR)}
                        else int(dev.load),
                    }
                    for dev in devices.device
                ]
            elif ctx.PWSid == RecType.MINES and ctx.PWSaddress.minefields:
                minefields = ctypes.cast(
                    ctx.PWSaddress.minefields, ctypes.POINTER(PWSMinefieldInfo)
                ).contents
                snapshot["minefields"] = [
                    {
                        "x": int(minefield.x),
                        "y": int(minefield.y),
                        "side": int(minefield.side),
                        "number": int(minefield.number),
                    }
                    for minefield in minefields.minefield
                    if int(minefield.x) > 0 and int(minefield.y) > 0 and int(minefield.number) > 0
                ]
            elif ctx.PWSid == RecType.LOCATION and ctx.PWSaddress.locations:
                locations = ctypes.cast(
                    ctx.PWSaddress.locations, ctypes.POINTER(PWSLocationInfo)
                ).contents
                snapshot["locations"] = [
                    {
                        "id": i,
                        "name": self._decode_cstr(loc.name),
                        "nation": self._as_int(loc.nation),
                        "type": int(loc.type),
                        "role": location_record_role(int(loc.type)),
                        "x": int(loc.X),
                        "y": int(loc.Y),
                        "arrive": int(loc.arrive),
                        "locNear": int(loc.locNear),
                        "prepPercent": int(loc.prepPercent),
                        "toe": int(loc.TOE),
                        "attachedHQ": int(loc.attachedHQ),
                        "HQtype": int(loc.HQtype),
                        "leaderID": int(loc.leaderID),
                        "port": int(loc.port),
                        "airfield": int(loc.airfield),
                        "shipRepair": int(loc.shipRepair),
                        "supply": int(loc.supply),
                        "supplyNeeded": int(loc.supplyNeeded),
                        "supportReq": int(loc.supportReq),
                        "supportTotal": int(loc.supportTotal),
                        "AVsupportReq": int(loc.AVsupportReq),
                        "AVsupportTotal": int(loc.AVsupportTotal),
                        "resources": int(loc.resources),
                        "resourcesNeeded": int(loc.resourcesNeeded),
                        "oil": int(loc.oil),
                        "oilNeeded": int(loc.oilNeeded),
                        "fuel": int(loc.fuel),
                        "fuelRequested": int(loc.fuelRequested),
                        "runwayDmg": int(loc.runwayDmg),
                        "portDmg": int(loc.portDmg),
                        "airfieldDmg": int(loc.airfieldDmg),
                        "destX": int(loc.destX),
                        "destY": int(loc.destY),
                        "loadedUnit": int(loc.loadedUnit),
                        "parentID": int(loc.parentID),
                        "shipCount": int(loc.shipCount),
                        "deviceID": [int(v) for v in loc.deviceID],
                        "deviceNumber": [int(v) for v in loc.deviceNumber],
                        "deviceTOENum": [int(v) for v in loc.deviceTOENum],
                    }
                    for i, loc in enumerate(locations.location)
                ]
                snapshot["locations_xy"] = {
                    i: (int(loc.X), int(loc.Y))
                    for i, loc in enumerate(locations.location)
                }
                base_names_by_xy: dict[tuple[int, int], str] = {}
                for loc in locations.location:
                    x, y = int(loc.X), int(loc.Y)
                    role = location_record_role(int(loc.type))
                    if role != "base":
                        continue
                    name = self._decode_cstr(loc.name)
                    if name:
                        base_names_by_xy[(x, y)] = name
                snapshot["base_names_by_xy"] = base_names_by_xy

        close_result = self._pws.pws_close_file(ctx)
        if close_result == 0:
            raise RuntimeError(f"PWSCloseFile failed for {day_file} with code {close_result}")
        return snapshot

    @staticmethod
    def _arrived_by_gameday(arrive_day: int | None, gameday: int | None) -> bool:
        # Convention: 0/non-positive or missing values are treated as already present.
        if gameday is None or arrive_day is None:
            return True
        if arrive_day <= 0:
            return True
        return arrive_day <= gameday

    def _log_base_dump(self, day_file: Path, base_name: str) -> None:
        snapshot = self._load_snapshot(day_file)
        locations = snapshot["locations"]
        leaders = snapshot["leaders"]
        ships = snapshot["ships"]
        shipclasses = snapshot["shipclasses"]
        airgroups = snapshot["airgroups"]
        aircrafts = snapshot["aircrafts"]
        devices = snapshot["devices"]
        gameday = snapshot["gameday"]

        base = None
        for loc in locations:
            if loc["role"] == "base" and loc["name"].casefold() == base_name.casefold():
                base = loc
                break
        if base is None:
            LOGGER.warning("[base-dump] Base '%s' not found", base_name)
            return

        base_id = int(base["id"])
        base_xy = (int(base["x"]), int(base["y"]))

        LOGGER.info("[base-dump] %s id=%s at %s,%s", base["name"], base_id, base_xy[0], base_xy[1])
        LOGGER.info(
            "[base-dump] port=%s airfield=%s ship_repair=%s supply=%s resources=%s fuel=%s runway_dmg=%s port_dmg=%s airfield_dmg=%s",
            base["port"],
            base["airfield"],
            base["shipRepair"],
            base["supply"],
            base["resources"],
            base["fuel"],
            base["runwayDmg"],
            base["portDmg"],
            base["airfieldDmg"],
        )

        facmach_entries: list[str] = []
        for dev_id, qty in zip(base["deviceID"], base["deviceNumber"]):
            if qty <= 0:
                continue
            if dev_id < 0 or dev_id >= len(devices):
                continue
            dev = devices[dev_id]
            if int(dev["type"]) != int(DeviceType.FACMACH):
                continue
            facmach_entries.append(f"{dev['name']} x{qty}")
        LOGGER.info("[base-dump] FACMACH: %s", ", ".join(facmach_entries) if facmach_entries else "none")

        resident_airgroups = [
            ag
            for ag in airgroups
            if int(ag["baseID"]) == base_id
            and ag["name"]
            and self._nation_allowed(int(ag["nation"]))
            and self._arrived_by_gameday(int(ag["delay"]), gameday)
        ]
        LOGGER.info("[base-dump] Airgroups (%s)", len(resident_airgroups))
        for ag in resident_airgroups:
            ac_id = int(ag["acType"])
            ac_name = "UNKNOWN_AIRCRAFT"
            ac_type_name = "UNKNOWN_AIRCRAFT_TYPE"
            if 0 <= ac_id < len(aircrafts):
                ac = aircrafts[ac_id]
                ac_name = ac["name"] or f"aircraft[{ac_id}]"
                ac_type_name = aircraft_type_to_name(int(ac["type"]))

            leader_txt = "UNKNOWN_LEADER"
            leader_id = int(ag["leaderID"])
            if 0 <= leader_id < len(leaders):
                lr = leaders[leader_id]
                if self._arrived_by_gameday(int(lr.get("arriveDay", 0)), gameday):
                    leader_txt = f"{rank_to_name(int(lr['rank']))} {lr['name']}"

            LOGGER.info("  - %s | leader=%s | aircraft=%s %s", ag["name"], leader_txt, ac_type_name, ac_name)

        resident_ships = [
            s
            for s in ships
            if int(s["shipBase"]) == base_id
            and s["name"]
            and self._nation_allowed(int(s["nation"]))
            and self._arrived_by_gameday(int(s["shipDelay"]), gameday)
        ]
        LOGGER.info("[base-dump] Ships (%s)", len(resident_ships))
        for ship in resident_ships:
            class_id = int(ship["shipClass"])
            ship_type = "UNKNOWN_CLASS_TYPE"
            ship_class_name = "UNKNOWN_CLASS"
            if 0 <= class_id < len(shipclasses):
                sc = shipclasses[class_id]
                ship_type = ship_class_type_to_name(int(sc["type"]))
                ship_class_name = sc["name"] or f"class[{class_id}]"

            leader_txt = "UNKNOWN_LEADER"
            leader_id = int(ship["shipLeader"])
            if 0 <= leader_id < len(leaders):
                lr = leaders[leader_id]
                if self._arrived_by_gameday(int(lr.get("arriveDay", 0)), gameday):
                    leader_txt = f"{rank_to_name(int(lr['rank']))} {lr['name']}"

            LOGGER.info("  - %s | leader=%s | type=%s class=%s", ship["name"], leader_txt, ship_type, ship_class_name)

        resident_ground = [
            loc for loc in locations
            if loc["role"] == "ground_unit"
            and (int(loc["locNear"]) == base_id or (int(loc["x"]), int(loc["y"])) == base_xy)
            and self._nation_allowed(int(loc["nation"]))
            and self._arrived_by_gameday(int(loc["arrive"]), gameday)
        ]
        LOGGER.info("[base-dump] Ground units (%s)", len(resident_ground))
        for gu in resident_ground:
            leader_txt = "UNKNOWN_LEADER"
            leader_id = int(gu["leaderID"])
            if 0 <= leader_id < len(leaders):
                lr = leaders[leader_id]
                if self._arrived_by_gameday(int(lr.get("arriveDay", 0)), gameday):
                    leader_txt = f"{rank_to_name(int(lr['rank']))} {lr['name']}"
            unit_type = location_type_to_name(int(gu["type"]))
            LOGGER.info("  - %s | leader=%s | type=%s", gu["name"], leader_txt, unit_type)

    def _log_aircombat_taskforces(self, start_of_day_file: Path, end_of_day_file: Path) -> None:
        start_snapshot = self._load_snapshot(start_of_day_file)
        end_snapshot = self._load_snapshot(end_of_day_file)
        end_gameday = end_snapshot["gameday"]

        start_taskgroups = start_snapshot["taskgroups"]
        start_ships = start_snapshot["ships"]
        start_locations_xy = start_snapshot["locations_xy"]

        taskgroups = end_snapshot["taskgroups"]
        ships = end_snapshot["ships"]
        shipclasses = end_snapshot["shipclasses"]
        leaders = end_snapshot["leaders"]
        end_locations_xy = end_snapshot["locations_xy"]
        end_base_names_by_xy = end_snapshot["base_names_by_xy"]
        if not (taskgroups and ships and shipclasses and leaders):
            LOGGER.warning("[aircombat-tf] Missing snapshot data; cannot produce task force listing")
            return

        ships_by_tf_id: dict[int, list[dict]] = {}
        for ship in ships:
            if not self._arrived_by_gameday(int(ship.get("shipDelay", 0)), end_gameday):
                continue
            if not self._nation_allowed(int(ship["nation"])):
                continue
            tf_id = self._taskforce_id_from_ship_tf(int(ship["shipTF"]))
            if tf_id is None:
                continue
            ships_by_tf_id.setdefault(tf_id, []).append(ship)

        for tf_id, tf in enumerate(taskgroups):
            if int(tf["tfMission"]) != int(TaskForceMission.AIRCOMBAT):
                continue

            flagship_id = int(tf["tfFlagship"])
            flagship_name = "UNKNOWN_SHIP"
            class_type_name = "UNKNOWN_CLASS_TYPE"
            class_name = "UNKNOWN_CLASS"
            tonnage = 0
            commander = "UNKNOWN_LEADER"
            tf_nation = "UNKNOWN_NATION"

            if 0 <= flagship_id < len(ships):
                ship = ships[flagship_id]
                if not self._arrived_by_gameday(int(ship.get("shipDelay", 0)), end_gameday):
                    continue
                if not self._nation_allowed(int(ship["nation"])):
                    continue
                flagship_name = ship["name"] or f"ship[{flagship_id}]"
                tf_nation = self._enum_name(int(ship["nation"]), Nationality)
                class_id = int(ship["shipClass"])
                if 0 <= class_id < len(shipclasses):
                    shipclass = shipclasses[class_id]
                    class_type_name = ship_class_type_to_name(int(shipclass["type"]))
                    class_name = shipclass["name"] or f"class[{class_id}]"
                    tonnage = int(shipclass["tonnage"])
                leader_id = int(ship["shipLeader"])
                if 0 <= leader_id < len(leaders):
                    leader = leaders[leader_id]
                    if self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                        leader_rank = rank_to_name(int(leader["rank"]))
                        leader_name = leader["name"] or f"leader[{leader_id}]"
                        commander = f"{leader_rank} {leader_name}"

            manifest_parts: list[str] = []
            tf_ships = ships_by_tf_id.get(tf_id, [])
            for ship in tf_ships:
                class_id = int(ship["shipClass"])
                ship_name = ship["name"] or "UNKNOWN_SHIP"
                ship_type = "UNKNOWN_CLASS_TYPE"
                ship_class_name = "UNKNOWN_CLASS"
                if 0 <= class_id < len(shipclasses):
                    sc = shipclasses[class_id]
                    ship_type = ship_class_type_to_name(int(sc["type"]))
                    ship_class_name = sc["name"] or f"class[{class_id}]"
                is_flagship = (ship_name == flagship_name)
                prefix = "Flagship: " if is_flagship else ""
                manifest_parts.append(f"{prefix}{ship_type} {ship_name} ({ship_class_name})")
            manifest = ", ".join(manifest_parts) if manifest_parts else "none"

            start_tf = start_taskgroups[tf_id] if start_taskgroups and tf_id < len(start_taskgroups) else None

            start_xy = None
            end_xy = None
            if 0 <= flagship_id < len(ships):
                end_ship = ships[flagship_id]
                end_xy = end_locations_xy.get(int(end_ship["shipTF"]))
                if start_ships and flagship_id < len(start_ships):
                    start_ship = start_ships[flagship_id]
                    start_xy = start_locations_xy.get(int(start_ship["shipTF"]))

            if start_xy is None and start_tf is not None:
                start_xy = start_locations_xy.get(int(start_tf["tfHomePort"]))
            if end_xy is None:
                end_xy = end_locations_xy.get(int(tf["tfHomePort"]))

            sx, sy = start_xy if start_xy is not None else (-1, -1)
            ex, ey = end_xy if end_xy is not None else (-1, -1)

            if (sx, sy) == (ex, ey):
                base_name = end_base_names_by_xy.get((ex, ey))
                if base_name:
                    movement_suffix = f" (stationary at base {base_name})"
                else:
                    movement_suffix = " (stationary, no base record at coordinates)"
            else:
                hexes_moved = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
                if hexes_moved > 6:
                    movement_suffix = f" ({hexes_moved:.2f} hexes moved, long-range move)"
                else:
                    movement_suffix = f" ({hexes_moved:.2f} hexes moved)"

            LOGGER.info(
                "[aircombat-tf] %s TaskForce#%s has flagship %s a %s of class %s and %s and went from %s,%s to %s,%s%s. Ships: %s",
                tf_nation,
                tf_id,
                flagship_name,
                class_type_name,
                class_name,
                f"commanded by {commander}",
                sx,
                sy,
                ex,
                ey,
                movement_suffix,
                manifest,
            )

    def _load_log_files(self, log_dir: Path) -> None:
        """Load and parse all game log files from log_dir."""
        self._load_intel_cache(log_dir)
        prefix = "a" if self.side != "JAPAN" else "j"
        log_files = {
            "combat_events":     log_dir / "CombatEvents.txt",
            "combat_report":     log_dir / "combatreport.txt",
            "operations_report": log_dir / f"{prefix}operationsreport.txt",
            "sigint":            log_dir / f"{prefix}sigint.txt",
        }
        for key, path in log_files.items():
            if not path.exists():
                LOGGER.warning("[log-files] Expected file not found: %s", path)
            else:
                LOGGER.debug("[log-files] Located: %s", path)

        self.combat_events = (
            parse_combat_events.load(log_files["combat_events"])
            if log_files["combat_events"].exists() else None
        )
        self.combat_report = (
            parse_combat_report.load(log_files["combat_report"])
            if log_files["combat_report"].exists() else None
        )
        self.operations_report = (
            parse_operations_report.load(log_files["operations_report"], self.side)
            if log_files["operations_report"].exists() else None
        )
        self.sigint = (
            parse_sigint.load(log_files["sigint"], self.side)
            if log_files["sigint"].exists() else None
        )
        self._build_active_combat_reports()
        self._build_active_threat_areas()
        self._save_intel_cache()

    @staticmethod
    def _write_json_records(path: Path, records: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(records, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")

    @staticmethod
    def _extract_mmddyy(text: str | None) -> str | None:
        if not text:
            return None
        match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", text)
        if not match:
            return None
        month, day, year = match.groups()
        return f"{month.zfill(2)}/{day.zfill(2)}/{year}"

    def _read_game_date_from_header(self, day_file: Path, mode: int = 0) -> str | None:
        ctx = self._pws.new_context(RecType.SCENARIO)
        open_result = self._pws.pws_open_file(ctx, str(day_file), mode)
        if open_result == 0:
            return None

        try:
            if ctx.PWSid == RecType.HEADER and ctx.PWSaddress.header:
                header = ctypes.cast(ctx.PWSaddress.header, ctypes.POINTER(PWSHeader)).contents
                comment_text = self._decode_cstr(header.comment)
                timestamp_text = self._decode_cstr(header.timestamp)
                return self._extract_mmddyy(comment_text) or self._extract_mmddyy(timestamp_text)

            while True:
                self._pws.pws_get_next_item(ctx)
                if ctx.PWSopened == -1:
                    break
                if ctx.PWSid == RecType.HEADER and ctx.PWSaddress.header:
                    header = ctypes.cast(ctx.PWSaddress.header, ctypes.POINTER(PWSHeader)).contents
                    comment_text = self._decode_cstr(header.comment)
                    timestamp_text = self._decode_cstr(header.timestamp)
                    return self._extract_mmddyy(comment_text) or self._extract_mmddyy(timestamp_text)
        finally:
            self._pws.pws_close_file(ctx)

        return None

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")

    @staticmethod
    def _threat_area_payload(area: ActiveThreatArea) -> dict:
        payload = {
            "record_id": int(area.record_id),
            "position": {
                "x": int(area.position.get("x", 0)),
                "y": int(area.position.get("y", 0)),
            },
            "threat_score": int(area.threat_score),
            "evidence_count": int(area.evidence_count),
            "threat_types": [str(v) for v in area.threat_types],
            "source_categories": [str(v) for v in area.source_categories],
            "sample_texts": [str(v) for v in area.sample_texts],
        }
        if area.display_radius_hexes is not None:
            payload["display_radius_hexes"] = float(area.display_radius_hexes)
        if area.display_radius_source:
            payload["display_radius_source"] = str(area.display_radius_source)
        return payload

    @staticmethod
    def _invasion_threat_payload(threat: ActiveInvasionThreat) -> dict:
        return {
            "record_id": int(threat.record_id),
            "threat_base_position": {
                "x": int(threat.threat_base_position.get("x", 0)),
                "y": int(threat.threat_base_position.get("y", 0)),
            },
            "threat_base_name": str(threat.threat_base_name),
            "invasion_force_units": [str(v) for v in threat.invasion_force_units],
            "evidence_texts": [str(v) for v in threat.evidence_texts],
            "evidence_count": int(threat.evidence_count),
        }

    def export_json(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        start_snapshot = self._load_snapshot(self.start_of_day_file)
        end_snapshot = self._load_snapshot(self.end_of_day_file)
        end_gameday = end_snapshot.get("gameday")

        start_locations_xy = start_snapshot.get("locations_xy", {})
        end_locations_xy = end_snapshot.get("locations_xy", {})

        locations = end_snapshot.get("locations", [])
        ships = end_snapshot.get("ships", [])
        shipclasses = end_snapshot.get("shipclasses", [])
        leaders = end_snapshot.get("leaders", [])
        pilots = end_snapshot.get("pilots", [])
        airgroups = end_snapshot.get("airgroups", [])
        aircrafts = end_snapshot.get("aircrafts", [])
        devices = end_snapshot.get("devices", [])
        taskgroups = end_snapshot.get("taskgroups", [])

        location_by_id = {int(loc["id"]): loc for loc in locations}
        map_x_min = 1
        map_x_max = 232
        map_y_min = 1
        map_y_max = 205

        def is_in_map_hex_range(x: int | None, y: int | None) -> bool:
            if x is None or y is None:
                return True
            return map_x_min <= x <= map_x_max and map_y_min <= y <= map_y_max

        def location_leader_name(location_record: dict) -> str | None:
            leader_id = int(location_record.get("leaderID", -1))
            if leader_id < 0 or leader_id >= len(leaders):
                return None
            leader = leaders[leader_id]
            if not self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                return None
            return leader.get("name") or None

        local_fleet_hq_by_base: dict[int, dict] = {}
        local_hq_units_by_base: dict[int, list[dict]] = {}
        for loc in locations:
            if str(loc.get("role") or "") != "ground_unit":
                continue
            if int(loc.get("type", -1)) != int(LocationType.HQ):
                continue
            if not self._nation_allowed(int(loc.get("nation", 0))):
                continue
            if not self._arrived_by_gameday(int(loc.get("arrive", 0)), end_gameday):
                continue

            linked_id = int(loc.get("locNear", -1))
            linked = location_by_id.get(linked_id)
            base_id = None
            if linked and linked.get("role") == "base":
                base_id = int(linked["id"])
            else:
                lx, ly = int(loc.get("x", 0)), int(loc.get("y", 0))
                for base in locations:
                    if base.get("role") == "base" and int(base.get("x", -1)) == lx and int(base.get("y", -1)) == ly:
                        base_id = int(base["id"])
                        break
            if base_id is None:
                continue

            attached_hq_id = int(loc.get("attachedHQ", -1))
            attached_hq = location_by_id.get(attached_hq_id)
            attached_hq_name = (attached_hq.get("name") or "") if attached_hq else ""
            unit_name = str(loc.get("name") or "")

            candidate_name = None
            if "fleet" in attached_hq_name.casefold():
                candidate_name = attached_hq_name
            elif "fleet" in unit_name.casefold():
                candidate_name = unit_name

            if candidate_name is None:
                continue

            local_hq_units_by_base.setdefault(base_id, []).append(
                {
                    "unit_id": int(loc["id"]),
                    "unit_name": unit_name or None,
                    "attached_hq_id": attached_hq_id if attached_hq else None,
                    "attached_hq_name": attached_hq_name or None,
                    "leader_name": location_leader_name(loc),
                }
            )

            if base_id not in local_fleet_hq_by_base:
                local_fleet_hq_by_base[base_id] = {
                    "name": candidate_name,
                    "source_unit_id": int(loc["id"]),
                    "source_unit_name": unit_name or None,
                    "source_leader_name": location_leader_name(loc),
                }

        def _resolve_ship_record_idx(candidate_ref_id: int) -> int | None:
            """Resolve potential ship references from either ship-index or location-style ids."""
            if candidate_ref_id < 0:
                return None

            candidates: list[int] = []

            # Common encoding used by baseID/locNear when referencing ship slots.
            if candidate_ref_id >= num_base_locs:
                candidates.append(candidate_ref_id - num_base_locs)

            # Some datasets may already provide ship record index directly.
            candidates.append(candidate_ref_id)

            seen: set[int] = set()
            for idx in candidates:
                if idx in seen:
                    continue
                seen.add(idx)
                if idx < 0 or idx >= len(ships):
                    continue
                return idx
            return None

        def loaded_ship_payload(candidate_ship_id: int) -> dict | None:
            ship_idx = _resolve_ship_record_idx(candidate_ship_id)
            if ship_idx is None:
                return None

            ship = ships[ship_idx]
            if not self._nation_allowed(int(ship["nation"])):
                return None
            if not self._arrived_by_gameday(int(ship.get("shipDelay", 0)), end_gameday):
                return None
            ship_name = ship.get("name") or None
            if not ship_name:
                return None
            ship_xy = end_locations_xy.get(int(ship.get("shipTF", -1)))
            task_force_id = self._taskforce_id_from_ship_tf(int(ship.get("shipTF", -1)))
            return {
                "id": ship_idx,
                "name": ship_name,
                "x": ship_xy[0] if ship_xy else None,
                "y": ship_xy[1] if ship_xy else None,
                "task_force_id": task_force_id,
            }

        pilot_count_by_airgroup: dict[int, int] = {}
        pilot_ids_by_airgroup: dict[int, list[int]] = {}
        pilot_names_by_airgroup: dict[int, list[str]] = {}
        active_pilot_records: list[dict] = []
        for pidx, pilot in enumerate(pilots):
            pilot_nation = int(pilot.get("nation", 0))
            if not self._nation_allowed(pilot_nation):
                continue
            if not self._arrived_by_gameday(int(pilot.get("arriveDay", 0)), end_gameday):
                continue

            pilot_airgroup_id = int(pilot.get("airgroupID", -1))
            pilot_name = pilot.get("name") or None
            active_pilot_records.append(
                {
                    "record_id": pidx,
                    "name": pilot_name,
                    "nation": self._enum_name(pilot_nation, Nationality),
                    "rank_name": rank_to_name(int(pilot.get("rank", 0))),
                    "airgroup_id": pilot_airgroup_id,
                }
            )
            if pilot_airgroup_id < 0:
                continue

            pilot_count_by_airgroup[pilot_airgroup_id] = pilot_count_by_airgroup.get(pilot_airgroup_id, 0) + 1
            pilot_ids_by_airgroup.setdefault(pilot_airgroup_id, []).append(pidx)
            if pilot_name:
                pilot_names_by_airgroup.setdefault(pilot_airgroup_id, []).append(pilot_name)

        # Direct link: airgroup.baseID is a location id; ids >= len(locations) encode ship slots.
        num_base_locs = len(locations)

        ship_records: list[dict] = []
        ships_by_tf_id: dict[int, list[dict]] = {}
        docked_tonnage_by_base: dict[int, int] = {}
        docked_troops_by_base: dict[int, int] = {}
        docked_cargo_by_base: dict[int, int] = {}
        docked_count_by_base: dict[int, int] = {}
        for idx, ship in enumerate(ships):
            nation = int(ship["nation"])
            if not self._nation_allowed(nation):
                continue
            if not self._arrived_by_gameday(int(ship.get("shipDelay", 0)), end_gameday):
                continue

            class_id = int(ship.get("shipClass", -1))
            class_name = None
            class_type_name = None
            class_tonnage = 0
            if 0 <= class_id < len(shipclasses):
                shipclass = shipclasses[class_id]
                class_name = shipclass.get("name") or None
                class_type_name = ship_class_type_to_name(int(shipclass["type"]))
                class_tonnage = int(shipclass.get("tonnage", 0))
                aircraft_capacity = int(shipclass.get("capacity", 0))
                troop_capacity = int(shipclass.get("troopCapacity", 0))
                cargo_capacity = int(shipclass.get("cargoCapacity", 0))
                liquid_capacity = int(shipclass.get("liquidCapacity", 0))
            else:
                aircraft_capacity = 0
                troop_capacity = 0
                cargo_capacity = 0
                liquid_capacity = 0

            leader_id = int(ship.get("shipLeader", -1))
            leader_name = None
            leader_rank = None
            if 0 <= leader_id < len(leaders):
                leader = leaders[leader_id]
                if self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                    leader_name = leader.get("name") or None
                    leader_rank = rank_to_name(int(leader["rank"]))

            assigned_location_id = int(ship.get("shipBase", -1))
            assigned_location = location_by_id.get(assigned_location_id)
            assigned_location_name = assigned_location.get("name") if assigned_location else None
            assigned_location_role = assigned_location.get("role") if assigned_location else None
            assigned_hq_id = int(assigned_location.get("attachedHQ", -1)) if assigned_location else -1
            assigned_hq = location_by_id.get(assigned_hq_id)
            assigned_hq_name = assigned_hq.get("name") if assigned_hq else None

            endurance = int(ship.get("shipEndurance", 0))
            endurance_per_day = max(0, int(endurance / 40)) if endurance > 0 else 0

            tf_location_id = int(ship.get("shipTF", -1))
            end_xy = end_locations_xy.get(tf_location_id)
            tf_id = self._taskforce_id_from_ship_tf(tf_location_id)
            if tf_id is not None:
                ships_by_tf_id.setdefault(tf_id, []).append(ship)

            if assigned_location and assigned_location.get("role") == "base":
                docked_tonnage_by_base[assigned_location_id] = docked_tonnage_by_base.get(assigned_location_id, 0) + class_tonnage
                docked_troops_by_base[assigned_location_id] = docked_troops_by_base.get(assigned_location_id, 0) + troop_capacity
                docked_cargo_by_base[assigned_location_id] = docked_cargo_by_base.get(assigned_location_id, 0) + cargo_capacity
                docked_count_by_base[assigned_location_id] = docked_count_by_base.get(assigned_location_id, 0) + 1

            ship_records.append(
                {
                    "record_id": idx,
                    "name": ship.get("name") or None,
                    "nation": self._enum_name(nation, Nationality),
                    "ship_class_id": class_id,
                    "ship_class_name": class_name,
                    "ship_class_type_name": class_type_name,
                    "ship_class_tonnage": class_tonnage,
                    "tonnage": class_tonnage,
                    "aircraft_capacity": aircraft_capacity,
                    "troop_capacity": troop_capacity,
                    "cargo_capacity": cargo_capacity,
                    "liquid_capacity": liquid_capacity,
                    "current_state": self._ship_repair_mode_to_state(int(ship.get("shipRepairMode", 0))),
                    "repair_mode": int(ship.get("shipRepairMode", 0)),
                    "repair_priority": int(ship.get("shipRepairPriority", 0)),
                    "Sys": int(ship.get("shipSysDmg", 0)),
                    "Flt": int(ship.get("shipFloatDmg", 0)),
                    "Eng": int(ship.get("shipEngineDmg", 0)),
                    "Fire": int(ship.get("shipFireDmg", 0)),
                    "system_damage": int(ship.get("shipSysDmg", 0)),
                    "flotation_damage": int(ship.get("shipFloatDmg", 0)),
                    "engine_damage": int(ship.get("shipEngineDmg", 0)),
                    "fire_damage": int(ship.get("shipFireDmg", 0)),
                    "leader_id": leader_id,
                    "leader_name": leader_name,
                    "leader_rank": leader_rank,
                    "assigned_location_id": assigned_location_id,
                    "assigned_location_name": assigned_location_name,
                    "assigned_location_role": assigned_location_role,
                    "assigned_hq_id": assigned_hq_id if assigned_hq else None,
                    "assigned_hq_name": assigned_hq_name,
                    "base_chain_hq_id": assigned_hq_id if assigned_hq else None,
                    "base_chain_hq_name": assigned_hq_name,
                    "local_fleet_hq_name": local_fleet_hq_by_base.get(assigned_location_id, {}).get("name"),
                    "local_fleet_hq_source_unit_id": local_fleet_hq_by_base.get(assigned_location_id, {}).get("source_unit_id"),
                    "local_fleet_hq_source_unit_name": local_fleet_hq_by_base.get(assigned_location_id, {}).get("source_unit_name"),
                    "local_fleet_hq_source_leader_name": local_fleet_hq_by_base.get(assigned_location_id, {}).get("source_leader_name"),
                    "endurance": endurance,
                    "endurance_per_day": endurance_per_day,
                    "ship_base_id": int(ship.get("shipBase", -1)),
                    "stationed_at_base_id": assigned_location_id if assigned_location and assigned_location.get("role") == "base" else None,
                    "stationed_at_base_name": assigned_location_name if assigned_location and assigned_location.get("role") == "base" else None,
                    "task_force_id": tf_id,
                    "x": end_xy[0] if end_xy else None,
                    "y": end_xy[1] if end_xy else None,
                    "loaded_ground_unit_id": None,
                    "loaded_ground_unit_name": None,
                    "loaded_ground_unit_type_name": None,
                    "loaded_airgroup_cargo_id": None,
                    "loaded_airgroup_cargo_name": None,
                    "_ship_unit_loaded_raw": int(ship.get("shipUnitLoaded", -1)),
                }
            )

        ground_records: list[dict] = []
        skipped_ground_out_of_range = 0
        base_records: list[dict] = []
        for loc in locations:
            nation = int(loc["nation"])
            role_probe = str(loc.get("role") or "")
            # ★★2026-10-14 修（战场基地坐标全丢的根因）★★
            #   原实现对**所有** location 一律套 `_nation_allowed`（side=JAPAN 只放行
            #   IJARMY/IJNAVY）。但**基地的 nation 是开局的属国**，与「谁在打这一局」无关：
            #   实测珊瑚海剧本里 Port Moresby/Rabaul/Lae 的 nation = AUSTRALIAN(7)、
            #   Tulagi = CW(15) —— 于是全部被当作「敌方」过滤掉，导出只剩日本本土
            #   （nation=1/2 的 204 个），**整个战场的基地从读层消失**：
            #   bases.json 里 PM/Rabaul/Lae/Tulagi 全无 ⇒ 参谋部威胁圈、
            #   敌机场锚点、前推位、基地归属全部失真（表现为「距 PM 98124 格」）。
            #   ⇒ 基地必须**全量导出**（含敌方属地）——归属是战场核心情报；
            #     双盲原则只隐藏敌方**编队/舰船明细**，不隐藏基地的存在与要素。
            if role_probe != "base" and not self._nation_allowed(nation):
                continue
            if not self._arrived_by_gameday(int(loc.get("arrive", 0)), end_gameday):
                continue

            role = str(loc.get("role") or "")
            location_id = int(loc["id"])
            loc_type = int(loc["type"])

            if role == "ground_unit":
                linked_id = int(loc.get("locNear", -1))
                linked = location_by_id.get(linked_id)
                loaded_ship = loaded_ship_payload(linked_id)
                start_xy = start_locations_xy.get(location_id)
                end_xy = end_locations_xy.get(location_id)
                if not is_in_map_hex_range(
                    end_xy[0] if end_xy else None,
                    end_xy[1] if end_xy else None,
                ):
                    skipped_ground_out_of_range += 1
                    continue
                destination_x = int(loc.get("destX", 0))
                destination_y = int(loc.get("destY", 0))
                destination_x = destination_x if destination_x > 0 else None
                destination_y = destination_y if destination_y > 0 else None
                attached_hq = None
                if linked and int(linked.get("type", -1)) == int(LocationType.HQ):
                    attached_hq = linked
                if attached_hq is None:
                    attached_hq = location_by_id.get(int(loc.get("attachedHQ", -1)))
                prep_target = None
                if linked and linked.get("role") in {"base", "beach"}:
                    prep_target = linked

                local_base_id = linked_id if linked and linked.get("role") == "base" and loaded_ship is None else None
                local_fleet_hq = local_fleet_hq_by_base.get(local_base_id, {}) if local_base_id is not None else {}
                base_chain_hq_id = int(attached_hq.get("id")) if attached_hq else None
                base_chain_hq_name = (attached_hq.get("name") or None) if attached_hq else None
                local_fleet_hq_name = local_fleet_hq.get("name")
                effective_hq_name = local_fleet_hq_name or base_chain_hq_name
                effective_hq_id = local_fleet_hq.get("source_unit_id") or base_chain_hq_id
                effective_hq_source = "local_fleet_hq" if local_fleet_hq_name else ("base_chain_hq" if base_chain_hq_name else None)

                device_type_breakdown: dict[str, int] = {}
                assigned_device_count = 0
                toe_device_count = 0
                troop_device_count = 0
                equipment_device_count = 0
                total_load_cost_assigned = 0
                total_load_cost_toe = 0
                cargo_cost_assigned = 0
                cargo_cost_toe = 0
                troop_load_cost_assigned = 0
                troop_load_cost_toe = 0
                infantry_count = 0
                infantry_count_toe = 0
                vehicle_count = 0
                vehicle_count_toe = 0
                gun_count = 0
                gun_count_toe = 0
                engineer_count = 0
                unit_device_details: list[dict] = []
                for dev_id, qty, toe_qty in zip(
                    loc.get("deviceID", []),
                    loc.get("deviceNumber", []),
                    loc.get("deviceTOENum", []),
                ):
                    if qty <= 0 and toe_qty <= 0:
                        continue
                    dev_name = None
                    dev_type_name = "UNKNOWN_DEVICE_TYPE"
                    dev_type_value = -1
                    if 0 <= dev_id < len(devices):
                        dev = devices[dev_id]
                        dev_name = dev.get("name") or None
                        dev_type_value = int(dev.get("type", -1))
                        dev_type_name = self._enum_name(dev_type_value, DeviceType)
                        dev_load = int(dev.get("load", 0))
                        dev_troop_size = int(dev.get("troop_size", 0))
                        dev_cargo_size = int(dev.get("cargo_size", 0))
                    else:
                        dev_load = 0
                        dev_troop_size = 0
                        dev_cargo_size = 0

                    assigned_device_count += int(qty)
                    toe_device_count += int(toe_qty)
                    total_load_cost_assigned += int(qty) * dev_load
                    total_load_cost_toe += int(toe_qty) * dev_load
                    cargo_cost_assigned += int(qty) * dev_cargo_size
                    cargo_cost_toe += int(toe_qty) * dev_cargo_size
                    device_type_breakdown[dev_type_name] = device_type_breakdown.get(dev_type_name, 0) + int(qty)

                    if dev_type_value in {int(DeviceType.SQUAD), int(DeviceType.ENGR)}:
                        troop_device_count += int(qty)
                        troop_load_cost_assigned += int(qty) * dev_troop_size
                        troop_load_cost_toe += int(toe_qty) * dev_troop_size
                    else:
                        equipment_device_count += int(qty)

                    if dev_type_value == int(DeviceType.SQUAD):
                        infantry_count += int(qty)
                        infantry_count_toe += int(toe_qty)
                    if dev_type_value == int(DeviceType.ENGR):
                        engineer_count += int(qty)
                        infantry_count_toe += int(toe_qty)
                    if dev_type_value == int(DeviceType.VEHICLE):
                        vehicle_count += int(qty)
                        vehicle_count_toe += int(toe_qty)
                    if dev_type_value == int(DeviceType.AFV):
                        vehicle_count_toe += int(toe_qty)
                    if dev_type_value in {
                        int(DeviceType.ARMYWEAP),
                        int(DeviceType.DPGUN),
                        int(DeviceType.NAVYGUN),
                        int(DeviceType.FLAK),
                    }:
                        gun_count += int(qty)
                        gun_count_toe += int(toe_qty)

                    unit_device_details.append(
                        {
                            "device_id": int(dev_id),
                            "device_name": dev_name,
                            "device_type": dev_type_name,
                            "device_load": dev_load,
                            "device_troop_size": dev_troop_size,
                            "device_cargo_size": dev_cargo_size,
                            "assigned": int(qty),
                            "toe": int(toe_qty),
                        }
                    )

                leader_id = int(loc.get("leaderID", -1))
                leader_name = None
                leader_rank = None
                if 0 <= leader_id < len(leaders):
                    leader = leaders[leader_id]
                    if self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                        leader_name = leader.get("name") or None
                        leader_rank = rank_to_name(int(leader["rank"]))

                naval_support = int(loc.get("supportTotal", 0))
                aviation_support = int(loc.get("AVsupportTotal", 0))
                other_troops_estimate = max(
                    0,
                    troop_device_count - infantry_count - engineer_count + naval_support + aviation_support,
                )

                ground_records.append(
                    {
                        "record_id": location_id,
                        "name": loc.get("name") or None,
                        "nation": self._enum_name(nation, Nationality),
                        "unit_type_name": location_type_to_name(loc_type),
                        "hq_kind": decode_hq_kind(int(loc.get("HQtype", 0))) if loc_type == int(LocationType.HQ) else None,
                        "leader_id": leader_id if leader_id >= 0 else None,
                        "leader_name": leader_name,
                        "leader_rank": leader_rank,
                        "arrive_day": int(loc.get("arrive", 0)),
                        "prep_percent": int(loc.get("prepPercent", 0)),
                        "prep_target_id": int(prep_target.get("id")) if prep_target else None,
                        "prep_target_name": (prep_target.get("name") or None) if prep_target else None,
                        "prep_target_x": int(prep_target.get("x", 0)) if prep_target else None,
                        "prep_target_y": int(prep_target.get("y", 0)) if prep_target else None,
                        "destination_x": destination_x,
                        "destination_y": destination_y,
                        "attached_hq_id": base_chain_hq_id,
                        "attached_hq_name": base_chain_hq_name,
                        "area_command": str(base_chain_hq_name) if base_chain_hq_name else "Independent",
                        "base_chain_hq_id": base_chain_hq_id,
                        "base_chain_hq_name": base_chain_hq_name,
                        "local_fleet_hq_name": local_fleet_hq_name,
                        "local_fleet_hq_source_unit_id": local_fleet_hq.get("source_unit_id"),
                        "local_fleet_hq_source_unit_name": local_fleet_hq.get("source_unit_name"),
                        "local_fleet_hq_source_leader_name": local_fleet_hq.get("source_leader_name"),
                        "effective_hq_id": effective_hq_id,
                        "effective_hq_name": effective_hq_name,
                        "effective_hq_source": effective_hq_source,
                        "loaded_on_ship_id": loaded_ship["id"] if loaded_ship else None,
                        "loaded_on_ship_name": loaded_ship["name"] if loaded_ship else None,
                        "task_force_id": loaded_ship.get("task_force_id") if loaded_ship else None,
                        "at_base_id": local_base_id,
                        "stationed_at_base_id": local_base_id,
                        "stationed_at_base_name": (linked.get("name") or None) if local_base_id is not None and linked else None,
                        "unit_toe_id": int(loc.get("toe", 0)),
                        "supplies_current": int(loc.get("supply", 0)),
                        "supplies_needed": int(loc.get("supplyNeeded", 0)),
                        "total_load_cost_assigned": total_load_cost_assigned,
                        "total_load_cost_toe": total_load_cost_toe,
                        "cargo_cost_assigned": cargo_cost_assigned,
                        "cargo_cost_toe": cargo_cost_toe,
                        "troop_load_cost_assigned": troop_load_cost_assigned,
                        "troop_load_cost_toe": troop_load_cost_toe,
                        "troop_cost_estimate": troop_load_cost_toe,
                        "troop_device_count": troop_device_count,
                        "equipment_device_count": equipment_device_count,
                        "infantry_count": infantry_count,
                        "infantry_count_toe": infantry_count_toe,
                        "vehicle_count": vehicle_count_toe,
                        "vehicle_count_assigned": vehicle_count,
                        "gun_count": gun_count_toe,
                        "gun_count_assigned": gun_count,
                        "engineer_count": engineer_count,
                        "other_troops_estimate": other_troops_estimate,
                        "naval_support": naval_support,
                        "naval_support_required": int(loc.get("supportReq", 0)),
                        "aviation_support": aviation_support,
                        "aviation_support_required": int(loc.get("AVsupportReq", 0)),
                        "assigned_device_count": assigned_device_count,
                        "toe_device_count": toe_device_count,
                        "device_type_breakdown": device_type_breakdown,
                        "device_details": unit_device_details,
                        "start_of_day_x": start_xy[0] if start_xy else None,
                        "start_of_day_y": start_xy[1] if start_xy else None,
                        "end_of_day_x": end_xy[0] if end_xy else None,
                        "end_of_day_y": end_xy[1] if end_xy else None,
                    }
                )

            if role == "base":
                base_port = int(loc.get("port", 0))
                docked_tonnage_limit = max(0, base_port * 10000)
                docked_tonnage_current = max(
                    docked_tonnage_by_base.get(location_id, 0),
                    int(loc.get("shipCount", 0)),
                )
                ship_repair_points = int(loc.get("shipRepair", 0))
                shipyard_device_points = 0
                for dev_id, qty in zip(loc.get("deviceID", []), loc.get("deviceNumber", [])):
                    if int(qty) <= 0:
                        continue
                    if 0 <= int(dev_id) < len(devices):
                        device_name = str(devices[int(dev_id)].get("name") or "")
                        if "repair shipyard" in device_name.casefold() or "shipyard" in device_name.casefold():
                            shipyard_device_points += int(qty)
                shipyard_capacity_tons = max(ship_repair_points, shipyard_device_points) * 1000
                base_attached_hq = location_by_id.get(int(loc.get("attachedHQ", -1)))
                base_attached_hq_name = (base_attached_hq.get("name") or None) if base_attached_hq else None
                base_records.append(
                    {
                        "record_id": location_id,
                        "name": loc.get("name") or None,
                        "nation": self._enum_name(nation, Nationality),
                        "area_command": str(base_attached_hq_name) if base_attached_hq_name else "Independent",
                        "x": int(loc.get("x", 0)),
                        "y": int(loc.get("y", 0)),
                        "port": base_port,
                        "airfield": int(loc.get("airfield", 0)),
                        "ship_repair": ship_repair_points,
                        "ship_repair_device_points": shipyard_device_points,
                        "ship_repair_capacity_tons": shipyard_capacity_tons,
                        "supply": int(loc.get("supply", 0)),
                        "supply_needed": int(loc.get("supplyNeeded", 0)),
                        "resources": int(loc.get("resources", 0)),
                        "resources_needed": int(loc.get("resourcesNeeded", 0)),
                        "oil": int(loc.get("oil", 0)),
                        "oil_needed": int(loc.get("oilNeeded", 0)),
                        "fuel": int(loc.get("fuel", 0)),
                        "fuel_needed": int(loc.get("fuelRequested", 0)),
                        "docked_ship_count": docked_count_by_base.get(location_id, 0),
                        "docked_tonnage_current": docked_tonnage_current,
                        "docked_tonnage_capacity": docked_tonnage_limit,
                        "docked_cargo_capacity": docked_cargo_by_base.get(location_id, 0),
                        "docked_troop_capacity": docked_troops_by_base.get(location_id, 0),
                        "runway_damage": int(loc.get("runwayDmg", 0)),
                        "port_damage": int(loc.get("portDmg", 0)),
                        "airfield_damage": int(loc.get("airfieldDmg", 0)),
                        "stationed_ground": [],
                        "stationed_air": [],
                        "stationed_port": [],
                        "stationed_ground_ids": [],
                        "stationed_ground_names": [],
                        "stationed_air_ids": [],
                        "stationed_air_names": [],
                        "stationed_port_ids": [],
                        "stationed_port_names": [],
                    }
                )

        if skipped_ground_out_of_range:
            LOGGER.info(
                "[export-json] excluded ground units out_of_map_range=%s",
                skipped_ground_out_of_range,
            )

        airgroup_records: list[dict] = []
        for idx, airgroup in enumerate(airgroups):
            nation = int(airgroup["nation"])
            if not self._nation_allowed(nation):
                continue
            if not self._arrived_by_gameday(int(airgroup.get("delay", 0)), end_gameday):
                continue

            aircraft_id = int(airgroup.get("acType", -1))
            aircraft_name = None
            aircraft_type_name = None
            aircraft_range = None
            if 0 <= aircraft_id < len(aircrafts):
                aircraft = aircrafts[aircraft_id]
                aircraft_name = aircraft.get("name") or None
                aircraft_type_name = aircraft_type_to_name(int(aircraft["type"]))
                aircraft_range = int(aircraft.get("range_normal", 0))

            leader_id = int(airgroup.get("leaderID", -1))
            leader_name = None
            leader_rank = None
            if 0 <= leader_id < len(leaders):
                leader = leaders[leader_id]
                if self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                    leader_name = leader.get("name") or None
                    leader_rank = rank_to_name(int(leader["rank"]))

            hq_id = int(airgroup.get("hqID", -1))
            direct_hq = location_by_id.get(hq_id)
            direct_hq_name = (direct_hq.get("name") or None) if direct_hq else None

            base_id = int(airgroup.get("baseID", 0))
            # base_id >= num_base_locs means it is a virtual ship location ID;
            # the ship record index is base_id - num_base_locs (direct encoding in the save).
            ship_record_idx = base_id - num_base_locs if base_id >= num_base_locs else -1
            base_loc = location_by_id.get(base_id) if ship_record_idx < 0 else None
            loaded_ship = loaded_ship_payload(ship_record_idx) if ship_record_idx >= 0 else None
            base_xy = (
                (int(base_loc["x"]), int(base_loc["y"]))
                if base_loc is not None and loaded_ship is None
                else None
            )
            rebase_base_id = int(airgroup.get("reinforceBaseID", -1))
            rebase_base_loc = location_by_id.get(rebase_base_id)
            rebase_xy = (
                (int(rebase_base_loc["x"]), int(rebase_base_loc["y"]))
                if rebase_base_loc is not None
                else None
            )
            is_rebasing = rebase_base_id > 0 and rebase_base_id != base_id and rebase_base_loc is not None

            local_hq_candidates = local_hq_units_by_base.get(base_id, [])
            local_air_hq = next(
                (
                    h
                    for h in local_hq_candidates
                    if any(
                        token in ((h.get("unit_name") or "") + " " + (h.get("attached_hq_name") or "")).casefold()
                        for token in ["air", "usaaf", "fleet air"]
                    )
                ),
                None,
            )
            local_fleet_hq = next(
                (
                    h
                    for h in local_hq_candidates
                    if "fleet" in ((h.get("unit_name") or "") + " " + (h.get("attached_hq_name") or "")).casefold()
                ),
                None,
            )
            percent_asw = int(airgroup.get("acPctASW", 0))
            percent_search = int(airgroup.get("acPctSearch", 0))
            asw_arc_start, asw_arc_end = self._mission_arc_fields(
                percent_asw,
                int(airgroup.get("acSearchASWStart", 0)),
                int(airgroup.get("acSearchASWEnd", 0)),
            )
            search_arc_start, search_arc_end = self._mission_arc_fields(
                percent_search,
                int(airgroup.get("acSearchNavStart", 0)),
                int(airgroup.get("acSearchNavEnd", 0)),
            )

            airgroup_records.append(
                {
                    "record_id": idx,
                    "name": airgroup.get("name") or None,
                    "nation": self._enum_name(nation, Nationality),
                    "aircraft_id": aircraft_id,
                    "aircraft_name": aircraft_name,
                    "aircraft_type_name": aircraft_type_name,
                    "aircraft_range": aircraft_range,
                    "aircraft_active": int(airgroup.get("acReady", 0)),
                    "aircraft_damaged": int(airgroup.get("acDamaged", 0)),
                    "aircraft_max": int(airgroup.get("maxplanes", 0)),
                    "aircraft_being_repaired": int(airgroup.get("acMaintained", 0)),
                    "pilot_count_assigned": int(pilot_count_by_airgroup.get(idx, 0)),
                    "pilot_ids": pilot_ids_by_airgroup.get(idx, []),
                    "pilot_names": pilot_names_by_airgroup.get(idx, []),
                    "pilot_count_active": int(airgroup.get("pilotsActive", 0)),
                    "pilot_count_available": int(airgroup.get("pilotsAvail", 0)),
                    "leader_id": leader_id,
                    "leader_name": leader_name,
                    "leader_rank": leader_rank,
                    "assigned_hq_id": hq_id if direct_hq else None,
                    "assigned_hq_name": direct_hq_name,
                    "area_command": str(direct_hq_name) if direct_hq_name else "Independent",
                    "local_air_hq_name": local_air_hq.get("attached_hq_name") if local_air_hq else None,
                    "local_air_hq_source_unit_id": local_air_hq.get("unit_id") if local_air_hq else None,
                    "local_air_hq_source_unit_name": local_air_hq.get("unit_name") if local_air_hq else None,
                    "local_fleet_hq_name": local_fleet_hq.get("attached_hq_name") if local_fleet_hq else None,
                    "local_fleet_hq_source_unit_id": local_fleet_hq.get("unit_id") if local_fleet_hq else None,
                    "local_fleet_hq_source_unit_name": local_fleet_hq.get("unit_name") if local_fleet_hq else None,
                    "primary_mission_code": int(airgroup.get("primaryMission", -1)),
                    "pilot_morale": int(airgroup.get("pilotMorale", -1)),
                    "pilot_exp": int(airgroup.get("pilotExp", -1)),
                    "secondary_mission_code": int(airgroup.get("secondaryMission", -1)),
                    "percent_cap": int(airgroup.get("acPctCAP", 0)),
                    "percent_lrcap": int(airgroup.get("acPctLRCAP", 0)),
                    "percent_asw": percent_asw,
                    "percent_search": percent_search,
                    "percent_train": int(airgroup.get("acPctTrain", 0)),
                    "percent_rest": int(airgroup.get("acPctRest", 0)),
                    "asw_arc_start": asw_arc_start,
                    "asw_arc_end": asw_arc_end,
                    "search_arc_start": search_arc_start,
                    "search_arc_end": search_arc_end,
                    "base_id": base_id,
                    "stationed_at_base_id": int(base_loc["id"]) if base_loc is not None and loaded_ship is None and base_loc.get("role") == "base" else None,
                    "stationed_at_base_name": (base_loc.get("name") or None) if base_loc is not None and loaded_ship is None and base_loc.get("role") == "base" else None,
                    "rebase_target_base_id": rebase_base_id if is_rebasing else None,
                    "rebase_target_base_name": (rebase_base_loc.get("name") or None) if is_rebasing else None,
                    "rebase_target_x": rebase_xy[0] if is_rebasing and rebase_xy else None,
                    "rebase_target_y": rebase_xy[1] if is_rebasing and rebase_xy else None,
                    "is_rebasing": is_rebasing,
                    "x": loaded_ship["x"] if loaded_ship else (base_xy[0] if base_xy else None),
                    "y": loaded_ship["y"] if loaded_ship else (base_xy[1] if base_xy else None),
                    "target_x": int(airgroup.get("targetX", 0)) if int(airgroup.get("targetX", 0)) > 0 else None,
                    "target_y": int(airgroup.get("targetY", 0)) if int(airgroup.get("targetY", 0)) > 0 else None,
                    "stationed_on_ship_id": loaded_ship["id"] if loaded_ship else None,
                    "stationed_on_ship_name": loaded_ship["name"] if loaded_ship else None,
                    "loaded_as_cargo_on_ship_id": None,
                    "loaded_as_cargo_on_ship_name": None,
                    "loaded_on_ship_id": loaded_ship["id"] if loaded_ship else None,
                    "loaded_on_ship_name": loaded_ship["name"] if loaded_ship else None,
                }
            )

        # Build ship -> airgroups from the direct loaded_on_ship_id link, then inject.
        airgroups_by_ship_id: dict[int, list[dict]] = {}
        for ag in airgroup_records:
            sid = ag.get("loaded_on_ship_id")
            if sid is None:
                continue
            airgroups_by_ship_id.setdefault(sid, []).append(
                {
                    "record_id": ag["record_id"],
                    "name": ag["name"],
                    "aircraft_id": ag["aircraft_id"],
                    "aircraft_name": ag["aircraft_name"],
                    "aircraft_type_name": ag["aircraft_type_name"],
                    "aircraft_active": ag["aircraft_active"],
                    "aircraft_max": ag["aircraft_max"],
                }
            )
        for ship_rec in ship_records:
            ship_rec["airgroups"] = airgroups_by_ship_id.get(ship_rec["record_id"], [])

        # Build reciprocal ship <-> loaded ground-unit links.
        loaded_ground_by_ship_id: dict[int, dict] = {}
        for unit in ground_records:
            sid = unit.get("loaded_on_ship_id")
            if sid is None:
                continue
            loaded_ground_by_ship_id.setdefault(
                int(sid),
                {
                    "record_id": unit.get("record_id"),
                    "name": unit.get("name"),
                },
            )

        ground_by_id: dict[int, dict] = {
            int(gr["record_id"]): gr
            for gr in ground_records
            if gr.get("record_id") is not None
        }

        def _resolve_ground_record_from_loaded(raw_loaded: int) -> dict | None:
            if raw_loaded <= 0:
                return None

            # Observed layouts may encode ground refs either directly as location id
            # or as a location-offset id (similar to ship/base references).
            candidate_ids = [raw_loaded]
            if raw_loaded >= num_base_locs:
                candidate_ids.append(raw_loaded - num_base_locs)

            seen: set[int] = set()
            for candidate_id in candidate_ids:
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                rec = ground_by_id.get(candidate_id)
                if rec is not None:
                    return rec
            return None

        def _resolve_ground_name_from_locations(raw_loaded: int) -> tuple[int | None, str | None, str | None]:
            if raw_loaded <= 0:
                return (None, None, None)

            candidate_ids = [raw_loaded]
            if raw_loaded >= num_base_locs:
                candidate_ids.append(raw_loaded - num_base_locs)

            seen: set[int] = set()
            for candidate_id in candidate_ids:
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                loc = location_by_id.get(candidate_id)
                if not loc:
                    continue
                if str(loc.get("role") or "") != "ground_unit":
                    continue
                loc_name = str(loc.get("name") or "").strip() or None
                loc_type_name = location_type_to_name(int(loc.get("type", -1))) if loc.get("type") is not None else None
                if loc_name:
                    return (candidate_id, loc_name, loc_type_name)
            return (None, None, None)

        # Build reciprocal ship <-> loaded-airgroup-cargo links using shipUnitLoaded.
        airgroup_by_id: dict[int, dict] = {int(ag["record_id"]): ag for ag in airgroup_records}
        for ship_rec in ship_records:
            ship_id = int(ship_rec["record_id"])

            loaded_ground = loaded_ground_by_ship_id.get(ship_id)
            if loaded_ground:
                ship_rec["loaded_ground_unit_id"] = loaded_ground.get("record_id")
                ship_rec["loaded_ground_unit_name"] = loaded_ground.get("name")
                ship_rec["loaded_ground_unit_type_name"] = loaded_ground.get("unit_type_name")

            raw_loaded = int(ship_rec.get("_ship_unit_loaded_raw", -1))
            if raw_loaded > 0:
                cargo_ground = _resolve_ground_record_from_loaded(raw_loaded)
                if cargo_ground and cargo_ground.get("name"):
                    ship_rec["loaded_ground_unit_id"] = cargo_ground.get("record_id")
                    ship_rec["loaded_ground_unit_name"] = cargo_ground.get("name")
                    ship_rec["loaded_ground_unit_type_name"] = cargo_ground.get("unit_type_name")
                    cargo_ground["loaded_on_ship_id"] = ship_id
                    cargo_ground["loaded_on_ship_name"] = ship_rec.get("name")
                    cargo_ground["task_force_id"] = ship_rec.get("task_force_id")
                    cargo_ground["at_base_id"] = None
                    cargo_ground["stationed_at_base_id"] = None
                    cargo_ground["stationed_at_base_name"] = None
                elif ship_rec.get("loaded_ground_unit_id") is None:
                    # Preserve unresolved cargo reference so UI can still show embarked load placeholders.
                    loc_unit_id, loc_unit_name, loc_unit_type_name = _resolve_ground_name_from_locations(raw_loaded)
                    ship_rec["loaded_ground_unit_id"] = loc_unit_id if loc_unit_id is not None else raw_loaded
                    ship_rec["loaded_ground_unit_name"] = loc_unit_name
                    ship_rec["loaded_ground_unit_type_name"] = loc_unit_type_name

                cargo_airgroup = airgroup_by_id.get(raw_loaded)
                if (
                    cargo_airgroup
                    and cargo_airgroup.get("name")
                    and cargo_airgroup.get("stationed_on_ship_id") != ship_id
                ):
                    ship_rec["loaded_airgroup_cargo_id"] = cargo_airgroup.get("record_id")
                    ship_rec["loaded_airgroup_cargo_name"] = cargo_airgroup.get("name")
                    cargo_airgroup["loaded_as_cargo_on_ship_id"] = ship_id
                    cargo_airgroup["loaded_as_cargo_on_ship_name"] = ship_rec.get("name")

            ship_rec.pop("_ship_unit_loaded_raw", None)

        base_rec_by_id: dict[int, dict] = {int(b["record_id"]): b for b in base_records}

        for ship_rec in ship_records:
            base_id = ship_rec.get("stationed_at_base_id")
            if base_id is None:
                continue
            base_rec = base_rec_by_id.get(int(base_id))
            if base_rec is None:
                continue
            summary = {
                "record_id": ship_rec.get("record_id"),
                "name": ship_rec.get("name"),
                "ship_class_type_name": ship_rec.get("ship_class_type_name"),
            }
            base_rec["stationed_port"].append(summary)
            base_rec["stationed_port_ids"].append(int(ship_rec.get("record_id")))
            if ship_rec.get("name"):
                base_rec["stationed_port_names"].append(ship_rec.get("name"))

        for unit_rec in ground_records:
            base_id = unit_rec.get("stationed_at_base_id")
            if base_id is None:
                continue
            base_rec = base_rec_by_id.get(int(base_id))
            if base_rec is None:
                continue
            summary = {
                "record_id": unit_rec.get("record_id"),
                "name": unit_rec.get("name"),
                "unit_type_name": unit_rec.get("unit_type_name"),
            }
            base_rec["stationed_ground"].append(summary)
            base_rec["stationed_ground_ids"].append(int(unit_rec.get("record_id")))
            if unit_rec.get("name"):
                base_rec["stationed_ground_names"].append(unit_rec.get("name"))

        for ag_rec in airgroup_records:
            base_id = ag_rec.get("stationed_at_base_id")
            if base_id is None:
                continue
            base_rec = base_rec_by_id.get(int(base_id))
            if base_rec is None:
                continue
            summary = {
                "record_id": ag_rec.get("record_id"),
                "name": ag_rec.get("name"),
                "aircraft_name": ag_rec.get("aircraft_name"),
                "aircraft_type_name": ag_rec.get("aircraft_type_name"),
            }
            base_rec["stationed_air"].append(summary)
            base_rec["stationed_air_ids"].append(int(ag_rec.get("record_id")))
            if ag_rec.get("name"):
                base_rec["stationed_air_names"].append(ag_rec.get("name"))

        # Add a compact, consistent relations object so each record is self-describing.
        for ship_rec in ship_records:
            ship_airgroups = ship_rec.get("airgroups", [])
            ship_rec["relations"] = {
                "stationed_at_base": {
                    "id": ship_rec.get("stationed_at_base_id"),
                    "name": ship_rec.get("stationed_at_base_name"),
                },
                "leader": {
                    "id": ship_rec.get("leader_id"),
                    "name": ship_rec.get("leader_name"),
                    "rank": ship_rec.get("leader_rank"),
                },
                "task_force": {
                    "id": ship_rec.get("task_force_id"),
                },
                "loaded_ground_unit": {
                    "id": ship_rec.get("loaded_ground_unit_id"),
                    "name": ship_rec.get("loaded_ground_unit_name"),
                },
                "loaded_airgroup_cargo": {
                    "id": ship_rec.get("loaded_airgroup_cargo_id"),
                    "name": ship_rec.get("loaded_airgroup_cargo_name"),
                },
                "stationed_airgroups": {
                    "ids": [int(a.get("record_id")) for a in ship_airgroups if a.get("record_id") is not None],
                    "names": [str(a.get("name")) for a in ship_airgroups if a.get("name")],
                },
            }

        for unit_rec in ground_records:
            unit_rec["relations"] = {
                "stationed_at_base": {
                    "id": unit_rec.get("stationed_at_base_id"),
                    "name": unit_rec.get("stationed_at_base_name"),
                },
                "leader": {
                    "id": unit_rec.get("leader_id"),
                    "name": unit_rec.get("leader_name"),
                    "rank": unit_rec.get("leader_rank"),
                },
                "loaded_on_ship": {
                    "id": unit_rec.get("loaded_on_ship_id"),
                    "name": unit_rec.get("loaded_on_ship_name"),
                },
                "attached_hq": {
                    "id": unit_rec.get("attached_hq_id"),
                    "name": unit_rec.get("attached_hq_name"),
                },
            }

        for ag_rec in airgroup_records:
            ag_rec["relations"] = {
                "stationed_at_base": {
                    "id": ag_rec.get("stationed_at_base_id"),
                    "name": ag_rec.get("stationed_at_base_name"),
                },
                "stationed_on_ship": {
                    "id": ag_rec.get("stationed_on_ship_id"),
                    "name": ag_rec.get("stationed_on_ship_name"),
                },
                "loaded_as_cargo_on_ship": {
                    "id": ag_rec.get("loaded_as_cargo_on_ship_id"),
                    "name": ag_rec.get("loaded_as_cargo_on_ship_name"),
                },
                "loaded_on_ship": {
                    "id": ag_rec.get("loaded_on_ship_id"),
                    "name": ag_rec.get("loaded_on_ship_name"),
                },
                "leader": {
                    "id": ag_rec.get("leader_id"),
                    "name": ag_rec.get("leader_name"),
                    "rank": ag_rec.get("leader_rank"),
                },
                "pilots": {
                    "ids": ag_rec.get("pilot_ids", []),
                    "names": ag_rec.get("pilot_names", []),
                    "count_assigned": ag_rec.get("pilot_count_assigned"),
                },
            }

        for base_rec in base_records:
            base_rec["relations"] = {
                "stationed_ground": {
                    "ids": base_rec.get("stationed_ground_ids", []),
                    "names": base_rec.get("stationed_ground_names", []),
                },
                "stationed_air": {
                    "ids": base_rec.get("stationed_air_ids", []),
                    "names": base_rec.get("stationed_air_names", []),
                },
                "stationed_port": {
                    "ids": base_rec.get("stationed_port_ids", []),
                    "names": base_rec.get("stationed_port_names", []),
                },
            }

        taskforce_records: list[dict] = []
        skipped_taskforce_mission_zero = 0
        skipped_taskforce_out_of_range = 0
        for tf_id, taskforce in enumerate(taskgroups):
            tf_ships = ships_by_tf_id.get(tf_id, [])
            if not tf_ships:
                continue

            mission_code = int(taskforce.get("tfMission", -1))
            if mission_code == 0:
                skipped_taskforce_mission_zero += 1
                continue

            flagship_id = int(taskforce.get("tfFlagship", -1))
            flagship_name = None
            nation_name = None
            start_xy = None
            end_xy = None
            commander = None
            target_xy = None
            target_location_id = None

            if 0 <= flagship_id < len(ships):
                flagship = ships[flagship_id]
                if self._nation_allowed(int(flagship["nation"])) and self._arrived_by_gameday(
                    int(flagship.get("shipDelay", 0)), end_gameday
                ):
                    flagship_name = flagship.get("name") or None
                    nation_name = self._enum_name(int(flagship["nation"]), Nationality)
                    leader_id = int(flagship.get("shipLeader", -1))
                    if 0 <= leader_id < len(leaders):
                        leader = leaders[leader_id]
                        if self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                            commander = f"{rank_to_name(int(leader['rank']))} {leader['name']}"

                    end_xy = end_locations_xy.get(int(flagship.get("shipTF", -1)))
                    start_ships = start_snapshot.get("ships", [])
                    if flagship_id < len(start_ships):
                        start_flagship = start_ships[flagship_id]
                        start_xy = start_locations_xy.get(int(start_flagship.get("shipTF", -1)))

                    tf_location_id = int(flagship.get("shipTF", -1))
                    tf_location = location_by_id.get(tf_location_id)
                    if tf_location is not None:
                        tx = int(tf_location.get("destX", 0))
                        ty = int(tf_location.get("destY", 0))
                        if tx > 0 and ty > 0:
                            target_xy = (tx, ty)
                            target_location_id = tf_location_id

            if target_xy is None:
                fallback_tf_location_id = tf_id + 14000
                tf_location = location_by_id.get(fallback_tf_location_id)
                if tf_location is not None:
                    tx = int(tf_location.get("destX", 0))
                    ty = int(tf_location.get("destY", 0))
                    if tx > 0 and ty > 0:
                        target_xy = (tx, ty)
                        target_location_id = fallback_tf_location_id

            if target_xy is None:
                home_port_id = int(taskforce.get("tfHomePort", -1))
                home_port_xy = end_locations_xy.get(home_port_id)
                if home_port_xy is not None:
                    target_xy = home_port_xy
                    target_location_id = home_port_id

            ship_manifest = []
            for tf_ship in tf_ships:
                class_id = int(tf_ship.get("shipClass", -1))
                ship_type = None
                ship_class_name = None
                ship_leader_name = None
                if 0 <= class_id < len(shipclasses):
                    shipclass = shipclasses[class_id]
                    ship_type = ship_class_type_to_name(int(shipclass["type"]))
                    ship_class_name = shipclass.get("name") or None
                ship_leader_id = int(tf_ship.get("shipLeader", -1))
                if 0 <= ship_leader_id < len(leaders):
                    ship_leader = leaders[ship_leader_id]
                    if self._arrived_by_gameday(int(ship_leader.get("arriveDay", 0)), end_gameday):
                        ship_leader_name = ship_leader.get("name") or None
                ship_manifest.append(
                    {
                        "name": tf_ship.get("name") or None,
                        "ship_type": ship_type,
                        "ship_class_name": ship_class_name,
                        "leader_name": ship_leader_name,
                    }
                )

            if not (
                is_in_map_hex_range(start_xy[0] if start_xy else None, start_xy[1] if start_xy else None)
                and is_in_map_hex_range(end_xy[0] if end_xy else None, end_xy[1] if end_xy else None)
                and is_in_map_hex_range(target_xy[0] if target_xy else None, target_xy[1] if target_xy else None)
            ):
                skipped_taskforce_out_of_range += 1
                continue

            taskforce_records.append(
                {
                    "record_id": tf_id,
                    "mission": self._enum_name(mission_code, TaskForceMission),
                    "nation": nation_name,
                    "flagship_id": flagship_id,
                    "flagship_name": flagship_name,
                    "commander": commander,
                    "start_of_day_x": start_xy[0] if start_xy else None,
                    "start_of_day_y": start_xy[1] if start_xy else None,
                    "end_of_day_x": end_xy[0] if end_xy else None,
                    "end_of_day_y": end_xy[1] if end_xy else None,
                    "target_x": target_xy[0] if target_xy else None,
                    "target_y": target_xy[1] if target_xy else None,
                    "target_location_id": target_location_id,
                    "ships": ship_manifest,
                }
            )

        if skipped_taskforce_mission_zero or skipped_taskforce_out_of_range:
            LOGGER.info(
                "[export-json] excluded taskforces mission0=%s out_of_map_range=%s",
                skipped_taskforce_mission_zero,
                skipped_taskforce_out_of_range,
            )

        for tf_rec in taskforce_records:
            tf_ships = tf_rec.get("ships", [])
            tf_rec["relations"] = {
                "flagship": {
                    "id": tf_rec.get("flagship_id"),
                    "name": tf_rec.get("flagship_name"),
                },
                "commander": {
                    "name": tf_rec.get("commander"),
                },
                "ships": {
                    "names": [str(s.get("name")) for s in tf_ships if s.get("name")],
                    "leaders": [str(s.get("leader_name")) for s in tf_ships if s.get("leader_name")],
                },
            }

        # Refresh in-memory active datasets from the computed export records.
        airgroup_name_by_id = {
            int(rec["record_id"]): (rec.get("name") or None)
            for rec in airgroup_records
        }

        leader_assignment: dict[int, dict] = {}
        for rec in ship_records:
            lid = rec.get("leader_id")
            if isinstance(lid, int) and lid >= 0 and lid not in leader_assignment:
                leader_assignment[lid] = {
                    "type": "ship",
                    "unit_id": rec.get("record_id"),
                    "unit_name": rec.get("name"),
                    "nation": rec.get("nation"),
                }
        for rec in ground_records:
            lid = rec.get("leader_id")
            if isinstance(lid, int) and lid >= 0 and lid not in leader_assignment:
                leader_assignment[lid] = {
                    "type": "ground_unit",
                    "unit_id": rec.get("record_id"),
                    "unit_name": rec.get("name"),
                    "nation": rec.get("nation"),
                }
        for rec in airgroup_records:
            lid = rec.get("leader_id")
            if isinstance(lid, int) and lid >= 0 and lid not in leader_assignment:
                leader_assignment[lid] = {
                    "type": "airgroup",
                    "unit_id": rec.get("record_id"),
                    "unit_name": rec.get("name"),
                    "nation": rec.get("nation"),
                }

        self.active_ships = [
            ActiveShip(
                record_id=int(rec["record_id"]),
                current=rec,
                nation_name=rec.get("nation"),
                shipclass_name=rec.get("ship_class_name"),
                shipclass_type_name=rec.get("ship_class_type_name"),
                shipclass_tonnage=int(rec.get("ship_class_tonnage", 0)),
                current_position={"x": rec.get("x"), "y": rec.get("y")},
                stationed_at_base_id=rec.get("stationed_at_base_id"),
                stationed_at_base_name=rec.get("stationed_at_base_name"),
                in_task_force_id=rec.get("task_force_id"),
                airgroup_ids=[int(a.get("record_id")) for a in rec.get("airgroups", []) if a.get("record_id") is not None],
                airgroup_names=[str(a.get("name")) for a in rec.get("airgroups", []) if a.get("name")],
                loaded_ground_unit_id=rec.get("loaded_ground_unit_id"),
                loaded_ground_unit_name=rec.get("loaded_ground_unit_name"),
                loaded_airgroup_cargo_id=rec.get("loaded_airgroup_cargo_id"),
                loaded_airgroup_cargo_name=rec.get("loaded_airgroup_cargo_name"),
            )
            for rec in ship_records
        ]

        self.active_ground_units = [
            ActiveGroundUnit(
                record_id=int(rec["record_id"]),
                current=rec,
                unit_name=rec.get("name"),
                unit_type_name=rec.get("unit_type_name"),
                arrive_day=rec.get("arrive_day"),
                nation_name=rec.get("nation"),
                attached_hq_id=rec.get("attached_hq_id"),
                attached_hq_name=rec.get("attached_hq_name"),
                stationed_at_base_id=rec.get("stationed_at_base_id"),
                stationed_at_base_name=rec.get("stationed_at_base_name"),
                loaded_on_ship_id=rec.get("loaded_on_ship_id"),
                loaded_on_ship_name=rec.get("loaded_on_ship_name"),
                start_of_day_position={"x": rec.get("start_of_day_x"), "y": rec.get("start_of_day_y")},
                end_of_day_position={"x": rec.get("end_of_day_x"), "y": rec.get("end_of_day_y")},
                destination_position={"x": rec.get("destination_x"), "y": rec.get("destination_y")},
                hq_kind=rec.get("hq_kind"),
            )
            for rec in ground_records
        ]

        self.active_airgroups = [
            ActiveAirgroup(
                record_id=int(rec["record_id"]),
                current=rec,
                nation_name=rec.get("nation"),
                aircraft_id=rec.get("aircraft_id"),
                aircraft_name=rec.get("aircraft_name"),
                aircraft_type_name=rec.get("aircraft_type_name"),
                pilot_ids=rec.get("pilot_ids", []),
                pilot_names=rec.get("pilot_names", []),
                current_position={"x": rec.get("x"), "y": rec.get("y")},
                target_position={"x": rec.get("target_x"), "y": rec.get("target_y")},
                stationed_at_base_id=rec.get("stationed_at_base_id"),
                stationed_at_base_name=rec.get("stationed_at_base_name"),
                in_task_force_id=None,
                loaded_on_ship_id=rec.get("loaded_on_ship_id"),
                loaded_on_ship_name=rec.get("loaded_on_ship_name"),
                stationed_on_ship_id=rec.get("stationed_on_ship_id"),
                stationed_on_ship_name=rec.get("stationed_on_ship_name"),
                loaded_as_cargo_on_ship_id=rec.get("loaded_as_cargo_on_ship_id"),
                loaded_as_cargo_on_ship_name=rec.get("loaded_as_cargo_on_ship_name"),
            )
            for rec in airgroup_records
        ]

        self.active_bases = [
            ActiveBase(
                record_id=int(rec["record_id"]),
                current=rec,
                nation_name=rec.get("nation"),
                port=rec.get("port"),
                airfield=rec.get("airfield"),
                ship_repair_points=rec.get("ship_repair"),
                supply=rec.get("supply"),
                resources=rec.get("resources"),
                fuel=rec.get("fuel"),
                runway_damage=rec.get("runway_damage"),
                port_damage=rec.get("port_damage"),
                airfield_damage=rec.get("airfield_damage"),
                ground_unit_ids=rec.get("stationed_ground_ids", []),
                air_group_ids=rec.get("stationed_air_ids", []),
                ship_ids=rec.get("stationed_port_ids", []),
                ground_unit_names=rec.get("stationed_ground_names", []),
                air_group_names=rec.get("stationed_air_names", []),
                ship_names=rec.get("stationed_port_names", []),
                stationed_ground_ids=rec.get("stationed_ground_ids", []),
                stationed_ground_names=rec.get("stationed_ground_names", []),
                stationed_air_ids=rec.get("stationed_air_ids", []),
                stationed_air_names=rec.get("stationed_air_names", []),
                stationed_port_ids=rec.get("stationed_port_ids", []),
                stationed_port_names=rec.get("stationed_port_names", []),
                position={"x": rec.get("x"), "y": rec.get("y")},
            )
            for rec in base_records
        ]

        self.active_task_forces = [
            ActiveTaskForce(
                record_id=int(rec["record_id"]),
                current=rec,
                nation_name=rec.get("nation"),
                flagship_name=rec.get("flagship_name"),
                commander_name=rec.get("commander"),
                ships=rec.get("ships", []),
                start_of_day_position={"x": rec.get("start_of_day_x"), "y": rec.get("start_of_day_y")},
                end_of_day_position={"x": rec.get("end_of_day_x"), "y": rec.get("end_of_day_y")},
                target_position={"x": rec.get("target_x"), "y": rec.get("target_y")},
            )
            for rec in taskforce_records
        ]

        self.active_leaders = []
        for leader_id, leader in enumerate(leaders):
            if not self._arrived_by_gameday(int(leader.get("arriveDay", 0)), end_gameday):
                continue
            assignment = leader_assignment.get(leader_id)
            if assignment is None:
                assignment = {
                    "type": "RESERVE",
                    "unit_id": None,
                    "unit_name": "RESERVE",
                    "nation": None,
                }
            self.active_leaders.append(
                ActiveLeader(
                    record_id=leader_id,
                    current=leader,
                    nation_name=assignment.get("nation"),
                    rank_name=rank_to_name(int(leader.get("rank", 0))),
                    assigned_unit_type=assignment.get("type"),
                    assigned_unit_id=assignment.get("unit_id"),
                    assigned_unit_name=assignment.get("unit_name"),
                )
            )

        self.active_pilots = []
        for pilot_rec in active_pilot_records:
            raw_agid = int(pilot_rec.get("airgroup_id", -1))
            pilot_airgroup_id = raw_agid if raw_agid in airgroup_name_by_id else None
            pilot_airgroup_name = airgroup_name_by_id.get(raw_agid)
            if pilot_airgroup_id is None and self.side != "JAPAN":
                pilot_airgroup_name = "TRACOM"
            self.active_pilots.append(
                ActivePilot(
                    record_id=int(pilot_rec["record_id"]),
                    current=pilot_rec,
                    nation_name=pilot_rec.get("nation"),
                    rank_name=pilot_rec.get("rank_name"),
                    airgroup_id=pilot_airgroup_id,
                    airgroup_name=pilot_airgroup_name,
                )
            )

        minefield_records = [
            {
                "x": int(record.get("x") or 0),
                "y": int(record.get("y") or 0),
                "mine_count": int(record.get("number") or 0),
                "side": "JAPAN" if int(record.get("side") or -1) == int(Side.JAPAN) else "ALLIED",
            }
            for record in end_snapshot.get("minefields", [])
            if self._minefield_side_allowed(int(record.get("side") or -1))
        ]

        self._write_json_records(output_dir / "ships.json", ship_records)
        self._write_json_records(output_dir / "ground_units.json", ground_records)
        self._write_json_records(output_dir / "airgroups.json", airgroup_records)
        self._write_json_records(output_dir / "bases.json", base_records)
        self._write_json_records(output_dir / "taskforces.json", taskforce_records)
        self._write_json_records(output_dir / "minefields.json", minefield_records)
        end_game_date = (
            end_snapshot.get("game_date")
            or self._end_day_game_date
            or self._read_game_date_from_header(self.end_of_day_file)
        )
        turn_payload = {
            "game_date": end_game_date,
            "game_turn": end_snapshot.get("gameday"),
            "scenario_name": end_snapshot.get("scenario_name"),
        }
        # ★2026-09-29 新增★ 导出胜负判定所需的权威比分（存档 SCENINFO 结构）
        for _k in ("japan_vp", "allied_vp", "japan_lcu_loss", "allied_lcu_loss"):
            if end_snapshot.get(_k) is not None:
                turn_payload[_k] = end_snapshot[_k]
        header_comment = end_snapshot.get("header_comment")
        if header_comment:
            turn_payload["header_comment"] = header_comment
        self._write_json(output_dir / "turn.json", turn_payload)

        threats_payload = {
            "game_date": turn_payload.get("game_date"),
            "game_turn": turn_payload.get("game_turn"),
            "scenario_name": turn_payload.get("scenario_name"),
            "threat_areas": [self._threat_area_payload(a) for a in self.active_threat_areas],
            "sub_threat_areas": [self._threat_area_payload(a) for a in self.active_sub_threat_areas],
            "surface_threat_areas": [self._threat_area_payload(a) for a in self.active_surface_threat_areas],
            "carrier_threat_areas": [self._threat_area_payload(a) for a in self.active_carrier_threat_areas],
            "invasion_threat_areas": [
                self._invasion_threat_payload(t)
                for t in self.active_invasion_threat_areas
            ],
        }
        self._write_json(output_dir / "threats.json", threats_payload)

        LOGGER.info(
            "[export-json] ships=%s ground_units=%s airgroups=%s bases=%s taskforces=%s minefields=%s threats=%s turn_json=%s output_dir=%s",
            len(ship_records),
            len(ground_records),
            len(airgroup_records),
            len(base_records),
            len(taskforce_records),
            len(minefield_records),
            {
                "all": len(self.active_threat_areas),
                "sub": len(self.active_sub_threat_areas),
                "surface": len(self.active_surface_threat_areas),
                "carrier": len(self.active_carrier_threat_areas),
                "invasion": len(self.active_invasion_threat_areas),
            },
            turn_payload,
            output_dir,
        )

    # Backward-compatible alias for older callers.
    def export_jsonl(self, output_dir: Path) -> None:
        self.export_json(output_dir)

    def load_day(self, day_file: Path, mode: int = 0, validate_samples: bool = False) -> str:
        expected_rec_types = {rec_type.name for rec_type in RecType}
        ctx = self._pws.new_context(RecType.SCENARIO)
        open_result = self._pws.pws_open_file(ctx, str(day_file), mode)
        LOGGER.info("PWSOpenFile file=%s mode=%s result=%s", day_file, mode, open_result)
        if open_result == 0:
            raise RuntimeError(f"PWSOpenFile failed for {day_file} with code {open_result}")

        try:
            rec_type_name = RecType(ctx.PWSid).name
        except ValueError:
            rec_type_name = f"UNKNOWN({ctx.PWSid})"

        LOGGER.info("PWSOpenFile populated rec_type=%s", rec_type_name)

        counts: Counter = Counter()
        if self.side != "JAPAN":
            sample_checks: dict[str, bool] = {
                "ships_enterprise": True,
                "pilot_boyington": True,
                "leader_nimitz": True,
            }
        else:  # JAPAN
            sample_checks: dict[str, bool] = {
                "ships_akagi": True,
            }
        _sample_shipclass_info = None
        _sample_airgroup_names: dict[int, str] = {}
        _pending_pilot_dump: tuple[int, object] | None = None
        _pending_ship_dumps: list[tuple[int, object]] = []
        if rec_type_name in expected_rec_types:
            counts[rec_type_name] += 1

        if ctx.PWSid == RecType.HEADER and ctx.PWSaddress.header:
            hdr = ctypes.cast(ctx.PWSaddress.header, ctypes.POINTER(PWSHeader)).contents
            comment_text = hdr.comment.decode("ascii", errors="replace").strip("\x00")
            timestamp_text = hdr.timestamp.decode("ascii", errors="replace").strip("\x00")
            header_game_date = self._extract_mmddyy(comment_text) or self._extract_mmddyy(timestamp_text)
            if day_file == self.start_of_day_file:
                self._start_day_game_date = header_game_date
            if day_file == self.end_of_day_file:
                self._end_day_game_date = header_game_date
            LOGGER.info("  comment=%s", comment_text)
            LOGGER.info("  timestamp=%s", timestamp_text)

        while True:
            self._pws.pws_get_next_item(ctx)
            if ctx.PWSopened == -1:
                break
            try:
                rec_type_name = RecType(ctx.PWSid).name
                counts[rec_type_name] += 1
            except ValueError:
                continue

            if ctx.PWSid == RecType.SCENARIO and ctx.PWSaddress.sceninfo:
                scen = ctypes.cast(ctx.PWSaddress.sceninfo, ctypes.POINTER(PWSScenInfo)).contents
                LOGGER.info("    scenario=%s", scen.scenario.decode("ascii", errors="replace").strip("\x00"))
                LOGGER.info("    gameturn=%s japanVP=%s alliedVP=%s", scen.gameturn, scen.japanVP, scen.alliedVP)
                LOGGER.info("    gametype=%s pbemphase=%s", scen.gametype, scen.pbemphase)
                LOGGER.info("    japanLCULoss=%s alliedLCULoss=%s", scen.japanLCULoss, scen.alliedLCULoss)

            if validate_samples and ctx.PWSid == RecType.SHIPCLASS and ctx.PWSaddress.shipclasses:
                _sample_shipclass_info = ctypes.cast(
                    ctx.PWSaddress.shipclasses, ctypes.POINTER(PWSShipClassInfo)
                ).contents

            if validate_samples and ctx.PWSid == RecType.AIRGROUP and ctx.PWSaddress.airgroups:
                airgroup_info = ctypes.cast(ctx.PWSaddress.airgroups, ctypes.POINTER(PWSAirGroupInfo)).contents
                for i, airgroup in enumerate(airgroup_info.airgroup):
                    name = self._decode_cstr(airgroup.groupname)
                    if name:
                        _sample_airgroup_names[i] = name

            if validate_samples and ctx.PWSid == RecType.SHIP and ctx.PWSaddress.ships:
                ship_info = ctypes.cast(ctx.PWSaddress.ships, ctypes.POINTER(PWSShipInfo)).contents
                ship_targets = (
                    [("Enterprise", "ships_enterprise")]
                    if self.side != "JAPAN"
                    else [("Akagi", "ships_akagi")]
                )
                for wanted, key in ship_targets:
                    idx, _ = self._find_name_index(ship_info.ship, wanted, allow_partial=False)
                    passed = self._log_sample_result("ship", wanted, (idx, _))
                    sample_checks[key] = passed
                    if passed:
                        ship = ship_info.ship[idx]
                        if _sample_shipclass_info:
                            self._dump_ship(idx, ship, _sample_shipclass_info)
                        else:
                            _pending_ship_dumps.append((idx, ship))

            if validate_samples and self.side != "JAPAN" and ctx.PWSid == RecType.PILOT and ctx.PWSaddress.pilots:
                pilot_info = ctypes.cast(ctx.PWSaddress.pilots, ctypes.POINTER(PWSPilotInfo)).contents
                idx, name = self._find_name_index(pilot_info.pilot, "Boyington", allow_partial=True)
                passed = self._log_sample_result("pilot", "Boyington", (idx, name))
                sample_checks["pilot_boyington"] = passed
                if passed:
                    pilot = pilot_info.pilot[idx]
                    airgroup_name = _sample_airgroup_names.get(pilot.agrp)
                    if airgroup_name:
                        self._dump_pilot(idx, pilot, airgroup_name)
                    else:
                        _pending_pilot_dump = (idx, pilot)

            if validate_samples and self.side != "JAPAN" and ctx.PWSid == RecType.LEADER and ctx.PWSaddress.leaders:
                leader_info = ctypes.cast(ctx.PWSaddress.leaders, ctypes.POINTER(PWSLeaderInfo)).contents
                idx, name = self._find_name_index(leader_info.leader, "Nimitz", allow_partial=True)
                passed = self._log_sample_result("leader", "Nimitz", (idx, name))
                sample_checks["leader_nimitz"] = passed
                if passed:
                    self._dump_leader(idx, leader_info.leader[idx])

        LOGGER.info("Known record counts: %s", dict(sorted(counts.items())))
        missing_rec_types = sorted(expected_rec_types - set(counts))
        LOGGER.info("Missing known rec_types: %s", missing_rec_types)

        close_result = self._pws.pws_close_file(ctx)
        LOGGER.info("PWSCloseFile result=%s", close_result)
        if close_result == 0:
            raise RuntimeError(f"PWSCloseFile failed for {day_file} with code {close_result}")

        if missing_rec_types:
            raise RuntimeError(
                f"Missing RecType values while iterating {day_file}: {', '.join(missing_rec_types)}"
            )

        if validate_samples:
            for idx, ship in _pending_ship_dumps:
                self._dump_ship(idx, ship, _sample_shipclass_info)

            if _pending_pilot_dump:
                idx, pilot = _pending_pilot_dump
                airgroup_name = _sample_airgroup_names.get(pilot.agrp, "UNKNOWN_AIRGROUP")
                self._dump_pilot(idx, pilot, airgroup_name)

            failed = sorted(name for name, passed in sample_checks.items() if not passed)
            if failed:
                raise RuntimeError(
                    f"Sample validation failed for {day_file}: {', '.join(failed)}"
                )

        return rec_type_name

    @property
    def pwsdll(self):
        return self._pws.raw