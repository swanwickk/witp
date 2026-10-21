#!/usr/bin/env python3
"""set-dest 定稿（2026-09-28）：**全程只用面板大字读数，不依赖顶栏**。

═══ 为什么绕开顶栏 ═══
本轮实测顶栏字体每字符仅约 5px：tesseract 系统性误读（`9`→`2`、`1`→`7`），
点阵模板在**相邻数字粘连**时（`116` 的两个 `1` 贴在一起，列投影并成一段）
也会读错。既然面板内 `Hex: x,y` 是大字且 OCR 稳定，就**只用它**。

═══ 闭环（探针即设定动作本身）═══
  1. 开面板（T 列表 → 目标行 x=200 双击；实测可靠）。
  2. 点 `Set TF Destination`(x=534) 进选点模式 → 点地图像素 P → 面板 Hex 行
     立刻显示该像素对应的格 H。
     ⇒ **这一次点击同时是「探针」和「设定」**，拿到 (P ↔ H) 锚点。
  3. 换一个像素再来一次 ⇒ 两个锚点解出 W、H（px/格）。
  4. 由 W、H 反算目标格的像素 → 点它 → 面板读回核验（精确相等）。
  5. 未命中则用实测落点重算锚点继续迭代。
"""

import os

# ★2026-09-28 实测根因★ 工具环境里 DISPLAY **未导出**，导致 `import` 截图
#   静默失败（返回空白/过期图，进而把界面状态判错）。这里统一兜底。
import os as _os
_os.environ.setdefault("DISPLAY", ":98")

import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.hexbar import get_window_offset            # noqa: E402
from lib import tfpanel as TP                        # noqa: E402
from PIL import Image, ImageOps                      # noqa: E402

WIN_W, WIN_H = 1024, 768
# 实测面板遮挡：x159..854 / y195..546（面板实际更宽，取保守框）
PANEL = (150, 185, 870, 560)
# 可用的探针像素（**实测**：要落在真正的地图带里）
#   地图带 = 顶部 y≈32..180（面板上方）与底部 y≈570..685（面板下方）。
#   ★y=700 已在底部信息栏上（点击无效，实测读回 None）。
#   ★实测映射： (300,120)↔(106,145)  (300,640)↔(105,159)  (700,120)↔(115,145)
#      ⇒ W≈44.4 px/格（x 方向）、H≈37 px/格（y 方向）
PROBES = [(300, 120), (300, 640), (700, 120), (700, 640)]


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _move(px, py):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncmove.py",
                    str(int(px)), str(int(py))], capture_output=True)


def _map_hash():
    """地图区像素指纹（判断视野是否真的动了）。"""
    import hashlib
    ox, oy = get_window_offset()
    subprocess.run(["import", "-window", "root", "/tmp/_sd3_hash.png"],
                   capture_output=True)
    im = Image.open("/tmp/_sd3_hash.png").crop((ox, oy, ox + 1024, oy + 768))
    return hashlib.md5(im.crop((40, 60, 980, 660)).tobytes()).hexdigest()[:12]


def _press_until_moved(key, max_tries=3, pace=0.55, log=None):
    """按方向键直到地图指纹确实变化（实测连发过快会丢键）。"""
    for _ in range(max_tries):
        before = _map_hash()
        _key(key, pace=pace)
        after = _map_hash()
        if before != after:
            return True
    if log:
        log(f"    ⚠ {key} 连续 {max_tries} 次未使视野移动")
    return False


def scroll_by_cells(dy_cells, log=None):
    """用方向键纵向滚视野。每按一次 = 2 格（实测、可逆）。"""
    key = "down" if dy_cells > 0 else "up"
    n = int(round(abs(dy_cells) / 2.0))
    done = 0
    for _ in range(n):
        if _press_until_moved(key, max_tries=3, log=log):
            done += 1
        else:
            break
    if log:
        log(f"    方向键{key}×{done}（≈{done*2} 格）")
    return done * 2


def _key(k, pace=0.6):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def _blocked(x, y):
    return PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]


def pick_clickable(x, y):
    """把目标像素挪到不被面板遮挡、且在地图可见区内的位置。"""
    if not _blocked(x, y) and 6 <= x <= WIN_W - 6 and 32 <= y <= WIN_H - 6:
        return (int(x), int(y))
    # 垂直方向找一个能点的 y
    for cand in (PANEL[1] - 12, PANEL[3] + 12, 620, 660, 700):
        if 32 <= cand <= WIN_H - 6 and not _blocked(x, cand):
            return (int(x), int(cand))
    return None


def px_reachable(x, y, tol=6):
    """该像素是否在地图可见区内（允许被面板遮挡，因为面板可先关掉）。"""
    return (tol <= x <= WIN_W - tol and 32 <= y <= WIN_H - tol)


