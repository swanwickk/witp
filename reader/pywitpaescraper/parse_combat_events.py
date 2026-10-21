"""
Parser for CombatEvents.txt.

File format:
  Line 1  : "COMBAT EVENTS FOR <date>"  (e.g. "COMBAT EVENTS FOR 12/24/41")
  Body    : Phase / event lines, one per line.

Observed line patterns:
  - All-caps phase headers   (e.g. "ADJUST TASK FORCE MISSIONS",
                                   "CALCULATE RANGE TO ENEMY",
                                   "ROUTINE AIR OPERATIONS")
  - Routine air-ops steps    (e.g. "setting CAP over objective",
                                   "withdrawing depleted air units",
                                   "planning major raids",
                                   "assigning bombers to transport duty",
                                   "assigning night missions")
  - Occupation events        (e.g. "Calayan is occupied by the Japanese")

Both sides' events appear in the same file; no side prefix.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger("pywitpae.combat_events")

_OCCUPATION_RE = re.compile(r"^(.+?)\s+is occupied by the\s+(.+)$", re.IGNORECASE)


@dataclass
class CombatPhaseBlock:
    header: str
    lines: list[str] = field(default_factory=list)


@dataclass
class CombatEventsLog:
    game_date: str | None = None
    raw_lines: list[str] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)
    phase_blocks: list[CombatPhaseBlock] = field(default_factory=list)
    occupation_events: list[str] = field(default_factory=list)


def _is_phase_header(text: str) -> bool:
    if not text:
        return False
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return all(ch.isupper() for ch in letters)


def _parse_entries(entries: list[str]) -> tuple[list[CombatPhaseBlock], list[str]]:
    phase_blocks: list[CombatPhaseBlock] = []
    occupation_events: list[str] = []

    current_phase: CombatPhaseBlock | None = None
    for entry in entries:
        if _is_phase_header(entry):
            current_phase = CombatPhaseBlock(header=entry)
            phase_blocks.append(current_phase)
            continue

        if _OCCUPATION_RE.match(entry):
            occupation_events.append(entry)

        if current_phase is None:
            current_phase = CombatPhaseBlock(header="UNSCOPED")
            phase_blocks.append(current_phase)
        current_phase.lines.append(entry)

    return phase_blocks, occupation_events


def load(path: Path) -> CombatEventsLog:
    LOGGER.info("[combat-events] Loading %s", path)
    result = CombatEventsLog()
    lines = path.read_text(encoding="gbk", errors="replace").splitlines()
    if lines:
        result.game_date = lines[0].strip()
        LOGGER.info("[combat-events] %s", result.game_date)

    result.raw_lines = lines
    LOGGER.info("[combat-events] %d lines read", len(lines))

    result.entries = [line.strip() for line in lines[1:] if line.strip()]
    result.phase_blocks, result.occupation_events = _parse_entries(result.entries)

    LOGGER.info(
        "[combat-events] phases=%s occupation_events=%s",
        len(result.phase_blocks),
        len(result.occupation_events),
    )
    if result.phase_blocks:
        first = result.phase_blocks[0]
        LOGGER.info("[combat-events] first phase='%s' line_count=%s", first.header, len(first.lines))
    return result
