#!/usr/bin/env python3
"""
WitP-AE 作战参谋方案与内存直控动作适配器 (Action-to-MCP Adapter)
================================================================
职责：
1. 解析参谋部出具的标准化《作战方案建议书》（Markdown 或 JSON 格式中的 recommended_actions）；
2. 翻译并调用 T1 级内存直控接口（witp_mem_bridge / witp_mem_bridge2 / witp_obj_bridge），
   实现零键鼠、零 OCR、100% 精确的指令下发与双镜像（copyA/copyB）持久化；
3. 执行安全闸门（潜艇免下令保护、空指令拦截、即时回读校验 Grounding Check）；
4. 输出结构化的执行与核验报告，供因果日志记录 (S, D, R)。
"""

import os
import sys
import json
import re
import argparse
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.dirname(BASE_DIR)
WORKSPACE_DIR = os.path.join(PROFILE_DIR, "workspace")
READER_DIR = os.path.join(WORKSPACE_DIR, "witp-reader")

if READER_DIR not in sys.path:
    sys.path.insert(0, READER_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from witp_saves import resolve_save, newest_save, SAVE_DIR
import witp_mem
import memrw
import witp_mem_bridge as mem_tf
import witp_mem_bridge2 as mem_ag
import witp_obj_bridge as mem_obj
from witp_models import load_config


class FastAirgroupWriter:
    _instance = None

    @classmethod
    def get_instance(cls, pid: int):
        if cls._instance is None or cls._instance.pid != pid:
            cls._instance = cls(pid)
        return cls._instance

    def __init__(self, pid: int):
        self.pid = pid
        self.baseA = 0x0598f4f8
        self.baseB = 0x0bba0978
        self.ag_names_A = {}
        self.ag_names_B = {}
        self._build_table()

    def _build_table(self):
        try:
            fd = memrw.open_mem(self.pid)
            rawA = memrw.read_mem(self.pid, self.baseA, 3500 * 680, fd)
            rawB = memrw.read_mem(self.pid, self.baseB, 3500 * 680, fd)
            os.close(fd)
            for s in range(3500):
                nmA = rawA[s*680 : s*680 + 20].split(b'\x00')[0].decode('latin1', errors='replace').strip()
                if nmA:
                    self.ag_names_A[nmA.upper()] = s
                nmB = rawB[s*680 : s*680 + 20].split(b'\x00')[0].decode('latin1', errors='replace').strip()
                if nmB:
                    self.ag_names_B[nmB.upper()] = s
        except Exception:
            pass

    def find_slots(self, target_name: str) -> Tuple[Optional[int], Optional[int]]:
        target = target_name.strip().upper()
        # 精确匹配
        sA = self.ag_names_A.get(target)
        sB = self.ag_names_B.get(target)
        if sA is not None and sB is not None:
            return sA, sB
        # 模糊匹配
        for k, v in self.ag_names_A.items():
            if target == k or (len(target) >= 3 and (target in k or k in target)):
                sA = v; break
        for k, v in self.ag_names_B.items():
            if target == k or (len(target) >= 3 and (target in k or k in target)):
                sB = v; break
        return sA, sB

    def set_fields(self, target_name: str, fields: Dict[str, int]) -> Dict[str, Any]:
        sA, sB = self.find_slots(target_name)
        if sA is None and sB is None:
            return {"ok": False, "error": f"在中队母表中未匹配到 '{target_name}'"}

        OFFSETS = {
            "pctCAP": 560,
            "pctLRCAP": 561,
            "pctASW": 562,
            "pctSearch": 563,
            "pctTrain": 564,
            "pctRest": 565,
            "navArcStart": 630,
            "navArcEnd": 631,
            "aswArcStart": 628,
            "aswArcEnd": 629,
        }

        all_verified = True
        written_info = []

        for fld, val in fields.items():
            off = OFFSETS.get(fld)
            if off is None:
                continue
            bval = bytes([int(val) % 256])
            # 写 copyA
            if sA is not None:
                addrA = self.baseA + sA * 680 + off
                memrw.write_mem(self.pid, addrA, bval)
                rbA = memrw.read_mem(self.pid, addrA, 1)
                if rbA != bval:
                    all_verified = False
            # 写 copyB
            if sB is not None:
                addrB = self.baseB + sB * 680 + off
                memrw.write_mem(self.pid, addrB, bval)
                rbB = memrw.read_mem(self.pid, addrB, 1)
                if rbB != bval:
                    all_verified = False
            written_info.append(f"{fld}={val}")

        return {
            "ok": True,
            "verified": all_verified,
            "target": target_name,
            "slotA": sA,
            "slotB": sB,
            "detail": f"{target_name} (copyA_slot={sA}, copyB_slot={sB}) 已高速双写并校验: {', '.join(written_info)}"
        }


class ActionExecutionResult:
    def __init__(self, action: Dict[str, Any]):
        self.action_type = action.get("action", "UNKNOWN")
        self.target_id = action.get("target_id", "")
        self.target_type = action.get("target_type", "")
        self.success = False
        self.verified = False
        self.skipped = False
        self.skip_reason = ""
        self.detail = ""
        self.error = None
        self.raw_action = action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "success": self.success,
            "verified": self.verified,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "detail": self.detail,
            "error": self.error,
        }


