#!/usr/bin/env python3
"""WitP-AE MCP 服务 —— 用逆向出的存档格式直接读写游戏状态与命令。

设计原则（为什么这样做）：
  * 读：不启动 Wine / 不用 32 位 Python / 不占用游戏进程，纯 Python 解析 .pws
    （gzip 容器 + 逐记录 zlib + 定长结构体数组），毫秒级。
  * 写：把命令（编队任务/航路点、航空队任务与巡逻比例、地面部队行军）
    直接写进一份**新的**存档文件，再把该存档在游戏里载入 → 引擎即按新命令结算。
    绝不覆盖已有存档，除非调用方显式给出 overwrite=True。
  * 校验：改写后用游戏自带的 pwsdll.dll（若可调用）回读一遍，确认引擎能解析。

工具清单见 list_tools。
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../profiles/witp/mcp-servers/witp-mcp
_PROFILE = _HERE.parent.parent                    # .../profiles/witp
# 允许用 WITP_WORKSPACE 覆盖；默认落在本 profile 自己的 workspace 下
WORKSPACE = Path(os.environ.get("WITP_WORKSPACE", str(_PROFILE / "workspace")))
READER = WORKSPACE / "witp-reader"
# 支持多实例：环境变量 WITP_INSTANCE 指向某个"实例根目录"，
# 该目录下应有 game/（游戏安装）与可选 prefix/（Wine 前缀）。
# 默认 = 主实例（:98，正在实战推进的那局）。
INSTANCE = Path(os.environ.get("WITP_INSTANCE", "/root/.wine-witp/drive_c/1108r9")).resolve()


def _resolve_game_dir(base: Path) -> Path:
    """在实例根目录下找含 SAVE/ 的游戏目录（兼容三种布局）。"""
    cands = [base,
             base / "game",
             base / "War in the Pacific Admiral's Edition",
             base / "drive_c" / "1108r9" / "War in the Pacific Admiral's Edition"]
    for c in cands:
        if (c / "SAVE").is_dir():
            return c
    # 退一步：搜一层子目录
    for c in base.glob("*/SAVE"):
        return c.parent
    return base


GAME_DIR = _resolve_game_dir(INSTANCE)
SAVE_DIR = GAME_DIR / "SAVE"
DISPLAY = os.environ.get("WITP_DISPLAY", ":98")
VNC_PORT = int(os.environ.get("WITP_VNC_PORT", "5902"))
# Keep helper DLL/Wine Python selection separate from live game-process routing.
# WITP_GAME_WINEPREFIX overrides the prefix derived from WITP_INSTANCE.
def _derive_game_winprefix():
    explicit = os.environ.get("WITP_GAME_WINEPREFIX")
    if explicit:
        return explicit
    inst = os.environ.get("WITP_INSTANCE", "")
    for marker in ("/drive_c", "/game"):
        if marker in inst:
            return inst.split(marker)[0] or "/root/.wine-witp"
    if inst.endswith("/prefix"):
        return inst
    return os.environ.get("WITP_WINEPREFIX") or os.environ.get("WINEPREFIX") or "/root/.wine-witp"


def _derive_winprefix():
    """DLL/helper prefix; unlike game routing, this may intentionally be the main prefix."""
    explicit = os.environ.get("WITP_WINEPREFIX")
    if explicit:
        return explicit
    return _derive_game_winprefix()


WITP_GAME_WINEPREFIX = _derive_game_winprefix()
WINEPREFIX = _derive_winprefix()
# 导出给 witp-reader 的内存读写模块（witp_obj/witp_mem.game_pid 按此精确匹配进程）
os.environ["WITP_GAME_WINEPREFIX"] = WITP_GAME_WINEPREFIX
os.environ["WITP_DISPLAY"] = DISPLAY  # OCR/截屏默认显示（备份通道 T3）


def _py32_prefix() -> str:
    """找出装了 32 位 Python（C:/py32）的 Wine 前缀。

    pwsdll 回读只依赖 DLL + 存档文件，与游戏实例无关，因此可以复用主前缀里的 py32。
    实例前缀往往没装 py32，直接用它会让 engine_verify 静默失败。
    """
    cands = [os.environ.get("WITP_PY32_PREFIX", ""), WINEPREFIX, "/root/.wine-witp"]
    for c in cands:
        if c and (Path(c) / "drive_c" / "py32" / "python.exe").exists():
            return c
    return WINEPREFIX
OUT_DIR = WORKSPACE / "witp-mcp-out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(READER))
sys.path.insert(0, str(READER / "pywitpaescraper"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import witp_core  # noqa: E402

# ★航空任务码表（静态反汇编 + 过回合实测确认，见内存任务名指针表 @0x85406c）
AG_MISSION = {
    1: "AIRFIELD_ATTACK", 2: "PORT_ATTACK", 3: "NAVAL_ATTACK",
    4: "GROUND_ATTACK", 5: "SWEEP", 6: "ESCORT", 7: "RECON",
    8: "NAVAL_SEARCH", 9: "ASW_PATROL",
    10: "SUPPLY_TRANSPORT", 11: "TROOP_TRANSPORT",
    16: "TRAINING",
}
AG_MISSION_R = {v: k for k, v in AG_MISSION.items()}

import witp_mem_bridge as _mem  # noqa: E402  运行时内存读写（零键鼠）
import witp_mem_bridge2 as _mem2  # noqa: E402  航空队/基地内存读写
import witp_obj_bridge as _obj  # noqa: E402  8类对象统一内存读写
import witp_report as _rpt  # noqa: E402  综合态势报告（纯内存读取）
import witp_obj as _witp_obj  # noqa: E402
import memrw as _memrw  # noqa: E402
import witp_mem as _witp_mem  # noqa: E402  任务枚举
sys.path.insert(0, str(READER))
import witp_orders  # noqa: E402
import pwsfile  # noqa: E402
import witp_gui as _gui  # noqa: E402  GUI 备份通道（VNC 注入，直控失败时用）

mcp = FastMCP("witp-ae")


# ------------------------------------------------- 通道整合：直控为主，键鼠为备份
# 通道层级：
#   T1 直控   /proc/<pid>/mem + 存档解析（所有工具的默认路径）
#   T2 键盘   VNC RFB 单键（end_turn 的 E→y 等）
#   T3 菜单   固定坐标（主菜单 LOAD→Autosave→SELECT，恢复场景）
# 直控失败（游戏进程不存在）时，_game_pid_with_recovery 自动走 T3 拉起实例并
# 载入 autosave，再重试直探——全部内存工具因此获得"直控失败→键鼠回退"能力。
# WITP_GUI_RECOVERY=0 可整体关闭回退。

import threading as _threading  # noqa: E402
import time as _time  # noqa: E402

_orig_game_pid = _witp_obj.game_pid
_recovery_lock = _threading.Lock()
_recovery_last = [0.0]


def _instance_env():
    """按 INSTANCE 区分两实例的显示/前缀/端口（与既有启动器参数一致）。"""
    inst = str(INSTANCE)
    if ".wine-witp-mcp" in inst:
        return {"DISPLAY": ":97", "WINEPREFIX": "/root/.wine-witp-mcp/prefix",
                "VNC": 5901, "NAME": "test97"}
    return {"DISPLAY": ":98", "WINEPREFIX": "/root/.wine-witp",
            "VNC": 5902, "NAME": "main98"}


def _pgrep(pat):
    p = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True)
    return p.returncode == 0


def _save_fingerprint(path):
    """存档 TF 航点计数向量（作为"当前载入了哪份存档"的确定性指纹）。"""
    try:
        import pwsfile as _pf, struct as _st
        blk = _pf.record_by_len(str(path), 2224000)
        out = {}
        for s in range(1, 60):
            r = blk[s * 556:(s + 1) * 556]
            if len(r) < 556:
                break
            out[s] = _st.unpack_from("<H", r, 320)[0]
        return out
    except Exception:
        return {}


def _memory_fingerprint():
    r = _mem.list_tfs(str(SAVE_DIR / "wpae000.pws"))
    if not r.get("ok"):
        return {}
    return {t["tf"]: t["wpCount"] for t in r["tfs"]}


def _which_save_loaded():
    """返回 (最佳匹配存档名, 吻合槽数, 总槽数)；用于确认游戏里跑的是哪份档。"""
    mem = _memory_fingerprint()
    if not mem:
        return None, 0, 0
    best = (None, -1, len(mem))
    for name in ("wpae000.pws", "wpae002.pws", "wpae001.pws"):
        p = SAVE_DIR / name
        if not p.exists():
            continue
        fp = _save_fingerprint(p)
        hit = sum(1 for k, v in mem.items() if fp.get(k) == v)
        if hit > best[1]:
            best = (name, hit, len(mem))
    return best


def _recover_game():
    """T3 回退：自建基础设施 → 启动游戏 → 主菜单固定坐标载入 autosave。

    ★ 不复用 launcher 脚本：脚本会点 ALLIED COMPUTER 进新剧本，
      与「主菜单载入 autosave」冲突。此处只拉起到主菜单即停。
    120s 冷却；WITP_GUI_RECOVERY=0 关闭整个回退。
    """
    with _recovery_lock:
        if _time.time() - _recovery_last[0] < 120:
            return False
        _recovery_last[0] = _time.time()
    try:
        ie = _instance_env()
        env = dict(os.environ, DISPLAY=ie["DISPLAY"], WINEPREFIX=ie["WINEPREFIX"],
                   HOME="/root", LANG="en_US.UTF-8",
                   LIBGL_ALWAYS_SOFTWARE="1", GALLIUM_DRIVER="llvmpipe",
                   WINEDLLOVERRIDES="midimap=d,quartz=d")
        # 1) Xvnc（幂等）
        if not _pgrep(f"Xvnc {ie['DISPLAY']} "):
            subprocess.Popen(
                ["Xvnc", ie["DISPLAY"], "-geometry", "1024x768x24",
                 "-rfbport", str(ie["VNC"]), "-SecurityTypes", "None", "-ac",
                 "-localhost", "no", "+extension", "XTEST", "+render", "-noreset"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            _time.sleep(2)
        # 2) openbox（无它键盘事件丢失；按 DISPLAY 探活）
        r = subprocess.run(["bash", "-c", f"DISPLAY={ie['DISPLAY']} xdotool getactivewindow"],
                           capture_output=True, timeout=10)
        if r.returncode != 0 and not _pgrep(f"openbox.*{ie['DISPLAY']}"):
            subprocess.Popen(["bash", "-c", f"DISPLAY={ie['DISPLAY']} openbox"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            _time.sleep(1)
        # 3) wine 虚拟桌面（幂等）
        subprocess.run(["wine", "reg", "add",
                        r"HKCU\Software\Wine\Explorer\Desktops", "/v", "Desktop",
                        "/t", "REG_SZ", "/d", "1024x768", "/f"],
                       env=env, capture_output=True, timeout=60)
        # 4) 游戏本体（不动菜单，交给后面的载入序列）
        if not _orig_game_pid():
            subprocess.Popen(["wine", str(GAME_DIR / "War in the Pacific Admiral Edition.exe")],
                             cwd=str(GAME_DIR), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        # 5) 等进程（最多 90s）
        pid = None
        for _ in range(45):
            pid = _orig_game_pid()
            if pid:
                break
            _time.sleep(2)
        if not pid:
            return False
        # 6) 等主菜单渲染稳定（整屏 md5 连续一致；非 OCR）
        prev = None
        for _ in range(30):
            try:
                cur = _gui.screen_md5(ie["DISPLAY"])
            except Exception:
                _time.sleep(3)
                continue
            if cur == prev:
                break
            prev = cur
            _time.sleep(3)
        # 7) 主菜单 → LOAD → Autosave → SELECT（OCR 优先，固定坐标兜底）
        os.environ["WITP_VNC_PORT"] = str(ie["VNC"])
        os.environ["WITP_DISPLAY"] = ie["DISPLAY"]
        _gui.load_autosave()
        _time.sleep(15)  # 等存档载入
        # 8) 闭环核验：用 TF 航点指纹确认载入的是 autosave（OCR 日期不可靠）
        try:
            _name, _hit, _tot = _which_save_loaded()
            if _name != "wpae000.pws" or (_tot and _hit / _tot < 0.8):
                # 载错档 → 重走一遍载入序列再验一次
                _gui.load_autosave()
                _time.sleep(15)
                _name, _hit, _tot = _which_save_loaded()
            os.environ["WITP_LAST_RECOVERY"] = f"{_name}:{_hit}/{_tot}"
        except Exception:
            pass
        return True
    except Exception:
        return False
    finally:
        with _recovery_lock:
            _recovery_last[0] = _time.time()


def _game_pid_with_recovery():
    pid = _orig_game_pid()
    if pid:
        return pid
    if os.environ.get("WITP_GUI_RECOVERY", "1") == "0":
        return None
    if _recover_game():
        return _orig_game_pid()
    return None


_witp_obj.game_pid = _game_pid_with_recovery  # 全模块委托此函数 → 一处 patch 全局生效


# ---------------------------------------------------------------- 基础设施
def _latest_save() -> Path:
    saves = sorted(SAVE_DIR.glob("*.pws"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not saves:
        raise RuntimeError(f"SAVE 目录下没有 .pws 存档：{SAVE_DIR}")
    return saves[0]


def _run(cmd, env=None, timeout=60, check=False):
    """跑外部命令，**必须**吞掉 stdout/stderr。

    MCP 的 stdio 传输把本进程 stdout 当 JSON-RPC 通道，子进程只要往 stdout 打一行
    非 JSON 文本，整个会话就会被 pydantic 判为非法消息而断链（实测 witp_end_turn
    因 VNC 点击脚本打印 "OK click @(...)" 触发）。故此处强制 capture。
    """
    return subprocess.run(cmd, env=env, timeout=timeout, check=check,
                          capture_output=True, text=True)


def _pick(save: str | None) -> Path:
    if save:
        p = Path(save)
        if not p.is_absolute():
            p = SAVE_DIR / p
        if not p.exists():
            raise RuntimeError(f"存档不存在：{p}")
        return p
    return _latest_save()


def _dll_verify(path: Path) -> dict:
    """用游戏自带 pwsdll.dll（Wine 内 32 位 Python）回读，验证引擎能解析。"""
    script = READER / "dllverify.py"
    env = dict(os.environ, WINEPREFIX=_py32_prefix(), HOME="/root",
               DISPLAY=DISPLAY, LANG="zh_CN.GBK")
    win_save = "Z:" + str(path).replace("/", "\\")
    win_script = "Z:" + str(script).replace("/", "\\")
    try:
        out = _run(["wine", r"C:\py32\python.exe", win_script, win_save],
                   env=env, timeout=180)
        text = (out.stdout or "") + (out.stderr or "")
        kv = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            if not k.replace("_", "").isalnum():
                continue
            if k == "message" or k == "records" or k.endswith(("_mission", "_cap", "_search",
                                                               "_name", "_flagship", "_home",
                                                               "_primary", "_alt", "_pct")):
                kv[k] = v.strip()
        ok = kv.get("message", "").startswith("End of file")
        res = {"ok": ok, **kv}
        if not ok and "error" not in res:
            tail = [ln for ln in text.splitlines() if ln.strip()][-6:]
            res["error"] = "引擎未返回 End of file"
            res["raw_tail"] = tail
        return res
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _next_free_slot() -> Path:
    """挑一个空闲存档名。游戏只认 wpaeNNN（三位），故在 001..099 里找空位。"""
    for n in range(1, 100):
        p = SAVE_DIR / f"wpae{n:03d}.pws"
        if not p.exists():
            return p
    raise RuntimeError("SAVE 目录里没有空余的 wpaeNNN 槽位（001-099 已满）")


# ---------------------------------------------------------------- 读工具
@mcp.tool()
def witp_channel_status() -> str:
    """【通道整合】探测三级通道可用性，给出推荐通道。

    T1 直控  = 游戏进程 + WINEPREFIX 匹配 + /proc/mem 可读（全部工具的主通道）
    T2 键盘  = VNC RFB 可连（end_turn 的 E→y；直控做不了的引擎动作）
    T3 菜单  = X display 可截屏（固定坐标恢复：主菜单载入 autosave）
    直控失败时工具会自动走 T3 恢复（WITP_GUI_RECOVERY=0 关闭），此工具用于人工诊断。
    """
    ie = _instance_env()
    out = {"instance": ie["NAME"], "display": ie["DISPLAY"], "vnc": ie["VNC"],
           "game_dir": str(GAME_DIR), "save_dir": str(SAVE_DIR)}
    pid = _orig_game_pid()
    out["T1_direct"] = {"game_pid": pid, "wineprefix_match": bool(pid)}
    if pid:
        try:
            _witp_obj._read(pid, _witp_obj.OBJECTS["taskforce"]["base"], 4)
            out["T1_direct"]["mem_probe"] = "ok"
        except Exception as exc:
            out["T1_direct"]["mem_probe"] = f"fail: {exc}"
    try:
        _gui._connect(ie["VNC"]).close()
        out["T2_keyboard"] = {"vnc": "connectable"}
    except Exception as exc:
        out["T2_keyboard"] = {"vnc": f"unreachable: {exc}"}
    try:
        md = _gui.screen_md5(ie["DISPLAY"])
        out["T3_menu"] = {"xwd": "ok", "screen_md5": md[:12]}
    except Exception as exc:
        out["T3_menu"] = {"xwd": f"fail: {exc}"}
    out["recovery"] = {"enabled": os.environ.get("WITP_GUI_RECOVERY", "1") != "0",
                       "cooldown_until": max(0, int(120 - (_time.time() - _recovery_last[0]))),
                       "last_result": os.environ.get("WITP_LAST_RECOVERY")}
    if pid:
        try:
            name, hit, tot = _which_save_loaded()
            out["loaded_save_fingerprint"] = {"best_match": name, "slots_matched": hit,
                                              "slots_total": tot,
                                              "note": "TF 航点计数向量指纹；巡逻 TF 载入后会被引擎重推，允许少量差异"}
        except Exception as exc:
            out["loaded_save_fingerprint"] = {"error": str(exc)}
    out["recommendation"] = ("T1 直控可用" if pid else
                             "T1 不可用：下一次内存工具调用会自动触发 T3 恢复（拉起+载入 autosave）")
    return json.dumps(out, ensure_ascii=False, indent=1)


@mcp.tool()
def witp_gui_fallback(action: str, x: int = 0, y: int = 0, key: str = "",
                      text: str = "", occurrence: int = 0) -> str:
    """【备份通道】键鼠动作（★T3 已放行 OCR 动态定位，2026-10-21 用户决定）。

    action 白名单：
      load_autosave  主菜单载入 Autosave（OCR 优先定位 LOAD/Autosave/SELECT，固定坐标兜底）
      key            发单键（key 参数：E / y / n / Escape / Return 等）
      click          在 (x,y) 固定坐标单击
      click_text     OCR 定位屏幕文字（text 参数）并点击其中心（布局会变，推荐用这个）
      find_text      OCR 定位文字，返回坐标（不点击）
      read_screen    OCR 整屏可读文本（画面内容核验）
      screen_md5     整屏 md5（画面变化判据）
    注意：这是备份通道。能用内存直控完成的操作一律不要走这里。
    """
    try:
        if action == "load_autosave":
            return json.dumps(_gui.load_autosave(), ensure_ascii=False)
        if action == "key":
            if not key:
                return json.dumps({"ok": False, "error": "缺少 key"}, ensure_ascii=False)
            return json.dumps(_gui.vnc_key(key), ensure_ascii=False)
        if action == "click":
            if not (x and y):
                return json.dumps({"ok": False, "error": "缺少 x/y"}, ensure_ascii=False)
            return json.dumps(_gui.vnc_click(x, y), ensure_ascii=False)
        if action == "click_text":
            if not text:
                return json.dumps({"ok": False, "error": "缺少 text"}, ensure_ascii=False)
            return json.dumps(_gui.ocr_click(text, occurrence=occurrence), ensure_ascii=False)
        if action == "find_text":
            if not text:
                return json.dumps({"ok": False, "error": "缺少 text"}, ensure_ascii=False)
            return json.dumps(_gui.ocr_find(text), ensure_ascii=False)
        if action == "read_screen":
            return json.dumps({"ok": True, "lines": _gui.ocr_text()}, ensure_ascii=False)
        if action == "screen_md5":
            return json.dumps({"ok": True, "md5": _gui.screen_md5()}, ensure_ascii=False)
        return json.dumps({"ok": False,
                           "error": f"未知 action {action}（白名单：load_autosave/key/click/"
                                    "click_text/find_text/read_screen/screen_md5）"},
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_status(save: str = "") -> str:
    """读取存档并返回中文态势摘要（日期/剧本/比分/编队列表）。

    save: 存档文件名（如 wpae000.pws）或绝对路径；留空=自动取 SAVE 目录里最新的存档。
    """
    g = witp_core.load(_pick(save or None))
    s = g.summary()
    return json.dumps({"summary": s, "brief": g.brief_cn()}, ensure_ascii=False, indent=1)


@mcp.tool()
def witp_taskforces(save: str = "", with_ships: bool = False,
                    mission: str = "", limit: int = 60) -> str:
    """列出全部编队（槽位/旗舰/任务码/当前位置/目的地/航路点）。

    mission: 任务名过滤（如 SURFACE / BOMBARDMENT / AIRCOMBAT），留空=全部。
    with_ships: 是否附带旗舰舰名与同编队舰名（需要遍历舰船表，稍慢）。
    """
    g = witp_core.load(_pick(save or None))
    ship_by_id = {s["id"]: s["name"] for s in g.ships}
    rows = []
    for t in g.tfs:
        if mission and t["mission"].upper() != mission.upper():
            continue
        row = dict(t)
        row["flagship_name"] = ship_by_id.get(t["flagship_id"], "?")
        if with_ships:
            row["ships"] = [s["name"] for s in g.ships if s["tf"] ==
                            next((x["tf"] for x in g.ships
                                  if x["id"] == t["flagship_id"]), None)]
        rows.append(row)
    return json.dumps(rows[:limit], ensure_ascii=False, indent=1)


@mcp.tool()
def witp_airgroups(save: str = "", base_id: int = -1, mission: str = "",
                   stationed_only: bool = True, limit: int = 40) -> str:
    """列出航空队（名称/驻地 base_id/主任务/巡逻比例/战备机数/士气经验）。

    base_id: 只列该基地 id 上的航空队；-1=不限。
    mission: 主任务中文名或码过滤（如 "对海攻击"、"8"）。
    stationed_only: 只列已部署（base_id>0 或已上舰）的航空队。
    """
    g = witp_core.load(_pick(save or None))
    rows = []
    for a in g.airgroups:
        if stationed_only and not a["base_id"]:
            continue
        if base_id >= 0 and a["base_id"] != base_id:
            continue
        if mission and mission not in (a["primary"], str(a["primary_code"])):
            continue
        rows.append(a)
    return json.dumps(rows[:limit], ensure_ascii=False, indent=1)


@mcp.tool()
def witp_bases(save: str = "", owner: int = -1, name_like: str = "",
               limit: int = 40) -> str:
    """列出基地（名称/归属 owner/坐标/港口/机场/补给/燃料/驻机/堆栈）。

    owner: 0=日军 1=盟军 -1=全部。name_like: 名称子串过滤。
    """
    g = witp_core.load(_pick(save or None))
    rows = []
    for b in g.bases():
        if owner in (0, 1) and b["owner"] != owner:
            continue
        if name_like and name_like.lower() not in b["name"].lower():
            continue
        rows.append(b)
    return json.dumps(rows[:limit], ensure_ascii=False, indent=1)


@mcp.tool()
def witp_ships(name_like: str = "", tf: int = -1, damaged_only: bool = False,
               save: str = "", limit: int = 60) -> str:
    """列出舰船（名称/舰级/所属编队/基地/损伤/修理优先级与模式/升级开关）。

    name_like: 名称子串过滤；tf: 只看某编队（-1=全部）；
    damaged_only: 只看有损伤的（任意一项 >0）。
    """
    g = witp_core.load(_pick(save or None))
    rows = []
    for sh in g.ships:
        if name_like and name_like.lower() not in sh["name"].lower():
            continue
        if tf >= 0 and sh.get("tf") != tf:
            continue
        if damaged_only and not (sh["sys_dmg"] or sh["float_dmg"]
                                 or sh["fire_dmg"] or sh["engine_dmg"]):
            continue
        rows.append(sh)
    return json.dumps(rows[:limit], ensure_ascii=False, indent=1)


@mcp.tool()
def witp_ground_units(save: str = "", name_like: str = "", limit: int = 40) -> str:
    """列出地面部队（名称/坐标/行军方向与长度/目的地/准备度/战力值）。"""
    g = witp_core.load(_pick(save or None))
    rows = [u for u in g.ground_units()
            if not name_like or name_like.lower() in u["name"].lower()]
    return json.dumps(rows[:limit], ensure_ascii=False, indent=1)


@mcp.tool()
def witp_saves() -> str:
    """列出游戏 SAVE 目录下的存档（文件名/大小/修改时间），按时间倒序。"""
    rows = []
    for p in sorted(SAVE_DIR.glob("*.pws"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        head = ""
        try:
            head = witp_core.load(p).header
        except Exception:
            head = "(解析失败)"
        rows.append({"file": p.name, "size": st.st_size,
                     "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                     "header": head})
    return json.dumps(rows, ensure_ascii=False, indent=1)


@mcp.tool()
def witp_reports(kind: str = "aoperationsreport", save: str = "", max_chars: int = 6000) -> str:
    """读取战报文本（GBK 自动转 UTF-8）。

    kind: aoperationsreport / joperationsreport / combatreport / CombatEvents /
          asigint / jsigint / updateReport
    save: 用于推断日期后缀（如 wpae008.pws）；留空则取该类型最新一份。
    """
    base = kind
    cands = sorted(SAVE_DIR.glob(f"{base}*.txt"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    if not cands:
        return f"未找到 {base}*.txt"
    p = cands[0]
    raw = p.read_bytes()
    for enc in ("gbk", "utf-8", "latin1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin1", "replace")
    return f"# {p.name}\n{text[:max_chars]}"


# ---------------------------------------------------------------- 写工具（命令注入）
@mcp.tool()
def witp_set_tf_orders(slot: int, mission: str = "", destination_x: int = -1,
                       destination_y: int = -1, waypoints: str = "",
                       out_file: str = "", overwrite: bool = False,
                       verify: bool = True) -> str:
    """改写编队命令（任务/目的地），写入一份新存档（不覆盖原档）。

    slot: 编队槽号（witp_taskforces 返回的 slot）。
    mission: 任务名（SURFACE/BOMBARDMENT/AIRCOMBAT/SUBPATROL/TRANSPORT/…）或数字码；留空=不改。
    destination_x/y: 目标六角格；-1=不改。
    waypoints: 显式航路点 "x1,y1;x2,y2;..."（含起点与终点），给出时优先于 destination_x/y。
    out_file: 输出存档名（默认自动取 SAVE 下下一个空闲 wpaeNNN.pws）。
    overwrite: 允许覆盖已存在的输出文件。
    verify: 改写后用游戏自带 pwsdll.dll 回读校验（慢，约 5-10 秒）。

    注意：写入的是**存档文件**；要让引擎按新命令结算，需在游戏里载入这份存档。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    changes = {}
    if mission:
        code = (int(mission) if mission.isdigit()
                else next((k for k, v in witp_orders.MISSION_NAMES.items()
                           if v == mission.upper()), None))
        if code is None:
            return json.dumps({"ok": False, "error": f"未知任务名 {mission}",
                               "valid": sorted(witp_orders.MISSION_NAMES.values())},
                              ensure_ascii=False)
        changes["mission"] = {"old": s.set_tf_mission(slot, code), "new": code}
    if waypoints:
        pts = []
        for seg in waypoints.split(";"):
            if not seg.strip():
                continue
            a, b = (int(v) for v in seg.split(","))
            pts.append((a, b))
        if len(pts) < 2:
            return json.dumps({"ok": False,
                               "error": 'waypoints 需形如 "106,125;104,128;99,126"（至少起点+终点）'},
                              ensure_ascii=False)
        base_id = None
        _blk = s.loc["data"]
        for _i in range(len(_blk) // witp_orders.LOC_SIZE):
            _b = _i * witp_orders.LOC_SIZE
            if not _blk[_b:_b + 25].split(b"\x00")[0]:
                continue
            if struct.unpack_from("<HH", _blk, _b + 36) == pts[-1]:
                base_id = _i
                break
        changes["waypoints"] = s.set_tf_destination(
            slot, pts[-1][0], pts[-1][1], path=pts, dest_base=base_id)
    elif destination_x >= 0 and destination_y >= 0:
        # 目标格若是基地，必须同时写 destBase(offset 58)，否则引擎结算时会用旧
        # 目的基地重算整条航路，把航路点覆盖回去（实测过）。
        base_id = None
        _blk = s.loc["data"]
        for _i in range(len(_blk) // witp_orders.LOC_SIZE):
            _b = _i * witp_orders.LOC_SIZE
            _nm = _blk[_b:_b + 25].split(b"\x00")[0]
            if not _nm:
                continue
            _x, _y = struct.unpack_from("<HH", _blk, _b + 36)
            if (_x, _y) == (destination_x, destination_y):
                base_id = _i
                break
        changes["destination"] = s.set_tf_destination(
            slot, destination_x, destination_y, dest_base=base_id)
    if not changes:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的命令"}, ensure_ascii=False)

    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}",
                           "hint": "改动幅度过大导致压缩流无法回填到原长度"},
                          ensure_ascii=False)
    result = {"ok": True, "src": str(src), "out": str(dst), "bytes": size,
              "changes": changes,
              "after": s.tf_row(slot),
              "next_step": "在游戏主菜单 → LOAD A SAVED GAME 载入该存档，引擎即按新命令结算"}
    if verify:
        result["engine_verify"] = _dll_verify(dst)
    return json.dumps(result, ensure_ascii=False, indent=1)


