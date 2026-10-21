"""gui_state.py — 读 TF 面板状态（OCR 文字匹配，比颜色计数可靠）

实测（1024x768，TF 面板）：
  · y≈274-282：Retirement 标签行
  · y≈285-293：状态值行（"Retirement Allowed" 或 "Remain on Station"）
  · 放大 355..500 x 270..296 后 tesseract --psm 6 能稳定读出
"""
import subprocess

from PIL import Image

DISPLAY = ":97"


def shot(path="/tmp/_gs.png"):
    subprocess.run(["import", "-window", "root", path], capture_output=True,
                   env={"DISPLAY": DISPLAY, "PATH": "/usr/bin:/bin"})
    return Image.open(path).convert("RGB")


def ocr_region(im, box, scale=4, psm="6"):
    crop = im.crop(box)
    w, h = crop.size
    crop = crop.resize((w * scale, h * scale))
    crop.save("/tmp/_ocr.png")
    r = subprocess.run(["tesseract", "/tmp/_ocr.png", "-", "--psm", psm],
                       capture_output=True, text=True)
    return (r.stdout or "").strip()


def retirement_state(im=None):
    """返回 'allowed' / 'remain' / 'unknown'。

    以 OCR 文本为准：出现 'Remain' → remain；出现 'Allowed'/'Alow' → allowed。
    tesseract 对这套点阵字会漏字，所以用宽松匹配。
    """
    im = im or shot()
    txt = ocr_region(im, (355, 270, 500, 296)).lower()
    if "remain" in txt or "station" in txt:
        return "remain", txt
    if "allow" in txt or "alow" in txt:
        return "allowed", txt
    return "unknown", txt


if __name__ == "__main__":
    st, txt = retirement_state()
    print("retirement =", st)
    print("ocr =", repr(txt))
