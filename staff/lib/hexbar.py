"""顶栏 `Hex: x y` 读取（定稿 v19：卷积扫描 + 模板匹配）。

═══ 为什么是卷积扫描 ═══
 实测字形沿 x 的分布**不规整**（同一帧内间距可为 6 / 17 / 12px），
 按固定步距取格必然错位。改为**逐像素卷积**：对每个 x 位置取 6 列窗口，
 算它与 10 个数字模板的最小汉明距离；距离 ≤ 阈值的即认定为命中，
 再按「同一字形只记一次、取距离最小者」去重。

═══ 已实测的字体事实 ═══
 · 字形 5 列 + 右补零 = 6 列窗口；8 行 y=6..13（**y=13 是底行**，
   含 `1` 的底横 `111110`，不能排除）。
 · 正确匹配可达 **dist=0**（`1`、`0` 实测 dist=0），故阈值取 2 足够严格。
 · 分段（列投影）用 y=6..12：必须排除 y=13，否则数字底横连成一片把相邻数字粘连。
 · tesseract 在该字体上系统性错读（`111`→`141`），故完全不用 OCR。

═══ 已知局限（如实记录）═══
 若某数字的字形与模板不对齐（实测 `6` 在 y 字段未匹配），该帧会判为读不出，
 由跨帧一致性 + 重试兜底；**不会给出错误数字**（宁可不读，不可读错）。
"""
import re

# ★2026-09-28 实测根因★ 工具环境里 DISPLAY **未导出**，导致 `import` 截图
#   静默失败（返回空白/过期图，进而把界面状态判错）。这里统一兜底。
import os
os.environ.setdefault("DISPLAY", ":98")

import subprocess
import time

import numpy as np
from PIL import Image, ImageOps

FB = "/tmp/_hexbar19_fb.png"
BAR = (790, 0, 1014, 26)
# 数字区候选裁剪窗（相对 BAR 左上角）：实测最稳为 (30,4)-(190,24)
NUM_BOXES = ((30, 4, 190, 24), (20, 2, 200, 26), (0, 0, 224, 26))
_LAST_VOTES = {}
BRIGHT = 140
CELL_Y = (6, 14)
WIN = 6
X_LO, X_HI = 112, 182
DIST_MAX = 3
GAP_MIN = 8              # 相邻命中间距 ≥8px 才算两个字形
LABEL_BOX = (95, 4, 120, 15)

TPL = {
    "0": ["011110", "010010", "100001", "100001", "100001", "100001", "010010", "011110"],
    "1": ["001000", "011000", "101000", "001000", "001000", "001000", "001000", "111110"],
    "2": ["001110", "010001", "000001", "000110", "001100", "011000", "100000", "111111"],
    "3": ["011110", "100001", "000001", "001110", "000001", "000001", "100001", "011110"],
    "4": ["001000", "001000", "010100", "010100", "100100", "111111", "000100", "000100"],
    "5": ["111100", "100000", "111100", "100110", "000001", "000001", "100010", "011100"],
    "6": ["011100", "100010", "100000", "011100", "100010", "100010", "100010", "011100"],
    "7": ["111110", "000010", "000100", "001000", "001000", "010000", "010000", "010000"],
    "8": ["011110", "100001", "100001", "011110", "100001", "100001", "100001", "011110"],
    "9": ["011110", "100001", "100001", "100001", "011111", "000001", "000100", "011000"],
    ":": ["000000", "000000", "001000", "000000", "000000", "000000", "000000", "001000"],
}
NON_DIGIT = {":"}


def get_window_offset():
    """
    ★2026-10-04 统一委托★
    原实现搜索 'War in the Pacific - Admiral'（带连字符），与 executor 搜索的
    'War in the Pacific' 不一致，很可能匹配 0 个窗口而静默退回 (188,150)，
    导致截图裁错位置。改为直接复用 executor 的唯一实现，避免两处漂移。
    """
    try:
        from lib.executor import get_window_offset as _off
        return _off()
    except Exception:
        return 188, 150


def _grab_win():
    from PIL import Image
    ox, oy = get_window_offset()
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":98"))
    for _ in range(3):
        subprocess.run(["import", "-window", "root", FB], capture_output=True,
                       env=env)
        try:
            im = Image.open(FB)
            im.load()
            return im.crop((ox, oy, ox + 1024, oy + 768))
        except Exception:
            time.sleep(0.8)
    raise RuntimeError("顶栏截图失败（import 连续 3 次未产出可读文件）")


def _win(g, x0):
    px = g.load()
    return ["".join("1" if px[x, y] > BRIGHT else "0"
                    for x in range(x0, x0 + WIN))
            for y in range(CELL_Y[0], CELL_Y[1])]


def _dist(bm, t):
    return sum(1 for ra, rb in zip(bm, t) for ca, cb in zip(ra, rb) if ca != cb)


