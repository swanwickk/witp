"""
Parser for combatreport.txt.

File format:
  Line 1  : "AFTER ACTION REPORTS FOR <date>"  (e.g. "Dec 24, 41")
  Body    : Action blocks separated by 80-char dash-divider lines ("---...---").

Each action block:
  Line 1  : Action title
              e.g. "Invasion Support action off Rabaul (106,125)"
              e.g. "Sub vs Sub: SS I-170 attacking SS Tambor  at 180,109  - near Molokai"
  Line 2  : Sub-title / context line
              e.g. "Defensive Guns engage approaching landing force"
  Body    : Ship/unit listings grouped under "Japanese Ships" / "Allied Ships"
            section headings, followed by per-unit event lines such as:
              "      TB Kamo fired at enemy troops"
              "      AMC Kinryu Maru, Shell hits 1,  on fire"
              "40mm Bofors AA Gun battery firing at AMC Kinryu Maru"

Both sides' engagements appear in the same file; no side prefix.

TODO: parse each action block into structured records with action type, location,
      coordinate, participating ship lists (Japanese / Allied), and event lines.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger("pywitpae.combat_report")

_DIVIDER_PREFIX = "---"
_COORDINATE_PATTERN = re.compile(r"\((\d+),(\d+)\)")
_ACTION_OFF_PATTERN = re.compile(r"^(?P<action>.+?) action off (?P<location>.+?) \((?P<x>\d+),(?P<y>\d+)\)$")
_ACTION_NEAR_PATTERN = re.compile(r"^(?P<action>.+?) at\s+(?P<x>\d+),(?P<y>\d+)\s+- near (?P<location>.+)$")
_SHIP_SECTION_NAMES = {"Japanese Ships", "Allied Ships"}


@dataclass
class CombatAction:
    title: str = ""
    subtitle: str | None = None
    action_type: str | None = None
    location: str | None = None
    coordinates: tuple[int, int] | None = None
    japanese_ships: list[str] = field(default_factory=list)
    allied_ships: list[str] = field(default_factory=list)
    event_lines: list[str] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class CombatReportLog:
    game_date: str | None = None
    actions: list[CombatAction] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)


def _parse_title_metadata(title: str) -> tuple[str | None, str | None, tuple[int, int] | None]:
    title = title.strip()
    match = _ACTION_OFF_PATTERN.match(title)
    if match:
        return (
            match.group("action").strip(),
            match.group("location").strip(),
            (int(match.group("x")), int(match.group("y"))),
        )

    match = _ACTION_NEAR_PATTERN.match(title)
    if match:
        return (
            match.group("action").strip(),
            match.group("location").strip(),
            (int(match.group("x")), int(match.group("y"))),
        )

    coord_match = _COORDINATE_PATTERN.search(title)
    coordinates = None
    if coord_match:
        coordinates = (int(coord_match.group(1)), int(coord_match.group(2)))

    action_type = title.split(":", 1)[0].strip() if ":" in title else title
    return action_type or None, None, coordinates


def _parse_action_block(block_lines: list[str]) -> CombatAction:
    non_empty_lines = [line.strip() for line in block_lines if line.strip()]
    title = non_empty_lines[0] if non_empty_lines else ""
    action_type, location, coordinates = _parse_title_metadata(title)

    action = CombatAction(
        title=title,
        raw_lines=list(block_lines),
        action_type=action_type,
        location=location,
        coordinates=coordinates,
    )

    current_section: str | None = None
    subtitle_set = False
    for raw_line in block_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped == title:
            continue
        if not subtitle_set:
            action.subtitle = stripped
            subtitle_set = True
            continue
        if stripped in _SHIP_SECTION_NAMES:
            current_section = stripped
            continue

        if current_section == "Japanese Ships" and raw_line.startswith("      "):
            action.japanese_ships.append(stripped)
            continue
        if current_section == "Allied Ships" and raw_line.startswith("      "):
            action.allied_ships.append(stripped)
            continue

        action.event_lines.append(stripped)

    return action


def load(path: Path) -> CombatReportLog:
    LOGGER.info("[combat-report] Loading %s", path)
    result = CombatReportLog()
    lines = path.read_text(encoding="gbk", errors="replace").splitlines()
    result.raw_lines = lines
    if not lines:
        return result

    result.game_date = lines[0].strip()
    LOGGER.info("[combat-report] %s", result.game_date)

    # Split body into blocks on divider lines; each block becomes one CombatAction.
    current_block: list[str] = []
    for line in lines[1:]:
        if line.startswith(_DIVIDER_PREFIX):
            if current_block:
                result.actions.append(_parse_action_block(current_block))
                current_block = []
        else:
            current_block.append(line)
    if current_block:
        result.actions.append(_parse_action_block(current_block))

    LOGGER.info("[combat-report] %d action blocks parsed", len(result.actions))
    if result.actions:
        first_action = result.actions[0]
        LOGGER.info(
            "[combat-report] first action type=%s location=%s coords=%s jap_ships=%s allied_ships=%s events=%s",
            first_action.action_type,
            first_action.location,
            first_action.coordinates,
            len(first_action.japanese_ships),
            len(first_action.allied_ships),
            len(first_action.event_lines),
        )
    return result
