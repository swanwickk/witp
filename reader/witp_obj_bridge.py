"""witp_obj_bridge.py — 8 类对象的 MCP 桥接层

统一入口，屏蔽各类的差异（基址/步长/镜像）。
"""
import os
import sys

import pathlib as _pl
READER = str(_pl.Path(__file__).resolve().parent)
if READER not in sys.path:
    sys.path.insert(0, READER)

import witp_obj

KINDS = tuple(witp_obj.OBJECTS)


def _pid():
    return witp_obj.game_pid()


def show(kind, idx):
    pid = _pid()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    if kind not in witp_obj.OBJECTS:
        return {"ok": False, "error": f"未知对象 {kind}，可用: {list(KINDS)}"}
    o = witp_obj.OBJECTS[kind]
    fields = {}
    for f in witp_obj.FIELDS[kind]:
        fields[f] = witp_obj.get(pid, kind, idx, f)
    return {"ok": True, "kind": kind, "index": idx,
            "base": hex(o["base"]), "step": o["sz"],
            "has_mirror": bool(o["mirror"]), "fields": fields}


def set_field(kind, idx, field, value):
    pid = _pid()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    if kind not in witp_obj.OBJECTS:
        return {"ok": False, "error": f"未知对象 {kind}"}
    if field not in witp_obj.FIELDS[kind]:
        return {"ok": False, "error": f"未知字段 {field}，可用: {list(witp_obj.FIELDS[kind])}"}
    try:
        value = int(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"需要数字，收到 {value!r}"}
    old = witp_obj.get(pid, kind, idx, field)
    ok, res = witp_obj.set_field(pid, kind, idx, field, value)
    return {"ok": ok, "kind": kind, "index": idx, "field": field,
            "old": old, "value": value, "copies": res, "verified": ok}


def find(kind, name):
    pid = _pid()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    if kind not in ("ship", "leader", "shipclass", "aircraft", "device"):
        return {"ok": False, "error": f"{kind} 不支持按名称查找"}
    i = witp_obj.find_by_name(pid, kind, name)
    return {"ok": i is not None, "kind": kind, "name": name, "index": i}


def list_objs(kind, limit=30):
    pid = _pid()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    if kind not in witp_obj.OBJECTS:
        return {"ok": False, "error": f"未知对象 {kind}"}
    occ = witp_obj.occupied(pid, kind)
    out = []
    KEY = {"taskforce": "flagship", "airgroup": "maxPlanes",
           "location": "X", "pilot": "id"}
    key = KEY.get(kind, "name")
    for i in occ[:limit]:
        item = {"index": i, key: witp_obj.get(pid, kind, i, key)}
        if kind == "ship":
            item.update({k: witp_obj.get(pid, kind, i, k)
                         for k in ("endurance", "repairPriority", "repairMode")})
        elif kind == "airgroup":
            item.update({k: witp_obj.get(pid, kind, i, k)
                         for k in ("primary", "pctCAP", "pctSearch", "baseID")})
        elif kind == "leader":
            item.update({k: witp_obj.get(pid, kind, i, k)
                         for k in ("rank", "skill", "morale", "politicalPoints")})
        out.append(item)
    return {"ok": True, "kind": kind, "count": len(out), "items": out}
