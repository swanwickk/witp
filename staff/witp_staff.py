#!/usr/bin/env python3
"""
WitP-AE 作战参谋本部核心引擎 (Universal / Scenario-Agnostic)
支持太平洋战争全剧本推演（无论全战役001、八纮一宇002、珊瑚海003、瓜岛004、马里亚纳011等）：
1. 动态自适应当前剧本名、当前推演日期、当前实际敌我编制与战场接触
2. 融合 SKB 战略教条，调用云端大模型 (System 2) 与本地 Kev-0.8B (System 1)
3. 出具公文级《作战方案建议书》，提交给前线主 Agent 审核与执行
4. 绝不盲动游戏外设，专注做好前线指挥官的智囊参谋
"""

import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import yaml
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from witp_saves import list_saves, resolve_save, SAVE_DIR
from witp_models import resolve_model_spec

from lib import (
    hex_math,
    fuel_calc,
    option_builder,
    verify,
    belief_update,
    perception,
    pm_status as pm_status_mod,
    carrier_station as carrier_station_mod,
    recon as recon_mod,
    theater as theater_mod,
)
from lib.hex_math import hex_distance

CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
SKB_DIR = os.path.join(BASE_DIR, "skb")
GAMES_DIR = os.path.join(BASE_DIR, "games")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

def _find_active_game_id() -> str:
    """自动查找当前活跃的对局目录（GAMES_DIR 下最新的非归档 game-* 目录）。"""
    import glob
    if os.path.isdir(GAMES_DIR):
        dirs = sorted(
            [d for d in glob.glob(os.path.join(GAMES_DIR, "game-*")) if os.path.isdir(d) and not d.endswith("_archive")],
            key=os.path.getmtime,
            reverse=True,
        )
        if dirs:
            return os.path.basename(dirs[0])
    return "game-001"

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def load_skb() -> Dict[str, Any]:
    skb = {"doctrines": "", "patterns": [], "eval_weights": {}}
    doc_path = os.path.join(SKB_DIR, "doctrines.md")
    if os.path.exists(doc_path):
        with open(doc_path, "r", encoding="utf-8") as f:
            skb["doctrines"] = f.read()
    pat_path = os.path.join(SKB_DIR, "patterns.json")
    if os.path.exists(pat_path):
        with open(pat_path, "r", encoding="utf-8") as f:
            skb["patterns"] = json.load(f)
    weight_path = os.path.join(SKB_DIR, "eval_weights.json")
    if os.path.exists(weight_path):
        with open(weight_path, "r", encoding="utf-8") as f:
            skb["eval_weights"] = json.load(f)
    return skb

def tf_label(t: dict) -> str:
    """编队标识：游戏内 TF 编号 = record_id；显示名用旗舰名。"""
    rid = t.get("record_id")
    flag = t.get("flagship_name") or "?"
    return f"TF{rid}（旗舰 {flag}）" if rid is not None else f"未知编队（旗舰 {flag}）"


def tf_cmd_id(t: dict) -> str:
    """可直接用于 witp-cmd set-dest 的编队编号。"""
    rid = t.get("record_id")
    return f"TF{rid}" if rid is not None else ""


def ag_label(a: dict) -> str:
    """航空队标识：优先中队名，否则用 record_id。"""
    nm = a.get("name")
    rid = a.get("record_id")
    if nm:
        return f"{nm}（id {rid}）" if rid is not None else str(nm)
    return f"AG#{rid}" if rid is not None else "未知中队"


def _player_side() -> str:
    """当前人类执哪一方（读 witp-reader/side.txt，与 theater 同一权威来源）。"""
    try:
        with open("/root/.hermes/profiles/witp/workspace/witp-reader/side.txt", encoding="utf-8") as f:
            s = f.read().strip().upper()
        if s in ("JAPAN", "ALLIED"):
            return s
    except Exception:
        pass
    return "ALLIED"


def _build_commander_priority() -> str:
    """三级优先级（严格字典序），**按当前阵营自适应**。

    ★2026-10-14 新增★ 旧实现把它写死为「①死守莫尔兹比港」= 盟军视角。
      人类执日军时一级目标恰恰相反（**攻占 PM** 是剧本胜负手），
      写死的框架会与局势矛盾，误导模型。
    """
    if _player_side() == "JAPAN":
        return (
            "严格字典序（层层递减）：①**攻占莫尔兹比港（98,130）**——这是本剧本日军获胜的胜负手；"
            "手段优先级：舰炮击压制 > 陆攻对地轰炸 > 两栖登陆后地面攻击（Deliberate 磨至 fort 0、"
            "odds≥2:1 一击而下，**严禁连打 Shock**）；两栖船团与炮击编队到位前，航母负责掩护登陆；"
            "②保住我方航母——**以「①可继续执行」为前提的条件性目标，无权否决第一级**；"
            "③猎杀敌航母——**一旦出现打击盟军航母的机会，必须毫不犹豫立即出击**"
            "（击沉敌航母可大幅拉开 VP 差距）。"
            "⚠️ 不得以「保航母」为由拒绝掩护登陆或拒绝前推。"
        )
    return (
        "严格字典序（层层递减）：①死守莫尔兹比港（98,130）——PM 未失守时这是唯一一级目标，"
        "陆基掠桅轰炸 > 水面夜袭拦截 > 航母舰载机，前两级不足时必须投入航母，"
        "**不得以「保航母」为由拒绝出动或拒绝前推**；"
        "②保住我方航母——**以「PM 未失守」为前提的条件性目标，无权否决第一级**；"
        "③只有①未被违反且②成立才猎杀敌航母；"
        "**且一旦出现打击日军航母的机会，必须毫不犹豫立即出击（不得以保航母为由犹豫或缺席）**。"
    )


# ─────────── ★2026-09-26 新增：己方兵力态势（补上参谋部「只讲敌情」的缺口）★ ───────────
#   来历：第十三局 05/06 回合，参谋部方案书通篇只讲敌情，**没有一句话说"我方现有航母几艘"**；
#   而 Lexington 已于 05/05 被击沉（读层/战报可查），指挥层据此执行了以 1 对 2 的航母突击，
#   Yorktown 中弹、突击队损失约 22 架。故把己方兵力显式注入提示词与输出。
_OWN_SHIPS_JSON = "/root/.hermes/profiles/witp/workspace/witp-reader/state/ships.json"


def build_own_posture() -> Dict[str, Any]:
    """统计我方兵力（重点：可用航母数量与伤情）。

    舰种判据用读层的 `ship_class_type_name`（实测 CV / CA / DD / SS / AO…）；
    ★不要用 airgroups 判航母★——巡洋舰也带 4 架水上侦察机，会误判成航母。
    """
    try:
        with open(_OWN_SHIPS_JSON, encoding="utf-8") as f:
            ships = json.load(f)
    except Exception as e:
        return {"ok": False, "err": str(e)}
    cvs, types = [], {}
    for s in ships:
        t = str(s.get("ship_class_type_name") or "").upper()
        rec = {"name": s.get("name"), "type": t, "tf": s.get("task_force_id"),
               "pos": [s.get("x"), s.get("y")],
               "sys": s.get("Sys"), "flt": s.get("Flt"),
               "fire": s.get("Fire"), "eng": s.get("Eng"),
               "cap": s.get("aircraft_capacity")}
        rec["dmg"] = (rec["sys"] or 0) + (rec["flt"] or 0) + (rec["eng"] or 0)
        if t.startswith("CV"):
            cvs.append(rec)
        else:
            types[t] = types.get(t, 0) + 1
    unarmed = [c for c in cvs if c["dmg"] <= 15]
    return {"ok": True, "carriers": cvs, "carrier_count": len(cvs),
            "carriers_fit": [c["name"] for c in unarmed],
            "other_types": types}


