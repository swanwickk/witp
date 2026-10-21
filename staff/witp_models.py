#!/usr/bin/env python3
"""
WitP-AE 参谋模型管理与智能路由模块 (Model Orchestration & Fallback Engine)
允许指挥官：
1. 查看可用模型池、当前主模型与备用链；
2. 动态指定主模型与 Fallback 链（持久化至 config.yaml）；
3. 单次运行临时覆盖模型（--model / --fallbacks 参数）；
4. 测试候选模型的网络连通性与响应速度。
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import yaml
from typing import Dict, Any, List, Optional, Tuple

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(AGENT_DIR, "config.yaml")


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def resolve_model_spec(model_name: str, config: Dict[str, Any], provider_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """根据模型名称从 providers_pool 自动解析 base_url, api_key, provider_id 等连接信息。"""
    pool = config.get("providers_pool", [])
    model_clean = model_name.strip()

    # 1. 若给出了 provider 提示，优先在该 provider 下找
    if provider_hint:
        for p in pool:
            if p.get("id") == provider_hint or p.get("name") == provider_hint:
                for m in p.get("models", []):
                    if m.lower() == model_clean.lower():
                        return {
                            "base_url": p.get("base_url", "").rstrip("/"),
                            "api_key": p.get("api_key", ""),
                            "model": m,
                            "provider_id": p.get("id"),
                            "provider_name": p.get("name", p.get("id"))
                        }

    # 2. 全局完全匹配
    for p in pool:
        for m in p.get("models", []):
            if m.lower() == model_clean.lower():
                return {
                    "base_url": p.get("base_url", "").rstrip("/"),
                    "api_key": p.get("api_key", ""),
                    "model": m,
                    "provider_id": p.get("id"),
                    "provider_name": p.get("name", p.get("id"))
                }

    # 3. 前缀/模糊匹配（如用户输入 claude-sonnet 匹配 claude-sonnet-4-6）
    for p in pool:
        for m in p.get("models", []):
            if model_clean.lower() in m.lower():
                return {
                    "base_url": p.get("base_url", "").rstrip("/"),
                    "api_key": p.get("api_key", ""),
                    "model": m,
                    "provider_id": p.get("id"),
                    "provider_name": p.get("name", p.get("id"))
                }

    # 4. 当前 strategy_model 若已配置该模型且有 url
    sm = config.get("strategy_model", {})
    if sm.get("model", "").lower() == model_clean.lower():
        return {
            "base_url": sm.get("base_url", "").rstrip("/"),
            "api_key": sm.get("api_key", ""),
            "model": sm.get("model"),
            "provider_id": sm.get("provider_id", "custom"),
            "provider_name": sm.get("provider_name", "custom")
        }

    return None


def ping_model(cand: Dict[str, Any], timeout: int = 15) -> Tuple[bool, float, str]:
    """向指定模型发送测试探测，返回 (是否可用, 耗时秒, 描述信息)。"""
    url = f"{cand['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cand.get('api_key', '')}"
    }
    payload = {
        "model": cand["model"],
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
        "temperature": 0.1
    }
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dur = round(time.time() - t0, 2)
            d = json.loads(resp.read().decode("utf-8"))
            msg = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, dur, msg.strip() or "OK"
    except Exception as e:
        dur = round(time.time() - t0, 2)
        return False, dur, str(e)


def set_models(primary: str, fallbacks: Optional[List[str]] = None, primary_provider: Optional[str] = None) -> Dict[str, Any]:
    """
    修改 config.yaml 持久化设置主模型与备用链。
    primary: 主模型名称
    fallbacks: 备用模型名称列表（按调用顺序）
    """
    cfg = load_config()
    res_primary = resolve_model_spec(primary, cfg, primary_provider)
    if not res_primary:
        return {"ok": False, "error": f"在 providers_pool 中未找到符合 '{primary}' 的模型。"}

    sm = cfg.get("strategy_model", {})
    sm["model"] = res_primary["model"]
    sm["base_url"] = res_primary["base_url"]
    sm["api_key"] = res_primary["api_key"]
    sm["provider_id"] = res_primary["provider_id"]
    sm["provider_name"] = res_primary["provider_name"]

    fb_specs = []
    if fallbacks:
        for fb_name in fallbacks:
            fb_spec = resolve_model_spec(fb_name, cfg)
            if fb_spec:
                fb_specs.append({
                    "base_url": fb_spec["base_url"],
                    "model": fb_spec["model"],
                    "api_key": fb_spec["api_key"],
                    "provider_id": fb_spec["provider_id"],
                    "provider_name": fb_spec["provider_name"]
                })
            else:
                print(f"[witp_models] 警告：备用模型 '{fb_name}' 未能解析，已跳过。", file=sys.stderr)
    sm["fallbacks"] = fb_specs
    cfg["strategy_model"] = sm
    save_config(cfg)
    return {"ok": True, "primary": res_primary, "fallbacks": fb_specs}


def list_models_status(test: bool = False) -> None:
    """打印当前模型配置状态、可用模型清单及网络测试。"""
    cfg = load_config()
    sm = cfg.get("strategy_model", {})
    cur_m = sm.get("model", "未配置")
    cur_p = sm.get("provider_id", "未知")
    fallbacks = sm.get("fallbacks", [])

    print("═══════════════════════════════════════════════════════════════════")
    print("🎖️ WitP-AE 作战参谋大模型配置状态")
    print("═══════════════════════════════════════════════════════════════════")
    print(f"【当前主模型】: {cur_m}  (Provider: {cur_p})")
    if fallbacks:
        print("【当前备用链】(顺序回退):")
        for idx, fb in enumerate(fallbacks, 1):
            print(f"   {idx}. {fb.get('model')}  (Provider: {fb.get('provider_id')})")
    else:
        print("【当前备用链】: (无 Fallback，主模型失败后将降级为启发式规则)")

    if test:
        print("\n── 正在测试当前主模型与备用链网络响应 ──")
        ok, dur, desc = ping_model(sm)
        status_sym = "✅ 正常" if ok else "❌ 异常"
        print(f"  主模型 [{cur_m}]: {status_sym} ({dur}s) - {desc}")
        for idx, fb in enumerate(fallbacks, 1):
            f_ok, f_dur, f_desc = ping_model(fb)
            f_sym = "✅ 正常" if f_ok else "❌ 异常"
            print(f"  备用{idx} [{fb.get('model')}]: {f_sym} ({f_dur}s) - {f_desc}")

    print("\n═══════════════════════════════════════════════════════════════════")
    print("📦 模型池全部可用候选 (可直接作为 --primary 或 --fallbacks 传入)")
    print("═══════════════════════════════════════════════════════════════════")
    pool = cfg.get("providers_pool", [])
    for p in pool:
        pid = p.get("id")
        pname = p.get("name", pid)
        base = p.get("base_url")
        models = p.get("models", [])
        print(f"\n▶ Provider [{pid}] : {pname}  ({base})")
        for m in models:
            is_active = (m == cur_m)
            is_fb = any(m == fb.get("model") for fb in fallbacks)
            mark = " ◄ 当前主模型" if is_active else (" ◄ 备用模型" if is_fb else "")
            print(f"    • {m}{mark}")
    print("\n💡 设定指令示例：")
    print("   witp-cmd model set --primary gemini-3.7-flash-high --fallbacks claude-sonnet-4-6,step-5-preview")
    print("   witp-cmd staff --model claude-sonnet-4-6  (单次指令临时指定)")
    print("═══════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        list_models_status(test=True)
    else:
        list_models_status(test=False)
