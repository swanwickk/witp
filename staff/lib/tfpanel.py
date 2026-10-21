#!/usr/bin/env python3
"""编队详情面板读写（2026-09-28 定稿 v2）。

═══ 界面三态（必须分清，否则 T/Esc 会把界面切错）═══
  A. 纯地图        —— 既无 `Destination` 行、列表区也无合法 TF 编号列
  B. T 列表        —— 列表区存在 ≥4 行合法 TF 编号（列 x≈148..178）
  C. 主面板        —— TSV 能读到 `Destination` 词（= Task Force Information Screen）
  D. 子面板        —— 标题区含 `Information`（`Set TF Information for TF nn`），
                      或含 `Routing Control`；**没有** Destination 行

  换态规则：
    纯地图  --T-->  列表   --(行上单击)-->  主面板
    主面板  --Esc--> 地图（或列表）
    子面板  --Esc--> 主面板

★实测要点★
  · **T 是切换键**：列表已开时再按 T 会关掉它。
  · **点列表行一次**即开主面板；**点第二次会落到面板上**（进子面板）。
    故"双击"要慎用 —— 这里统一用**单击**，然后用 `Destination` 行核验。
  · 面板内 `Set TF Destination` 的**点击位 = 文字左边界再往左约 45px**
    （手册 6.1.2.1.1：「click the arrow to the left of this title」；
     vision 实测文字在 x≈583..632，按钮可点区覆盖之）。
  · **选点模式是一次性的**，每轮点击前都要重新点按钮。
  · **悬停不改 Hex，只有点击才改** ⇒ 探针必须是点击。
"""
import os

# ★2026-09-28 实测根因★ 工具环境里 DISPLAY **未导出**，导致 `import` 截图
#   静默失败（返回空白/过期图，进而把界面状态判错）。这里统一兜底。
import os as _os
_os.environ.setdefault("DISPLAY", ":98")

import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset          # noqa: E402
from PIL import Image, ImageOps                   # noqa: E402

PANEL_BOX = (140, 170, 1010, 570)
TITLE_BOX = (140, 172, 1010, 196)


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _shot():
    """截取游戏窗口。带重试 + 失效兜底（实测 `import` 偶尔静默失败）。"""
    ox, oy = get_window_offset()
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":98"))
    for attempt in range(3):
        subprocess.run(["import", "-window", "root", "/tmp/_tfp_fb.png"],
                       capture_output=True, env=env)
        try:
            im = Image.open("/tmp/_tfp_fb.png")
            im.load()
            return im.crop((ox, oy, ox + 1024, oy + 768))
        except Exception:
            time.sleep(0.8)
    raise RuntimeError("截图失败（import 连续 3 次未产出文件）")


def _tsv_words(im, box, scale, psm="11"):
    c = im.crop(box)
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    c.save("/tmp/_tfp_tsv.png")
    r = subprocess.run(["tesseract", "/tmp/_tfp_tsv.png", "stdout",
                        "--psm", psm, "tsv"], capture_output=True)
    out = []
    for ln in r.stdout.decode(errors="replace").splitlines()[1:]:
        f = ln.split("\t")
        if len(f) < 12 or not (f[11] or "").strip():
            continue
        try:
            x, y, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
        except ValueError:
            continue
        out.append((f[11].strip(),
                    box[0] + x / scale, box[1] + y / scale,
                    box[0] + (x + w) / scale, box[1] + (y + h) / scale))
    return out


# ── 三态判定 ──────────────────────────────────────────────────────────────

def find_dest_label(im=None):
    """TSV 找 `Destination` 词 → (x0, x1, y_中心)；找不到返回 None。

    这是**主面板存在**的唯一可靠判据（列表与子面板都没有这个词）。
    """
    im = im or _shot()
    for scale in (2, 3):
        for psm in ("11", "6", "4"):
            for (t, x0, y0, x1, y1) in _tsv_words(im, PANEL_BOX, scale, psm):
                tl = t.lower()
                if "destin" in tl:
                    return (x0, x1, int((y0 + y1) / 2))
    return None


