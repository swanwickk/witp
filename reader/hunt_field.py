"""hunt_field.py — 按"值分布特征"在存档里定向搜索某字段的偏移

不依赖行对齐，只用 CSV 的**取值直方图**与存档各偏移的直方图比对。
适用于小基数枚举字段（TFRouting/TFReaction/TFRetirement/TFMove/LCUStance）。
"""
import csv
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

G = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
     + chr(39) + "s Edition")
SAVE = os.path.join("/root/.wine-witp-mcp/prefix/drive_c/1108r9",
                    "War in the Pacific Admiral" + chr(39) + "s Edition",
                    "SAVE", "wpae015.pws")
SZ = 1172


def main():
    cols = sys.argv[1:] or ["TFRouting", "TFReaction", "TFRetirement",
                            "TFMove", "LCUStance"]
    blk = [r for r in read_container(SAVE)["records"]
           if len(r["data"]) == 21096000][0]["data"]
    rows = list(csv.DictReader(open(os.path.join(G, "SCEN", "WITPloc003.csv"),
                                    encoding="latin1")))

    # 存档侧直方图（只用命名槽）
    slots = []
    for i in range(len(blk) // SZ):
        b = i * SZ
        if blk[b:b + 25].split(b"\x00")[0].strip():
            slots.append(i)
    print(f"命名槽 {len(slots)}")

    hist8 = {}
    for o in range(SZ):
        c = Counter(blk[i * SZ + o] for i in slots)
        if len(c) <= 8:                    # 只关心小基数
            hist8[o] = c

    for col in cols:
        cv = Counter()
        for r in rows:
            v = (r.get(col) or "").strip()
            if v == "":
                continue
            try:
                cv[int(v)] += 1
            except ValueError:
                pass
        if len(cv) < 2:
            print(f"\n{col}: CSV 常量或空，跳过 {dict(cv)}")
            continue
        print(f"\n{col}: CSV 分布 {cv.most_common(6)}")
        # 找"零值占绝大多数 + 同值集合"的偏移
        nz_csv = {k for k in cv if k}
        best = []
        for o, c in hist8.items():
            nz_off = {k for k in c if k}
            if nz_off == nz_csv:
                # 零值占比接近
                r_csv = cv.get(0, 0) / max(1, sum(cv.values()))
                r_off = c.get(0, 0) / max(1, sum(c.values()))
                best.append((abs(r_csv - r_off), o, c))
        best.sort()
        for d, o, c in best[:5]:
            print(f"   候选 off {o:>4} 分布 {c.most_common(6)}  零值比差 {d:.3f}")


if __name__ == "__main__":
    main()
