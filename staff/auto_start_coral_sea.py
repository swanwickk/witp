#!/usr/bin/env python3
"""
WitP-AE Automated Scenario Launcher (Coral Sea 1942 - Scenario 003)
Accurately selects Scenario 003 (The Battle of the Coral Sea, 1 May 1942).
Verified coordinates:
- Scenario 003 row: screen(488, 392) / game(300, 242)
- SELECT SCENARIO: screen(524, 720) / game(336, 570)
- START GAME: screen(798, 699) / game(610, 549)
"""
import subprocess
import time
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from lib.executor import vnc_click, vnc_key, close_summaries, focus_map
from lib.perception import capture_state

LAUNCH_SCRIPT = "/root/.hermes/profiles/witp/workspace/witp-launch-en1108.sh"

def check_game_window() -> bool:
    try:
        out = subprocess.check_output(["DISPLAY=:98 xdotool search --name 'War in the Pacific'"], shell=True).decode()
        return bool(out.strip())
    except Exception:
        return False

def _create_new_game_dir(scenario="The Battle of the Coral Sea"):
    """★2026-09-24 新增★ 新开局时创建独立对局目录 games/game-NNN。

    背景：参谋部 _active_game_dir() 按 mtime 取最新目录，若新局没有独立目录，
    因果三元组会被写进上一局的目录（实测第八局 turn_03 写进了 game-007），
    造成跨局记录污染，与早期"网页串话"是同一个坑。
    """
    import re as _re, json as _json, time as _t, os as _os
    games_dir = "/root/.hermes/profiles/witp/witp-agent/games"
    _os.makedirs(games_dir, exist_ok=True)
    # ★2026-10-15 修（编号偏移 059→060、060→061）★
    #   开新局的常见序列是 `witp-cmd new-game` + 本脚本，两者都会建目录
    #   ⇒ 同一局出现两个编号，锚点与归档各指一个。
    #   幂等：若锚点指向的目录是「刚建、无因果记录、未归档」的，直接复用。
    try:
        _anchor = _os.path.join(games_dir, "_current_game")
        if _os.path.exists(_anchor):
            _gid0 = open(_anchor).read().strip()
            _p0 = _os.path.join(games_dir, _gid0)
            _sf0 = _os.path.join(_p0, "summary.json")
            if _gid0 and _os.path.isdir(_p0) and _os.path.exists(_sf0):
                _s0 = _json.load(open(_sf0))
                _fresh = (_t.time() - float(_s0.get("started_at") or 0)) < 300.0
                _n = len([f for f in _os.listdir(_os.path.join(_p0, "causal_log"))
                          if f.startswith("turn_")]) if _os.path.isdir(_os.path.join(_p0, "causal_log")) else 0
                if _fresh and _n == 0 and not _s0.get("outcome"):
                    print("[auto_start] 复用刚创建的对局目录 " + _p0 + "（不重复建局）")
                    return _p0
    except Exception:
        pass

    nums = []
    for d in _os.listdir(games_dir):
        m = _re.match(r"game-(\d+)", d)
        if m and _os.path.isdir(_os.path.join(games_dir, d)):
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    gdir = _os.path.join(games_dir, "game-%03d" % nxt)
    _os.makedirs(_os.path.join(gdir, "causal_log"), exist_ok=True)
    meta = {
        "game_id": "game-%03d" % nxt,
        "scenario": scenario,
        "started_at": _t.time(),
        "started_at_str": _t.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(_os.path.join(gdir, "summary.json"), "w") as f:
        _json.dump(meta, f, ensure_ascii=False, indent=2)
    # ★2026-10-14 新增★ 写「当前对局」锚点，让参谋部整局锁定同一编号。
    #   否则 record-turn/close-game 靠 mtime 猜目录 ⇒ 台账编号错位
    #   （实测同一局被记成 game-048 与 game-049 两行）。
    try:
        with open(_os.path.join(games_dir, "_current_game"), "w") as f:
            f.write("game-%03d\n" % nxt)
    except Exception:
        pass
    print("[auto_start] 已创建新对局目录 " + gdir)
    return gdir


def _kill_stray_game_procs():
    """按 /proc/<pid>/exe 的真实可执行文件名清理游离游戏实例。

    ★为什么不用 pkill -f★ `-f` 匹配完整命令行，会命中**本命令自己**
    （命令行里就含那个 exe 名）⇒ 自残。读 `exe` 符号链接只匹配真正的
    可执行文件，不会误伤 shell。
    返回清掉的个数。
    """
    n = 0
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            exe = os.path.basename(os.readlink(f"/proc/{d}/exe"))
        except Exception:
            continue
        if "Pacific Admiral Edition.exe" in exe or "witprec" in exe:
            try:
                os.kill(int(d), 9)
                n += 1
            except Exception:
                pass
    return n


def _count_wine_procs():
    """当前残留的 wine 相关进程数（用于等待旧实例完全退出）。"""
    n = 0
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            exe = os.path.basename(os.readlink(f"/proc/{d}/exe"))
        except Exception:
            continue
        if any(k in exe for k in ("Pacific Admiral Edition.exe", "witprec",
                                  "wineserver", "winedevice.exe", "services.exe",
                                  "plugplay.exe", "rpcss.exe")):
            n += 1
    return n


def restart_and_launch_coral_sea() -> dict:

    # ★★2026-10-09 重写：必须经 systemd 独立服务启动，且不得用 pkill -f★★
    #   旧实现的两个致命问题：
    #     ① `pkill -9 -f "War in the Pacific Admiral Edition.exe"` ——
    #        `-f` 匹配**完整命令行**，会命中执行这条 pkill 的 shell 自身
    #        （其命令行里含该字符串）⇒ 可能自杀；且本项目已明令禁用 pkill -f。
    #     ② `subprocess.Popen([LAUNCH_SCRIPT])` 从**当前 shell** 拉起游戏 ⇒
    #        游戏落在 `hermes-web-ui.service` 的 cgroup 里，
    #        该服务重启时 systemd 会 SIGKILL 整个 cgroup 把游戏一起杀掉
    #        （即「跑 1.5~3.5 小时必崩」的根因）。launch 自己把这个坑又引入了。
    #    正确做法：先停服务（连 cgroup 一起清），再 `systemctl start` 独立服务。
    print("[auto_start] 停止旧游戏实例（经 systemd，连 cgroup 一起清）...")
    subprocess.run(["systemctl", "stop", "witp-game-en.service"], check=False)
    # ★★2026-10-09 修：必须**等 wine 完全退出**再启★★
    #   实测：`systemctl stop` 后主进程常进入 final-sigterm 超时（要 90s 才 SIGKILL），
    #   若此时立刻 `systemctl start`，新实例会与僵死的旧实例**争抢 X 窗口/前缀**，
    #   表现为新游戏"起来 12 秒后 InitHeap→FreeHeap 自行退出"（不是 cgroup 问题）。
    #   对策：轮询等待——直到既没有服务、也没有任何 wine 进程残留。
    #   ⚠️ 循环里**只等待、不 kill** —— 早先版本在循环内调 `_kill_stray_game_procs()`，
    #      万一循环跑在"新实例已起"之后就会把新实例打死（实测踩过）。
    #   ⚠️ 关键：`systemctl stop` 是**异步**的。实测早先版本第一次判断就读到
    #      `wine残留=0`（/proc 竞态：wine 进程正在退出但短暂不可见），于是立刻 start
    #      ⇒ 新旧实例争抢 X 窗口/前缀 ⇒ 新实例 "InitHeap→FreeHeap" 启动即退。
    #      对策：**最短等待 8s**（让 stop 真正生效）且要求**连续两次读到 0** 才认定清干净。
    time.sleep(8.0)
    _calm = 0
    for _i in range(45):
        subprocess.run(["systemctl", "reset-failed", "witp-game-en.service"],
                       check=False, capture_output=True)
        _act = subprocess.run(["systemctl", "is-active", "witp-game-en.service"],
                              capture_output=True).stdout.decode().strip()
        _wine_left = _count_wine_procs()
        if _act != "active" and _wine_left == 0:
            _calm += 1
            if _calm >= 2:          # 连续两次为 0 才算真干净
                print(f"[auto_start]   ✓ 旧实例已清干净（连续 {_calm} 次为 0）")
                break
        else:
            _calm = 0
        if _i % 4 == 0:
            print(f"[auto_start]   等待旧实例退出… svc={_act} wine残留={_wine_left}")
        time.sleep(2.0)
    else:
        # 超时仍未清干净 ⇒ 兜底强清（此时确定还没有新实例）
        print("[auto_start]   ⚠ 等待超时，强制清理残留 wine 进程")
        _kill_stray_game_procs()
        time.sleep(3.0)
    time.sleep(2.0)

    # 教条#10：开局前清空 SAVE 目录旧存档，防止点 SCENARIO SELECTION 崩溃
    save_dir = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
    import glob as _glob, shutil as _shutil
    old_saves = _glob.glob(os.path.join(save_dir, "*.pws"))
    # ★2026-09-26 新增★ 战报也必须一起清！实测漏了这个会造成**智力污染**：
    #   新局开局后 SAVE 里仍留着上一局的 combatreport_4205xx.txt / aoperationsreport_4205xx.txt，
    #   而读层的"近 6 日"扫描按日期取文件 → 把上一局的战报当成当前情报
    #   （本局第十四局即因此凭空读出"敌航母在 (108,138)"、进而差点把双航母送进一场虚构的航母战斗；
    #    真相是那份战报来自上一局，里面挨打的 Yorktown 在本局其实毫发无伤）。
    old_reports = [p for p in _glob.glob(os.path.join(save_dir, "*.txt"))
                   if any(k in os.path.basename(p) for k in
                          ("combatreport", "aoperationsreport", "joperationsreport",
                           "asigint", "jsigint", "Combat_Events", "CombatEvents",
                           "intel_cache"))]
    if old_saves or old_reports:
        bak_dir = f"/root/.hermes/profiles/witp/workspace/saves_auto_bak_{int(time.time())}"
        os.makedirs(bak_dir, exist_ok=True)
        print(f"[auto_start] 备份并移出 {len(old_saves)} 份旧存档 + "
              f"{len(old_reports)} 份旧战报至 {bak_dir}...")
        for sp in list(old_saves) + list(old_reports):
            try:
                _shutil.move(sp, os.path.join(bak_dir, os.path.basename(sp)))
            except Exception as _e:
                print(f"[auto_start]   ⚠️ 移出失败 {os.path.basename(sp)}: {_e}")

    _create_new_game_dir("The Battle of the Coral Sea")

    print("[auto_start] 经独立 systemd 服务启动游戏（独立 cgroup，免疫 web-ui 重启）...")
    _r = subprocess.run(["systemctl", "start", "witp-game-en.service"],
                        capture_output=True)
    if _r.returncode != 0:
        print(f"[auto_start] ⚠ systemctl start 返回 {_r.returncode}："
              f"{_r.stderr.decode(errors='replace')[:200]}")
        print("[auto_start]   回退：直接跑启动器（注意：会寄生在当前 cgroup）")
        subprocess.Popen([LAUNCH_SCRIPT], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    
    print("[auto_start] Waiting for game window to appear on DISPLAY=:98...")
    window_ready = False
    for _ in range(30):
        time.sleep(1.5)
        _act = subprocess.run(["systemctl", "is-active", "witp-game-en.service"],
                              capture_output=True).stdout.decode().strip()
        if _act == "failed":
            # ★2026-10-09 新增：服务 failed ⇒ 游戏"启动即退"（InitHeap→FreeHeap）
            #   最常见原因是**旧实例未清干净**（新旧争抢）。明确报错，别继续点屏幕。
            return {"ok": False,
                    "error": "witp-game-en.service 已 failed（游戏启动即退）。"
                             "多半是旧实例未清干净；重试 launch 即可。"}
        if check_game_window():
            window_ready = True
            break

    if not window_ready:
        return {"ok": False, "error": "Game window did not appear after launch"}

    # ★启动后健康核验：窗口出现 ≠ 游戏健康（可能仍在启动/已僵）
    time.sleep(5.0)
    _act = subprocess.run(["systemctl", "is-active", "witp-game-en.service"],
                          capture_output=True).stdout.decode().strip()
    if _act != "active":
        return {"ok": False,
                "error": f"启动后服务状态异常（{_act}）——游戏可能已退出"}

    print("[auto_start] Waiting 35s for intro movies to finish and Main Menu to load...")
    time.sleep(35.0)

    # ★2026-09-26 修复★ 连击流程是秒退元凶（对照实验：无点击启动存活 5min+，连击必秒退）。
    #   机理：每次点击强制屏幕重绘，本环境 wined3d 退到软件 blitter
    #   （日志反复 err:d3d:cpu_blitter_blit Failed to blit.），连击把重绘压力堆崩。
    #   改为**每步先截图核验目标屏已出现、再点一下**，并去掉盲点连击关闭简报的循环。
    from lib.executor import _game_shot as _gs, _ocr as _oc

    def _wait_for(keys, label, timeout=60, need_all=True, required=False):
        """轮询等某屏出现。

        ★★2026-10-09 重要订正：默认**仅提示，不中止**★★
        实测：OCR 对同一屏的识别**逐帧波动**（同一张剧本选择屏，我单独测能稳定
        命中 'scenario'/'description'，而 launch 内的 `_wait_for` 却超时）
        —— 用 OCR 做**流程闸门**过于脆弱，会把本来能走通的流程判死。
        证据：launch 报"未进入剧本选择屏"中止，但它点 SCENARIO SELECTION 的
        那次点击**实际生效了**（事后截图确认已在该屏）。
        ⇒ 改为：屏检只作日志提示；流程靠**固定点击序列**推进，
          最后统一用 `required=True` 核验"战术地图"（那一步才是真终点）。
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            if _gs("/tmp/_as.png"):
                txt = _oc("/tmp/_as.png").lower()
                hit = (all(k.lower() in txt for k in keys) if need_all
                       else any(k.lower() in txt for k in keys))
                if hit:
                    print(f"[auto_start] ✓ 已到「{label}」屏（{int(time.time() - t0)}s）")
                    return True
            time.sleep(2.5)
        if required:
            print(f"[auto_start] ✗ 等待「{label}」屏超时（{timeout}s）——必要步骤失败")
        else:
            print(f"[auto_start] ⚠ 未确认「{label}」屏（{timeout}s）——仅提示，继续")
        return False

    # ★★2026-10-09 关键修复：**绝不在主菜单按 Escape**★★
    #   实测（决定性对照实验）：游戏启动 ~45s 时已在**主菜单**；
    #   此时 `vnc_key("escape")` 会被游戏当作**退出**处理 ——
    #   服务立刻 deactivating、窗口消失、日志尾 `FreeHeap`。
    #   这正是"launch 起来 12~40 秒就死"的元凶（此前误判为 cgroup / 时序）。
    #   对策：不按任何键，只**轮询等主菜单文字出现**；出现即直接点按钮。
    #   实测主菜单可读到的词：REALISM OPTIONS / GAME OPTIONS / PREFERENCES /
    #   SCENARIO SELECTION / LOAD A SAVED GAME（OCR psm11 对大字可靠）
    _wait_for(["scenario", "realism", "gamestyle"], "主菜单", 90, need_all=False)

    # ★★2026-10-12 新增第0步：先设 GAMESTYLE（决定人类执哪一方）★★
    #   判决性实验（同一份 wpae000.pws，唯一变量=GAMESTYLE）：
    #     JAPANESE COMPUTER（旋钮默认位）→ 载入/开局后顶栏 = ALLIED PLAYER（人类执盟军）
    #     ALLIED COMPUTER                → 载入/开局后顶栏 = JAPANESE PLAYER（人类执日军）
    #   本函数此前从不设它 ⇒ 一直按默认位开出**盟军**局。
    #   目标阵营由环境变量 WITP_SIDE 指定（japan=人类执日军 → 点 ALLIED COMPUTER），
    #   默认 **japan**（用户要求玩日军）。
    #   坐标由 tesseract tsv 实测词框算得：JAPANESE COMPUTER≈(566,120)、ALLIED COMPUTER≈(660,178)。
    _want = (os.environ.get("WITP_SIDE") or "japan").strip().lower()
    _gs_xy = (660, 178) if _want in ("japan", "japanese") else (566, 120)
    print(f"[auto_start] 第0步 设 GAMESTYLE={_want} @ {_gs_xy}（人类执该方）")
    vnc_click(_gs_xy[0], _gs_xy[1], "click")
    time.sleep(2.0)

    print("[auto_start] 第1步 点 SCENARIO SELECTION (696,575)")
    vnc_click(696, 575, "click")
    time.sleep(4.0)
    #   ★2026-10-09 修判据★ 实测该屏标题是 "SCENARIO MENU"（不是 "select"），
    #   且屏幕内必现 "SCENARIO DESCRIPTION"。旧判据找 "select" 永远不中。
    _wait_for(["scenario", "description"], "剧本选择", 20, need_all=False)

    print("[auto_start] 第2步 选剧本 003 行 (300,239)")
    vnc_click(300, 239, "click")
    time.sleep(4.0)

    print("[auto_start] 第3步 点 SELECT SCENARIO (340,578)")
    vnc_click(340, 578, "click")
    time.sleep(5.0)
    #   ★2026-10-09 修判据★ 该屏有 "START GAME" 按钮；OCR 对 "start game" 两词
    #   组合常因换行拆散，改为找 "start"（need_all=False）并放宽到 60s。
    _wait_for(["start", "difficulty", "scenario"], "剧本详情", 25, need_all=False)

    print("[auto_start] 第4步 点 START GAME (695,525)")
    vnc_click(695, 525, "click")
    time.sleep(8.0)
    #   ★2026-10-09 修判据★ 实测地图屏 OCR 可读到的词：
    #     `ALLIED PLAYER`、`Forecast: Overcast`、基地信息 `Supply:` `Fuel:`
    #   但 OCR **逐帧波动**（同一屏有时读得到、有时读不到），故：
    #     ① 用 5 个候选取 OR（命中任一即算到）；
    #     ② 超时放宽到 180s；
    #     ③ 兜底判据 = 服务仍在 active 且窗口存在（OCR 全失败也不冤杀）。
    _got_map = _wait_for(["allied", "forecast", "supply", "fuel", "moonlight"],
                         "战术地图", 180, need_all=False)
    if not _got_map:
        _act = subprocess.run(["systemctl", "is-active", "witp-game-en.service"],
                              capture_output=True).stdout.decode().strip()
        if _act == "active" and check_game_window():
            print("[auto_start] ⚠ OCR 未确认地图屏，但服务 active + 窗口在 —— "
                  "按成功处理（OCR 逐帧波动，不以它作否决）")
        else:
            return {"ok": False,
                    "error": f"未能进入地图屏（svc={_act}）"}

    print("[auto_start] 进入战术地图，清理可能残留的简报（单次、核验式）")
    vnc_key("escape")
    time.sleep(2.0)
    focus_map()

    print("[auto_start] Refreshing state scraper for Turn 1...")
    try:
        state = capture_state(run_scraper=True)
        turn_date = state.get("turn", {}).get("date", "05/01/42")
        turn_num = state.get("turn", {}).get("turn", 1)
        # ★2026-09-26 修复★ 报成功前必须确认游戏**真的还活着**（进程存在 + 窗口存在）。
        #   旧实现只看抓取结果就报成功；实测游戏秒退时照样打印『successfully running』。
        import subprocess as _sp
        _alive = _sp.run("ps -eo args 2>/dev/null | grep -F "
                         "'War in the Pacific Admiral Edition.exe' | grep -v grep",
                         shell=True, capture_output=True, text=True).stdout.strip()
        _win = _sp.run("DISPLAY=:98 xwininfo -root -children 2>/dev/null | "
                       "grep -cE '102[0-9]x7[0-9][0-9]'",
                       shell=True, capture_output=True, text=True).stdout.strip()
        if not _alive or _win in ("", "0"):
            print(f"[auto_start] ✗ 抓到状态但游戏已不在（进程={'有' if _alive else '无'} 窗口={_win}）"
                  f" —— 判为启动失败，不报成功")
            return {
                "ok": False,
                "turn": turn_num,
                "date": turn_date,
                "scenario": "003 The Battle of the Coral Sea",
                "error": "游戏在启动后消失（Wine 异常退出）；进程或窗口已不存在",
            }
        print(f"[auto_start] Scenario 003 successfully running! Date: {turn_date}, Turn: {turn_num}")
        return {
            "ok": True,
            "turn": turn_num,
            "date": turn_date,
            "scenario": "003 The Battle of the Coral Sea",
            "message": f"Successfully launched Coral Sea 1942 (Turn {turn_num}, {turn_date})"
        }
    except Exception as e:
        # ★2026-09-26 修复★ 旧实现异常时也返回 ok=True 并硬编码「成功」负载 ——
        #   实测 launch 两次都打印『Scenario 003 successfully running!』，而游戏进程随即退出、
        #   SAVE 目录里一个 .pws 都没有。这正是「以为开了其实没开」的源头：异常必须如实报失败。
        return {
            "ok": False,
            "turn": None,
            "date": None,
            "scenario": "003 The Battle of the Coral Sea",
            "error": f"启动流程异常：{e}",
        }

if __name__ == "__main__":
    res = restart_and_launch_coral_sea()
    print("Result:", res)