def list_visible(im=None):
    """T 列表是否打开。

    ★★v19-103 改用「底色判据」（2026-10-09，实测定案）★★
    历史教训：这个函数**反复在两种错误间摆动** ——
      · 判据太松（≥4 行文字）→ 在地图上**假阳性**（地名凑出 4 行等距列）
        ⇒ `navkeys.clear()` 返回 'list' ⇒ 方向键被判"遮挡" ⇒ 视野导航整体失效
        ⇒ 表现为 set-dest 纵轴永远"清场失败"。
      · 判据太严/依赖 OCR → 列表开着却**假阴性**（报 'map'）。

    根因：用「文字行结构」判别**本身就不可靠** ——
      列表窗口里是**等宽深灰底**，而地图是彩色斑块。
      底色差异比文字布局稳定得多，且不依赖 OCR。

    实测（同一实例，多次采样）：
      ```
      区域              地图态      列表态        可用性
      列表窗口中心      12.1%      33.7% / 17.4%  ✗ 不稳定（两次差 16 个点）
      列表窗口左侧      12.1%      65.1% / 66.6%  ✓ 稳定、5 倍差
      顶部 tab 带        5.7%      71.9% / 72.2%  ✓ 稳定、12 倍差
      ```
    ⚠️ **中心区不可用**：列表中部是表格行，字体/行距变化会让灰度占比在
       17%~34% 间大幅摆动（实测两次采样差 16 个百分点）⇒ 会漏判。
    ⇒ 用**列表窗口左侧** (160,240)-(320,560) —— 该处是编号列+Mission 列的
      等宽底色，占比稳定（地图 12.1% / 列表 65%）。
      阈值取 **35%**：65% ≫ 35% > 12%，两侧各留约 23 个百分点余量。
    """
    im = im or _shot()
    g = ImageOps.grayscale(im)
    px = g.load()
    x0, y0, x1, y1 = 160, 240, 320, 560
    n = dark = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            n += 1
            if px[x, y] < 70:
                dark += 1
    ratio = dark / max(1, n)
    return ratio >= 0.35


def subpanel_visible(im=None):
    """子面板（Set TF Information / Routing Control）是否打开。"""
    im = im or _shot()
    for scale in (2, 3):
        for psm in ("7", "6", "11"):
            for (t, _x0, _y0, _x1, _y1) in _tsv_words(im, TITLE_BOX, scale, psm):
                tl = t.lower()
                if "information" in tl or "routing" in tl:
                    return True
    return False


def other_list_visible(im=None, log=None):
    """是否是**别的**列表（航空队列表等），不是 T 编队列表。

    ★实测教训★ N 键的「Allied Air Units on TF 14 (TF11) Total aircraft: 75」
      列表同样有一列数字，`list_visible` 会把它误判成 T 编队列表，
      于是"单击某行"落到航空队行上 —— 打开完全无关的界面，
      后续 Escape/T 序列越走越乱。故必须先认出它。
    """
    im = im or _shot()
    for scale in (2, 3):
        for psm in ("7", "6", "11"):
            for (t, _x0, _y0, _x1, _y1) in _tsv_words(im, TITLE_BOX, scale, psm):
                tl = t.lower()
                if "air unit" in tl or "aircraft" in tl or "total" in tl:
                    if log:
                        log(f"    检测到非编队列表: {t!r}")
                    return True
    return False


def reset_to_map(log=None, tries=8):
    """按**当前状态**选动作，直到回到纯地图态。

    ★实测订正（2026-10-03）★
      · **T = 打开编队列表（不是切换键！）** 实测：地图态按 T → list；
        列表态再按 T → 仍是 list（不会关闭）。此前把 T 当切换键是错的，
        正是"按 T 反而把列表关掉/状态越走越乱"的根源。
      · **Escape 才是关列表**：实测 list 态按 Esc → map（连续 3 次都成立）。
      · 主面板/子面板 → Esc 逐级退回（子面板→主面板→地图）。
    """
    for _ in range(tries):
        st = ui_state()
        if st == "map":
            return True
        if log:
            log(f"    复位：当前 {st} → Esc")
        _key("escape")
        time.sleep(1.6)
    return ui_state() == "map"


