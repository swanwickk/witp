#!/usr/bin/env python3
"""
witp_preflight.py — WitP-AE 实例存活强制前置检查（★防"在尸体上调试"★）

为什么需要它
────────────
本工程已**三次**在已崩溃的游戏实例上做测量与调试：
  · 第 1、2 次：边缘滚动 / 视野导航测出"四向全无效"（错的，跑在尸体上）
  · 第 3 次：T 键打不开列表、四种发键方式全部"无效"
    —— 实际是主 exe 已死、X 窗口只是 wineserver 留下的**残影**，
       画面冻结在最后一帧 ⇒ 任何输入都"没有反应"，
       而且截图 md5 恒定 ⇒ 看起来像"输入通道失效"，完全误导。

判据设计
────────
1. 主进程存活：/proc/*/cmdline 精确含 `War in the Pacific Admiral Edition.exe`
   （★不能用 ps comm，会被截断成 15 字符；
     ★必须排除 witprec.exe —— 它常驻且在主 exe 死后可能仍存活）
2. 窗口存在且尺寸 1024x768
3. **画面活性**：间隔 1.5s 取两次窗口截图，md5 应不同
   （游戏主循环每帧都在重绘；若两次完全相同 ⇒ 画面冻结 ⇒ 实体已死）
   ★注意：这条是"活性"而非"输入生效"判据，
     只看输入是否生效会把"静默丢键"和"进程死亡"混为一谈。

用法
────
  from witp_preflight import preflight, assert_alive
  preflight()          # 返回 dict，不抛异常
  assert_alive()       # 不健康直接抛 RuntimeError
"""
import os
import subprocess
import sys
import time
import hashlib

os.environ.setdefault("DISPLAY", ":98")

MAIN_EXE = "War in the Pacific Admiral Edition.exe"
WIN_W, WIN_H = 1024, 768


def _iter_procs():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if not raw:
            continue
        argv = [a for a in raw.split(b"\0") if a]
        yield int(pid), [a.decode(errors="replace") for a in argv]


def find_game_pids():
    """返回主游戏 exe 的 PID 列表（**不含** witprec.exe）。"""
    out = []
    for pid, argv in _iter_procs():
        joined = " ".join(argv)
        if MAIN_EXE in joined and "witprec" not in joined.lower():
            out.append((pid, argv))
    return out


def find_witprec_pids():
    """返回 witprec.exe 的 PID 列表。

    ★★这是本工程最重要的健康判据★★
    ★★重要更正（2026-10-09，实测推翻了先前的假设）★★
    先前我曾断言「witprec 死 ⇒ 主进程变僵尸 ⇒ 输入全失效」，
    **该断言是错的**，已实测推翻：
      · 新实例（run31）在 witprec 已经不在的情况下，
        Esc / T / F 三个按键**全部正常改变画面**，鼠标点击也正常。
      · 也就是说 **witprec.exe 不是游戏运行期必需的常驻进程** ——
        它可能只在特定时机（解码/播放）被拉起，用完即退。
      · 因此 **witprec 存活与否不能作为健康硬闸**，只能作参考信息。

    那「怎么判定实例是真死还是在静置？」→ 用 `probe_alive()`：
    发一个**必定改变画面且可撤销**的输入（T 开编队列表），比对截图 md5。
    地图静置时帧本来就不变（游戏只在有变化时重绘），
    所以「两帧相同」本身**不是**死亡证据；「发了输入仍无变化」才是。
    """
    out = []
    for pid, argv in _iter_procs():
        joined = " ".join(argv)
        if "witprec" in joined.lower():
            out.append((pid, argv))
    return out


def find_window():
    """返回 (win_id, name, w, h) 或 None。"""
    try:
        r = subprocess.run(["xdotool", "search", "--name", "Pacific"],
                           capture_output=True, env=os.environ)
        ids = [x for x in r.stdout.decode().split() if x.strip()]
        if not ids:
            return None
        wid = ids[0]
        nm = subprocess.run(["xdotool", "getwindowname", wid],
                            capture_output=True, env=os.environ).stdout.decode().strip()
        geo = subprocess.run(["xdotool", "getwindowgeometry", "--shell", wid],
                             capture_output=True, env=os.environ).stdout.decode()
        d = {}
        for line in geo.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
        return (wid, nm, int(d.get("WIDTH", 0)), int(d.get("HEIGHT", 0)))
    except Exception:
        return None


