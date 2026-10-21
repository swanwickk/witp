"""Minimal probe: how does this build's pwsdll.dll enumerate a real save?

Prints rec_type / PWSopened / return value for each iteration so we can see exactly
where the chain stops. Local diagnostic for the ekko WitP-AE project (not part of upstream).
"""
import ctypes
import sys
from pathlib import Path

import pwsdll as P


def main() -> int:
    dll_dir = Path(sys.argv[1])
    save = sys.argv[2]
    max_iter = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    pw = P.PWSDll(dll_dir)
    ctx = pw.new_context()
    rc = pw.pws_open_file(ctx, save, 0)
    print(f"open rc={rc} PWSopened={ctx.PWSopened} PWSid={int(ctx.PWSid)}")
    for i in range(max_iter):
        ret = pw.pws_get_next_item(ctx)
        print(f"  it={i:03d} ret={ret} PWSopened={ctx.PWSopened} PWSid={int(ctx.PWSid)}")
        if ctx.PWSopened < 0:
            print("  -> terminator reached (PWSopened < 0)")
            break
    print(f"close rc={pw.pws_close_file(ctx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
