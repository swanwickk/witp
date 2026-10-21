import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: verify_turn_json.py <turn.json path> <required scenario substring>")
        return 2

    turn_json_path = Path(sys.argv[1])
    required_substring = sys.argv[2]

    if not turn_json_path.exists():
        print(f"ERROR: turn.json not found: {turn_json_path}")
        return 1

    try:
        payload = json.loads(turn_json_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: failed to parse JSON from {turn_json_path}: {exc}")
        return 1

    scenario_name = str(payload.get("scenario_name", ""))
    if required_substring.lower() not in scenario_name.lower():
        print(
            "ERROR: scenario_name did not contain required text. "
            f"required='{required_substring}' actual='{scenario_name}'"
        )
        return 1

    print(
        "OK: turn.json scenario_name check passed. "
        f"required='{required_substring}' actual='{scenario_name}'"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
