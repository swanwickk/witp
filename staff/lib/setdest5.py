#!/usr/bin/env python3
"""`set-dest` v5（2026-10-03）：**视野标定走顶栏探针，面板只负责"设定"**。

═══ 分工（本轮实测结论）═══
· **顶栏 Hex 是可信的视野探针**（模板/白名单读取器已与 vision 真值核验）。
  地图模式下点一处地图 → 顶栏即显示该格。实测四点自洽：
    (300,100)→(106,144)  (300,650)→(106,158)
    (700,100)→(116,144)  (700,650)→(116,158)
  ⇒ **W=40.00、H=39.29 px/格**，且 x 不随 y 变化（纯线性，无行偏移项）。
· **面板内 Hex 行不可作为基准**：滚动后出现互斥读数（实测 (106,118) 与
  (105,159) 同屏自相矛盾）。
· 面板/子面板/列表三态由 tfpanel 判定；落子后用 **T 列表 Location 列**核验。

═══ 流程 ═══
  ① 地图模式 4 点顶栏探针 → W、H、锚点
  ② 算目标像素；若被面板遮挡/出界 → 滚视野（北/南，按需时长）后重探
  ③ 开面板 → 点 `Set TF Destination` → 点目标像素
  ④ 读 T 列表 Location 列核验；不符则按落点差修正锚点重试
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset, read_bar_once   # noqa: E402
from lib import tfpanel as TP                             # noqa: E402
from PIL import Image                                     # noqa: E402

import os as _os
_os.environ.setdefault("DISPLAY", ":98")

WIN_W, WIN_H = 1024, 768
PANEL = (150, 185, 870, 560)
# ★视野探针点（实测扫描得出）★
#   地图可用区：上带 y≈40..180（面板上方）、左条 x<150、右条 x>870。
#   ★y≥650 的点击会被**左下信息面板/底部栏吞掉**（实测 (300,700)、(700,700)
#     读回的是上一个点击的值）⇒ 探针绝不能放在 y>640。
#   实测自洽： (300,60)→(106,146) (700,60)→(116,146)
#              (100,400)→(101,155) (950,600)→(122,160) ⇒ W≈40.5、H≈39
PROBES = [(300, 60), (700, 60), (100, 400), (950, 600)]
# 目标落点带（可点击）：上带 / 下带中心（下带必须 ≤640）
BAND_TOP, BAND_BOT = 90, 610


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _move(px, py):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                    str(int(px)), str(int(py))], capture_output=True)


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def _onscreen(x, y):
    # ★实测★ y>640 落在左下信息面板/底部栏上，点击无效
    return 10 <= x <= WIN_W - 10 and 36 <= y <= 640


def probe_topbar(px, py, log=None, tries=2):
    """地图模式下点一处地图 → 顶栏 Hex。多读取众数。"""
    from collections import Counter
    seen = []
    for _ in range(tries):
        _vnc(int(px), int(py))
        time.sleep(1.2)
        h = read_bar_once()
        if h:
            seen.append(h)
    if not seen:
        return None
    return Counter(seen).most_common(1)[0][0]


def median_scale(anchors, vk, hk):
    vals = []
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            (pa, ha), (pb, hb) = anchors[i], anchors[j]
            dh = hb[hk] - ha[hk]
            if abs(dh) < 2:
                continue
            vals.append((pb[vk] - pa[vk]) / dh)
    if not vals:
        return None
    vals.sort()
    med = vals[len(vals) // 2]
    keep = [v for v in vals if med == 0 or abs(v - med) <= 0.25 * abs(med)]
    return sum(keep) / len(keep) if keep else med


def _fit_slope(pxs, hs, k):
    """最小二乘拟合 px = a + W*(hex - mean)。k=0 用 x 轴，k=1 用 y 轴。"""
    n = len(pxs)
    if n < 2:
        return None
    mx = sum(p[k] for p in pxs) / n
    mh = sum(h[k] for h in hs) / n
    num = sum((hs[i][k] - mh) * (pxs[i][k] - mx) for i in range(n))
    den = sum((hs[i][k] - mh) ** 2 for i in range(n))
    if den < 1e-9:
        return None
    return num / den


def _resid(pxs, hs, k, W):
    n = len(pxs)
    mx = sum(p[k] for p in pxs) / n
    mh = sum(h[k] for h in hs) / n
    return max(abs(pxs[i][k] - (mx + W * (hs[i][k] - mh))) for i in range(n))


def measure_view(log=print, probe_log=None):
    """地图模式下顶栏探针 → dict(W,H,anchors) 或 None。

    ★四点联合求解★ 实测顶栏 OCR 在该小字体上会**个位数混淆**
      （真值 115,131 的同帧里也有 6 票读成 115,134），单纯多数投票会平票/投错。
      故每个探针点保留**候选集**，穷举组合，取「四点能拟合成同一条线性映射」
      （最大像素残差最小）的那个组合 —— 错误读数会破坏拟合，天然被淘汰。
    """
    from itertools import product
    from lib.hexbar import read_bar_votes
    if TP.ui_state() != "map":
        TP.reset_to_map(log=None)
    pxs, cands = [], []
    prev = None
    for p in PROBES:
        v = {}
        for _try in range(3):
            _vnc(*p)
            time.sleep(1.2)
            v = read_bar_votes()
            if not v:
                continue
            top = sorted(v.items(), key=lambda kv: -kv[1])[0][0]
            # ★点击生效校验★ 若读数与上一探针完全相同（且像素不同），
            #   说明这次点击没落到地图上（实测：面板/信息栏遮挡、或游戏崩溃时
            #   顶栏会一直停在旧值）→ 重新点，宁判失败不采信陈旧值。
            if prev is None or top != prev:
                break
            if probe_log:
                probe_log(f"  顶栏探针 {p} 读数与上一点相同（{top}）→ 重点")
        if probe_log:
            probe_log(f"  顶栏探针 {p} 候选 {v}")
        if not v:
            continue
        top2 = sorted(v.items(), key=lambda kv: -kv[1])[:2]
        pxs.append(p)
        cands.append([t[0] for t in top2])
        prev = top2[0][0]
    if len(pxs) < 3:
        log(f"  ✗ 顶栏锚点不足（{len(pxs)}）")
        return None
    best = None
    for combo in product(*cands):
        W = _fit_slope(pxs, list(combo), 0)
        H = _fit_slope(pxs, list(combo), 1)
        if W is None or H is None:
            continue
        # 放宽闸门（实测该栏/地图下 W≈38~46、H≈37~41；放宽到 15~90 以免
        #  个别帧因残差略大而被整体判死）
        if not (15 <= abs(W) <= 90) or not (15 <= abs(H) <= 90):
            continue
        r = max(_resid(pxs, list(combo), 0, W), _resid(pxs, list(combo), 1, H))
        if best is None or r < best[0]:
            best = (r, W, H, list(combo))
    if best is None:
        log("  ✗ 无任何候选组合能拟合（顶栏读数全不可信）")
        return None
    r, W, H, hs = best
    log(f"  ✓ 视野标定 W={W:.2f} H={H:.2f} px/格 残差={r:.1f}px（锚点 {len(pxs)}）")
    for p, h in zip(pxs, hs):
        log(f"      {p} ↔ {h}")
    if r > 15:
        log(f"  ⚠ 拟合残差偏大（{r:.1f}px），标定可能不可信")
    return {"W": W, "H": H, "anchors": list(zip(pxs, hs))}


def pixel_of(vw, tx, ty):
    base = min(vw["anchors"],
               key=lambda a: abs(a[1][0] - tx) + abs(a[1][1] - ty))
    return (base[0][0] + (tx - base[1][0]) * vw["W"],
            base[0][1] + (ty - base[1][1]) * vw["H"])


def make_clickable(vw, tx, ty, log=print, rounds=6):
    """滚视野直到目标像素落在可点带内。返回新的 vw 或 None。"""
    for _ in range(rounds):
        px, py = pixel_of(vw, tx, ty)
        if _onscreen(px, py) and not _blocked(px, py):
            log(f"  目标像素 ({px:.0f},{py:.0f}) 可点")
            return vw
        # ★方向与落点带（实测标定）★
        #   悬停**上边缘** → 视野北移 → 固定像素处的 hex y 变小
        #     ⇒ 目标的屏幕 y **增大**（内容下移）
        #   悬停**下边缘** → 视野南移 → 目标屏幕 y **减小**（内容上移）
        #   故：目标太高(py<上带) → 北滚，让它落到**下带**；
        #       目标太低/被面板挡 → 南滚，让它落到**上带**。
        #   （先前把两者配反，导致南北来回振荡、永不收敛。）
        if py < BAND_TOP:
            north, desire = True, BAND_BOT
        else:
            north, desire = False, BAND_TOP
        need = abs(desire - py)
        secs = min(3.0, max(1.2, need / vw["H"] / 10.5))
        log(f"  目标像素({px:.0f},{py:.0f})不可点 → {'北' if north else '南'}滚 "
            f"{secs:.1f}s（移到 y≈{desire}，差 {need:.0f}px）")
        TP.reset_to_map(log=None)
        _vnc(950, 650)                 # 空白海面取地图焦点
        time.sleep(0.6)
        _move(WIN_W // 2, 0 if north else WIN_H - 1)
        time.sleep(secs)
        _move(WIN_W // 2, WIN_H // 2)
        time.sleep(0.8)
        vw2 = measure_view(log=log)
        if vw2 is None:
            log("  ✗ 滚动后标定失败")
            return None
        vw = vw2
    return vw


OCR_FIX = str.maketrans({
    "i": "1", "l": "1", "I": "1", "|": "1", "!": "1",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2",
    "G": "6", "T": "7", "q": "9", "g": "9",
})


def parse_list_location(t):
    """从 T 列表 Location 列文本解析目的地。

    ★实测坑★ OCR 会把 `104` 的 `1` 认成 `i`（得到 `movetoi04 145`），
      若简单取"最后两组数字"就会误得 (4,145)。
      ⇒ ① 先做**形近字符归一**；② 用**动词锚定**正则
         （`mve to` / `moveto` / `move to` 后面紧跟的两个数才是目的地；
          `near to x,y` 是"当前位置"不是目的地，必须排除）。
    """
    t2 = t.translate(OCR_FIX)
    # 归一后动词形如：moveto→mvet0、mve to→mve t0、mv to→mv t0
    m = re.search(r"(?:mve\s*t0|mvet0|m0vet0|mv\s*t0|mve\s*t)"
                  r"\D{0,3}(\d{2,3})\D{1,3}(\d{2,3})", t2)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        if 10 <= x <= 250 and 10 <= y <= 250:
            return (x, y)
    return None


def read_dest_from_list(tf_id, log=None, tries=3):
    """读 T 列表里该编队的 Location 列（`moveto x,y`）。

    ★实测★ 落子后**面板会自动关闭**，此时 T 列表也未必开着 ⇒
      必须先确保列表打开（按 T），否则 find_tf_row 直接失败。
    """
    from lib.setdest import find_tf_row
    for _ in range(tries):
        r = find_tf_row(tf_id, log=None)
        if r is None:
            TP.reset_to_map(log=None)
            # ★键盘需焦点★ 先点地图空白处再按 T（否则 T 静默失效）
            _vnc(950, 60)
            time.sleep(0.8)
            _key("t")
            time.sleep(3.2)
            r = find_tf_row(tf_id, log=None)
        if r is None:
            continue
        im = TP._shot()
        c = im.crop((690, r - 9, 1024, r + 9))
        c = c.resize((c.width * 6, c.height * 6), Image.LANCZOS)
        c.save("/tmp/_v5_loc.png")
        rr = subprocess.run(["tesseract", "/tmp/_v5_loc.png", "stdout", "--psm", "7"],
                            capture_output=True)
        t = rr.stdout.decode(errors="replace")
        got = parse_list_location(t)
        if log:
            log(f"    列表原文 {t.strip()!r} → 解析 {got}")
        if got:
            return got
        time.sleep(0.8)
    return None


def read_dest_via_panel(tf_id, log=None):
    """兜底通道：重开主面板，读其 Hex 行（大字）。

    ★实测★ T 列表 Location 列在**带基地名前缀**时不显示坐标数字
      （实测该列只显示 `Torokina,moveto`，数字被列宽挤掉）。
      ⇒ 列表解析失败时必须回退到面板大字读数。
    """
    from collections import Counter
    by, bx = TP.open_tf_panel(tf_id, log=(log or (lambda *a: None)))
    if by is None:
        return None
    seen = []
    for _ in range(3):
        v = TP.read_panel_hex(tries=2, log=None)
        if v:
            seen.append(v)
    if not seen:
        return None
    return Counter(seen).most_common(1)[0][0]


def read_dest_any(tf_id, log=None):
    """双通道回读：先列表（快），失败则开面板读大字。

    ★实测★ 面板 Hex 行在**滚动后**才会出现自相矛盾读数；
      而「一次落子后的核验」只需要读一次当前值，用面板是可靠的。
    """
    got = read_dest_from_list(tf_id, log=log)
    if got:
        return got
    if log:
        log("    列表未给出坐标 → 回退面板大字回读")
    got = read_dest_via_panel(tf_id, log=log)
    if log:
        log(f"    面板回读 = {got}")
    return got


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（v5：顶栏探针）===")
    vw = measure_view(log=log)
    if vw is None:
        log("  ✗ 视野标定失败")
        return False, None
    vw = make_clickable(vw, tx, ty, log=log)
    if vw is None:
        log("  ✗ 无法把目标拉进可点带")
        return False, None
    px, py = pixel_of(vw, tx, ty)
    px, py = int(px), int(py)

    for attempt in range(4):
        # ★点击前确保目标像素可点★（实测：标定残差略大时算出的像素可能落在
        #   顶栏(y<36)或面板遮挡区，直接点会点到界面上 → 落子失败/误触）
        if not (_onscreen(px, py) and not _blocked(px, py)):
            vw = make_clickable(vw, tx, ty, log=log)
            if vw is None:
                log("  ✗ 无法把目标拉进可点带")
                return False, None
            px, py = pixel_of(vw, tx, ty)
            px, py = int(px), int(py)
            if not (_onscreen(px, py) and not _blocked(px, py)):
                log(f"  ✗ 目标像素({px},{py})仍不可点")
                return False, None
        by, bx = TP.open_tf_panel(tf_id, log=(log if attempt == 0 else
                                              (lambda *a: None)))
        if by is None:
            log("  ✗ 未能打开编队详情面板")
            return False, None
        _vnc(bx, by)
        time.sleep(2.0)
        _vnc(px, py)
        time.sleep(2.8)
        got = read_dest_any(tf_id, log=log)
        log(f"  [{attempt+1}] 点({px},{py}) → 回读 {got}")
        if got == (tx, ty):
            log(f"  ✓ 列表确认目的地 = {got}")
            return True, got
        if got:
            # ★用实测落点直接替换最近的锚点★
            #   实测：按 (got-target)*W 平移锚点是**符号搞反**的（越修正越远）。
            #   正解：观测到「像素 P → 格 H」，就把该锚点设为 (P,H)，再由它外推。
            idx = min(range(len(vw["anchors"])),
                      key=lambda i: (abs(vw["anchors"][i][1][0] - tx)
                                     + abs(vw["anchors"][i][1][1] - ty)))
            vw["anchors"][idx] = ((px, py), got)
            px, py = pixel_of(vw, tx, ty)
            px, py = int(px), int(py)
            log(f"        锚点更新为 ({vw['anchors'][idx][0]}) ↔ {got}；"
                f"新目标像素 ({px},{py})")
            if not (_onscreen(px, py) and not _blocked(px, py)):
                vw = make_clickable(vw, tx, ty, log=log)
                if vw is None:
                    return False, None
                px, py = pixel_of(vw, tx, ty)
                px, py = int(px), int(py)
    log("  ✗ 未确认")
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 104
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 145
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
