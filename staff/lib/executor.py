"""
WitP-AE Semantic GUI Executor
Provides high-level idempotent commands over RFB/VNC protocol:
- set_tf_destination (probe method)
- set_air_mission
- set_cap_percent
- end_turn
- close_summaries
Ensures the AI agent only operates on semantic orders, automatically handles window offsets (+188, +150).
"""
import subprocess
import time
import os
from typing import Tuple, Dict, Any, Optional

VNC_CLICK = "/root/.hermes/profiles/witp/workspace/witp_vncclick.py"
VNC_KEY = "/root/.hermes/profiles/witp/workspace/witp_vnckey.py"
GAME_SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"

def get_window_offset() -> Tuple[int, int]:
    """
    Dynamically get the Wine window offset in Xvnc framebuffer.

    ★2026-10-04 订正★
    陷阱：`xdotool getwindowgeometry` 报的位置**包含窗口管理器装饰偏移**，
      在 override-redirect 窗口上与真实客户端原点不一致（实测同窗分别报
      751,320 与 563,170）。必须用 `xwininfo` 的 Absolute upper-left，
      它才是可用于坐标换算的客户端原点。
    另：同名幽灵窗口会累积（历次崩溃/重启残留），`search` 取第一个会拿到
      已 unmap 的旧窗口 ⇒ 偏移错乱。改为选**最上层可见**的那个。
    """
    try:
        out = subprocess.check_output(
            ["DISPLAY=:98 xdotool search --name 'War in the Pacific'"],
            shell=True, timeout=5
        ).decode()
        wids = [w for w in out.strip().split("\n") if w.strip()]
        if not wids:
            return 188, 150
        # 取最上层（xdotool 列出顺序不可靠，用 _NET_WM_STATE 无关，改用几何可见性）
        best = None
        for wid in wids:
            try:
                winfo = subprocess.check_output(
                    [f"DISPLAY=:98 xwininfo -id {wid}"],
                    shell=True, timeout=5
                ).decode()
            except Exception:
                continue
            if "Map State: IsViewable" not in winfo:
                continue
            ox = oy = None
            for line in winfo.split("\n"):
                if "Absolute upper-left X:" in line:
                    ox = int(line.split(":")[-1].strip())
                elif "Absolute upper-left Y:" in line:
                    oy = int(line.split(":")[-1].strip())
            if ox is None or oy is None:
                continue
            # 必须完整在屏内（1400x1050），否则坐标会落到屏幕外
            if 0 <= ox and 0 <= oy and ox + 1024 <= 1400 and oy + 768 <= 1050:
                best = (ox, oy)
        if best:
            return best
        # ★★2026-10-09 修：不得静默回退到魔法值 (188,150)★★
        #   实测本环境游戏窗口**恒为 (0,0)**（虚拟桌面 1024x768 + openbox）。
        #   旧代码在"找不到窗口"时返回 (188,150)，于是所有点击被平移
        #   +188/+150 落到错误位置（实测 `vnc_click(696,575)` 实际点 (884,725)），
        #   而**没有任何报错** —— 静默失败的典型。
        #   真实故障（窗口不存在）反而被这个魔法值掩盖了。
        return (0, 0)
    except Exception:
        return (0, 0)

def vnc_click(game_x: int, game_y: int, action: str = "click", steps: int = 1) -> bool:
    """Send mouse click with automatic window offset translation."""
    ox, oy = get_window_offset()
    real_x = game_x + ox
    real_y = game_y + oy
    try:
        subprocess.run(
            ["python3", VNC_CLICK, str(real_x), str(real_y), action, str(steps)],
            check=True, timeout=10
        )
        return True
    except Exception as e:
        print(f"[executor] VNC click error at game({game_x},{game_y}) -> screen({real_x},{real_y}): {e}")
        return False

def vnc_key(*keys: str) -> bool:
    """Send keypresses via RFB protocol."""
    try:
        subprocess.run(["python3", VNC_KEY, *keys], check=True, timeout=10)
        return True
    except Exception as e:
        print(f"[executor] VNC key error {keys}: {e}")
        return False

def focus_map() -> None:
    """Give focus to the tactical map."""
    vnc_click(300, 500, "click")
    time.sleep(0.5)

