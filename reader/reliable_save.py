"""reliable_save.py — 可靠存档（逐步验证版）

教训（实测）：
  1. `f` 键**不能**打开存档框（那是旧版/其他配置的键位）。
     实测有效：点顶部工具栏磁盘图标 (16,16)。
  2. 存档框打开后，鼠标点击**有效**（EXIT (663,547) 能关掉它）。
  3. 槽位行必须点**左侧箭头图标 x≈65**，点 x=200 无效。
  4. 行位置 y = 121 + 16*slot（列表未滚动时）。
  5. SAVE 按钮在 (78,547)。

用法:
  python3 reliable_save.py <slot>          # 存档到指定槽
  python3 reliable_save.py <slot> --dry    # 只打开并报告可见槽位
"""
import glob
import os
import subprocess
import sys
import time

DISP = os.environ.get("WITP_DISPLAY", ":97")
SAVE = None
for c in glob.glob("/root/.wine-witp-mcp/prefix/drive_c/1108r9/*/SAVE") + \
         glob.glob("/root/.wine-witp/drive_c/1108r9/*/SAVE"):
    if os.path.isdir(c):
        SAVE = c
        break

SAVE_BTN = (78, 547)
EXIT_BTN = (663, 547)
ROW_X = 65
FIRST_Y = 121
ROW_H = 16


def sh(cmd, **kw):
    kw.setdefault("text", True)
    return subprocess.run(cmd, capture_output=True,
                          env=dict(os.environ, DISPLAY=DISP), **kw)


def click(x, y, wait=0.9):
    sh(["xdotool", "mousemove", str(x), str(y)])
    time.sleep(0.35)
    sh(["xdotool", "click", "1"])
    time.sleep(wait)


def key(k, wait=0.6):
    sh(["xdotool", "key", k])
    time.sleep(wait)


def shot(p="/tmp/_rs.png"):
    sh(["import", "-window", "root", "-crop", "1024x768+0+0", "+repage", p])
    return p


def ocr_rows(png="/tmp/_rs.png"):
    """OCR 存档列表，返回 {槽号(str): y中心}"""
    r = subprocess.run(["tesseract", png, "-", "--psm", "6", "tsv"],
                       capture_output=True, text=True,
                       env=dict(os.environ, LANG="C.UTF-8", DISPLAY=DISP))
    rows = {}
    for line in (r.stdout or "").splitlines():
        p = line.split("\t")
        if len(p) < 12:
            continue
        t = p[11].strip()
        # 形如 "020" 或 "020—Empty" 或 "o1L—Empty"
        digits = "".join(c for c in t if c.isdigit())
        if len(digits) >= 3 and t[:3].strip() != "":
            try:
                y = int(p[7]) + int(p[9]) // 2
            except ValueError:
                continue
            if 110 < y < 520:
                rows.setdefault(digits[:3].zfill(3), y)
    return rows


def open_save_dialog():
    """关掉可能存在的面板，然后点磁盘图标开存档框。"""
    key("Escape", 1.5)
    click(16, 16, 3.0)
    return shot()


def snap():
    out = {}
    for f in glob.glob(os.path.join(SAVE, "*.pws")):
        st = os.stat(f)
        out[os.path.basename(f)] = (st.st_mtime, st.st_size)
    return out


def save_to(slot, timeout=40):
    slot = f"{int(slot):03d}"
    before = snap()
    open_save_dialog()
    rows = ocr_rows()
    if not rows:
        return None, "OCR 读不到槽号"
    vis = sorted(rows)
    print(f"  可见槽: {vis[0]}..{vis[-1]} (共{len(vis)})")

    # 目标不可见时滚动
    tries = 0
    while slot not in rows and tries < 10:
        mid = vis[len(vis) // 2]
        pg = "Page_Up" if int(slot) < int(mid) else "Page_Down"
        for _ in range(2):
            key(pg, 0.4)
        time.sleep(0.7)
        rows = ocr_rows()
        vis = sorted(rows)
        tries += 1
    if slot not in rows:
        return None, f"槽 {slot} 滚动后仍不可见（可见 {vis[0]}..{vis[-1]}）"

    y = rows[slot]
    print(f"  点槽 {slot} @ ({ROW_X},{y})")
    click(ROW_X, y, 1.2)
    # 点 SAVE
    print(f"  点 SAVE @ {SAVE_BTN}")
    click(*SAVE_BTN, 2.0)
    # 可能弹覆盖确认 → 点 YES
    click(508, 422, 1.5)

    t0 = time.time()
    seen = None
    last = -1
    stable = 0
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        after = snap()
        changed = [k for k, v in after.items() if before.get(k) != v]
        if changed:
            seen = changed[0]
            sz = after[seen][1]
            if sz == last and sz > 100_000:
                stable += 1
                if stable >= 2:
                    # 退出对话框
                    click(*EXIT_BTN, 1.5)
                    return os.path.join(SAVE, seen), f"{sz}B"
            else:
                stable = 0
            last = sz
    return None, f"超时（最后 {seen} {last}B）"


if __name__ == "__main__":
    slot = sys.argv[1] if len(sys.argv) > 1 else "020"
    print("SAVE dir:", SAVE)
    if "--dry" in sys.argv:
        open_save_dialog()
        r = ocr_rows()
        print("可见槽:", sorted(r))
        print("y 位置:", {k: r[k] for k in sorted(r)})
    else:
        p, info = save_to(slot)
        print("结果:", p, info)
