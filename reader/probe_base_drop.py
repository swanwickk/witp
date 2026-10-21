# -*- coding: utf-8 -*-
"""Probe: why are Rabaul/PM dropped from bases.json export?"""
import sys, os
sys.path.insert(0, r"Z:\root\.hermes\workspace\witp-reader\pywitpaescraper")
from pathlib import Path
SAVE = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition\SAVE\wpae003.pws")
GAME = Path(r"Z:\root\.wine-witp\drive_c\1108r9\War in the Pacific Admiral's Edition")
import witpae_today as W
inst = W.WITPAE_Today(GAME, SAVE, SAVE, "Japan")
snap = inst._load_snapshot(SAVE)
locs = snap.get("locations", [])

# mimic export filters for key bases
import importlib
for name in ("Port Moresby", "Rabaul", "Lae", "Tulagi", "Truk", "Ponape"):
    for l in locs:
        if str(l.get("name")) == name and l.get("role") == "base":
            nat = int(l.get("nation") or 0)
            print("%-16s id=%-5s nation=%-3s allowed=%-5s arrive=%-3s x=%s y=%s type=%s" %
                  (name, l.get("id"), nat, inst._nation_allowed(nat), l.get("arrive"),
                   l.get("x"), l.get("y"), l.get("type")))
            break

print()
print("--- nation histogram of role==base ---")
from collections import Counter
bases = [l for l in locs if l.get("role") == "base"]
print(Counter(int(l.get("nation") or 0) for l in bases))
print("--- nation histogram of role==base with X<300 ---")
print(Counter(int(l.get("nation") or 0) for l in bases if 0 < (l.get("x") or 0) < 300))
print()
print("--- is_in_map_hex_range? ---")
try:
    from witpae_today import is_in_map_hex_range
    for l in bases:
        if str(l.get("name")) in ("Port Moresby", "Rabaul", "Truk"):
            print("  ", l.get("name"), l.get("x"), l.get("y"), is_in_map_hex_range(l.get("x"), l.get("y")))
except Exception as e:
    print("  no is_in_map_hex_range:", e)
print()
print("--- export loop: how many bases pass all filters ---")
n_all = n_pass = 0
for loc in locs:
    if str(loc.get("role")) != "base":
        continue
    n_all += 1
    nation = int(loc["nation"])
    if not inst._nation_allowed(nation):
        continue
    if not inst._arrived_by_gameday(int(loc.get("arrive", 0)), snap.get("gameday")):
        continue
    n_pass += 1
print("  base total:", n_all, " pass export filters:", n_pass)
