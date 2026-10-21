"""
WitP Dashboard – Hermes Python plugin backend.

Provides REST endpoints under /api/plugins/witp-dashboard/ for the
WitP-AE self-iterating agent dashboard.
Includes:
- Multi-provider management (add, edit, delete, activate)
- Remote model fetching (/v1/models query)
- Single turn execution & causal logs
- Static web serving of witp-dashboard.html at root /
"""

import json
import os
import subprocess
import glob
import asyncio
import time
import urllib.request
import urllib.error

import yaml
import sys
from aiohttp import web

PROFILE_DIR = "/root/.hermes/profiles/witp"
AGENT_DIR = os.path.join(PROFILE_DIR, "witp-agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

# ---------------------------------------------------------------------------
# Data paths (profile-local)
# ---------------------------------------------------------------------------
PROFILE_DIR = "/root/.hermes/profiles/witp"
AGENT_DIR = os.path.join(PROFILE_DIR, "witp-agent")
CONFIG_PATH = os.path.join(AGENT_DIR, "config.yaml")
HERMES_CONFIG_PATH = os.path.join(PROFILE_DIR, "config.yaml")
SKB_DIR = os.path.join(AGENT_DIR, "skb")
GAMES_DIR = os.path.join(AGENT_DIR, "games")
LOGS_DIR = os.path.join(AGENT_DIR, "logs")
LOOP_STATE_FILE = os.path.join(AGENT_DIR, "loop_state.json")
ORCHESTRATOR_PY = os.path.join(AGENT_DIR, "orchestrator.py")
READER_DIR = "/root/.hermes/profiles/witp/workspace/witp-reader"
READ_SCRIPT = os.path.join(READER_DIR, "witp_read.sh")
STATE_DIR = os.path.join(READER_DIR, "state")
TURN_JSON = os.path.join(STATE_DIR, "turn.json")
SYNC_STATUS_FILE = os.path.join(STATE_DIR, "sync_status.json")
LASTGOOD_DIR = os.path.join(READER_DIR, "state_lastgood")
RESULTS_LEDGER = os.path.join(GAMES_DIR, "results.json")

# 存档枚举/定位（与参谋部核心共用同一模块）
try:
    from witp_saves import list_saves as _list_saves, resolve_save as _resolve_save
except Exception:
    def _list_saves(*a, **k):
        return []
    def _resolve_save(*a, **k):
        return None
SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
DASHBOARD_HTML = "/root/.hermes/profiles/witp/workspace/witp-dashboard.html"

PREFIX = "/api/plugins/witp-dashboard"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_yaml(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _read_text(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str, fallback=None):
    if fallback is None:
        fallback = {}
    if not os.path.isfile(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _check_port(port: int) -> bool:
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        return f":{port}" in result.stdout
    except Exception:
        return False


def _get_loop_state() -> dict:
    return _read_json(LOOP_STATE_FILE, {
        "state": "stopped",
        "started_at": None,
        "paused_at": None,
    })


def _set_loop_state(state: str, **extra) -> dict:
    data = _get_loop_state()
    data["state"] = state
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if state == "running":
        data["started_at"] = now
        data["paused_at"] = None
    elif state == "paused":
        data["paused_at"] = now
    elif state == "stopped":
        data["started_at"] = None
        data["paused_at"] = None
    data.update(extra)
    _write_json(LOOP_STATE_FILE, data)
    return data


def _snapshot_backup() -> None:
    """读层会清空 state/，先备份良好快照以便空窗期/失败时回滚。"""
    try:
        if not os.path.exists(os.path.join(STATE_DIR, "turn.json")):
            return
        os.makedirs(LASTGOOD_DIR, exist_ok=True)
        subprocess.run(["rsync", "-a", "--delete", STATE_DIR + "/", LASTGOOD_DIR + "/"],
                       capture_output=True, timeout=60)
    except Exception:
        pass


def _snapshot_restore() -> None:
    try:
        if not os.path.isdir(LASTGOOD_DIR):
            return
        os.makedirs(STATE_DIR, exist_ok=True)
        subprocess.run(["rsync", "-a", LASTGOOD_DIR + "/", STATE_DIR + "/"],
                       capture_output=True, timeout=60)
    except Exception:
        pass


def _read_turn_with_fallback() -> dict:
    """读取 turn.json；若读层正在重建 state/（空窗期），回退到上次良好快照。"""
    for base in (STATE_DIR, LASTGOOD_DIR):
        fp = os.path.join(base, "turn.json")
        if os.path.exists(fp):
            d = _read_json(fp, {})
            if d.get("game_date") or d.get("date"):
                return d
    return {}


def _data_freshness() -> dict:
    """返回快照与存档的时间戳对比，用于判断看板数据是否新鲜。"""
    import time as _t
    save_m = 0.0
    for f in ("wpae002.pws", "wpae000.pws"):
        fp = os.path.join(SAVE_DIR, f)
        if os.path.exists(fp):
            try:
                save_m = max(save_m, os.path.getmtime(fp))
            except OSError:
                pass
    snap_m = 0.0
    if os.path.exists(TURN_JSON):
        try:
            snap_m = os.path.getmtime(TURN_JSON)
        except OSError:
            pass
    sync = _read_json(SYNC_STATUS_FILE, {})
    return {
        "snapshot_mtime": snap_m,
        "save_mtime": save_m,
        "staleness_s": round(save_m - snap_m, 1) if (save_m and snap_m) else None,
        "snapshot_age_s": round(_t.time() - snap_m, 1) if snap_m else None,
        "last_scrape_ok": sync.get("last_scrape_ok"),
        "last_scrape_at": sync.get("last_scrape_at"),
        "watcher_heartbeat_at": sync.get("watcher_heartbeat_at"),
        "watcher_started_at": sync.get("watcher_started_at"),
        "syncing": sync.get("syncing", False),
    }


def _find_active_game_dir() -> str | None:
    if not os.path.isdir(GAMES_DIR):
        return None
    dirs = sorted(
        [d for d in glob.glob(os.path.join(GAMES_DIR, "game-*")) if os.path.isdir(d) and not d.endswith("_archive")],
        key=os.path.getmtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def _sync_providers_pool() -> list:
    """
    Ensure config.yaml has a populated providers_pool using Hermes profile config.
    """
    cfg = _read_yaml(CONFIG_PATH)
    pool = cfg.get("providers_pool", [])
    
    # If pool is empty, import from Hermes profile config.yaml
    if not pool and os.path.exists(HERMES_CONFIG_PATH):
        hcfg = _read_yaml(HERMES_CONFIG_PATH)
        for cp in hcfg.get("custom_providers", []):
            name = cp.get("name") or cp.get("base_url")
            m_list = list(cp.get("models", {}).keys()) if isinstance(cp.get("models"), dict) else cp.get("models", [])
            pool.append({
                "id": cp.get("name", name.lower().replace(" ", "_")),
                "name": name,
                "base_url": cp.get("base_url", ""),
                "api_key": cp.get("api_key", ""),
                "models": m_list
            })
        cfg["providers_pool"] = pool
        _write_yaml(CONFIG_PATH, cfg)
        
    return pool


# ---------------------------------------------------------------------------
# Middleware: CORS & Preflight
# ---------------------------------------------------------------------------

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response


# ===================================================================
# Route handlers
# ===================================================================

# ---- Root Dashboard Serving ------------------------------------------

async def handle_root(request: web.Request) -> web.Response:
    """Serve the complete dashboard HTML at root /"""
    if os.path.isfile(DASHBOARD_HTML):
        with open(DASHBOARD_HTML, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="Dashboard HTML not found at " + DASHBOARD_HTML, status=404)


# ---- Multi-Provider Endpoints ----------------------------------------

async def get_providers(request: web.Request) -> web.Response:
    """GET /providers → list all available providers & active model info."""
    pool = _sync_providers_pool()
    cfg = _read_yaml(CONFIG_PATH)
    strat = cfg.get("strategy_model", {})
    return web.json_response({
        "active_provider_id": strat.get("provider_id", "gg"),
        "active_model": strat.get("model", "gemini-2.5-pro"),
        "active_base_url": strat.get("base_url", ""),
        "providers": pool
    })


async def post_providers_save(request: web.Request) -> web.Response:
    """POST /providers/save → add or update a provider in the pool."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    pid = body.get("id") or str(int(time.time()))
    name = body.get("name", "Custom Provider")
    base_url = body.get("base_url", "").strip().rstrip("/")
    api_key = body.get("api_key", "").strip()
    models = body.get("models", [])

    if not base_url:
        return web.json_response({"error": "base_url is required"}, status=400)

    cfg = _read_yaml(CONFIG_PATH)
    pool = cfg.get("providers_pool", [])
    
    # Check if exists
    found = False
    for p in pool:
        if p.get("id") == pid or p.get("name") == name:
            p["name"] = name
            p["base_url"] = base_url
            if api_key:
                p["api_key"] = api_key
            if models:
                p["models"] = models
            found = True
            break
            
    if not found:
        pool.append({
            "id": pid,
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "models": models
        })
        
    cfg["providers_pool"] = pool
    _write_yaml(CONFIG_PATH, cfg)
    return web.json_response({"ok": True, "providers": pool})


async def post_providers_delete(request: web.Request) -> web.Response:
    """POST /providers/delete → remove a provider from the pool."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
        
    pid = body.get("id")
    cfg = _read_yaml(CONFIG_PATH)
    pool = [p for p in cfg.get("providers_pool", []) if p.get("id") != pid]
    cfg["providers_pool"] = pool
    _write_yaml(CONFIG_PATH, cfg)
    return web.json_response({"ok": True, "providers": pool})


async def post_providers_activate(request: web.Request) -> web.Response:
    """POST /providers/activate → switch the active provider & model for strategy."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    pid = body.get("provider_id")
    model = body.get("model")
    
    cfg = _read_yaml(CONFIG_PATH)
    pool = cfg.get("providers_pool", [])
    
    selected_p = None
    for p in pool:
        if p.get("id") == pid:
            selected_p = p
            break
            
    if not selected_p:
        return web.json_response({"error": f"Provider {pid} not found in pool"}, status=404)

    if not model and selected_p.get("models"):
        model = selected_p["models"][0]

    strat = cfg.get("strategy_model", {})
    strat["provider_id"] = pid
    strat["provider_name"] = selected_p.get("name")
    strat["base_url"] = selected_p.get("base_url")
    strat["api_key"] = selected_p.get("api_key")
    strat["model"] = model
    cfg["strategy_model"] = strat
    
    _write_yaml(CONFIG_PATH, cfg)
    return web.json_response({"ok": True, "active": strat})


# ---------------------------------------------------------------------------
# Models & Fallbacks API (司令可视化选择与设置主模型/备用链)
# ---------------------------------------------------------------------------

async def get_models_config(request: web.Request) -> web.Response:
    """GET /models → 获取当前主模型、备用链配置以及全部模型池清单。"""
    try:
        from witp_models import load_config
        cfg = load_config()
        sm = cfg.get("strategy_model", {})
        pool = cfg.get("providers_pool", [])
        return web.json_response({
            "ok": True,
            "primary": {
                "model": sm.get("model", ""),
                "provider_id": sm.get("provider_id", ""),
                "provider_name": sm.get("provider_name", sm.get("provider_id", "")),
                "base_url": sm.get("base_url", "")
            },
            "fallbacks": sm.get("fallbacks", []),
            "providers_pool": pool
        })
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def post_models_save(request: web.Request) -> web.Response:
    """POST /models/save → 司令在网页端保存主模型与备用链配置。"""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    primary = body.get("primary")
    if not primary:
        return web.json_response({"ok": False, "error": "缺少主模型 (primary)"}, status=400)

    fallbacks = body.get("fallbacks", [])
    if isinstance(fallbacks, str):
        fallbacks = [f.strip() for f in fallbacks.split(",") if f.strip()]

    primary_provider = body.get("primary_provider")

    try:
        from witp_models import set_models
        res = set_models(primary, fallbacks=fallbacks, primary_provider=primary_provider)
        return web.json_response(res)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def post_models_test(request: web.Request) -> web.Response:
    """POST /models/test → 网页端一键探测当前主备模型连通性与耗时。"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        from witp_models import load_config, resolve_model_spec, ping_model
        cfg = load_config()
        targets = body.get("models")
        results = []

        if targets and isinstance(targets, list):
            for m in targets:
                spec = resolve_model_spec(str(m), cfg)
                if spec:
                    ok, dur, desc = ping_model(spec, timeout=12)
                    results.append({"model": spec["model"], "provider": spec["provider_id"], "ok": ok, "latency_s": dur, "msg": desc})
                else:
                    results.append({"model": str(m), "ok": False, "latency_s": 0, "msg": "未在模型池找到"})
        else:
            sm = cfg.get("strategy_model", {})
            if sm.get("model"):
                ok, dur, desc = ping_model(sm, timeout=12)
                results.append({"role": "primary", "model": sm["model"], "provider": sm.get("provider_id", ""), "ok": ok, "latency_s": dur, "msg": desc})
            for idx, fb in enumerate(sm.get("fallbacks", []), 1):
                ok, dur, desc = ping_model(fb, timeout=12)
                results.append({"role": f"fallback_{idx}", "model": fb.get("model", ""), "provider": fb.get("provider_id", ""), "ok": ok, "latency_s": dur, "msg": desc})

        return web.json_response({"ok": True, "results": results})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def _fetch_one_provider(session, p):
    base_url = p.get("base_url", "").strip().rstrip("/")
    api_key = p.get("api_key", "").strip()
    if not base_url:
        return False, p.get("id"), [], "未配置 base_url"
    url = f"{base_url}/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        import aiohttp
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                data = await resp.json()
                raw_models = data.get("data", [])
                model_ids = []
                for m in raw_models:
                    if isinstance(m, dict) and "id" in m:
                        model_ids.append(m["id"])
                    elif isinstance(m, str):
                        model_ids.append(m)
                return True, p.get("id"), sorted(model_ids), None
            else:
                err = await resp.text()
                return False, p.get("id"), [], f"HTTP {resp.status}: {err[:120]}"
    except Exception as e:
        return False, p.get("id"), [], str(e)


async def post_fetch_models(request: web.Request) -> web.Response:
    """POST /providers/fetch-models → 拉取单个接入点或全部接入点的模型列表。"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    base_url = body.get("base_url", "").strip().rstrip("/")
    api_key = body.get("api_key", "").strip()
    pid = body.get("provider_id")

    cfg = _read_yaml(CONFIG_PATH)
    import aiohttp

    # 一键拉取全部接入点模型
    if pid == "all" or (not pid and not base_url):
        pool = cfg.get("providers_pool", [])
        total_found = 0
        updated = []
        errors = []
        async with aiohttp.ClientSession() as session:
            tasks = [_fetch_one_provider(session, p) for p in pool]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, tuple):
                    ok, p_id, m_list, err = res
                    if ok and m_list:
                        for p in pool:
                            if p.get("id") == p_id:
                                p["models"] = m_list
                                total_found += len(m_list)
                                updated.append({"provider": p_id, "count": len(m_list)})
                                break
                    elif err:
                        errors.append({"provider": p_id, "error": err})
        _write_yaml(CONFIG_PATH, cfg)
        return web.json_response({
            "ok": True,
            "total_models": total_found,
            "updated": updated,
            "errors": errors,
            "count": total_found
        })

    # 拉取指定单接入点
    if pid and (not base_url or not api_key):
        for p in cfg.get("providers_pool", []):
            if p.get("id") == pid:
                base_url = p.get("base_url", "").strip().rstrip("/")
                api_key = p.get("api_key", "").strip()
                break

    if not base_url:
        return web.json_response({"ok": False, "error": f"找不到接入点 {pid} 的端点配置"}, status=400)

    url = f"{base_url}/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                elapsed_ms = int((time.time() - t0) * 1000)
                if resp.status == 200:
                    data = await resp.json()
                    raw_models = data.get("data", [])
                    model_ids = []
                    for m in raw_models:
                        if isinstance(m, dict) and "id" in m:
                            model_ids.append(m["id"])
                        elif isinstance(m, str):
                            model_ids.append(m)

                    if pid:
                        for p in cfg.get("providers_pool", []):
                            if p.get("id") == pid:
                                p["models"] = sorted(model_ids)
                                _write_yaml(CONFIG_PATH, cfg)
                                break

                    return web.json_response({
                        "ok": True,
                        "count": len(model_ids),
                        "latency_ms": elapsed_ms,
                        "models": sorted(model_ids)
                    })
                else:
                    err_txt = await resp.text()
                    return web.json_response({
                        "ok": False,
                        "status": resp.status,
                        "latency_ms": elapsed_ms,
                        "error": f"HTTP {resp.status}: {err_txt[:200]}"
                    })
    except asyncio.TimeoutError:
        return web.json_response({"ok": False, "error": "请求超时 (15s)"})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)})


# ---- Config (Backward Compatible) -------------------------------------

async def get_config(request: web.Request) -> web.Response:
    data = _read_yaml(CONFIG_PATH)
    return web.json_response(data)


async def post_config(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    
    current = _read_yaml(CONFIG_PATH)
    for k, v in body.items():
        if isinstance(v, dict) and isinstance(current.get(k), dict):
            current[k].update(v)
        else:
            current[k] = v
            
    _write_yaml(CONFIG_PATH, current)
    return web.json_response({"ok": True, "config": current})


async def post_config_test(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}

    config = _read_yaml(CONFIG_PATH)
    strategy = config.get("strategy_model", {})

    base_url = (body.get("base_url") or strategy.get("base_url", "")).strip().rstrip("/")
    api_key = (body.get("api_key") or strategy.get("api_key", "")).strip()
    model = (body.get("model") or strategy.get("model", "")).strip()

    if not base_url or not api_key or not model:
        return web.json_response({
            "ok": False,
            "error": "base_url, api_key, and model must be specified",
        }, status=400)

    import aiohttp
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": "ping"}],
    }
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                elapsed_ms = int((time.time() - t0) * 1000)
                text = await resp.text()
                if resp.status < 300:
                    return web.json_response({
                        "ok": True,
                        "status": resp.status,
                        "latency_ms": elapsed_ms,
                        "response": text[:300]
                    })
                else:
                    return web.json_response({
                        "ok": False,
                        "status": resp.status,
                        "latency_ms": elapsed_ms,
                        "error": text[:400]
                    })
    except asyncio.TimeoutError:
        return web.json_response({"ok": False, "error": "Request timed out (30s)"})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)})


# ---- Status -----------------------------------------------------------

async def get_status(request: web.Request) -> web.Response:
    config = _read_yaml(CONFIG_PATH)
    kev_port = config.get("kev_server", {}).get("port", 18090)
    vnc_display = config.get("game", {}).get("vnc_display", ":98")
    vnc_port = config.get("game", {}).get("vnc_port", 5902)

    kev_up = _check_port(kev_port)
    game_up = _check_port(vnc_port)
    loop = _get_loop_state()

    t_data = _read_turn_with_fallback()

    turn_info = {
        "turn": t_data.get("game_turn") or t_data.get("turn") or 1,
        "date": t_data.get("game_date") or t_data.get("date") or "未知",
        "scenario": t_data.get("scenario_name") or "未知剧本",
        "side": "Allied",
        "game_dir": os.path.basename(_find_active_game_dir() or "game-001")
    }

    return web.json_response({
        "kev_server": {"port": kev_port, "up": kev_up},
        "game": {"vnc_display": vnc_display, "vnc_port": vnc_port, "up": game_up},
        "loop": loop,
        "turn": turn_info,
        "freshness": _data_freshness(),
    })
async def post_run_turn(request: web.Request) -> web.Response:
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        advance = body.get("advance_turn", False)
        cmd = ["python3", ORCHESTRATOR_PY]
        if advance:
            cmd.append("--advance")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=AGENT_DIR
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")
        
        causal_files = sorted(glob.glob(os.path.join(GAMES_DIR, "*", "causal_log", "*.json")))
        latest_causal = _read_json(causal_files[-1]) if causal_files else None
        
        return web.json_response({
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": out_text,
            "error": err_text,
            "latest_log": latest_causal
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---- SKB (Strategic Knowledge Base) -----------------------------------

async def get_skb(request: web.Request) -> web.Response:
    doctrines = _read_text(os.path.join(SKB_DIR, "doctrines.md"))
    patterns = _read_json(os.path.join(SKB_DIR, "patterns.json"), [])
    eval_weights = _read_json(os.path.join(SKB_DIR, "eval_weights.json"), {})
    return web.json_response({
        "doctrines": doctrines,
        "patterns": patterns,
        "eval_weights": eval_weights,
    })


async def post_skb_doctrine(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        text = body.get("content", "")
    except Exception:
        text = await request.text()
        
    os.makedirs(SKB_DIR, exist_ok=True)
    path = os.path.join(SKB_DIR, "doctrines.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        
    try:
        subprocess.run(["git", "commit", "-am", "SKB updated via dashboard"], cwd=SKB_DIR, check=False)
    except Exception:
        pass
        
    return web.json_response({"ok": True, "bytes": len(text.encode("utf-8"))})


# ---- Proposals & Strategy Recommendations -----------------------------

_proposal_generating = False

async def get_proposal_latest(request: web.Request) -> web.Response:
    """GET /proposal/latest → 返回当前对局最新生成的《作战方案建议书》。若发现方案属于上一回合，自动现场在后台为当前回合重新生成。"""
    global _proposal_generating
    import asyncio as _a
    game_dir = _find_active_game_dir()
    proposal = None
    t_info = _read_turn_with_fallback()
    current_turn = t_info.get("game_turn") or t_info.get("turn")

    if game_dir:
        causal_dir = os.path.join(game_dir, "causal_log")
        prop_files = sorted(glob.glob(os.path.join(causal_dir, "proposal_turn_*.json")), key=os.path.getmtime)
        if prop_files:
            proposal = _read_json(prop_files[-1])

    # 如果没有建议书，或者建议书属于过往旧回合，自动触发后台为当前最新回合生成
    need_generate = False
    if not proposal:
        need_generate = True
    elif current_turn and proposal.get("turn") and proposal.get("turn") < current_turn:
        need_generate = True

    if need_generate and not _proposal_generating:
        _proposal_generating = True
        gid = os.path.basename(game_dir) if game_dir else "game-008"
        async def _bg_gen():
            global _proposal_generating
            try:
                loop = _a.get_running_loop()
                from witp_staff import generate_staff_proposal
                await loop.run_in_executor(None, lambda: generate_staff_proposal(run_scraper=False, game_id=gid))
            except Exception as e:
                print(f"[get_proposal_latest] 后台生成建议书失败: {e}", file=sys.stderr)
            finally:
                _proposal_generating = False
        _a.create_task(_bg_gen())

    return web.json_response({
        "ok": bool(proposal),
        "proposal": proposal,
        "current_turn": current_turn,
        "is_generating": _proposal_generating,
        "is_fresh": bool(proposal and current_turn and proposal.get("turn") == current_turn)
    })


async def post_proposal_generate(request: web.Request) -> web.Response:
    """POST /proposal/generate → 现场调用参谋部大模型生成当前最新建议书。"""
    try:
        from witp_staff import generate_staff_proposal
        game_dir = _find_active_game_dir()
        gid = os.path.basename(game_dir) if game_dir else "game-007"
        proposal = generate_staff_proposal(run_scraper=True, game_id=gid)
        return web.json_response({"ok": True, "proposal": proposal})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


# ---- Causal Logs ------------------------------------------------------

async def get_causal_logs(request: web.Request) -> web.Response:
    """GET /causal-logs → 读取当前对局归档的因果三元组（仅包含 turn_*.json）。"""
    logs = []
    game_dir = _find_active_game_dir()
    if game_dir:
        pattern = os.path.join(game_dir, "causal_log", "turn_*.json")
        for f in sorted(glob.glob(pattern)):
            d = _read_json(f)
            if d:
                logs.append(d)
    return web.json_response({"logs": logs, "total": len(logs)})


# ---- Belief map -------------------------------------------------------

async def get_belief(request: web.Request) -> web.Response:
    from lib.belief_update import DEFAULT_REGIONS
    game_dir = _find_active_game_dir()
    belief = {}
    if game_dir:
        belief = _read_json(os.path.join(game_dir, "belief.json"), {})
    if not belief:
        belief = {"regions": DEFAULT_REGIONS}
    return web.json_response(belief)


# ---- Orders -----------------------------------------------------------

async def get_orders(request: web.Request) -> web.Response:
    causal_files = sorted(glob.glob(os.path.join(GAMES_DIR, "*", "causal_log", "*.json")))
    if causal_files:
        latest = _read_json(causal_files[-1], {})
        orders = latest.get("D_decision", {}).get("orders", [])
        return web.json_response({"orders": orders, "turn": latest.get("turn")})
    return web.json_response({"orders": [], "turn": 0})


# ---- Games ------------------------------------------------------------

async def get_games(request: web.Request) -> web.Response:
    if not os.path.isdir(GAMES_DIR):
        return web.json_response({"games": []})
    games = []
    for entry in sorted(os.listdir(GAMES_DIR)):
        d = os.path.join(GAMES_DIR, entry)
        if not os.path.isdir(d):
            continue
        summary = _read_json(os.path.join(d, "summary.json"), {})
        games.append({
            "name": entry,
            "path": d,
            "summary": summary,
            "has_belief": os.path.isfile(os.path.join(d, "belief.json")),
            "has_orders": os.path.isfile(os.path.join(d, "orders.json")),
        })
    return web.json_response({"games": games})


# ---- Loop control -----------------------------------------------------

async def post_loop_start(request: web.Request) -> web.Response:
    state = _set_loop_state("running")
    return web.json_response({"ok": True, "loop": state})


async def post_loop_pause(request: web.Request) -> web.Response:
    state = _set_loop_state("paused")
    return web.json_response({"ok": True, "loop": state})


async def post_loop_stop(request: web.Request) -> web.Response:
    state = _set_loop_state("stopped")
    return web.json_response({"ok": True, "loop": state})


# ===================================================================
# Plugin entry point
# ===================================================================


AUTO_START_PY = os.path.join(AGENT_DIR, "auto_start_coral_sea.py")

async def post_restart_scenario(request: web.Request) -> web.Response:
    """POST /game/restart-scenario → automatically launch Coral Sea scenario."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", AUTO_START_PY,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=AGENT_DIR
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")
        return web.json_response({
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": out_text,
            "error": err_text
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

# ---- Refresh state (触发读层重读存档) --------------------------------

async def post_refresh_state(request: web.Request) -> web.Response:
    """POST /refresh-state → 重跑读层脚本，刷新态势快照。"""
    import asyncio as _a
    lock = "/tmp/witp_refresh.lock"
    STALE_AFTER = 600  # 秒：超过此年龄的锁视为残留（进程被中断时 finally 可能未执行）

    # 残留锁自愈：锁龄过大则强制接管
    if os.path.exists(lock):
        try:
            age = time.time() - os.path.getmtime(lock)
        except OSError:
            age = 0
        if age > STALE_AFTER:
            try:
                os.unlink(lock)
                print(f"[refresh] 清理残留刷新锁（已 {int(age)}s）")
            except OSError:
                pass

    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        return web.json_response(
            {"ok": False, "error": "已有刷新任务在执行，请稍候；若长期如此请执行 witp-cmd staff --fix"},
            status=409)
    # 解析请求体：可指定要解析的存档
    save_spec = None
    try:
        body = await request.json()
        save_spec = (body or {}).get("save")
    except Exception:
        pass

    cmd = ["bash", READ_SCRIPT]
    resolved = None
    if save_spec:
        resolved = _resolve_save(str(save_spec))
        if not resolved:
            return web.json_response(
                {"ok": False, "error": f"无法解析指定存档：{save_spec}（可用存档见 GET /saves）"},
                status=400)
        cmd.append(resolved)

    _snapshot_backup()
    try:
        proc = await _a.create_subprocess_exec(
            *cmd,
            cwd=READER_DIR,
            stdout=_a.subprocess.PIPE,
            stderr=_a.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        ok = proc.returncode == 0
        t_data = _read_turn_with_fallback()
        if ok and not t_data:
            _snapshot_restore()
            ok = False
            err = b"scrape produced no valid turn.json; rolled back"
        if ok:
            try:
                staff_py = os.path.join(AGENT_DIR, "witp_staff.py")
                import subprocess as _sp
                _sp.Popen(["python3", staff_py, "brief", "--save", "000"],
                          stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            except Exception:
                pass
        return web.json_response({
            "ok": ok,
            "exit_code": proc.returncode,
            "turn": t_data.get("game_turn") or t_data.get("turn"),
            "date": t_data.get("game_date") or t_data.get("date"),
            "scenario": t_data.get("scenario_name"),
            "data_source_save": (os.path.basename(resolved) if resolved else "自动选取（最新 .pws）"),
            "freshness": _data_freshness(),
            "error": None if ok else (err or b"").decode("utf-8", "replace")[-400:],
        })
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


# ---- Results ledger (对局战果台账) ------------------------------------

async def get_results(request: web.Request) -> web.Response:
    """GET /results → 读取真实对局战果台账 + 各局因果记录条数。"""
    ledger = _read_json(RESULTS_LEDGER, [])
    if not isinstance(ledger, list):
        ledger = []
    enriched = []
    for g in ledger:
        gid = g.get("game_id")
        n_turns = 0
        if gid:
            n_turns = len(glob.glob(os.path.join(GAMES_DIR, gid, "causal_log", "turn_*.json")))
        item = dict(g)
        item["turns_recorded"] = n_turns
        enriched.append(item)
    return web.json_response({"results": enriched, "total": len(enriched)})


# ---- Saves enumeration (存档枚举) -------------------------------------

async def get_saves(request: web.Request) -> web.Response:
    """GET /saves → 枚举可用存档（槽位/时间/日期），供前线指定要解析的存档。"""
    saves = _list_saves()
    return web.json_response({"saves": saves, "total": len(saves)})


def setup(app: web.Application) -> None:
    app.router.add_get("/", handle_root)
    app.router.add_get("/index.html", handle_root)

    app.router.add_get(f"{PREFIX}/providers", get_providers)
    app.router.add_post(f"{PREFIX}/providers/save", post_providers_save)
    app.router.add_post(f"{PREFIX}/providers/delete", post_providers_delete)
    app.router.add_post(f"{PREFIX}/providers/activate", post_providers_activate)
    app.router.add_post(f"{PREFIX}/providers/fetch-models", post_fetch_models)

    app.router.add_get(f"{PREFIX}/models", get_models_config)
    app.router.add_post(f"{PREFIX}/models/save", post_models_save)
    app.router.add_post(f"{PREFIX}/models/test", post_models_test)

    app.router.add_get(f"{PREFIX}/config", get_config)
    app.router.add_post(f"{PREFIX}/config", post_config)
    app.router.add_post(f"{PREFIX}/config/test", post_config_test)

    app.router.add_get(f"{PREFIX}/proposal/latest", get_proposal_latest)
    app.router.add_post(f"{PREFIX}/proposal/generate", post_proposal_generate)

    app.router.add_get(f"{PREFIX}/status", get_status)
    app.router.add_post(f"{PREFIX}/run-turn", post_run_turn)
    app.router.add_post(f"{PREFIX}/refresh-state", post_refresh_state)
    app.router.add_post(f"{PREFIX}/game/restart-scenario", post_restart_scenario)

    app.router.add_get(f"{PREFIX}/skb", get_skb)
    app.router.add_post(f"{PREFIX}/skb/doctrine", post_skb_doctrine)
    app.router.add_get(f"{PREFIX}/causal-logs", get_causal_logs)

    app.router.add_get(f"{PREFIX}/belief", get_belief)
    app.router.add_get(f"{PREFIX}/orders", get_orders)
    app.router.add_get(f"{PREFIX}/games", get_games)
    app.router.add_get(f"{PREFIX}/results", get_results)
    app.router.add_get(f"{PREFIX}/saves", get_saves)

    app.router.add_post(f"{PREFIX}/loop/start", post_loop_start)
    app.router.add_post(f"{PREFIX}/loop/pause", post_loop_pause)
    app.router.add_post(f"{PREFIX}/loop/stop", post_loop_stop)


def make_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    setup(app)
    return app


if __name__ == "__main__":
    app = make_app()
    print(f"Starting standalone WitP Dashboard API on port 18091 (prefix: {PREFIX})...")
    web.run_app(app, host="0.0.0.0", port=18091)
