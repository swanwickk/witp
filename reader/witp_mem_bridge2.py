"""witp_mem_bridge2.py — 航空队 + 基地 的 MCP 桥接层

补充 witp_mem_bridge（只管 TF）。
所有定位都现场进行，不缓存（地址会漂移）。
"""
import os
import struct
import sys

import pathlib as _pl
READER = str(_pl.Path(__file__).resolve().parent)
if READER not in sys.path:
    sys.path.insert(0, READER)

import witp_ag
import witp_ag2
import witp_loc


# ── 航空队 ──────────────────────────────────────────────

def _ag_expect(save_path):
    import pwsfile
    d = pwsfile.record_by_len(save_path, 20400680)
    if d:
            out = {}
            for s in range(30001):
                b = s * witp_ag.AG_SZ
                if d[b + 245] == 0 and d[b + 44] == 0:
                    continue
                out[s] = (d[b + 44], d[b + 245],
                          struct.unpack_from("<H", d, b + 308)[0])
            return out
    return {}


def ag_locate(save_path):
    pid = witp_ag.game_pid()
    if not pid:
        return None, None
    return pid, witp_ag.find_ag_base(pid, _ag_expect(save_path))


def ag_show(save_path, ag):
    pid, base = ag_locate(save_path)
    if base is None:
        return {"ok": False, "error": "无法定位航空队数组"}
    return {"ok": True, "ag": ag, "base": hex(base),
            "fields": {k: witp_ag.get(pid, base, ag, k) for k in witp_ag.AG_OFF}}


def ag_set(save_path, ag, field, value):
    """★ 必须同时写 copyA 与 copyB。

    实测：只写 copyA → 界面变但过回合后存档不变（假成功）；
         写 copyB → 引擎存盘采纳。两份都写最稳。
    """
    if field not in witp_ag.AG_OFF:
        return {"ok": False, "error": f"未知字段，可用: {list(witp_ag.AG_OFF)}"}
    try:
        value = int(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"需要数字，收到 {value!r}"}

    pid = witp_ag2.pid_of()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    sig = witp_ag2.save_ag(save_path, ag)
    if not sig:
        return {"ok": False, "error": f"存档里找不到 AG{ag}"}

    a, b = witp_ag2.find_both(pid, ag, sig)
    if a is None:
        return {"ok": False, "error": "无法定位航空队结构"}

    detail = {}
    all_ok = True
    for nm, addr in (("copyA", a), ("copyB", b)):
        if not addr:
            continue
        old = witp_ag2.get(pid, addr, field)
        ok = witp_ag2.set_field(pid, addr, field, value)
        new = witp_ag2.get(pid, addr, field)
        detail[nm] = {"addr": hex(addr), "old": old, "new": new, "ok": ok}
        if new != value:
            all_ok = False
    return {"ok": all_ok, "ag": ag, "field": field, "value": value,
            "copies": detail, "verified": all_ok,
            "note": "copyB 是引擎存盘读取的那份，两份都已写入"}


def ag_list(save_path, limit=40):
    pid, base = ag_locate(save_path)
    if base is None:
        return {"ok": False, "error": "无法定位航空队数组"}
    out = []
    for ag in witp_ag.occupied(pid, base):
        out.append({
            "ag": ag,
            "primary": witp_ag.get(pid, base, ag, "primary"),
            "maxPlanes": witp_ag.get(pid, base, ag, "maxPlanes"),
            "pctCAP": witp_ag.get(pid, base, ag, "pctCAP"),
            "pctLRCAP": witp_ag.get(pid, base, ag, "pctLRCAP"),
            "pctASW": witp_ag.get(pid, base, ag, "pctASW"),
            "pctSearch": witp_ag.get(pid, base, ag, "pctSearch"),
            "pctTrain": witp_ag.get(pid, base, ag, "pctTrain"),
            "pctRest": witp_ag.get(pid, base, ag, "pctRest"),
            "baseID": witp_ag.get(pid, base, ag, "baseID"),
            "reinforceBase": witp_ag.get(pid, base, ag, "reinforceBase"),
        })
        if len(out) >= limit:
            break
    return {"ok": True, "base": hex(base), "count": len(out), "airgroups": out}


# ── 基地 ────────────────────────────────────────────────

def _loc_expect(save_path):
    import pwsfile
    d = pwsfile.record_by_len(save_path, 21096000)
    if d:
            out = {}
            for s in range(18000):
                b = s * witp_loc.LOC_SZ
                x = struct.unpack_from("<H", d, b + 36)[0]
                y = struct.unpack_from("<H", d, b + 38)[0]
                if not (0 < x < 250 and 0 < y < 250):
                    continue
                out[s] = (x, y, d[b + 104],
                          struct.unpack_from("<H", d, b + 102)[0])
            return out
    return {}


def loc_locate(save_path):
    pid = witp_loc.game_pid()
    if not pid:
        return None, None
    return pid, witp_loc.find_loc_base(pid, _loc_expect(save_path))


def loc_show(save_path, loc):
    pid, base = loc_locate(save_path)
    if base is None:
        return {"ok": False, "error": "无法定位基地数组"}
    return {"ok": True, "loc": loc, "base": hex(base),
            "fields": {k: witp_loc.get(pid, base, loc, k)
                       for k in witp_loc.LOC_OFF}}


def loc_set(save_path, loc, field, value):
    pid, base = loc_locate(save_path)
    if base is None:
        return {"ok": False, "error": "无法定位基地数组"}
    if field not in witp_loc.LOC_OFF:
        return {"ok": False, "error": f"未知字段，可用: {list(witp_loc.LOC_OFF)}"}
    try:
        value = int(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"需要数字，收到 {value!r}"}
    old = witp_loc.get(pid, base, loc, field)
    ok = witp_loc.set_field(pid, base, loc, field, value)
    new = witp_loc.get(pid, base, loc, field)
    return {"ok": bool(ok) and new == value, "loc": loc, "field": field,
            "old": old, "new": new, "verified": new == value}


def loc_find_by_hex(save_path, x, y):
    """按六角坐标找 Location 槽号（内存侧优先）。"""
    pid, base = loc_locate(save_path)
    if base is None:
        return {"ok": False, "error": "无法定位基地数组"}
    found = []
    for s in range(1, 14000):
        d = witp_loc._read(pid, base + s * witp_loc.LOC_SZ, 40)
        if not d:
            continue
        sx = struct.unpack_from("<H", d, 36)[0]
        sy = struct.unpack_from("<H", d, 38)[0]
        if (sx, sy) == (x, y):
            found.append(s)
    return {"ok": True, "hex": [x, y], "slots": found}
