#!/usr/bin/env python3
"""
WitP-AE Self-Iterating Agent Master Orchestrator (Modern Memory-Direct Version)
================================================================================
核心职责：
驱动内循环、中循环与外循环的自动化推演闭环：
1. 认知与决策 (Understand & Strategize)：
   调用作战参谋本部核心引擎 (witp_staff.py)，结合当前剧本与最新存档、
   融合 SKB 战略教条，由云端/本地大模型与战术评估引擎生成《作战方案建议书》与标准化 Action。
2. 动作下发与闭环核验 (Execute & Verify)：
   调用内存直控转译适配器 (witp_action_adapter.py)，直接操作进程内存（T1 零键鼠通道），
   完成编队航路点、中队 CAP/搜索扇面、任务航速等指令的高精度写入与双镜像持久化校验。
3. 因果记录三元组 (Middle Loop Causal Log)：
   记录 (S_situation, D_decision, R_result) 至当前对局目录，支撑战略复盘与跨局迭代进化。
4. 回合推进 (Advance Turn)：
   若指定 --advance，执行安全推进过回合（含终局画面保护与 Autosave 更新等待）。
"""

import os
import sys
import json
import time
import argparse
from typing import Dict, Any, List, Optional

_VENV_PY = "/root/.hermes/hermes-agent/venv/bin/python3"
if sys.executable != _VENV_PY and os.path.exists(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY] + sys.argv)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from witp_staff import generate_staff_proposal, _find_active_game_id
from witp_action_adapter import apply_proposal_actions, _get_active_save_path
from witp_saves import resolve_save, newest_save, SAVE_DIR
from lib.executor import end_turn, game_has_ended

GAMES_DIR = os.path.join(BASE_DIR, "games")
LOGS_DIR = os.path.join(BASE_DIR, "logs")


