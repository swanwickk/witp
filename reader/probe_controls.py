#!/usr/bin/env python3
"""控件测绘器：对指定屏幕区域做悬停扫描，找出所有“会响应鼠标”的控件位置，输出控件图。

用法:
  probe_controls.py <名称> <x0> <y0> <x1> <y1> <步长> [阈值]
产物:
  /root/.hermes/profiles/witp/workspace/witp-reader/control_maps/<名称>.json  （原始响应点）
  /root/.hermes/profiles/witp/workspace/witp-reader/control_maps/<名称>.txt   （聚类后的矩形与摘要）

原理：先取一张基线截图，鼠标逐点移动后各截一张图，与基线做像素差；
差超阈值的点即“有响应”（悬停高亮/焦点框），再把相邻响应点聚成矩形。
注意：本脚本只移动鼠标、不点击，安全。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops

DISPLAY = ":98"
OUT = Path("/root/.hermes/profiles/witp/workspace/witp-reader/control_maps")
PARK = (1359, 2)          # 停放鼠标的位置（避免遮挡）


def shot(path: Path) -> Image.Image:
    subprocess.run(["import", "-window", "root", str(path)], check=True,
                   env={"DISPLAY": DISPLAY, "PATH": "/usr/bin:/bin"})
    return Image.open(path).convert("RGB")


def move(x: int, y: int) -> None:
    subprocess.run(["xdotool", "mousemove", str(x), str(y)],
                   env={"DISPLAY": DISPLAY, "PATH": "/usr/bin:/bin"}, check=False)


def diff_count(a: Image.Image, b: Image.Image, pix_thresh: int = 8) -> int:
    """快速像素差计数：用 C 实现的灰度化+直方图，避免逐像素 Python 循环。"""
    d = ImageChops.difference(a, b).convert("L")
    hist = d.histogram()
    return sum(hist[pix_thresh:])


def cluster(points: list[tuple[int, int]], gap: int = 18) -> list[tuple[int, int, int, int]]:
    """把相邻响应点聚成矩形 (x0,y0,x1,y1)。"""
    boxes: list[list[int]] = []
    for x, y in sorted(points, key=lambda p: (p[1], p[0])):
        for b in boxes:
            if b[0] - gap <= x <= b[2] + gap and b[1] - gap <= y <= b[3] + gap:
                b[0] = min(b[0], x); b[1] = min(b[1], y)
                b[2] = max(b[2], x); b[3] = max(b[3], y)
                break
        else:
            boxes.append([x, y, x, y])
    # 合并重叠矩形
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1]):
                    a[0] = min(a[0], b[0]); a[1] = min(a[1], b[1])
                    a[2] = max(a[2], b[2]); a[3] = max(a[3], b[3])
                    boxes.pop(j); merged = True; break
            if merged:
                break
    return [tuple(b) for b in boxes]


def main() -> int:
    name = sys.argv[1]
    x0, y0, x1, y1, step = (int(v) for v in sys.argv[2:7])
    thresh = int(sys.argv[7]) if len(sys.argv) > 7 else 250
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path("/tmp/_probe.png")

    move(*PARK); time.sleep(0.4)
    base = shot(tmp)
    hits: list[tuple[int, int, int]] = []
    n = 0
    t0 = time.time()
    for y in range(y0, y1 + 1, step):
        for x in range(x0, x1 + 1, step):
            move(x, y); time.sleep(0.05)
            cur = shot(tmp)
            d = diff_count(base, cur)
            n += 1
            if d >= thresh:
                hits.append((x, y, d))
        print(f"  …y={y} 已完成 {n} 点，命中 {len(hits)}，用时 {time.time()-t0:.0f}s", flush=True)
    move(*PARK)

    boxes = cluster([(x, y) for x, y, _ in hits])
    (OUT / f"{name}.json").write_text(
        json.dumps({"region": [x0, y0, x1, y1], "step": step, "threshold": thresh,
                    "hits": hits, "boxes": boxes}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"控件测绘：{name}  区域({x0},{y0})-({x1},{y1}) 步长{step} 阈值{thresh}",
             f"响应点 {len(hits)} 个，聚成矩形 {len(boxes)} 个："]
    for bx in sorted(boxes, key=lambda b: (b[1], b[0])):
        cx, cy = (bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2
        lines.append(f"  矩形({bx[0]},{bx[1]})-({bx[2]},{bx[3]})  中心({cx},{cy})  宽{bx[2]-bx[0]+step} 高{bx[3]-bx[1]+step}")
    (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