def check_endgame_screen() -> Optional[str]:
    """Check if the screen is displaying End Game results (Final Score / Victory Level / Draw).

    ★2026-10-15 修（终局漏检 → 一连串假故障）★
      旧实现直接拿 1024×768 原图喂 `tesseract --psm 11`，实测**读不出**
      "VICTORY LEVEL / FINAL SCORE"（与 witp_endgame 当初同一坑）⇒ 恒返回 None。
      后果连锁：终局屏一直挂在屏幕上 → `_mark_game_ended` 从不触发 →
      脚本继续发 E → 被终局屏挡住（ui_state='list'）报"硬闸拦截"、
      autosave 不再更新报"结算超时"，而屏幕上就是写着比分的终局屏。
      修法：与 witp_endgame 统一为**灰度 + autocontrast + 2× 放大**，
      并同时跑 psm 11 与 psm 6 取并集。
    """
    try:
        shot_path = "/tmp/_witp_endgame_check.png"
        subprocess.run(["bash", "-c", f"source /root/.hermes/profiles/witp/workspace/witp-ui.sh && witp_shot_game && cp /tmp/witp_shot.png {shot_path}"], capture_output=True, timeout=10)
        from PIL import Image, ImageOps
        try:
            im = Image.open(shot_path).convert("RGB")
        except Exception:
            return None
        g = ImageOps.autocontrast(ImageOps.grayscale(im))
        g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
        g.save("/tmp/_witp_endgame_up.png")
        txt = ""
        for psm in ("11", "6"):
            r = subprocess.run(["tesseract", "/tmp/_witp_endgame_up.png", "stdout",
                                "--psm", psm], capture_output=True, text=True, timeout=15)
            txt += "\n" + (r.stdout or "")
        up = txt.upper()
        for kw in ["FINAL SCORE", "VICTORY LEVEL", "DECISIVE JAPANESE", "DECISIVE ALLIED", "MARGINAL VICTORY", "DRAW"]:
            if kw in up:
                perm = "/root/.hermes/profiles/witp/workspace/endgame_captured.png"
                subprocess.run(["cp", shot_path, perm], check=False)
                return kw
    except Exception:
        pass
    return None

def close_summaries() -> bool:
    """Dismiss after-action combat/detection summaries back to map."""
    # 若已经是终局画面，禁止盲点
    if check_endgame_screen():
        return True
    for _ in range(4):
        vnc_click(566, 255, "click")
        time.sleep(0.6)
        vnc_key("space")
        time.sleep(0.6)
    vnc_key("escape")
    time.sleep(0.5)
    return True

def _preclear_for_endturn() -> str:
    """
    end-turn 前置清场（2026-10-04 新增，实测依据见 ops-log）。

    症状：TF 列表（T）或 TF 详情面板打开时按 E 无效，再点 (508,422) 也无效，
          引擎不结算、wpae000.pws mtime 不变 → 表现为「回合卡住」。

    正确次序：
      ① 连按 Escape 逐级退出（列表 → 详情面板 → 无）
      ② 判定 ui_state()=='map'（不依赖任何面板）
      ③ 点地图空白 (700,500) 取键盘焦点（T 键被面板抢焦点时必须做）
      ④ 再判定一次 map
    返回可读的清场结果描述，便于 ops-log 留痕。
    """
    try:
        # ★v19-89 导入健壮化★
        #   原写法 `from lib.tfpanel import ...` 要求 **witp-agent 目录本身**
        #   在 sys.path 上（这样 `lib` 才是包）。但调用方（如直接
        #   `python3 -c "import executor"` 或 witp_state）往往只把
        #   `lib/` 加进 sys.path ⇒ 抛 `No module named 'lib.tfpanel'`
        #   ⇒ 前置清场恒失败 ⇒ end-turn 硬闸永远拦截（实测本轮即为该形态）。
        #   现在两条路径都试，任一成功即可。
        try:
            from lib.tfpanel import reset_to_map, ui_state
        except Exception:
            from tfpanel import reset_to_map, ui_state
    except Exception as e:  # pragma: no cover
        return f"跳过(tfpanel 导入失败: {e})"

    try:
        reset_to_map()
    except Exception as e:
        return f"reset_to_map 异常: {e}"

    st = None
    for _ in range(6):
        try:
            st = ui_state()
        except Exception:
            st = None
        if st == "map":
            break
        try:
            vnc_key("Escape")
        except Exception:
            pass
        time.sleep(0.6)

    # 点地图空白取焦点：面板抢焦点时 T/E 键静默失效
    try:
        vnc_click(700, 500, "click")
        time.sleep(0.5)
        st2 = ui_state()
    except Exception:
        st2 = None

    # ★★v19-90 返回状态词，不返回描述串★★
    #   调用方（end_turn 的硬闸）判据是 `cleared != "map"`，
    #   而原实现返回 `f"reset→{st} 焦点后→{st2}"` ⇒ **永远不等于 'map'**
    #   ⇒ 硬闸恒定拦截，E 永远发不出去（实测本轮即此形态：
    #     日志显示 "reset→map 焦点后→map" 明明是干净的 map，却被判为不合格）。
    #   判据必须用**纯状态词**；描述另存便于留痕（放 print 里）。
    final = st2 if st2 is not None else st
    print(f"[executor]   清场轨迹: reset→{st} 焦点后→{st2}  最终={final}")
    return final if final else "?"


