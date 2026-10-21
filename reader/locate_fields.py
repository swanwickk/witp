"""locate_fields.py — 用官方 witploadAE 的 CSV 值反推存档字节偏移

原理：
  witploadAE /e 导出的 CSV 是**官方字段名 + 值**，顺序与存档记录里的结构体一致。
  对每个 CSV 列，取它在多个单位上的取值序列，去存档里搜索"哪个字节偏移的取值序列
  与之完全吻合"。吻合则定位成功。

适用：存档与 CSV 来自同一剧本时最准；跨剧本需按名称对齐。
"""
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

G = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
     + chr(39) + "s Edition")
SCEN = os.path.join(G, "SCEN")
SAVE = os.path.join(G, "SAVE")

KIND = {
    "loc": (21096000, 1172, "WITPloc"),
    "shp": (9280000, 464, "WITPshp"),
    "grp": (20400680, 680, "WITPgrp"),
}


def load_csv(scen, pre):
    p = os.path.join(SCEN, f"{pre}{scen:03d}.csv")
    with open(p, encoding="latin1") as fh:
        rd = csv.DictReader(fh)
        return [dict(r) for r in rd]


def block(path, kind):
    ln = KIND[kind][0]
    for r in read_container(path)["records"]:
        if len(r["data"]) == ln:
            return r["data"]
    raise SystemExit(f"{path}: 无 {kind} 记录")


def slot_names(blk, kind, ordered=False):
    """返回 名称->槽（ordered=True 时返回 [(槽,名)] 保留重复）。"""
    sz = KIND[kind][1]
    out = {} if not ordered else []
    for i in range(len(blk) // sz):
        b = i * sz
        nm = blk[b:b + 25].split(b"\x00")[0].decode("latin1", "replace").strip()
        if not nm:
            continue
        if ordered:
            out.append((i, nm))
        else:
            out.setdefault(nm, i)
    return out


def as_int(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def locate(kind, save_path, scen):
    sz = KIND[kind][1]
    blk = block(save_path, kind)
    rows = load_csv(scen, KIND[kind][2])
    names_in_save = slot_names(blk, kind)
    if not names_in_save:
        raise SystemExit("存档里没有可对齐的名称")

    # 按顺序配对：CSV 第 k 行 与 存档第 k 个"有名字的槽"一一对应
    # （存档记录与 SCEN 数据同序，这是 witploadAE 的既定布局）
    ordered = slot_names(blk, kind, ordered=True)
    paired = []
    csv_named = [r for r in rows if (r.get("Name") or "").strip()]
    for (slot, nm), r in zip(ordered, csv_named):
        if (r.get("Name") or "").strip() == nm:
            paired.append((slot, r))
    print(f"{kind}: CSV {len(rows)} 行，存档 {len(names_in_save)} 名，可对齐 {len(paired)} 个")
    if not paired:
        return

    # 对每个字节偏移，构造该偏移在各对齐单位上的取值序列
    off_series = {}
    for off in range(sz):
        key = tuple(blk[b * sz + off] for b, _ in paired)
        off_series.setdefault(((sz // 128) and (sz * 1000 // 128),), None)
    # 上面写法太绕，直接建 偏移 -> 序列
    off_series = {}
    for off in range(sz):
        off_series[off] = tuple(blk[b * sz + off] for b, _ in paired)

    # 对每个 CSV 列，构造取值序列，找匹配的偏移
    cols = list(paired[0][1].keys())
    print(f"\n{'列名':<20} {'偏移':>6}  匹配")
    hits = 0
    for col in cols:
        vals = []
        ok = True
        for _, r in paired:
            v = as_int(r.get(col))
            if v is None:
                ok = False
                break
            vals.append(v & 0xFF)
        if not ok:
            continue
        key = tuple(vals)
        if len(set(key)) < 2:          # 常量列无法定位
            continue
        found = [off for off, ser in off_series.items() if ser == key]
        if found:
            print(f"{col:<20} {found[0]:>6}  ← 唯一匹配 {len(found)} 处")
            hits += 1
        else:
            # 试 u16 小端的两字节
            u16 = []
            ok2 = True
            for _, r in paired:
                v = as_int(r.get(col))
                if v is None or v > 0xFFFF:
                    ok2 = False
                    break
                u16.append(v)
            if ok2:
                key16 = tuple(u16)
                f16 = []
                for off in range(sz - 1):
                    ser = tuple(struct.unpack_from("<H", blk, b * sz + off)[0]
                                for b, _ in paired)
                    if ser == key16:
                        f16.append(off)
                if f16:
                    print(f"{col:<20} {f16[0]:>6}  ← u16 匹配 {len(f16)} 处")
                    hits += 1
    print(f"\n定位成功 {hits} 列")


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "loc"
    save = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAVE, "wpae015.pws")
    scen = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    locate(kind, save, scen)
