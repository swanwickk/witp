"""
WitP-AE Perception Layer
Extracts the ground-truth state S_t by wrapping witp_read.sh and loading parsed JSONs.
Produces normalized dictionaries of TaskForces, Ships, Bases, Airgroups, Threats, and Turn metadata.
Supports all WitP scenarios dynamically without hardcoded dates or scenario names.
"""
import os
import json
import subprocess
import sys
from typing import Dict, Any, Optional

READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
READ_SCRIPT = os.path.join(READER_DIR, "witp_read.sh")
STATE_DIR = os.path.join(READER_DIR, "state")

def _load_json_tolerant(path, health=None, label=""):
    """容错加载 state JSON。

    背景（2026-09-25 实测）：witp-watcher 与手动 staff --save 可能**并发运行读层**，
    导致 state/*.json 出现「完整 JSON + 尾部残留半段」的脏文件（实测 airgroups.json 尾部多出 81KB），
    此时 json.load 抛 'Extra data'，参谋部会静默拿不到航空队数据（搜索方案为空）。
    对策：先按标准解析；失败则用 raw_decode 取**第一个完整 JSON 值**，并记入健康告警。
    """
    import json as _json
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return _json.load(f)
    except Exception as e1:
        try:
            raw = open(path, "r", encoding="utf-8", errors="replace").read().lstrip()
            obj, idx = _json.JSONDecoder().raw_decode(raw)
            if health is not None:
                health.setdefault("warnings", []).append(
                    f"{label or path} 含尾部冗余数据（疑似读层并发写，共 {len(raw) - idx} 字节）"
                    f"—— 已按首个完整 JSON 解析（数据可用）")
            return obj
        except Exception as e2:
            if health is not None:
                health["warnings"].append(f"{label or path} 解析失败: {e2}（原始错误: {e1}）")
            return None


def capture_state(save_path: Optional[str] = None, run_scraper: bool = False) -> Dict[str, Any]:
    """
    Run witp_read.sh (if run_scraper is True) and load the generated JSON states.
    Returns structured S_t dictionary.

    第六局修复：读层失败或输出陈旧时**不再静默返回旧 state/**，而是:
      1. 记录读层子进程的 stdout/stderr 与退出码；
      2. 校验 turn.json 的 game_date/game_turn 是否与目标存档头一致；
      3. 不一致时在 state["perception_health"] 里明确标记 stale，让上层拒绝采信。
    """
    state = {
        "turn": {
            "game_date": "未知",
            "game_turn": 1,
            "scenario_name": "未知剧本",
            "header_comment": ""
        },
        "taskforces": [],
        "airgroups": [],
        "ships": [],
        "bases": [],
        "threats": {},
        "brief": "",
        "perception_health": {
            "scraper_ran": bool(run_scraper),
            "scraper_ok": None,
            "state_fresh": None,
            "warnings": []
        }
    }
    health = state["perception_health"]

    if run_scraper:
        cmd = [READ_SCRIPT]
        if save_path:
            cmd.append(save_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            health["scraper_ok"] = proc.returncode == 0
            if proc.returncode != 0:
                health["warnings"].append(
                    f"读层返回码 {proc.returncode}: {(proc.stderr or proc.stdout or '')[:200]}")
        except Exception as exc:
            health["scraper_ok"] = False
            health["warnings"].append(f"读层执行异常: {exc}")

    # 若指定了存档但读层失败，明确拒绝返回陈旧 state
    if save_path and health["scraper_ok"] is False:
        health["state_fresh"] = False
        health["warnings"].append("读层失败，拒绝返回可能陈旧的 state/ 数据")
        return state

    # 1. Load brief.txt
    brief_file = os.path.join(STATE_DIR, "brief.txt")
    if os.path.exists(brief_file):
        with open(brief_file, "r", encoding="utf-8", errors="replace") as f:
            state["brief"] = f.read()

    # 2. Load turn.json (Extract game_date, game_turn, scenario_name accurately)
    turn_file = os.path.join(STATE_DIR, "turn.json")
    if os.path.exists(turn_file):
        try:
            with open(turn_file, "r", encoding="utf-8") as f:
                t_raw = json.load(f)
                state["turn"] = {
                    "game_date": t_raw.get("game_date") or t_raw.get("date") or "未知",
                    "game_turn": t_raw.get("game_turn") or t_raw.get("turn") or 1,
                    "scenario_name": t_raw.get("scenario_name") or "未知剧本",
                    "header_comment": t_raw.get("header_comment", "")
                }
        except Exception as exc:
            health["warnings"].append(f"turn.json 解析失败: {exc}")

    # 2b. 校验 state 新鲜度：与目标存档头的日期比对
    if save_path and os.path.isfile(save_path):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from witp_saves import parse_save_meta
            meta = parse_save_meta(save_path)
            meta_date = meta.get("date")          # 形如 05/15/42
            cur_date = state["turn"]["game_date"]  # 形如 05/15/42
            if meta_date and cur_date and meta_date != cur_date:
                health["state_fresh"] = False
                health["warnings"].append(
                    f"存档日期 {meta_date} 与 state/ 日期 {cur_date} 不一致——state/ 可能陈旧")
            else:
                health["state_fresh"] = True
        except Exception as exc:
            health["state_fresh"] = None
            health["warnings"].append(f"存档元信息比对失败: {exc}")

    # 3. Load taskforces.json
    tf_file = os.path.join(STATE_DIR, "taskforces.json")
    if os.path.exists(tf_file):
        try:
            with open(tf_file, "r", encoding="utf-8") as f:
                state["taskforces"] = _load_json_tolerant(tf_file, health, "taskforces.json")
        except Exception:
            pass

    # 4. Load airgroups.json
    ag_file = os.path.join(STATE_DIR, "airgroups.json")
    if os.path.exists(ag_file):
        try:
            with open(ag_file, "r", encoding="utf-8") as f:
                state["airgroups"] = _load_json_tolerant(ag_file, health, "airgroups.json")
        except Exception:
            pass

    # 5. Load ships.json
    ships_file = os.path.join(STATE_DIR, "ships.json")
    if os.path.exists(ships_file):
        try:
            with open(ships_file, "r", encoding="utf-8") as f:
                state["ships"] = _load_json_tolerant(ships_file, health, "ships.json")
        except Exception:
            pass

    # 6. Load bases.json
    bases_file = os.path.join(STATE_DIR, "bases.json")
    if os.path.exists(bases_file):
        try:
            with open(bases_file, "r", encoding="utf-8") as f:
                state["bases"] = _load_json_tolerant(bases_file, health, "bases.json")
        except Exception:
            pass

    # 7. Load threats.json
    threat_file = os.path.join(STATE_DIR, "threats.json")
    if os.path.exists(threat_file):
        try:
            with open(threat_file, "r", encoding="utf-8") as f:
                state["threats"] = _load_json_tolerant(threat_file, health, "threats.json")
        except Exception:
            pass

    return state
