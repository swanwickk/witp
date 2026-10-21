#!/usr/bin/env python3
"""
witp-cmd 参谋管理 + 回写闭环扩展模块

被 witp-cmd 以 `from witp_cmd_staffops import ...` 方式导入。
提供：
  参谋体检/修复     staff_check() / staff_fix() / staff_resync()
  回写因果三元组    record_turn(...)
  归档对局战果      close_game(...)
  追加教条并提交    skb_add_doctrine(...)
"""

import os
import re
import sys
import json
import time
import glob
import shutil
import subprocess
from datetime import datetime

AGENT_DIR = "/root/.hermes/profiles/witp/witp-agent"
SKB_DIR = os.path.join(AGENT_DIR, "skb")
GAMES_DIR = os.path.join(AGENT_DIR, "games")
RESULTS_LEDGER = os.path.join(GAMES_DIR, "results.json")

READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
STATE_DIR = os.path.join(READER_DIR, "state")
LASTGOOD_DIR = os.path.join(READER_DIR, "state_lastgood")
TURN_JSON = os.path.join(STATE_DIR, "turn.json")
SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"

API = "http://127.0.0.1:18091/api/plugins/witp-dashboard"
SERVICES = ["witp-dashboard.service", "witp-watcher.service", "witp-kev.service"]


# ─────────────────────────── 工具函数 ───────────────────────────

