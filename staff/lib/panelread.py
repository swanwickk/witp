#!/usr/bin/env python3
"""
★2026-10-04 面板读数器（替换失效的 _read_row_pct）★

实测依据：
  详情面板的 Patrol levels 区块内，行序固定为
      ASW / Search / Train / Rest / Current Altitude / Maximum Range
  数值列在标签右侧固定 x 区间，肉眼与 OCR 都能稳定读出
  （实测 VS-2 面板：ASW 0 / Search 100 / Train 0 / Rest 0）。
  原 `_read_row_pct` 失败原因是**在整图上按「亮度簇」猜按钮位置**，
  而面板里按钮与文字的亮度接近，簇识别必然漂 ⇒ 读数窗错 ⇒ None。
  改为「先裁出 Patrol 区块，再按行序 + 固定 x 区间读数字」，不再猜按钮。
"""
import os
import re
import subprocess

from PIL import Image, ImageOps

# Patrol levels 区块（窗内坐标，实测 VS-2 面板）
_PAT_X0, _PAT_X1 = 430, 700
_ROWS = ["ASW", "Search", "Train", "Rest", "Current Altitude", "Maximum Range"]


def _shot_win(path="/tmp/_pr.png"):
    sys_path = None
    from lib.executor import get_window_offset
    ox, oy = get_window_offset()
    subprocess.run(["import", "-window", "root", path],
                   env=dict(os.environ, DISPLAY=":98"), timeout=15)
    im = Image.open(path)
    return im.crop((ox, oy, ox + 1024, oy + 768)), ox, oy


def _ocr_num(img, whitelist="0123456789"):
    img = ImageOps.autocontrast(ImageOps.grayscale(img))
    img = img.resize((img.width * 8, img.height * 8), Image.LANCZOS)
    img.save("/tmp/_pr_num.png")
    raw = subprocess.run(
        ["tesseract", "/tmp/_pr_num.png", "stdout",
         "--psm", "7", "-c", f"tessedit_char_whitelist={whitelist}"],
        capture_output=True, text=True, timeout=40).stdout
    t = raw.strip().replace("O", "0").replace("o", "0") \
                 .replace("C", "0").replace("S", "5").replace("I", "1") \
                 .replace("L", "1").replace("B", "8").replace("G", "6")
    m = re.search(r"\d{1,3}", t)
    return int(m.group()) if m else None


def read_panel_levels(verbose=True):
    """
    返回 {行名: 数值}；读不到的键不出现在结果里。

    ★2026-10-04 修★ 原实现靠 OCR 找 "Patrol levels" 标签定区块起点，
      但该标签是**黄字**，TSV 常把它置信度过滤掉（实测必然找不到）⇒ 永远返回 {}。
      改为**纯像素法**：ASW/Search/Train/Rest/Altitude/Range 六行在面板里
      行距均匀且等宽，直接在已知 x 带内数行峰，从 Search 行（已知固定
      序号 1）起读数。完全不含 OCR 标签依赖。
    """
    win, ox, oy = _shot_win()
    win.save("/tmp/_pr_w.png")

    import numpy as np
    a = np.array(win.convert("L"))
    band = a[_BAND_Y0:_BAND_Y1, _PAT_X0:_PAT_X1]
    med = np.median(band)
    bright = (band > med + 40).sum(axis=1)
    peaks, cur = [], None
    for i, v in enumerate(bright):
        if v >= 5:
            cur = [i, i] if cur is None else [cur[0], i]
        else:
            if cur is not None:
                peaks.append(cur)
                cur = None
    if cur is not None:
        peaks.append(cur)
    ys = [_BAND_Y0 + (p[0] + p[1]) // 2 for p in peaks]

    if verbose:
        print(f"      [面板读数] 行峰 y={ys}")
    out = {}
    for name, y in zip(_ROWS, ys):
        v = _ocr_num(win.crop((_PAT_X0, y - 7, _PAT_X1, y + 7)))
        if v is not None:
            out[name] = v
    if verbose:
        print(f"      [面板读数] → {out}")
    return out
