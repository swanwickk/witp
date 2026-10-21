"""WitP GUI 备份通道（VNC RFB 注入 + OCR 动态定位 + 固定坐标配方）。

通道层级（2026-10-21 整合；★同日按用户决定修订：T3 放行 OCR）：
  1 直控（/proc/<pid>/mem + 存档解析）—— 主通道，全部工具的默认路径
  2 VNC 单键键盘（E→y 过回合等）—— 直控无法实现的引擎动作
  3 OCR 动态定位 + 固定坐标菜单 —— 备份/恢复通道
    ★ 游戏画面上的元素坐标经常随界面状态变化，固定坐标不可靠；
      T3 允许 OCR（tesseract）在截屏上动态定位文字后点击。
    直控工具（T1）内部仍零 OCR/键鼠。
"""

import os
import socket
import struct
import subprocess
import time

HOST = "127.0.0.1"

KEYSYMS = {
    "Return": 0xFF0D, "Enter": 0xFF0D, "Escape": 0xFF1B, "Tab": 0xFF09,
    "BackSpace": 0xFF08, "space": 0x0020, "Delete": 0xFFFF,
    "Up": 0xFF52, "Down": 0xFF54, "Left": 0xFF51, "Right": 0xFF53,
    "F1": 0xFFBE, "F2": 0xFFBF, "F3": 0xFFC0, "F4": 0xFFC1, "F5": 0xFFC2,
}

# 主菜单固定配方（1024x768 桌面，实测于 :97/:98）
MENU_LOAD = (738, 640)        # 主菜单 LOAD 按钮
MENU_SLOT_AUTOSAVE = (185, 210)  # 存档列表 Autosave 行
MENU_SELECT = (335, 573)      # SELECT 按钮


def vnc_port():
    return int(os.environ.get("WITP_VNC_PORT", "5902"))


def default_display():
    return os.environ.get("WITP_DISPLAY", ":98")


def _connect(port=None):
    s = socket.create_connection((HOST, port or vnc_port()), timeout=10)
    s.sendall(b"RFB 003.008\n")
    buf = b""
    while len(buf) < 12:
        chunk = s.recv(12 - len(buf))
        if not chunk:
            raise ConnectionError("RFB 握手失败")
        buf += chunk
    if not buf.startswith(b"RFB "):
        raise RuntimeError(f"非 RFB 响应: {buf!r}")
    n_types = s.recv(1)[0]
    types = b""
    while len(types) < n_types:
        types += s.recv(n_types - len(types))
    if 1 not in types:
        raise RuntimeError("VNC 不支持 None 认证")
    s.sendall(bytes([1]))
    if buf >= b"RFB 003.008":
        res = b""
        while len(res) < 4:
            res += s.recv(4 - len(res))
        if struct.unpack(">I", res)[0] != 0:
            raise RuntimeError("SecurityResult 非 0")
    s.sendall(bytes([1]))
    head = b""
    while len(head) < 24:
        head += s.recv(24 - len(head))
    name_len = struct.unpack(">I", head[20:24])[0]
    if name_len:
        rest = b""
        while len(rest) < name_len:
            rest += s.recv(name_len - len(rest))
    return s


def vnc_key(name, port=None, hold=0.05):
    """发单个键（keysym 名或单字符）。"""
    sym = KEYSYMS.get(name) or (ord(name) if len(name) == 1 else None)
    if sym is None:
        raise ValueError(f"未知 keysym: {name}")
    s = _connect(port)
    try:
        s.sendall(struct.pack(">BBHI", 4, 1, 0, sym))
        time.sleep(hold)
        s.sendall(struct.pack(">BBHI", 4, 0, 0, sym))
    finally:
        s.close()
    return {"ok": True, "key": name, "port": port or vnc_port()}


def vnc_click(x, y, port=None, settle=1.5):
    """在固定坐标单击（PointerEvent 按下+抬起）。"""
    s = _connect(port)
    try:
        s.sendall(struct.pack(">BBHH", 5, 1, int(x), int(y)))
        time.sleep(0.08)
        s.sendall(struct.pack(">BBHH", 5, 0, int(x), int(y)))
    finally:
        s.close()
    time.sleep(settle)
    return {"ok": True, "click": [int(x), int(y)]}


def screen_md5(display=None):
    """整屏 xwd 的 md5 —— 用于弹框/画面变化判据（非 OCR）。"""
    d = display or default_display()
    p = subprocess.run(["bash", "-c", f"DISPLAY={d} xwd -root -silent | md5sum"],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"xwd 失败: {p.stderr[:200]}")
    return p.stdout.split()[0]