def run_single_turn(game_id: Optional[str] = None,
                    advance_turn: bool = False,
                    save_spec: Optional[str] = None,
                    dry_run: bool = False,
                    override_model: Optional[str] = None,
                    override_fallbacks: Optional[str] = None) -> Dict[str, Any]:
    """执行单个完整的回合闭环。"""
    if not game_id or game_id == "game-001":
        game_id = _find_active_game_id()

    print(f"\n[orchestrator] 🚀 启动回合推演闭环 (活跃对局: {game_id}, dry_run={dry_run}, advance_turn={advance_turn})")

    # 1. 确定存档路径
    save_path = _get_active_save_path(save_spec)
    print(f"[orchestrator] ① 选定当前基准存档: {save_path}")

    # 2. 呼叫参谋本部生成作战方案
    print("[orchestrator] ② 参谋部研判中 (SKB 教条融合 + 大模型 System 2 推理)...")
    proposal = generate_staff_proposal(
        run_scraper=False,
        game_id=game_id,
        save_spec=save_spec,
        override_model=override_model,
        override_fallbacks=override_fallbacks
    )

    turn_num = proposal.get("turn", 1)
    turn_date = proposal.get("date", "05/01/42")
    scenario_name = proposal.get("scenario", "The Battle of the Coral Sea")
    actions = proposal.get("recommended_actions", [])

    print(f"[orchestrator] ③ 参谋部已出具方案: 《{proposal.get('title', '方案建议书')}》")
    print(f"               推演日期: {turn_date} | 推荐动作数: {len(actions)}")
    print(f"               宏观意图: {proposal.get('strategic_intent', '')[:80]}...")

    # 3. 内存直控执行与即时核验 (T1 零键鼠通道)
    print("[orchestrator] ④ 启动内存直控适配器执行动作 (T1 零键鼠直写)...")
    exec_summary = apply_proposal_actions(proposal, save_path=save_path, dry_run=dry_run)
    print(f"[orchestrator]    下发结果: 总计 {exec_summary['total_actions']} 条 | "
          f"成功 {exec_summary['applied_count']} 条 | "
          f"校验通过 {exec_summary['verified_count']} 条 | "
          f"守卫跳过 {exec_summary['skipped_count']} 条 | "
          f"失败 {exec_summary['failed_count']} 条")

    # 4. 记录因果三元组 (S, D, R)
    print("[orchestrator] ⑤ 回写因果三元组 (S, D, R) 到对局日志...")
    causal_dir = os.path.join(GAMES_DIR, game_id, "causal_log")
    os.makedirs(causal_dir, exist_ok=True)

    triplet = {
        "turn": turn_num,
        "date": turn_date,
        "scenario": scenario_name,
        "recorded_at": time.time(),
        "recorded_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "S_situation": {
            "scenario": scenario_name,
            "date": turn_date,
            "turn": turn_num,
            "threat_regions": proposal.get("situation_summary", {}).get("threat_regions", {}),
            "pm_status": proposal.get("pm_status", {}),
            "carrier_station": proposal.get("carrier_station", {}),
            "source_save": save_path
        },
        "D_decision": {
            "strategic_intent": proposal.get("strategic_intent", ""),
            "model_used": proposal.get("active_model_used", ""),
            "recommended_actions": actions,
            "guards_applied": proposal.get("guards_applied", [])
        },
        "R_result": {
            "execution_summary": {
                "applied_count": exec_summary["applied_count"],
                "verified_count": exec_summary["verified_count"],
                "skipped_count": exec_summary["skipped_count"],
                "failed_count": exec_summary["failed_count"],
                "dry_run": dry_run
            },
            "action_details": exec_summary["results"]
        }
    }

    log_file = os.path.join(causal_dir, f"turn_{turn_num:02d}.json")
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(triplet, f, indent=2, ensure_ascii=False)
    print(f"[orchestrator]    因果日志已持久化: {log_file}")

    # 5. 推进回合 (Advance Turn)
    advance_result = {"advanced": False, "note": "未请求推进回合"}
    if advance_turn and not dry_run:
        print("[orchestrator] ⑥ 检查终局屏并推进过回合 (E -> YES)...")
        ended = game_has_ended()
        if ended:
            print(f"[orchestrator] ⛔ 游戏已终局 ({ended.get('keyword')})，停止发送过回合指令。")
            advance_result = {"advanced": False, "ended": True, "details": ended}
        else:
            success = end_turn(wait_for_save=True, timeout_sec=300)
            if success:
                print("[orchestrator] ✓ 回合结算完成！新 Autosave 存档已生成。")
                advance_result = {"advanced": True, "success": True}
            else:
                print("[orchestrator] ⚠️ 过回合结算未确认，请检查游戏窗口或进程。")
                advance_result = {"advanced": False, "success": False, "error": "结算超时或窗口未响应"}

    final_result = {
        "ok": (exec_summary["failed_count"] == 0),
        "turn": turn_num,
        "date": turn_date,
        "scenario": scenario_name,
        "actions_total": exec_summary["total_actions"],
        "actions_applied": exec_summary["applied_count"],
        "actions_verified": exec_summary["verified_count"],
        "actions_skipped": exec_summary["skipped_count"],
        "actions_failed": exec_summary["failed_count"],
        "causal_log": log_file,
        "advance_result": advance_result
    }
    return final_result


def main():
    parser = argparse.ArgumentParser(description="WitP-AE 回合推演主编排器")
    parser.add_argument("--advance", action="store_true", help="下发指令后自动推进过回合 (E -> YES)")
    parser.add_argument("--game-id", type=str, help="指定对局目录 (如 game-108)")
    parser.add_argument("--save", type=str, help="指定存档槽位 (如 000)")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式，不下发实际内存指令")
    parser.add_argument("--model", type=str, help="临时指定参谋大模型")
    parser.add_argument("--fallbacks", type=str, help="临时指定备用模型链")
    args = parser.parse_args()

    res = run_single_turn(
        game_id=args.game_id,
        advance_turn=args.advance,
        save_spec=args.save,
        dry_run=args.dry_run,
        override_model=args.model,
        override_fallbacks=args.fallbacks
    )
    print("\n[orchestrator] 执行完毕，最终摘要:")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
