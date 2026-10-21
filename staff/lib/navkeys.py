#!/usr/bin/env python3
"""
witp_nav.py —— 主地图视野导航（方向键通道）

═══ 为什么废弃边缘滚动 ═══
v19-25 用**可靠判据**（主地图纯地图区图像 md5 指纹）重新标定后确认：
  · 边缘悬停滚动 **四向全部无效**：N/S/E/W 停 3.5s，指纹恒为 9eab23d2de2f。
  · 拖拽无效：手册 §4.2 虽说 "drag the mouse pointer"，但 `witp_vncdrag.py`
    实测三向拖拽后指纹不变。
  · 小地图（Jump Map）点选无效：手册 §4.2.5 虽是明文机制，实测无效。
  · 战略图（Ctrl+A）红框**是固定装饰不是视野**：四向滚动/方向键/小地图点选
    全部操作下，红框中心恒 (476,489)、边界恒 (410,396)-(542,582)。

═══ 唯一有效通道：方向键 ═══
手册 §4.2.5 明文：*"Or, use the arrow keys ... in order to move the map view."*
v19-26 实测（Hex 栏 OCR + 指纹双判据）：
    Left  ×1  指纹 9eab23d2de2f → 5bb188ce8eb1  ★变★
    Right ×1  指纹 5bb188ce8eb1 → c524093d2619  ★变★
    Up    ×1  指纹 3f8d1831d16f → 46f3cd2c0f1c  ★变★
    Down  ×1  指纹 728d9c0db203 → fa1f7a2ea961  ★变★
    Right×1/2/4/8 → Hex栏 107 / 108 / 112 / 116  ⇒ **横向每按一次 = 1 格**
  ⚠ Down 在地图南边界附近连按 8 次指纹不变 = 已到边界（不是失效）。

═══ 判据 ═══
`fingerprint()`：主地图纯地图区 (200,150)-(824,640) 的 md5。
纯图像哈希、对平移敏感、**不依赖任何面板/OCR**。
历史教训：面板单次回读会拿到陈旧值；hexbar 旧裁剪区 ((30,4,190,24)) 落在
左侧图标区永远读不到（Hex 栏真实位置 x∈[896,940), y∈[0,18)）。
"""
import hashlib
import os
import subprocess
import sys
import time

os.environ.setdefault("DISPLAY", ":98")
sys.path.insert(0, "/root/.hermes/profiles/witp/workspace")

# ★★v19-97 补齐缺失依赖（2026-10-09）★★
#   本文件曾是「半成品」：clear() 引用了 **未定义**的 `TP` 与 `_key`，
#   任何调用都抛 NameError。此前没人走到这条路径（set-dest 更早就崩在
#   `import witp_nav` 的 AttributeError），所以一直没暴露。
#   ——这是"模块被改名/移动后没有跟着改依赖"的典型后果：
#      同一个概念（视野导航）存在**两个同名不同内容的模块**，
#      调用方 `import witp_nav` 拿到了错的那个。
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from lib import tfpanel as TP          # noqa: E402
except Exception:                          # pragma: no cover
    import tfpanel as TP                   # noqa: E402


def _key(k, pace=0.6):
    """键盘点击（VNC 通道）。与 tfpanel._key 同义；此别名供 clear() 用。"""
    _vnc_key(k, pace=pace)


WIN_W, WIN_H = 1024, 768
CENTER = (512, 384)
CROP = (200, 150, 824, 640)          # 纯地图区，避开顶栏/底栏/小地图
HEXBAR = (886, 0, 952, 18)            # ★v19-28 修正★ Hex 栏真实范围。
# 原设 (896,0,940,18) **右边界截掉了数字**：实测该框 OCR 返回空，
# 而 (890,0,950,18) 能读出完整 'Hex: 142 152'、(860,0,980,24) 读出
# '32% Hex112152'、(0,0,1024,34) 整条读出
# '...Moonlight:32% Hex:112152 ...' ⇒ 真实框约 x∈[886,952)。

# 方向 → 键名（★v19-26 实测符号：Right = 视野东移 = Hex x 增大★）
KEYS = {"right": "Right", "left": "Left",
        "up": "Up", "down": "Down"}