def call_strategic_model(prompt_data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    strat_cfg = config.get("strategy_model", {})
    api_key = strat_cfg.get("api_key", "").strip()
    base_url = strat_cfg.get("base_url", "").strip().rstrip("/")
    model = strat_cfg.get("model", "step-5-preview")

    # 主模型 + fallbacks 依次尝试（第六局新增）
    candidates = [dict(base_url=base_url, model=model, api_key=api_key)]
    for fb in strat_cfg.get("fallbacks", []) or []:
        candidates.append({
            "base_url": fb.get("base_url", "").strip().rstrip("/"),
            "model": fb.get("model", ""),
            "api_key": fb.get("api_key", "").strip(),
        })
    candidates = [c for c in candidates if c["base_url"] and c["model"] and c["api_key"]]
    if not candidates:
        return None

    last_err = None
    for cand in candidates:
        result, err = _call_one_model(cand, prompt_data, strat_cfg)
        if result is not None:
            return result
        last_err = err
    if last_err:
        print(f"[witp_staff] 所有候选模型调用失败: {last_err}", file=sys.stderr)
    return None


def _call_one_model(cand: Dict[str, str], prompt_data: Dict[str, Any],
                    strat_cfg: Dict[str, Any]):
    """调用单个候选模型，返回 (result|None, err|None)。"""
    url = f"{cand['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cand['api_key']}"
    }

    system_msg = (
        "You are the Chief of Staff AI for the Operational Commander in War in the Pacific: Admiral's Edition (WitP-AE).\n"
        "You advise across ALL Pacific theater scenarios (Coral Sea, Guadalcanal, Marianas, Full Campaign, etc.).\n"
        "Your role is an ADVISORY BRAIN to the field commander. You do not click GUI directly.\n"
        "Analyze the dynamic situation for the active scenario, apply doctrines, and output an operational proposal in JSON:\n"
        "{\n"
        "  'strategic_intent': 'Clear intent summary quoting doctrines where relevant',\n"
        "  'threat_assessment': [{'zone': 'Name', 'threat_level': 'HIGH|MEDIUM|LOW', 'intel': 'detail'}],\n"
        "  'tf_recommendations': [\n"
        "     {'tf_id': 'TF...', 'action': 'SET_DESTINATION', 'goal_hex': [x, y], 'rationale': '...', 'confidence': 0.9}\n"
        "  ],\n"
        "  'air_recommendations': [\n"
        "     {'ag_id': 'AG...', 'action': 'SET_CAP_PERCENT', 'cap_pct': 100, 'rationale': '...', 'confidence': 0.95}\n"
        "  ],\n"
        "  'recon_focus': 'Guidance on search arcs and patrol priority'\n"
        "}"
    )

    payload = {
        "model": cand["model"],
        "temperature": strat_cfg.get("temperature", 0.3),
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)}
        ]
    }
    if strat_cfg.get("max_tokens"):
        payload["max_tokens"] = strat_cfg["max_tokens"]

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content), None
    except Exception as e:
        return None, f"{cand['model']}@{cand['base_url']}: {e}"