def _sh(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def _svc_active(name):
    rc, out, _ = _sh(f"systemctl is-active {name}", timeout=15)
    return out.strip() == "active"


def _save_mtime():
    m = 0.0
    for f in ("wpae002.pws", "wpae000.pws"):
        p = os.path.join(SAVE_DIR, f)
        if os.path.exists(p):
            try:
                m = max(m, os.path.getmtime(p))
            except OSError:
                pass
    return m


def _read_turn():
    for base in (STATE_DIR, LASTGOOD_DIR):
        fp = os.path.join(base, "turn.json")
        if os.path.exists(fp):
            try:
                d = json.load(open(fp, encoding="utf-8"))
                if d.get("game_date") or d.get("date"):
                    return d, base
            except Exception:
                pass
    return {}, None


def _api_post(path, timeout=300):
    rc, out, err = _sh(
        f'curl -s -m {timeout} -X POST {API}{path} -H "Content-Type: application/json"',
        timeout=timeout + 20)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def _api_get(path, timeout=30):
    rc, out, _ = _sh(f'curl -s -m {timeout} {API}{path}', timeout=timeout + 10)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


# ─────────────────────────── 参谋体检 ───────────────────────────

def staff_check(verbose=True):
    """参谋部全面体检。返回 (healthy: bool, report: dict)。"""
    issues = []
    rep = {}

    # 1. 三个服务
    svc = {}
    for s in SERVICES:
        ok = _svc_active(s)
        svc[s] = ok
        if not ok:
            issues.append(f"服务未运行: {s}")
    rep["services"] = svc

    # 2. API 可达
    st = _api_get("/status")
    rep["api_reachable"] = st is not None
    if st is None:
        issues.append("参谋 API (18091) 不可达")

    # 3. 快照新鲜度
    turn, base = _read_turn()
    rep["snapshot_source"] = os.path.basename(base) if base else None
    rep["snapshot"] = {k: turn.get(k) for k in ("scenario_name", "game_date", "game_turn")}
    sm = _save_mtime()
    snap_m = os.path.getmtime(TURN_JSON) if os.path.exists(TURN_JSON) else 0
    staleness = (sm - snap_m) if (sm and snap_m) else None
    rep["staleness_s"] = round(staleness, 1) if staleness is not None else None
    rep["snapshot_age_s"] = round(time.time() - snap_m, 1) if snap_m else None
    if not turn:
        issues.append("快照缺失或不可解析（参谋无数据可读）")
    elif staleness is not None and staleness > 180:
        issues.append(f"快照落后存档 {round(staleness)}s（参谋读的是过期数据）")

    # 4. 与游戏实际存档一致性（直接解析两份 pws，取最新日期）
    import gzip, struct, zlib, re
    actual_date, actual_mtime = None, 0.0
    for _n in ("wpae000.pws", "wpae002.pws"):
        _p = os.path.join(SAVE_DIR, _n)
        if not os.path.exists(_p):
            continue
        try:
            _raw = gzip.open(_p, "rb").read()
            _, _, _c = struct.unpack_from("<III", _raw, 0)
            _inner = zlib.decompress(_raw[12:12 + _c])
            _m = re.search(rb"Date:\s*([0-9/]+)", _inner)
            if _m:
                _d = _m.group(1).decode()
                if _d >= (actual_date or ""):
                    actual_date = _d
            actual_mtime = max(actual_mtime, os.path.getmtime(_p))
        except Exception:
            pass
    rep["actual_save_date"] = actual_date
    rep["save_age_s"] = round(time.time() - actual_mtime, 1) if actual_mtime else None

    # 4b. 对局是否处于待机/推演间歇期（存档与快照长时间未动属于正常待机，不作为服务故障）
    warnings = []
    if rep["save_age_s"] is not None and rep["save_age_s"] > 3600:
        rep["game_inactive"] = True
        warnings.append(
            f"对局待机中：存档 {round(rep['save_age_s']/3600,1)} 小时未更新（推演间歇期，推进回合即可自动激活）")
    if actual_date and turn.get("game_date") and actual_date != turn.get("game_date"):
        issues.append(
            f"★ 参谋剧本/日期与实际存档不一致：快照={turn.get('game_date')} 存档={actual_date}")

    # 5. SKB 可写
    rep["skb_writable"] = os.access(SKB_DIR, os.W_OK)
    if not rep["skb_writable"]:
        issues.append("知识库目录不可写")

    healthy = not issues
    rep["issues"] = issues
    rep["warnings"] = warnings
    rep["healthy"] = healthy

    if verbose:
        print("=== 参谋部体检报告 ===")
        for s, ok in svc.items():
            print(f"  {'✓' if ok else '✗'} {s}")
        print(f"  {'✓' if rep['api_reachable'] else '✗'} 参谋 API (18091)")
        print(f"  快照来源 : {rep['snapshot_source']}")
        print(f"  快照剧本 : {turn.get('scenario_name')}  日期 {turn.get('game_date')}  回合 {turn.get('game_turn')}")
        print(f"  实际存档 : {actual_date}   （存档年龄 {rep.get('save_age_s')} 秒）")
        print(f"  快照滞后 : {rep['staleness_s']} 秒   快照年龄 {rep['snapshot_age_s']} 秒")
        if rep.get("game_inactive"):
            print("  ⓘ 对局待机：当前处于推演间歇期；若本局已终局请执行 close-game 归档战果并复盘。")
        for w in warnings:
            print(f"  ℹ {w}")
        if healthy:
            print("  ✅ 参谋部内部服务健康，随时可以受领推演任务。")
        else:
            print("  ❌ 发现 %d 项服务异常：" % len(issues))
            for i in issues:
                print(f"     - {i}")
            print("  → 请执行： witp-cmd staff fix")
    return healthy, rep


# ─────────────────────────── 参谋修复 ───────────────────────────

def staff_fix(verbose=True):
    """修复参谋部：拉起服务 → 强制重读存档 → 复验。返回 (ok, report)。"""
    steps = []
    if verbose:
        print("=== 参谋部修复流程 ===")

    # 1. 拉起未运行的服务
    for s in SERVICES:
        if not _svc_active(s):
            _sh(f"systemctl restart {s}", timeout=60)
            time.sleep(2)
            ok = _svc_active(s)
            steps.append((f"重启 {s}", ok))
            if verbose:
                print(f"  {'✓' if ok else '✗'} 重启 {s}")

    # 2. 清理可能残留的刷新锁
    for lock in ("/tmp/witp_refresh.lock", "/tmp/witp_state_watcher.lock"):
        if os.path.exists(lock):
            # watcher 锁由其自身持有，删掉会导致双实例；只清 refresh 锁
            if "refresh" in lock:
                try:
                    os.unlink(lock)
                    steps.append((f"清理残留锁 {os.path.basename(lock)}", True))
                except OSError:
                    pass

    # 3. 强制重读存档
    res = staff_resync(verbose=verbose)
    steps.append(("强制重读存档", bool(res and res.get("ok"))))

    # 4. 复验
    healthy, rep = staff_check(verbose=False)
    steps.append(("复验体检", healthy))

    if verbose:
        print()
        if healthy:
            print("  ✅ 修复完成，参谋部已恢复健康。")
        else:
            print("  ⚠️ 修复后仍存在问题：")
            for i in rep.get("issues", []):
                print(f"     - {i}")
            print("  → 请人工介入检查，或执行 witp-cmd staff check 查看详情。")
    return healthy, {"steps": steps, "check": rep}


def staff_resync(verbose=True):
    """强制参谋部重读当前存档（绕过缓存）。"""
    if verbose:
        print("[参谋] 强制重读存档中（约 10-30s）…")
    d = _api_post("/refresh-state", timeout=300)
    if d is None:
        if verbose:
            print("  ✗ 参谋 API 不可达，无法重读。请先执行 witp-cmd staff fix")
        return {"ok": False, "error": "api unreachable"}
    if verbose:
        if d.get("ok"):
            print(f"  ✓ 已重读：{d.get('scenario')}  {d.get('date')}  第 {d.get('turn')} 回合")
        else:
            print(f"  ✗ 重读失败：{d.get('error')}")
    return d


# ─────────────────────────── 回写：因果三元组 ───────────────────────────

def _active_game_dir():
    """当前对局目录。

    ★2026-10-14 修（编号错位根因）★
      旧实现 `sorted(dirs, key=getmtime, reverse=True)[0]` 取**最新 mtime** 的
      game-* 目录。问题：新局由 `auto_start_coral_sea.py` 创建 game-049，
      但 close-game 时若 game-048 的目录恰好刚被某个写入touch 过，
      取到的就是 game-048 ⇒ 台账里同一局被记成两个编号（实测 game-048 出现两行）。
      ⇒ 改为**对局级锚点**：新局创建时写 games/CURRENT_GAME（内容=目录名），
        此后整局的 record-turn / close-game / 读档命令一律以此锚点为准，
        mtime 只作无锚点时的兜底。
    """
    anchor = os.path.join(GAMES_DIR, "_current_game")
    if os.path.exists(anchor):
        try:
            gid = open(anchor, encoding="utf-8").read().strip()
            p = os.path.join(GAMES_DIR, gid)
            if gid and os.path.isdir(p):
                return p
        except Exception:
            pass
    if not os.path.isdir(GAMES_DIR):
        return None
    dirs = [d for d in glob.glob(os.path.join(GAMES_DIR, "game-*")) if os.path.isdir(d) and not d.endswith("_archive")]
    return sorted(dirs, key=os.path.getmtime, reverse=True)[0] if dirs else None


def set_current_game(game_id, verbose=False):
    """把某局设为「当前对局」（写锚点）。新局创建后必须调用。"""
    os.makedirs(GAMES_DIR, exist_ok=True)
    gid = os.path.basename(str(game_id).rstrip("/"))
    p = os.path.join(GAMES_DIR, gid)
    if not os.path.isdir(p):
        return {"ok": False, "error": f"目录不存在: {p}"}
    with open(os.path.join(GAMES_DIR, "_current_game"), "w", encoding="utf-8") as f:
        f.write(gid + "\n")
    if verbose:
        print(f"[对局] 当前对局锚点已设为 {gid}")
    return {"ok": True, "game_id": gid, "dir": p}


def new_game(scenario="The Battle of the Coral Sea", verbose=True):
    """新建一局（编号 = 现有最大编号 + 1），创建因果日志目录并设锚点。

    ★2026-10-15 修（编号偏移：059→060、060→061）★
      实测成因：开新局时先跑 `witp-cmd new-game` 建了 game-060，紧接着
      `auto_start_coral_sea.py` 又建 game-061（它自己数目录也要新建），
      ⇒ 同一局出现两个目录、锚点指向后者、close-game 却归档到前者。
      ⇒ 两条防线：
        ① **幂等窗口**：若当前锚点指向的目录是「刚建的」（started_at 在
           IDEMPOTENT_SEC 秒内 且 尚无因果记录），直接复用它，不再新建；
        ② 编号判断与 auto_start 保持一致（同样的 max+1 规则）。
    """
    import re as _re
    os.makedirs(GAMES_DIR, exist_ok=True)
    IDEMPOTENT_SEC = 300.0

    # ① 幂等：复用刚建好、还没用过的当前对局
    try:
        anchor = os.path.join(GAMES_DIR, "_current_game")
        if os.path.exists(anchor):
            gid0 = open(anchor, encoding="utf-8").read().strip()
            p0 = os.path.join(GAMES_DIR, gid0)
            sf0 = os.path.join(p0, "summary.json")
            if gid0 and os.path.isdir(p0) and os.path.exists(sf0):
                s0 = json.load(open(sf0, encoding="utf-8"))
                import time as _t
                fresh = (_t.time() - float(s0.get("started_at") or 0)) < IDEMPOTENT_SEC
                n_causal = len(glob.glob(os.path.join(p0, "causal_log", "turn_*.json")))
                if fresh and n_causal == 0 and not s0.get("outcome"):
                    if verbose:
                        print(f"[对局] 复用刚创建的对局 {gid0}（{IDEMPOTENT_SEC:.0f}s 内、"
                              f"无因果记录、未归档）—— 不重复建局")
                    return p0
    except Exception:
        pass

    nums = []
    for d in os.listdir(GAMES_DIR):
        m = _re.match(r"game-(\d+)$", d)
        if m and os.path.isdir(os.path.join(GAMES_DIR, d)):
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    gid = "game-%03d" % nxt
    gdir = os.path.join(GAMES_DIR, gid)
    os.makedirs(os.path.join(gdir, "causal_log"), exist_ok=True)
    summary = {
        "game_id": gid,
        "scenario": scenario,
        "started_at": time.time(),
        "started_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(gdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    set_current_game(gid)
    if verbose:
        print(f"[对局] 已创建新对局 {gid} → {os.path.relpath(gdir, AGENT_DIR)}")
    return gdir


def record_turn(decision, result, orders=None, game_id=None, verbose=True):
    """
    记录本回合的因果三元组 (S, D, R)，写入 games/<game>/causal_log/turn_NN.json。
    S 自动取自当前参谋快照（客观态势），D 与 R 由前线指挥官填写。
    """
    turn, _ = _read_turn()
    gdir = os.path.join(GAMES_DIR, game_id) if game_id else _active_game_dir()
    if not gdir:
        gdir = os.path.join(GAMES_DIR, "game-001")
    cdir = os.path.join(gdir, "causal_log")
    os.makedirs(cdir, exist_ok=True)

    tnum = turn.get("game_turn") or turn.get("turn") or 0
    fp = os.path.join(cdir, f"turn_{int(tnum):02d}.json")

    record = {
        "turn": tnum,
        "date": turn.get("game_date") or turn.get("date"),
        "scenario": turn.get("scenario_name"),
        "recorded_at": time.time(),
        "recorded_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "S_situation": {
            "scenario": turn.get("scenario_name"),
            "date": turn.get("game_date") or turn.get("date"),
            "turn": tnum,
            "source": "参谋快照 state/turn.json",
        },
        "D_decision": {
            "decision": decision,
            "orders": orders or [],
        },
        "R_result": {
            "result": result,
        },
    }

    # 若该回合已有记录则合并（保留已有字段，追加本次）
    if os.path.exists(fp):
        try:
            old = json.load(open(fp, encoding="utf-8"))
            old.setdefault("D_decision", {})
            if decision:
                old["D_decision"]["decision"] = decision
            if orders:
                old["D_decision"]["orders"] = orders
            old.setdefault("R_result", {})
            if result:
                old["R_result"]["result"] = result
            old["recorded_at"] = record["recorded_at"]
            record = old
        except Exception:
            pass

    tmp = fp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, fp)

    if verbose:
        print(f"[回写] 已记录因果三元组 → {os.path.relpath(fp, AGENT_DIR)}")
        print(f"  S 态势: {record['S_situation']['scenario']} {record['S_situation']['date']} T{tnum}")
        print(f"  D 决策: {str(decision)[:120]}")
        print(f"  R 结果: {str(result)[:120]}")
    return {"ok": True, "path": fp, "turn": tnum}