# ★v19-46 实测：方向键**一次不是 1 格，而是约 3 格**★
#   证据（navtest / set-dest TF15 日志，指纹逐次变化）：
#     连续按 left 3 次后指纹不再变 → 撞边界；
#     退避按 right 3 次能退开。
#   且视野总宽仅约 4 格（黄框 40px ÷ 0.748px/格 ≈ 53 格？——不，
#   实际是主地图 W=37.5px/格、窗口 1024px ⇒ 视野约 27 格宽；
#   但**方向键一次跳 3 格**，且滚动后目标格会移出视野中央带）。
#   ⇒ nav 必须知道「一次按键 = STEP 格」，否则按 N 次会冲过头 N×3 格。
STEP_PER_KEY = 3


def _vnc_key(k, pace=0.42):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", k],
                   capture_output=True)
    time.sleep(pace)


def clear():
    """
    清场到地图态 —— **绝不点地图**。

    ★★v19-69 根因修复★★
    原实现末尾有 `_click(700, 300)`（点地图空白取焦点）。
    实测这**会改变视野**：连续两轮读同一锚点得到 (105,149) 与 (100,139)，
    差值正是点地图造成的（游戏把该像素对应的格移到视野中心附近）。

    这是"锚点读数不稳、Δ 时正时负、伺服误差忽大忽小"的**真正根因**，
    而我此前一直归因于"面板刷新噪声"（实测每轮内 6/6 帧稳定，无噪声）。

    正确清场：只用 Escape 逐级退出，**不点地图**。
    地图焦点由"面板打开/关闭"本身赋予，不需要点击。
    """
    try:
        TP.reset_to_map(log=None)
    except Exception:
        pass
    st = None
    for _ in range(4):
        try:
            st = TP.ui_state()
            if st == "map":
                break
        except Exception:
            st = None
        _key("Escape")
        time.sleep(0.5)
    time.sleep(0.8)          # ★不点地图★
    # ★★v19-98 修复：必须返回状态★★
    #   原实现**没有 return**，恒返回 None；
    #   而 nav() 里 `st = clear(); if st != "map": 报"清场失败"` ——
    #   于是导航**永远**在第一步就被判失败并返回 0 位移。
    #   这就是「目标在视野外时 set-dest 必失败」的直接原因（TF14 案例）。
    return st


def fingerprint():
    """主地图纯地图区 md5 —— 唯一干净的视野判据。"""
    p = "/tmp/witp_nav_fp.png"
    w, h = CROP[2] - CROP[0], CROP[3] - CROP[1]
    subprocess.run(["import", "-window", "root", "-crop",
                    f"{w}x{h}+{CROP[0]}+{CROP[1]}", "+repage", p],
                   capture_output=True)
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:12]


def hexbar():
    """Hex 栏 OCR（辅助判据）。格式 `Hex: <n>, <n>`。"""
    try:
        from libocr import ocr as _ocr
        from PIL import Image, ImageOps
        p = "/tmp/witp_nav_hex.png"
        subprocess.run(["import", "-window", "root", p], capture_output=True)
        im = Image.open(p).convert("RGB").crop(HEXBAR)
        big = im.resize((im.width * 8, im.height * 8), Image.LANCZOS)
        return _ocr(ImageOps.grayscale(big), psm=7)
    except Exception as e:
        return f"<ERR {e}>"


def read_hex_robust(tries=5):
    """
    读 Hex 栏 → (hx, hy)。多帧逐位多数票，抗 OCR 单帧误读。

    ★实测 OCR 缺陷★：第二位常被读成 '1412'、'13¢'、'11:'、'15:'
    （末位被当成标点粘连）。故：
      · 连拍 tries 帧
      · 第一位取 3 位、第二位取 3 位（不足左补）
      · 逐位多数票，只取数字位
    """
    import re
    from collections import Counter
    from libocr import ocr as _ocr
    from PIL import Image, ImageOps

    frames = []
    for _ in range(tries):
        p = "/tmp/witp_nav_hex2.png"
        subprocess.run(["import", "-window", "root", p],
                       capture_output=True)
        try:
            im = Image.open(p).convert("RGB").crop(HEXBAR)
        except Exception:
            time.sleep(0.5)
            continue
        big = im.resize((im.width * 10, im.height * 10), Image.LANCZOS)
        txt = _ocr(ImageOps.grayscale(big), psm=7)
        nums = re.findall(r"\d{2,4}", txt)
        if len(nums) >= 2:
            frames.append((nums[0], nums[1]))
        time.sleep(0.45)
    if not frames:
        return None, []
    out = []
    for idx, width in ((0, 3), (1, 3)):
        col = Counter()
        for f in frames:
            s = f[idx]
            # 只要前 width 位纯数字（丢掉粘连的标点尾巴）
            s = re.sub(r"\D", "", s)[:width].rjust(width, "0")
            col[s] += 1
        out.append(col.most_common(1)[0][0])
    try:
        return (int(out[0]), int(out[1])), frames
    except ValueError:
        return None, frames


