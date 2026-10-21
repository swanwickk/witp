"""brute_locate.py — 不依赖行对齐的字段偏移定位

思路：
  取存档里所有"在用槽"的某个字节偏移，构成一条取值序列 S(off)。
  取 CSV 某列在所有行上的取值序列 C(col)。
  若 S(off) 是 C(col) 的**子序列**（长度相等且逐项相等），且 C 里该值分布非平凡，
  则 off 就是该列的偏移。

  为避免 8499 vs 5173 的行数不匹配，改为比较"值的多重集合 + 相邻差分模式"，
  更稳的做法：只用在存档中能唯一定位的锚点列（Name）确定映射，再逐列比。

实测更有效的替代方案：**直接按结构体尺寸等分 + 用已知字段校准**。
本脚本实现后者。
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
SCEN = os.path.join(G, "SCEN")

KIND = {"loc": (21096000, 1172, "WITPloc"),
        "shp": (9280000, 464, "WITPshp"),
        "grp": (20400680, 680, "WITPgrp")}


def csv_rows(scen, pre):
    with open(os.path.join(SCEN, f"{pre}{scen:03d}.csv"), encoding="latin1") as fh:
        return list(csv.DictReader(fh))


def block(path, kind):
    ln = KIND[kind][0]
    for r in read_container(path)["records"]:
        if len(r["data"]) == ln:
            return r["data"]
    raise SystemExit("no block")


def main(kind, save, scen):
    sz = KIND[kind][1]
    blk = block(save, kind)
    rows = csv_rows(scen, KIND[kind][2])

    # 存档侧：所有命名槽的 (槽号, 名字)
    slots = []
    for i in range(len(blk) // sz):
        b = i * sz
        nm = blk[b:b + 25].split(b"\x00")[0].decode("latin1", "replace").strip()
        if nm:
            slots.append((i, nm))
    print(f"{kind}: 存档命名槽 {len(slots)}, CSV 行 {len(rows)}")

    # 名称多重集合对照，看看是否是同一批单位
    a = Counter(nm for _, nm in slots)
    b = Counter((r.get("Name") or "").strip() for r in rows if (r.get("Name") or "").strip())
    common = sum((a & b).values())
    print(f"名称交集（按多重集合）: {common} / {sum(a.values())}")
    if common < 100:
        print("!! 交集过小，CSV 与存档不是同一剧本单位集，无法定位")
        return

    # 按名称分组，组内按出现顺序一一配对（重名单位也能对上）
    from collections import defaultdict
    by_name_save = defaultdict(list)
    for i, nm in slots:
        by_name_save[nm].append(i)
    by_name_csv = defaultdict(list)
    for r in rows:
        nm = (r.get("Name") or "").strip()
        if nm:
            by_name_csv[nm].append(r)

    paired = []
    for nm, csv_list in by_name_csv.items():
        for slot, r in zip(by_name_save.get(nm, []), csv_list):
            paired.append((slot, r))
    print(f"可配对 {len(paired)} 行")

    offs = {}
    for off in range(sz):
        offs[off] = tuple(blk[i * sz + off] for i, _ in paired)

    print(f"\n{'列名':<20}{'偏移':>7}  {'唯一性':>6}")
    ok = 0
    for col in paired[0][1].keys():
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
            if n < 0 or n > 0xFFFF:
                good = False
                break
            vals.append(n)
        if not good:
            continue
        if len(set(vals)) < 2:
            continue
        # u8
        key8 = tuple(v & 0xFF for v in vals)
        hit8 = [o for o, s in offs.items() if s == key8 and max(vals) <= 0xFF]
        if hit8:
            print(f"{col:<20}{hit8[0]:>7}  u8 x{len(hit8)}")
            ok += 1
            continue
        # u16
        best = []
        for o in range(sz - 1):
            ser = tuple(struct.unpack_from("<H", blk, i * sz + o)[0]
                        for i, _ in paired)
            if ser == tuple(vals):
                best.append(o)
        if best:
            print(f"{col:<20}{best[0]:>7}  u16 x{len(best)}")
            ok += 1
    print(f"\n成功 {ok} 列")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loc",
         sys.argv[2] if len(sys.argv) > 2 else "",
         int(sys.argv[3]) if len(sys.argv) > 3 else 3)