# ─────────────────────────── 回写：对局战果归档 ───────────────────────────

def close_game(outcome, enemy_score=None, own_score=None, notes="", game_id=None, verbose=True):
    """归档对局战果：写 games/<game>/summary.json，并追加到全局战果台账。"""
    turn, _ = _read_turn()
    gdir = os.path.join(GAMES_DIR, game_id) if game_id else _active_game_dir()
    if not gdir:
        gdir = os.path.join(GAMES_DIR, "game-001")
    os.makedirs(gdir, exist_ok=True)

    summary = {
        "game_id": os.path.basename(gdir),
        "scenario": turn.get("scenario_name"),
        "ended_at": time.time(),
        "ended_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "final_date": turn.get("game_date") or turn.get("date"),
        "final_turn": turn.get("game_turn") or turn.get("turn"),
        "outcome": outcome,
        "enemy_score": enemy_score,
        "own_score": own_score,
        "notes": notes,
    }
    sf = os.path.join(gdir, "summary.json")
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 追加全局台账
    ledger = []
    if os.path.exists(RESULTS_LEDGER):
        try:
            ledger = json.load(open(RESULTS_LEDGER, encoding="utf-8"))
        except Exception:
            ledger = []
    ledger.append(summary)
    with open(RESULTS_LEDGER, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)

    # 统计本局因果记录条数，便于复盘
    n_turns = len(glob.glob(os.path.join(gdir, "causal_log", "turn_*.json")))

    if verbose:
        print("[归档] 对局战果已记录")
        print(f"  剧本   : {summary['scenario']}")
        print(f"  终局   : {summary['final_date']} (T{summary['final_turn']})")
        print(f"  胜负   : {outcome}")
        print(f"  比分   : 敌方 {enemy_score} : 我方 {own_score}")
        print(f"  因果记录: {n_turns} 回合")
        print(f"  → {os.path.relpath(sf, AGENT_DIR)}")
        print(f"  → 台账 {os.path.relpath(RESULTS_LEDGER, AGENT_DIR)}")
        if n_turns == 0:
            print("  ⚠️ 本局没有任何因果记录（turn_*.json）—— 复盘将无据可依！")
            print("     今后请每回合执行： witp-cmd record-turn --decision ... --result ...")
    return {"ok": True, "summary": summary, "turns_recorded": n_turns}


