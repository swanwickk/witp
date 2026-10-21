"""
运行时控件发现引擎（Runtime Widget Discovery）

为什么要这一层：
  旧 witp-cmd 把界面坐标**写死**在代码里（如「Patrol levels」「Set TF Destination」的
  x/y）。实测同一面板在不同状态下**整块位移 31px**、行序还会变（把 Search 设为非 0 会
  露出搜索弧控件、Search/Train/Rest 整块下移），写死坐标必然失效 —— 这是「偏 1 格 /
  点不中」的根源之一。
  本层提供**按语义找控件**的原语：先用 OCR 找到标签文字，再由标签推导该行/该面板的
  可点区域（含按钮），坐标全部当场算出。

设计约定：
  · 所有坐标均为 **游戏坐标**（1024x768 窗口内，不含窗口偏移）。
  · 只依赖 PIL（可离线对截图基线做单测，不需要游戏在跑）。
  · 纯函数优先：`*_from_img(img, ...)` 形式可用任意图片测试；
    带副作用的包装（截图/点击）另行提供。
"""
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageOps
    _PIL = True
except Exception:                                   # pragma: no cover
    _PIL = False

GAME_W, GAME_H = 1024, 768


# ─────────────────────────── 截图 / OCR ───────────────────────────

def shot() -> "Image.Image":
    """截取游戏区（1024x768）。依赖工作区的 witp-ui.sh（会做窗口偏移裁剪与尺寸断言）。"""
    import subprocess
    subprocess.run(["bash", "-c",
                    "source /root/.hermes/profiles/witp/workspace/witp-ui.sh && witp_shot_game && "
                    "cp /tmp/witp_shot.png /tmp/_widgets_shot.png"],
                   capture_output=True)
    return Image.open("/tmp/_widgets_shot.png").convert("RGB")