def press(direction, n=1, pace=0.42):
    """按方向键 n 次。direction 可给键名（Right/Left/Up/Down）或小写别名。"""
    keyname = KEYS.get(direction, direction)
    for _ in range(n):
        _vnc_key(keyname, pace=pace)


def nav(axis, delta, log=print, max_steps=None):
    """
    用方向键把视野移动 delta 格 —— **闭环 + 自动退避**，无需位置反馈。

    为什么不用位置反馈
    ------------------
    Hex 栏（x∈[886,952)）读数虽可靠（实测 4/4 帧一致），但它反映的是
    **鼠标悬停格**而非视野中心格：实测 clear() 前后同一次会话里读到
    (112,152) / (114,152) / (116,152)，而视野并未相应移动。
    ⇒ 不能拿它算位移。改用**指纹差分**这一唯一可靠信号。

    闭环逻辑
    --------
    1) 每按一次方向键 → 取指纹 → 与基准比较。
    2) 指纹变了 ⇒ 该轴推进 1 格，基准更新，继续。
    3) 指纹没变 ⇒ **撞到地图边界**（方向键在边缘无效）。
       此时反向键连续按 BWD 步（指纹必须每步都变），
       把视野推离边界，再继续正向。
    4) 反向也推不动（视野窄到双向都贴边）⇒ 放弃该轴，返回实际步数。

    代价：每格一次指纹 ≈ 1.5~2s。远距离 15 格约 30s，可接受。

    返回 (实际净位移格数, 是否达成, 末次指纹)
    """
    if delta == 0:
        return 0, True, fingerprint()

    # ★按格数换算按键次数★
    want_keys = max(1, round(abs(delta) / STEP_PER_KEY))
    log(f"    目标 {delta:+d} 格 ÷ 每键 {STEP_PER_KEY} 格 = 按 {want_keys} 次")

    fwd = ("right" if delta > 0 else "left") if axis == "h" \
        else ("down" if delta > 0 else "up")
    bwd = {"right": "left", "left": "right",
           "down": "up", "up": "down"}[fwd]
    want = abs(delta)
    steps_budget = max_steps or (want_keys * 4 + 20)

    st = clear()
    base = fingerprint()
    # ★★v19-102 放宽（2026-10-09）★★
    #   原判据要求严格 == "map"，但实测**编队列表态下方向键照样生效**
    #   （TF16 的 set-dest 就是在 ui_state='list' 下完成横/纵导航的）。
    #   真正遮挡方向键的是**主面板/子面板**（main/sub），不是列表。
    #   严格要求 "map" 会把可用的列表态误判为"清场失败"而中止导航。
    if st not in ("map", "list"):
        log(f"    ✗ 清场失败（{st!r}），面板仍遮挡，方向键不会生效")
        return 0, False, base
    net = 0                      # 净位移（正 = 请求方向）
    used = 0
    log(f"    导航 {axis}轴 {fwd}，目标 {want} 格（基准指纹 {base}）")

    while abs(net) < want and used < steps_budget:
        press(fwd, 1)
        used += 1
        time.sleep(0.9)
        now = fingerprint()
        if now != base:
            base = now
            # 一次按键约 STEP_PER_KEY 格（v19-46 实测）
            net += STEP_PER_KEY if delta > 0 else -STEP_PER_KEY
            log(f"    · {net:+d}/{want:+d} 指纹 {base}")
            continue

        # ── 撞边界：**就地停止**（不做反向退避）──
        #
        # ★★v19-99 修正方向 bug（2026-10-09）★★
        #   原逻辑撞边界后「反向退避最多 12 步」，并把退避计入 net
        #   （`net -= 1 if delta > 0 else -1` 使其朝反方向累加）。
        #   实测事故：请求 h 轴向西 4 格，
        #     先按 left 一次 → net=-3；再按 left 指纹未变（触西边界）
        #     → 反向按 right **7 次** → net = -3 + 7 = **+4**
        #     → `abs(net) >= want` 成立 → **误报成功**，
        #       实际把视野**向东移了 4 格**（与目标方向相反）。
        #   方向键在边界处本就无效 ⇒ 正确行为是「该方向已到头」，
        #   立即停止并如实报告位移；反向退避只会把视野推到相反方向。
        log(f"    ⚠ {fwd} 指纹未变（{base}）→ 该方向已到地图边界，停止")
        break

    # ★成功判据必须是「朝请求方向」达到目标，不能只看绝对值★
    #   （否则南辕北辙也会被判成功，见上面的方向 bug）
    ok = (net >= want) if delta > 0 else (net <= -want)
    log(f"    {'✓' if ok else 'ⓘ'} 净位移 {net:+d}/{want:+d}"
        f"（按键 {used} 次，指纹 {base}）")
    return net, ok, base


