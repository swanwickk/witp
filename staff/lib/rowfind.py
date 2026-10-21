#!/usr/bin/env python3
"""
从列表截图里定位数据行的 y（纯像素法，不依赖 OCR/视觉）。

实测背景：A 列表 OCR 好用；N 列表（舰载）队名 OCR 几乎全错，
`_find_airgroup_row` 因此定位失败 ⇒ set-search 点不到行 ⇒ 设了等于没设。
像素法则只数「横向文字密度」的行峰，与内容无关，两种列表通用。

用法：
    rows = find_rows("/tmp/dbgNw.png", x0=150, x1=700, y0=320, y1=470)
"""
import numpy as np
from PIL import Image


def find_rows(path, x0=150, x1=700, y0=315, y1=480, thresh=8, min_gap=6):
    """
    返回 [(行中心y, 该行文字像素数), ...]，按 y 升序。
    """
    im = Image.open(path).convert("L")
    a = np.array(im)
    band = a[y0:y1, x0:x1]
    # 背景是纹理噪点 ⇒ 用「比局部中位数亮很多」当作文字
    med = np.median(band)
    bright = (band > med + 40).sum(axis=1)
    peaks = []
    cur = None
    for i, v in enumerate(bright):
        y = y0 + i
        if v >= thresh:
            cur = [y, y, v] if cur is None else [cur[0], y, max(cur[2], v)]
        else:
            if cur is not None:
                peaks.append(cur)
                cur = None
    if cur is not None:
        peaks.append(cur)

    # 行峰去重（同一行可能被高阈值切成多段，间隔 < min_gap 合并）
    merged = []
    for p in peaks:
        if merged and p[0] - merged[-1][1] <= min_gap:
            merged[-1][1] = p[1]
            merged[-1][2] = max(merged[-1][2], p[2])
        else:
            merged.append(p)
    return [((p[0] + p[1]) // 2, p[2]) for p in merged if p[2] >= thresh]


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dbgNw.png"
    for y, n in find_rows(p):
        print(f"y={y}  文字像素={n}")
