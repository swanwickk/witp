#!/usr/bin/env python3
"""
WitP-AE 存档枚举与定位（共享模块）

供参谋部核心 witp_staff.py、看板后端 plugin_api.py、前线工具 witp-cmd 共同调用。
让前线主 Agent 能「主动指挥参谋部读取指定存档」，而不是由参谋部自行猜测该读哪份。

对外接口：
    list_saves()          -> 枚举 SAVE 目录下所有 .pws，附带槽位/时间/日期
    resolve_save(spec)    -> 把「槽位号 / 文件名 / 绝对路径」解析成绝对路径
    parse_save_meta(path) -> 直接解析 .pws 头，取出日期等元信息（无需 Wine，毫秒级）
"""

import os
import re
import glob
import gzip
import zlib
import struct
from datetime import datetime
from typing import Optional, List, Dict, Any

SAVE_DIR = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"

# 已知槽位语义（来自实测）
SLOT_MEANING = {
    "000": "Autosave（结算后新状态）",
    "002": "PreTurnSave（结算前旧状态）",
    "003": "手动存档槽",
}


def parse_save_meta(path: str) -> Dict[str, Any]:
    """直接解析 .pws（gzip + zlib 块）取日期等元信息，不依赖 Wine。"""
    meta = {"date": None, "parse_error": None}
    try:
        raw = gzip.open(path, "rb").read()
        _, _, c = struct.unpack_from("<III", raw, 0)
        inner = zlib.decompress(raw[12:12 + c])
        m = re.search(rb"Date:\s*([0-9/]+)", inner)
        if m:
            meta["date"] = m.group(1).decode()
        m2 = re.search(rb"Scenario:\s*([^\r\n\x00]{3,80})", inner)
        if m2:
            meta["scenario_raw"] = m2.group(1).decode(errors="replace").strip()
    except Exception as exc:
        meta["parse_error"] = str(exc)
    return meta


def _slot_of(filename: str) -> Optional[str]:
    m = re.match(r"wpae(\d{3})\.pws$", filename)
    return m.group(1) if m else None


def list_saves(save_dir: str = SAVE_DIR, with_meta: bool = True) -> List[Dict[str, Any]]:
    """枚举存档目录下所有 .pws，按 mtime 倒序。"""
    out: List[Dict[str, Any]] = []
    for p in glob.glob(os.path.join(save_dir, "*.pws")):
        try:
            st = os.stat(p)
        except OSError:
            continue
        fn = os.path.basename(p)
        slot = _slot_of(fn)
        item = {
            "file": fn,
            "path": p,
            "slot": slot,
            "slot_meaning": SLOT_MEANING.get(slot or "", ""),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "mtime_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "age_s": round(datetime.now().timestamp() - st.st_mtime, 1),
        }
        if with_meta:
            item.update(parse_save_meta(p))
        out.append(item)
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def resolve_save(spec: str, save_dir: str = SAVE_DIR) -> Optional[str]:
    """
    把用户的指定解析为存档绝对路径。支持三种写法：
      - 槽位号：   "000" / "002" / "003"        （自动补成 wpaeNNN.pws）
      - 文件名：   "wpae002.pws"
      - 绝对路径： "/root/.wine-witp/.../SAVE/wpae002.pws"
    解析失败返回 None。
    """
    if not spec:
        return None
    spec = spec.strip()

    # 绝对路径
    if os.path.isabs(spec):
        return spec if os.path.isfile(spec) else None

    # 槽位号（3 位数字）
    if re.fullmatch(r"\d{1,3}", spec):
        cand = os.path.join(save_dir, f"wpae{int(spec):03d}.pws")
        return cand if os.path.isfile(cand) else None

    # 文件名
    if spec.endswith(".pws"):
        cand = os.path.join(save_dir, spec)
        return cand if os.path.isfile(cand) else None

    # 前缀模糊匹配（如 "wpae00"）
    matches = [p for p in glob.glob(os.path.join(save_dir, "*.pws"))
               if os.path.basename(p).startswith(spec)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        # 多个匹配时取最新的
        return max(matches, key=os.path.getmtime)
    return None


def newest_save(save_dir: str = SAVE_DIR) -> Optional[str]:
    saves = list_saves(save_dir, with_meta=False)
    return saves[0]["path"] if saves else None
