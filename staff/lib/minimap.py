#!/usr/bin/env python3
"""小地图跳转（绝对定位）—— 替代靠推算的方向键滚动。

★为什么需要它（2026-09-26 实测）★
  set-dest 的纠偏循环是「纯像素空间」的：点一次 → 回读落格 → 按格差×每格像素平移点击坐标。
  它收敛很快（实测 2 轮内到 1 格），但有一个硬前提：**目标像素必须落在窗口可点区内**。
  实测本地比例 H≈40px/格、可点 y 上限 740，而 hex150 需 780px —— 物理上够不着。
  推算法（方向键）已证不可靠：滚动量既非固定格数、又依赖焦点，三次实测互相矛盾。

★小地图是唯一可靠的绝对定位通道（实测）★
  · 点小地图**红框之外** → 视野真的跳过去（点红框之内只是重新居中）
  · 两次跳转的可达性已验证：见 minimap_calib.py / minimap_verify.py

用法：
    from lib import minimap
    c = minimap.load_calib()
    x, y = minimap.clamp_to_box(minimap.mm_for_hex(100, 150, c), c)
    vnc_click(x, y, "click")
然后由 set-dest 的纯像素空间闭环收尾（不依赖任何基准精度）。
"""
import json
import os

CALIB_PATH = "/root/.hermes/profiles/witp/workspace/mapgeom_minimap.json"

# 实测样本（minimap 像素 → 该次跳转后「像素(500,500)」对应的真实格）：
#   (905,672) → (99,119)      (1000,750) → (11,155)      (904,739) → (99,155)
# 三点最小二乘（数据本身有 ±5 格噪声，够用即可——闭环会吸收残差）
DEFAULT = {
    "ax": -0.9215, "bx": 932.5,        # hex_x = ax*mmx + bx
    "ay": 0.5370,  "by": -241.8,       # hex_y = ay*mmy + by
    "box": [892, 664, 1020, 764],      # 小地图可点范围（游戏窗口坐标）
    "samples": [[[905, 672], [99, 119]], [[1000, 750], [11, 155]], [[904, 739], [99, 155]]],
    "note": "噪声 ±5 格；只用于把目标拉进可点区，精度由闭环收尾",
}


def load_calib():
    try:
        with open(CALIB_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if all(k in d for k in ("ax", "bx", "ay", "by")):
            d.setdefault("box", DEFAULT["box"])
            return d
    except Exception:
        pass
    return dict(DEFAULT)


def save_calib(d):
    with open(CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def mm_for_hex(hx, hy, c=None):
    """目标格 → 应点的小地图像素。"""
    c = c or load_calib()
    return (int(round((hx - c["bx"]) / c["ax"])),
            int(round((hy - c["by"]) / c["ay"])))


def hex_for_mm(mx, my, c=None):
    """小地图像素 → 预计落到像素(500,500)的格（用于预测/自检）。"""
    c = c or load_calib()
    return (round(c["ax"] * mx + c["bx"], 1), round(c["ay"] * my + c["by"], 1))


def clamp_to_box(p, c=None):
    """把点击点夹进小地图可点范围（留 4px 边，避免点到边框）。"""
    c = c or load_calib()
    x0, y0, x1, y1 = c["box"]
    return (max(x0 + 4, min(x1 - 4, int(p[0]))),
            max(y0 + 4, min(y1 - 4, int(p[1]))))


def fit_from_samples(samples):
    """用 (mm → hex) 样本重新最小二乘拟合（样本多了可调此函数刷新标定）。"""
    import statistics
    if len(samples) < 2:
        return None
    xs = [s[0][0] for s in samples]; hx = [s[1][0] for s in samples]
    ys = [s[0][1] for s in samples]; hy = [s[1][1] for s in samples]

    def lin(a, b):
        n = len(a); ma = sum(a) / n; mb = sum(b) / n
        den = sum((v - ma) ** 2 for v in a)
        if den == 0:
            return 0.0, mb
        k = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / den
        return k, mb - k * ma
    ax, bx = lin(xs, hx)
    ay, by = lin(ys, hy)
    return {"ax": ax, "bx": bx, "ay": ay, "by": by,
            "samples": samples, "box": DEFAULT["box"]}