# ─────────────────────────── 回写：知识库 ───────────────────────────

def _count_doctrines(txt: str) -> int:
    """统计教条条数，兼容两种格式：旧 `## 教条 #N` 与合并重构后的 `### Dx.y`。"""
    if not txt:
        return 0
    legacy = txt.count("## 教条 #")
    grouped = len(re.findall(r"^### D\d+\.\d+", txt, re.M))
    return legacy + grouped


# ★SKB 定位守卫（2026-09-26 用户订正）★
#   SKB = **参谋部写作战策略**的知识库，会被注入参谋提示词、参与战略推理。
#   把操作层内容（OCR 参数、截图像素、点击通道、plumbing 根因…）写进来
#   = 往战略推理里灌技术垃圾，属定位错误（本次即因此被指挥官订正）。
#   故：默认 scope=strategy，命中操作层关键词即**拒收**，并提示改用 --scope ops；
#       scope=ops 则路由到技能库 references/ops-log.md（不注入参谋提示词）。
_OPS_KEYWORDS = (
    "OCR", "ocr", "截图", "像素", "点击", "xdotool", "VNC", "vnc", "plumbing", "PIL",
    "字号", "倍率", "裁剪", "行带", "懒加载", "NameError", "ImportError",
    "对话框", "反引号", "grep", "git ", "正则", "坐标写死", "写死", "偏移",
    "窗口偏移", "进程", "服务重启", "黑屏",
)
_OPS_LOG = ("/root/.hermes/profiles/witp/skills/wargaming/"
            "witp-ae-interface/references/ops-log.md")


