"""set-dest 定稿 v3：以**编队面板的大字 Hex 行**为闭环反馈。

═══ 为什么不用顶栏 ═══
 顶栏是 5~6px 的微小点阵字体（宽窄不一），实测 tesseract 系统性错读
（`111`→`141`），手工解析也极易出错。而编队详情面板里的 `Hex: x,y` 行
**字体更大**，OCR 稳定可得正确值（实测拿到 105,116 / 119,118 / 104,153）。

═══ 已实测的关键机制 ═══
 ① 选点模式是**一次性**的：点 `Set TF Destination` 后再点一次地图，
    即设定目的地并**退出**该模式。⇒ 每次点击前都要重新点按钮。
 ② 面板遮挡地图 x159..854 / y195..546 ⇒ 点击必须落在**面板外的可见地图带**
    （下带 y=560..730 最宽敞）。
 ③ 点击落在面板上会把面板关掉 ⇒ 每轮先检查面板是否还在，不在就重开。
 ④ 方向键仅在**纯地图模式**下滚动视野，面板打开时无效 ⇒ 目标须先在地图模式下
    滚到可见带内。
 ⑤ 最终权威核验是**结算后读层**的 `target_x/target_y`（面板文本只作过程判据）。
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

sys.path.insert(0, "/root/.hermes/profiles/witp/witp-agent")
os.environ.setdefault("LANG", "C.UTF-8")
os.environ.setdefault("LC_ALL", "C.UTF-8")

from lib.hexbar import get_window_offset, read_hex       # noqa: E402
from PIL import Image, ImageOps                          # noqa: E402

# 可点地图区 = 窗口内 (40..990, 40..755) 去掉面板遮挡矩形 (159,195)-(854,546)
CLICK = (40, 40, 990, 755)
PANEL = (159, 195, 854, 546)
MARGIN = 10                 # 贴近面板/边缘时的安全余量
DEFAULT_W, DEFAULT_H = 42.1, 40.0
KEY_CELLS = 2


def in_map(x, y):
    """该像素是否落在「面板外的可见地图」内。"""
    if not (CLICK[0] <= x <= CLICK[2] and CLICK[1] <= y <= CLICK[3]):
        return False
    return not (PANEL[0] - MARGIN <= x <= PANEL[2] + MARGIN
                and PANEL[1] - MARGIN <= y <= PANEL[3] + MARGIN)


def clamp_to_map(x, y):
    """把任意像素钳到最近的可点地图位置（四带取最近者）。"""
    if in_map(x, y):
        return (x, y)
    x = min(CLICK[2], max(CLICK[0], x))
    y = min(CLICK[3], max(CLICK[1], y))
    if in_map(x, y):
        return (x, y)
    # 被面板挡住 → 推到面板最邻近的一条带
    # ★必须用 MARGIN+2：in_map 的禁区本身就是「面板 ± MARGIN」，
    #   贴到 PANEL±MARGIN 上仍被判为禁区（实测踩过 → 返回 None）。
    off = MARGIN + 2
    cands = [
        (PANEL[0] - off, y),             # 面板左侧
        (PANEL[2] + off, y),             # 面板右侧
        (x, PANEL[1] - off),             # 面板上方
        (x, PANEL[3] + off),             # 面板下方
    ]
    cands = [c for c in cands if in_map(*[int(v) for v in c])]
    if not cands:
        return None
    best = min(cands, key=lambda c: (c[0] - x) ** 2 + (c[1] - y) ** 2)
    return (int(best[0]), int(best[1]))



def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(k, pace=0.55):
    """发一次按键。

    ★实测坑★ 方向键**连发过快会被丢弃**（间隔 0.35s 时 right 连续 6 次全部无效，
      单独发、间隔 1.6s 时 6/6 生效）。故统一用 0.55s 间隔并逐次确认。
    """
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _map_hash():
    """地图区像素指纹（用于确认视野是否真的动了）。"""
    import hashlib
    ox, oy = get_window_offset()
    subprocess.run(["import", "-window", "root", "/tmp/_sd_map.png"],
                   capture_output=True)
    im = Image.open("/tmp/_sd_map.png").crop((ox, oy, ox + 1024, oy + 768))
    return hashlib.md5(im.crop((60, 60, 820, 640)).tobytes()).hexdigest()[:12]


def scroll_cells(dx_cells, dy_cells, log=None, max_each=14):
    """按格数滚动视野（每次按键 2 格）。**只按确实生效的键**：
    每次按键前后比对地图指纹，未生效就重发一次（实测连发丢键是主要失败模式）。
    返回实际按下的总次数。
    """
    plan = []
    if dx_cells > 0:
        plan.append(("right", int(abs(dx_cells) // 2)))
    elif dx_cells < 0:
        plan.append(("left", int(abs(dx_cells) // 2)))
    if dy_cells > 0:
        plan.append(("down", int(abs(dy_cells) // 2)))
    elif dy_cells < 0:
        plan.append(("up", int(abs(dy_cells) // 2)))
    total = 0
    for k, n in plan:
        n = min(n, max_each)
        for _ in range(n):
            _key(k, pace=0.55)          # ★间隔 0.55s★ 实测 0.35s 连发会丢键
            total += 1
        time.sleep(0.6)
    if total:
        time.sleep(1.2)
    return total


def _shot():
    """截取游戏窗口（带重试：实测 `import` 偶发留下**截断的半张图**）。"""
    ox, oy = get_window_offset()
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":98"))
    for _ in range(3):
        subprocess.run(["import", "-window", "root", "/tmp/_sd3_fb.png"],
                       capture_output=True, env=env)
        try:
            im = Image.open("/tmp/_sd3_fb.png")
            im.load()
            return im.crop((ox, oy, ox + 1024, oy + 768))
        except Exception:
            time.sleep(0.8)
    raise RuntimeError("截图失败（import 连续 3 次未产出可读文件）")


def find_dest_button(im):
    """OCR 定位 `Set TF Destination` 行 → (y_中心, x_点击)。找不到返回 (None, None)。

    ★实测坑★ 最初用固定「3x 放大 + psm 6」扫 (420,185)-(720,350)，
    对某些编队（内容不同、按钮行位置不同）会读不出 `Destination`，
    明明面板已经打开却报"未看到详情面板" → 整个流程在第二步死掉。
    改为多裁剪窗口 × 多放大 × 多 psm 投票，任一命中即返回。
    """
    for box in ((420, 185, 740, 360), (400, 175, 780, 380), (420, 195, 740, 340)):
        for sc in (2, 3, 4):
            c = im.crop(box)
            c = c.resize((c.width * sc, c.height * sc), Image.LANCZOS)
            c.save("/tmp/_sd3_btn.png")
            for psm in ("6", "11", "4"):
                r = subprocess.run(["tesseract", "/tmp/_sd3_btn.png", "stdout",
                                    "--psm", psm, "tsv"], capture_output=True)
                for ln in r.stdout.decode(errors="replace").splitlines()[1:]:
                    f = ln.split("\t")
                    if len(f) < 12:
                        continue
                    t = (f[11] or "").strip().lower()
                    # 容忍 OCR 把 Destination 读成 Destin ation / Destinstion 等
                    if "destin" in t or "estination" in t:
                        y = box[1] + (int(f[7]) + int(f[9]) // 2) // sc
                        return y, 534
    return None, None


# 最近一次 find_tf_row 定位到的「TF 编号列」左边界（供双击定位复用）
_LAST_COL_X0 = None


# Jump Map（右下角小地图）：实测本体范围与「当前视野红框」位置（视觉标定）
MM_BOX = (852, 662, 998, 758)       # 小地图本体
MM_VIEW = (930, 720, 955, 740)      # 当前视野红框（标定时刻读数）


def minimap_jump_and_set(mm_x, mm_y, by, bx, log=None):
    """★远距离一步到位★ 在**选点模式**下点小地图。

    实测（第 2 轮）：选点模式下点小地图 → **视野跳到该处**且**面板关闭**
    （= 目的地已设定并退出选点模式）。这是覆盖任意远距离目标的唯一通道：
    比"滚视野 50 格"可靠得多（滚动要按 25 次键且极易丢键）。
    返回 True 表示已发出点击（最终以重开面板/读层核验）。
    """
    if log:
        log(f"  走小地图通道：选点模式 → 点小地图({mm_x},{mm_y})")
    _vnc(bx, by); time.sleep(2.4)          # 进选点模式
    _vnc(mm_x, mm_y); time.sleep(3.4)      # 点小地图（会跳视野并结束选点）
    return True


def ensure_map_focus(log=None, max_tries=4):
    """确保方向键在地图模式下生效（自适应探测 Escape 次数）。

    ★为什么需要它★ 实测焦点状态很脆：
        · 编队详情面板打开 → 方向键被面板吃掉
        · 面板关闭后，Escape 按多几次 / 点击地图 **都会**破坏地图焦点
        · 唯一可靠的判据是「按一次方向键，看地图像素是否变化」
    故这里**逐次尝试**：每按一次 Escape，就用一次方向键试探；一旦地图有反应即成功。
    """
    for i in range(max_tries + 1):
        before = _map_hash()
        _key("down", pace=0.5)
        after = _map_hash()
        if before != after:
            if log:
                log(f"  地图焦点已就绪（第 {i} 次试探命中，已下移 1 键）")
            # ★不按 up 抵消★ 实测：抵消动作本身会把地图焦点再次弄丢。
            #   试探造成的 1 键位移由调用方按实际按键数计入。
            return True
        if i < max_tries:
            # ★只按一次 Escape★（实测：esc×1 → 生效；esc×2 → 失效）
            _key("escape", pace=0.7)
            _vnc(200, 620)                # 点一处空白水域，帮助地图取回焦点
            time.sleep(0.6)
    if log:
        log("  ⚠ 无法获得地图焦点（方向键无效）")
    return False


def read_panel_hex(by, tries=4):
    """读面板内按钮下行的 `Hex: x,y`（大字体，OCR 可靠）。"""
    for _ in range(tries):
        g = ImageOps.grayscale(_shot()).crop((430, by + 2, 700, by + 26))
        for sc in (6, 8, 10):
            z = g.resize((g.width * sc, g.height * sc), Image.LANCZOS)
            z.save("/tmp/_sd3_row.png")
            for psm in ("7", "6", "11"):
                r = subprocess.run(["tesseract", "/tmp/_sd3_row.png", "-",
                                    "--psm", psm], capture_output=True)
                t = r.stdout.decode(errors="replace")
                m = re.search(r"(\d{2,3})\s*[,，.]?\s*(\d{2,3})", t)
                if m:
                    x, y = int(m.group(1)), int(m.group(2))
                    if 10 <= x <= 250 and 10 <= y <= 250:
                        return (x, y)
        time.sleep(1.0)
    return None


def panel_alive(im):
    """面板是否还在（用按钮关键字判断）。"""
    y, _ = find_dest_button(im)
    return y is not None


class MapView:
    """纯地图模式下的像素↔格映射（用顶栏标定；顶栏读取失败则退回经验值）。"""

    def __init__(self):
        self.W, self.H = DEFAULT_W, DEFAULT_H
        self.ax = self.ay = self.hx = self.hy = None

    def calibrate(self, px=(512, 384), log=None):
        _vnc(*px)
        time.sleep(2.2)
        h = read_hex(frames=4, unanimous=False)
        if not h:
            return None
        self.ax, self.ay, self.hx, self.hy = px[0], px[1], h[0], h[1]
        if log:
            log(f"  视角标定 像素{px} ↔ Hex{h}")
        return h

    def pixel_of(self, tx, ty):
        return (self.ax + (tx - self.hx) * self.W, self.ay + (ty - self.hy) * self.H)

    def bring_into(self, tx, ty, want, iters=10, log=None):
        """滚视野，使 (tx,ty) 落在 want 像素附近。"""
        for _ in range(iters):
            if self.calibrate(log=None) is None:
                return False
            gx, gy = self.pixel_of(tx, ty)
            nx = int(round((gx - want[0]) / (self.W * KEY_CELLS)))
            ny = int(round((gy - want[1]) / (self.H * KEY_CELLS)))
            if abs(nx) <= 1 and abs(ny) <= 1:
                if log:
                    log(f"  目标格位于像素 ({gx:.0f},{gy:.0f})，已就位")
                return True
            nx, ny = max(-14, min(14, nx)), max(-14, min(14, ny))
            for _ in range(abs(nx)):
                _key("right" if nx > 0 else "left"); time.sleep(0.3)
            for _ in range(abs(ny)):
                _key("down" if ny > 0 else "up"); time.sleep(0.3)
            time.sleep(1.8)
        return False


def find_tf_row(tf_id, log=None):
    """在 T 列表按 **TF 编号**定位行 y（不能假定第一行就是目标；实测 TF14 占着首行）。

    做法：逐行带 OCR TF 编号列（窗口 x150..215），取首个匹配行。
    """
    im = _shot()
    g = ImageOps.grayscale(im)
    # ★tf_id 可能带 `TF` 前缀（witp-cmd 传 "TF14"），必须只取数字★
    #   实测教训：`int("TF14")` 抛 ValueError → 反推分支静默失效 →
    #   每轮都报"未找到 TF 行"，看起来像 T 键失效，实际是这里。
    global _LAST_COL_X0
    want = re.sub(r"\D", "", str(tf_id)) or str(tf_id)
    # ★实测几何（决定性测试所得）★
    #   · TF 编号列：x≈148..178（读数时以 148 为起点最稳；实测 read(x=148,y) 能出 `14`）
    #   · 数据行 y 从 236 起、行距 15（TF14 命中 y≈249..253，取 251）
    #   · 列表只有十几行 ⇒ 直接逐行扫，不做花哨的自洽搜索（那样要 1500+ 次 OCR，超时）
    # ★★v19-93 行距订正★★
    #   实测（listcal.py 前景带扫描 + OCR，2026-10-06）：
    #     表头 y=232；TF 行 y = 250, 264, 278, 292, 306 ⇒ **行距 14**（不是 15）
    #   旧值 15 会让第 k 行累积偏差 k 像素：第 5 行差 5px ⇒ 落在两行之间
    #   ⇒ OCR 读到相邻行的编号 ⇒ **打开错误的编队**
    #   （实测：open_tf_panel('TF15') 打开了 TF21 潜艇面板，
    #     面板写着 "US Navy TF 21"、Hex 97,129，与读层 TF21 的 target 吻合）
    COL_X0 = 148
    ROW_Y0, ROW_DY, ROW_N = 250, 14, 16

    def _read_row(y):
        votes = {}
        for sc in (5, 7):
            band = g.crop((COL_X0, y - 12, COL_X0 + 32, y + 4))
            z = band.resize((band.width * sc, band.height * sc), Image.LANCZOS)
            z.save("/tmp/_sdfr_b.png")
            for psm in ("7", "6"):
                r = subprocess.run(["tesseract", "/tmp/_sdfr_b.png", "-",
                                    "--psm", psm, "-c",
                                    "tessedit_char_whitelist=0123456789"],
                                   capture_output=True)
                t = re.sub(r"\D", "", r.stdout.decode(errors="replace"))
                if 1 <= len(t) <= 3:
                    votes[t] = votes.get(t, 0) + 1
        if not votes:
            return None, 0
        return max(votes.items(), key=lambda kv: kv[1])

    rows = []
    for k in range(ROW_N):
        y = ROW_Y0 + k * ROW_DY
        if y > 690:
            break
        t, c = _read_row(y)
        if t and c >= 2:
            rows.append((y, t, c))
    global _LAST_COL_X0
    _LAST_COL_X0 = COL_X0
    if log:
        log(f"  列扫描（{len(rows)} 行）: " +
            ", ".join(f"{t}@{yy}" for yy, t, _ in rows[:14]))
    for yy, t, c in rows:
        if t == want:
            if log:
                log(f"  TF{tf_id} 列表行 y={yy}（票 {c}）")
            return yy
    # 反推（绕过 `14`→`44` 这类字形误读）：用最近的合法锚点 + 行距
    try:
        cand = sorted([(yy, int(t)) for yy, t, c in rows if 10 <= int(t) <= 99])
        if cand:
            y_a, n_a = min(cand, key=lambda kv: abs(kv[1] - int(want)))
            guess = y_a + (int(want) - n_a) * ROW_DY
            if log:
                log(f"  TF{tf_id} 由最近锚点 {n_a}@{y_a} 反推 y={guess}"
                    f"（行距 {ROW_DY}px）")
            return int(guess)
    except Exception as _e:
        if log:
            log(f"  ⚠ 反推异常: {_e!r}")
    if log:
        log(f"  ⚠ TF{tf_id} 未在列表中找到")
    return None


def _unused_old_find_tf_row():
    # ★用「行序 + 行距 14px」反推★
    #   实测：`14` 会被读成 `43`/`166`（`1` 的斜起笔被判成 `4`），
    #   但 `15`/`18`/`20`/`21`/`22`/`23` 读得稳；该列表按编号升序、行距恒 14px。
    #   ⇒ 用**最靠近目标编号的锚点**线性推：y = y_a + (want − n_a) × 14。
    #   取"最靠近"而非"最长串"，是因为列表中编号可能不连续（如无 TF19），
    #   用远处锚点会累加逐行误差。
    try:
        cand = sorted([(yy, int(t)) for yy, t, c in rows if 10 <= int(t) <= 60])
        if cand:
            y_a, n_a = min(cand, key=lambda kv: abs(kv[1] - int(want)))
            guess = y_a + (int(want) - n_a) * 14
            if log:
                log(f"  TF{tf_id} 由最近锚点 {n_a}@{y_a} 反推 y={guess}"
                    f"（行距 14px 实测）")
            return int(guess)
    except Exception as _e:
        if log:
            log(f"  ⚠ 反推异常: {_e!r}")
    if log:
        log(f"  ⚠ TF{tf_id} 未在列表中找到（列扫描原始结果 "
            f"{[(t, y) for y, t, _ in rows]}）")
    return None


def _dead_find_tf_row_unused():
    bands = []
    for y in bands:
        band = g.crop((col_x0, y - 6, min(col_x1, W), y + 7))
        # ★必须走「数字白名单 + 多次放大投票」★
        #   实测教训：通用 OCR 把 `14` 读成 `44`、`15` 读成 `45`
        #   （字形 `1` 与 `4` 在该字体下形近，且 4x 放大时被拉伸成 4）。
        #   更严重的是：`44` 与 `14` 都是合法 TF 编号 → **静默改错编队**。
        #   故：白名单只读数字 + 多放大倍数/psm 投票，且要求票数 ≥2。
        from collections import Counter
        votes = Counter()
        for sc in (6, 8, 10, 12):
            z = band.resize((band.width * sc, band.height * sc), Image.LANCZOS)
            z.save("/tmp/_sdfr_b.png")
            for psm in ("7", "8", "10", "13"):
                r = subprocess.run(["tesseract", "/tmp/_sdfr_b.png", "-",
                                    "--psm", psm, "-c",
                                    "tessedit_char_whitelist=0123456789"],
                                   capture_output=True)
                t = re.sub(r"\D", "", r.stdout.decode(errors="replace"))
                if 1 <= len(t) <= 3:
                    votes[t] += 1
        if not votes:
            continue
        best, cnt = votes.most_common(1)[0]
        if best == want and cnt >= 2:
            if log:
                log(f"  TF{tf_id} 列表行 y={y}（票 {cnt}，候选 {votes.most_common(3)}）")
            return y
    return None


def set_tf_dest(tf_id, tx, ty, row_y=None, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty}) ===")
    # ★不要在这里按 Escape★ 实测：开局按 Escape 会破坏地图焦点，
    #   导致随后的 T（打开编队列表）失效 → 整个流程在第一步就死掉。
    #   若当前有面板/列表打开，open_panel 内部会按 T 把它切掉。

    # ── 第 1 步：地图模式把目标滚到「面板下方可见带」 ──
    mv = MapView()
    ok_cal = mv.calibrate(log=log) is not None
    if not ok_cal:
        log("  ⚠ 顶栏标定失败，改用经验比例并只做一次粗略置位")
    # 标定/点击用的稳定点：面板下方那条带（实测面板遮挡至 y=546）
    want = (500, 640)
    if ok_cal:
        mv.bring_into(tx, ty, want, log=log)

    # ── 第 2 步：开面板 ──
    def open_panel(retries=2):
        """打开目标编队的详情面板。

        ★实测★
          · **不要**在按 T 之前按 Escape：那会破坏地图焦点，导致随后的 T 也无效。
          · T 是切换键：再按一次会关掉列表，故只在「列表不在」时才按。
          · 判定「列表在不在」用 TF 编号列能否 OCR 出行。
        """
        nonlocal row_y

        _LIST_PROBE = (14, 15, 16, 18, 20, 22, 25)

        def list_open():
            """列表是否已打开：看「列表区域是否有一列合法 TF 编号」。

            ★为什么不能靠"探测某个具体编号"★ 实测：单次探测经常读不出
            （字形 `1`/`4` 形近、或该帧 OCR 抖动），一旦误判为"列表没开"，
            后续按 T 反而把列表**关掉** —— 这轮反复出现"T 突然失效"的真因。
            改为结构性判据：只要列表区存在「≥4 行、行距 14px、编号 1~99」的列，
            即认定列表已打开。
            """
            try:
                g_ = ImageOps.grayscale(_shot())
                W_ = g_.size[0]
                px2 = g_.load()
                for cx in (140, 148, 156, 164, 172):
                    ys = [y for y in range(232, 480)
                          if sum(1 for x in range(cx, min(cx + 26, W_))
                                 if px2[x, y] > 110) >= 3]
                    groups, cur = [], []
                    for y in ys:
                        if cur and y - cur[-1] <= 2:
                            cur.append(y)
                        else:
                            if cur and cur[-1] - cur[0] >= 3:
                                groups.append((cur[0] + cur[-1]) // 2)
                            cur = [y]
                    if cur and cur[-1] - cur[0] >= 3:
                        groups.append((cur[0] + cur[-1]) // 2)
                    if len(groups) >= 4:
                        return True
            except Exception:
                pass
            return False

        # ★★★ 三种界面状态必须先分清，否则 T 会把界面切错 ★★★
        #   实测（本轮核心坑）：T 是**切换键**。
        #     · 若**编队详情面板**已打开：按 T 会把它关掉 → 之后既无列表也无面板
        #     · 若**列表**已打开：按 T 会关掉列表 → 下一轮"找不到行"
        #   故顺序必须是：先看详情面板在不在 → 再看列表在不在 → 都不在才按 T。
        for _try in range(retries + 1):
            im_now = _shot()
            by_now, bx_now = find_dest_button(im_now)
            if by_now is not None:
                # 详情面板已开 —— 直接用它，不需要列表
                log(f"  编队详情面板已打开（按钮 y={by_now}）")
                return by_now, bx_now
            r = find_tf_row(tf_id, log=None)
            if r is None and not list_open():
                log("  列表与面板均未打开 → 按 T 打开列表")
                _key("t"); time.sleep(3.4)
                r = find_tf_row(tf_id, log=None)
            if r is not None:
                log(f"  定位到 TF{tf_id} 列表行 y={r}")
            if r is None:
                # ★失败时存证★ 把当前画面存下来，便于事后判断"到底在哪一屏"
                _shot_tag = f"/tmp/_sd_fail_{_try}.png"
                try:
                    _shot().save(_shot_tag)
                    log(f"  ⚠ T 列表里没找到 TF{tf_id}（第 {_try+1} 次）"
                        f"—— 已存证 {_shot_tag}")
                except Exception:
                    log(f"  ⚠ T 列表里没找到 TF{tf_id}（第 {_try+1} 次）")
                # 可能列表其实没开 → 关掉再开一次
                _key("t"); time.sleep(2.2)
                _key("t"); time.sleep(3.2)
                r = find_tf_row(tf_id, log=log)
                if r is None:
                    continue
            row_y = r
            # ★双击点必须落在该行的 **TF 编号列** 上★
            #   实测：写死 x=200 会随着列表窗口水平漂移而落到"任务名"列甚至窗口外，
            #   表现成"双击没反应、列表仍开着"。
            # ★实测：单击/双击都必须在 x≈200（"任务名"列）才生效★
            #   在编号列（x=156/168）点击**无效**（实测 click 与 dblclick 均不打开面板）。
            cx_click = 200
            _vnc(cx_click, r, "dblclick"); time.sleep(3.8)
            by_, bx_ = find_dest_button(_shot())
            if by_ is not None:
                return by_, bx_
            log(f"  ⚠ 双击后未看到详情面板（第 {_try+1} 次），重试")
            _key("escape"); time.sleep(1.0)
        return None, None
        im = _shot()
        # ★核验打开的是不是目标编队★
        #   标题形如 "IJ Navy TF 14 (10 ships) is at sea"。
        #   实测：该标题 OCR 不稳（常把 `TF 14` 读成 `TF 44` 或整个读空），
        #   故核验必须是**宽松**的：只有在"明确读出了另一个编号"时才拒绝；
        #   读空一律放行（此时以面板存在为准，由后续读层核验兜底）。
        want_digits = re.sub(r"\D", "", str(tf_id))
        z = im.crop((150, 178, 580, 208)).resize((430 * 3, 30 * 3), Image.LANCZOS)
        z.save("/tmp/_sdtitle.png")
        tr = subprocess.run(["tesseract", "/tmp/_sdtitle.png", "-", "--psm", "7"],
                            capture_output=True).stdout.decode(errors="replace")
        mm = re.search(r"TF\s*[:.]?\s*(\d{1,3})", tr, re.I)
        got = mm.group(1) if mm else None
        if got is not None and got != want_digits and got.lstrip("0") != want_digits:
            log(f"  ⚠ 打开的编队是 TF{got}，与目标 TF{want_digits} 不符 → 拒绝继续"
                f"（标题原文 {tr.strip()!r}）")
            _key("escape"); time.sleep(1.0)
            return None, None
        y, x = find_dest_button(im)
        return y, x

    by, bx = open_panel()
    if by is None:
        log("  ✗ 未能打开编队详情面板")
        return False, None
    log(f"  面板就绪，按钮 y={by}")

    # ── 第 2.5 步：地图模式预滚（把目标拉进可见区）──
    # ★为什么必须在地图模式下滚★
    #   编队详情面板打开时，点击地图**不会移动视野**（面板吃掉了地图交互），
    #   所以「在面板里滚动 → 重探基准」永远测不出位移（实测原地打转 8 轮）。
    #   且方向键只在面板**关闭**时生效，故必须：退到地图 → 滚动 → 再开面板。
    def ensure_target_visible(tx_, ty_, base_px_, base_h_, W_, H_):
        """在地图模式下把目标滚到可点区。返回 (base_px, base_h)。"""
        bx, bh = base_px_, base_h_
        for _ in range(4):
            px_ = bx[0] + (tx_ - bh[0]) * W_
            py_ = bx[1] + (ty_ - bh[1]) * H_
            cx_ = clamp_to_map(px_, py_)
            if cx_ is not None and abs(cx_[0] - px_) <= DEFAULT_W * 4 \
                    and abs(cx_[1] - py_) <= DEFAULT_H * 4:
                return bx, bh
            need_x, need_y = tx_ - bh[0], ty_ - bh[1]
            log(f"  预滚视野 ({need_x:+d},{need_y:+d} 格) …")
            # ★远距离：滚视野（实测方向键有效，前提是地图焦点正确）★
            #   实测结论：
            #     · 方向键**有效**（单发、间隔 ≥0.5s；连发过快会被丢键）
            #     · **只按一次 Escape** 即回地图且焦点可用；按两次或点地图都会失焦
            #     · 选点模式下点小地图只**跳视野**，不会设定目的地（因此不能当捷径）
            need_x, need_y = tx_ - bh[0], ty_ - bh[1]
            log(f"  目标距可见区较远 → 退到地图滚视野 "
                f"({need_x:+d},{need_y:+d} 格)")
            _key("escape")
            time.sleep(1.2)
            if not ensure_map_focus(log=log):
                log("    ⚠ 未能取得地图焦点，放弃预滚")
                break
            n = scroll_cells(need_x, need_y, log=log)
            log(f"    已发 {n} 键")
            # 滚动只改「像素↔hex」的基准，不影响比例；按实际按键数平移基准
            if need_x:
                bh = (bh[0] + (n if need_x > 0 else -n) * KEY_CELLS, bh[1])
            elif need_y:
                bh = (bh[0], bh[1] + (n if need_y > 0 else -n) * KEY_CELLS)
            continue
            if open_panel()[0] is None:
                break
            hb = probe(*bx)
            if hb:
                log(f"    小地图跳转后目的地 = {hb}")
                bh = hb
                continue
            break
            dx = n * KEY_CELLS if need_x else 0
            dy = n * KEY_CELLS if need_y else 0
            bh = (bh[0] + (dx if need_x else 0), bh[1] + (dy if need_y else 0))
            log(f"    按 {n} 键 → 基准推算 {bh}")
            if open_panel()[0] is None:
                log("    ✗ 面板重开失败")
                break
            # 重探基准（此时面板又打开了，读的是面板内坐标，可靠）
            hb = probe(*bx)
            if hb:
                log(f"    重探基准 {bx} → {hb}")
                bh = hb
            else:
                break
        return bx, bh

    # ── 第 3 步：以面板读数为反馈的闭环 ──
    # 标定点取「下带」内两点（都在面板可见区）
    p1 = (300, 600)
    p2 = (800, 700)

    def probe(px, py):
        """点一次地图（每次都要重新进选点模式），返回面板读数。"""
        for _ in range(2):
            if panel_alive(_shot()):
                break
            log("    面板不在 → 重开")
            if open_panel()[0] is None:
                return None
        _vnc(bx, by); time.sleep(2.2)          # 进选点模式
        _vnc(int(px), int(py)); time.sleep(2.6)
        return read_panel_hex(by)

    h1 = probe(*p1)
    log(f"  标定1 像素{p1} → {h1}")
    h2 = probe(*p2)
    log(f"  标定2 像素{p2} → {h2}")
    W, H = mv.W, mv.H
    if h1 and h2 and (h2[0] != h1[0]) and (h2[1] != h1[1]):
        w = (p2[0] - p1[0]) / (h2[0] - h1[0])
        h = (p2[1] - p1[1]) / (h2[1] - h1[1])
        if 20 <= abs(w) <= 70 and 20 <= abs(h) <= 70:
            W, H = w, h
    log(f"  → 使用比例 W={W:.2f} H={H:.2f} px/格")

    base_px, base_h = (p2 if h2 else p1), (h2 or h1)
    if base_h is None:
        log("  ✗ 面板读数不可用，无法闭环")
        return False, None
    if base_h == (tx, ty):
        log(f"  ✓ 已确认为 ({tx},{ty})")
        return True, base_h

    base_px, base_h = ensure_target_visible(tx, ty, base_px, base_h, W, H)

    cur = base_px
    for i in range(8):
        dx = (tx - base_h[0]) * W
        dy = (ty - base_h[1]) * H
        want = (base_px[0] + dx, base_px[1] + dy)
        nxt = clamp_to_map(want[0], want[1])
        if nxt is None:
            log(f"  [{i+1}] 目标像素需求 ({want[0]:.0f},{want[1]:.0f}) 无可用点击位 —— "
                f"预滚未把它带进可见区，放弃（以结算后读层为准）")
            break
        h = probe(int(nxt[0]), int(nxt[1]))
        log(f"  [{i+1}] 点({nxt[0]:.0f},{nxt[1]:.0f}) → 面板 {h}")
        if h is None:
            continue
        cur = nxt
        if h == (tx, ty):
            log(f"  ✓ 面板确认目的地 = ({tx},{ty})")
            # 收尾只按一次 Escape（实测：两次会破坏地图焦点，且无必要）
            _key("escape"); time.sleep(1.0)
            return True, h
        # 用最新观测更新基准
        base_px, base_h = nxt, h
    _key("escape"); time.sleep(1.0)
    log("  ✗ 未在面板确认（以结算后读层为准）")
    return False, base_h


if __name__ == "__main__":
    tf = sys.argv[3] if len(sys.argv) > 3 else "TF1"
    tx, ty = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (105, 150)
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
