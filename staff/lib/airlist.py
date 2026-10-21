#!/usr/bin/env python3
"""
★2026-10-04 A 列表（陆基航空队）权威读数器★

实测发现（旧配方全错）：
  ① A 列表是**纯数据表**，行内**没有任何加减按钮**——旧代码找的
     zero/minus/plus/full 按钮（652/671/742/763）在 A 列表里根本不存在，
     所以永远读回 None。
  ② 权威判据是行内 `Search` 标签右侧的数值列。
     OCR 实测（TSV）：`Search` 标签位于 x≈658，数值紧随其右。
  ③ 控件只在**选中某中队后的详情面板**里才出现；
     旧配方所谓"运行时动态定位面板行"指的是详情面板，不是列表行。

因此正确流程是：
  列��读数（权威，反映真实状态） → 如不符则开详情面板改 → 再回列表复核
"""
import csv
import os
import re
import subprocess

SHOT = "/tmp/_aread.png"


def _shot():
    sys_off = subprocess.run(
        "DISPLAY=:98 xdotool search --name 'War in the Pacific'",
        shell=True, capture_output=True).stdout.decode().strip().split("\n")
    ox, oy = 188, 150
    for wid in sys_off:
        if not wid.strip():
            continue
        info = subprocess.run(f"DISPLAY=:98 xwininfo -id {wid}",
                              shell=True, capture_output=True).stdout.decode()
        if "Map State: IsViewable" not in info:
            continue
        for ln in info.split("\n"):
            if "Absolute upper-left X:" in ln:
                ox = int(ln.split(":")[-1])
            elif "Absolute upper-left Y:" in ln:
                oy = int(ln.split(":")[-1])
        break
    env = dict(os.environ, DISPLAY=":98")
    subprocess.run(["import", "-window", "root", SHOT], env=env, timeout=15)
    from PIL import Image
    im = Image.open(SHOT)
    return im.crop((ox, oy, ox + 1024, oy + 768))


def list_pct():
    """返回 {部队名: 搜索百分比}；读不到的行不出现在字典里。"""
    im = _shot()
    im.save("/tmp/_aread_w.png")
    subprocess.run(["tesseract", "/tmp/_aread_w.png", "/tmp/_aread_t",
                    "--psm", "6", "tsv"], capture_output=True, timeout=60)
    try:
        rows = list(csv.DictReader(open("/tmp/_aread_t.tsv"), delimiter="\t",
                                   quoting=csv.QUOTE_NONE))
    except FileNotFoundError:
        return {}

    # 先按行分组（block/par/line 号）
    lines = {}
    for r in rows:
        key = (r.get("block_num"), r.get("par_num"), r.get("line_num"))
        lines.setdefault(key, []).append(r)

    out = {}
    for key, toks in lines.items():
        toks = [t for t in toks if (t.get("text") or "").strip()]
        if not toks:
            continue
        # 找 Search 标签
        sx = None
        for t in toks:
            if re.fullmatch(r"(?i)searc?h", t["text"].strip()):
                sx = int(t["left"])
                break
        if sx is None:
            continue
        # 其右侧最近的 0-100 整数
        cands = []
        for t in toks:
            tx = int(t["left"])
            if tx > sx:
                v = t["text"].strip().rstrip(".")
                if re.fullmatch(r"\d{1,3}", v):
                    v = int(v)
                    if 0 <= v <= 100:
                        cands.append((tx, v))
        if not cands:
            continue
        cands.sort()
        val = cands[0][1]
        # 部队名 = 该行最左侧的非数字词元
        name = None
        for t in sorted(toks, key=lambda z: int(z["left"])):
            s = t["text"].strip()
            if re.search(r"[A-Za-z]", s):
                name = s
                break
        out[name] = val
    return out
