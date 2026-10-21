"""地图导航闭环（定稿 v2）：把「点击」精确送到任意 hex。

═══ 三条实机确立的事实（第29 局实测，多轮复现）═══
 ① 顶栏 `Hex:` = **上次点击选中的格**（不是鼠标悬停格、不是视野中心）：
      只移动鼠标（xdotool / VNC 都试过）→ 读数恒定；点击地图 → 变为该点击格。
    且点击**不滚动视野** ⇒ 点击 = 往地图上钉钉子，是可靠的绝对探针。
 ② 方向键（**必须走 VNC 通道**）每次平移 **2 格**、可逆。
 ③ 像素↔格 **W≈42、H≈40 px/格**（图像自相关 42/38 与逐点扫描互证）。

═══ 定稿的关键设计（对旧实现"振荡/发散"的解药）═══
 A. **基点只能来自"自己点 + 随后读回"**：绝不能把「当前 hex」绑到某个假定像素
    ——那个 hex 来自上一次点击，位置未知，据此换算会得到屏幕外像素（实测踩过）。
 B. **滚动必须每轮重新标定**：按键次数簿记累加一旦符号/步长有误就发散
    （实测出现「滚动 57 次」「目标像素 4904」）。改为每轮「点固定锚点 → 读回 →
    重算目标像素」，自校正，且顺带验证滚动是否真的生效。
 C. 读数不稳（约 5~10% 的帧）时**原地重试**，不要误判为"位置没变"。
"""
import subprocess

# ★2026-09-28 实测根因★ 工具环境里 DISPLAY **未导出**，导致 `import` 截图
#   静默失败（返回空白/过期图，进而把界面状态判错）。这里统一兜底。
import os as _os
_os.environ.setdefault("DISPLAY", ":98")

import time

from .hexbar import read_hex, get_window_offset

CLICK_X0, CLICK_X1 = 40, 985
CLICK_Y0, CLICK_Y1 = 40, 735
KEY_CELLS = 2
ANCHOR = (512, 384)


def _vnc(px, py, act="click"):
    ox, oy = get_window_offset()
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(ox + px)), str(int(oy + py)), act],
                   capture_output=True)


def _key(name):
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", name],
                   capture_output=True)


class MapNav:
    def __init__(self, W=42.0, H=40.0):
        self.W, self.H = W, H
        self.ax = self.ay = self.hx = self.hy = None      # 锚点像素 ↔ hex
        self.obs = []

    # ── 标定 ──
    def calibrate(self, px=ANCHOR, log=None, retries=3):
        for _ in range(retries):
            _vnc(*px)
            time.sleep(2.3)
            h = read_hex()
            if h:
                self.ax, self.ay, self.hx, self.hy = px[0], px[1], h[0], h[1]
                self.obs.append((px[0], px[1], h[0], h[1]))
                self.learn()
                if log:
                    log(f"  标定 像素({px[0]},{px[1]}) ↔ Hex{h}  "
                        f"W={self.W:.2f} H={self.H:.2f} px/格")
                return h
        return None

    def learn(self):
        """用观测对更新 W/H（中位数，抗离群）。"""
        if len(self.obs) < 2:
            return
        for axis, hi, lo, rng in ((0, 2, 0, (20, 70)), (1, 3, 1, (20, 70))):
            rs = []
            for i in range(len(self.obs)):
                for j in range(i + 1, len(self.obs)):
                    a, b = self.obs[i], self.obs[j]
                    dh, dp = b[hi] - a[hi], b[lo] - a[lo]
                    if dh:
                        r = dp / dh
                        if rng[0] <= abs(r) <= rng[1]:
                            rs.append(abs(r))
            if rs:
                rs.sort()
                med = rs[len(rs) // 2]
                if axis == 0:
                    self.W = med
                else:
                    self.H = med

    def pixel_of(self, tx, ty):
        return (self.ax + (tx - self.hx) * self.W,
                self.ay + (ty - self.hy) * self.H)

    # ── 滚动（每轮重新标定，自校正）──
    def bring_into_view(self, tx, ty, want=ANCHOR, iters=12, log=None):
        for _ in range(iters):
            if self.calibrate(log=None) is None:
                if log:
                    log("  ⚠ 滚动中标定失败")
                return False
            gx, gy = self.pixel_of(tx, ty)
            ex, ey = gx - want[0], gy - want[1]
            nx = int(round(ex / (self.W * KEY_CELLS)))
            ny = int(round(ey / (self.H * KEY_CELLS)))
            if abs(nx) <= 1 and abs(ny) <= 1:
                if log:
                    log(f"  目标格位于像素 ({gx:.0f},{gy:.0f})，已进入可点区")
                return True
            nx = max(-14, min(14, nx))
            ny = max(-14, min(14, ny))
            for _ in range(abs(nx)):
                _key("right" if nx > 0 else "left")
                time.sleep(0.32)
            for _ in range(abs(ny)):
                _key("down" if ny > 0 else "up")
                time.sleep(0.32)
            time.sleep(1.9)
            if log:
                log(f"  滚动 {'right' if nx>0 else 'left'}×{abs(nx)} "
                    f"{'down' if ny>0 else 'up'}×{abs(ny)}"
                    f"（目标当时像素 {gx:.0f},{gy:.0f}）")
        return False

    # ── 闭环点击 ──
    def click_hex(self, tx, ty, attempts=14, log=print, pre_scroll=True):
        """把「点击」精确送到 Hex(tx,ty)。返回 (ok, 末次读数, 轮数)。"""
        if self.ax is None:
            if self.calibrate(log=log) is None:
                log("  ✗ 初始标定失败")
                return False, None, 0
        if pre_scroll:
            self.bring_into_view(tx, ty, log=log)
        cur = (512, 384)
        for i in range(attempts):
            _vnc(*cur)
            time.sleep(2.3)
            h = read_hex()
            if h is None:
                if log:
                    log(f"  [{i+1}] 读数不可靠 → 原地重试")
                continue
            # 用「本次点击像素 ↔ 本次读回 hex」作为新观测（这才是可信配对）
            self.obs.append((cur[0], cur[1], h[0], h[1]))
            self.learn()
            self.ax, self.ay, self.hx, self.hy = cur[0], cur[1], h[0], h[1]
            if h == (tx, ty):
                if log:
                    log(f"  [{i+1}] ✓ 顶栏 Hex = ({tx},{ty}) 精确命中"
                        f"（W={self.W:.2f} H={self.H:.2f} px/格）")
                return True, h, i + 1
            gx, gy = self.pixel_of(tx, ty)
            if not (CLICK_X0 <= gx <= CLICK_X1 and CLICK_Y0 <= gy <= CLICK_Y1):
                if log:
                    log(f"  [{i+1}] 目标像素 ({gx:.0f},{gy:.0f}) 越界 → 重新滚动")
                if not self.bring_into_view(tx, ty, log=log):
                    # 滚动无效则退化为按误差直推（至少继续尝试）
                    gx = cur[0] + (tx - h[0]) * self.W
                    gy = cur[1] + (ty - h[1]) * self.H
                else:
                    gx, gy = self.pixel_of(tx, ty)
            nx = int(round(max(CLICK_X0, min(CLICK_X1, gx))))
            ny = int(round(max(CLICK_Y0, min(CLICK_Y1, gy))))
            if log:
                log(f"  [{i+1}] 点 ({cur[0]},{cur[1]}) → 实得 ({h[0]},{h[1]})"
                    f" 差 ({tx-h[0]:+d},{ty-h[1]:+d}) → 下一击 ({nx},{ny})")
            cur = (nx, ny)
        return False, None, attempts