def _ops_hits(text):
    return [k for k in _OPS_KEYWORDS if k in text]


def skb_add_doctrine(text, confidence=None, evidence=None, verbose=True, scope="strategy"):
    """向知识库追加一条教条，并自动 git 提交（自我迭代的落地动作）。

    scope="strategy"（默认）→ 写入 SKB（供参谋部战略推理）
    scope="ops"             → 写入技能库 references/ops-log.md（操作笔记，不进参谋提示词）
    """
    hits = _ops_hits(text)

    # ① 操作层内容 + 未显式声明 ops → 拒收（守护 SKB 的战略纯度）
    if scope != "ops" and hits:
        if verbose:
            print("[知识库] ❌ 拒收：该条目被判为**操作层内容**，SKB 只收作战策略。")
            print(f"  命中操作层关键词: {', '.join(hits[:8])}")
            print("  正确做法（任选其一）：")
            print("    · 操作笔记 → witp-cmd skb --add \"...\" --scope ops   （写入技能库，不进参谋提示词）")
            print("    · 作战策略 → 改写掉技术细节后重发（SKB 里只留可指导打法的结论）")
        return {"ok": False, "reason": "ops_content_rejected", "hits": hits}

    # ② scope=ops → 写技能库操作日志，不碰 SKB
    if scope == "ops":
        os.makedirs(os.path.dirname(_OPS_LOG), exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(_OPS_LOG, "a", encoding="utf-8") as f:
            if not os.path.exists(_OPS_LOG) or os.path.getsize(_OPS_LOG) == 0:
                f.write("# 操作层笔记（SKB 之外；供 witp-cmd/界面操作复用）\n\n")
                f.write("> 本文件**不是**战略知识库，不注入参谋提示词。战略教条请写 SKB。\n\n")
            f.write(f"## [{stamp}] {text.splitlines()[0][:70]}\n{text}\n")
            if confidence is not None:
                f.write(f"- 置信度: {confidence}\n")
            if evidence:
                f.write(f"- 证据: {evidence}\n")
            f.write("\n")
        if verbose:
            print("[操作笔记] 已写入技能库（SKB 未被触碰）")
            print(f"  路径: {_OPS_LOG}")
            print(f"  内容: {text[:120]}")
        return {"ok": True, "scope": "ops", "path": _OPS_LOG}

    os.makedirs(SKB_DIR, exist_ok=True)
    doc = os.path.join(SKB_DIR, "doctrines.md")

    # 统计现有教条编号（★2026-09-25 兼容合并重构后的 ### Dx.y 结构★）
    n = 0
    txt = ""
    if os.path.exists(doc):
        try:
            txt = open(doc, encoding="utf-8").read()
        except Exception:
            txt = ""
    n = _count_doctrines(txt) + 1
    # 新增条目统一追加到「后续新增（待归并）」小节，编号 D11.N
    SEC = "## 十一、后续新增（待归并）"
    sub = len(re.findall(r"^### D11\.", txt, re.M)) + 1

    block = ""
    if SEC not in txt:
        block += f"\n---\n\n{SEC}\n\n"
    block += f"### D11.{sub} {text.splitlines()[0][:60]}\n{text}\n"
    if confidence is not None:
        block += f"- 置信度: {confidence}\n"
    if evidence:
        block += f"- 证据: {evidence}\n"

    with open(doc, "a", encoding="utf-8") as f:
        f.write(block)

    # git 提交
    msg = f"复盘提炼：新增教条 #{n}（{datetime.now().strftime('%m-%d %H:%M')}）"
    _sh("git add -A", timeout=30)  # cwd 由下面 cwd= 指定
    rc1, _, _ = _sh(f'cd {SKB_DIR} && git add -A && git -c user.name=witp-agent -c user.email=witp@local commit -m "{msg}"',
                    timeout=60)

    if verbose:
        print(f"[知识库] 已追加教条 #{n} 并提交 Git")
        print(f"  内容: {text[:120]}")
        print(f"  {'✓' if rc1 == 0 else '⚠️ git 提交返回 ' + str(rc1)}")
    return {"ok": True, "index": n, "committed": rc1 == 0}


def skb_status(verbose=True):
    """查看知识库当前状态与提交历史。"""
    doc = os.path.join(SKB_DIR, "doctrines.md")
    n_doc = 0
    if os.path.exists(doc):
        n_doc = _count_doctrines(open(doc, encoding="utf-8").read())
    pat = os.path.join(SKB_DIR, "patterns.json")
    n_pat = 0
    if os.path.exists(pat):
        try:
            n_pat = len(json.load(open(pat, encoding="utf-8")))
        except Exception:
            pass
    rc, out, _ = _sh(f"cd {SKB_DIR} && git log --oneline --date=short --pretty='%h %ad %s'", timeout=30)
    commits = [l for l in out.splitlines() if l.strip()]
    if verbose:
        print("=== 战略知识库状态 ===")
        print(f"  教条数量 : {n_doc}")
        print(f"  模式数量 : {n_pat}")
        print(f"  提交次数 : {len(commits)}")
        for c in commits[:10]:
            print(f"    {c}")
        if len(commits) <= 1:
            print("  ⚠️ 知识库从未因复盘更新过 —— 自我迭代尚未发生！")
    return {"doctrines": n_doc, "patterns": n_pat, "commits": commits}