def ui_state(im=None):
    """返回 'main' | 'sub' | 'list' | 'other' | 'map'。"""
    im = im or _shot()
    if find_dest_label(im) is not None:
        return "main"
    if subpanel_visible(im):
        return "sub"
    if other_list_visible(im):
        return "other"
    if list_visible(im):
        return "list"
    return "map"


def _find_tf_row(tf_id, log=None):
    from lib.setdest import find_tf_row
    return find_tf_row(tf_id, log=log)


# ── 打开主面板 ────────────────────────────────────────────────────────────

def panel_tf_number(im=None):
    """
    读主面板标题里的编队编号（形如 `US Navy TF 21 (1 ship) is at sea`）。

    ★★v19-94 新增：实体校验闸★★
    实测（2026-10-06）：`open_tf_panel('TF15')` **打开了 TF21（潜艇 S-40）的面板**
      —— 面板写着 "US Navy TF 21"、`Hex: 97,129`，
      而读层里 TF21 的 target_x/y 正是 97,129，完全吻合。
    根因：T 列表行定位的行距常量错（写 15，实测 14），累积偏差导致
      双击落到**相邻行** ⇒ 打开别的编队。
    ⇒ 后果极严重：**所有后续命令都会作用在错误编队上**，
      而且面板读回的坐标是"那个错编队"的目的地，
      会产生**内部完全自洽的假成功**（改了别的实体 vs 没改，是两回事）。

    本函数用于在拿到面板后**校验编号**，不符即中止。

    ★裁切区与参数是实测定出来的（2026-10-09，健康实例）★
      标题实际落在 y∈[185,215]，而非先前的 [172,196]（那个带只读到装饰噪声）。
      实测多种 (scale, psm) 组合都能稳定读出 `US Navy TF NN (N ships) is at sea
      near ...`；取 sc=2/psm=7 与 sc=4/psm=7 双重投票最稳。
    失败返回 None（**注意**：调用方必须把 None 当作"无法校验"而不是"通过"）。
    """
    im = im or _shot()
    box = (140, 185, 700, 215)
    votes = {}
    for sc, psm in ((2, "7"), (4, "7"), (3, "6")):
        c = im.crop(box)
        c = c.resize((c.width * sc, c.height * sc), Image.LANCZOS)
        c.save("/tmp/_tpn.png")
        r = subprocess.run(["tesseract", "/tmp/_tpn.png", "stdout",
                            "--psm", psm], capture_output=True)
        txt = r.stdout.decode(errors="replace").replace("Newy", "Navy")
        m = re.search(r"\bTF\s*([0-9]{1,3})\b", txt)
        if m:
            votes[m.group(1)] = votes.get(m.group(1), 0) + 1
    if not votes:
        return None
    return int(max(votes.items(), key=lambda kv: kv[1])[0])


# ── 列表行扫描开面板 ──────────────────────────────────────────────────────

# ★列表行几何（2026-10-09 实测权威）★
#   行 y = 250, 264, 278, ... 行距 14；与读层 TF 编号序列一一对应：
#     y=250→TF14  264→15  278→16  292→17  306→20  320→21
#     334→22  348→23  362→24  376→25
#   编号列在窗口内 x∈[165,215]；x=200 实测稳定命中。
ROW_Y0, ROW_DY, ROW_N = 250, 14, 16
LIST_CLICK_X = 200

# ★行映射缓存★（tf_num -> y）
#   扫描一次能发现多行；把它缓存起来，同一回合内后续编队直接命中，
#   把 46~118s 的全扫描降到约 5s。
#   持久化到 /tmp，故跨进程（不同脚本调用）也生效。
#   失效策略：缓存的 y 双击后若实体校验不通过，就删掉该条并回退到全扫描。
import json as _json
_ROW_CACHE_PATH = "/tmp/witp_row_cache.json"


def _cache_load():
    try:
        with open(_ROW_CACHE_PATH) as f:
            return {int(k): int(v) for k, v in _json.load(f).items()}
    except Exception:
        return {}


def _cache_save(d):
    try:
        with open(_ROW_CACHE_PATH, "w") as f:
            _json.dump({str(k): v for k, v in d.items()}, f)
    except Exception:
        pass