def query_kev_decision(tf_id: str, current_hex: tuple, options: list, intent_summary: str, config: dict) -> tuple:
    kev_cfg = config.get("kev_server", {})
    host = kev_cfg.get("host", "127.0.0.1")
    port = kev_cfg.get("port", 18090)
    
    try:
        criteria = {opt["hex"]: opt["note"] for opt in options}
        payload = {
            "state": f"Task force {tf_id} at {current_hex}. Strategic intent: {intent_summary}",
            "model": "kev-0.8b",
            "questions": {
                "dest_choice": {"type": "choice", "criteria": criteria}
            }
        }
        req = urllib.request.Request(
            f"http://{host}:{port}/v1/systemone",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ans = data.get("answers", {}).get("dest_choice", {})
            choice_hex = ans.get("choice")
            conf = ans.get("confidence", 0.8)
            probs = ans.get("probabilities") or {}
            # ★2026-09-24 修复★ KEV 评分函数对候选格均等打分时，probabilities 全相等，
            #   置信度公式 (best_p-1/K)/(1-1/K) 归零后被 clamp 到下限 0.1。
            #   语义上这是「无法区分」，不是「确定错误」；直接显示 10% 会严重误导前线。
            #   → 检测到全等概率时回退中性置信度 0.75，并在 rationale 侧可见。
            if len(probs) > 1:
                vals = list(probs.values())
                if max(vals) - min(vals) < 1e-9:
                    conf = 0.75
            for opt in options:
                if opt["hex"] == choice_hex:
                    return opt["coord"], conf
    except Exception:
        pass
    return options[0]["coord"], 0.75

def generate_staff_proposal(run_scraper: bool = False, game_id: str = None,
                            save_spec: str = None,
                            override_model: str = None,
                            override_fallbacks: str = None) -> Dict[str, Any]:
    """
    出具《作战方案建议书》。
    save_spec: 指定要解析的存档（槽位号如 "000"/"002"、文件名、或绝对路径）。
    override_model: 用户指定的临时主模型名称（覆盖 config.yaml）。
    override_fallbacks: 用户指定的临时备用模型链（逗号分隔字符串）。
    """
    if not game_id or game_id == "game-001":
        game_id = _find_active_game_id()

    config = load_config()
    skb = load_skb()

    # 动态指令级覆盖大模型与备用链
    if override_model:
        m_spec = resolve_model_spec(override_model, config)
        if m_spec:
            sm = config.setdefault("strategy_model", {})
            sm["model"] = m_spec["model"]
            sm["base_url"] = m_spec["base_url"]
            sm["api_key"] = m_spec["api_key"]
            sm["provider_id"] = m_spec["provider_id"]
            sm["provider_name"] = m_spec["provider_name"]
            print(f"[参谋部] 用户指定覆盖主模型：{m_spec['model']} ({m_spec['provider_id']})")
        else:
            print(f"[参谋部] ⚠️ 未在模型池找到指定模型 '{override_model}'，按配置继续运行。", file=sys.stderr)

    if override_fallbacks:
        fb_specs = []
        for fb_name in override_fallbacks.split(","):
            fb_name = fb_name.strip()
            if not fb_name:
                continue
            fb_spec = resolve_model_spec(fb_name, config)
            if fb_spec:
                fb_specs.append({
                    "base_url": fb_spec["base_url"],
                    "model": fb_spec["model"],
                    "api_key": fb_spec["api_key"],
                    "provider_id": fb_spec["provider_id"],
                    "provider_name": fb_spec["provider_name"]
                })
        if fb_specs:
            config.setdefault("strategy_model", {})["fallbacks"] = fb_specs
            print(f"[参谋部] 用户指定覆盖备用链：{[f['model'] for f in fb_specs]}")

    # 0. 存档定位：严格锁定当前正在玩的活跃存档
    save_path = None
    if save_spec:
        save_path = resolve_save(save_spec)
        if not save_path:
            raise SystemExit(f"[参谋部] 无法解析指定存档：{save_spec}\n"
                             f"        可用存档请用 --saves 查看。")
        run_scraper = True  # 指定存档必然需要重跑读层
    else:
        # 锁定当前正在玩的存档：优先取 wpae000.pws（Autosave / 结算后新状态），若无则取最新 .pws
        auto_pws = os.path.join(SAVE_DIR, "wpae000.pws")
        if os.path.exists(auto_pws):
            save_path = auto_pws
        else:
            from witp_saves import list_saves
            saves = list_saves()
            if saves:
                save_path = saves[0]["path"]

    # 1. 客观感知（零硬编码，严格按存档读取真实数据）
    state = perception.capture_state(save_path=save_path, run_scraper=run_scraper)
    turn_info = state.get("turn", {})
    scenario_name = turn_info.get("scenario_name") or "WitP-AE 战役推演"
    turn_date = turn_info.get("game_date") or "未知日期"
    turn_num = turn_info.get("game_turn") or 1
    
    # 提取真实编制列表
    active_tfs = state.get("taskforces", [])
    raw_ags = state.get("airgroups", [])
    # 第六局修复：先筛选出真正有在役飞机的中队，并按 舰载战斗机/舰载轰炸机/远程巡逻机/陆基轰炸机/其他 优先级排序
    def _ag_priority(a):
        nm = (a.get("name") or "").upper()
        ty = (a.get("aircraft_type_name") or a.get("aircraft_name") or "").upper()
        if "VF" in nm or "FIGHTER" in ty:
            return 0
        if "VS" in nm or "VB" in nm or "VT" in nm:
            return 1
        if "VP" in nm or "PBY" in ty or "CATALINA" in ty:
            return 2
        if "B-25" in ty or "A-20" in ty or "BG" in nm or "BS" in nm:
            return 3
        return 4

    active_ags = [a for a in raw_ags if a.get("aircraft_active", 0) > 0 and a.get("name")]
    active_ags.sort(key=_ag_priority)

    threat_areas = state.get("threats", {}).get("threat_areas", [])

    # ★2026-09-25 新增★ 莫尔兹比港状态 + 航母前推位
    #   动机（指挥官订正）：三级优先级是「层层递减」的严格字典序，
    #   「保航母」以「PM 未失守」为前提，是第一级的从属考量，**不是第一级的否决权**。
    #   故参谋部必须每回合按敌情算出航母前推位（废除固定红线），交指挥层审核。
    pm_st = pm_status_mod.read_pm_status(turn_date=turn_date)
    _cv_pos = []
    for t in active_tfs:
        _hx = t.get("start_of_day_x") or t.get("end_of_day_x")
        _hy = t.get("start_of_day_y") or t.get("end_of_day_y")
        _fl = str(t.get("flagship_name") or "")
        _ms = str(t.get("mission") or "").upper()
        if _hx is None or _hy is None:
            continue
        # ★通用航母判据★：按 ship_type 前缀 CV 识别，不硬编码舰名
        if theater_mod.tf_has_carrier(t) or _ms in ("AIRCOMBAT", "CARRIER"):
            _cv_pos.append({"tf": tf_cmd_id(t) or t.get("record_id"),
                            "hex": (int(_hx), int(_hy)), "flagship": _fl,
                            "carriers": theater_mod.carrier_ships_in_tf(t)})
    cv_station = carrier_station_mod.recommend_carrier_station(
        pm_st, threat_areas, _cv_pos, bases=state.get("bases", []))

    # ★2026-09-25 新增★ 侦察链（指挥官指正：十二局从未发现敌航母 = 侦察策略有缺陷）
    #   ① 扫战报找「日军舰载攻击机」接触 —— 「己方头顶出现日军舰载机 ⇒ 敌航母就在附近」
    #   ② 据此产出搜索方案（PBY/VS 专职 100% 搜索 + 按敌情方位角设扇面，禁止全向摊薄）
    recon_contacts = recon_mod.carrier_aircraft_contacts(turn_date=turn_date)
    search_plan = recon_mod.build_search_plan(
        active_ags, state.get("bases", []), threat_areas, recon_contacts)
    cv_proximity = recon_mod.carrier_proximity(recon_contacts, _cv_pos)

    # 把舰载机接触点并入航母机会判定的情报源（这是最直接的敌航母线索）
    _threats_opp = list(threat_areas)
    # ★2026-09-26 关键修正★ 只有「我方击中敌舰」的那些格才是**敌位置**；
    #   「我方在该格挨打」的格是**我方位置**，若当敌位置喂下去，参谋部会建议
    #   朝我们自己所在处『前出打击』（实测把约克城挨打的 (108,138) 当成了敌航母位）。
    _prox_pool = []
    for _h in (recon_contacts.get("hits") or []):
        if not _h.get("hex"):
            continue
        if _h.get("on_us"):
            _prox_pool.append(_h)            # 仅供"敌在我附近"的邻近告警
            continue
        _threats_opp.append({
            "position": {"x": _h["hex"][0], "y": _h["hex"][1]},
            "threat_types": ["carrier"], "threat_score": 10,
            "sample_texts": [f"舰载机接触 {_h['file']}: {_h['title']}"],
        })

    # ★2026-09-26 新增★ 己方兵力态势 + 航母失衡警告（治「只讲敌情、不讲我情」）
    own_posture = build_own_posture()
    _enemy_cv_groups = len((state.get("threats", {}) or {}).get("carrier_threat_areas", []) or [])
    _own_cv = own_posture.get("carrier_count", 0)
    _cv_balance_warning = "无"
    if own_posture.get("ok"):
        if _own_cv == 0:
            _cv_balance_warning = "🚨 我方已无航母 —— 任何「航母前推/机会打击」建议一律不可执行。"
        elif _enemy_cv_groups >= 2 and _own_cv < _enemy_cv_groups:
            _cv_balance_warning = (
                f"🚨 航母失衡：我方仅 {_own_cv} 艘 vs 敌方推定 {_enemy_cv_groups} 组。"
                f"依 D3.6「单航母不可突入已确认的敌双航母打击半径」，"
                f"任何机会打击建议**必须同时给出风险与代价评估**（预计我方伤亡、能否承受），"
                f"不得只讲收益；指挥层须先核此失衡再决定。")

    # ★2026-09-25 新增★ 日军航母「机会打击」判定
    #   指挥官指令：「当有机会打击日军航母时，应当毫不犹豫抓住机会进行攻击。」
    cv_opp = carrier_station_mod.detect_carrier_opportunity(
        pm_st, _threats_opp,
        (state.get("threats", {}) or {}).get("carrier_threat_areas", []),
        _cv_pos, bases=state.get("bases", []),
        own_cv=own_posture.get("carrier_count", 0), enemy_groups=_enemy_cv_groups)

    # 2. 动态战区评估
    intel_data = {
        "date": turn_date,
        "scenario_name": scenario_name,
        "contacts": threat_areas
    }
    belief = belief_update.update_belief_map({}, intel_data)
    
    # 3. 战略推演提示上下文（通用型）
    tf_summaries = []
    for t in active_tfs[:20]:
        rid = t.get("record_id")
        cmd_id = tf_cmd_id(t)
        sx = t.get("start_of_day_x") or t.get("end_of_day_x")
        sy = t.get("start_of_day_y") or t.get("end_of_day_y")
        tx, ty = t.get("target_x"), t.get("target_y")
        n_ships = len(t.get("ships") or [])
        tf_summaries.append(
            f"{cmd_id or 'TF?'} (flagship {t.get('flagship_name') or '?'}, {n_ships} ships) "
            f"pos=({sx},{sy}) target=({tx},{ty}) mission={t.get('mission') or '?'}")

    ag_summaries = []
    for a in active_ags[:24]:
        loc = a.get("stationed_on_ship_name") or a.get("stationed_at_base_name") or "海空"
        ag_summaries.append(
            f"{a.get('name')}: {a.get('aircraft_active', 0)} active, "
            f"type={a.get('aircraft_type_name') or a.get('aircraft_name') or '?'}, "
            f"loc={loc}, mission_code={a.get('primary_mission_code')}, cap={a.get('percent_cap', 0)}%")

    # 结构化提炼情报摘要给大模型
    threat_summaries = []
    for zkey, zval in belief.get("regions", {}).items():
        threat_summaries.append(f"[{zval.get('level')}] {zval.get('name')}: {zval.get('detail')}")

    prompt_context = {
        "scenario": scenario_name,
        "turn": turn_num,
        "date": turn_date,
        "our_posture": own_posture,
        "carrier_balance_warning": _cv_balance_warning,
        "our_task_forces": tf_summaries,
        "our_airgroups": ag_summaries,
        "threat_intel": threat_summaries,
        # ★2026-09-25 新增★ 把指挥官三级优先级与 PM 实况喂给模型，
        #   避免模型沿用「航母南撤避险」的旧惯性（那是把第二级当成了第一级的否决权）
        # ★★2026-10-14 修（换阵营遗留：三级优先级写死盟军视角）★★
        #   旧文案把「①死守莫尔兹比港」写死为唯一一级目标 —— 那只在人类执**盟军**时成立。
        #   本局人类执**日军**，一级目标恰恰相反：**攻占 PM**（剧本胜负手）。
        #   ⇒ 按 side.txt 自适应生成，不再让模型拿到与当前阵营矛盾的战略框架。
        "commander_priority": _build_commander_priority(),
        "pm_status": pm_st,
        "carrier_station_reference": cv_station,
        "carrier_opportunity": cv_opp,
        "recon_contacts": recon_contacts,
        "search_plan_reference": search_plan,
        "carrier_proximity": cv_proximity,
        "recon_doctrine": (
            "侦察纪律（指挥官指正）：十二局从未发现敌航母 = 侦察策略有缺陷。"
            "①搜索必须专职化：PBY 远程核心 100%、舰载侦察机 VS 专职 100%、巡洋舰水侦 50/50，"
            "禁止把搜索结果摊薄或全部改为反潜；②必须设搜索扇面（按敌情罗盘方位角 ±45°），"
            "无扇面的全向搜索等于削弱一半效率；③**「当己方头顶出现日军舰载机时，说明日军航母就在附近」**"
            "（以 D3A/B5N 等舰载攻击机为证据；A6M2 通用不作数、G3M/G4M 为陆基须排除）——"
            "此时应**加强机动与空中侦察、按战局寻找打击机会，而不是一味退让**。"
        ),
        "general_principle": (
            "方法论（指挥官）：WitP 模拟性强，指挥策略可依据**二战一般性经验**；"
            "但**剧本每回合存在随机性**——对手不一定按历史策略行动，也不一定在历史位置部署。"
            "故必须：①以一般性经验（侦察优先、兵力集中、任务式指挥、保全兵力打下一仗）为出发点；"
            "②**严禁剧本推定**——不得假设敌在某历史日期出现在某历史位置，不得预设敌方兵力构成；"
            "③**一切「敌人在哪、有多少」的判断只能来自当回合读层情报**"
            "（目击报告 / 舰载机接触 / 基地 area_command 归属）；情报不足时明确写「未知」，**不得编造**；"
            "④**根据战局随机应变**：计划按当回合实际态势重算，不沿用上一局或历史的套路。"
        ),
        "doctrines": skb.get("doctrines", ""),
        "patterns": skb.get("patterns", []),
        "eval_weights": skb.get("eval_weights", {})
    }
    
    raw_strategy = call_strategic_model(prompt_context, config)
    if not raw_strategy:
        # 通用启发式兜底（针对实际存在的部队动态生成，绝不硬编码部队代号）
        actions_dyn = []
        if active_tfs:
            primary_tf = active_tfs[0]
            ptid = tf_cmd_id(primary_tf)
            px, py = primary_tf.get("target_x"), primary_tf.get("target_y")
            if ptid and px is not None and py is not None:
                actions_dyn.append({
                    "tf_id": ptid,
                    "action": "SET_DESTINATION",
                    "goal_hex": [px, py],
                    "rationale": f"保持 {primary_tf.get('flagship_name') or ptid} 当前阵位与机动展开",
                    "confidence": 0.85
                })

        cap_actions_dyn = []
        # 只推荐「有中队名」的航空队；未命名条目不可执行，一律跳过
        for ag in active_ags:
            ag_name = ag.get("name")
            if not ag_name:
                continue
            if len(cap_actions_dyn) >= 4:
                break
            cap_actions_dyn.append({
                "ag_id": str(ag_name),
                "action": "SET_CAP_PERCENT",
                "cap_pct": 100,
                "rationale": "遵循教条#1，保全核心打击力量，防空伞拉满",
                "confidence": 0.95
            })
            
        raw_strategy = {
            "strategic_intent": f"在 {scenario_name} 当前战局下执行积极海空态势控制。严守防空掩护与严密海空搜索原则，确保战场制空与情报先手。",
            "threat_assessment": belief.get("regions", {}),
            "tf_recommendations": actions_dyn,
            "air_recommendations": cap_actions_dyn,
            "recon_focus": "全空域展开扇面海搜，重点追踪敌方航母打击群与突击编队动向。"
        }
        
    # 4. 战术选项细化
    actions = []

    # ★2026-09-25 新增（修复②）：输出层守卫所需的索引★
    #   动机：第十/十一局实测，参谋部建议存在两类稳定缺陷，每回合都要靠下游守卫纠偏：
    #     ① 补给编队「后撤疏散」的目标被设为其**当前位置**（11 局实测 10 次）→ 语义自相矛盾
    #     ② 航母目标越到 100,138 以北（第七局 Lexington 在 (102,129) 战沉）
    #   与其每回合在下游纠偏，不如在**输出层**直接改正，让建议书本身就是合规的。
    #   ★2026-09-25 订正★ 航母识别改为**通用舰种判据**（ship_type 前缀 CV），
    #     不再硬编码美舰名——剧本每回合有随机性，兵力构成须以存档数据为准。
    _POS, _HAS_CV = {}, {}
    _TF_REC = {}                      # ★2026-10-14 新增：tid → TF 记录（供守卫A 取常设目标）
    for _t in active_tfs:
        _k = tf_cmd_id(_t)
        _sx = _t.get("start_of_day_x") or _t.get("end_of_day_x")
        _sy = _t.get("start_of_day_y") or _t.get("end_of_day_y")
        if _sx is not None and _sy is not None:
            _POS[_k] = (int(_sx), int(_sy))
        _HAS_CV[_k] = theater_mod.tf_has_carrier(_t) \
                      or (str(_t.get("mission") or "").upper().find("AIRCOMBAT") >= 0)
        _TF_REC[_k] = _t
    for tf_rec in raw_strategy.get("tf_recommendations", []):
        tid = tf_rec.get("tf_id")
        goal = tuple(tf_rec.get("goal_hex", [100, 100]))
        
        # 查找该编队的真实起始坐标与旗舰信息
        cur_hex = goal
        flagship = str(tid)
        mission = ""
        for t in active_tfs:
            if tf_cmd_id(t) == tid or str(t.get("record_id")) == str(tid).replace("TF", ""):
                sx = t.get("start_of_day_x") or t.get("end_of_day_x")
                sy = t.get("start_of_day_y") or t.get("end_of_day_y")
                if sx is not None and sy is not None:
                    cur_hex = (int(sx), int(sy))
                flagship = t.get("flagship_name") or str(tid)
                mission = (t.get("mission") or "").upper()
                break

        opts = option_builder.build_tf_destination_options(tid, cur_hex, [goal])
        best_coord, conf = query_kev_decision(tid, cur_hex, opts["options"], raw_strategy.get("strategic_intent", ""), config)
        
        tid_str = str(tid)
        is_carrier = ("14" in tid_str or "16" in tid_str or "CV" in mission or "CARRIER" in mission)
        is_logistics = ("15" in tid_str or "17" in tid_str or "AO" in mission or "CONVOY" in mission)
        is_sub = ("20" in tid_str or "22" in tid_str or "24" in tid_str or "SUB" in mission)

        if is_carrier:
            tgroup = "CARRIER"
            p_label = "必选避险" if conf < 0.85 else "核心机动"
            a_label = "机动集结"
        elif is_logistics:
            tgroup = "LOGISTICS"
            p_label = "后撤疏散"
            a_label = "后撤保全"
        elif is_sub:
            tgroup = "SUBMARINE"
            p_label = "前哨伏击"
            a_label = "水下潜伏"
        else:
            tgroup = "SURFACE"
            p_label = "战术突击"
            a_label = "战术前出"

        actions.append({
            "target_type": "TF",
            "target_id": tid,
            "unit_name": f"{tid}（{flagship}）" if flagship != tid else tid,
            "tactical_group": tgroup,
            "priority_label": p_label,
            "action": "SET_DESTINATION",
            "action_label": a_label,
            "params": {"hex": list(best_coord)},
            "param_label": f"海域 ({best_coord[0]},{best_coord[1]})",
            "rationale": tf_rec.get("rationale", "战术机动"),
            "confidence": conf
        })
        
    # ★2026-09-25 新增（修复②）：输出层两条确定性守卫★
    guards_applied = []
    carrier_advisories = []
    REAR_HEX = (99, 153)          # 布里斯班外海后方待机区
    RABAUL = (106, 125)   # ⚠️ 仅作初始值；实际由 cv_station 的数据推导锚点覆盖
    PM_HEX = (98, 130)
    _ea = cv_station.get("enemy_air_anchor") or {}
    RABAUL = tuple(_ea["hex"]) if _ea.get("hex") else RABAUL
    _ea_label = _ea.get("name") or "兜底常量"
    _ea_src = _ea.get("source") or "剧本常量回退（读层无 base 数据）"
    _station_hex = cv_station.get("hex")
    _opp_hex = cv_opp.get("strike_hex") if cv_opp.get("detected") else None

    for _a in actions:
        _tid = str(_a.get("target_id", ""))
        _hex = (_a.get("params") or {}).get("hex")
        if not _hex or _a.get("action") != "SET_DESTINATION":
            continue
        _hx, _hy = int(_hex[0]), int(_hex[1])
        _grp = str(_a.get("tactical_group", "")).upper()
        _cur = _POS.get(_tid)
        _is_cv = (_grp == "CARRIER") or _HAS_CV.get(_tid, False)

        # 守卫A：目标 == 当前位置 → 语义矛盾，必须纠正。
        # ★2026-09-29 修正★ 原实现仅对 _grp == "LOGISTICS" 生效，
        #   导致第十九局「TF16（CARRIER）目标 (100,136) == 当前位置 (100,136)」
        #   这条空指令未被拦下（同批 TF15/TF17 被正确拦下）。
        #   现改为**对所有编队通用**：空指令对任何编队都无意义。
        #   纠正方式按编队类型区分：
        #     · 后勤/补给编队 → 撤到后方待机区 REAR_HEX
        #     · 其他编队       → 保留原目标但标注「空指令」，交指挥层裁决
        if _cur and (_hx, _hy) == _cur:
            # ★2026-10-10 修正：不再只告警★
            #   指挥层规则：「驳回一条必须同时补一条有效替代指令（空指令＝目标即当前位置，
            #   只删不补＝该编队整回合滞留挨打）」。
            #   ⇒ 空指令一律替换为**由读层数据推导的有效坐标**，不留空指令给指挥层。
            #      · 后勤/补给编队 → 后方待机区 REAR_HEX（撤出敌打击圈，D11.29）
            #      · 航母编队       → D11.30 打击位 = PM 正向 7 格（SBD 正常航程内，
            #                          可覆盖经 Milne Bay/Deboyne 接近 PM 的敌船团）
            #      · 其他（水面等）  → 若在 PM 打击圈北侧则回 PM 邻近拦截位，
            #                          否则撤至 REAR_HEX
            _alts = None
            # ★★2026-10-14 修（守卫A 误撤登陆/炮击编队）★★
            #   旧逻辑只看编队分类：LOGISTICS→后撤；CV→打击位；其余→若距 PM>8 格则
            #   一律「撤至后方待机区」。实测本局 T1：TF6(BOMBARDMENT 目标 PM 98,130)、
            #   TF7(AMPHIB 目标 PM) 的既有目标**有效且正是作战核心**，却因
            #   「距 PM>8 格（实际 106,125 → 6 格，仍被错算）」被判为「撤至后方」，
            #   参谋部建议书上出现「TF6/TF7 撤至后方 (99,153)」—— 直接违背本局目标（夺 PM）。
            #   ⇒ 守卫A 必须**优先沿用该 TF 记录里已存在的有效目标**（target_x/target_y），
            #     尤其是 BOMBARDMENT / AMPHIB / TRANSPORT 这类有常设作战任务的编队。
            #     仅当确实无有效目标时才退回分类规则。
            _rec = _TF_REC.get(_tid) or {}
            _tx, _ty = _rec.get("target_x"), _rec.get("target_y")
            _mis = str(_rec.get("mission") or "").upper()
            _has_mission_target = (_tx and _ty and int(_tx) > 0 and int(_ty) > 0
                                   and (int(_tx), int(_ty)) != _cur)
            if _has_mission_target and any(k in _mis for k in ("BOMBARD", "AMPHIB", "TRANSPORT", "CARGO", "FAST")):
                _alts = (int(_tx), int(_ty))
                _why = (f"沿用该编队常设任务目标（{_mis}；读层 taskforces.json 的 target）"
                        f"——不覆盖作战任务")
            elif _grp == "LOGISTICS":
                _alts = REAR_HEX
                _why = "撤出敌舰载机打击圈（D11.29）"
            elif _is_cv:
                _alts = (PM_HEX[0] + 2, PM_HEX[1] + 7)   # → (100,137)
                _why = "D11.30 打击位：PM 正向 7 格，SBD 正常航程内可覆盖敌船团"
            else:
                _d_pm = hex_distance(_cur, PM_HEX)
                if _d_pm <= 8:
                    _alts = (PM_HEX[0] + 1, PM_HEX[1] + 4)   # → (99,134) PM 邻格拦截位
                    _why = "PM 邻格水面拦截位（D11.15 登陆窗口）"
                else:
                    _alts = REAR_HEX
                    _why = "撤至后方待机区（无登陆迹象，避免暴露）"
            _a["params"]["hex"] = [_alts[0], _alts[1]]
            _a["param_label"] = f"海域 ({_alts[0]},{_alts[1]})"
            _a["rationale"] = (_a.get("rationale", "") +
                               f"｜[守卫A] 原目标 ({_hx},{_hy}) 等于当前位置，空指令；"
                               f"已按 {_why} 替换为 ({_alts[0]},{_alts[1]})")
            guards_applied.append(
                f"守卫A 纠正 {_tid}({_grp or '未分类'})：{(_hx, _hy)}==当前位置 → {_alts}（{_why}）")
            continue

        # ★2026-09-25 废除守卫B（硬纠偏）★
        #   原实现：航母目标越到 100,138 以北 → 一律拉回 140。
        #   指挥官订正：三级优先级层层递减，「保航母」以「PM 未失守」为前提，
        #   是第一级的**从属考量**，不是第一级的**否决权**。硬拉回把下级写成了上级的否决权。
        #   现改为：①只报告风险，不拦截；②第一级手段必须投入时，按参谋部前推位主动修正（透明记录）。
        if _is_cv:
            _d_rb = hex_distance((_hx, _hy), RABAUL)
            _risk = ("在岸基轰炸圈内" if _d_rb <= 5 else
                     "贴近岸基轰炸圈边缘" if _d_rb <= 7 else "在岸基轰炸圈外")
            _note = (f"{_tid} 目标 ({_hx},{_hy})：距敌方机场 {_ea_label} {_d_rb} 格（{_risk}）"
                     f"、距 PM {hex_distance((_hx, _hy), PM_HEX)} 格｜锚点来源：{_ea_src}")
            carrier_advisories.append(_note)
            _a["rationale"] = (_a.get("rationale", "") +
                               f"｜[航母风险提示·不自动纠偏] {_note}。"
                               f"按严格字典序，第二级无权否决第一级。")

            # ① 机会打击优先（指挥官：「当有机会打击日军航母时，应当毫不犹豫抓住机会进行攻击」）
            #    只要有敌航母目击，就把航母拉到能即刻出击的打击位——与「避险」方向相反。
            if _opp_hex and hex_distance((_hx, _hy), tuple(_opp_hex)) >= 2:
                _a["params"]["hex"] = list(_opp_hex)
                _a["param_label"] = f"海域 ({_opp_hex[0]},{_opp_hex[1]})（机会打击位）"
                _a["rationale"] = (
                    f"[机会打击·不犹豫] 敌航母目击于 "
                    f"({cv_opp.get('enemy_carrier_hex', [None, None])[0]},"
                    f"{cv_opp.get('enemy_carrier_hex', [None, None])[1]})"
                    f"（{cv_opp.get('enemy_carrier_intel_source')}）→ 由 ({_hx},{_hy}) "
                    f"前出至 ({_opp_hex[0]},{_opp_hex[1]})，距敌航母 "
                    f"{cv_opp.get('distance_strike_to_enemy_cv_hex')} 格（舰载机出击半径内），"
                    f"距我舰当下 {cv_opp.get('distance_own_cv_to_strike_hex')} 格。"
                    f"按指挥官指令抓住机会立即出击（D3.7 先手出击；第五局约克城『未撤未打』即战沉）"
                    f"（指挥层审核后执行）｜" + _a.get("rationale", ""))
                _a["confidence"] = max(0.85, float(_a.get("confidence") or 0.85))
                guards_applied.append(
                    f"机会打击 {_tid}：({_hx},{_hy}) → ({_opp_hex[0]},{_opp_hex[1]})"
                    f"｜敌航母 ({cv_opp.get('enemy_carrier_hex', [None, None])[0]},"
                    f"{cv_opp.get('enemy_carrier_hex', [None, None])[1]})")
                carrier_advisories.append(
                    f"{_tid} 已按机会打击位修正（前出方向）——{cv_opp.get('verdict')}")
                if cv_opp.get("level1_tension"):
                    carrier_advisories.append(
                        f"{_tid} 注意：PM 同时正遭登陆，本出击判定为与第一级同向，仍需指挥层复核分兵")

            # ② 否则：第一级手段必须投入（PM 未失守且登陆进行中）→ 按守港前推位修正
            elif cv_station.get("mode") == "守港打击位" and _station_hex:
                if hex_distance((_hx, _hy), tuple(_station_hex)) >= 3:
                    _a["params"]["hex"] = list(_station_hex)
                    _a["param_label"] = f"海域 ({_station_hex[0]},{_station_hex[1]})"
                    _a["rationale"] = (
                        f"[参谋部前推位] PM 登陆进行中，第一级手段必须投入 → 由 ({_hx},{_hy}) "
                        f"前推至 ({_station_hex[0]},{_station_hex[1]})，距锚点 "
                        f"{cv_station.get('distance_to_anchor_hex')} 格（指挥层审核后执行）｜"
                        + _a.get("rationale", ""))
                    _a["confidence"] = max(0.8, float(_a.get("confidence") or 0.8))
                    guards_applied.append(
                        f"参谋部前推位 {_tid}：({_hx},{_hy}) → "
                        f"({_station_hex[0]},{_station_hex[1]})｜守港打击位")
                    carrier_advisories.append(
                        f"{_tid} 已按参谋部前推位修正（前推方向）——注意这与旧守卫B的『拉回』方向相反")

    # ★2026-09-25 新增★ 搜索命令（SET_NAVAL_SEARCH）
    #   指挥官指正：十二局从未发现敌航母 = 侦察策略有缺陷。
    #   根因之一是「搜索从未成为可执行命令」——recon_guidance 只是散文。
    #   现把侦察方案变成逐中队的 SET_NAVAL_SEARCH 动作（比例 + 扇面），交指挥层审核后下达。
    search_actions = []
    for _sa in (search_plan.get("assignments") or []):
        search_actions.append({
            "target_type": "AIRGROUP",
            "target_id": _sa["ag"],
            "unit_name": f"{_sa['ag']}（{_sa.get('type') or ''}）",
            "tactical_group": "RECON",
            "priority_label": "侦察专职化",
            "action": "SET_NAVAL_SEARCH",
            "action_label": "对海搜索",
            "params": {
                "nav_search": _sa["nav_search"],
                "asw_search": _sa["asw_search"],
                "arc_start": _sa.get("arc_start"),
                "arc_end": _sa.get("arc_end"),
            },
            "param_label": (f"对海 {_sa['nav_search']}% / ASW {_sa['asw_search']}%"
                            + (f" / 扇面 {_sa['arc_start']:03d}°→{_sa['arc_end']:03d}°"
                               if _sa.get("arc_start") is not None else " / 全向")),
            "rationale": f"[{_sa['role']}] {_sa['note']}",
            "confidence": 0.9,
        })
    actions.extend(search_actions)

    # ★2026-09-24 修复★ 攻击机不得设 CAP。
    #   原实现把模型返回的 air_recommendations 无条件转成 SET_CAP_PERCENT，
    #   导致 VB/VS/VT（俯冲/侦察/鱼雷机）被设成 CAP 100%
    #   → 所有攻击机都去巡逻、无人执行对舰攻击，航母丧失全部打击能力。
    #   规则：只有战斗机单位可设 CAP；非战斗机一律过滤并记录。
    _FGHT_KW = ("wildcat", "warhawk", "kittyhawk", "tomahawk", "airacobra",
                "lightning", "spitfire", "hurricane", "buffalo", "corsair",
                "hellcat", "boomerang", "mustang", "zero", "zeke", "oscar",
                "claude", "nate", "tojo", "tony", "ruse")

    def _is_fighter_unit(ag_name: str, ac_model: str = "") -> bool:
        """只有战斗机单位能执行 CAP。双判据：机队名前缀 + 机型关键词。"""
        n = (ag_name or "").strip().upper()
        if any(n.startswith(p) for p in ("VF", "VMF", "FG", "FS")):
            return True
        m = (ac_model or "").lower()
        return any(k in m for k in _FGHT_KW)

    # 当前 CAP 值索引（跳过已达标项，避免重复建议）
    _cur_cap, _cur_model = {}, {}
    for _ag in active_ags:
        _nm = _ag.get("name")
        if _nm:
            _cur_cap[str(_nm)] = _ag.get("percent_cap")
            _cur_model[str(_nm)] = _ag.get("aircraft_type_name") or ""

    filtered_non_fighter = []

    for air_rec in raw_strategy.get("air_recommendations", []):
        ag_id = air_rec.get("ag_id")
        if not ag_id:
            continue
        ag_id = str(ag_id)
        if not _is_fighter_unit(ag_id, _cur_model.get(ag_id, "")):
            filtered_non_fighter.append(ag_id)
            continue
        cap = air_rec.get("cap_pct", 100)
        if _cur_cap.get(ag_id) == cap:
            filtered_non_fighter.append(f"{ag_id}(当前已为{cap}%)")
            continue
        actions.append({
            "target_type": "AIRGROUP",
            "target_id": ag_id,
            "unit_name": ag_id,
            "tactical_group": "AIR_CAP",
            "priority_label": "防空顶格",
            "action": "SET_CAP_PERCENT",
            "action_label": "战斗空中巡逻",
            "params": {"cap_pct": cap},
            "param_label": f"CAP {cap}%",
            "rationale": air_rec.get("rationale", "制空掩护"),
            "confidence": air_rec.get("confidence", 0.9)
        })

    # 提取我方核心兵力战备现势（供推演决策看板展示）
    friendly_carriers = []
    for t in active_tfs:
        rid = str(t.get("record_id", ""))
        ms = (t.get("mission") or "").upper()
        fn = t.get("flagship_name") or ""
        if rid in ["14", "16"] or "CV" in ms or "CARRIER" in ms or any("CARRIER" in (s.get("type") or "").upper() for s in t.get("ships", [])):
            sx = t.get("start_of_day_x") or t.get("end_of_day_x")
            sy = t.get("start_of_day_y") or t.get("end_of_day_y")
            friendly_carriers.append({
                "tf_id": tf_cmd_id(t),
                "flagship": fn or f"TF{rid}",
                "pos": [sx, sy],
                "target": [t.get("target_x"), t.get("target_y")]
            })

    f_ready = sum(a.get("aircraft_active", 0) for a in active_ags if _is_fighter_unit(a.get("name", ""), a.get("aircraft_type_name", "")))
    s_ready = sum(a.get("aircraft_active", 0) for a in active_ags if not _is_fighter_unit(a.get("name", ""), a.get("aircraft_type_name", "")))

    proposal = {
        "title": f"{scenario_name} 第 {turn_num} 回合《作战方案建议书》",
        "scenario": scenario_name,
        "turn": turn_num,
        "date": turn_date,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "situation_summary": {
            "threat_regions": belief.get("regions", {})
        },
        "strategic_intent": raw_strategy.get("strategic_intent", ""),
        "recommended_actions": actions,
        "friendly_forces": {
            "carriers": friendly_carriers,
            "fighters_ready": f_ready,
            "strike_ready": s_ready
        },
        "recon_guidance": raw_strategy.get("recon_focus", "保持扇面侦察"),
        "active_model_used": config.get("strategy_model", {}).get("model", "rule_fallback"),
        "data_source_save": (os.path.basename(save_path) if save_path
                             else "自动选取（最新 .pws）"),
        # 第六局新增：数据源健康度（让前线一眼看出建议书是否基于新鲜数据）
        "perception_health": state.get("perception_health", {}),
        "skb_doctrine_count": (len(re.findall(r"^### D\d+\.\d+", skb.get("doctrines", ""), re.M))
                               + skb.get("doctrines", "").count("## 教条 #")) if skb.get("doctrines") else 0,
        "skb_pattern_count": len(skb.get("patterns", [])),
        # 2026-09-24 新增：被规则过滤掉的建议（非战斗机设CAP / 已达标项），保持透明
        "filtered_recommendations": filtered_non_fighter,
        # 2026-09-25 新增：输出层守卫已自动纠正的条目（透明化，便于指挥官复核）
        "guards_applied": guards_applied,
        # ★2026-09-25 新增★ PM 实况 + 航母前推位（指挥层审核后执行）
        "pm_status": pm_st,
        "carrier_station": cv_station,
        "carrier_advisories": carrier_advisories,
        "carrier_opportunity": cv_opp,
        "our_posture": own_posture,
        "carrier_balance_warning": _cv_balance_warning,
        "recon_contacts": recon_contacts,
        "search_plan": search_plan,
        "carrier_proximity": cv_proximity,
        "commander_priority": _build_commander_priority(),
    }

    # 归档建议书
    causal_dir = os.path.join(GAMES_DIR, game_id, "causal_log")
    os.makedirs(causal_dir, exist_ok=True)
    prop_file = os.path.join(causal_dir, f"proposal_turn_{turn_num:02d}.json")
    with open(prop_file, "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2, ensure_ascii=False)
        
    return proposal

def format_proposal_markdown(p: Dict[str, Any]) -> str:
    lines = [
        f"# 🎖️ {p['title']}",
        f"> **生成时间**：{p['generated_at']} | **战役日期**：{p['date']} | **推理底座**：`{p['active_model_used']}` | **SKB**：{p.get('skb_doctrine_count', 0)} 条教条 / {p.get('skb_pattern_count', 0)} 个模式",
        "",
    ]
    # 数据源健康度警示（第六局新增）
    health = p.get("perception_health") or {}
    if health.get("warnings"):
        lines.append("> ⚠️ **数据源健康告警**：")
        for w in health["warnings"]:
            lines.append(f">   - {w}")
        lines.append("")
    lines.extend([
        "## 一、战场客观态势与威胁研判",
        "| 战区 / 监测区域 | 威胁等级 | 参谋情报警示 |",
        "|---|---|---|"
    ])
    for rkey, rval in p.get("situation_summary", {}).get("threat_regions", {}).items():
        name = rval.get("name", rkey)
        lvl = rval.get("level", "MEDIUM")
        dtl = rval.get("detail", "常规警戒中")
        badge = "🔴 高危" if lvl == "HIGH" else ("🟡 中危" if lvl == "MEDIUM" else "🟢 安全")
        lines.append(f"| **{name}** | {badge} | {dtl} |")
        
    lines.extend([
        "",
        "## 二、本回合核心战略意图",
        f"**【作战指导】**：{p['strategic_intent']}",
        f"**【侦察指导】**：{p['recon_guidance']}",
    ])

    # ★2026-09-25 新增★ 指挥官三级优先级 + PM 实况 + 航母前推位
    pm = p.get("pm_status") or {}
    cs = p.get("carrier_station") or {}
    # ★2026-09-26 新增★ 己方兵力态势章节（治「只讲敌情、不讲我情」）
    _op = p.get("our_posture") or {}
    lines.extend(["", "## 二之一、我方兵力态势（先看我情，再谈打法）"])
    if not _op.get("ok"):
        lines.append(f"- ⚠️ 己方兵力读取失败：{_op.get('err')}")
    else:
        _cvs = _op.get("carriers") or []
        lines.append(f"- **可用航母 {_op.get('carrier_count', 0)} 艘**"
                     f"（良好：{'、'.join(_op.get('carriers_fit') or []) or '无'}）")
        if _cvs:
            lines.append("")
            lines.append("| 航母 | 编队 | 位置 | 系统 | 进水 | 火 | 引擎 |")
            lines.append("|---|---|---|---|---|---|---|")
            for c in _cvs:
                lines.append(f"| {c.get('name')} | TF{c.get('tf')} | "
                             f"({(c.get('pos') or [None, None])[0]},{(c.get('pos') or [None, None])[1]}) | "
                             f"{c.get('sys')} | {c.get('flt')} | {c.get('fire')} | {c.get('eng')} |")
        lines.append(f"- 其他舰种：{_op.get('other_types')}")
    _w = p.get("carrier_balance_warning") or "无"
    if _w != "无":
        lines.extend(["", f"> {_w}"])
    lines.extend(["", "## 三、指挥官三级优先级与莫尔兹比港实况（严格字典序）"])
    lines.append(f"> **{p.get('commander_priority', '')}**")
    if pm:
        own_map = {"allied": "🟢 盟军", "japan": "🔴 日军", "unknown": "⚪ 未知"}
        lines.append("")
        lines.append("| 项目 | 实况 |")
        lines.append("|---|---|")
        lines.append(f"| PM 归属 | {own_map.get(pm.get('owner'), '?')}（{pm.get('area_command') or '—'}）|")
        lines.append(f"| 登陆进程 | 第 {pm.get('landing_stage', 0)} 级 — {pm.get('landing_desc') or '—'}"
                     + (f"（证据 {pm.get('landing_evidence')}）" if pm.get("landing_evidence") else "") + " |")
        _l1_label = ("第一级（攻占 PM）是否须投入航母" if _player_side() == "JAPAN"
                     else "第一级（死守 PM）是否须投入航母")
        _l1_val = ("**是**（登陆/掩护进行中）" if pm.get('level1_active') else "否")
        lines.append(f"| {_l1_label} | {_l1_val} |")
    if cs:
        lines.extend(["", "### 参谋部建议的航母前推位（**指挥层审核后执行**）"])
        lines.append(f"- **模式**：{cs.get('mode')}")
        if cs.get("hex"):
            _ea = cs.get("enemy_air_anchor") or {}
            lines.append(f"- **前推位**：`({cs['hex'][0]},{cs['hex'][1]})`"
                         f"（距锚点 {cs.get('distance_to_anchor_hex')} 格 / 距 PM {cs.get('distance_to_pm_hex')} 格"
                         f" / 距敌方机场 {_ea.get('name') or '—'} {cs.get('distance_to_enemy_air_hex')} 格）")
            lines.append(f"- **锚点推导**：{cs.get('anchor_derivation')}"
                         + (f"；敌方机场 {_ea.get('name')}（{_ea.get('airfield')} 级，"
                            f"距 PM {_ea.get('distance_hex')} 格）" if _ea else ""))
            _fs = cs.get("friendly_support_anchor") or {}
            if _fs:
                lines.append(f"- **退路基准**：{_fs.get('name')}（港口 {_fs.get('port')} 级，"
                             f"距 PM {_fs.get('distance_hex')} 格）——数据推导，非剧本地名")
            anc = cs.get("anchor") or {}
            lines.append(f"- **打击锚点**：{anc.get('desc')} `({anc.get('hex', [None, None])[0]},"
                         f"{anc.get('hex', [None, None])[1]})`")
        else:
            lines.append("- **前推位**：本回合不强行前推（无敌情）")
        lines.append(f"- **理由**：{cs.get('rationale')}")
        lines.append(f"- **固定红线**：{'无（已废除）' if cs.get('fixed_red_line') is None else cs.get('fixed_red_line')}")
        for n in (cs.get("risk_notes") or []):
            lines.append(f"- ⚠️ {n}")
        for alt in (cs.get("alternatives") or []):
            lines.append(f"  - 备选 `({alt['hex'][0]},{alt['hex'][1]})` 风险分 {alt['risk_score']}")

    # ★2026-09-25 新增★ 日军航母机会打击
    opp = p.get("carrier_opportunity") or {}
    if opp:
        lines.extend(["", "### 日军航母机会打击（**有机会即毫不犹豫出击**）"])
        lines.append(f"- **判定**：{opp.get('verdict')}")
        if opp.get("detected"):
            ech = opp.get("enemy_carrier_hex") or [None, None]
            sh = opp.get("strike_hex") or [None, None]
            lines.append(f"- **敌航母目击**：`({ech[0]},{ech[1]})`（{opp.get('enemy_carrier_intel_source')}）")
            lines.append(f"- **证据**：{opp.get('enemy_carrier_evidence')}")
            lines.append(f"- **打击位**：`({sh[0]},{sh[1]})`（距敌航母 "
                         f"{opp.get('distance_strike_to_enemy_cv_hex')} 格 / 距 PM "
                         f"{opp.get('distance_strike_to_pm_hex')} 格 / 距我舰当下 "
                         f"{opp.get('distance_own_cv_to_strike_hex')} 格）")
        lines.append(f"- **理由**：{opp.get('rationale')}")
        for n in (opp.get("risk_notes") or []):
            lines.append(f"- {n}")
        for alt in (opp.get("alternatives") or []):
            lines.append(f"  - 备选 `({alt['hex'][0]},{alt['hex'][1]})` 代价 {alt['cost']}")

    # ★2026-09-25 新增★ 侦察与搜索方案 + 敌航母邻近判定
    sp = p.get("search_plan") or {}
    prox = p.get("carrier_proximity") or {}
    rc = p.get("recon_contacts") or {}
    lines.extend(["", "### 侦察与搜索方案（侦察纪律：专职化 + 必须设扇面）"])
    lines.append(f"- **舰载机接触扫描**：{rc.get('note')}")
    lines.append(f"- **敌航母邻近判定**：{prox.get('verdict')}")
    if prox.get("proximity"):
        lines.append("- **推定证据**：")
        for e in (prox.get("evidence") or []):
            lines.append(f"  - {e}")
        lines.append(f"- **应对**：{prox.get('guidance')}")
        lines.append(f"- ⚠️ {prox.get('risk_note')}")
    if sp.get("assignments"):
        lines.append("")
        lines.append("| 中队 | 机型 | 角色 | 对海搜索 | ASW | 搜索扇面 |")
        lines.append("|---|---|---|---|---|---|")
        for a in sp["assignments"]:
            arc = (f"{a['arc_start']:03d}°→{a['arc_end']:03d}°"
                   if a.get("arc_start") is not None else "全向（未设扇面）")
            lines.append(f"| {a['ag']} | {a.get('type') or ''} | {a['role']} | "
                         f"{a['nav_search']}% | {a['asw_search']}% | {arc} |")
        ax = sp.get("principal_axis")
        if ax:
            lines.append(f"- **搜索主轴**：{ax.get('bearing_text')} —— 指向 {ax.get('source')} "
                         f"`({ax['hex'][0]},{ax['hex'][1]})`")
        lines.append(f"- {sp.get('doctrine')}")
        lines.append(f"- {sp.get('note')}")

    if p.get("carrier_advisories"):
        lines.extend(["", "### 航母风险提示（只报告，不自动纠偏）"])
        for n in p["carrier_advisories"]:
            lines.append(f"- {n}")

    lines.extend([
        "",
        "## 四、参谋部推荐战术行动清单（供用户审核执行）",
        "| 序号 | 目标部队 | 动作类型 | 关键参数 | 战术理由 | 置信度 |",
        "|---|---|---|---|---|---|"
    ])
    
    for idx, act in enumerate(p.get("recommended_actions", []), 1):
        ttype = act.get("target_type")
        tid = act.get("target_id")
        action = act.get("action")
        params = json.dumps(act.get("params", {}), ensure_ascii=False)
        rat = act.get("rationale", "")
        conf = f"{int(act.get('confidence', 0.8) * 100)}%"
        lines.append(f"| {idx} | `{ttype}:{tid}` | `{action}` | `{params}` | {rat} | {conf} |")
        
    lines.extend([
        "",
        "---",
        "💡 **前线指挥操作提示**：",
        "主 Agent 审查上述建议后，可直接在终端或会话中调用 `witp-cmd` 工具箱亲手向游戏下达指令并推进过回合。"
    ])
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="WitP-AE 作战参谋部 CLI 核心 (通用型)")
    subparsers = parser.add_subparsers(dest="command")
    
    p_brief = subparsers.add_parser("brief", help="读取当前游戏状态并出具通用《作战方案建议书》")
    p_brief.add_argument("--scraper", action="store_true", help="调用 witp_read.sh 重新解析存档")
    p_brief.add_argument("--save", default=None,
                         help="指定要解析的存档（槽位号 000/002/003、文件名或绝对路径）")
    p_brief.add_argument("--saves", action="store_true",
                         help="列出所有可用存档（含槽位、时间、日期）后退出")
    p_brief.add_argument("--json", action="store_true", help="输出纯 JSON 格式")
    p_brief.add_argument("--game-id", default="game-001", help="对局归档标识")
    p_brief.add_argument("--model", default=None, help="用户指定本回合主模型名称 (如 gemini-3.7-flash-high, step-5-preview)")
    p_brief.add_argument("--fallbacks", default=None, help="用户指定备用模型链，逗号分隔 (如 claude-sonnet-4-6,step-5-preview)")
    
    p_skb = subparsers.add_parser("skb", help="查看战略知识库当前教条与版本状态")
    
    args = parser.parse_args()

    # 列出存档后退出
    if getattr(args, "saves", False):
        rows = list_saves()
        print("=== 可用存档（按时间倒序）===")
        print(f"  {'槽位':<6}{'文件':<18}{'时间':<22}{'日期':<12}说明")
        for r in rows:
            print(f"  {r['slot'] or '--':<6}{r['file']:<18}{r['mtime_str']:<22}"
                  f"{str(r.get('date') or '?'):<12}{r['slot_meaning']}")
        print()
        print("  用法： witp-cmd staff --save <槽位|文件名|路径>")
        print("  例：   witp-cmd staff --save 000     # 读 Autosave（结算后新状态）")
        print("         witp-cmd staff --save 002     # 读 PreTurnSave（结算前旧状态）")
        return

    if args.command == "brief" or not args.command:
        run_sc = getattr(args, "scraper", False)
        gid = getattr(args, "game_id", None)
        if not gid or gid == "game-001":
            gid = _find_active_game_id()
        prop = generate_staff_proposal(run_scraper=run_sc, game_id=gid,
                                       save_spec=getattr(args, "save", None),
                                       override_model=getattr(args, "model", None),
                                       override_fallbacks=getattr(args, "fallbacks", None))
        if getattr(args, "json", False):
            print(json.dumps(prop, indent=2, ensure_ascii=False))
        else:
            print(format_proposal_markdown(prop))
    elif args.command == "skb":
        skb = load_skb()
        print("=== WitP-AE 战略知识库 (SKB) ===")
        print(skb.get("doctrines", "无教条内容"))

if __name__ == "__main__":
    main()
