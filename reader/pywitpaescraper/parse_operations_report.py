"""
Parser for {a|j}operationsreport.txt.

File naming:
  Allied side  -> aoperationsreport.txt
  Japan side   -> joperationsreport.txt

File format:
  Line 1  : "OPERATIONAL REPORT FOR <date>"  (e.g. "Dec 24, 41")
  Body    : One logical event per line.  The game engine may wrap long lines at
            ~79 chars with no indentation on the continuation; wrapped
            continuations contain no leading keyword.

Observed line patterns (Allied file - aoperationsreport.txt):
  - Sub assignment  : "SS <name> assigned to offensive patrol <x1>,<y1> - <x2>,<y2> off <location>"
  - Coastwatcher    : "Coastwatcher sighting: <n> Japanese ship(s) at <x>,<y> near <location> , Speed <n> , Moving <dir>"
  - Repair report   : "No additional repairs possible on <ship> using currently assigned resources at <location>"
  - TF out of fuel  : "Task Force <n> out of fuel at <x>, <y>"
  - TF sighting     : "TF <n> sights/detected by/snooped by/followed by/shadowed by ... at <x>,<y> near <location>"
  - Mine sweep      : "Mine Sweeping TF <n> resumes patrol, enroute to <x>, <y>  near <location>"
  - Ship snooped    : "<ship> snooped by/observed/detects ... at <x>,<y> near <location>"
  - Sub sighting    : "PBY-5 Catalina reports [possible ]submarine at <x>, <y> near <location>"

Observed line patterns (Japan file - joperationsreport.txt):
  - TF transfer     : "SS <name> transfers to <location>"
  - Occupation      : "<location> is occupied by the Japanese"
  - TF behaviour    : "Task Force <n> slows down to allow following TF <n> to catch up"
  - Coastwatcher    : "Coastwatcher Report: <n> ship in port at <location>"
  - Sighting report : "<aircraft> sighting report: <n> Allied ships at <x>,<y> near <location>..."
  - Sub detection   : "<aircraft> reports [possible ]submarine/shadow/conning tower at <x>, <y> near <location>"
  - Auto convoy     : "Auto Convoy TF <n> will load <cargo> at <location> for return to <dest>"
  - TF detection    : "TF <n> detected/shadowed by <aircraft> at <x>,<y> near <location>"

TODO: join wrapped continuation lines and parse each event into typed records.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger("pywitpae.operations_report")

_COORD_PAIR_RE = re.compile(r"(\d+)\s*,\s*(\d+)")
_NEAR_LOCATION_RE = re.compile(r"\bnear\s+(.+)$", re.IGNORECASE)
_AT_LOCATION_RE = re.compile(r"\bat\s+([^,]+?)(?:\s+for\s+return\s+to|\s*$)", re.IGNORECASE)
_OFF_LOCATION_RE = re.compile(r"\boff\s+(.+)$", re.IGNORECASE)
_TRANSFER_TO_RE = re.compile(r"\btransfers to\s+(.+)$", re.IGNORECASE)
_TASK_FORCE_ID_RE = re.compile(r"\b(?:Task Force|TF|Auto Convoy TF|Mine Sweeping TF)\s+(\d+)\b", re.IGNORECASE)
_OCCUPATION_RE = re.compile(r"^(.+?)\s+is occupied by the Japanese$", re.IGNORECASE)


@dataclass
class OperationsEvent:
    text: str
    category: str
    coordinates: tuple[int, int] | None = None
    location: str | None = None
    task_force_id: int | None = None


@dataclass
class OperationsReportLog:
    side: str = ""              # "US" or "JAPAN"
    game_date: str | None = None
    raw_lines: list[str] = field(default_factory=list)
    normalized_lines: list[str] = field(default_factory=list)
    events: list[OperationsEvent] = field(default_factory=list)


def _line_may_continue(line: str) -> bool:
    # Most complete entries end with punctuation, a direction, or a full word.
    # Wrapped entries often end mid-word (e.g. "Movi") with no punctuation.
    if not line:
        return False
    if line.endswith((".", ":", ")")):
        return False
    parts = line.split()
    if not parts:
        return False
    last_word = parts[-1]
    if len(last_word) <= 2:
        return True
    if last_word.isdigit():
        return False
    return last_word[-1].isalpha() and last_word[-1].islower()


def _coalesce_wrapped_lines(lines: list[str]) -> list[str]:
    combined: list[str] = []
    i = 0
    while i < len(lines):
        current_raw = lines[i]
        current = re.sub(r"\s+", " ", current_raw).strip()
        if not current:
            i += 1
            continue

        while i + 1 < len(lines):
            nxt_raw = lines[i + 1]
            nxt = re.sub(r"\s+", " ", nxt_raw).strip()
            if not nxt:
                i += 1
                continue

            # Join only when the source line is near fixed-width limit and
            # continuation clearly starts mid-word.
            source_looks_wrapped = len(current_raw.rstrip()) >= 78
            continuation_looks_midword = bool(re.match(r"^[a-z]", nxt))
            if not (source_looks_wrapped and continuation_looks_midword and _line_may_continue(current)):
                break

            current = f"{current}{nxt}"
            current_raw = current_raw.rstrip() + nxt_raw.lstrip()
            i += 1
        combined.append(current)
        i += 1
    return combined


def _extract_coordinates(text: str) -> tuple[int, int] | None:
    match = _COORD_PAIR_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _extract_location(text: str) -> str | None:
    occ_match = _OCCUPATION_RE.match(text)
    if occ_match:
        return occ_match.group(1).strip()

    near_match = _NEAR_LOCATION_RE.search(text)
    if near_match:
        location = near_match.group(1).strip()
        location = re.split(r"\s+,\s+Speed\b", location, maxsplit=1, flags=re.IGNORECASE)[0]
        return location.strip()

    off_match = _OFF_LOCATION_RE.search(text)
    if off_match:
        return off_match.group(1).strip()

    transfer_match = _TRANSFER_TO_RE.search(text)
    if transfer_match:
        return transfer_match.group(1).strip()

    at_match = _AT_LOCATION_RE.search(text)
    if at_match:
        return at_match.group(1).strip()
    return None


def _classify_event(text: str) -> str:
    lowered = text.lower()
    if "coastwatcher" in lowered:
        return "coastwatcher"
    if "transfers to" in lowered:
        return "transfer_event"
    if "slows down to allow following" in lowered:
        return "task_force_coordination"
    if "out of fuel" in lowered:
        return "task_force_out_of_fuel"
    if "is occupied by the japanese" in lowered:
        return "occupation"
    if "no additional repairs possible" in lowered:
        return "repair_status"
    if "assigned to offensive patrol" in lowered:
        return "sub_patrol_assignment"
    if "resumes patrol" in lowered:
        return "patrol_resume"
    if "sighting report:" in lowered:
        return "air_sighting"
    if "reports submarine" in lowered or "reports possible submarine" in lowered or "reports conning tower" in lowered:
        return "sub_detection"
    if "reports shadow in water" in lowered:
        return "contact_report"
    if "credited with kill number" in lowered:
        return "kill_credit"
    if "attains ace status" in lowered:
        return "ace_status"
    if "detected by" in lowered or "snooped by" in lowered or "shadowed by" in lowered or "followed by" in lowered:
        return "detection_event"
    if "auto convoy tf" in lowered:
        return "auto_convoy"
    if "task force" in lowered or re.search(r"\bTF\s+\d+\b", text):
        return "task_force_event"
    if "sights " in lowered or "sighted by" in lowered or "observes " in lowered or "detects " in lowered:
        return "detection_event"
    return "other"


def _parse_event(text: str) -> OperationsEvent:
    tf_id = None
    tf_match = _TASK_FORCE_ID_RE.search(text)
    if tf_match:
        tf_id = int(tf_match.group(1))
    return OperationsEvent(
        text=text,
        category=_classify_event(text),
        coordinates=_extract_coordinates(text),
        location=_extract_location(text),
        task_force_id=tf_id,
    )


def load(path: Path, side: str) -> OperationsReportLog:
    LOGGER.info("[operations-report] Loading %s (side=%s)", path, side)
    result = OperationsReportLog(side=side)
    lines = path.read_text(encoding="gbk", errors="replace").splitlines()
    result.raw_lines = lines
    if lines:
        result.game_date = lines[0].strip()
        LOGGER.info("[operations-report] %s", result.game_date)
    LOGGER.info("[operations-report] %d lines read", len(lines))

    body_lines = lines[1:] if lines else []
    result.normalized_lines = _coalesce_wrapped_lines(body_lines)
    result.events = [_parse_event(line) for line in result.normalized_lines if line]

    category_counts: dict[str, int] = {}
    for ev in result.events:
                category_counts[ev.category] = category_counts.get(ev.category, 0) + 1

    LOGGER.info("[operations-report] %d normalized entries", len(result.normalized_lines))
    LOGGER.info("[operations-report] category counts=%s", dict(sorted(category_counts.items())))
    if result.events:
                sample = result.events[0]
                LOGGER.info(
                        "[operations-report] sample category=%s tf=%s coords=%s location=%s text='%s'",
                        sample.category,
                        sample.task_force_id,
                        sample.coordinates,
                        sample.location,
                        sample.text,
                )
    return result