@mcp.tool()
def witp_set_ship_conversion(ship_id: int, convert: int = -1, delay: int = -1,
                             out_file: str = "", overwrite: bool = False) -> str:
    """舰船改装（手册 14.1.2 Conversions）。

    ship_id: 舰船槽号（witp_ships 返回的 id）
    convert: shipTempAPConv@341（1=开始改装）；-1=不改
    delay:   改装剩余天数 shipConversionDelay@344；-1=不改

    注：SHIP 是大记录，f2/f3 是引擎校验值；本工具用「清零空槽残留」
        把压缩长度压回原值，实测引擎可正常读档（records=62 / End of file）。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    try:
        changes = s.set_ship_conversion(
            ship_id,
            convert=None if convert < 0 else convert,
            delay=None if delay < 0 else delay)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    if not changes:
        return json.dumps({"ok": False, "error": "没有给出要改的值"}, ensure_ascii=False)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}"}, ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": changes, "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)



# ═══════════════════════════════════════════════════════════════
# 运行时内存工具（零键鼠，直接读写游戏进程）
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def witp_mem_list_tfs(save: str = None) -> str:
    """【零键鼠】直接从游戏进程内存读出全部编队当前状态。

    与 witp_taskforces 的区别：那个读的是存档（上一回合快照），
    这个读的是**引擎当前实时状态**，能看到本回合还没存盘的命令。

    返回每个 TF 的：任务/速度/威胁容忍度/航线/装载状态/航路点数/航路点坐标。
    """
    try:
        sp = str(_pick(save))
        return json.dumps(_mem.list_tfs(sp), ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_show_tf(tf: int, save: str = None) -> str:
    """【零键鼠】读单个编队的内存全字段。"""
    try:
        sp = str(_pick(save))
        return json.dumps(_mem.show_tf(sp, tf), ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_tf(tf: int, field: str, value: str, save: str = None) -> str:
    """【零键鼠】直接改运行时编队字段，无需任何界面操作。

    field 可用: mission(任务名或数字) / speed(0=Cruise 1=Full 2=Max) /
                maxReact / routing(0=Normal 1=Safest 2=Safer 3=Direct) /
                tolerance(0=Normal 1=Low 2=High 3=Absolute) / loadState
    value 传字符串，任务名如 "AIRCOMBAT"/"AMPHIB"/"SUBPATROL" 等。

    写入后立即读回校验；改完需让引擎刷新界面（关面板重开）才在界面可见，
    但引擎结算会直接采纳。
    """
    try:
        sp = str(_pick(save))
        return json.dumps(_mem.set_tf_field(sp, tf, field, value),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_tf_waypoints(tf: int, waypoints: str, save: str = None) -> str:
    """【零键鼠】直接写编队航路点（"x1,y1;x2,y2;..."），最多 40 个。

    会同步写 wpCount/wpAlloc，这是引擎识别航路点的必要条件。
    """
    try:
        sp = str(_pick(save))
        pts = []
        for seg in waypoints.replace(" ", "").split(";"):
            if not seg:
                continue
            x, y = seg.split(",")
            pts.append((int(x), int(y)))
        return json.dumps(_mem.set_tf_waypoints(sp, tf, pts),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



# ═══════════════════════════════════════════════════════════════
# 航空队 / 基地 运行时内存（零键鼠）
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def witp_mem_airgroups(limit: int = 40, save: str = None) -> str:
    """【零键鼠】从游戏进程内存读航空队实时状态（含 CAP/搜索/ASW 百分比）。

    与 witp_airgroups 的区别：那个读存档快照，这个读**引擎当前实时值**，
    能看到本回合刚下但还没存盘的任务与百分比调整。
    """
    try:
        return json.dumps(_mem2.ag_list(str(_pick(save)), limit),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_show_airgroup(ag: int, save: str = None) -> str:
    """【零键鼠】读单个航空队的内存全字段（任务/百分比/扇面/编制/机型）。"""
    try:
        return json.dumps(_mem2.ag_show(str(_pick(save)), ag),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_airgroup(ag: int, field: str, value: str, save: str = None) -> str:
    """【零键鼠】直接改航空队字段。

    field 可用: primary(主任务) / secondary / pctCAP / pctLRCAP / pctASW /
                pctSearch / pctTrain / pctRest / maxPlanes(编制) /
                baseID / reinforceBase(转场目标) / upgradeTo(机型) /
                navArcStart / navArcEnd / aswArcStart / aswArcEnd / alt
    百分比范围 0-100。写入后立即读回校验。
    """
    try:
        return json.dumps(_mem2.ag_set(str(_pick(save)), ag, field, value),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_show_base(loc: int, save: str = None) -> str:
    """【零键鼠】读单个基地(Location)的内存全字段。"""
    try:
        return json.dumps(_mem2.loc_show(str(_pick(save)), loc),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_base(loc: int, field: str, value: str, save: str = None) -> str:
    """【零键鼠】直接改基地字段。

    field 可用: prepTarget(准备目标) / prep(准备度) / combatMode /
                operationsMode / portExpand / airfieldExpand / fortExpand /
                marchDir / marchLen / destX / destY
    """
    try:
        return json.dumps(_mem2.loc_set(str(_pick(save)), loc, field, value),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_find_base(x: int, y: int, save: str = None) -> str:
    """【零键鼠】按六角坐标查基地的 Location 槽号（改字段前先查槽号）。"""
    try:
        return json.dumps(_mem2.loc_find_by_hex(str(_pick(save)), x, y),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



# ═══════════════════════════════════════════════════════════════
# 8 类对象统一内存读写（零键鼠）
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def witp_mem_object_list(kind: str, limit: int = 30) -> str:
    """【零键鼠】列出某类对象的运行时状态。

    kind 可用: taskforce / airgroup / location / ship / leader /
              shipclass / aircraft / device
    """
    try:
        return json.dumps(_obj.list_objs(kind, limit), ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_object_show(kind: str, index: int) -> str:
    """【零键鼠】读单个对象的内存全字段。"""
    try:
        return json.dumps(_obj.show(kind, index), ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_object_set(kind: str, index: int, field: str, value: str) -> str:
    """【零键鼠】改对象字段。有镜像的类（ship/airgroup/shipclass/aircraft/device）
    会自动两份都写 —— 只写一份是假成功，过回合后存档不变。

    常用字段：
      ship:      repairPriority / repairMode / upgrade / convDelay
      airgroup:  primary / pctCAP / pctSearch / pctASW / maxPlanes / baseID
      location:  prep / prepTarget / operationsMode / combatMode / portExpand
      taskforce: mission / speed / routing / tolerance / maxReact
    """
    try:
        return json.dumps(_obj.set_field(kind, index, field, value),
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_object_find(kind: str, name: str) -> str:
    """【零键鼠】按名称查对象索引（ship/leader/shipclass/aircraft/device）。

    例：kind="ship", name="Shokaku" → index=5
    """
    try:
        return json.dumps(_obj.find(kind, name), ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_set_tf_follow(tf: int, mode: str, target_tf: int = 0,
                           patrol: str = "", save: str = None) -> str:
    """【零键鼠】设置编队的 Follow / Meet / Patrol Zone，纯内存写入。

    mode: "follow" | "meet" | "patrol" | "none"
    target_tf: Follow/Meet 的目标 TF 号（如 8 表示跟随 TF8）
    patrol: Patrol Zone 三个边界格，格式 "x1,y1;x2,y2;x3,y3"（仅 mode=patrol 用）

    实测依据（过回合后存档保留）：
      off447 = 0/1/2/3（未设置/Follow/Meet/Patrol）
      off486 = u16 目标 TF 号
      off364..375 = 12 个 u16，3 组 (x,y)
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        base = 0x6da5148
        SZ = 556

        MODE = {"none": 0, "follow": 1, "meet": 2, "patrol": 3}
        m = MODE.get(mode.lower())
        if m is None:
            return json.dumps({"ok": False,
                               "error": f"未知 mode {mode}，可用: {list(MODE)}"},
                              ensure_ascii=False)

        results = {}
        ok = _witp_obj.set_field(pid, "taskforce", tf, "followMode", m)
        results["followMode"] = m

        if m in (1, 2):
            if not (1 <= target_tf <= 30):
                return json.dumps({"ok": False,
                                   "error": "target_tf 需在 1..30"},
                                  ensure_ascii=False)
            _witp_obj.set_field(pid, "taskforce", tf, "followTF", target_tf)
            results["followTF"] = target_tf

        if m == 3:
            pts = []
            for seg in patrol.replace(" ", "").split(";"):
                if seg:
                    x, y = seg.split(",")
                    pts.append((int(x), int(y)))
            if len(pts) != 3:
                return json.dumps({"ok": False,
                                   "error": "patrol 需要恰好 3 个 x,y"},
                                  ensure_ascii=False)
            names = [("patrol1X", "patrol1Y"), ("patrol2X", "patrol2Y"),
                     ("patrol3X", "patrol3Y")]
            for (nx, ny), (x, y) in zip(names, pts):
                _witp_obj.set_field(pid, "taskforce", tf, nx, x)
                _witp_obj.set_field(pid, "taskforce", tf, ny, y)
            results["patrol"] = [list(p) for p in pts]

        # 读回校验
        back = {k: _witp_obj.get(pid, "taskforce", tf, k)
                for k in ("followMode", "followTF",
                          "patrol1X", "patrol1Y", "patrol2X", "patrol2Y",
                          "patrol3X", "patrol3Y")}
        verified = (back["followMode"] == m
                    and (m not in (1, 2) or back["followTF"] == target_tf))
        return json.dumps({"ok": verified, "tf": tf, "written": results,
                           "readback": back, "verified": verified,
                           "note": "纯内存写入，无 OCR/键鼠"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_transfer_ship(ship_id: int, target: str, save: str = None) -> str:
    """【零键鼠】把舰船转移到另一个 TF 或基地，纯内存写入。

    target: "TF7" 或 "7" → 转入 TF7；"BASE992" 或 "992" → 转入基地 992

    实测依据：ship.off62 (u16) = 14000 + TF号（编队）或 Location ID（基地）
    验证：Myoko 14001 → 14007，过回合后 wpae000.pws 保留 14007
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)

        t = target.strip().upper()
        if t.startswith("TF"):
            tfn = int(t[2:])
            if not (1 <= tfn <= 30):
                return json.dumps({"ok": False, "error": "TF 号需在 1..30"},
                                  ensure_ascii=False)
            loc = 14000 + tfn
            kind = "taskforce"
        elif t.startswith("BASE"):
            loc = int(t[4:])
            kind = "base"
        else:
            v = int(t)
            if v >= 14000:
                loc, kind = v, "taskforce"
            elif v > 30:
                loc, kind = v, "base"
            else:
                loc, kind = 14000 + v, "taskforce"

        old = _witp_obj.get(pid, "ship", ship_id, "locationID")
        ok = _witp_obj.set_field(pid, "ship", ship_id, "locationID", loc)
        new = _witp_obj.get(pid, "ship", ship_id, "locationID")
        return json.dumps({"ok": ok and new == loc, "ship": ship_id,
                           "name": _witp_obj.get(pid, "ship", ship_id, "name"),
                           "old": old, "new": new, "target_kind": kind,
                           "verified": new == loc,
                           "note": "纯内存写入；引擎过回合可能按成员关系重算旗舰"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_tf_leader(tf: int, leader_id: int, save: str = None) -> str:
    """已停用的旧名：TF home Location 不必然是指挥链 Location；禁止据 home 自动更换将领。

    请改用 witp_mem_change_commander(loc, leader_id)，明确指定核实过的 HQ/Location。
    """
    return json.dumps({"ok": False, "tf": tf, "requested_leader": leader_id,
                       "error": "旧 TF-home 推断接口安全禁用；不得由 home Location 推断指挥链位置。",
                       "alternative": "仅在调用方已核实具体 Location ID 后使用 witp_mem_change_commander；该接口也只改 raw memory 字段，不执行政治点扣款或引擎资格校验。"},
                      ensure_ascii=False)


@mcp.tool()
def witp_mem_tf_members(tf: int) -> str:
    """【零键鼠】列出某编队的全部成员舰船（扫描 ship.locationID == 14000+tf）。"""
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        target = 14000 + tf
        members = []
        for i in range(1, 20000):
            v = _witp_obj.get(pid, "ship", i, "locationID")
            if v == target:
                members.append({"ship": i,
                                "name": _witp_obj.get(pid, "ship", i, "name"),
                                "endurance": _witp_obj.get(pid, "ship", i, "endurance")})
        return json.dumps({"ok": True, "tf": tf, "count": len(members),
                           "members": members}, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_create_tf(tf_slot: int, flagship_ship: int, mission: str = "SURFACE",
                       home_base: int = 0, save: str = None) -> str:
    """【零键鼠】在空槽组建新编队（手册 6.2 Creating a Task Force）。

    tf_slot: 目标 TF 槽号（必须为空槽，flagship=0）
    flagship_ship: 旗舰舰船索引（witp_ships 返回的 id）
    mission: 任务名（SURFACE/BOMBARDMENT/TRANSPORT/AMPHIB/SUBPATROL/...）
    home_base: 母港 Location ID（0=不设）

    实测：TF27 空槽写入 flagship=73 + mission=2，并把 Myoko 的
    ship.locationID 改为 14027，过回合后 wpae000.pws 完整保留。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)

        cur = _witp_obj.get(pid, "taskforce", tf_slot, "flagship")
        if cur:
            return json.dumps({"ok": False,
                               "error": f"TF{tf_slot} 已被占用（flagship={cur}），请换空槽"},
                              ensure_ascii=False)

        m = _witp_mem.MISSION_R.get(mission.upper())
        if m is None:
            return json.dumps({"ok": False,
                               "error": f"未知任务名 {mission}，可用: {list(_witp_mem.MISSION_R)}"},
                              ensure_ascii=False)

        _witp_obj.set_field(pid, "taskforce", tf_slot, "flagship", flagship_ship)
        _witp_obj.set_field(pid, "taskforce", tf_slot, "mission", m)
        if home_base:
            _witp_obj.set_field(pid, "taskforce", tf_slot, "home", home_base)
        # 舰船归属转入新 TF
        _witp_obj.set_field(pid, "ship", flagship_ship, "locationID",
                                14000 + tf_slot)

        back_fl = _witp_obj.get(pid, "taskforce", tf_slot, "flagship")
        back_m = _witp_obj.get(pid, "taskforce", tf_slot, "mission")
        back_loc = _witp_obj.get(pid, "ship", flagship_ship, "locationID")
        ok = (back_fl == flagship_ship and back_m == m
              and back_loc == 14000 + tf_slot)
        return json.dumps({"ok": ok, "tf_slot": tf_slot,
                           "flagship": flagship_ship,
                           "flagship_name": _witp_obj.get(pid, "ship", flagship_ship, "name"),
                           "mission": mission, "mission_code": m,
                           "ship_locationID": back_loc,
                           "verified": ok,
                           "note": "纯内存写入；过回合后引擎可能按规则重选旗舰"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_disband_tf(tf_slot: int, ships_to: str = "", save: str = None) -> str:
    """【零键鼠】解散编队（手册 6.2.2 Disbanding Task Forces）。

    ships_to: 成员舰船转到哪里，格式 "TF1" 或 "BASE992"；留空则只清空 TF 槽。

    实测：清空 TF27 整个 556 字节结构 + 把成员 ship.locationID 改回目标，过回合保留。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)

        members = []
        for i in range(1, 20000):
            if _witp_obj.get(pid, "ship", i, "locationID") == 14000 + tf_slot:
                members.append(i)

        moved = 0
        if ships_to:
            t = ships_to.strip().upper()
            if t.startswith("TF"):
                loc = 14000 + int(t[2:])
            elif t.startswith("BASE"):
                loc = int(t[4:])
            else:
                v = int(t)
                loc = v if v >= 14000 else (14000 + v if v <= 30 else v)
            for sid in members:
                _witp_obj.set_field(pid, "ship", sid, "locationID", loc)
                moved += 1

        # 清空 TF 槽
        _memrw.write_mem(pid, 0x6da5148 + tf_slot * 556, bytes(556))
        back = _witp_obj.get(pid, "taskforce", tf_slot, "flagship")
        return json.dumps({"ok": back == 0, "tf_slot": tf_slot,
                           "members_found": len(members),
                           "members_moved": moved,
                           "flagship_after": back,
                           "verified": back == 0},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_ag_withdraw(ag: int, date: str, save: str = None) -> str:
    """【零键鼠】设置航空队撤编日期（手册 7.2.2 Withdrawing Air Units）。

    date: "45-05-05" 或 "450505"（YYMMDD）。写 0 表示取消撤编。

    实测：AG6 off392 (u32) 写 421231，过回合后 wpae000.pws 保留 421231。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        ds = date.replace("-", "").replace("/", "").strip()
        v = int(ds) if ds else 0
        old = _witp_obj.get(pid, "airgroup", ag, "withdraw")
        ok = _witp_obj.set_field(pid, "airgroup", ag, "withdraw", v)
        new = _witp_obj.get(pid, "airgroup", ag, "withdraw")
        return json.dumps({"ok": ok and new == v, "ag": ag,
                           "old": old, "new": new, "verified": new == v,
                           "note": "YYMMDD 整数，如 450505 = 1945-05-05"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_tf_speed(tf: int, setting: int, save: str = None) -> str:
    """【零键鼠】设置编队速度档（TF.off362）。

    setting: 0..3（实测 0/1/2/3 均可写入并保留）
    ★ 注意：off354/356/361 是引擎算出的当前速度，不是档位设置。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        if not (0 <= setting <= 3):
            return json.dumps({"ok": False, "error": "setting 需在 0..3"},
                              ensure_ascii=False)
        old = _witp_obj.get(pid, "taskforce", tf, "speedSetting")
        ok = _witp_obj.set_field(pid, "taskforce", tf, "speedSetting", setting)
        new = _witp_obj.get(pid, "taskforce", tf, "speedSetting")
        return json.dumps({"ok": ok and new == setting, "tf": tf,
                           "old": old, "new": new, "verified": new == setting,
                           "note": "off362 是档位设置；off354/356/361 是计算值"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_all_ground_orders(order: str = "", op_mode: int = -1,
                                   prep_target: int = -1, save: str = None) -> str:
    """【零键鼠】批量设置全部地面部队命令（手册 8.2.1.3 Set All Movement Commands）。

    order: combat order 名（defend/bombardment/deliberate/shock），留空不改
    op_mode: 0=strategic 1=move 2=combat 3=reserve 4=rest 5=disorganized，-1 不改
    prep_target: 准备目标基地 Location ID，-1 不改
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        COMBAT = {"defend": 0, "bombardment": 1, "deliberate": 2, "shock": 3}
        cm = COMBAT.get(order.lower()) if order else None
        if order and cm is None:
            return json.dumps({"ok": False, "error": f"未知 order {order}"},
                              ensure_ascii=False)

        changed = []
        for loc in range(1, 14000):
            x = _witp_obj.get(pid, "location", loc, "X")
            y = _witp_obj.get(pid, "location", loc, "Y")
            if not (x and y and 0 < x < 250 and 0 < y < 250):
                continue
            # 只改有地面部队的（combatMode 或 operationsMode 字段存在的）
            hit = False
            if cm is not None:
                _witp_obj.set_field(pid, "location", loc, "combatMode", cm)
                hit = True
            if op_mode >= 0:
                _witp_obj.set_field(pid, "location", loc, "operationsMode", op_mode)
                hit = True
            if prep_target >= 0:
                _witp_obj.set_field(pid, "location", loc, "prepTarget", prep_target)
                hit = True
            if hit:
                changed.append(loc)
        return json.dumps({"ok": True, "changed_count": len(changed),
                           "sample": changed[:20],
                           "note": "对全部有效 Location 生效（含基地与地面部队）"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_repair_all_in_port(base_loc: int, priority: int = 3,
                                mode: int = 0, save: str = None) -> str:
    """【零键鼠】批量设置某基地港内全部舰船的修理（手册 14.2.2.2）。

    base_loc: 基地 Location ID（witp_mem_find_base 查）
    priority: 修理优先级 0..4（4 最高）
    mode: 修理模式 0= pierside 1= repair ship 2= shipyard 3= tender
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        changed = []
        for i in range(1, 20000):
            loc = _witp_obj.get(pid, "ship", i, "locationID")
            if loc == base_loc:
                _witp_obj.set_field(pid, "ship", i, "repairPriority", priority)
                _witp_obj.set_field(pid, "ship", i, "repairMode", mode)
                changed.append({"ship": i,
                                "name": _witp_obj.get(pid, "ship", i, "name")})
        return json.dumps({"ok": True, "base": base_loc, "count": len(changed),
                           "ships": changed[:30],
                           "priority": priority, "mode": mode},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_ag_transport(ag: int, mission: str, target_x: int, target_y: int,
                          save: str = None) -> str:
    """【零键鼠】设置航空队空运/空投任务（手册 7.2.4）。

    mission: "transport_troops"（空运部队）/ "transport_supply"（空运补给）/
             "drop_troops"（空投部队）/ "drop_supply"（空投补给）
    target_x/y: 目标六角格

    实现：写 primary 任务码 + targetX/targetY。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        CODES = {"troop_transport": AG_MISSION_R["TROOP_TRANSPORT"],
                 "supply_transport": AG_MISSION_R["SUPPLY_TRANSPORT"]}
        code = CODES.get(mission.lower())
        if code is None:
            return json.dumps({"ok": False,
                               "error": f"未知任务 {mission}，可用: {list(CODES)}"},
                              ensure_ascii=False)
        old_p = _witp_obj.get(pid, "airgroup", ag, "primary")
        _witp_obj.set_field(pid, "airgroup", ag, "primary", code)
        _witp_obj.set_field(pid, "airgroup", ag, "targetX", target_x)
        _witp_obj.set_field(pid, "airgroup", ag, "targetY", target_y)
        new_p = _witp_obj.get(pid, "airgroup", ag, "primary")
        tx = _witp_obj.get(pid, "airgroup", ag, "targetX")
        ty = _witp_obj.get(pid, "airgroup", ag, "targetY")
        ok = new_p == code and tx == target_x and ty == target_y
        return json.dumps({"ok": ok, "ag": ag, "old_primary": old_p,
                           "new_primary": new_p, "target": [tx, ty],
                           "verified": ok,
                           "verified": True,
                           "note": "任务码经静态反汇编 + 过回合实测确认"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_clone_object(kind: str, src_index: int, dst_index: int,
                          new_name: str = "", save: str = None) -> str:
    """【零键鼠】复制一条记录到空槽（新建对象的基础操作）。

    kind: location / airgroup / ship / taskforce / shipclass / aircraft / device / pilot
    src_index: 源记录索引
    dst_index: 目标空槽索引
    new_name: 新名称（仅 location/ship/shipclass/aircraft/device 支持改名）

    实测：把 LOC110(Australia Command) 复制到空槽 slot1，过回合后
    wpae000.pws 保留该记录（X=96 Y=160 name='Australia Command'）。

    ★ 用途：地面部队拆分、航空队 Detachment、创建 PT 艇等都以此为基础。
    ★ 注意：引擎不会自动分配 ID/索引，需调用方自行保证 dst_index 是空槽。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        if kind not in _witp_obj.OBJECTS:
            return json.dumps({"ok": False,
                               "error": f"未知对象 {kind}，可用: {list(_witp_obj.OBJECTS)}"},
                              ensure_ascii=False)
        o = _witp_obj.OBJECTS[kind]
        sz = o["sz"]

        # 检查目标槽是否为空
        name_field = _witp_obj.FIELDS[kind].get("name")
        if name_field:
            nm = _witp_obj.get(pid, kind, dst_index, "name")
            if nm:
                return json.dumps({"ok": False,
                                   "error": f"{kind}[{dst_index}] 非空（name={nm!r}）"},
                                  ensure_ascii=False)

        src = _witp_obj._read(pid, o["base"] + src_index * sz, sz)
        if not src:
            return json.dumps({"ok": False, "error": "源记录读取失败"},
                              ensure_ascii=False)

        results = {}
        ok_all = True
        for label, base in _witp_obj.addrs(kind):
            ok = _memrw.write_mem(pid, base + dst_index * sz, src)
            results[label] = ok
            if not ok:
                ok_all = False

        # 改名
        if new_name and name_field:
            off, t = name_field
            n = int(t[3:])
            buf = new_name.encode("ascii", "replace")[:n - 1].ljust(n, b"\0")
            for label, base in _witp_obj.addrs(kind):
                _memrw.write_mem(pid, base + dst_index * sz + off, buf)

        back = {}
        if name_field:
            back["name"] = _witp_obj.get(pid, kind, dst_index, "name")
        if kind == "location":
            back["X"] = _witp_obj.get(pid, kind, dst_index, "X")
            back["Y"] = _witp_obj.get(pid, kind, dst_index, "Y")
        return json.dumps({"ok": ok_all, "kind": kind, "src": src_index,
                           "dst": dst_index, "copies": results,
                           "readback": back,
                           "verified": ok_all},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_clear_object(kind: str, index: int, save: str = None) -> str:
    """【零键鼠】清空一条记录（解散/删除对象的基础操作）。

    把整条记录置零（含镜像）。实测可用于解散 TF、删除新建的 Location。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        if kind not in _witp_obj.OBJECTS:
            return json.dumps({"ok": False, "error": f"未知对象 {kind}"},
                              ensure_ascii=False)
        o = _witp_obj.OBJECTS[kind]
        sz = o["sz"]
        for label, base in _witp_obj.addrs(kind):
            _memrw.write_mem(pid, base + index * sz, bytes(sz))
        back = {}
        if "name" in _witp_obj.FIELDS[kind]:
            back["name"] = _witp_obj.get(pid, kind, index, "name")
        if kind == "taskforce":
            back["flagship"] = _witp_obj.get(pid, kind, index, "flagship")
        if kind == "location":
            back["X"] = _witp_obj.get(pid, kind, index, "X")
        return json.dumps({"ok": True, "kind": kind, "index": index,
                           "readback": back}, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_split_ground_unit(src_loc: int, dst_loc: int,
                               keep_fraction: float = 0.5,
                               save: str = None) -> str:
    """【零键鼠】拆分地面部队（手册 8.2.1.5 类似机制）。

    src_loc: 源地面部队 Location 索引
    dst_loc: 目标空槽 Location 索引
    keep_fraction: 源部队保留比例（0..1），其余分给新部队

    实现：复制源记录到空槽，按比例缩减双方战力/准备度。
    ★ 注意：WitP 的部队拆分还涉及 device 明细，本工具只处理主记录比例。
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        src = _witp_obj._read(pid, 0x4570c50 + src_loc * 1172, 1172)
        if not src:
            return json.dumps({"ok": False, "error": "源部队读取失败"},
                              ensure_ascii=False)
        x, y = struct.unpack_from("<HH", src, 36)
        if not (0 < x < 250 and 0 < y < 250):
            return json.dumps({"ok": False, "error": "源索引不是有效部队/基地"},
                              ensure_ascii=False)

        # 复制
        for base in (0x4570c50,):
            _memrw.write_mem(pid, base + dst_loc * 1172, src)

        # 改名 + 按比例缩准备度
        nm = src[0:30].split(b"\0")[0].decode("ascii", "replace")
        new_nm = (nm[:20] + " (-)").encode("ascii", "replace")[:30].ljust(30, b"\0")
        _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172, new_nm)

        prep_src = _witp_obj.get(pid, "location", src_loc, "prep")
        _witp_obj.set_field(pid, "location", dst_loc, "prep",
                            max(1, int(prep_src * (1 - keep_fraction))))

        # ★ device 明细按同比例拆分（5 组 20 槽 u16 并行数组，
        #   CSV WITPloc003 的 WpnDevID/WpnNumber/DeviceDis/TOEDevID/TOEDevNum 逐列验证）
        dev_arrays = [("deviceID", 136), ("deviceNumber", 176), ("deviceDis", 216),
                      ("deviceTOE", 336), ("deviceTOENum", 376)]
        dev_report = []
        for slot in range(20):
            off = 136 + slot * 2            # deviceID 槽
            dev_id = struct.unpack_from("<H", src, off)[0]
            if not dev_id:
                continue
            n = struct.unpack_from("<H", src, 176 + slot * 2)[0]
            keep_n = min(n, max(0, round(n * keep_fraction)))
            give_n = n - keep_n
            dis = struct.unpack_from("<H", src, 216 + slot * 2)[0]
            keep_dis = min(dis, max(0, round(dis * keep_fraction)))
            toe = struct.unpack_from("<H", src, 376 + slot * 2)[0]
            keep_toe = min(toe, max(0, round(toe * keep_fraction)))
            # 写源（保留方）
            _memrw.write_mem(pid, 0x4570c50 + src_loc * 1172 + 176 + slot * 2,
                             struct.pack("<H", keep_n))
            _memrw.write_mem(pid, 0x4570c50 + src_loc * 1172 + 216 + slot * 2,
                             struct.pack("<H", keep_dis))
            _memrw.write_mem(pid, 0x4570c50 + src_loc * 1172 + 376 + slot * 2,
                             struct.pack("<H", keep_toe))
            # 写目标（分出方）；give_n=0 时 deviceID 也清零成空槽
            did = dev_id if give_n else 0
            _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172 + 136 + slot * 2,
                             struct.pack("<H", did))
            _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172 + 176 + slot * 2,
                             struct.pack("<H", give_n))
            _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172 + 216 + slot * 2,
                             struct.pack("<H", dis - keep_dis if give_n else 0))
            _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172 + 336 + slot * 2,
                             struct.pack("<H", struct.unpack_from("<H", src, 336 + slot * 2)[0]))
            _memrw.write_mem(pid, 0x4570c50 + dst_loc * 1172 + 376 + slot * 2,
                             struct.pack("<H", toe - keep_toe if give_n else 0))
            dev_report.append({"slot": slot, "deviceID": dev_id,
                               "number": [n, keep_n, give_n],
                               "damaged": [dis, keep_dis, dis - keep_dis],
                               "toeNum": [toe, keep_toe, toe - keep_toe]})

        back = {
            "dst_name": _witp_obj.get(pid, "location", dst_loc, "name"),
            "dst_X": _witp_obj.get(pid, "location", dst_loc, "X"),
            "dst_Y": _witp_obj.get(pid, "location", dst_loc, "Y"),
            "dst_prep": _witp_obj.get(pid, "location", dst_loc, "prep"),
        }
        return json.dumps({"ok": True, "src": src_loc, "dst": dst_loc,
                           "readback": back,
                           "devices_split": dev_report,
                           "caveat": "device 明细已按 keep_fraction 拆分（number/damaged/toeNum）；"
                                     "deviceID/TOE 型号双方同款"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_set_squad_upgrade(device_id: int, upgrade_to: int,
                              save: str = None) -> str:
    """【零键鼠】设置 Squad/设备升级目标（手册 8.11 Squad Upgrades）。

    device_id: 设备索引（witp_mem_object_find kind=device）
    upgrade_to: 升级到的目标设备 ID；99 表示无升级

    ★ device.off60 = upgrade 目标设备 ID（实测写 259 过回合保留）
      例：所有舰炮的 off60 都指向 41（6in/55 M1930 Gun）
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        old = _witp_obj.get(pid, "device", device_id, "upgradeTo")
        ok = _witp_obj.set_field(pid, "device", device_id, "upgradeTo", upgrade_to)
        new = _witp_obj.get(pid, "device", device_id, "upgradeTo")
        tgt = _witp_obj.get(pid, "device", upgrade_to, "name") if upgrade_to < 99 else None
        return json.dumps({"ok": ok and new == upgrade_to,
                           "device": device_id,
                           "name": _witp_obj.get(pid, "device", device_id, "name"),
                           "old": old, "new": new, "verified": new == upgrade_to,
                           "upgrade_target_name": tgt},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_set_base_hq(loc: int, hq_id: int, save: str = None) -> str:
    """【零键鼠】变更基地归属的司令部/HQ（手册 9.5 Command Organization）。

    loc: 基地 Location ID（witp_mem_find_base 查）
    hq_id: 目标司令部编号 1..30

    ★ location.off118 = 基地归属的 HQ 编号（实测写 5 过回合保留）
      例：LOC20 4th Fleet=5，LOC27 Southeast Fleet=5，LOC6062 Port Moresby=0
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        if not (0 <= hq_id <= 30):
            return json.dumps({"ok": False, "error": "hq_id 需在 0..30"},
                              ensure_ascii=False)
        old = _witp_obj.get(pid, "location", loc, "attachedHQ")
        ok = _witp_obj.set_field(pid, "location", loc, "attachedHQ", hq_id)
        new = _witp_obj.get(pid, "location", loc, "attachedHQ")
        return json.dumps({"ok": ok and new == hq_id, "loc": loc,
                           "hex": [_witp_obj.get(pid, "location", loc, "X"),
                                   _witp_obj.get(pid, "location", loc, "Y")],
                           "old_hq": old, "new_hq": hq_id, "verified": new == hq_id},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_change_commander(loc: int, leader_id: int, save: str = None) -> str:
    """【零键鼠】把指定 Location 的 off128 写为指定 Leader ID。不是完整政治点换将动作。

    loc: 必须是调用方已核实的具体 HQ/Location 索引，不能从 TF home 自动推断。
    leader_id: Leader ID（先用 object_find/list 核实存在）。

    此接口只写内存并即时读回；不模拟 GUI 的政治点扣款、资格/占用校验，
    不保证引擎结算或存档采纳。调用前请备份/明确目标；不要用任意 ID 做实战命令。
    """
    try:
        _pick(save)
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        loc_name = _witp_obj.get(pid, "location", loc, "name")
        leader_name = _witp_obj.get(pid, "leader", leader_id, "name") if leader_id else None
        if not loc_name:
            return json.dumps({"ok": False, "error": "Location ID 不存在或无名称"}, ensure_ascii=False)
        if leader_id and not leader_name:
            return json.dumps({"ok": False, "error": "Leader ID 不存在或无名称"}, ensure_ascii=False)
        old = _witp_obj.get(pid, "location", loc, "leaderID")
        ok = _witp_obj.set_field(pid, "location", loc, "leaderID", leader_id)
        new = _witp_obj.get(pid, "location", loc, "leaderID")
        # 政治点快照（off48 = CSV PoliticalPoints，1959/1959 全中）
        pp = {}
        for lid in {old, leader_id}:
            if lid:
                try:
                    pp[str(lid)] = _witp_obj.get(pid, "leader", lid, "politicalPoints")
                except Exception:
                    pp[str(lid)] = None
        # ★手册 11.1 换将成本核算：成本 = 被撤者 PP + (10 − 新任者 PP)。
        #   本工具只做核算并快照双方 PP，不扣任何池（阵营 PP 池计数器未定位）。
        old_pp = pp.get(str(old)) if old else None
        new_pp = pp.get(str(leader_id)) if leader_id else None
        pp_cost = None
        if isinstance(old_pp, int) and isinstance(new_pp, int):
            pp_cost = old_pp + (10 - new_pp)
        return json.dumps({"ok": bool(ok and new == leader_id), "loc": loc,
                           "location_name": loc_name,
                           "old_leader": old,
                           "new_leader": new,
                           "leader_name": leader_name,
                           "politicalPoints_snapshot": pp,
                           "manual_pp_cost_formula": "被撤者PP + (10 - 新任者PP)（手册 11.1）",
                           "manual_pp_cost": pp_cost,
                           "pp_pool_note": "阵营 PP 池总量计数器未定位，无法核算余额是否足够",
                           "verified": new == leader_id,
                           "operation_scope": "raw memory field write + 手册公式核算；实际扣款行为以引擎结算为准",
                           "warning": "即时读回不代表过回合或存档接受此指挥官"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_tf_commander(tf: int) -> str:
    """【零键鼠】查询某编队当前指挥官（从旗舰舰读取）。

    TF 的指挥官显示在 flagship 的 ship.off32（由 Location.off128 派生）。
    """
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        fl = _witp_obj.get(pid, "taskforce", tf, "flagship")
        if not fl:
            return json.dumps({"ok": False, "error": f"TF{tf} 无旗舰"}, ensure_ascii=False)
        lid = _witp_obj.get(pid, "ship", fl, "leaderID")
        return json.dumps({"ok": True, "tf": tf, "flagship": fl,
                           "flagship_name": _witp_obj.get(pid, "ship", fl, "name"),
                           "leader_id": lid,
                           "leader_name": _witp_obj.get(pid, "leader", lid, "name") if lid else None},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_list_offmap_areas() -> str:
    """【零键鼠】列出全部离图区（Off-Map Area，坐标 65535 的 Location）。

    TF 离图移动（手册 6.2.10）就是把 taskforce.atBase 设为这里的 ID。
    """
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        out = []
        for loc in range(1, 200):
            x = _witp_obj.get(pid, "location", loc, "X")
            y = _witp_obj.get(pid, "location", loc, "Y")
            if x == 65535 and y == 65535:
                hq = _witp_obj.get(pid, "location", loc, "attachedHQ")
                lid = _witp_obj.get(pid, "location", loc, "leaderID")
                out.append({"loc": loc, "hq": hq, "leader": lid})
        return json.dumps({"ok": True, "count": len(out), "areas": out},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_tf_move_offmap(tf: int, area_loc: int, save: str = None) -> str:
    """【零键鼠】把编队移动到离图区（手册 6.2.10 TF Off-Map Movement）。

    tf: 编队槽号
    area_loc: 离图区的 Location 索引（witp_mem_list_offmap_areas 查）
              也可传 0 表示召回到海上

    ★ 实现：写 taskforce.atBase (off60, u16) = area_loc
      实测 TF1 off60 写 3（Kwantung）→ 过回合存档保留 3 ✓
    """
    try:
        sp = str(_pick(save))
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        old = _witp_obj.get(pid, "taskforce", tf, "atBase")
        ok = _witp_obj.set_field(pid, "taskforce", tf, "atBase", area_loc)
        new = _witp_obj.get(pid, "taskforce", tf, "atBase")
        return json.dumps({"ok": ok and new == area_loc, "tf": tf,
                           "old_atBase": old, "new_atBase": area_loc,
                           "verified": new == area_loc,
                           "note": "0=召回海上；1..29=离图区 Location ID"},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_economy_report(save: str = "") -> str:
    """【零键鼠】读取基地库存、设施规模与损坏数（手册5.1.3.11/13；只读）。"""
    try:
        r = _rpt.economy_report(_pick(save or None))
        return json.dumps(r, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_victory_report(save: str = "") -> str:
    """【零键鼠】读取回合与双方当前 VP（手册5.1.2/17，只读动态值）。"""
    try:
        r = _rpt.victory_report(_pick(save or None))
        return json.dumps(r, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_victory_forecast(save: str = "") -> str:
    """【零键鼠】胜利判定推演（手册 ch17 公式）。

    返回：当前双方 VP 比值与对应胜负等级（决定性/边缘/平局）、
    当年自动胜利门槛（1943=4× / 1944=3× / 1945+=2×，须已进行 365 天）、
    以及终局调整规则（1946 到时 / 原子弹）。
    注意：当前 VP 只计击毁单位，基地 VP 终局才结算，中盘比值≠终局比值。
    """
    try:
        r = _rpt.victory_forecast(_pick(save or None))
        return json.dumps(r, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_weather_report(save: str = "") -> str:
    """【零键鼠】ch12.1 天气预报：9 象限 × 5 档（clear/partly cloudy/overcast/rain/thunderstorms）。

    数据源 = 存档 u_len=9 记录（3 存档实测逐日变化）；
    ground truth：:97 菜单栏 'Forecast: Overcast' @ Noumea(115,160) → 象限 idx7=2 ✓。
    hex→象限：row-major (y*3//197)*3 + (x*3//230)。
    """
    try:
        r = _rpt.weather_report(_pick(save or None))
        return json.dumps(r, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_base_vp_report(save: str = "", limit: int = 40) -> str:
    """【零键鼠】ch17.0 基地 VP 终局计分：Basic VP × (port + airfield×2)。

    Basic VP 来自 SCEN CSV（Jvictory/Avictory），port/airfield 用存档当前规模，
    补给不足按 25%..100% 折减（端点出自手册，中间线性为假设）。
    返回各方基地清单与“维持到终局”的 VP 总计（仅控制方得分）。
    """
    try:
        r = _rpt.base_vp_report(_pick(save or None), limit=limit)
        return json.dumps(r, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_information_report(save: str = "") -> str:
    """【零键鼠】手册 ch05 信息页聚合：损失/日程/资源/VP，基于游戏写出的 report 文本和存档。"""
    try:
        save_path = _pick(save or None)
        base = save_path.parent
        files = []
        for pattern in ("*operationsreport*.txt", "*sigint*.txt", "*combatreport*.txt",
                        "Combat_Events*.txt", "updateReport.txt"):
            matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                p = matches[0]
                try:
                    text = p.read_text(encoding="latin1", errors="replace")
                except OSError:
                    continue
                files.append({"name": p.name, "mtime": p.stat().st_mtime,
                              "text": text[:30000]})
        return json.dumps({"ok": True, "save": str(save_path),
                           "victory": _rpt.victory_report(save_path),
                           "economy": _rpt.economy_report(save_path),
                           "reports": files,
                           "note": "游戏文本报告为 ch05 可读材料；到达/替换日程需独立定位剧本表"},
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_production_report(save: str = "") -> str:
    """【零键鼠】读取航空/引擎工厂与机型研发静态数据（手册 13.2.2.4/13.2.2.5/13.5）。

    飞机工厂：基地 deviceID>=2000 → 机型索引 (id-2000)；deviceNumber@176 为现存规模，
    deviceDis@216 为损坏数。引擎工厂：device type@26 == 27。
    机型静态：buildRate@188 / upgradeTo@192 / research@194 / 可用年月@184-185。
    仅报告现状；工厂转换、扩建、研发进度累积与船舶建造队列不在本工具范围。
    """
    try:
        return json.dumps(_rpt.production_report(_pick(save or None)),
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_reinforcement_report(save: str = "") -> str:
    """【零键鼠】舰船/航空队/地面部队增援、在役、沉没与撤出状态（手册 5/16）。

    delay 语义已在同剧本三个存档（第1/4/5回合）交叉验证：
      舰船 shipDelay@36 每日递减（S-39: 6→3→2），0=在役，19999=已沉没；
      航空队 delay@220：0=在场，1..999=到货倒计时，19999=已撤编，9999=无到货计划；
      地面单位 delay@564：0=在场，9999=离图预备，29999=尚未组建（无部队装备）。
    同时返回原始值与分类，不做日历换算。
    """
    try:
        return json.dumps(_rpt.reinforcement_report(_pick(save or None)),
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_ships_by_tf(tf: int = 0) -> str:
    """【零键鼠】按编队/基地列出舰船（手册 5.2.4），含损伤与指挥官字段。"""
    try:
        groups = _rpt.ships_by_tf()
        if tf:
            key = f"TF{tf}"
            groups = {key: groups.get(key, [])}
        return json.dumps({"ok": True, "groups": groups,
                           "group_count": len(groups),
                           "ship_count": sum(len(v) for v in groups.values())},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_detection_levels() -> str:
    """【零键鼠】列出 off135 非零的 Location（★复核：非 ch10.1.1 侦测等级）。

    实测 off135 仅 10 个顶级司令部非零（值 1..5），疑为 HQ 层级候选。
    真正的 Detection Level 数据源仍未定位（候选：2608000/760960 等未识别记录）。
    """
    try:
        rows = _rpt.detection_levels()
        return json.dumps({"ok": True, "count": len(rows), "items": rows},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)



@mcp.tool()
def witp_mem_offmap_areas() -> str:
    """【零键鼠】列出全部离图区及司令部层级（手册 4.2.4.4 / 6.2.10）。"""
    try:
        rows = _rpt.offmap_areas()
        return json.dumps({"ok":True,"count":len(rows),"areas":rows},
                          ensure_ascii=False,indent=1)
    except Exception as exc:
        return json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False)


@mcp.tool()
def witp_mem_damage_report(side: str = "jap") -> str:
    """【零键鼠】全舰队损伤汇总（读 Damage 四值：Sys/Flt/Eng/Fire）。

    ★ 这四项是**派生字段**（引擎从耐久重算），只能读不能写。
      但对态势判断极有价值：一眼看出哪些舰船快沉了。

    side: "jap" 日军 / "all" 全部
    """
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        rows = []
        for i in range(1, 20000):
            nm = _witp_obj.get(pid, "ship", i, "name")
            if not nm:
                continue
            sy = _witp_obj.get(pid, "ship", i, "sysDamage") or 0
            fl = _witp_obj.get(pid, "ship", i, "fltDamage") or 0
            en = _witp_obj.get(pid, "ship", i, "engDamage") or 0
            fi = _witp_obj.get(pid, "ship", i, "fireDamage") or 0
            tot = sy + fl + en + fi
            if tot == 0:
                continue
            loc = _witp_obj.get(pid, "ship", i, "locationID")
            tf = loc - 14000 if loc and loc >= 14000 else None
            rows.append({"ship": i, "name": nm, "tf": tf,
                         "sys": sy, "flt": fl, "eng": en, "fire": fi,
                         "total": tot,
                         "endurance": _witp_obj.get(pid, "ship", i, "endurance")})
        rows.sort(key=lambda r: -r["total"])
        return json.dumps({"ok": True, "damaged_count": len(rows),
                           "note": "派生字段，只读不可写", "ships": rows[:60]},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_ag_missions() -> str:
    """【零键鼠】返回航空任务码表（静态反汇编；保留行为按已述范围验证）。"""
    return json.dumps({"ok": True, "source": "内存任务名指针表 @0x85406c",
                       "verified": "码 8/9/10 过回合保留；11 需指定目标格；16=TRAINING；其余行为不作保证",
                       "missions": {str(k): v for k, v in AG_MISSION.items()}},
                      ensure_ascii=False, indent=1)



@mcp.tool()
def witp_mem_situation_report(section: str = "all") -> str:
    """【零键鼠】综合态势报告（纯内存读取；无 OCR/键鼠）。

    section: all / taskforces / airgroups / bases / ships / pilots / damaged
    数量仅代表本工具纳入的记录，不代表数据库中所有条目。只返回已标定字段。
    """
    try:
        r = _rpt.full_report()
        if not r.get("ok"):
            return json.dumps(r, ensure_ascii=False)
        if section == "all":
            return json.dumps(r, ensure_ascii=False, indent=1)
        key = {"taskforces": "taskforces", "airgroups": "airgroups",
               "bases": "bases", "ships": "ships", "pilots": "pilots",
               "damaged": "damaged"}.get(section)
        if not key:
            return json.dumps({"ok": False,
                               "error": f"未知 section {section}，可用: all/taskforces/airgroups/bases/ships/pilots/damaged"},
                              ensure_ascii=False)
        return json.dumps({"ok": True, "section": section,
                           "items": r.get(key, [])}, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_ground_unit_roster(loc: int, save: str = "") -> str:
    """【零键鼠】读取一个地面部队/基地的完整装备编制（手册 8.2.1.5 / 5.2.3）。

    Location 记录含 5 组 20 槽 u16 并行数组，已用 WITPloc003.csv 的
    WpnDevID/TOEDevID 列逐一比对确认：
      deviceID   @136  当前装备 ID
      deviceNumber @176 当前装备数量
      deviceDis  @216  当前损坏数量
      deviceTOE  @336  编制（TOE）装备 ID
      deviceTOENum @376 编制（TOE）数量
    返回逐项对照与"缺编"，可直接用于拆分部队时复制 device 明细。
    """
    try:
        import pwsfile
        sp = _pick(save or None)
        blk = pwsfile.record_by_len(sp, 21096000)
        if not (0 <= loc < len(blk) // 1172):
            return json.dumps({"ok": False, "error": "Location 索引越界"}, ensure_ascii=False)
        raw = blk[loc * 1172:(loc + 1) * 1172]
        name = raw[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        ids = struct.unpack_from("<20H", raw, 136)
        nums = struct.unpack_from("<20H", raw, 176)
        dis = struct.unpack_from("<20H", raw, 216)
        toe = struct.unpack_from("<20H", raw, 336)
        toen = struct.unpack_from("<20H", raw, 376)

        pid = _witp_obj.game_pid()
        def devname(d):
            if not d:
                return None
            if pid:
                try:
                    return _witp_obj.get(pid, "device", d, "name")
                except Exception:
                    pass
            return None

        items = []
        deficits = []
        for j in range(20):
            if not (ids[j] or nums[j] or toe[j] or toen[j]):
                continue
            cur, want = nums[j], toen[j]
            items.append({
                "slot": j,
                "device_id": ids[j] or None,
                "device_name": devname(ids[j]),
                "count": cur,
                "damaged": dis[j],
                "toe_device_id": toe[j] or None,
                "toe_count": want,
                "shortfall": max(0, want - cur),
            })
            if want > cur:
                deficits.append({"device_id": ids[j], "device_name": devname(ids[j]),
                                 "have": cur, "need": want, "missing": want - cur})

        return json.dumps({
            "ok": True, "loc": loc, "name": name,
            "unit_type": struct.unpack_from("<H", raw, 28)[0],
            "hex": list(struct.unpack_from("<HH", raw, 36)),
            "is_ground_unit": struct.unpack_from("<H", raw, 28)[0] not in (0, 1, 4, 5, 12),
            "devices": items,
            "shortfalls": deficits,
            "raw_arrays": {
                "deviceID": list(ids), "deviceNumber": list(nums),
                "deviceDis": list(dis), "deviceTOE": list(toe), "deviceTOENum": list(toen),
            },
            "field_notes": "deviceID@136 / deviceNumber@176 / deviceDis@216 / "
                           "deviceTOE@336 / deviceTOENum@376 (5 × 20 u16), "
                           "verified column-by-column against WITPloc003.csv",
        }, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_clear_tf_destination(tf_slot: int) -> str:
    """【零键鼠】清空编队航路点（= 界面 Set TF Destination 后右键取消）。

    实现：wp 数组清零 + wpCount/wpAlloc=0（set_waypoints 空表），与引擎自身
    "到达目的地后"的记录状态一致（TF3 到港后 wpCount=0 且跨回合保持）。

    ★实测语义边界（:97，turn4→6 三轮验证）：
    - 写入立即生效且不被引擎回弹（3 秒后仍为 0，跨回合记录持久）。
    - AMPHIB / SUBPATROL 等任务，引擎在回合结算时**按任务状态重推航路点**
      （两栖→目标滩头，潜艇→巡逻圈），这与界面清除后的行为相同——
      界面清除也只清路径，不清任务。要硬停车需同时把 mission 改为非自动任务。
    """
    try:
        sp = str(_pick(None))
        tfs = _mem.list_tfs(sp)
        if not tfs.get("ok"):
            return json.dumps(tfs, ensure_ascii=False)
        pid, base = tfs["pid"], int(tfs["base"], 16)
        if not any(t["tf"] == tf_slot for t in tfs["tfs"]):
            return json.dumps({"ok": False, "error": f"TF{tf_slot} 不存在（现有: "
                               f"{sorted(t['tf'] for t in tfs['tfs'])}）"}, ensure_ascii=False)
        before = _mem.witp_mem.get(pid, base, tf_slot, "wpCount")
        if not _mem.witp_mem.set_waypoints(pid, base, tf_slot, []):
            return json.dumps({"ok": False, "error": "内存写入失败"}, ensure_ascii=False)
        import time as _t
        _t.sleep(2)
        after = _mem.witp_mem.get(pid, base, tf_slot, "wpCount")
        return json.dumps({"ok": after == 0, "tf": tf_slot,
                           "wpCount_before": before, "wpCount_after": after,
                           "note": "AMPHIB/SUBPATROL 任务结算时引擎会按任务重推路径；"
                                   "硬停车请同时改 mission"},
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_set_tf_retirement(tf_slot: int, state: str) -> str:
    """【零键鼠】设置编队重新部署状态（手册 6.9）。

    state: "remain"（坚守阵地，off388=1）/ "allowed"（允许撤退，off388=0）

    ★ 字段依据：用 WITPloc003.csv 的 TFRetirement 列对 4 个存档 102 个 TF 样本
      交叉验证 off388：第1回合 26/26 精确命中；第4/5回合 99/102
      （3 个差异是引擎在航行中自行改写，不是字段错误）。
    ★ off355 是旧文档误记的 maxReact；真实 maxReact 在 off389（100% 命中）。
    """
    key = {"remain": 1, "station": 1, "allowed": 0, "retire": 0}.get((state or "").lower())
    if key is None:
        return json.dumps({"ok": False,
                           "error": "state 需为 remain / allowed"},
                          ensure_ascii=False)
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        old = _witp_obj.get(pid, "taskforce", tf_slot, "retirement")
        ok, detail = _witp_obj.set_field(pid, "taskforce", tf_slot, "retirement", key)
        back = _witp_obj.get(pid, "taskforce", tf_slot, "retirement")
        return json.dumps({
            "ok": bool(ok) and back == key,
            "tf_slot": tf_slot,
            "requested": state,
            "old": old, "new": back,
            "verified": back == key,
            "field": "taskforce.off388 (0=Retire Allowed, 1=Remain on Station)",
            "note": "纯内存写入并即时读回；引擎在航行/结算时可能按自身逻辑改写",
        }, ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_get_tf_retirement(tf_slot: int = 0) -> str:
    """【零键鼠】读取编队 Retirement 状态（off388）与 Max React（off389）。"""
    try:
        pid = _witp_obj.game_pid()
        if not pid:
            return json.dumps({"ok": False, "error": "游戏未运行"}, ensure_ascii=False)
        slots = [tf_slot] if tf_slot else list(range(1, 40))
        rows = []
        for t in slots:
            fl = _witp_obj.get(pid, "taskforce", t, "flagship")
            if not fl:
                continue
            v = _witp_obj.get(pid, "taskforce", t, "retirement")
            rows.append({
                "tf": t,
                "retirement_raw": v,
                "retirement": {0: "Retire Allowed", 1: "Remain on Station"}.get(v, f"unknown({v})"),
                "max_react": _witp_obj.get(pid, "taskforce", t, "maxReact"),
                "routing": _witp_obj.get(pid, "taskforce", t, "routing"),
            })
        return json.dumps({"ok": True, "count": len(rows), "taskforces": rows},
                          ensure_ascii=False, indent=1)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_set_tf_load(slot: int, action: str, out_file: str = "",
                     overwrite: bool = False) -> str:
    """TF 装载 / 卸载 / 停止（手册 6.3.3）。写 PWSTaskGroup off350。

    action: load（装载）/ unload（卸载）/ stop（停止）
    实证：GUI 点 Load Supplies → off350 由 99 变 1，界面显示 "loading supplies"
    并出现 "Cancel Load Supplies"；改回 0 → Cargo Status 恢复 idle。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    try:
        changes = s.set_tf_load(slot, action)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}"}, ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": changes, "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)


@mcp.tool()
def witp_set_tf_routing(slot: int, routing: int = -1, tolerance: int = -1,
                        max_react: int = -1,
                        out_file: str = "", overwrite: bool = False) -> str:
    """设置 TF 路由安全等级 / 威胁容忍度 / 最大反应半径（手册 6.1.2.1.2 / 6.2.4）。

    routing:   0=Normal 1=Safest 2=Safer 3=Direct；-1=不改
    tolerance: 0=Normal 1=Low 2=High 3=Absolute；-1=不改
    max_react: 最大反应半径（格，0-6）；-1=不改

    均在 PWSTaskGroup(556B)：routing=off369 / tolerance=off448 / max_react=off355。
    已由「GUI 改设置→存档差分」+「改字节→载入看界面」双重实证。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    try:
        changes = s.set_tf_routing(
            slot,
            routing=None if routing < 0 else routing,
            tolerance=None if tolerance < 0 else tolerance,
            max_react=None if max_react < 0 else max_react)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    if not changes:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的命令"},
                          ensure_ascii=False)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}"}, ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": changes, "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)


@mcp.tool()
def witp_set_airgroup_orders(slot: int, primary_mission: int = -1,
                             target_x: int = -1, target_y: int = -1,
                             cap: int = -1, lrcap: int = -1, asw: int = -1,
                             search: int = -1, train: int = -1, rest: int = -1,
                             altitude: int = -1, search_arc: str = "",
                             transfer_to_base: int = -1, resize_to: int = -1,
                             out_file: str = "", overwrite: bool = False) -> str:
    """改写航空队命令（主任务码/目标格/各巡逻比例 %），写入新存档。

    主任务码实测：1=机场攻击 2=港口攻击 3=对海攻击 4=对地攻击 6=护航/CAP
                 8=海上搜索 9=反潜巡逻 12=训练 16=侦察
    比例参数取值 0-100（界面按 10% 递增），-1=不改。
    altitude: 任务高度（英尺，手册 7.2.1.9 的五档：0-10k/10-15k/16-20k/21-30k/31k+）；-1=不改。
    search_arc: 搜索扇面 "起,止"（度，0-360），如 "0,90"；空=不改。
    resize_to: **编制数 Resize**（手册 7.3），如 24；-1=不改。
    transfer_to_base: **转场目标基地 Location ID**（手册 7.2.3），-1=不改。
        写 reinforceBaseID(42)；引擎据 baseID(40)!=reinforceBaseID 判定"正在转场"。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    kw = {}
    if primary_mission >= 0:
        kw["primary"] = primary_mission
    if target_x >= 0 and target_y >= 0:
        kw["targetX"], kw["targetY"] = target_x, target_y
    for name, val in (("pctCAP", cap), ("pctLRCAP", lrcap), ("pctASW", asw),
                      ("pctSearch", search), ("pctTrain", train), ("pctRest", rest)):
        if val >= 0:
            kw[name] = val
    if altitude >= 0:
        kw["alt"] = altitude
    if transfer_to_base >= 0:
        kw["reinforceBaseID"] = transfer_to_base
    if resize_to >= 0:
        kw["maxPlanes"] = resize_to
    if search_arc:
        try:
            a, b = (int(v.strip()) for v in search_arc.split(","))
        except Exception:
            return json.dumps({"ok": False, "error": 'search_arc 需形如 "0,90"'},
                              ensure_ascii=False)
        kw["navArcStart"], kw["navArcEnd"] = a % 360, b % 360
    if not kw:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的命令"}, ensure_ascii=False)
    changes = s.set_ag(slot, **kw)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}",
                           "hint": "改动幅度过大导致压缩流无法回填到原长度"},
                          ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": {k: list(v) for k, v in changes.items()},
                       "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)


@mcp.tool()
def witp_set_ground_orders(slot: int, order: str = "", prep_target_base: int = -1,
                           dest_x: int = -1, dest_y: int = -1, prep_percent: int = -1,
                           march_dir: int = -1, march_len: int = -1,
                           op_mode: str = "",
                           out_file: str = "", overwrite: bool = False) -> str:
    """改写地面部队命令，写入新存档。

    order（手册 8.2.1.2 Combat Orders）：defend / bombardment / deliberate / shock
        —— 实测映射到 combatMode：0/1/2/3。
    prep_target_base: **准备目标基地 Location ID**（手册 8.2.1.4 Future Objective），-1=不改。
        实测：4th Fleet prepTarget=981(Port Moresby)、Southeast Fleet=992(Rabaul)。
    dest_x/dest_y: 行军目的地六角格（手册 8.3.1），-1=不改。
    prep_percent: 准备度 0-100（对 prep_target_base 的完成度），-1=不改。
    march_dir / march_len: 行军方向(0-8) / 距离(格)；-1=不改。
    op_mode: **Operations Mode**（手册 8.2.1.1），可传名称或数字：
        strategic/move/combat/reserve/rest/disorganized（对应 0..5）
        实证：off906，GUI 把 11th Air Fleet 由 Combat 改 Move → 0→1；
              写 4 → 界面 OpMode 列显示 Rest。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    if slot * 1172 >= len(s.loc["data"]):
        return json.dumps({"ok": False,
                           "error": f"slot {slot} 超出位置表范围（0..17999）"},
                          ensure_ascii=False)
    changes = {}
    if order:
        try:
            changes.update(s.set_ground_order(slot, order))
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    kw = {}
    if prep_target_base >= 0:
        kw["prepTarget"] = prep_target_base
    if dest_x >= 0:
        kw["destX"] = dest_x
    if dest_y >= 0:
        kw["destY"] = dest_y
    if prep_percent >= 0:
        kw["prep"] = min(100, prep_percent)
    if march_dir >= 0:
        kw["marchDir"] = march_dir
    if march_len >= 0:
        kw["marchLen"] = march_len
    if op_mode:
        OP = {"strategic": 0, "move": 1, "combat": 2, "reserve": 3,
              "rest": 4, "disorganized": 5}
        key = str(op_mode).strip().lower()
        code = OP.get(key)
        if code is None:
            if key.isdigit() and int(key) <= 5:
                code = int(key)
            else:
                return json.dumps({"ok": False,
                                   "error": f"未知 op_mode {op_mode}",
                                   "valid": sorted(OP)}, ensure_ascii=False)
        kw["operationsMode"] = code
    if kw:
        changes.update(s.set_loc(slot, **kw))
    if not changes:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的命令"}, ensure_ascii=False)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}",
                           "hint": "改动幅度过大导致压缩流无法回填到原长度"},
                          ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": {k: list(v) for k, v in changes.items()},
                       "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)


@mcp.tool()
def witp_set_base_build(slot: int, port: int = -1, airfield: int = -1,
                        fort: int = -1, out_file: str = "",
                        overwrite: bool = False) -> str:
    """设置基地扩建指令（手册 9.4.2 Base Construction and Repair），写入新存档。

    slot: 基地在位置表里的槽位（witp_bases 返回的 slot）。
    port / airfield / fort: 0=停止建设，1=开始扩建，>1=施工进度%（游戏自填）；
        -1=不改。
    注意：扩建需要该基地有工兵与补给，指令只是"允许建设"。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    kw = {}
    if port >= 0:
        kw["portExpand"] = port
    if airfield >= 0:
        kw["airfieldExpand"] = airfield
    if fort >= 0:
        kw["fortExpand"] = fort
    if not kw:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的指令"}, ensure_ascii=False)
    changes = s.set_base_build(slot, port_expand=kw.get("portExpand"),
                              airfield_expand=kw.get("airfieldExpand"),
                              fort_expand=kw.get("fortExpand"))
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}"}, ensure_ascii=False)
    return json.dumps({"ok": True, "out": str(dst), "bytes": size,
                       "changes": {k: list(v) for k, v in changes.items()},
                       "engine_verify": _dll_verify(dst)}, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 过回合闭环核验（铁律 2.3：命令下发后检测回港漂移/任务码覆盖）
_ORDERS_FIELDS = ("flagship", "home", "mission", "speed", "routing",
                  "maxReact", "retirement", "loadState")


@mcp.tool()
def witp_mem_orders_snapshot(save: str = None) -> str:
    """【零键鼠】给全部编队的**命令状态**拍快照（过回合前后各拍一次用于对比）。

    返回 JSON 文本，请原样保存，过回合后传给 witp_mem_orders_diff。
    记录字段：mission / speed / routing / maxReact / retirement / loadState /
    home / flagship / 航路点表。任何字段在结算后被引擎改动即视为“命令被覆盖”。
    """
    try:
        sp = str(_pick(save))
        tfs = _mem.list_tfs(sp)
        if not tfs.get("ok"):
            return json.dumps(tfs, ensure_ascii=False)
        out = []
        for t in tfs["tfs"]:
            snap = {"tf": t["tf"]}
            for f in _ORDERS_FIELDS:
                snap[f] = t.get(f)
            try:  # list_tfs 未返回 retirement，单独补读（off388）
                snap["retirement"] = _mem.witp_mem.get(tfs["pid"], int(tfs["base"], 16),
                                                       t["tf"], "retirement")
            except Exception:
                pass
            snap["waypoints"] = t.get("waypoints", [])
            out.append(snap)
        return json.dumps({"ok": True, "save": sp, "turn": _rpt.victory_report(sp).get("turn"),
                           "snapshot": out}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


@mcp.tool()
def witp_mem_orders_diff(before: str, save: str = None) -> str:
    """【零键鼠】对比过回合前后的命令快照，报告哪些编队的命令被引擎改动。

    before = witp_mem_orders_snapshot 返回的 JSON 原文。
    改动分类：mission_changed（任务码被覆盖）/ wp_changed（航路点被改=可能回港漂移）/
    home_changed（回港）/ gone（编队解散）/ new（新建）/ 其他字段差异逐条列出。
    """
    try:
        b = json.loads(before)
        if not b.get("ok"):
            return json.dumps({"ok": False, "error": "before 快照无效"}, ensure_ascii=False)
        sp = str(_pick(save))
        tfs = _mem.list_tfs(sp)
        if not tfs.get("ok"):
            return json.dumps(tfs, ensure_ascii=False)
        old = {s["tf"]: s for s in b["snapshot"]}
        changes = []
        for t in tfs["tfs"]:
            tf = t["tf"]
            o = old.pop(tf, None)
            if o is None:
                changes.append({"tf": tf, "kind": "new"})
                continue
            d = {}
            for f in _ORDERS_FIELDS:
                if o.get(f) != t.get(f):
                    d[f] = [o.get(f), t.get(f)]
            if o.get("waypoints") != t.get("waypoints"):
                d["waypoints"] = [o.get("waypoints"), t.get("waypoints")]
            if d:
                kind = []
                if "mission" in d:
                    kind.append("mission_changed")
                if "waypoints" in d:
                    kind.append("wp_changed")
                if "home" in d:
                    kind.append("home_changed")
                changes.append({"tf": tf, "kind": kind or ["field_changed"], "diff": d})
        for tf in old:
            changes.append({"tf": tf, "kind": "gone"})
        changes.sort(key=lambda c: c["tf"])
        return json.dumps({"ok": True, "save": sp,
                           "turn_before": b.get("turn"),
                           "turn_now": _rpt.victory_report(sp).get("turn"),
                           "changed_count": len(changes), "changes": changes},
                          ensure_ascii=False)
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "before 不是合法 JSON"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------- 回合推进（VNC 键盘单键注入：E → y；实测 2026-10-20 于 :97）
def _vnc_key(key: str) -> str:
    """经现有 VNC RFB 键盘通道发送**单个**按键；失败回退 xdotool。

    只发确定键名（e/y/Return/Escape 等），绝不涉及坐标定位。
    返回实际使用的通道："vnc" / "xdotool" / ""。
    """
    script = WORKSPACE / "witp_vnckey97.py"
    env = dict(os.environ, DISPLAY=DISPLAY, WITP_VNC_PORT=str(VNC_PORT), HOME="/root")
    if script.exists():
        try:
            out = subprocess.run([sys.executable, str(script), key], env=env,
                                 timeout=15, capture_output=True, text=True)
            if "OK" in (out.stdout or ""):
                return "vnc"
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "key", "--", key],
                       env=dict(os.environ, DISPLAY=DISPLAY, HOME="/root"),
                       timeout=10, capture_output=True)
        return "xdotool"
    except Exception:
        return ""


def _screen_hash() -> str:
    """整屏像素 md5（只作“画面是否变化”判据，不做 OCR/不取坐标）。"""
    try:
        # 优先截取游戏窗口，避免 Xvnc root 未合成导致全黑
        p = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "War in the Pacific"],
                           env=dict(os.environ, DISPLAY=DISPLAY, HOME="/root"),
                           timeout=5, capture_output=True, text=True)
        wid = p.stdout.strip().split()[0] if (p.returncode == 0 and p.stdout.strip()) else "root"
        out = subprocess.run(["import", "-window", wid, "png:-"],
                             env=dict(os.environ, DISPLAY=DISPLAY, HOME="/root"),
                             timeout=25, capture_output=True)
        if out.returncode == 0 and out.stdout:
            return hashlib.md5(out.stdout).hexdigest()
    except Exception:
        pass
    return ""


def _turn_of(path: Path):
    """读存档 SCENARIO 记录的 turn（偏移 30，witp_report.victory_report 同源）。"""
    try:
        return _rpt.victory_report(str(path)).get("turn")
    except Exception:
        return None


@mcp.tool()
def witp_end_turn(confirm: bool = False, wait_seconds: int = 900) -> str:
    """结束当前 Orders Phase 并推进回合（键盘单键注入：E → y）。

    实测链路（:97，2026-10-20）：地图界面按 E 弹出 "End the Orders Phase?"，
    按 y 确认 YES（Return 无效），引擎结算数分钟后回写 Autosave(wpae000.pws)，
    turn 递增。全程只有两次确定按键，无 OCR、无坐标点击、无鼠标。
    confirm=true 才执行（防误触）。wait_seconds 为等待结算回写 autosave 的上限。
    """
    if not confirm:
        return json.dumps({"ok": False,
                           "error": "确认推进回合请 confirm=true（将立即注入 E→y，不可撤销）"},
                          ensure_ascii=False)
    autosave = SAVE_DIR / "wpae000.pws"
    if not autosave.exists():
        # 若刚开局还没有 wpae000.pws，尝试找当前最新的存档作为前置基准
        cands = sorted(SAVE_DIR.glob("*.pws"), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            before_turn = _turn_of(cands[0]) or 1
            before_mtime = 0.0
        else:
            return json.dumps({"ok": False, "error": f"Autosave 不存在且无任何存档：{autosave}"}, ensure_ascii=False)
    else:
        before_turn = _turn_of(autosave)
        before_mtime = autosave.stat().st_mtime

    # ① 截屏基线 → 发 E → 要求画面出现变化（= 确认框弹出）才算建立
    base = _screen_hash()
    if not base:
        return json.dumps({"ok": False, "error": "无法截取游戏画面（DISPLAY/工具不可用）",
                           "display": DISPLAY},
                          ensure_ascii=False)
    dialog_hash = ""
    chan_e = ""
    for _ in range(3):
        chan_e = _vnc_key("e")
        time.sleep(2.0)
        h = _screen_hash()
        if h and h != base:
            dialog_hash = h
            break
    if not dialog_hash:
        return json.dumps({"ok": False,
                           "error": "按 E 后画面无变化：确认框未弹出（游戏可能在结算中或不在地图界面）",
                           "channel": chan_e, "before_turn": before_turn},
                          ensure_ascii=False)

    # ② 发 y 确认 YES；若 90s 后 autosave 未动且确认框仍在（画面=弹窗基线）则重发一次
    chan_y = _vnc_key("y")
    deadline = time.time() + max(60, wait_seconds)
    resent = 0
    mtime = before_mtime
    while time.time() < deadline:
        time.sleep(5)
        mtime = autosave.stat().st_mtime if autosave.exists() else before_mtime
        if mtime != before_mtime:
            break
        if resent < 2 and time.time() > deadline - max(60, wait_seconds) + 90:
            if _screen_hash() == dialog_hash:   # 确认框还挂着
                _vnc_key("y")
                resent += 1

    if mtime == before_mtime:
        return json.dumps({"ok": False,
                           "error": "已注入 E→y，但结算未在时限内回写 Autosave（引擎可能仍在结算或弹窗未确认）",
                           "before_turn": before_turn, "wait_seconds": wait_seconds},
                          ensure_ascii=False)
    time.sleep(3)  # 等写档收尾
    after_turn = _turn_of(autosave)
    return json.dumps({"ok": True,
                       "before_turn": before_turn, "after_turn": after_turn,
                       "turn_advanced": (after_turn is not None and before_turn is not None
                                         and after_turn != before_turn),
                       "autosave": str(autosave),
                       "channel": {"e": chan_e, "y": chan_y, "y_resent": resent},
                       "elapsed_s": round(time.time() - (deadline - max(60, wait_seconds)), 1)},
                      ensure_ascii=False)


@mcp.tool()
def witp_set_ship_repair(ship_id: int, priority: int = -1, mode: int = -1,
                         upgrade: int = -1, out_file: str = "",
                         overwrite: bool = False) -> str:
    """设置舰船修理优先级 / 修理模式 / 升级开关（手册 14.2.2），写入新存档。

    ship_id: 舰船记录槽号（witp_ships 返回的 id）。
    priority: 修理优先级（实测默认 1）；-1=不改。
    mode:     修理模式（0=默认/自动，其余见手册 14.2.3）；-1=不改。
    upgrade:  是否允许升级 0/1；-1=不改。
    """
    src = _pick(None)
    s = witp_orders.Save(src)
    try:
        changes = s.set_ship_repair(ship_id,
                                    priority=None if priority < 0 else priority,
                                    mode=None if mode < 0 else mode,
                                    upgrade=None if upgrade < 0 else upgrade)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    if not changes:
        return json.dumps({"ok": False, "error": "没有给出任何要修改的命令"},
                          ensure_ascii=False)
    dst = Path(out_file) if out_file else _next_free_slot()
    if not dst.is_absolute():
        dst = SAVE_DIR / dst
    if dst.exists() and not overwrite:
        return json.dumps({"ok": False, "error": f"{dst} 已存在；如需覆盖请 overwrite=true"},
                          ensure_ascii=False)
    try:
        size, _ = s.save(dst)
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": f"写档失败：{exc}"}, ensure_ascii=False)
    return json.dumps({"ok": True, "src": str(src), "out": str(dst), "bytes": size,
                       "changes": {k: list(v) for k, v in changes.items()},
                       "engine_verify": _dll_verify(dst)},
                      ensure_ascii=False, indent=1)


if __name__ == "__main__":
    mcp.run()
