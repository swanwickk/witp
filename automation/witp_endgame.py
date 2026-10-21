#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终局屏自动处理：OCR 记分 + 点 Quit Game 关闭 → 回到可载入状态。

背景（2026-10-15 实测定案）：
  end_turn 结算后若出现「VICTORY LEVEL / FINAL SCORE」模态屏，
  该屏**只认鼠标点按钮**（Return/Space/Tab/Esc 全无响应），
  主线程会在 EXE 0x3cd8xx 处定点自旋、画面冻结、存档停写。
  此前 end_turn 检测到它就 return True 留着不动 ⇒ 表现为「游戏卡死」。
  正确做法 = OCR 读出比分 → 点 Quit Game → 回到主菜单（可载入下一局）。

判据与坐标依据：
  · 按钮文字经 tesseract 定位：「View End Game Status」y≈458、「Quit Game」y≈479（x 736..787）
  · 点中判据 = 画面 md5 变化（模态屏消失）
用法：
  python3 witp_endgame.py            # 检测→记分→关闭
  python3 witp_endgame.py --detect   # 只检测与记分，不点击
"""
import os
import re
import subprocess
import sys
import time

os.environ.setdefault("DISPLAY", ":98")
SHOT = "/tmp/_endgame_shot.png"
CAPTURE = "/root/.hermes/profiles/witp/workspace/endgame_captured.png"

_KWS = ("FINAL SCORE", "VICTORY LEVEL", "DECISIVE JAPANESE",
        "DECISIVE ALLIED", "MARGINAL VICTORY", "DRAW")


def _shot(path=SHOT):
    subprocess.run(["import", "-window", "root", "-crop", "1024x768+0+0",
                    "+repage", path], capture_output=True)
    return path


def _ocr(img):
    """OCR 截图为文本。

    ★2026-10-15 修（终局记分漏读）★
      实测坑：直接拿 1024×768 原图喂 tesseract（psm 11）只得到碎片
      （'dang ve Ne on ...'），`JAPANESE: 342 / ALLIED: 1952` 完全读不出
      ⇒ 记分失败、scores={}。
      修法：**灰度 + autocontrast + 2× 放大** 后再 OCR，实测同一张图
      稳定读出 'JAPANESE: 342  ALLIED: 1952' 与胜负判定文字。
      另同时跑 psm 11 与 psm 6，取并集，进一步降低漏读。
    """
    from PIL import Image, ImageOps
    try:
        im = Image.open(img).convert("RGB")
    except Exception:
        return ""
    g = ImageOps.autocontrast(ImageOps.grayscale(im))
    g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    g.save("/tmp/_eg_up.png")
    outs = []
    for psm in ("11", "6"):
        r = subprocess.run(["tesseract", "/tmp/_eg_up.png", "stdout",
                            "--psm", psm], capture_output=True, text=True)
        outs.append(r.stdout or "")
    return "\n".join(outs)


def detect():
    """返回 (关键词, 分数dict) 或 (None, {})。"""
    _shot()
    txt = _ocr(SHOT)
    up = txt.upper()
    kw = next((k for k in _KWS if k in up), None)
    if not kw:
        return None, {}
    scores = {}
    # ★2026-10-15：终局屏写的是 'JAPANESE: 342'；OCR 偶尔把冒号读成 . 或 ,
    #   或在数字前插空格，故分隔符放宽、允许跨空白。
    for m in re.finditer(r"(JAPANESE|ALLIED)\s*[:.,;]?\s*(\d{2,6})", up):
        scores[m.group(1)] = int(m.group(2))
    return kw, scores


def _find_quit_btn(img):
    """OCR 定位 'Quit Game' 行，返回 (x, y)；失败返回 None。"""
    box = (600, 430, 1024, 560)
    from PIL import Image, ImageOps
    im = Image.open(img).convert("RGB").crop(box)
    im = ImageOps.autocontrast(ImageOps.grayscale(im))
    im = im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
    im.save("/tmp/_eg_btn.png")
    r = subprocess.run(["tesseract", "/tmp/_eg_btn.png", "stdout",
                        "--psm", "6", "tsv"], capture_output=True, text=True)
    words = []
    for ln in r.stdout.splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 12:
            continue
        t = p[11].strip()
        if t:
            words.append((int(p[6]) // 4 + box[0], int(p[7]) // 4 + box[1],
                          int(p[8]) // 4, int(p[9]) // 4, t))
    # 找 "Quit" 后紧跟 "Game" 的行（取该行最右端 Game 的右缘 + 一点）
    for i, (x, y, w, h, t) in enumerate(words):
        if t.lower().startswith("quit"):
            for x2, y2, w2, h2, t2 in words[i:i + 3]:
                if t2.lower().startswith("game") and abs(y2 - y) < 8:
                    return (x2 + w2 // 2 + 6, y + h // 2)
            return (x + w + 10, y + h // 2)
    return None


def _md5(p):
    import hashlib
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def close(capture_only=False):
    """检测→记分→（尝试）点 Quit Game→（失败则）重建显示栈。

    ★2026-10-15 实测定案★
      终局屏在本环境下**不可交互**：VNC 点击、xdotool 原生点击、
      Return/Space/Tab/Esc 全部无效，画面 md5 恒不变，主线程在
      EXE 0x3cd8xx 处**定点自旋**（不是消息泵）⇒ 输入根本无法被处理。
      故「点 Quit Game」只能当 best-effort；**可靠出口 = 重建显示栈**
      （witp_clean_restart.sh，已实测可用），回到干净主菜单。
    返回 (ok, info)。ok=True 表示终局已妥善处理（含比分）。
    """
    kw, scores = detect()
    if not kw:
        return False, {"reason": "无终局屏"}
    try:
        subprocess.run(["cp", SHOT, CAPTURE], check=False)
    except Exception:
        pass
    info = {"keyword": kw, "scores": scores, "capture": CAPTURE}
    # 落盘比分，供 close-game / 归档直接读取
    try:
        import json
        with open("/root/.hermes/profiles/witp/workspace/endgame_scores.json", "w") as f:
            json.dump({"keyword": kw, **scores, "ts": time.time()}, f,
                      ensure_ascii=False, indent=1)
        info["scores_file"] = "/root/.hermes/profiles/witp/workspace/endgame_scores.json"
    except Exception as e:
        info["scores_file_error"] = str(e)
    if capture_only:
        return True, info

    # ① best-effort：点 Quit Game（部分环境下可行）
    btn = _find_quit_btn(SHOT)
    info["quit_btn"] = btn
    if btn:
        h0 = _md5(SHOT)
        for _ in range(2):
            subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                            str(btn[0]), str(btn[1]), "click"], capture_output=True)
            time.sleep(2.5)
            _shot("/tmp/_eg_after.png")
            if _md5("/tmp/_eg_after.png") != h0:
                info["closed"] = "click"
                return True, info

    # ② 可靠出口：重建显示栈 → 干净主菜单
    info["closed"] = "rebuild"
    try:
        r = subprocess.run(["bash", "/root/.hermes/profiles/witp/workspace/witp_clean_restart.sh"],
                           capture_output=True, text=True, timeout=300)
        info["rebuild_tail"] = (r.stdout or "").strip().splitlines()[-3:]
    except Exception as e:
        info["rebuild_error"] = str(e)
        return False, info
    return True, info


if __name__ == "__main__":
    only = "--detect" in sys.argv
    ok, info = close(capture_only=only)
    print("ok =", ok)
    for k, v in info.items():
        print(f"  {k} = {v}")
