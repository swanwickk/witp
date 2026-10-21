"""guisave.py — 可靠存档 + 自动快照

解决之前反复出现的问题：存到哪个槽不确定、存没存成功不知道。

做法：
  1. 存档前记录 SAVE 目录所有 .pws 的 (mtime, size)
  2. 用 F 键开存档框，按目标槽位的**可见性**定位行（用 OCR 找该槽号所在 y）
  3. 点 SAVE，轮询目录直到出现"新 mtime 的文件"
  4. 报告实际写入的槽位（而不是假设的）
"""
import os
import glob
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
PORT = os.environ.get("WITP_VNC_PORT", "5901")
DISP = os.environ.get("WITP_DISPLAY", ":97")
SAVE = None
for c in glob.glob("/root/.wine-witp-mcp/prefix/drive_c/1108r9/*/SAVE") + \
         glob.glob("/root/.wine-witp/drive_c/1108r9/*/SAVE"):
    if os.path.isdir(c):
        SAVE = c
        break


def sh(cmd, **kw):
    kw.setdefault("text", True)
    return subprocess.run(cmd, capture_output=True,
                          env=dict(os.environ, DISPLAY=DISP), **kw)


def click(x, y, act="click"):
    sh(["python3", f"{WS}/witp_vncclick2.py", str(x), str(y), act])
    time.sleep(0.5)


def key(k):
    sh(["python3", f"{WS}/witp_vnckey2.py", k])
    time.sleep(0.6)


def snap_state():
    out = {}
    for f in glob.glob(os.path.join(SAVE, "*.pws")):
        st = os.stat(f)
        out[os.path.basename(f)] = (st.st_mtime, st.st_size)
    return out


def ocr_rows(png="/tmp/_gs.png", crop=None):
    """OCR 存档列表，返回 {槽号: y中心}"""
    sh(["import", "-window", "root", png])
    if crop:
        sh(["convert", png, "-crop", crop, "+repage", "/tmp/_gs_c.png"])
        png = "/tmp/_gs_c.png"
    r = sh(["tesseract", png, "-", "--psm", "11", "tsv"])
    rows = {}
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        txt = parts[11].strip()
        if len(txt) == 3 and txt.isdigit():
            try:
                y = int(parts[7]) + int(parts[9]) // 2
                rows[txt] = y
            except ValueError:
                pass
    return rows


def do_save(slot, timeout=20):
    """存档到 slot（3 位字符串），返回实际写入的文件名或 None。"""
    before = snap_state()
    key("Escape")
    time.sleep(1.0)
    key("f")
    time.sleep(3.5)

    rows = ocr_rows()
    if not rows:
        print("  ! OCR 没读到槽号")
        return None
    target = f"{int(slot):03d}"
    print(f"  可见槽: {sorted(rows)[:6]} ... {sorted(rows)[-3:] if len(rows)>6 else ''}")

    # 列表滚动：如果目标不在可见范围，先滚动
    tries = 0
    while target not in rows and tries < 12:
        keys = sorted(rows)
        if not keys:
            break
        cur_mid = keys[len(keys) // 2]
        if int(target) < int(cur_mid):
            for _ in range(3):
                key("Page_Up")
            time.sleep(0.8)
        else:
            for _ in range(3):
                key("Page_Down")
            time.sleep(0.8)
        rows = ocr_rows()
        tries += 1

    if target not in rows:
        print(f"  ! 槽 {target} 滚动后仍不可见")
        return None

    y = rows[target]
    click(65, y)          # 行左箭头选中
    time.sleep(0.8)
    click(62, 546)        # SAVE
    t0 = time.time()
    seen = None
    stable = 0
    last_size = -1
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        after = snap_state()
        changed = [k for k, v in after.items() if before.get(k) != v]
        if changed:
            seen = changed[0]
            size = after[seen][1]
            # 等文件大小连续两次不变且 > 100KB，才算写完
            if size == last_size and size > 100_000:
                stable += 1
                if stable >= 2:
                    print(f"  ✓ 写入: {seen}  ({size}B)")
                    return seen
            else:
                stable = 0
            last_size = size
    print(f"  ! 超时（最后见到 {seen} {last_size}B）")
    return None


def do_save_fixed(slot, timeout=25):
    """按固定行距直接算 y（列表未滚动时有效）：y = 123 + 16*slot。"""
    before = snap_state()
    key("Escape")
    time.sleep(1.0)
    key("f")
    time.sleep(3.5)
    y = 123 + 16 * int(slot)
    click(65, y)
    time.sleep(0.8)
    click(62, 546)
    t0 = time.time()
    last = -1
    stable = 0
    seen = None
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        after = snap_state()
        changed = [k for k, v in after.items() if before.get(k) != v]
        if changed:
            seen = changed[0]
            size = after[seen][1]
            if size == last and size > 100_000:
                stable += 1
                if stable >= 2:
                    # 存完退出对话框，回游戏界面
                    click(670, 549)
                    time.sleep(2.0)
                    return seen, size, y
            else:
                stable = 0
            last = size
    return None, last, y


if __name__ == "__main__":
    slot = sys.argv[1] if len(sys.argv) > 1 else "019"
    print("SAVE dir:", SAVE)
    r = do_save_fixed(slot)
    print("result:", r)
