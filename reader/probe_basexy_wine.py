# -*- coding: utf-8 -*-
"""Probe raw .pws location coordinates (ASCII output only)."""
import sys, os
sys.path.insert(0, r"Z:\root\.hermes\workspace\witp-reader\pywitpaescraper")
from pathlib import Path

SAVE = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition\SAVE\wpae003.pws")
GAME = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition")

import witpae_today as W
inst = W.WITPAE_Today(GAME, SAVE, SAVE, "Japan")
snap = inst._load_snapshot(SAVE)
locs = snap.get("locations", [])
print("location total:", len(locs))

real = [l for l in locs if l.get("x") is not None and 0 < l.get("x") < 300]
print("X in (0,300):", len(real))

from collections import Counter
print("role counter (all):", Counter(str(l.get("role")) for l in locs))
print("role counter (real X):", Counter(str(l.get("role")) for l in real))

bases = [l for l in locs if l.get("role") == "base"]
print("base total:", len(bases))
rc = [b for b in bases if b.get("x") is not None and 0 < b.get("x") < 300]
print("base with valid X:", len(rc))

print("--- first 12 bases raw X/Y ---")
for b in bases[:12]:
    print("   id=%s name=%s x=%s y=%s type=%s" % (b.get("id"), b.get("name"), b.get("x"), b.get("y"), b.get("type")))

print("--- key bases ---")
for l in locs:
    nm = str(l.get("name") or "")
    if any(k in nm for k in ("Moresby", "Rabaul", "Truk", "Lae", "Tulagi")):
        print("   id=%s name=%s x=%s y=%s role=%s type=%s destX=%s destY=%s" %
              (l.get("id"), nm, l.get("x"), l.get("y"), l.get("role"), l.get("type"),
               l.get("destX"), l.get("destY")))

# Also: what does locations_xy hold for the TF ids?
xy = snap.get("locations_xy", {})
print("locations_xy size:", len(xy))
sample = list(xy.items())[:8]
print("locations_xy sample:", sample)