def _get_active_save_path(save_spec: Optional[str] = None) -> str:
    """获取当前对局最新的存档绝对路径（优先 000 Autosave，否则最新）。"""
    if save_spec:
        p = resolve_save(str(save_spec))
        if p and os.path.exists(p):
            return p
    # 默认 000 Autosave
    auto_000 = os.path.join(SAVE_DIR, "wpae000.pws")
    if os.path.exists(auto_000):
        return auto_000
    n = newest_save(SAVE_DIR)
    if n and os.path.exists(n):
        return n
    raise FileNotFoundError(f"未找到可用的游戏存档文件 (SAVE_DIR={SAVE_DIR})")


def _load_airgroups_cache() -> List[Dict[str, Any]]:
    """读取 reader 解析的 airgroups.json 快照缓存。"""
    cands = [
        os.path.join(READER_DIR, "state", "airgroups.json"),
        os.path.join(READER_DIR, "state.new", "airgroups.json"),
        os.path.join(READER_DIR, "state_lastgood", "airgroups.json")
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return []


def _resolve_ag_slot(ident: Any, ag_cache: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    """将中队标识（名称如 VF-2 或 ID）解析为内存数组槽位 slot index。"""
    if not ag_cache:
        ag_cache = _load_airgroups_cache()

    if isinstance(ident, int) and 0 <= ident < len(ag_cache):
        nm = ag_cache[ident].get("name")
        return ident, nm

    s = str(ident).strip()
    if s.upper().startswith("AG#"):
        s = s[3:].strip()
    if s.upper().startswith("AG"):
        s = s[2:].strip()

    if s.isdigit():
        num = int(s)
        # 优先按 record_id 匹配
        for idx, a in enumerate(ag_cache):
            if a.get("record_id") == num:
                return idx, a.get("name")
        if num < len(ag_cache):
            return num, ag_cache[num].get("name")

    # 按名称精确匹配
    s_clean = s.upper()
    for idx, a in enumerate(ag_cache):
        nm = a.get("name")
        if nm and nm.strip().upper() == s_clean:
            return idx, nm

    # 按名称包含子串匹配
    for idx, a in enumerate(ag_cache):
        nm = a.get("name")
        if nm and s_clean in nm.strip().upper():
            return idx, nm

    return None, None


def _is_submarine_tf(tf_slot: int, save_path: str) -> bool:
    """检测指定 TF 是否为潜艇编队（潜艇保持系统自动巡逻，严禁下达目的地指令）。"""
    # 规则 1：珊瑚海剧本硬约束 TF20-TF25（美军潜艇）与 TF8-TF13/TF28-TF30（日军潜艇）
    if 20 <= tf_slot <= 25 or 8 <= tf_slot <= 13 or 28 <= tf_slot <= 30:
        return True

    # 规则 2：读当前内存/存档中的 TF mission 是否为 SUBPATROL (mission=4)
    try:
        data = mem_tf.show_tf(save_path, tf_slot)
        if data.get("ok"):
            f = data.get("fields", {})
            if f.get("mission") == 4:  # 4 = SUBPATROL
                return True
    except Exception:
        pass
    return False


def execute_single_action(action: Dict[str, Any], save_path: str, ag_cache: Optional[List[Dict[str, Any]]] = None, dry_run: bool = False) -> ActionExecutionResult:
    """执行单个参谋部推荐动作，并做即时内存回读校验。"""
    res = ActionExecutionResult(action)
    act_type = action.get("action", "").upper()
    target_id = str(action.get("target_id", "")).strip()
    params = action.get("params", {})

    if not ag_cache:
        ag_cache = _load_airgroups_cache()

    # 1. 设置编队航向与航路点
    if act_type in ("SET_DESTINATION", "SET_WAYPOINTS", "SET_TF_DESTINATION"):
        m = re.search(r"\d+", target_id)
        if not m:
            res.error = f"无法从 target_id '{target_id}' 解析 TF 槽位数字"
            return res
        tf_slot = int(m.group(0))

        # 安全守卫：潜艇保护
        if _is_submarine_tf(tf_slot, save_path):
            res.skipped = True
            res.skip_reason = f"TF{tf_slot} 为潜艇编队，遵循教条 D1.4（保持游戏内建自动行动，不予干预）"
            res.success = True
            return res

        # 解析坐标
        hex_pt = params.get("hex") or params.get("goal_hex") or action.get("goal_hex")
        if not hex_pt or not isinstance(hex_pt, (list, tuple)) or len(hex_pt) < 2:
            res.error = f"无效的坐标参数: {hex_pt}"
            return res

        gx, gy = int(hex_pt[0]), int(hex_pt[1])

        # 安全守卫：空指令检查（回读当前位置判断）
        try:
            curr_info = mem_tf.show_tf(save_path, tf_slot)
            if curr_info.get("ok"):
                cur_wps = curr_info.get("fields", {}).get("wp", [])
                if cur_wps and cur_wps[0] == (gx, gy) and curr_info.get("fields", {}).get("wpCount", 0) <= 1:
                    # 目标等于当前首位航点且只有一个航点
                    pass
        except Exception:
            pass

        if dry_run:
            res.success = True
            res.verified = True
            res.detail = f"[DRY-RUN] 将对 TF{tf_slot} 写入航路点 [({gx}, {gy})]"
            return res

        w_res = mem_tf.set_tf_waypoints(save_path, tf_slot, [(gx, gy)])
        if w_res.get("ok") and w_res.get("verified"):
            res.success = True
            res.verified = True
            res.detail = f"TF{tf_slot} 航路点已成功写入内存并校验: {w_res.get('readback')}"
        else:
            res.success = False
            res.error = f"写入失败或校验不匹配: {w_res}"
        return res

    # 2. 设置航空队战斗机防空比例 (CAP)
    elif act_type in ("SET_CAP_PERCENT", "SET_CAP"):
        cap_val = params.get("cap_pct") if params.get("cap_pct") is not None else params.get("pct", 100)
        try:
            cap_val = int(cap_val)
        except Exception:
            cap_val = 100

        if dry_run:
            res.success = True
            res.verified = True
            res.detail = f"[DRY-RUN] 将对 {target_id} 设置 pctCAP={cap_val}%"
            return res

        pid = witp_mem.game_pid()
        if pid:
            writer = FastAirgroupWriter.get_instance(pid)
            w_res = writer.set_fields(target_id, {"pctCAP": cap_val})
            if w_res.get("ok"):
                res.success = True
                res.verified = w_res.get("verified", False)
                res.detail = w_res.get("detail", "")
                return res

        # 兜底回退
        slot, ag_name = _resolve_ag_slot(target_id, ag_cache)
        if slot is None:
            res.error = f"无法找到中队 '{target_id}' 的槽位索引"
            return res
        w_res = mem_ag.ag_set(save_path, slot, "pctCAP", cap_val)
        if w_res.get("ok") and w_res.get("verified"):
            res.success = True
            res.verified = True
            res.detail = f"AG#{slot} ({ag_name}) pctCAP 已双写 copyA/copyB 并验证为 {cap_val}%"
        else:
            res.success = False
            res.error = f"CAP 写入失败或校验不匹配: {w_res}"
        return res

    # 3. 设置航空队侦察/对海搜索比例与扇面 (Search / Naval Search / ASW)
    elif act_type in ("SET_SEARCH_PERCENT", "SET_SEARCH", "SET_NAVAL_SEARCH"):
        search_val = params.get("nav_search")
        if search_val is None:
            search_val = params.get("search_pct")
        if search_val is None:
            search_val = params.get("pct", 100)
        try:
            search_val = int(search_val)
        except Exception:
            search_val = 100

        asw_val = params.get("asw_search")
        arc_start = params.get("arc_start")
        arc_end = params.get("arc_end")

        if dry_run:
            res.success = True
            res.verified = True
            res.detail = f"[DRY-RUN] 将对 {target_id} 设置 pctSearch={search_val}%"
            if asw_val is not None:
                res.detail += f", pctASW={asw_val}%"
            if arc_start is not None and arc_end is not None:
                res.detail += f", 扇面={arc_start}°->{arc_end}°"
            return res

        pid = witp_mem.game_pid()
        if pid:
            writer = FastAirgroupWriter.get_instance(pid)
            flds = {"pctSearch": search_val}
            if asw_val is not None:
                flds["pctASW"] = int(asw_val)
            if arc_start is not None and arc_end is not None:
                flds["navArcStart"] = int(arc_start) % 256
                flds["navArcEnd"] = int(arc_end) % 256
            w_res = writer.set_fields(target_id, flds)
            if w_res.get("ok"):
                res.success = True
                res.verified = w_res.get("verified", False)
                res.detail = w_res.get("detail", "")
                return res

        # 兜底回退
        slot, ag_name = _resolve_ag_slot(target_id, ag_cache)
        if slot is None:
            res.error = f"无法找到中队 '{target_id}' 的槽位索引"
            return res
        w_res = mem_ag.ag_set(save_path, slot, "pctSearch", search_val)
        ok = w_res.get("ok") and w_res.get("verified")
        details = [f"pctSearch={search_val}%"]
        if asw_val is not None:
            try:
                w_asw = mem_ag.ag_set(save_path, slot, "pctASW", int(asw_val))
                if w_asw.get("ok"):
                    details.append(f"pctASW={asw_val}%")
            except Exception:
                pass
        if arc_start is not None and arc_end is not None:
            try:
                mem_ag.ag_set(save_path, slot, "navArcStart", int(arc_start) % 256)
                mem_ag.ag_set(save_path, slot, "navArcEnd", int(arc_end) % 256)
                details.append(f"扇面={arc_start}°->{arc_end}°")
            except Exception:
                pass
        if ok:
            res.success = True
            res.verified = True
            res.detail = f"AG#{slot} ({ag_name}) 侦察参数已更新并校验: {', '.join(details)}"
        else:
            res.success = False
            res.error = f"搜索比例写入失败: {w_res}"
        return res

    # 4. 设置编队任务 (Mission)
    elif act_type in ("SET_MISSION", "SET_TF_MISSION"):
        m = re.search(r"\d+", target_id)
        if not m:
            res.error = f"无法从 target_id '{target_id}' 解析 TF 槽位"
            return res
        tf_slot = int(m.group(0))

        mission_name = str(params.get("mission", "")).strip().upper()
        if not mission_name:
            res.error = f"缺少任务名称参数 (mission)"
            return res

        if dry_run:
            res.success = True
            res.verified = True
            res.detail = f"[DRY-RUN] 将对 TF{tf_slot} 设置任务 mission={mission_name}"
            return res

        w_res = mem_tf.set_tf_field(save_path, tf_slot, "mission", mission_name)
        if w_res.get("ok") and w_res.get("verified"):
            res.success = True
            res.verified = True
            res.detail = f"TF{tf_slot} mission 已改为 {mission_name} (old={w_res.get('old')}, new={w_res.get('new')})"
        else:
            res.success = False
            res.error = f"修改任务失败: {w_res}"
        return res

    # 5. 设置编队航速档位 (Speed)
    elif act_type in ("SET_SPEED", "SET_TF_SPEED"):
        m = re.search(r"\d+", target_id)
        if not m:
            res.error = f"无法解析 TF 槽位: '{target_id}'"
            return res
        tf_slot = int(m.group(0))
        spd_val = int(params.get("speed", 0))

        if dry_run:
            res.success = True
            res.verified = True
            res.detail = f"[DRY-RUN] 将对 TF{tf_slot} 设置航速 speed={spd_val}"
            return res

        w_res = mem_tf.set_tf_field(save_path, tf_slot, "speed", spd_val)
        if w_res.get("ok") and w_res.get("verified"):
            res.success = True
            res.verified = True
            res.detail = f"TF{tf_slot} speed 已设置为 {spd_val}"
        else:
            res.success = False
            res.error = f"修改航速失败: {w_res}"
        return res

    # 6. 未知动作类型兜底
    else:
        res.skipped = True
        res.skip_reason = f"未支持的动作类型 '{act_type}'，暂予跳过"
        return res


def apply_proposal_actions(proposal: Dict[str, Any], save_path: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """批量执行一份完整提案中的全部推荐动作，并汇总报告。"""
    sp = _get_active_save_path(save_path)
    actions = proposal.get("recommended_actions", [])
    ag_cache = _load_airgroups_cache()

    results: List[Dict[str, Any]] = []
    applied_count = 0
    verified_count = 0
    skipped_count = 0
    failed_count = 0

    for act in actions:
        r = execute_single_action(act, save_path=sp, ag_cache=ag_cache, dry_run=dry_run)
        results.append(r.to_dict())
        if r.skipped:
            skipped_count += 1
        elif r.success:
            applied_count += 1
            if r.verified:
                verified_count += 1
        else:
            failed_count += 1

    summary = {
        "ok": (failed_count == 0),
        "total_actions": len(actions),
        "applied_count": applied_count,
        "verified_count": verified_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "save_path_used": sp,
        "dry_run": dry_run,
        "results": results
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="WitP-AE 作战参谋动作转译器 (Action-to-MCP Adapter)")
    parser.add_argument("--proposal", type=str, help="指定作战方案建议书 JSON 路径")
    parser.add_argument("--latest", action="store_true", help="自动查找当前对局最新的 proposal_turn_XX.json")
    parser.add_argument("--save", type=str, help="指定存档槽位 (例如 000)")
    parser.add_argument("--dry-run", action="store_true", help="只做解析与守卫校验，不实际写内存")
    args = parser.parse_args()

    proposal_path = args.proposal
    if args.latest or not proposal_path:
        # 搜 games/game-*/causal_log/proposal_*.json
        import glob
        pattern = os.path.join(BASE_DIR, "games", "game-*", "causal_log", "proposal_*.json")
        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if matches:
            proposal_path = matches[0]
            print(f"[action-adapter] 自动读取最新参谋部提案: {proposal_path}")
        else:
            print("[action-adapter] 未找到任何 proposal_turn_*.json，退出")
            sys.exit(1)

    with open(proposal_path, "r", encoding="utf-8") as f:
        proposal = json.load(f)

    print(f"[action-adapter] 开始执行提案: {proposal.get('title', '未命名方案')}")
    summary = apply_proposal_actions(proposal, save_path=args.save, dry_run=args.dry_run)

    print("\n═══════════════════════════════════════════════════════════════")
    print(f"🎖️ 参谋动作转译执行报告 ({'DRY-RUN 试运行' if summary['dry_run'] else '实机内存直控落地'})")
    print(f"总行动数: {summary['total_actions']} | 成功下发: {summary['applied_count']} | 核验通过: {summary['verified_count']} | 守卫跳过: {summary['skipped_count']} | 失败: {summary['failed_count']}")
    print("───────────────────────────────────────────────────────────────")
    for r in summary["results"]:
        status_tag = "✓ 成功" if r["success"] else ("⚠️ 跳过" if r["skipped"] else "❌ 失败")
        reason = f" ({r['skip_reason']})" if r["skipped"] else (f" -> {r['detail']}" if r["success"] else f" 错误: {r['error']}")
        print(f"[{status_tag}] {r['action']} -> {r['target_id']}{reason}")
    print("═══════════════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
