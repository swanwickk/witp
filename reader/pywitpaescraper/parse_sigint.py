"""
Parser for {a|j}sigint.txt.

File naming:
  Allied side  -> asigint.txt
  Japan side   -> jsigint.txt

File format:
  Line 1  : "SIG INT REPORT FOR <date>"  (e.g. "Dec 24, 41")
  Body    : One intel item per line.

Observed line patterns (Allied file - asigint.txt):
  - Ship movement   : "<ship> is moving to <location> (<x>,<y>)."
  - Unit location   : "<unit> is located at <location>(<x>,<y>)."
                      (note: coordinate may be directly adjacent to location name)
  - Radio (normal)  : "Radio transmissions detected at <location> (<x>,<y>)."
  - Radio (heavy)   : "Heavy Volume of Radio transmissions detected at <location> (<x>,<y>)."
  - Attack planning : "<unit> is planning for an attack on <location>."

Observed line patterns (Japan file - jsigint.txt):
  - Radio (normal)  : "Radio transmissions detected at <location> (<x>,<y>)."
  - Radio (heavy)   : "Heavy Volume of Radio transmissions detected at <location> (<x>,<y>)."

Both files may carry radio-detection entries for the opposing side's bases/units.

TODO: parse each line into typed intel records (ship movement, unit location,
      radio detection, attack plan).
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger("pywitpae.sigint")

_COORD_RE = re.compile(r"\((\d+)\s*,\s*(\d+)\)")
_RADIO_HEAVY_RE = re.compile(r"^Heavy Volume of Radio transmissions detected at\s+(.+?)\s*\((\d+)\s*,\s*(\d+)\)\.?$", re.IGNORECASE)
_RADIO_NORMAL_RE = re.compile(r"^Radio transmissions detected at\s+(.+?)\s*\((\d+)\s*,\s*(\d+)\)\.?$", re.IGNORECASE)
_RADIO_COORD_ONLY_RE = re.compile(r"^(Heavy Volume of )?Radio transmissions detected at\s+(\d+)\s*,\s*(\d+)\.?$", re.IGNORECASE)
_MOVING_RE = re.compile(r"^(.+?)\s+is moving to\s+(.+?)\s*\((\d+)\s*,\s*(\d+)\)\.?$", re.IGNORECASE)
_LOCATED_RE = re.compile(r"^(.+?)\s+is located at\s+(.+?)\s*\((\d+)\s*,\s*(\d+)\)\.?$", re.IGNORECASE)
_ATTACK_PLAN_RE = re.compile(r"^(.+?)\s+is planning for an attack on\s+(.+?)\.?$", re.IGNORECASE)


@dataclass
class SigintEvent:
    text: str
    category: str
    subject: str | None = None
    location: str | None = None
    coordinates: tuple[int, int] | None = None
    intensity: str | None = None  # For radio detections: "normal" | "heavy"


@dataclass
class SigintLog:
    side: str = ""              # "US" or "JAPAN"
    game_date: str | None = None
    raw_lines: list[str] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)
    events: list[SigintEvent] = field(default_factory=list)


def _coords_from_match(match: re.Match) -> tuple[int, int]:
    return int(match.group(match.lastindex - 1)), int(match.group(match.lastindex))


def _extract_coords_fallback(text: str) -> tuple[int, int] | None:
    match = _COORD_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _parse_sigint_line(text: str) -> SigintEvent:
    heavy_match = _RADIO_HEAVY_RE.match(text)
    if heavy_match:
        return SigintEvent(
            text=text,
            category="radio_detection",
            location=heavy_match.group(1).strip(),
            coordinates=_coords_from_match(heavy_match),
            intensity="heavy",
        )

    normal_match = _RADIO_NORMAL_RE.match(text)
    if normal_match:
        return SigintEvent(
            text=text,
            category="radio_detection",
            location=normal_match.group(1).strip(),
            coordinates=_coords_from_match(normal_match),
            intensity="normal",
        )

    coord_only_match = _RADIO_COORD_ONLY_RE.match(text)
    if coord_only_match:
        return SigintEvent(
            text=text,
            category="radio_detection",
            coordinates=(int(coord_only_match.group(2)), int(coord_only_match.group(3))),
            intensity="heavy" if coord_only_match.group(1) else "normal",
        )

    moving_match = _MOVING_RE.match(text)
    if moving_match:
        return SigintEvent(
            text=text,
            category="ship_movement",
            subject=moving_match.group(1).strip(),
            location=moving_match.group(2).strip(),
            coordinates=(int(moving_match.group(3)), int(moving_match.group(4))),
        )

    located_match = _LOCATED_RE.match(text)
    if located_match:
        return SigintEvent(
            text=text,
            category="unit_location",
            subject=located_match.group(1).strip(),
            location=located_match.group(2).strip(),
            coordinates=(int(located_match.group(3)), int(located_match.group(4))),
        )

    attack_match = _ATTACK_PLAN_RE.match(text)
    if attack_match:
        return SigintEvent(
            text=text,
            category="attack_plan",
            subject=attack_match.group(1).strip(),
            location=attack_match.group(2).strip(),
        )

    return SigintEvent(
        text=text,
        category="other",
        coordinates=_extract_coords_fallback(text),
    )


def load(path: Path, side: str) -> SigintLog:
    LOGGER.info("[sigint] Loading %s (side=%s)", path, side)
    result = SigintLog(side=side)
    lines = path.read_text(encoding="gbk", errors="replace").splitlines()
    result.raw_lines = lines
    if lines:
        result.game_date = lines[0].strip()
        LOGGER.info("[sigint] %s", result.game_date)
    LOGGER.info("[sigint] %d intel lines read", len(lines))

    result.entries = [line.strip() for line in lines[1:] if line.strip()]
    result.events = [_parse_sigint_line(entry) for entry in result.entries]

    category_counts: dict[str, int] = {}
    for event in result.events:
                category_counts[event.category] = category_counts.get(event.category, 0) + 1

    LOGGER.info("[sigint] parsed entries=%s category counts=%s", len(result.entries), dict(sorted(category_counts.items())))
    if result.events:
                sample = result.events[0]
                LOGGER.info(
                        "[sigint] sample category=%s subject=%s location=%s coords=%s intensity=%s text='%s'",
                        sample.category,
                        sample.subject,
                        sample.location,
                        sample.coordinates,
                        sample.intensity,
                        sample.text,
                )
    return result