def _mark_game_ended(keyword: str = "FINAL SCORE"):
    """★2026-10-15 新增★ 落「本局已结束」标记，供上层自动收尾。

    动机：`end_turn` 检测到终局屏后**会把它关掉**（回主菜单），
    于是调用方事后再检测终局屏就检测不到 → 误以为还没结束 →
    在已终结的游戏上继续发 E → 每次"结算超时"（实测回归局 T10-T12 三次假超时）。
    ⇒ 结束标记必须由**检测到终局的那一次**写入，而不是事后靠屏幕判断。
    """
    import json as _json
    path = "/root/.hermes/profiles/witp/workspace/game_ended.json"
    info = {"ended": True, "keyword": keyword, "ts": time.time()}
    try:
        with open("/root/.hermes/profiles/witp/workspace/endgame_scores.json") as f:
            info.update(_json.load(f))
    except Exception:
        pass
    try:
        with open(path, "w") as f:
            _json.dump(info, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return path


def game_has_ended():
    """返回结束标记 dict（含 keyword/比分）或 None。"""
    import json as _json
    try:
        with open("/root/.hermes/profiles/witp/workspace/game_ended.json") as f:
            d = _json.load(f)
        return d if d.get("ended") else None
    except Exception:
        return None


def end_turn(wait_for_save: bool = True, timeout_sec: int = 300) -> bool:
    """
    Execute end-turn sequence:
    Press 'e' -> Wait -> Confirm YES at game(508, 422) -> Wait for autosave (wpae000.pws).
    """
    # ★2026-10-04 修：前置清场。实测 TF 列表或 TF 详情面板打开时，E 键被面板吞掉，
    #   只点 (508,422) 的 YES 等于空等 → 表现为「E+YES 卡住、存档永不更新」。
    #   正确次序：Escape 逐级关面板 → 确认 ui_state=='map' → 点地图空白取焦点 → E。
    # ★2026-10-04 修（第二轮）：mtime 必须在发 E **之前**记录。
    #   结算很快时 E/YES 后再取 mtime 可能已经拿到新值 → 条件 `cur>init` 永不成立 → 假超时。
    autosave = os.path.join(GAME_SAVE_DIR, "wpae000.pws")
    init_mtime = os.path.getmtime(autosave) if os.path.exists(autosave) else 0

    # ★2026-10-15 新增：本局已结束则短路★
    #   终局屏被关掉后屏幕上看不出已结束，继续发 E 只会无限"超时"。
    ended = game_has_ended()
    if ended:
        print(f"[executor] ⛔ 本局已结束（{ended.get('keyword')}，"
              f"日 {ended.get('JAPANESE')} : 盟 {ended.get('ALLIED')}）"
              f"—— 不再发送 E。请开新局或载入其它存档。")
        return False

    cleared = _preclear_for_endturn()
    print(f"[executor] end-turn 前置清场: {cleared}")

    # ★硬闸：清场结果不是 map 就绝不按 E。
    #   面板未关时 E 被面板吞掉，后面点 (508,422) 是纯空等 → 回合永不推进。
    #   此时必须停下、留证据，让上层重入清场链，而不是盲按。
    if cleared != "map":
        p = _game_shot("/root/.hermes/profiles/witp/workspace/endturn_blocked.png")
        print(f"[executor] ✗ 硬闸拦截：ui_state={cleared!r} 非 'map'，已中止发送 E。")
        print(f"[executor]   截图: {p}  窗口偏移={get_window_offset()}")
        return False

    vnc_key("e")
    time.sleep(3.0)

    # Click confirmation dialog YES button at game(508, 422)
    vnc_click(508, 422, "click")
    time.sleep(2.0)

    if not wait_for_save:
        return True

    print(f"[executor] init_mtime={init_mtime:.3f}")
    print(f"[executor] Waiting for engine resolution to update autosave...")
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        time.sleep(10)
        if os.path.exists(autosave):
            cur_mtime = os.path.getmtime(autosave)
            if cur_mtime > init_mtime:
                print(f"[executor] Engine resolution finished in {int(time.time() - t0)}s!")
                time.sleep(5)
                # 终局保护：若出现终局计分画面，妥善截图并停止盲点
                #   ★2026-10-15：终局屏可能滞后出现，检测重试 3 轮（0/12/18s）
                eg = None
                for _w in (0, 12, 18):
                    if _w:
                        time.sleep(_w)
                    eg = check_endgame_screen()
                    if eg:
                        break
                if eg:
                    print(f"[executor] 🏆 检测到终局结算画面 ({eg})！已捕获终局截图至 /root/.hermes/profiles/witp/workspace/endgame_captured.png")
                    # ★2026-10-15 治本★
                    #   终局屏是**模态等待**：只认鼠标点按钮，Return/Space/Tab/Esc 全无响应，
                    #   主线程在 EXE 0x3cd8xx 定点自旋、画面冻结、存档停写。
                    #   此前这里直接 return True 把屏留着 ⇒ 表现为「游戏卡死/输入全失效」，
                    #   且按钮坐标会随分辨/主题漂移，人工点击常点空。
                    #   正解 = OCR 读出比分并自动点 Quit Game 关闭，回到可载入状态。
                    try:
                        r = subprocess.run(
                            ["/root/.hermes/hermes-agent/venv/bin/python3",
                             "/root/.hermes/profiles/witp/workspace/witp_endgame.py"],
                            capture_output=True, text=True, timeout=120)
                        out = (r.stdout or "").strip().replace("\n", " | ")
                        print(f"[executor] 终局屏自动处理: {out[:400]}")
                    except Exception as _e:
                        print(f"[executor] 终局屏自动处理异常: {_e}")
                    _mark_game_ended(eg)
                    return True
                close_summaries()
                return True
                
    # ★2026-10-15★ 超时最常见的原因就是「结算后停在终局屏」——
    #   终局屏不写 autosave，故 mtime 永不更新 ⇒ 必然走超时分支。
    #   且**终局屏的出现会滞后于结算**（实测：300s 超时那一刻屏幕还没弹窗，
    #   再等十几秒才出现）⇒ 必须**重试检测**，否则漏判、
    #   上层会继续在已结束的游戏上发 E（表现为一连串假超时）。
    for _wait in (0, 15, 20):
        if _wait:
            time.sleep(_wait)
        eg2 = check_endgame_screen()
        if eg2:
            print(f"[executor] 🏆 超时实为终局结算画面 ({eg2})，转终局处理。")
            try:
                r = subprocess.run(
                    ["/root/.hermes/hermes-agent/venv/bin/python3",
                     "/root/.hermes/profiles/witp/workspace/witp_endgame.py"],
                    capture_output=True, text=True, timeout=300)
                print(f"[executor] 终局屏自动处理: {(r.stdout or '').strip()[:400]}")
            except Exception as _e:
                print(f"[executor] 终局屏自动处理异常: {_e}")
            _mark_game_ended(eg2)
            return True

    # ★2026-10-04：超时时必须留全套证据，否则上层无法判断是「没发出去」还是「发出去了没结算」
    p = _game_shot("/root/.hermes/profiles/witp/workspace/endturn_timeout.png")
    print(f"[executor] Warning: Engine resolution timed out.")
    print(f"[executor]   init_mtime={init_mtime:.3f}  now={os.path.getmtime(autosave) if os.path.exists(autosave) else None}")
    print(f"[executor]   screenshot={p}  offset={get_window_offset()}")
    return False

def set_cap_percent(clicks_of_20_pct: int = 4) -> bool:
    """
    Adjust CAP slider in airgroup details.
    Standard CAP button is at game(763, 302).
    """
    for _ in range(clicks_of_20_pct):
        vnc_click(763, 302, "click")
        time.sleep(0.4)
    return True

def _game_shot(path: str) -> bool:
    """抓一张 1024x768 游戏区截图（无名窗口按几何兜底）。"""
    import re as _re
    wid = subprocess.run("xdotool search --name 'War in the Pacific' | head -1",
                         shell=True, capture_output=True, text=True).stdout.strip()
    brd = (0, 0)
    if not wid:
        out = subprocess.run(r"xwininfo -root -children | grep -E '^\s+0x[0-9a-f]+'",
                             shell=True, capture_output=True, text=True).stdout
        for line in out.splitlines():
            m = _re.search(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
            if m and 1020 <= int(m.group(1)) <= 1032 and 764 <= int(m.group(2)) <= 792:
                wid = line.split()[0]
                if int(m.group(1)) > 1024:
                    brd = (1, 20)
                break
    if not wid:
        return False
    info = subprocess.run(f"xwininfo -id {wid}", shell=True, capture_output=True,
                          text=True).stdout
    ox = oy = None
    for l in info.splitlines():
        if "Absolute upper-left X" in l:
            ox = int(l.split()[-1])
        if "Absolute upper-left Y" in l:
            oy = int(l.split()[-1])
    if ox is None or oy is None:
        return False
    ox += brd[0]; oy += brd[1]
    subprocess.run("import -window root /tmp/_ex_full.png", shell=True)
    subprocess.run(f"convert /tmp/_ex_full.png -crop 1024x768+{ox}+{oy} +repage {path}",
                   shell=True)
    return os.path.exists(path)


def _ocr(path: str) -> str:
    subprocess.run(f"convert {path} -resize 200% -colorspace Gray -normalize /tmp/_ex_g.png",
                   shell=True, capture_output=True)
    return subprocess.run("tesseract /tmp/_ex_g.png - --psm 11 2>/dev/null",
                          shell=True, capture_output=True, text=True).stdout


def open_tf_list(retries: int = 3) -> bool:
    """打开编队列表（T 键）。

    ★2026-09-26 加固★ 旧实现只 focus_map() + vnc_key('t') 就 return True，
    实测**经常失败**（按 T 后列表没打开，调用方却以为成功，随后所有坐标点击全落空，
    表现为『无法打开 TF 列表界面』或『落子失败』）。根因是按键焦点丢失。
    现改为：Esc 清场 → 点地图取焦 → 按 T → **截图 OCR 核验列表是否真的打开** → 最多重试 3 次。
    判据：列表顶部会出现 'Mission' / 'Endure' / 'CruiseMode' 这类列头。
    """
    for i in range(max(1, retries)):
        vnc_key("escape")
        time.sleep(0.8)
        vnc_click(512, 400, "click")     # 点地图正中取焦（比 (300,500) 更不容易点到基地/编队）
        time.sleep(1.2)
        vnc_key("t")
        time.sleep(2.5)
        if _game_shot("/tmp/_ex_tf.png"):
            txt = _ocr("/tmp/_ex_tf.png").lower()
            if ("mission" in txt and ("cruise" in txt or "endure" in txt)) or \
               ("task forces" in txt):
                return True
        print(f"[executor] ⚠ 编队列表未打开（第 {i + 1} 次），重试...")
    print("[executor] ✗ 编队列表连续打开失败")
    return False

def open_air_list() -> bool:
    """Open Airgroup list via hotkey 'a'."""
    focus_map()
    vnc_key("a")
    time.sleep(2.0)
    return True

def escape_to_main() -> bool:
    """Close active dialogs/overlays back to map."""
    vnc_key("escape")
    time.sleep(1.0)
    return True
