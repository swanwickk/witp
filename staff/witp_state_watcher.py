#!/usr/bin/env python3
"""
WitP-AE 存档变更监听器 (State Watcher)
职责：监视游戏 SAVE 目录的存档变动，自动重跑读层 witp_read.sh，
      把最新的真实态势快照写进 state/，供战略推演看板实时读取。

背景：看板原先只读缓存快照，游戏推进后不会自动更新，导致看板长期显示过期数据。
本守护进程补上这条"数据管道"。

设计要点：
- 轮询 wpae000.pws / wpae002.pws 的 mtime，变更即触发
- 文件锁防重入（读层会拉起 Wine，耗时数十秒）
- 去抖：存档写入后等待若干秒再解析，避免读到写一半的文件
- 每次同步记录状态到 state/sync_status.json，供看板展示新鲜度
"""
import os
import sys
import json
import time
import fcntl
import subprocess
from datetime import datetime

READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
READ_SCRIPT = os.path.join(READER_DIR, "witp_read.sh")
STATE_DIR = os.path.join(READER_DIR, "state")
SYNC_STATUS = os.path.join(STATE_DIR, "sync_status.json")
LASTGOOD_DIR = os.path.join(READER_DIR, "state_lastgood")
LOCK_FILE = "/tmp/witp_state_watcher.lock"

SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
WATCH_FILES = ["wpae002.pws", "wpae000.pws"]

POLL_INTERVAL = 20      # 轮询间隔（秒）
DEBOUNCE = 8            # 存档变动后等待（秒）再解析
SCRAPE_TIMEOUT = 300    # 读层超时（秒）


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def watched_mtimes() -> dict:
    out = {}
    for f in WATCH_FILES:
        p = os.path.join(SAVE_DIR, f)
        try:
            out[f] = os.path.getmtime(p)
        except OSError:
            out[f] = 0
    return out


def write_sync_status(**kw) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    data = {}
    if os.path.exists(SYNC_STATUS):
        try:
            with open(SYNC_STATUS, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    data.update(kw)
    data["watcher_updated_at"] = time.time()
    tmp = SYNC_STATUS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, SYNC_STATUS)


def backup_state() -> None:
    """把当前良好快照备份到 state_lastgood，供同步空窗期兜底。"""
    try:
        if not os.path.isdir(STATE_DIR):
            return
        if not os.path.exists(os.path.join(STATE_DIR, "turn.json")):
            return
        os.makedirs(LASTGOOD_DIR, exist_ok=True)
        subprocess.run(
            ["rsync", "-a", "--delete", STATE_DIR + "/", LASTGOOD_DIR + "/"],
            capture_output=True, timeout=60,
        )
        log("已备份良好快照 → state_lastgood")
    except Exception as exc:
        log(f"备份快照失败（不影响主流程）: {exc}")


def restore_state() -> bool:
    """读层失败/产出不完整时，用上次良好快照恢复，避免看板出现'未知'。"""
    try:
        if not os.path.isdir(LASTGOOD_DIR):
            return False
        os.makedirs(STATE_DIR, exist_ok=True)
        subprocess.run(
            ["rsync", "-a", LASTGOOD_DIR + "/", STATE_DIR + "/"],
            capture_output=True, timeout=60,
        )
        log("已用上次良好快照恢复 state/")
        return True
    except Exception as exc:
        log(f"恢复快照失败: {exc}")
        return False


def state_is_valid() -> bool:
    """校验读层产出是否完整（turn.json 存在且可解析）。"""
    tj = os.path.join(STATE_DIR, "turn.json")
    if not os.path.exists(tj):
        return False
    try:
        with open(tj, encoding="utf-8") as fh:
            d = json.load(fh)
        return bool(d.get("game_date") or d.get("date"))
    except Exception:
        return False


def run_scraper() -> bool:
    """执行读层脚本，刷新 state/ 快照。"""
    log("开始重跑读层 witp_read.sh …")
    write_sync_status(syncing=True)
    backup_state()
    t0 = time.time()
    try:
        proc = subprocess.run(
            ["bash", READ_SCRIPT],
            cwd=READER_DIR,
            capture_output=True,
            text=True,
            timeout=SCRAPE_TIMEOUT,
        )
        ok = proc.returncode == 0
        dur = round(time.time() - t0, 1)
        if ok and not state_is_valid():
            log("读层返回成功但产出不完整，回滚到上次良好快照")
            restore_state()
            ok = False
        if ok:
            log(f"读层完成，耗时 {dur}s")
        else:
            tail = (proc.stderr or "")[-400:]
            log(f"读层失败(rc={proc.returncode}) 耗时 {dur}s :: {tail}")
        write_sync_status(
            syncing=False,
            last_scrape_ok=ok,
            last_scrape_at=time.time(),
            last_scrape_duration_s=dur,
            last_scrape_error=None if ok else (proc.stderr or "")[-400:],
        )
        return ok
    except subprocess.TimeoutExpired:
        log(f"读层超时(>{SCRAPE_TIMEOUT}s)")
        write_sync_status(last_scrape_ok=False, last_scrape_at=time.time(),
                          last_scrape_error=f"timeout >{SCRAPE_TIMEOUT}s")
        return False
    except Exception as exc:
        log(f"读层异常: {exc}")
        write_sync_status(last_scrape_ok=False, last_scrape_at=time.time(),
                          last_scrape_error=str(exc))
        return False


def trigger_staff_proposal_async() -> None:
    """异步触发参谋大模型生成最新回合建议书，确保前线与看板实时拿到推演方案。"""
    try:
        staff_script = "/root/.hermes/profiles/witp/witp-agent/witp_staff.py"
        subprocess.Popen(
            ["python3", staff_script, "brief", "--save", "000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log("已异步触发参谋大模型生成最新作战方案建议书")
    except Exception as exc:
        log(f"触发方案生成异常: {exc}")


def main() -> None:
    # 单实例锁
    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("已有监听器实例在运行，退出。")
        return

    log(f"存档监听器启动，监视 {SAVE_DIR}")
    write_sync_status(watcher_started_at=time.time())

    last = watched_mtimes()
    log(f"初始基线: {last}")

    # 启动时若快照缺失或明显过期，先同步一次
    turn_json = os.path.join(STATE_DIR, "turn.json")
    need_initial = not os.path.exists(turn_json)
    if not need_initial:
        snap_m = os.path.getmtime(turn_json)
        save_m = max(last.values()) if last else 0
        if save_m > snap_m + 60:
            need_initial = True
    if need_initial:
        log("快照缺失或落后于存档，执行首次同步。")
        if run_scraper():
            trigger_staff_proposal_async()

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            cur = watched_mtimes()
            changed = any(cur[k] != last.get(k) for k in cur)
            if changed:
                log(f"检测到存档变动: {cur}")
                time.sleep(DEBOUNCE)          # 去抖，等写入完成
                cur = watched_mtimes()
                if run_scraper():
                    trigger_staff_proposal_async()
                last = cur
            else:
                write_sync_status(watcher_heartbeat_at=time.time())
        except Exception as exc:
            log(f"监听循环异常: {exc}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