def load_autosave(gap=3.0, use_ocr=True):
    """主菜单载入 Autosave：OCR 动态定位优先，固定坐标兜底。

    ★ 游戏画面坐标会随界面状态变化（2026-10-21 用户决定，T3 放行 OCR）。
    步骤：
      1) LOAD 按钮：OCR 找 "LOAD"，未命中退固定坐标
      2) 存档行：OCR 找 "Autosave" 字样；找不到则解析全部 MM/DD/YY 日期 token，
         点**最新日期**所在行（实测固定行号会点错旧存档）
      3) SELECT 按钮：OCR 找 "SELECT"，未命中退固定坐标
    """
    import re as _re
    steps = []

    def _click_word_or_fixed(word, fixed):
        if use_ocr:
            try:
                r = ocr_click(word, settle=0.5)
                if r.get("ok"):
                    return f"ocr@{r['clicked_at']}(conf={r['conf']})"
            except Exception:
                pass
        vnc_click(*fixed)
        return f"fixed@{list(fixed)}"

    steps.append({"LOAD": _click_word_or_fixed("LOAD", MENU_LOAD)})
    time.sleep(gap)

    # 存档行：优先 "Autosave" 字样；否则最新日期行（日期格式 MM/DD/YY）
    how = "fixed@Autosave（未命中OCR）"
    if use_ocr:
        try:
            words = ocr_words()
            hit = next((w for w in words if "utosave" in w["text"]), None)
            if hit:
                vnc_click(hit["x"], hit["y"])
                how = f"ocr-Autosave@{hit['x']},{hit['y']}"
            else:
                dated = []
                for w in words:
                    m = _re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2})", w["text"])
                    if m:
                        dated.append(((int(m.group(3)), int(m.group(1)),
                                       int(m.group(2))), w))
                if dated:
                    dated.sort(reverse=True)
                    best = dated[0][1]
                    vnc_click(best["x"], best["y"])
                    how = f"ocr-date@{best['x']},{best['y']}({best['text']},conf={best['conf']})"
        except Exception as exc:
            how = f"ocr-error:{exc} → fixed"
        if how.startswith(("fixed", "ocr-error")):
            vnc_click(*MENU_SLOT_AUTOSAVE)
    steps.append({"Autosave": how})
    time.sleep(gap)

    steps.append({"SELECT": _click_word_or_fixed("SELECT", MENU_SELECT)})
    time.sleep(gap)
    return {"ok": True, "steps": steps, "recipe": "OCR优先（最新日期行）+固定坐标兜底"}


# ------------------------------------------------------------------ OCR（T3 动态定位）
def screenshot(display=None, out=None):
    """截屏到 PNG（xwd→convert），返回文件路径。"""
    d = display or default_display()
    out = out or f"/tmp/witp_ocr_{d.strip(':')}_{int(time.time())}.png"
    p = subprocess.run(["bash", "-c",
                        f"DISPLAY={d} xwd -root -silent | convert xwd:- png:'{out}'"],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"截屏失败: {p.stderr[:200]}")
    return out


def ocr_words(display=None, psm=11, png=None):
    """tesseract TSV → [{text,x,y,w,h,conf}]（词级框，屏幕坐标）。"""
    img = png or screenshot(display)
    p = subprocess.run(["tesseract", img, "stdout", "--psm", str(psm), "tsv"],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"tesseract 失败: {p.stderr[:200]}")
    words = []
    for line in p.stdout.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12:
            continue
        text = cols[11].strip()
        if not text or float(cols[10]) < 30:
            continue
        words.append({"text": text,
                      "x": int(cols[6]) + int(cols[8]) // 2,
                      "y": int(cols[7]) + int(cols[9]) // 2,
                      "box": [int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9])],
                      "conf": round(float(cols[10]))})
    return words


def ocr_text(display=None, psm=11, png=None):
    """整屏可读文本（低置信行剔除）。"""
    img = png or screenshot(display)
    p = subprocess.run(["tesseract", img, "stdout", "--psm", str(psm)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"tesseract 失败: {p.stderr[:200]}")
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def ocr_find(needle, display=None, psm=11, threshold=70):
    """在截屏上定位包含 needle 的词，返回全部命中（按置信度排序）。"""
    nd = needle.lower()
    hits = [w for w in ocr_words(display, psm) if nd in w["text"].lower()]
    hits.sort(key=lambda w: -w["conf"])
    return {"ok": bool(hits), "needle": needle,
            "count": len(hits),
            "hits": [{k: w[k] for k in ("text", "x", "y", "box", "conf")} for w in hits[:8]]}


def ocr_click(needle, display=None, occurrence=0, settle=1.5, threshold=70):
    """OCR 定位文字并点击其中心。仅限备份通道。"""
    r = ocr_find(needle, display)
    if not r["hits"]:
        return {"ok": False, "error": f"OCR 未找到 {needle!r}"}
    h = r["hits"][min(occurrence, len(r["hits"]) - 1)]
    c = vnc_click(h["x"], h["y"], settle=settle)
    return {"ok": True, "needle": needle, "clicked_at": [h["x"], h["y"]],
            "word": h["text"], "conf": h["conf"]}


def launch_instance(launcher_script=None, systemd_unit=None):
    """拉起实例（备份通道最外层）：优先脚本，其次 systemd。不等待、不点菜单。"""
    if launcher_script and os.path.exists(launcher_script):
        subprocess.Popen(["bash", str(launcher_script)],
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "via": f"script {launcher_script}"}
    if systemd_unit:
        p = subprocess.run(["systemctl", "start", systemd_unit],
                           capture_output=True, text=True, timeout=60)
        return {"ok": p.returncode == 0, "via": f"systemd {systemd_unit}",
                "stderr": p.stderr[:200]}
    return {"ok": False, "error": "无可用启动器"}