def frame_md5(win_id, crop=None):
    """取窗口截图的 md5 缩写。

    ★用 ImageMagick `import`，**不要**用 `xwd | PIL`★
    实测（2026-10-09）：PIL 的 `.open()` **读不了 xwd 导出的原始
    XWD 格式**（`UnidentifiedImageError`）—— 于是 frame_md5 恒返回 None，
    体检报"截图失败，无法判定画面活性"，把真正的僵尸判定为"未知"。
    这是本工具首版自身的 bug，已修。
    ImageMagick 的 `import -window` 直接出 PNG，可靠。
    """
    # ★★v19-107 捕获方式订正（2026-10-09）★★
    #   原用 `import -window <id>` —— 实测 Wine 下它**返回陈旧帧**
    #   （窗口内容已变、md5 却恒定），导致把"活着且已响应"误判为死。
    #   改用 `import -window root -crop 1024x768+0+0`（与 navkeys.fingerprint
    #   同法），该法在大量实测中一直可靠。
    try:
        # 先取得游戏窗口在根窗口中的偏移（本项目固定 (0,0)，但仍动态取）
        ox, oy = 0, 0
        try:
            g = subprocess.run(["xdotool", "getwindowgeometry", "--shell", str(win_id)],
                               capture_output=True, env=os.environ, timeout=10).stdout.decode()
            for line in g.splitlines():
                if line.startswith("X="):
                    ox = int(line[2:])
                elif line.startswith("Y="):
                    oy = int(line[2:])
        except Exception:
            pass
        r = subprocess.run(["import", "-window", "root", "-crop",
                            f"1024x768+{ox}+{oy}", "+repage", "png:-"],
                           capture_output=True, env=os.environ, timeout=20)
    except Exception:
        return None
    if r.returncode != 0 or len(r.stdout) < 1000:
        return None
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    except Exception:
        return None
    if crop:
        im = im.crop(crop)
    return hashlib.md5(im.tobytes()).hexdigest()[:12]


def _vnc_click(px, py):
    """VNC 通道点击（游戏只认 VNC，xdotool 的 XTEST 无效）。"""
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vncclick.py",
                    str(int(px)), str(int(py)), "click"],
                   capture_output=True, env=os.environ)
    time.sleep(0.5)


def _vnc_key(key, pace=0.6):
    """★必须走 VNC 通道★（技能 witp-ae-interface 实测定案）：
    WitP-AE 在 Wine 下**不认 xdotool 的 XTEST 注入事件**
    （输入通道 = Xvnc :98，RFB 端口 5902；`witp_vnckey.py` 直连 RFB 发 KeyEvent）。
    若探针用 xdotool，会在**健康实例**上误报"输入无响应" ⇒ 假阴性。
    """
    subprocess.run(["python3", "/root/.hermes/profiles/witp/workspace/witp_vnckey.py", key],
                   capture_output=True, env=os.environ)
    time.sleep(pace)


def _xdotool_key(wid, key):
    """（保留作为对照/兜底）xdotool 方式。**不要**用于游戏输入探针。"""
    subprocess.run(["xdotool", "windowactivate", str(wid)],
                   capture_output=True, env=os.environ)
    time.sleep(0.6)
    subprocess.run(["xdotool", "key", "--clearmodifiers", key],
                   capture_output=True, env=os.environ)


