"""
WitP-AE 地图几何引擎（全剧本通用，替代写死的 42.86/37.5 px/格）

为什么需要它：
  旧 set-dest 只标定「原点」（像素(500,500) 对应哪个 hex），但**比例写死 42.86/37.5**。
  比例稍有误差就产生**系统性邻格偏移** —— 实测第 1 回合 5 条编队指令精确命中仅 3/5，
  错误全是「偏 1 格」，而当时的判据容忍 ±1，于是偏差被洗成「确认」。
  本模块用**实测样本**拟合真比例，任何剧本、任何分辨率都通用。

模型（WitP-AE 为 odd-r 偏移六角格）：
    px = ox + hx * W
    py = oy + hy * H + (hx & 1) * SHIFT      # SHIFT ∈ {0, H/2}
  拟合步骤：
    ① 同 hy 的样本对求 W = Δpx / Δhx（取中位数，抗 OCR 离群）
    ② 同 hx 的样本对求 H = Δpy / Δhy（同上）
    ③ 枚举 SHIFT ∈ {0, H/2} 与全部样本一起最小二乘定 ox/oy，取残差更小者
"""
import json
import math
import os
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

CACHE = "/root/.hermes/profiles/witp/workspace/mapgeom.json"


def _solve_linear(A, b):
    """解最小二乘 A x = b（高斯消元，A 为 n×m 列表，b 长度 n）。返回 x 列表。"""
    n = len(A)
    m = len(A[0])
    # 正规方程 (AᵀA) x = Aᵀb
    AtA = [[sum(A[k][i] * A[k][j] for k in range(n)) for j in range(m)] for i in range(m)]
    Atb = [sum(A[k][i] * b[k] for k in range(n)) for i in range(m)]
    for i in range(m):                      # 高斯消元
        p = max(range(i, m), key=lambda r: abs(AtA[r][i]))
        if abs(AtA[p][i]) < 1e-12:
            return None
        AtA[i], AtA[p] = AtA[p], AtA[i]
        Atb[i], Atb[p] = Atb[p], Atb[i]
        for r in range(i + 1, m):
            f = AtA[r][i] / AtA[i][i]
            for c in range(i, m):
                AtA[r][c] -= f * AtA[i][c]
            Atb[r] -= f * Atb[i]
    x = [0.0] * m
    for i in range(m - 1, -1, -1):
        s = Atb[i] - sum(AtA[i][j] * x[j] for j in range(i + 1, m))
        x[i] = s / AtA[i][i]
    return x


def _fit_once(samples):
    """单次最小二乘拟合（无鲁棒处理）。返回 dict 或 None。"""
    if len(samples) < 4:
        return None
    Ax = [[1.0, float(hx)] for _, _, hx, _ in samples]
    bx = [float(px) for px, _, _, _ in samples]
    solx = _solve_linear(Ax, bx)
    Ay = [[1.0, float(hy), float(hx & 1)] for _, _, hx, hy in samples]
    by = [float(py) for _, py, _, _ in samples]
    soly = _solve_linear(Ay, by)
    if not solx or not soly:
        return None
    ox, W = solx
    oy, H, A = soly
    if not (10 < W < 120 and 10 < H < 120):
        return None
    shift = 0.0 if abs(A) < abs(A - H / 2) else H / 2.0
    res, err = [], 0.0
    for px, py, hx, hy in samples:
        ex = ox + hx * W
        ey = oy + hy * H + (hx & 1) * shift
        err += (ex - px) ** 2 + (ey - py) ** 2
        res.append(math.hypot(ex - px, ey - py))
    return {"W": W, "H": H, "ox": ox, "oy": oy, "shift": shift, "raw_parity_A": A,
            "rmse": math.sqrt(err / len(samples)), "n": len(samples), "residuals": res}


def fit(samples: List[Tuple[float, float, int, int]]) -> Optional[Dict[str, Any]]:
    """samples: [(px, py, hx, hy), ...] → 几何参数 dict（**MAD 迭代重加权的稳健拟合**）。

    ★2026-09-25 两次改进★
      ① 旧实现靠「同 hy / 同 hx 的样本对」取中位数 —— 散点样本几乎凑不出对，
         实测 ΔH=2.1 px/格、RMSE 18px（跨 20 格偏 45px）。
      ② 改最小二乘后又发现：**一处 OCR 误读就能把 W 带偏 2.8 px/格**（固定阈值剔除无效，
         因为坏点污染了拟合本身，残差整体抬高、坏点反而混在阈值内）。
      现采用 **MAD 迭代重加权**：按残差中位数与 MAD 定阈（med+3·MAD），剔除后重拟合，
      最多迭代 3 次 —— 对 ≤1/3 的离群样本鲁棒。
    """
    cur = list(samples)
    g = _fit_once(cur)
    if not g:
        return None
    for _it in range(3):
        res = g["residuals"]
        med = median(res)
        mad = median([abs(r - med) for r in res]) or 1.0
        thr = med + 3.0 * mad
        keep = [s for s, r in zip(cur, res) if r <= thr]
        if len(keep) == len(cur) or len(keep) < 4:
            break
        g2 = _fit_once(keep)
        if not g2:
            break
        dropped = len(samples) - len(keep)
        g2["outliers_dropped"] = dropped
        cur, g = keep, g2
    g.pop("residuals", None)
    return g



def hex_to_px(g: Dict[str, Any], hx: int, hy: int) -> Tuple[int, int]:
    px = g["ox"] + hx * g["W"]
    py = g["oy"] + hy * g["H"] + (hx & 1) * g["shift"]
    return int(round(px)), int(round(py))


def px_to_hex(g: Dict[str, Any], px: float, py: float) -> Tuple[int, int]:
    hx = int(round((px - g["ox"]) / g["W"]))
    hy = int(round((py - g["oy"] - (hx & 1) * g["shift"]) / g["H"]))
    return hx, hy


def save_geom(g: Dict[str, Any]) -> None:
    g = dict(g)
    g["saved_at"] = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)


def load_geom() -> Optional[Dict[str, Any]]:
    try:
        with open(CACHE, encoding="utf-8") as f:
            g = json.load(f)
        if g.get("W") and g.get("H"):
            return g
    except Exception:
        pass
    return None
