"""
WitP-AE 莫尔兹比港（PM, 98,130）状态感知

两个判据，各自独立、互不替代：

1. **归属**：以 `bases.json` 的 `area_command`（该基地隶属的指挥部名）为准。
   ⚠️ **不得用 `nation`**：基地被占领后 `nation` 仍是原属国（PM 易主后仍写 AUSTRALIAN），
   只有 `area_command` 会切换到占领方指挥部（盟军 = Southwest Pacific / 日军 = Southeast Fleet）。
   ⚠️ **不得用「PM 是否出现在本方基地段」**：读层的本方基地段在 PM 易主后**仍会列出 PM**。

2. **登陆进程**：按战报标志词分级（越靠后越严重）。
   只读当前回合及前 3 个游戏日的战报，避免读到上一局的残留文件。

本模块被 witp_staff.py 复用，用于决定航母前推位的激进程度。
"""
import os
import re
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

PM_HEX = (98, 130)
RABAUL_HEX = (106, 125)
GAMESATA_RING_ANCHOR = (102, 129)   # 第七局 Lexington 战沉处（俾斯麦海/Gasmata 岸基轰炸圈）

GAME_SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
STATE_DIR = os.path.join(READER_DIR, "state")

# 日军指挥部名关键字（判定基地已被日军占领）
JP_HQ_KEYWORDS = ("Southeast Fleet", "Fourth Fleet", "Combined Fleet", "Southwest Area Fleet",
                  "Southern Army", "8th Fleet", "Southeast Area Fleet", "Imperial")
# 盟军指挥部名关键字
AL_HQ_KEYWORDS = ("Southwest Pacific", "South Pacific", "Central Pacific", "North Pacific",
                  "Australia", "New Zealand", "ANZAC", "ABDA", "USAFFE", "Hawaiian",
                  "West Coast", "Southeast Asia", "Southwest")

# 登陆进程分级：数值越大越严重
LANDING_MARKS = [
    (4, "Ground combat at Port Moresby", "已上岸并地面交战"),
    (3, "troops unloading over beach at Port Moresby", "部队正在卸载（最紧急）"),
    (2, "Amphibious Assault at Port Moresby", "两栖突击进行中"),
    (1, "Pre-Invasion action off Port Moresby", "登陆前火力准备"),
    (1, "Invasion Support action off Port Moresby", "登陆支援行动"),
]


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return __import__("json").load(f)
    except Exception:
        return None


def read_pm_owner(state_dir: Optional[str] = None) -> Tuple[str, str, str]:
    """返回 (owner, area_command, 说明)。owner ∈ {'allied','japan','unknown'}"""
    state_dir = state_dir or STATE_DIR
    bases = _read_json(os.path.join(state_dir, "bases.json")) or []
    for b in bases:
        if (b.get("x"), b.get("y")) == list(PM_HEX) or b.get("name") == "Port Moresby":
            hq = str(b.get("area_command") or "").strip()
            if any(k in hq for k in JP_HQ_KEYWORDS):
                return "japan", hq, f"PM 隶属指挥部 = {hq}（日军）"
            if any(k in hq for k in AL_HQ_KEYWORDS):
                return "allied", hq, f"PM 隶属指挥部 = {hq}（盟军）"
            return "unknown", hq, f"PM 隶属指挥部 = {hq or '未记录'}（无法判定）"
    return "unknown", "", "bases.json 中未找到 PM（98,130）条目"


def _dates_back(date_str: str, n: int):
    """把 turn.json 的 '05/15/42' 形式日期往前推 n 天，返回 ['420515', ...]"""
    out = []
    m = re.match(r"(\d{2})/(\d{2})/(\d{2})", str(date_str or ""))
    if not m:
        return out
    mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        d = datetime(2000 + yy, mm, dd)
    except ValueError:
        return out
    for i in range(n):
        out.append((d - timedelta(days=i)).strftime("%y%m%d"))
    return out


def read_pm_landing(save_dir: Optional[str] = None,
                    turn_date: Optional[str] = None) -> Tuple[int, str, str]:
    """返回 (stage, 说明, 证据文件名)。stage=0 表示未发现登陆迹象。"""
    save_dir = save_dir or GAME_SAVE_DIR
    # 窗口取「当前回合 + 前 5 个游戏日」：一次两栖登陆从接近到完成通常持续 2~3 天，
    # 3 天窗口会漏掉登陆首日的 Pre-Invasion action，故放宽到 6 天。
    dates = _dates_back(turn_date or "", 6)
    if not dates:   # 无日期信息时不猜，直接报未知
        return 0, "无法确定游戏日期，未读取战报（不猜）", ""

    best, desc, evid = 0, "未发现登陆迹象", ""
    for d in dates:
        for pat in (f"combatreport_{d}.txt", f"aoperationsreport_{d}.txt"):
            path = os.path.join(save_dir, pat)
            if not os.path.exists(path):
                continue
            try:
                # 路径含单引号（Admiral's Edition）→ 必须用双引号包裹，
                # 否则 shell 引号截断、iconv 静默失败，检测恒为 False（已踩坑两次）
                txt = subprocess.run(f'iconv -f GBK -t UTF-8 "{path}"',
                                     shell=True, capture_output=True, text=True,
                                     timeout=30).stdout
            except Exception:
                continue
            for lvl, mark, label in LANDING_MARKS:
                if mark in txt and lvl > best:
                    best, desc, evid = lvl, label, pat
    return best, desc, evid


def read_pm_status(save_dir: Optional[str] = None,
                   state_dir: Optional[str] = None,
                   turn_date: Optional[str] = None) -> Dict[str, Any]:
    """汇总 PM 状态。

    返回：
      owner / area_command / owner_note
      landing_stage(0-4) / landing_desc / landing_evidence
      pm_at_risk(bool)  —— 第一级（死守 PM）是否正被直接挑战
      level1_active(bool) —— 第一级手段是否必须投入（PM 未失守 且 有登陆迹象）
    """
    if turn_date is None:
        t = _read_json(os.path.join(state_dir or STATE_DIR, "turn.json")) or {}
        turn_date = t.get("game_date") or ""

    owner, hq, owner_note = read_pm_owner(state_dir)
    stage, desc, evid = read_pm_landing(save_dir, turn_date)

    pm_at_risk = (stage >= 1) or (owner == "japan")
    # 严格字典序：只有「PM 未失守」的前提下才谈保航母；
    # 因此 PM 仍属盟军且发现登陆迹象时，第一级手段必须投入。
    level1_active = (owner == "allied" and stage >= 1)

    return {
        "hex": list(PM_HEX),
        "owner": owner,
        "area_command": hq,
        "owner_note": owner_note,
        "landing_stage": stage,
        "landing_desc": desc,
        "landing_evidence": evid,
        "pm_at_risk": pm_at_risk,
        "level1_active": level1_active,
        "turn_date": turn_date,
    }