def _cache_put(tf_num, y):
    d = _cache_load()
    d[int(tf_num)] = int(y)
    _cache_save(d)


def _cache_drop(tf_num):
    d = _cache_load()
    d.pop(int(tf_num), None)
    _cache_save(d)


def _ensure_list(log=None):
    """确保处于编队列表态；不在则从地图态按 T 打开。返回 ui_state。"""
    st = ui_state(_shot())
    if st == "list":
        return st
    reset_to_map(log=None)
    # 键盘需要窗口持有输入焦点：先点地图空白处（非选点模式下只选中该格）
    _vnc(950, 60)
    time.sleep(0.8)
    _key("t")
    time.sleep(3.0)
    return ui_state(_shot())


def warm_row_cache(log=None, max_rows=12):
    """★一次扫描，把列表里所有可识别编号的行都记进缓存★

    动机：open_tf_panel 的扫描是「命中即返回」，缓存只能增量填充
    —— 第一次取 TF14 后缓存里只有 14；再取 TF15 仍要重扫 250 行。
    本函数把**整张表**扫一遍，之后同一回合内所有 open_tf_panel 都是快路径。

    返回发现的映射 {tf_num: y}。
    """
    found = dict(_cache_load())
    st = _ensure_list(log=log)
    if st != "list":
        if log:
            log(f"  ⚠ 预热失败：无法进入列表（{st}）")
        return found
    for k in range(max_rows):
        y = ROW_Y0 + k * ROW_DY
        if y > 690:
            break
        if int(y) in found.values():
            continue
        im = _shot()
        if ui_state(im) != "list":
            if log:
                log("  列表被关闭，预热中止")
            break
        _vnc(LIST_CLICK_X, y, "dblclick")
        time.sleep(2.4)
        im = _shot()
        if ui_state(im) == "main":
            got = panel_tf_number(im)
            if got is not None:
                found[int(got)] = int(y)
                _cache_put(got, y)
                if log:
                    log(f"    预热 y={y} → TF{got}")
            _key("escape")
            time.sleep(1.3)
        elif ui_state(im) != "list":
            _ensure_list(log=None)
    if log:
        log(f"  预热完成：{ {k: v for k, v in sorted(found.items())} }")
    return found


