#!/usr/bin/env python3
"""
★地图几何标定（实测事实库）★

用途：把「像素 ↔ Hex」的真值持久化，供 set-dest 直接查表命中，
不再依赖任何比例模型（实测证明线性模型在 hex 错列网格上必然有半格误差）。

标定方式：对同一视野状态，逐点实点地图 + 读 TF 面板 Destination 行回读。
每条记录 = (像素x, 像素y, hex_x, hex_y, 视野锚点)。
视野一变（滚动/跳转）则整表失效，必须以新锚点重新标定。
"""
import json
import os

CAL_FILE = "/tmp/witp_map_cal.json"


def load(anchor=None):
    """anchor=(hex_at_PROBE, probe_px)；不匹配当前锚点则返回空表。"""
    try:
        with open(CAL_FILE) as f:
            d = json.load(f)
    except Exception:
        return {}
    if anchor is not None and tuple(d.get("anchor", [])) != tuple(anchor):
        return {}
    return {tuple(int(v) for v in k.split(",")): (h[0], h[1])
            for k, h in d.get("points", {}).items()}


def save(anchor, points):
    """points: {(px,py): (hx,hy)}"""
    d = {"anchor": list(anchor),
         "points": {f"{k[0]},{k[1]}": list(v) for k, v in points.items()},
         "ts": __import__("time").time()}
    with open(CAL_FILE, "w") as f:
        json.dump(d, f, indent=1)
    return len(points)


def find_hex(hx, hy):
    for px, h in load().items():
        if h == (hx, hy):
            return px
    return None


if __name__ == "__main__":
    pts = {
        (220, 231): (105, 143),
        (200, 324): (104, 150),
        (180, 416): (103, 153),
        (240, 138): (105, 145),
        (260, 45):  (105, 145),
        (300, 120): (106, 145),
        (200, 231): (104, 148),
        (220, 324): (105, 150),
    }
    n = save((106, 145, 300, 120), pts)
    print(f"已保存 {n} 条标定 → {CAL_FILE}")
    print("反查 (104,148) →", find_hex(104, 148))
