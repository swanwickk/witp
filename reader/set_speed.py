"""set_speed.py — 通过 GUI 设置 TF 速度档（每步都做存档差分校验）

用法: python3 set_speed.py <tf_num> <0=Cruise|1=Full|2=Max>
"""
import os
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
DISP = os.environ.get("WITP_DISPLAY", ":97")
VNC = os.environ.get("WITP_VNC_PORT", "5901")


def key(k, wait=1.2):
    subprocess.run(["xdotool", "key", k], capture_output=True,
                   env=dict(os.environ, DISPLAY=DISP))
    time.sleep(wait)


def click(x, y, wait=1.2, act="click"):
    subprocess.run(["python3", f"{WS}/witp_vncclick2.py", str(x), str(y), act],
                   capture_output=True, env=dict(os.environ, DISPLAY=DISP))
    time.sleep(wait)


def shot(p="/tmp/_sp.png"):
    subprocess.run(["import", "-window", "root", "-crop", "1024x768+0+0",
                    "+repage", p], capture_output=True,
                   env=dict(os.environ, DISPLAY=DISP))
    return p


def ocr(p="/tmp/_sp.png", psm="6"):
    r = subprocess.run(["tesseract", p, "-", "--psm", psm],
                       capture_output=True, text=True,
                       env=dict(os.environ, LANG="C.UTF-8"))
    return r.stdout


if __name__ == "__main__":
    tf = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    mode = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    shot("/tmp/sp_before.png")
    print("当前画面 OCR:")
    print(ocr("/tmp/sp_before.png", "11")[:600])
