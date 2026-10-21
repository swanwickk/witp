"""locate_tf_fields.py — 定位 Loc 记录里的 TF/LCU 命令字段偏移

针对 TFRouting / TFReaction / TFRetirement / TFMission / TFMove / LCUStance
等一直找不到的命令字段（它们不在 PWSTaskGroup 里，而在 PWSLocation 记录里）。
"""
import csv
import os
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

G = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
     + chr(39) + "s Edition")
SAVE = os.path.join("/root/.wine-witp-mcp/prefix/drive_c/1108r9",
                    "War in the Pacific Admiral" + chr(39) + "s Edition",
                    "SAVE", "wpae015.pws")
CSV = os.path.join(G, "SCEN", "WITPloc003.csv")
SZ = 1172

COLS = ("TFRouting", "TFReaction", "TFRetirement", "TFMission", "TFMove",
        "LCUStance", "DestinationID", "DestX", "DestY", "Follow",
        "TargetID", "HomeBaseID", "WayPts1", "WayPts2", "Planning",
        "LCUFormationID", "Suffix", "primUnit")


def main():
    save = sys.argv[1] if len(sys.argv) > 1 else SAVE
    blk = [r for r in read_container(save)["records"]
           if len(r["data"]) == 21096000][0]["data"]
    rows = list(csv.DictReader(open(CSV, encoding="latin1")))

    slots = []
    for i in range(len(blk) // SZ):
        b = i * SZ
        nm = blk[b:b + 25].split(b"\x00")[0].decode("latin1", "replace").strip()
        if nm:
            slots.append((i, nm))

    bn = defaultdict(list)
    for i, nm in slots:
        bn[nm].append(i)
    bc = defaultdict(list)
    for r in rows:
        nm = (r.get("Name") or "").strip()
        if nm:
            bc[nm].append(r)

    paired = []
    for nm, cl in bc.items():
        for s_, r in zip(bn.get(nm, []), cl):
            paired.append((s_, r))
    print(f"配对 {len(paired)} 个槽\n")

    off8 = {o: tuple(blk[i * SZ + o] for i, _ in paired) for o in range(SZ)}
    off16 = {o: tuple(struct.unpack_from("<H", blk, i * SZ + o)[0]
                      for i, _ in paired) for o in range(SZ - 1)}

    print(f"{'列名':<18}{'分布':<26}{'u8偏移':<10}{'u16偏移'}")
    for col in COLS:
        vals = []
        good = True
        for _, r in paired:
            v = (r.get(col) or "").strip()
            if v == "":
                good = False
                break
            try:
                n = int(v)
            except ValueError:
                good = False
                break
            vals.append(n)
        dist = str(Counter(vals).most_common(4))[:24] if good else "(空/非常量)"
        if not good or len(set(vals)) < 2:
            print(f"{col:<18}{dist}")
            continue
        h8 = [o for o, s in off8.items()
              if s == tuple(v & 0xFF for v in vals) and max(vals) <= 255]
        h16 = [o for o, s in off16.items() if s == tuple(vals)]
        print(f"{col:<18}{dist:<26}{str(h8[:3]):<10}{h16[:3]}")


if __name__ == "__main__":
    main()