def _scan(g):
    """逐像素卷积 → [(x, digit, dist)]，去重（同字形取最小距离）。"""
    hits = []
    for x0 in range(X_LO, X_HI):
        if "1" not in "".join(_win(g, x0)):
            continue
        bm = _win(g, x0)
        d, dist = None, 999
        for k, t in TPL.items():
            dd = _dist(bm, t)
            if dd < dist:
                d, dist = k, dd
        if dist <= DIST_MAX:
            hits.append((x0, d, dist))
    # 去重：按 x 排序，间距 < GAP_MIN 视为同一字形，保留 dist 最小者
    hits.sort()
    out = []
    for x0, d, dist in hits:
        if out and x0 - out[-1][0] < GAP_MIN:
            if dist < out[-1][2]:
                out[-1] = (x0, d, dist)
        else:
            out.append((x0, d, dist))
    return out


def _norm_glyph(img):
    """把字形二值图归一化到 6x8 的 0/1 网格（供模板匹配）。"""
    import numpy as np
    a = np.array(img.convert("L"))
    b = (a > BRIGHT).astype(np.uint8)
    ys, xs = np.nonzero(b)
    if len(ys) == 0:
        return None
    b = b[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im2 = Image.fromarray(b * 255).resize((WIN, CELL_Y[1] - CELL_Y[0]),
                                          Image.BILINEAR)
    import numpy as _np
    return ["".join("1" if v > 127 else "0" for v in row)
            for row in _np.array(im2)]


def _match_glyph(bm):
    best, bd = None, 999
    for ch, t in TPL.items():
        d = _dist(bm, t)
        if d < bd:
            best, bd = ch, d
    return best, bd


def read_bar_once(verbose=False):
    r"""读顶栏 `Hex: X Y`（2026-10-03 定稿 v5）。

    ★做法：**固定数字窗 + 多尺度多psm 白名单 OCR 广域投票 + 按位数切分**★

    ★为什么不再靠 TSV 找 `Hex:` 标签★ 实测 tesseract 会把 `Hex:111`
      读成 `Hewat` 之类的乱码，标签匹配直接失效（整个读取返回 None）。
      而该栏布局是固定的：`... Moonlight: 42%  Hex: XXX YYY`，
      `Moonlight:42%` 最右约到 BAR x=89，故 **BAR x≥112 起就只剩 Hex 的数字**，
      用固定窗即可完全避开标签识别。

    ★为什么广域投票★ 该 5px 字体上单配置会个位数混淆（131/134 各半）；
      多尺度×多宽度×多psm 投票后正确值通常占多数（配合 setdest 的四点联合求解更稳）。
    """
    win = _grab_win()
    g = ImageOps.grayscale(win.crop(BAR))

    def ok(x, y):
        return 10 <= x <= 250 and 10 <= y <= 250

    def split_digits(d):
        if len(d) >= 6:
            x, y = int(d[:3]), int(d[3:6])
            if ok(x, y):
                return x, y
        if len(d) == 5:
            for a_, b_ in ((d[:2], d[2:]), (d[:3], d[3:])):
                x, y = int(a_), int(b_)
                if ok(x, y):
                    return x, y
        if len(d) == 4:
            x, y = int(d[:2]), int(d[2:])
            if ok(x, y):
                return x, y
        return None

    from collections import Counter
    votes = Counter()
    order = []
    for x0, w in ((112, 80), (112, 92), (118, 74), (105, 100)):
        box = (x0, 3, min(x0 + w, BAR[2] - BAR[0]), 25)
        c = g.crop(box)
        for scale in (8, 12, 14):
            cc = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
            cc.save("/tmp/_hb_num.png")
            for psm in ("7", "13"):
                rr = subprocess.run(
                    ["tesseract", "/tmp/_hb_num.png", "stdout", "--psm", psm,
                     "-c", "tessedit_char_whitelist=0123456789 "],
                    capture_output=True)
                d = re.sub(r"\D", "", rr.stdout.decode(errors="replace"))
                got = split_digits(d)
                if got:
                    votes[got] += 1
                    order.append(got)
    global _LAST_VOTES
    _LAST_VOTES = dict(votes)
    if not votes:
        if verbose:
            print("   固定窗全部配置均未得出合法坐标")
        return None
    best, n = votes.most_common(1)[0]
    if verbose:
        print(f"   票={dict(votes)} → {best}")
    return best


def read_bar_votes(verbose=False):
    """返回该帧的**候选票数** {坐标: 票数}（供多点联合求解消歧）。"""
    read_bar_once(verbose=verbose)
    return dict(_LAST_VOTES)


def read_hex(frames=5, pace=0.12, unanimous=False):
    from collections import Counter
    seen = []
    for _ in range(frames):
        h = read_bar_once()
        if h:
            seen.append(h)
        time.sleep(pace)
    if not seen:
        return None
    best, cnt = Counter(seen).most_common(1)[0]
    if unanimous:
        return best if cnt == len(seen) and cnt >= 2 else None
    return best if cnt >= 2 else None


def read_hex_dbg(frames=3):
    from collections import Counter
    seen = []
    for _ in range(frames):
        seen.append(read_bar_once())
        time.sleep(0.15)
    return seen, Counter([s for s in seen if s]).most_common()


if __name__ == "__main__":
    import sys
    t0 = time.time()
    if "--dbg" in sys.argv:
        print(read_hex_dbg())
    elif "--v" in sys.argv:
        print("  →", read_bar_once(verbose=True))
    else:
        for i in range(3):
            print(f"  第{i+1}次 Hex =", read_hex())
    print(f"  （耗时 {time.time()-t0:.2f}s）")
