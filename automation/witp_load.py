#!/usr/bin/env python3
"""一键载入 WitP-AE 存档：主菜单 → LOAD A SAVED GAME → 槽位 → 确认。

坐标全部来自 witp_menu.py 的 OCR 实测（2026-09-26）：
  主菜单 LOAD A SAVED GAME ≈ (738,644)   注意主菜单 EXIT GAME ≈ (752,718) 同排！
  存档对话框 槽位 000 行 ≈ (198,211)
  对话框确认按钮 ≈ (348,570)

用法: python3 witp_load.py [槽位行y]     默认 211（即槽位 000）
"""
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
sys.path.insert(0, WS)
import witp_menu as nav  # noqa: E402

SLOT_Y = int(sys.argv[1]) if len(sys.argv) > 1 else 211
MENU_LOAD = (738, 644)
MENU_EXIT = (752, 718)
CONFIRM = (348, 570)


def ocr_screen():
    nav.shot()
    return nav.words()


def main():
    print("[load] 等待主菜单...")
    for i in range(40):
        if nav.shot():
            ws = ocr_screen()
            txt = " ".join(t for t, *_ in ws).upper()
            if "PREFERENCES" in txt or "MAIN MENU SCREEN" in txt:
                print(f"[load] 已到主菜单（{(i+1)*5}s）")
                break
            if "SAVE MENU" in txt or "SAVE GAME" in txt:
                print("[load] 已在存档对话框，跳到选槽")
                break
            if "ALLIED" in txt and "FORECAST" in txt:
                print("[load] 已经在地图（无需载入）")
                return 0
        time.sleep(5)
    else:
        print("[load] ✗ 未等到主菜单")
        return 1

    ws = ocr_screen()
    txt = " ".join(t for t, *_ in ws).upper()
    if "PREFERENCES" in txt or "MAIN MENU SCREEN" in txt:
        # 用 OCR 定位 LOAD A SAVED GAME，找不到才退回实测坐标
        p = nav.find("LOAD A SAVED GAME", ws)
        if not p:
            p = nav.find("LOAD A SAVED", ws)
        if not p:
            # 依次尝试 LOAD / SAVED 两个词的中点
            a = nav.find("LOAD", ws)
            b = nav.find("SAVED", ws)
            p = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) if (a and b) else MENU_LOAD
        # 安全检查：若落点与 EXIT 同行且 x 接近，强制用实测坐标
        if abs(p[1] - MENU_EXIT[1]) < 12:
            print(f"[load] ⚠ OCR 落点 {p} 疑似 EXIT 行，改用实测坐标 {MENU_LOAD}")
            p = MENU_LOAD
        print(f"[load] 点 LOAD A SAVED GAME @ {tuple(round(v) for v in p)}")
        nav.click(p[0], p[1], allow_danger=True)
        time.sleep(5)

    ws = ocr_screen()
    print(f"[load] 当前屏：{nav.screen_name(ws)}")
    print(f"[load] 点槽位行 y={SLOT_Y}")
    nav.click(198, SLOT_Y)
    time.sleep(2)
    print(f"[load] 点确认按钮 {CONFIRM}")
    nav.click(*CONFIRM)
    print("[load] 等待载入...")
    # ★2026-09-29 修正判据★
    #   旧判据 "ALLIED in txt and FORECAST in txt" 会**假成功**——
    #   存档/载入对话框背后仍露出地图顶栏的这两个词，于是对话框开着也被判为
    #   「已回到地图」。现改为：(a) 屏上**不得存在**对话框特征词；
    #   (b) 必须读得到**顶栏日期**（对话框遮挡时读不到）。
    DIALOG_MARKERS = ("SAVED GAMES", "SELECT", "SAVE GAME", "CONTRACT")
    for i in range(12):
        time.sleep(5)
        ws = ocr_screen()
        txt = " ".join(t for t, *_ in ws).upper()
        dlg = any(m in txt for m in DIALOG_MARKERS)
        date = _read_topbar_date()
        if date and not dlg:
            print(f"[load] ✓ 载入完成（{(i+1)*5}s），顶栏日期 = {date}")
            return 0
        if dlg:
            print(f"[load]   ({(i+1)*5}s) 仍在对话框（{date or '无顶栏'}），继续等")
    print("[load] ⚠ 未确认载入完成（未读到顶栏日期或对话框未关闭），请人工核对")
    return 1


def _read_topbar_date():
    """读顶栏日期；对话框遮挡时返回 None。"""
    try:
        import subprocess as _sp
        from PIL import Image as _Im
        p = "/root/.hermes/profiles/witp/workspace/tmp_load_tb.png"
        off = nav.offset() or (0, 0)
        _sp.run(["bash", "-c",
                 f"DISPLAY=:98 import -window root -crop 1024x768"
                 f"+{off[0]}+{off[1]} {p}"], capture_output=True)
        im = _Im.open(p)
        im.crop((560, 2, 1024, 24)).resize((1856, 88)).save(
            "/root/.hermes/profiles/witp/workspace/tmp_load_tb_z.png")
        import sys as _sys
        _sys.path.insert(0, "/root/.hermes/profiles/witp/witp-agent/lib")
        import executor as _ex
        raw = _ex._ocr("/root/.hermes/profiles/witp/workspace/tmp_load_tb_z.png")
        import re as _re
        m = _re.search(r"([A-Z][a-z]{2})\s*(\d{1,2})[.,]\s*(\d{4})", raw)
        return f"{m.group(1)} {m.group(2)}, {m.group(3)}" if m else None
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
