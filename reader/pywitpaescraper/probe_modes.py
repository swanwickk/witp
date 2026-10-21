"""Minimal probe #2: does PWSOpenFile's third argument (mode) change enumeration?

Upstream always calls mode=0. Try several values and report where each run stops.
Local diagnostic for the ekko WitP-AE project (not part of upstream).
"""
import sys
from pathlib import Path

import pwsdll as P


def run(dll_dir: Path, save: str, mode: int, max_iter: int = 12) -> str:
    pw = P.PWSDll(dll_dir)
    ctx = pw.new_context()
    rc = pw.pws_open_file(ctx, save, mode)
    seq = []
    for _ in range(max_iter):
        pw.pws_get_next_item(ctx)
        seq.append(int(ctx.PWSid))
        if ctx.PWSopened < 0:
            break
    stop = ctx.PWSopened
    pw.pws_close_file(ctx)
    return f"mode={mode} open_rc={rc} seq={seq} final_PWSopened={stop}"


def main() -> int:
    dll_dir = Path(sys.argv[1])
    save = sys.argv[2]
    modes = [int(x) for x in sys.argv[3:]] or [0, 1, 2, 3]
    for m in modes:
        try:
            print(run(dll_dir, save, m))
        except Exception as exc:  # keep probing other modes
            print(f"mode={m} raised {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
