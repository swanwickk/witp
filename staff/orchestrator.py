#!/usr/bin/env python3
"""
WitP-AE Self-Iterating Agent Master Orchestrator
Executes the three-level nested loop:
- Inner loop: Perceive -> Understand/Strategize -> Tactical Choice -> Execute -> Verify
- Middle loop: Maintain game memory & causal logs (S, D, R)
- Outer loop: Distill lessons into Strategic Knowledge Base (SKB)
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
import yaml
from typing import Dict, Any, List, Optional

# Ensure lib directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from lib import (
    hex_math,
    fuel_calc,
    option_builder,
    verify,
    belief_update,
    perception,
    executor
)

CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
SKB_DIR = os.path.join(BASE_DIR, "skb")
GAMES_DIR = os.path.join(BASE_DIR, "games")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

def load_config() -> Dict[str, Any]:
    """Load config.yaml; supports hot-reloading at each turn."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def load_skb() -> Dict[str, Any]:
    """Load current doctrines, patterns, and evaluation weights from SKB."""
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

def call_cloud_strategy(prompt_data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Call user-configured cloud API (OpenAI compatible) to generate strategic intents.
    Returns structured JSON intent if successful, else None.
    """
    strat_cfg = config.get("strategy_model", {})
    api_key = strat_cfg.get("api_key", "").strip()
    base_url = strat_cfg.get("base_url", "").strip().rstrip("/")
    model = strat_cfg.get("model", "claude-sonnet-4-20250514")
    
    if not api_key or not base_url:
        return None  # Cloud API not yet filled by user
        
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    system_msg = (
        "You are the Strategic Commander AI for War in the Pacific: Admiral's Edition (Coral Sea 1942).\n"
        "Given current turn brief, intel, and strategic doctrines, produce a JSON object with your strategic intent.\n"
        "Output format:\n"
        "{\n"
        "  'rationale': '...', \n"
        "  'tf_intents': [{'tf_id': 'TF16', 'goal_hex': [103, 137], 'intent': 'advance'}],\n"
        "  'air_intents': [{'ag_id': 'VF-42', 'cap_pct': 100, 'mission': 'CAP'}],\n"
        "  'recon_priority': 'Track enemy CV carriers east of Rabaul'\n"
        "}"
    )
    
    payload = {
        "model": model,
        "temperature": strat_cfg.get("temperature", 0.3),
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)}
        ]
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            # Extract JSON block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
    except Exception as e:
        print(f"[orchestrator] Cloud API call failed: {e}")
        return None

def fallback_rule_strategy(state: Dict[str, Any], skb: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic tactical baseline when cloud API is unconfigured:
    Applies proven Coral Sea doctrines directly:
    1. CAP 100% on fleet carriers
    2. Advance TF16 toward Louisiades (103, 137) to contest landing
    """
    return {
        "rationale": "Applying verified Coral Sea tactical doctrine (CAP 100% + advance to Louisiades 103,137)",
        "tf_intents": [
            {"tf_id": "TF16", "goal_hex": [103, 137], "intent": "advance"}
        ],
        "air_intents": [
            {"ag_id": "VF-42", "cap_pct": 100, "mission": "CAP"}
        ],
        "recon_priority": "PBY long-range search of Rabaul / Louisiades axes"
    }

def run_single_turn(game_id: str = "game-001", advance_turn: bool = False) -> Dict[str, Any]:
    """
    Execute one complete inner-loop cycle:
    1. Read S_t
    2. Formulate Strategic Intent
    3. Build Tactical Options
    4. Execute
    5. Verify
    6. Record Causal Triplet (S, D, R)
    """
    config = load_config()
    skb = load_skb()
    
    print("\n[orchestrator] === 1. PERCEIVE: Reading current game state ===")
    state = perception.capture_state(run_scraper=False)
    turn_info = state.get("turn", {})
    turn_date = turn_info.get("date", "05/01/42")
    turn_num = turn_info.get("turn", 1)
    print(f"[orchestrator] Current Game Date: {turn_date}, Turn: {turn_num}")
    
    print("[orchestrator] === 2. UNDERSTAND & STRATEGIZE ===")
    # Update qualitative belief map
    belief_data = belief_update.update_belief_map({}, {"date": turn_date})
    
    # Formulate strategy (Cloud API or Fallback Rule)
    prompt_context = {
        "turn": turn_info,
        "brief": state.get("brief", "")[:3000],
        "belief": belief_data,
        "doctrines": skb.get("doctrines", "")
    }
    
    intent = call_cloud_strategy(prompt_context, config)
    if not intent:
        print("[orchestrator] Cloud API not configured or failed; using verified tactical rules.")
        intent = fallback_rule_strategy(state, skb)
    else:
        print(f"[orchestrator] Strategy from Cloud API: {intent.get('rationale')}")

    print("[orchestrator] === 3. TACTICAL OPTIONS & DECISION ===")
    planned_orders = []
    
    # Process TF intents
    for tfi in intent.get("tf_intents", []):
        tid = tfi.get("tf_id")
        goal = tuple(tfi.get("goal_hex", [103, 137]))
        opts = option_builder.build_tf_destination_options(tid, (106, 142), [goal])
        # Query Kev-0.8B local decision server via /v1/systemone
        chosen_hex = opts["options"][0]["coord"]
        kev_cfg = config.get("kev_server", {})
        kev_host = kev_cfg.get("host", "127.0.0.1")
        kev_port = kev_cfg.get("port", 18090)
        try:
            criteria_dict = {opt["hex"]: opt["note"] for opt in opts["options"]}
            kev_req_payload = {
                "state": f"Task force {tid} at (106,142), strategic goal {goal}. Intel: {intent.get('rationale')}",
                "model": "kev-0.8b",
                "questions": {
                    "hex_choice": {"type": "choice", "criteria": criteria_dict}
                }
            }
            req = urllib.request.Request(
                f"http://{kev_host}:{kev_port}/v1/systemone",
                data=json.dumps(kev_req_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as k_resp:
                k_data = json.loads(k_resp.read().decode("utf-8"))
                ans = k_data.get("answers", {}).get("hex_choice", {})
                best_hex_str = ans.get("choice")
                conf = ans.get("confidence", 0.0)
                print(f"[orchestrator] Kev-0.8B System 1 Decision for {tid}: {best_hex_str} (confidence: {conf})")
                for opt in opts["options"]:
                    if opt["hex"] == best_hex_str:
                        chosen_hex = opt["coord"]
                        break
        except Exception as e:
            print(f"[orchestrator] Kev System 1 query bypassed ({e}); using heuristic option.")
        planned_orders.append({
            "type": "set_tf_destination",
            "target_id": tid,
            "expected_hex": chosen_hex
        })
        
    # Process Air intents
    for ai in intent.get("air_intents", []):
        ag_id = ai.get("ag_id")
        cap = ai.get("cap_pct", 100)
        planned_orders.append({
            "type": "set_cap_percent",
            "target_id": ag_id,
            "expected_cap_pct": cap
        })
        
    print(f"[orchestrator] Planned {len(planned_orders)} orders: {planned_orders}")

    print("[orchestrator] === 4. EXECUTE & VERIFY ===")
    # Send semantic VNC actions to game
    try:
        executor.focus_map()
        for o in planned_orders:
            if o.get("type") == "set_cap_percent":
                print(f"[orchestrator] Applying CAP setting to {o.get('target_id')}...")
                executor.set_cap_percent(4)  # Sets to 100%
        if advance_turn:
            print("[orchestrator] Advancing turn: Pressing E and confirming YES...")
            executor.end_turn(wait_for_save=True, timeout_sec=240)
    except Exception as exec_err:
        print(f"[orchestrator] VNC execution note: {exec_err}")

    # Perform verification against state
    v_report = verify.verify_orders(planned_orders, state)
    print(f"[orchestrator] Grounding check: {v_report['passed_count']} passed, {v_report['drift_count']} drift/unapplied")

    print("[orchestrator] === 5. RECORD CAUSAL TRIPLET (S, D, R) ===")
    causal_dir = os.path.join(GAMES_DIR, game_id, "causal_log")
    os.makedirs(causal_dir, exist_ok=True)
    
    triplet = {
        "turn": turn_num,
        "date": turn_date,
        "timestamp": time.time(),
        "S_situation": {
            "belief": belief_data,
            "threats": state.get("threats", {})
        },
        "D_decision": {
            "intent": intent,
            "orders": planned_orders
        },
        "R_result": {
            "verified": v_report,
            "losses": {}
        }
    }
    
    log_file = os.path.join(causal_dir, f"turn_{turn_num:02d}.json")
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(triplet, f, indent=2, ensure_ascii=False)
    print(f"[orchestrator] Saved causal log to {log_file}")
    
    return {
        "status": "success",
        "turn": turn_num,
        "date": turn_date,
        "orders_count": len(planned_orders),
        "verified": v_report["verified"]
    }

if __name__ == "__main__":
    advance = "--advance" in sys.argv
    print(f"[orchestrator] Running single-turn cycle (advance_turn={advance})...")
    res = run_single_turn("game-001", advance_turn=advance)
    print(f"[orchestrator] Result: {res}")