def edge_scroll(dx_px, dy_px, log=print, rate_cells_per_sec=10.5, max_secs=2.6,
                fixed_secs=None):
    """按像素偏差方向停在窗口最外 1 像素上滚动视野。

    ★实测★ 边缘滚动确实生效（鼠标停在最外 1px，视野持续平移）；
      鼠标移开后立即停止 ⇒ **停顿时长决定滚动量**。
    ★实测标定★ 停 3.2s ≈ 平移 34 格 ⇒ 约 **10.5 格/秒**；
      但 0.5s 实测**不生效**（疑似有启动延迟），故时长下限取 1.5s。
    """
    if abs(dx_px) >= abs(dy_px):
        cells = abs(dx_px) / 44.0          # 44 px/格（实测 W≈44.4）
        secs = fixed_secs or min(max_secs, max(1.5, cells / rate_cells_per_sec))
        if dx_px > 0:
            _move(WIN_W - 1, WIN_H // 2)
            d = "右"
        else:
            _move(0, WIN_H // 2)
            d = "左"
    else:
        cells = abs(dy_px) / 40.0          # 40 px/格（实测 H≈40.0）
        secs = fixed_secs or min(max_secs, max(1.5, cells / rate_cells_per_sec))
        if dy_px > 0:
            _move(WIN_W // 2, WIN_H - 1)
            d = "下"
        else:
            _move(WIN_W // 2, 0)
            d = "上"
    log(f"    边缘滚动({d}) {secs:.1f}s …")
    time.sleep(secs)
    _move(WIN_W // 2, WIN_H // 2)
    time.sleep(0.8)
    return secs


class PanelSession:
    """保持面板打开，每次点击前重新进选点模式。"""

    def __init__(self, tf_id, log=print):
        self.tf = tf_id
        self.log = log
        self.by = None
        self.bx = 534

    def open(self):
        self.by, self.bx = TP.open_tf_panel(self.tf, log=self.log)
        return self.by is not None

    def ensure(self):
        by, bx = TP.find_dest_button()
        if by is not None:
            self.by = by
            self.bx = bx
            return True
        return self.open()

    def _button_xs(self):
        """候选的按钮点击 x。

        ★实测★ 按钮位 = `Destination` 词左边界再往左约 45px
        （手册 6.1.2.1.1` click the arrow to the left of this title`；
          实测词在 x=578..632，按钮 x=533 点击即进入选点模式）。
        """
        xs = [self.bx, 533, 534, 520]
        return [x for x in xs if x and 150 < x < 900]

    def probe(self, px, py, expect_change=True):
        """进选点模式 → 点地图像素 → 读面板。返回 (格, 面板是否仍存活)。

        ★实测★ 选点模式是**一次性的**：点一次地图即设定并退出，
        故每次点击前都必须重新点 `Set TF Destination` 按钮。
        ★实测★ **悬停不改 Hex，只有点击才改** —— 探针必须是点击。
        ★自校验★ 判断是否进入选点模式的唯一依据 =
        随后点地图使面板 Hex **发生变化**。未变者视为没进去，换下一个候选。
        """
        for bx in self._button_xs():
            if not self.ensure():
                return None, False
            before = TP.read_panel_hex(tries=2)
            _vnc(bx, self.by)
            time.sleep(1.8)
            _vnc(int(px), int(py))
            time.sleep(2.6)
            by2 = TP.find_dest_button()[0]
            if by2 is None:
                return None, True       # 面板被关掉（=已设定并退出）
            self.by = by2
            got = TP.read_panel_hex(tries=3)
            if got is None:
                continue
            if not expect_change or before is None or got != before:
                self.bx = bx
                return got, True
        return None, True


def set_tf_dest(tf_id, tx, ty, log=print):
    log(f"=== set-dest {tf_id} → Hex({tx},{ty})（面板闭环版）===")
    s = PanelSession(tf_id, log=log)
    if not s.open():
        log("  ✗ 未能打开编队详情面板")
        return False, None
    log(f"  面板已打开 y={s.by}")

    # ── 探针：建立 (像素 ↔ 格) ──
    anchors = []
    for (px, py) in PROBES:
        got, alive = s.probe(px, py)
        log(f"  探针 点({px},{py}) → 面板 {got}")
        if got:
            anchors.append(((px, py), got))
            if got == (tx, ty):
                log(f"  ✓ 已是目的地 {got}")
                return True, got
        if len(anchors) >= 4:
            break
    if len(anchors) < 2:
        log("  ✗ 探针不足两个，无法解比例")
        return False, None

    # ★分别解 W 与 H★：取 |Δhx| 最大的一对解 W、|Δhy| 最大的一对解 H。
    #   （旧实现硬用前两点，实测会遇到 Δhy=0 或 Δhy 过小导致比例失真。）
    def _slope(key, hk):
        best = None
        for i in range(len(anchors)):
            for j in range(i + 1, len(anchors)):
                (pa, ha), (pb, hb) = anchors[i], anchors[j]
                dh = hb[hk] - ha[hk]
                if abs(dh) < 2:            # 位移太小则误差放大，忽略
                    continue
                v = (pb[key] - pa[key]) / dh
                if best is None or abs(dh) > best[0]:
                    best = (abs(dh), v)
        return best[1] if best else None

    W = _slope(0, 0)
    H = _slope(1, 1)
    if W is None or H is None or not (15 <= abs(W) <= 90) or not (15 <= abs(H) <= 90):
        log(f"  ✗ 比例不合法 W={W} H={H}  锚点={anchors}")
        return False, None
    log(f"  ✓ 比例 W={W:.2f} H={H:.2f} px/格（锚点 {len(anchors)} 个）")

    # 用「与目标最近」的锚点作为基准最稳（比例另由全部锚点解出）
    base_px, base_h = min(
        anchors,
        key=lambda ah: abs(ah[1][0] - tx) + abs(ah[1][1] - ty))

    # ── 远距离：把目标拉进可视区 ──
    for rnd in range(10):
        want = (base_px[0] + (tx - base_h[0]) * W,
                base_px[1] + (ty - base_h[1]) * H)
        if px_reachable(*want):
            log(f"  目标已进入可视区（第 {rnd} 轮）")
            break
        log(f"  [{rnd+1}] 目标像素({want[0]:.0f},{want[1]:.0f})超出可视区 → 滚视野")
        # 退到地图（面板会挡住地图边缘）
        _key("escape")
        time.sleep(1.0)
        edge_scroll(want[0] - WIN_W // 2, want[1] - WIN_H // 2, log=log)
        # 滚动后用一次探针重定基准
        if not s.ensure():
            log("    ⚠ 滚后面板重开失败")
            return False, None
        got, _ = s.probe(400, 640)
        if not got:
            log("    ⚠ 滚后探针失败")
            return False, None
        base_px, base_h = (400, 640), got
        log(f"    滚后基准 {base_px} ↔ {got}")

    # ── 迭代命中 ──
    for i in range(10):
        want = (base_px[0] + (tx - base_h[0]) * W,
                base_px[1] + (ty - base_h[1]) * H)
        if not px_reachable(*want):
            log(f"  [{i+1}] 目标像素({want[0]:.0f},{want[1]:.0f})仍不可达")
            return False, None
        click = (want[0], want[1])
        if _blocked(*click):
            # ★目标被面板挡住：用视野滚动把该格挪进「上带」★
            #   为什么只送上带：把目标的屏幕 y **变小**（上移）需要**向南滚**，
            #   而窗口只有**下边缘**能可靠触发滚动（手册 4.2.5：上边缘被标题栏占用）。
            #   ⇒ 统一把目标送到上带中心 y≈100。
            desire = 100.0
            shift = desire - want[1]          # 负 = 内容需上移 = 向南滚
            log(f"  [{i+1}] 目标被面板遮挡 → 滚视野把该格移入上带 y≈{desire:.0f}"
                f"（需内容位移 {shift:+.0f}px ≈ {abs(shift)/H:.1f} 格）")
            _key("escape")
            time.sleep(1.0)
            _vnc(500, 400)          # ★实测：必须先点一下地图取得焦点，边缘滚动才生效
            time.sleep(0.6)
            # 实测边缘滚动速率 ≈10.5 格/秒；时长按需给，下限 1.5s（0.5s 实测不生效）
            cells = abs(shift) / H
            secs = min(3.5, max(1.8, cells / 10.5))
            edge_scroll(0, 1, log=log, fixed_secs=secs)     # dy>0 → 向南
            if not s.ensure():
                log("    ⚠ 滚后面板重开失败")
                return False, None
            got, _ = s.probe(300, 640)
            if got:
                base_px, base_h = (300, 640), got
                log(f"    滚后基准 {base_px} ↔ {got}")
            continue
        got, alive = s.probe(int(click[0]), int(click[1]))
        log(f"  [{i+1}] 点({click[0]:.0f},{click[1]:.0f}) → 面板 {got}")
        if got is None:
            if not alive:
                log("        面板被关闭 → 重开读回")
                if s.ensure():
                    got = TP.read_panel_hex(tries=3)
                    log(f"        重开面板读回 = {got}")
            if got is None:
                continue
        if got == (tx, ty):
            log("  ✓ 面板确认命中")
            _key("escape")
            time.sleep(0.8)
            return True, got
        base_px, base_h = click, got
        log(f"        修正锚点: ({click[0]:.0f},{click[1]:.0f}) ↔ {got}")
    log("  ✗ 未命中（以结算后读层为准）")
    _key("escape")
    time.sleep(0.8)
    return False, None


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "TF14"
    tx = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    ty = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    ok, h = set_tf_dest(tf, tx, ty)
    print("RESULT", ok, h)
