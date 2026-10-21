"""witp_mem_bridge.py — MCP 用的内存读写桥接层

把 witp_mem.py 的能力包装成 MCP 可直接调用的函数。
每次调用都现场定位基址（地址会漂移），并用当前存档做交叉验证。

设计要点：
  · 定位必须用「当前存档的 flagship 集合」，否则游戏状态变了会定位到旧数组
  · 每次 set 后立刻读回确认，返回新旧值
  · 不缓存基址（实测 0xcf7510c 几分钟后失效）
"""
import os
import struct
import sys

import pathlib as _pl
READER = str(_pl.Path(__file__).resolve().parent)
if READER not in sys.path:
    sys.path.insert(0, READER)

import witp_mem


def _expect_from_save(save_path):
    import pwsfile
    c = pwsfile.read_container(save_path)
    for r in c["records"]:
        if r["u_len"] == 2224000:
            out = {}
            for s in range(200):
                b = s * witp_mem.TF_SZ
                fl = struct.unpack_from("<I", r["data"], b + 44)[0]
                if fl:
                    out[s] = fl
            return out
    return {}


def locate(save_path):
    """返回 (pid, base) 或 (None, None)"""
    pid = witp_mem.game_pid()
    if not pid:
        return None, None
    expect = _expect_from_save(save_path)
    base = witp_mem.find_tf_base(pid, expect)
    return pid, base


def list_tfs(save_path):
    pid, base = locate(save_path)
    if not base:
        return {"ok": False, "error": "无法定位 TF 数组（游戏未运行或存档不匹配）"}
    out = []
    for tf in witp_mem.occupied(pid, base):
        m = witp_mem.get(pid, base, tf, "mission")
        out.append({
            "tf": tf,
            "flagship": witp_mem.get(pid, base, tf, "flagship"),
            "home": witp_mem.get(pid, base, tf, "home"),
            "mission": m,
            "mission_name": witp_mem.MISSION.get(m, "?"),
            "speed": witp_mem.get(pid, base, tf, "speed"),
            "maxReact": witp_mem.get(pid, base, tf, "maxReact"),
            "routing": witp_mem.get(pid, base, tf, "routing"),
            "tolerance": witp_mem.get(pid, base, tf, "tolerance"),
            "loadState": witp_mem.get(pid, base, tf, "loadState"),
            "wpCount": witp_mem.get(pid, base, tf, "wpCount"),
            "waypoints": [list(p) for p in witp_mem.get(pid, base, tf, "wp")
                          if p != (0, 0)],
        })
    return {"ok": True, "pid": pid, "base": hex(base),
            "step": witp_mem.TF_SZ, "count": len(out), "tfs": out}


def show_tf(save_path, tf):
    pid, base = locate(save_path)
    if not base:
        return {"ok": False, "error": "无法定位 TF 数组"}
    d = {}
    for k in witp_mem.TF_OFF:
        d[k] = witp_mem.get(pid, base, tf, k)
    return {"ok": True, "tf": tf, "base": hex(base), "fields": d}


def set_tf_field(save_path, tf, field, value):
    pid, base = locate(save_path)
    if not base:
        return {"ok": False, "error": "无法定位 TF 数组"}
    if field not in witp_mem.TF_OFF:
        return {"ok": False, "error": f"未知字段 {field}，可用: {list(witp_mem.TF_OFF)}"}
    # 任务字段允许传名称（AIRCOMBAT）或数字（1）；其他字段只接受数字
    if field == "mission" and isinstance(value, str) and not value.lstrip("-").isdigit():
        v = witp_mem.MISSION_R.get(value.upper())
        if v is None:
            return {"ok": False, "error": f"未知任务名 {value}，可用: {list(witp_mem.MISSION_R)}"}
        value = v
    try:
        value = int(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"字段 {field} 需要数字，收到 {value!r}"}
    old = witp_mem.get(pid, base, tf, field)
    ok = witp_mem.set_field(pid, base, tf, field, int(value))
    new = witp_mem.get(pid, base, tf, field)
    return {"ok": bool(ok) and new == int(value), "tf": tf, "field": field,
            "old": old, "new": new, "verified": new == int(value)}


def set_tf_waypoints(save_path, tf, points):
    pid, base = locate(save_path)
    if not base:
        return {"ok": False, "error": "无法定位 TF 数组"}
    pts = [tuple(p) for p in points][:40]
    old_cnt = witp_mem.get(pid, base, tf, "wpCount")
    ok = witp_mem.set_waypoints(pid, base, tf, pts)
    new_cnt = witp_mem.get(pid, base, tf, "wpCount")
    back = [list(p) for p in witp_mem.get(pid, base, tf, "wp")[:len(pts)]]
    return {"ok": bool(ok) and new_cnt == len(pts),
            "tf": tf, "old_wpCount": old_cnt, "new_wpCount": new_cnt,
            "written": [list(p) for p in pts], "readback": back,
            "verified": back == [list(p) for p in pts]}
