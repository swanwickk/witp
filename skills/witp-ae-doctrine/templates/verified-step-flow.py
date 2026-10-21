#!/usr/bin/env python3
"""逐步可核验的启动 / 导航骨架（template —— 复制后只改 INJECT 段即可用）。

为什么需要这个骨架：本环境的 3D 后端会退化到软件 blitter（日志反复
`err:d3d:cpu_blitter_blit Failed to blit`），**连续盲点会把重绘压力堆到它崩**，
表现为「游戏启动后数秒自行退出」。对照实验已确认：不做任何点击则稳定存活数分钟，
走连击流程则必崩（重建显示会话、启用 GLX 均不能解决）。所以凡「启动 → 菜单 → 进图」
这类多步流程，必须满足三条硬约束：

  1. 每一步**先截图 + OCR 确认目标屏已出现**，再点**一次**（不要连点、不要盲点）；
  2. 等不到目标屏就**如实返回 ok=False 并指出卡在哪一步**，绝不盲点下一步；
  3. 报成功前核验**结果本身**（进程存在 + 窗口存在 + 存档已写出），
     不以「我点了 / 抓取没抛错」当回执，更不要在 except 里返回硬编码的成功负载。

用法：把 INJECT-A 段四个函数换成你 harness 里的实现（截图 / OCR / 点击 / 按键），
再按屏幕顺序填 INJECT-B 段的 STEPS，然后 run_flow() → (ok, 卡住的步骤名)。
"""

# ── INJECT-A：换成你 harness 里的实现 ──────────────────────────────
# 注意：CLICK 内部**不要**带重试循环或连点——重试由外层 wait_for_screen 控制。
def SHOT(path):
    """截图到 path，成功返回 True。"""
    raise NotImplementedError("换成 harness 的截图实现")


def OCR(path):
    """返回 path 的全小写 OCR 文本。"""
    raise NotImplementedError("换成 harness 的 OCR 实现")


def CLICK(x, y):
    """单次点击。"""
    raise NotImplementedError("换成 harness 的点击实现")


def KEY(name):
    """单次按键，如 "escape"。"""
    raise NotImplementedError("换成 harness 的按键实现")


# ── INJECT-B：每一步「目标屏特征词 + 该步要做的动作」────────────────
# 特征词取**该屏独有**的词，越独特越不会误判；need_all=True 要求全部出现。
# 屏幕之间必须重新确定坐标，**严禁拿上一屏的坐标点下一屏**（实测会点到退出项）。
STEPS = [
    # (步骤名, 目标屏特征词, need_all, 动作)
    ("主菜单", ["preferences", "scenario"], True, lambda: CLICK(696, 575)),
    ("剧本选择", ["scenario", "select"], False, lambda: CLICK(300, 239)),
    # …按实际屏序继续填；不确定坐标就先跑 OCR 定位再填
]


# ── 以下不需改 ────────────────────────────────────────────────
import time

SETTLE_SECONDS = 3.0   # 点击后给引擎留出重绘时间，再进下一步
POLL_SECONDS = 2.5


def wait_for_screen(path, keys, timeout=60, need_all=True):
    """轮询截图直到目标屏特征词出现。返回 (是否命中, 实际等待秒数)。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if SHOT(path):
            txt = OCR(path) or ""
            low = txt.lower()
            hit = (all(k.lower() in low for k in keys) if need_all
                   else any(k.lower() in low for k in keys))
            if hit:
                return True, int(time.time() - t0)
        time.sleep(POLL_SECONDS)
    return False, timeout


def run_flow(shot_path="/tmp/_step.png", per_step_timeout=60):
    """按 STEPS 逐步核验执行。返回 (ok, 失败原因或空串)。"""
    for name, keys, need_all, act in STEPS:
        ok, waited = wait_for_screen(shot_path, keys, per_step_timeout, need_all)
        if not ok:
            return False, "等待「%s」屏超时（%ss）" % (name, waited)
        act()
        time.sleep(SETTLE_SECONDS)
    return True, ""


if __name__ == "__main__":
    ok, why = run_flow()
    print("OK" if ok else "FAILED: " + why)