def probe_alive(win_id, verbose=True):
    """
    ★唯一可靠的实例活性判据★：**输入-响应探针**。

    做法（实测有效，2026-10-09）：
      1. 按 Escape ×2 → 保证回到地图态（幂等）
      2. 记录地图截图 md5
      3. 按 T（必定打开编队列表，画面必然改变）
      4. 再记 md5，比对
      5. 按 Escape 复原
      ⇒ 画面变化 = 活的；画面不变 = 死/挂起

    为什么不看"两帧是否相同"：
      地图静置时游戏**根本不重绘**（只在有变化时刷帧），
      两帧相同是正常的 ⇒ 该判据会把健康实例误判为死亡（本工具首版就犯了这错）。
    为什么不看 witprec：
      witprec 不是运行期常驻进程，它不在时输入照样生效（实测）。
    返回 True/False；截图失败返回 None。
    """
    # ★★v19-105 探针鲁棒化（2026-10-09）★★
    #   原探针：Escape×2 → 记 md5 → 按 T → 记 md5。
    #   实测**假阴性**：某次它报"输入无响应"，但同一实例手工按 T/Esc/Down
    #   **全部有效** —— 假阴性来自两点：
    #     ① 连按两次 Escape 后立刻按 T，第一次 T 可能被吞；
    #     ② Wine 窗口的 `import -window <id>` 偶发截到黑帧，两次 md5 恰好
    #        相同（都是黑帧的哈希）。
    #   修法：先点一下地图取焦点并"唤醒"重绘，然后 **T 最多试两次**，
    #        任一次引起变化即判活。
    def _md5():
        for _ in range(3):
            v = frame_md5(win_id)
            if v is not None:
                return v
            time.sleep(0.6)
        return None

    if _md5() is None:
        return None
    _vnc_click(512, 384)          # 取焦点 + 触发重绘
    time.sleep(1.2)
    base = _md5()
    if base is None:
        return None
    ok = False
    for _try in range(2):
        _vnc_key("t"); time.sleep(2.5)
        after = _md5()
        if after is not None and after != base:
            ok = True
            break
        time.sleep(1.0)
    _vnc_key("escape"); time.sleep(1.5)
    if after is None:
        return None
    if verbose:
        print(f"  输入探针: 静置={base} 按T后={after} → "
              f"{'★输入生效，实例健康★' if ok else '✗ 输入无响应'}")
    return ok


def preflight(live_check=True, gap=1.5, verbose=True):
    """
    返回 dict:
      ok            总体健康
      pids          主 exe PID 列表
      window        (wid,name,w,h) 或 None
      win_ok        窗口尺寸正确
      live          画面在变（None = 未能判定）
      reasons       不健康原因列表
    """
    reasons = []
    pids = find_game_pids()
    wit = find_witprec_pids()
    if not pids:
        reasons.append("主进程不存在（War in the Pacific Admiral Edition.exe 未在 /proc 中找到）")
    win = find_window()
    win_ok = bool(win and win[2] == WIN_W and win[3] == WIN_H)
    if not win:
        reasons.append("找不到游戏窗口")
    elif not win_ok:
        reasons.append(f"窗口尺寸异常 {win[2]}x{win[3]}（应 {WIN_W}x{WIN_H}）")
    elif not pids:
        reasons.append("★窗口存在但主进程已死 ⇒ 这是 wineserver 留下的**残影窗口**"
                       "（画面冻结在最后一帧）")

    live = None
    if live_check and win and not reasons:
        live = probe_alive(win[0], verbose=verbose)
        if live is False:
            reasons.append("★输入探针无响应（按 T 画面不变）⇒ 实例已死/完全挂起，"
                           "禁止在其上做任何测量或操作，必须重启")
        elif live is None:
            print("  ⚠ 输入探针未能判定（截图失败），不作为否决理由")

    ok = (not reasons)
    res = {"ok": ok, "pids": [p for p, _ in pids], "window": win,
           "win_ok": win_ok, "live": live, "reasons": reasons}
    if verbose:
        print("[preflight] " + ("✓ 健康" if ok else "✗ 不健康"))
        print(f"  主进程 PID     : {res['pids'] or '（无）'}")
        print(f"  窗口           : {win}")
        print(f"  画面活性       : {live}")
        for r in reasons:
            print(f"  ✗ {r}")
    return res


def assert_alive():
    res = preflight()
    if not res["ok"]:
        raise RuntimeError("WitP 实例不健康，拒绝继续操作：\n  - " +
                           "\n  - ".join(res["reasons"]))
    return res


if __name__ == "__main__":
    r = preflight()
    sys.exit(0 if r["ok"] else 1)