def ocr_tokens(img: "Image.Image",
               box: Optional[Tuple[int, int, int, int]] = None,
               psm: int = 6, min_conf: float = 20.0,
               zoom: int = 2, autocontrast: bool = True) -> List[Dict[str, Any]]:
    """OCR 出 [(x, y, w, h, text)]（**游戏坐标**）。

    对暗底白字界面：灰度 + autocontrast + 放大 + TSV，再按 zoom 换回坐标。
    """
    import csv
    import subprocess
    if not _PIL:
        return []
    reg = box or (0, 0, img.width, img.height)
    crop = img.crop(reg)
    g = crop.convert("L")
    if autocontrast:
        g = ImageOps.autocontrast(g)
    if zoom != 1:
        g = g.resize((g.width * zoom, g.height * zoom), Image.LANCZOS)
    g.save("/tmp/_widgets_ocr.png")
    subprocess.run(f"tesseract /tmp/_widgets_ocr.png /tmp/_widgets_ocr --psm {psm} tsv 2>/dev/null",
                   shell=True)
    out: List[Dict[str, Any]] = []
    try:
        with open("/tmp/_widgets_ocr.tsv") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                t = (r.get("text") or "").strip()
                if not t:
                    continue
                try:
                    conf = float(r.get("conf") or -1)
                except Exception:
                    conf = -1
                if conf < min_conf:
                    continue
                out.append({
                    "x": reg[0] + int(int(r["left"]) // zoom),
                    "y": reg[1] + int(int(r["top"]) // zoom),
                    "w": int(int(r["width"]) // zoom),
                    "h": int(int(r["height"]) // zoom),
                    "conf": conf,
                    "text": t,
                })
    except Exception:
        pass
    return out


def norm(s: str) -> str:
    """归一化用于模糊匹配：小写、去非字母数字、消 OCR 常见数字混淆。"""
    t = re.sub(r"[^a-z0-9]", "", (s or "").lower())
    for a, b in (("i", "1"), ("l", "1"), ("o", "0"), ("s", "5")):
        t = t.replace(a, b)
    return t


_CONF = {"1": "1il", "0": "0o", "5": "5s", "4": "4a", "9": "9gs", "2": "2z", "6": "6b",
         "8": "8bs", "7": "7t", "3": "3e", "i": "i1", "l": "l1", "o": "o0", "s": "s598",
         "a": "a4", "z": "z2", "b": "b68", "t": "t7", "e": "e3", "g": "g9", "f": "ft"}


def _confusable(a: str, b: str) -> bool:
    """两个字符是否属于同一「易混集合」（OCR 常见：1↔i↔l、0↔o、5↔s、9↔g、4↔a…）。"""
    return a == b or (b in _CONF.get(a, "")) or (a in _CONF.get(b, ""))


def match_entity(text: str, target: str, max_plain_diff: int = 0) -> bool:
    """实体名匹配（混淆感知的**严格前缀匹配**），容忍列表 OCR 噪声。

    实测噪声样本：
      'No.11 Sqd RAAF' → 'noidsqdraafcatalin'   （11→id，字形混淆）
      '3rd BG/90th BS' → '3rd BG/S0th BS'       （9→S，字形混淆）
      '49th FG/7th FS' → 'AStHFG/7thFS'         （4→A、9→S，字形混淆）
      'VF-5'           → 'VBS SBD-3...'(另一行)  ← **必须不能命中**（那是 VB-5 的行）

    ★核心纪律（2026-09-25 实测调出）★
      只容许**字形混淆**（5↔S、9↔g、4↔A、0↔O、1↔I/L…），**绝不容许数字↔数字替换**。
      先前用「15% 容差」时，3rd BG/55th 会把 3rd BG/90th 也命中、VF-5 会命中 VB-5 的行
      —— 番号里的数字才是区分信息，对它宽容等于丧失鉴别力。
      默认 max_plain_diff=0（全部易混即可）；找不到时调用方可显式放宽并**要求唯一命中**。
    """
    t = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    g = re.sub(r"[^a-z0-9]", "", (target or "").lower())
    if len(t) < len(g) or len(g) < 3:
        return False
    plain = sum(0 if _confusable(t[i], g[i]) else 1 for i in range(len(g)))
    return plain <= max_plain_diff


def find_entity(tokens: Sequence[Dict[str, Any]], target: str,
                relaxed: bool = False) -> List[Dict[str, Any]]:
    """按实体名找行；返回**全部**命中（调用方应检查唯一性）。

    relaxed=False（默认）：严格字形混淆匹配。
    relaxed=True：允许 1 处非易混差异，但**仅当结果唯一时可用**（番号易串，慎用）。
    """
    hits = [t for t in tokens if match_entity(t["text"], target, 0)]
    if not hits and relaxed:
        hits = [t for t in tokens if match_entity(t["text"], target, 1)]
    return hits


def find_token(tokens: Sequence[Dict[str, Any]], pattern: str,
               mode: str = "contains") -> List[Dict[str, Any]]:
    """按文本找 token。mode: exact | contains | startswith | regex | fuzzy | entity。"""
    if mode == "entity":
        return find_entity(tokens, pattern)
    pat = pattern
    if mode == "regex":
        rx = re.compile(pattern, re.I)
        return [t for t in tokens if rx.search(t["text"])]
    k = norm(pat) if mode == "fuzzy" else pat.lower()
    res = []
    for t in tokens:
        tx = norm(t["text"]) if mode == "fuzzy" else t["text"].lower()
        if mode == "exact" and tx == k:
            res.append(t)
        elif mode == "contains" and k in tx:
            res.append(t)
        elif mode == "startswith" and tx.startswith(k):
            res.append(t)
        elif mode == "fuzzy" and k and (tx.startswith(k) or k in tx):
            res.append(t)
    return res


def find_label(img: "Image.Image", pattern: str, box=None, **kw) -> Optional[Dict[str, Any]]:
    """找标签行（返回 y 最大者＝面板下半部，避免命中同名菜单项）。"""
    toks = ocr_tokens(img, box, **kw)
    hits = find_token(toks, pattern, mode=kw.pop("mode", "fuzzy"))
    if not hits:
        hits = find_token(toks, pattern, mode="contains")
    if not hits:
        return None
    hits.sort(key=lambda t: t["y"])
    return hits[-1]


# ─────────────────────── 像素级：文字簇 / 按钮簇 ───────────────────────

def col_clusters(img: "Image.Image", y0: int, y1: int,
                 x0: int = 0, x1: Optional[int] = None,
                 bright: int = 140, gap: int = 2,
                 min_px: int = 1) -> List[Tuple[int, int]]:
    """行带内按列统计亮像素，返回 [(x_start, x_end)] 连续簇。

    用途：定位一行里的若干控件（按钮是小圆钮＝窄簇；标签/数值是宽簇）。
    """
    if not _PIL:
        return []
    x1 = x1 if x1 is not None else img.width
    y1 = min(y1, img.height)
    g = img.convert("L")
    px = g.load()
    runs: List[List[int]] = []
    cur: Optional[List[int]] = None
    for x in range(max(0, x0), x1):
        n = sum(1 for y in range(max(0, y0), y1) if px[x, y] > bright)
        if n >= min_px:
            if cur and x - cur[1] <= gap:
                cur[1] = x
            else:
                if cur:
                    runs.append(cur)
                cur = [x, x]
    if cur:
        runs.append(cur)
    return [(a, b) for a, b in runs]


def row_buttons(img: "Image.Image", row_y: int,
                x0: int = 0, x1: Optional[int] = None,
                half: int = 7) -> Optional[Dict[str, int]]:
    """定位一行的 4 个控件（→0 / −10 / +10 / →最大）。

    ★教训（2026-09-25 实测）★
      不能用「最右两簇」—— 该行附近出现额外文字（如搜索弧 Start/End OGC）时会多出
      右侧文字簇，把非按钮当按钮（实测把 VP-11 的 +100 点错）。
      左侧两簇位置稳定，故**以左对为基准 + 实测偏移**推右对：
        +10 = 左对首项 + 90 ； →最大 = 左对首项 + 111
      （全部坐标由调用方给出的 x0/x1 约束，不做全局假设。）
    """
    cl = col_clusters(img, row_y - half, row_y + half, x0, x1)
    if len(cl) < 2:
        return None
    mid = lambda c: (c[0] + c[1]) // 2
    zx = mid(cl[0])
    return {"zero": zx, "minus": mid(cl[1]), "plus": zx + 90, "full": zx + 111,
            "clusters": cl}


def bright_row_bands(img: "Image.Image", box: Tuple[int, int, int, int],
                     bright: int = 140, min_px: int = 8,
                     gap: int = 2) -> List[Tuple[int, int]]:
    """区域内亮像素行带（用于把一块面板切分成若干「行」）。"""
    if not _PIL:
        return []
    x0, y0, x1, y1 = box
    g = img.convert("L")
    px = g.load()
    bands: List[List[int]] = []
    cur: Optional[List[int]] = None
    for y in range(max(0, y0), min(y1, g.height)):
        n = sum(1 for x in range(max(0, x0), min(x1, g.width)) if px[x, y] > bright)
        if n >= min_px:
            if cur and y - cur[1] <= gap:
                cur[1] = y
            else:
                if cur:
                    bands.append(cur)
                cur = [y, y]
    if cur:
        bands.append(cur)
    return [(a, b) for a, b in bands]


def green_rows(img: "Image.Image", box: Tuple[int, int, int, int],
               thresh: float = 0.15) -> List[int]:
    """区域内「绿色高亮」行中心（列表框的选中态通常是绿色）。"""
    if not _PIL:
        return []
    x0, y0, x1, y1 = box
    px = img.convert("RGB").load()
    out = []
    for y in range(max(0, y0), min(y1, img.height)):
        n = g = 0
        for x in range(max(0, x0), min(x1, img.width)):
            r, gg, b = px[x, y]
            n += 1
            if gg > 80 and r < 110 and b < 110:
                g += 1
        if n and g / n >= thresh:
            out.append(y)
    return out


def diff_bbox(a: "Image.Image", b: "Image.Image", box=None,
              thr: int = 60) -> Optional[Tuple[int, int, int, int]]:
    """两图差异的包围盒（游戏坐标）。用于判定「点了之后到底哪里变了」。"""
    if not _PIL:
        return None
    box = box or (0, 0, min(a.width, b.width), min(a.height, b.height))
    x0, y0, x1, y1 = box
    pa, pb = a.convert("RGB").load(), b.convert("RGB").load()
    xs, ys = [], []
    for y in range(y0, y1):
        for x in range(x0, x1):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            if abs(ra - rb) + abs(ga - gb) + abs(ba - bb) > thr:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