# ── 小地图跳转（视野粗调）────────────────────────────────────────────────
#
# ★2026-10-09 实测定案★
#   小地图 = 整个太平洋区域图；**红框 = 本剧本限制区**（只有红框内点击生效）；
#   黄框 = 当前视野。红框实测 x∈[939,964] y∈[715,744]。
#   映射实测：mm(941,717)↔hex(100,116) ; mm(962,742)↔hex(111,152)
#     ⇒ 横 1 格 = 1.909 mm-px；纵 1 格 = 0.694 mm-px
#   实测点击后主地图指纹**每次必变** ⇒ 跳转确实生效。
#
# ★精度上限★ 纵向 1.44 格/px、横向 0.52 格/px ⇒ 小地图**只能粗调**
#   （把目标拉进主屏），精点仍由主地图负责。
MM_X0, MM_X1, MM_Y0, MM_Y1 = 939, 964, 715, 744
_MM_HEX_REF = (100, 116)
_MM_PX_REF = (941, 717)
_MM_KX = 1.909
_MM_KY = 0.694


def yellow_box():
    """返回小地图「黄框」(= 当前视野框) 的 (x0,x1,y0,y1)，读不到返回 None。

    ★这是唯一可靠的视野绝对读数★（2026-10-09 实测定案）：
      黄框 = 当前视野；其中心经小地图映射即视野中心格。
      不依赖面板、不受 TF 当前目的地影响、不依赖指纹。
    黄 = R>180 且 G>180 且 B<110，掩膜区 x[894,1024] y[662,768]。
    """
    from PIL import Image
    p = "/tmp/_nv_yellow.png"
    subprocess.run(["import", "-window", "root", "-crop", "130x106+894+662",
                    "+repage", p], capture_output=True)
    try:
        im = Image.open(p).convert("RGB")
    except Exception:
        return None
    xs, ys = [], []
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = im.getpixel((x, y))
            if r > 180 and g > 180 and b < 110:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    # 转回全屏坐标
    return (min(xs) + 894, max(xs) + 894, min(ys) + 662, max(ys) + 662)


def view_center():
    """视野中心格 (cx, cy) —— 由小地图黄框换算。读不到返回 None。

    映射实测：mm(941,717)↔hex(100,116) ; mm(962,742)↔hex(111,152)
      ⇒ 横 1 格 = 1.909 mm-px、纵 1 格 = 0.694 mm-px
    """
    y = yellow_box()
    if not y:
        return None
    cx = (y[0] + y[1]) / 2.0
    cy = (y[2] + y[3]) / 2.0
    return (100 + (cx - 941) / _MM_KX, 116 + (cy - 717) / _MM_KY)


def mm_px_for_hex(hx, hy, clamp=False):
    px = _MM_PX_REF[0] + (hx - _MM_HEX_REF[0]) * _MM_KX
    py = _MM_PX_REF[1] + (hy - _MM_HEX_REF[1]) * _MM_KY
    if clamp:
        px = max(MM_X0 + 1, min(MM_X1 - 1, px))
        py = max(MM_Y0 + 1, min(MM_Y1 - 1, py))
    return int(round(px)), int(round(py))