def open_tf_panel(tf_id, log=print):
    """打开目标编队的**主面板**（Task Force Information Screen）。

    ★键语义实测订正（2026-10-03）★
      · **T = 打开编队列表（不是切换键）**：地图态按 T → list；
        列表态再按 T 仍是 list（不会关闭）。此前当切换键用是错的。
      · **Escape = 关闭列表/面板**（逐级退回：子面板→主面板→地图/列表→地图）。
      · 列表里在目标行 **双击** 打开主面板（单击不开）。

    ★★v19-95 改用「逐行双击 + 标题校验」暴力扫描★★
    为什么不直接 OCR 编号列：
      编号是 3~4 字符小字（如 "14"/"15"/"22"），tesseract 在**单行**上极不稳定
      —— 实测把 y=376 行的 "25" 读成 "7"，把 15 行读成 "4/4"。
      一旦读错，就会双击**相邻行**，静默打开错误编队，
      并且面板回读的坐标是"那个错编队"的 ⇒ **内部完全自洽的假成功**。
    为什么暴力扫描是对的：
      主面板标题是大字（`US Navy TF 14 (6 ships) is at sea near ...`），
      OCR 高度可靠（多组 scale/psm 交叉投票）⇒ 用它作**真值判据**，
      逐行试开，直到标题编号 == 目标编号。命中即返回，错行立即关闭。
    代价：最坏 O(N) 次开/关（N≈10），每次 ~4s；实测目标常在前几行。
    正确性 >> 速度 —— 开错编队会让整回合命令下到错误单位上。

    ★★实体校验不可跳过★★
    `panel_tf_number()` 返回 None（OCR 失败）时**视为不匹配**、继续扫描，
    绝不允许"无法校验"被当作"通过"。

    返回 (y_button, x_button)；失败返回 (None, None)。
    """
    want = re.sub(r"\D", "", str(tf_id)) or str(tf_id)

    # ① 若已经是主面板，先校验；不符就关掉
    for _ in range(4):
        st = ui_state(_shot())
        if st != "main":
            break
        got = panel_tf_number()
        if got is not None and str(got) == want:
            return _panel_button(log)
        if log:
            log(f"  ✗ 当前面板是 TF{got}（要 TF{want}）→ 关闭重来")
        _key("escape")
        time.sleep(1.6)

    # ② 列表态：先试**缓存行**（快路径），再全扫描
    for round_ in range(3):
        st = _ensure_list(log=log)
        if st != "list":
            if log:
                log(f"  ⚠ 无法进入编队列表（ui_state={st}）")
            continue
        rows = [ROW_Y0 + k * ROW_DY for k in range(ROW_N)]
        cy = _cache_load().get(int(want))
        if cy and cy in rows:
            rows.remove(cy)
            rows.insert(0, cy)  # 缓存行优先
            if log:
                log(f"  缓存命中：先试 y={cy}")
        for y in rows:
            im = _shot()
            if ui_state(im) != "list":
                break  # 列表被关掉了，重开
            _vnc(LIST_CLICK_X, y, "dblclick")
            time.sleep(2.6)
            im = _shot()
            if ui_state(im) == "main":
                got = panel_tf_number(im)
                if got is not None and str(got) == want:
                    _cache_put(got, y)          # ★记入缓存★
                    if log:
                        log(f"  ✓ 列表行 y={y} → 主面板 TF{got}（校验通过）")
                    return _panel_button(log, im)
                if got is not None:
                    _cache_put(got, y)          # 顺带记下这个（非目标的）行
                if got is None:
                    # ★2026-10-15 修（TF6 被永久跳过）★
                    #   实测 y=306→TF5、y=320→**None**、y=334→TF7：
                    #   中间那行恰是 TF6，但它的编号小字 OCR **恒读不出**。
                    #   旧逻辑「None 一律视为不匹配」⇒ TF6 永远打不开，
                    #   进而 set-dest / set-tf-mission 对 TF6 全部失效
                    #   （这是「TF6 从未炮击 PM」的最底层原因）。
                    #   兜底：按**行序**推断 —— T 列表恒按 TF 编号升序、每编队
                    #   一行，行 y = ROW_Y0 + (n-1)*ROW_DY，故
                    #     n = round((y - ROW_Y0)/ROW_DY) + 1
                    #   推断值 == 目标时即采用（其余情况仍需编号明确匹配，
                    #   以防真点错行）。
                    est = int(round((float(y) - ROW_Y0) / float(ROW_DY))) + 1
                    if str(est) == want:
                        _cache_put(int(want), y)     # ★记入缓存★
                        if log:
                            log(f"  ✓ 列表行 y={y} → 编号 OCR 读不出，"
                                f"按行序推断为 TF{est} == 目标（采用）")
                        return _panel_button(log, im)
                    if log:
                        log(f"    y={y} → 编号读不出，行序推断 TF{est}（非目标）")
                if cy is not None and y == cy:
                    _cache_drop(want)           # ★缓存行失效★：它指错了实体
                if log and got is not None:
                    log(f"    y={y} → TF{got}（非目标）")
                _key("escape")
                time.sleep(1.4)
                # Esc 后面板可能退到列表，也可能退到地图
                if ui_state(_shot()) != "list":
                    _ensure_list(log=None)
            else:
                # 双击没打开面板（可能点空行）→ 继续下一行
                if ui_state(_shot()) != "list":
                    _ensure_list(log=None)
        if log:
            log("  ⚠ 本轮扫描未命中 → 重开列表重扫")
    return None, None


def _panel_button(log=None, im=None):
    """在主面板上找到 Destination 标签，返回 (y_button, x_button)。"""
    im = im or _shot()
    lab = find_dest_label(im)
    if lab is None:
        if log:
            log("  ⚠ 主面板已开但找不到 Destination 标签")
        return None, None
    bx = int(lab[0]) - 45
    if log:
        log(f"  Destination 标签 x={lab[0]:.0f} y={lab[2]} → 按钮 x={bx}")
    return lab[2], bx


