# -*- coding: utf-8 -*-
"""Probe: why are Zuikaku(EII)/Shoho(EIII) airgroups missing from export?"""
import sys
sys.path.insert(0, r"Z:\root\.hermes\workspace\witp-reader\pywitpaescraper")
from pathlib import Path
SAVE = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition\SAVE\wpae000.pws")
GAME = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition")
import witpae_today as W
inst = W.WITPAE_Today(GAME, SAVE, SAVE, "Japan")
snap = inst._load_snapshot(SAVE)
ags = snap.get("airgroups", [])
print("airgroups total:", len(ags))
locs = snap.get("locations", [])
nloc = len(locs)
print("num locations:", nloc)
# find all airgroups whose name contains E, I, II, III
for a in ags:
    nm = str(a.get("name") or "")
    if any(k in nm for k in ("EI", "EII", "EIII", "Daitai", "Chutai")):
        nat = int(a.get("nation") or 0)
        print("  name=%s nation=%s allowed=%s delay=%s baseID=%s" %
              (nm, nat, inst._nation_allowed(nat), a.get("delay"), a.get("baseID")))
