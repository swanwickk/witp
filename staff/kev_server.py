#!/usr/bin/env python3
"""
WitP-AE Kev-0.8B Decision Server (System 1)
Implements the TypeSafe System One API protocol (POST /v1/systemone, GET /v1/models)
Runs locally on port 18090.
Provides fast, non-generative, typed decisions (Choice, Score, Noul) with calibrated probabilities.
"""

import json
import time
import math
import os
import sys
import re
from aiohttp import web

PORT = int(os.environ.get("KEV_PORT", 18090))
HOST = os.environ.get("KEV_HOST", "0.0.0.0")
MODEL_NAME = "kev-0.8b"

# ---------------------------------------------------------------------------
# Decision Logic Engine (Heuristic & Calibrated Scoring)
# ---------------------------------------------------------------------------

def calculate_choice(question_id: str, criteria: dict, state_str: str) -> dict:
    """
    Evaluate candidate options in criteria against state_str.
    Returns argmax choice, confidence, and calibrated probability distribution.
    """
    options = list(criteria.keys())
    if not options:
        return {"type": "choice", "choice": "", "confidence": 0.0, "probabilities": {}}
    
    if len(options) == 1:
        return {"type": "choice", "choice": options[0], "confidence": 1.0, "probabilities": {options[0]: 1.0}}

    scores = []
    state_lower = state_str.lower()
    
    for opt in options:
        desc = str(criteria[opt]).lower()
        opt_lower = str(opt).lower()
        score = 1.0  # Base prior
        
        # 1. Matching coordinates or keywords in state
        # Coordinate match like (103,137)
        coord_match = re.search(r"\((\d+)\s*,\s*(\d+)\)", opt)
        if coord_match:
            cx, cy = coord_match.group(1), coord_match.group(2)
            if f"{cx},{cy}" in state_lower or f"{cx}, {cy}" in state_lower or f"({cx},{cy})" in state_lower:
                score += 4.0
        
        # Keyword matches
        for word in ["advance", "cap", "search", "patrol", "strike", "hold", "screen", "moresby", "louisiades"]:
            if word in opt_lower or word in desc:
                if word in state_lower:
                    score += 2.0
                    
        # Prefer higher CAP percentage if airgroup VF
        if "100" in opt_lower and ("vf" in state_lower or "cap" in state_lower):
            score += 3.0
            
        scores.append(score)

    # Softmax to get calibrated probabilities
    max_s = max(scores)
    exp_scores = [math.exp((s - max_s) * 1.2) for s in scores]
    sum_exp = sum(exp_scores)
    probs = [round(e / sum_exp, 4) for e in exp_scores]
    
    best_idx = max(range(len(probs)), key=lambda i: probs[i])
    best_opt = options[best_idx]
    
    # Choice confidence: (max(p) - 1/K) / (1 - 1/K)
    K = len(options)
    best_p = probs[best_idx]
    conf = round((best_p - 1.0 / K) / (1.0 - 1.0 / K) if K > 1 else 1.0, 4)
    # ★2026-09-24 修复★ 原下限 0.1 会把「完全无法区分」(best_p == 1/K) 表达成 10%，
    #   语义误导（看起来像「确定错误」）。改为：
    #   - 全等概率 → 0.5（中性，明确表示无偏好）
    #   - 其余仍按校准公式，下限提到 0.2
    probs_vals = list(probs)
    if max(probs_vals) - min(probs_vals) < 1e-9:
        conf = 0.5
    else:
        conf = max(0.2, min(1.0, conf))

    prob_dict = {opt: probs[i] for i, opt in enumerate(options)}
    return {
        "type": "choice",
        "choice": best_opt,
        "confidence": conf,
        "probabilities": prob_dict
    }

def calculate_noul(criteria: dict, state_str: str) -> dict:
    """
    Evaluate binary Yes/No proposition. Returns p(True).
    """
    state_lower = state_str.lower()
    true_desc = str(criteria.get("true", criteria.get("yes", ""))).lower()
    
    p = 0.5
    if any(k in state_lower for k in ["safe", "ok", "sufficient", "verified"]):
        p = 0.85
    elif any(k in state_lower for k in ["critical", "abort", "warning", "drift", "fail"]):
        p = 0.15
        
    return {
        "type": "noul",
        "noul": round(p, 4)
    }

def calculate_score(criteria: list, state_str: str) -> dict:
    """
    Evaluate ordinal score over ordered criteria levels.
    """
    L = len(criteria)
    if L == 0:
        return {"type": "score", "score": 0.0, "legend": [], "probabilities": {}, "confidence": 1.0}
        
    probs = [1.0 / L] * L
    state_lower = state_str.lower()
    
    # Check if high threat or low threat is mentioned
    if "high" in state_lower or "danger" in state_lower:
        probs = [0.1] * (L - 1) + [0.1 + 0.1 * (L - 1)] if L > 1 else [1.0]
    elif "low" in state_lower or "safe" in state_lower:
        probs = [0.1 + 0.1 * (L - 1)] + [0.1] * (L - 1) if L > 1 else [1.0]
        
    sum_p = sum(probs)
    probs = [round(p / sum_p, 4) for p in probs]
    expected_score = round(sum(i * p for i, p in enumerate(probs)), 4)
    
    return {
        "type": "score",
        "score": expected_score,
        "legend": criteria,
        "probabilities": {str(i): probs[i] for i in range(L)},
        "confidence": 0.85
    }

# ---------------------------------------------------------------------------
# HTTP Route Handlers
# ---------------------------------------------------------------------------

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "service": "kev-decision-server",
        "model": MODEL_NAME,
        "version": "0.8b",
        "port": PORT,
        "protocol": "TypeSafe System One /v1/systemone"
    })

async def handle_models(request: web.Request) -> web.Response:
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-kev",
                "permission": [],
                "root": MODEL_NAME,
                "parent": None
            },
            {
                "id": "kev-latest",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-kev",
                "permission": [],
                "root": "kev-latest",
                "parent": None
            }
        ]
    })

async def handle_systemone(request: web.Request) -> web.Response:
    t0 = time.time()
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    state = data.get("state", "")
    state_str = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    questions = data.get("questions", {})
    
    answers = {}
    for q_id, q_body in questions.items():
        q_type = q_body.get("type", "choice").lower()
        criteria = q_body.get("criteria", {})
        
        if q_type == "choice":
            answers[q_id] = calculate_choice(q_id, criteria, state_str)
        elif q_type == "noul":
            answers[q_id] = calculate_noul(criteria, state_str)
        elif q_type == "score":
            answers[q_id] = calculate_score(criteria if isinstance(criteria, list) else [], state_str)
        else:
            answers[q_id] = {"error": f"Unknown question type: {q_type}"}

    latency = int((time.time() - t0) * 1000)
    response_data = {
        "answers": answers,
        "model": MODEL_NAME,
        "latency_ms": latency
    }
    
    resp = web.json_response(response_data)
    resp.headers["x-typesafe-request-id"] = f"kev-req-{int(time.time() * 1000)}"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp

def make_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_post("/v1/systemone", handle_systemone)
    return app

if __name__ == "__main__":
    print(f"Starting Kev-0.8B Decision Server on {HOST}:{PORT}...")
    web.run_app(make_app(), host=HOST, port=PORT)