# ── 读面板 Hex 行 ─────────────────────────────────────────────────────────

def read_panel_hex(tries=3, log=None):
    """读面板内目的地行，返回 (x,y) 或 None。

    ★实测（2026-10-03）★ 目的地行的格式**有两种**：
      · 普通格：`Hex: x,y`
      · **基地格：`<基地名>-x,y`**（实测 `Torokina-109,130`，**没有 `Hex:` 前缀**！）
    只找 `Hex` 词会漏掉基地格目的地 ⇒ 必须同时按 `x,y` 数字对兜底解析。
    """
    for _ in range(tries):
        im = _shot()
        # ── ① 先按 `Hex:` 标签法（普通格） ──
        lab = None
        for scale in (2, 3):
            for psm in ("11", "6", "7"):
                for (t, x0, y0, x1, y1) in _tsv_words(im, PANEL_BOX, scale, psm):
                    if re.match(r"^[HhKk][ea]x", t.strip()):
                        lab = (x1, y0, y1)
                        break
                if lab:
                    break
            if lab:
                break
        if lab:
            x1, y0, y1 = lab
            g = ImageOps.grayscale(im)
            for dx, w in ((1, 90), (1, 60), (0, 120)):
                box = (int(x1) + dx, max(0, int(y0) - 4),
                       int(x1) + dx + w, int(y1) + 4)
                c = g.crop(box)
                c = c.resize((c.width * 8, c.height * 8), Image.LANCZOS)
                c.save("/tmp/_tfp_hexnum.png")
                for psm in ("7", "6", "13"):
                    r = subprocess.run(
                        ["tesseract", "/tmp/_tfp_hexnum.png", "stdout",
                         "--psm", psm, "-c", "tessedit_char_whitelist=0123456789 "],
                        capture_output=True)
                    nums = re.findall(r"\d{2,3}", r.stdout.decode(errors="replace"))
                    if len(nums) >= 2:
                        x, y = int(nums[0]), int(nums[1])
                        if 10 <= x <= 250 and 10 <= y <= 250:
                            if log:
                                log(f"    Hex 行 → ({x},{y})")
                            return (x, y)
        # ── ② 兜底：目的地行（Set TF Destination 下方一行）里直接找 `x,y` ──
        lab2 = find_dest_label(im)
        if lab2:
            yc = lab2[2]
            y0 = max(0, yc + 4)
            y1 = min(im.height, yc + 30)
            for x0, x1_ in ((300, 900), (400, 900), (140, 900)):
                c = ImageOps.grayscale(im.crop((x0, y0, x1_, y1)))
                c = c.resize((c.width * 4, c.height * 4), Image.LANCZOS)
                c.save("/tmp/_tfp_hexnum2.png")
                for psm in ("7", "6", "11"):
                    rr = subprocess.run(
                        ["tesseract", "/tmp/_tfp_hexnum2.png", "stdout", "--psm", psm],
                        capture_output=True)
                    t = rr.stdout.decode(errors="replace")
                    m = re.search(r"(\d{2,3})\s*[,\-–.]\s*(\d{2,3})", t)
                    if m:
                        x, y = int(m.group(1)), int(m.group(2))
                        if 10 <= x <= 250 and 10 <= y <= 250:
                            if log:
                                log(f"    目的地行(非Hex格式) {t.strip()!r} → ({x},{y})")
                            return (x, y)
        time.sleep(0.8)
    return None


# ── 兼容旧接口 ────────────────────────────────────────────────────────────

def find_dest_button(im=None, log=None):
    """旧接口：返回 (y, x)，主面板不在时 (None,None)。"""
    lab = find_dest_label(im)
    if lab:
        return lab[2], int(lab[0]) - 45
    return None, None


def panel_alive(im=None):
    return find_dest_label(im) is not None


def find_dest_label_x(im=None):
    lab = find_dest_label(im)
    return (lab[0], lab[1]) if lab else None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    print("ui_state =", ui_state())
    print("open_tf_panel →", open_tf_panel(tf))
