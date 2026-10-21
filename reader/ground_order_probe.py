#!/usr/bin/env python3
"""ground_order_probe.py — 用界面操作 + 存档字节差分，反推地面部队命令字段偏移。

流程：
  1) 在游戏里按 G 打开地面部队列表，点一个日军单位进详情屏
  2) 截图，OCR 定位 "Select Operations Mode" 与 "Combat Orders" 两行的左箭头
  3) 点一次箭头（循环到下一个选项）
  4) F → 存档到指定槽 → 退出
  5) 对比存档前后 LOCATION 块，列出变化的 (slot, offset, old, new)

用法：
  WITP_VNC_PORT=5901 WITP_DISPLAY=:97 python3 ground_order_probe.py <save_slot> <unit_name_substr>
"""
import os
import struct
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
sys.path.insert(0, WS + "/witp-reader")
DISPLAY = os.environ.get("WITP_DISPLAY", ":97")
PORT = os.environ.get("WITP_VNC_PORT", "5901")
GAME = os.environ.get(
    "WITP_GAME_DIR",
    "/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral's Edition")
SAVE = GAME + "/SAVE"

import witp_core          # noqa: E402
import pwsfile            # noqa: E402
import ctypes             # noqa: E402
import pwsdll as P        # noqa: E402

LOC_SIZE = ctypes.sizeof(P.PWSLocation)


def vnc(x, y, mode="click"):
    env = dict(os.environ, WITP_VNC_PORT=PORT)
    subprocess.run([sys.executable, f"{WS}/witp_vncclick2.py", str(x), str(y), mode],
                   check=False, timeout=60, env=env)
    time.sleep(0.9)


def key(k):
    env = dict(os.environ, WITP_VNC_PORT=PORT)
    subprocess.run([sys.executable, f"{WS}/witp_vnckey2.py", k],
                   check=False, timeout=60, env=env)
    time.sleep(0.6)


def shot(name):
    subprocess.run(["import", "-display", DISPLAY, "-window", "root", name],
                   check=False, timeout=30)
    subprocess.run(["convert", name, "-crop", "1024x768+0+0", "+repage", name],
                   check=False, timeout=30)
    return name


def ocr_words(name):
    subprocess.run(["convert", name, "-resize", "200%", "-colorspace", "Gray",
                    "-normalize", "/tmp/_probe_g.png"], check=False, timeout=30)
    r = subprocess.run(["tesseract", "/tmp/_probe_g.png", "-", "--psm", "11", "tsv"],
                       capture_output=True, text=True, timeout=90,
                       env=dict(os.environ, LANG="C.UTF-8"))
    out = []
    for line in r.stdout.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        out.append({"t": f[11].strip(), "x": int(f[6]) // 2, "y": int(f[7]) // 2,
                    "w": int(f[8]) // 2, "h": int(f[9]) // 2})
    return out


def loc_block(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == LOC_SIZE * 18000:
            return r["data"]
    raise SystemExit("no LOCATION block")


def diff_locs(a, b):
    out = []
    for i in range(len(a) // LOC_SIZE):
        base = i * LOC_SIZE
        if a[base:base + LOC_SIZE] == b[base:base + LOC_SIZE]:
            continue
        for o in range(LOC_SIZE):
            if a[base + o] != b[base + o]:
                out.append((i, o, a[base + o], b[base + o]))
    return out


def main():
    slot = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    name_sub = sys.argv[2] if len(sys.argv) > 2 else "JNAF"

    before = f"{SAVE}/wpae{slot:03d}.pws"
    if not os.path.exists(before):
        raise SystemExit(f"先准备好存档 {before}")
    a = loc_block(before)

    vnc(400, 300)                     # 给地图焦点
    key("g")                          # 地面部队列表
    time.sleep(2)
    img = shot("/tmp/probe_list.png")
    words = ocr_words(img)
    print("[probe] 列表页关键词:", " ".join(w["t"] for w in words)[:200])

    # 找目标单位名（可能被 OCR 拆成多个词，取含子串的行）
    hit = None
    for w in words:
        if name_sub.lower() in w["t"].lower():
            hit = w
            break
    if not hit:
        print("[probe] 未在列表找到目标单位，OCR 全文：")
        print(" ".join(f"{w['t']}@{w['x']},{w['y']}" for w in words)[:1200])
        return 2
    print(f"[probe] 点单位 {hit['t']} @({hit['x']},{hit['y']})")
    vnc(hit["x"], hit["y"])
    time.sleep(2.5)
    img2 = shot("/tmp/probe_detail.png")
    w2 = ocr_words(img2)
    print("[probe] 详情屏关键词:", " ".join(f"{w['t']}@{w['x']},{w['y']}"
                                            for w in w2)[:900])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
