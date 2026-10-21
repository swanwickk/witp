#!/usr/bin/env python3
"""WitP-AE 参谋视图生成器（中文简报，纯文本，便于直接复制转发）。

用法: witp_summarize.py <JSON导出目录> [游戏SAVE目录(用于附战报原文)]

所有数值均取自存档解析结果；解析结果里没有的字段一律不写，不做任何推测。
任务码为存档原始值，中文映射尚未核验（见文末标注）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TF_MISSION_CN = {
    "AIRCOMBAT": "空战（航母编队）", "SURFACE": "水面战", "BOMBARDMENT": "炮击",
    "FASTTRANSPORT": "快速运输", "TRANSPORT": "运输", "REPLENISHMENT": "海上补给",
    "MINELAYING": "布雷", "SUBPATROL": "潜艇巡逻", "SUBMINELAYING": "潜艇布雷",
    "SUBTRANSPORT": "潜艇运输", "CARGO": "货运", "AIRTRANSPORT": "空运",
    "CVESCORT": "航母护航", "AMPHIB": "两栖登陆", "ASWCOMBAT": "反潜",
    "PTBOAT": "鱼雷艇", "TANKER": "油船", "MINESWEEPING": "扫雷",
    "LANDINGCRAFT": "登陆艇", "SUPPORT": "支援", "LOCALMINESWEEPING": "局部扫雷",
    "ESCORT": "护航",
}
HQ_ALLIED_HINT = "司令部"          # 本方指挥部命名特征（实测：南太平洋/西南太平洋司令部）
OFFMAP = 65535                     # 存档里离图基地的坐标哨兵值
REPORT_FILES = ("combatreport.txt", "aoperationsreport.txt", "asigint.txt")


def load(d: Path, name: str):
    p = d / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def own_base(b: dict) -> bool:
    if (b.get("x") in (None, OFFMAP)) or (b.get("y") in (None, OFFMAP)):
        return False
    if b.get("stationed_air") or b.get("stationed_ground"):
        return True
    return HQ_ALLIED_HINT in str(b.get("area_command") or "")


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    save_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    turn = load(out_dir, "turn.json") or {}
    tfs = load(out_dir, "taskforces.json") or []
    ships = load(out_dir, "ships.json") or []
    airgroups = load(out_dir, "airgroups.json") or []
    bases = load(out_dir, "bases.json") or []
    ground = load(out_dir, "ground_units.json") or []
    threats = load(out_dir, "threats.json") or {}

    L: list[str] = []

    L.append("一、基本态势")
    L.append(f"日期 {turn.get('game_date','?')}　回合 {turn.get('game_turn','?')}　剧本 {turn.get('scenario_name','?')}")
    if turn.get("header_comment"):
        L.append(f"存档头注释：{turn['header_comment']}")
    L.append(f"本方编队 {len(tfs)} 个；舰船 {len([s for s in ships if s.get('name')])} 艘；"
             f"地面部队 {len(ground)} 个；航空队 {len([a for a in airgroups if a.get('aircraft_active')])} 个")
    L.append("")

    L.append("二、我方编队")
    for t in tfs:
        mission = TF_MISSION_CN.get(t.get("mission", ""), t.get("mission", "?"))
        L.append(f"TF{t.get('record_id')}　{mission}　舰船 {len(t.get('ships') or [])} 艘　旗舰 {t.get('flagship_name') or '?'}"
                 f"　指挥官 {t.get('commander') or '?'}")
        L.append(f"　　位置 ({t.get('start_of_day_x')},{t.get('start_of_day_y')})→"
                 f"({t.get('end_of_day_x')},{t.get('end_of_day_y')})　目标 ({t.get('target_x')},{t.get('target_y')})")
        names = [s.get("name") for s in (t.get("ships") or []) if s.get("name")]
        if names:
            L.append(f"　　编成：{'、'.join(names)}")
    L.append("")

    L.append("三、舰船状况（舰名/舰级/损伤 系统-进水-起火-引擎/所属编队/位置）")
    for s in [x for x in ships if x.get("name")]:
        dmg = f"{s.get('system_damage','?')}-{s.get('flotation_damage','?')}-{s.get('fire_damage','?')}-{s.get('engine_damage','?')}"
        tf = f"TF{s.get('task_force_id')}" if s.get("task_force_id") is not None else "—"
        L.append(f"{s.get('name')} / {s.get('ship_class_name') or '?'} / 损伤 {dmg} / {tf} / "
                 f"{s.get('stationed_at_base_name') or '海上'}")
    L.append("")

    L.append("四、航空兵（中队　机型　可用/编制　驻地　主任务码(次任务码)　搜索比例　扇面　驻地/转场）")
    for a in [x for x in airgroups if x.get("aircraft_active") or x.get("name")]:
        where = a.get("stationed_on_ship_name") or a.get("stationed_at_base_name") or "?"
        extra = ""
        if a.get("rebase_target_base_name"):
            extra = f"　转场→{a.get('rebase_target_base_name')}"
        arc = ""
        if a.get("search_arc_start") or a.get("search_arc_end"):
            arc = f"　扇面 {a.get('search_arc_start')}-{a.get('search_arc_end')}"
        L.append(f"{a.get('name')}　{a.get('aircraft_name') or '?'}　{a.get('aircraft_active')}/{a.get('aircraft_max')}　"
                 f"{where}　主任务码 {a.get('primary_mission_code')}({a.get('secondary_mission_code')})　"
                 f"搜索 {a.get('percent_search')}%{arc}{extra}")
    L.append("")

    L.append("五、本方基地后勤（仅列图内、且属本方指挥体系的基地；名称　港口/机场　补给/需求　燃料/需求　油料　资源）")
    all_on_map = [b for b in bases if b.get("x") not in (None, OFFMAP) and b.get("y") not in (None, OFFMAP)]
    mine = [b for b in all_on_map if own_base(b)]
    mine.sort(key=lambda b: (b.get("supply") or 0) + (b.get("fuel") or 0), reverse=True)
    for b in mine[:30]:
        L.append(f"{b.get('name')}　{b.get('port')}/{b.get('airfield')}　{b.get('supply')}/{b.get('supply_needed')}　"
                 f"{b.get('fuel')}/{b.get('fuel_needed')}　{b.get('oil')}　{b.get('resources')}"
                 f"　({b.get('x')},{b.get('y')})　{b.get('area_command') or ''}")
    if len(mine) > 30:
        L.append(f"（另有 {len(mine)-30} 个本方基地未列出；图上基地共 {len(all_on_map)} 个，非本方或未判定的 {len(all_on_map)-len(mine)} 个）")
    L.append("")

    L.append("六、威胁区（由战报与情报推导，坐标为我方判读）")
    any_threat = False
    for key, label in (("sub_threat_areas", "潜艇"), ("surface_threat_areas", "水面"),
                       ("carrier_threat_areas", "航母"), ("invasion_threat_areas", "登陆")):
        items = threats.get(key) or []
        if not items:
            continue
        any_threat = True
        L.append(f"{label}威胁区 {len(items)} 处：")
        for it in items[:8]:
            pos = it.get("position") or {}
            ev = (it.get("evidence_texts") or [""])[0]
            tgt = it.get("threat_base_name") or it.get("invasion_target_name") or ""
            L.append(f"　({pos.get('x')},{pos.get('y')})　见证 {it.get('evidence_count')} 条　{tgt}　{ev[:120]}")
    if not any_threat:
        L.append("（本回合无威胁区记录）")
    L.append("")

    if save_dir and save_dir.is_dir():
        L.append("七、战报原文（游戏自己写出，GBK 文本）")
        for name in REPORT_FILES:
            p = save_dir / name
            if not p.exists():
                continue
            try:
                body = p.read_text(encoding="gbk", errors="replace").strip()
            except Exception as exc:
                body = f"（读取失败：{exc}）"
            L.append(f"--- {name} ---")
            L.append(body[:1800] if body else "（空）")
        L.append("")

    L.append("附注：航空兵“主任务码”为存档原始编号，中文名称映射尚未核验，故此处不译，避免臆造。")

    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