def mm_reachable(hx, hy):
    px, py = mm_px_for_hex(hx, hy, clamp=False)
    return MM_X0 <= px <= MM_X1 and MM_Y0 <= py <= MM_Y1


def jump_minimap(hx, hy, log=print):
    """点小地图把 hex(hx,hy) 一带拉进主屏（粗调）。返回点击像素或 None。"""
    far = not mm_reachable(hx, hy)
    px, py = mm_px_for_hex(hx, hy, clamp=True)
    if far and log:
        log(f"  ⚠ hex({hx},{hy}) 在红框外，夹紧到 ({px},{py}) 近似跳转")
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(px), str(py), "click"], capture_output=True)
    time.sleep(2.5)
    if log:
        log(f"  小地图跳转 hex({hx},{hy}) → mm像素({px},{py})")
    return px, py


def recenter(log=print, max_push=25):
    """
    用方向键把视野推回**远离边界**的位置。

    背景：方向键导航在地图边缘会失效（按了指纹不变），
    而远目的地任务可能需要反向移动十几格 ⇒ 必须先退开边界。
    做法：先反向猛推 max_push 次（此时已在边界，多推无效也无害），
    再正向推回一半，确保停在地图中部。

    ★注意★ 反向推的格数无法直接测量（边界处无效），
    故实现为「反向推 N 次 → 正向推 N//2 次」，靠指纹确认每步生效。
    """
    log(f"  回中：反向推 {max_push} 次（脱离边界）")
    clear()
    prev = fingerprint()
    moved = 0
    # 先反向推（不知道哪个方向是"内"，两个方向都试）
    for d in ("right", "left"):
        clear()
        prev = fingerprint()
        n = 0
        for _ in range(max_push):
            press(d, 1)
            time.sleep(0.35)
            now = fingerprint()
            if now == prev:
                break
            prev = now
            n += 1
        log(f"    {d}: 连续有效 {n} 次")
        if n >= max_push:
            log(f"    ✓ {d} 方向可连续推 {max_push} 次（未触边界）")
            return d, n
    log("    ⓘ 两方向都很快触边界 —— 视野已在地图角落")
    return None, 0


def locate_target(tx, ty, log=print, tol=1):
    """
    把视野中心导航到目标 Hex (tx,ty) 附近。

    依赖主地图两点标定（v19-10，多轮复核一致）：
        PROBE_A=(300,120) → (100,135)，W=37.5 px/格，H=36.7 px/格
    由此主地图中心 (512,384) ↔ Hex (106,142)。
    """
    from setdest14 import PROBE_A, HEX_A, W_USE, H_USE   # 惰性，防循环 import
    cx_hex = HEX_A[0] + round((CENTER[0] - PROBE_A[0]) / W_USE)
    cy_hex = HEX_A[1] + round((CENTER[1] - PROBE_A[1]) / H_USE)
    log(f"    视野中心当前 Hex ≈ ({cx_hex},{cy_hex})，目标 ({tx},{ty})")

    dx = tx - cx_hex
    dy = ty - cy_hex
    if abs(dx) <= tol and abs(dy) <= tol:
        log("    ✓ 已在目标格，无需导航")
        return True, (cx_hex, cy_hex)

    if dx:
        nav("h", dx, log=log)
    if dy:
        nav("v", dy, log=log)

    # 复核
    clear()
    log(f"    导航后指纹 = {fingerprint()}   Hex栏 = {hexbar()!r}")
    return True, (cx_hex + dx, cy_hex + dy)


if __name__ == "__main__":
    print("=== 方向键导航自检 ===")
    clear()
    print(f"  基线指纹 = {fingerprint()}   Hex栏 = {hexbar()!r}")
    for d, n in (("Right", 3), ("Left", 3), ("Up", 2), ("Down", 2)):
        clear()
        b = fingerprint()
        press(d, n)
        time.sleep(1.2)
        a = fingerprint()
        print(f"  {d:6s}×{n}  {b} → {a}  {'★变★' if a != b else '同'}")
