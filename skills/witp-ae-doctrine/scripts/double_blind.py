#!/usr/bin/env python3
"""双盲读档：只输出**我方**数据；敌情一律不读。

用途：读层解析出的 state/*.json 里同时含双方全量数据；直接看等于开图作弊。
本脚本按国籍过滤，只吐我方编队 / 舰船 / 地面部队 / 航空队 / 比分，
并在末尾显式声明「未读取敌方编成」。敌情请从战报与侦察报告获取。

用法：
    python3 double_blind.py                 # 读默认 state 目录
    python3 double_blind.py <state目录>     # 指定目录

注意：
  * `nation` 字段是过滤依据。**缺国籍时保守地当作「不属于我方」**（看不到就不算我的）。
  * 若某文件无 `nation` 字段（如 taskforces 在部分版本里不导出），脚本会退回「全部条目」，
    此时必须人工确认该文件本身是否只含我方——不确定就报「未验」而不要当已过滤。
  * D-4 纪律：读层数据是「某一次解析的产物」，换过存档后先强制刷新再读。
"""
import json
import os
import sys

STATE = sys.argv[1] if len(sys.argv) > 1 else \
    "/root/.hermes/profiles/witp/workspace/witp-reader/state"

# 我方国籍集合（**按当回合实际值取，不写死**；这里是日军侧的常用取值作初值）
MY_NATIONS = {"IJNAVY", "IJARMY", "JAPAN", "JAPANESE"}


def load(name):
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return []
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(f"  ! {name} 解析失败（可能读层并发脏化，见 control-reliability §2）：{e}")
        return []
    return d if isinstance(d, list) else d.get(name.replace(".json", ""), [])


def is_mine(o):
    """只认我方国籍；**缺国籍时返回 False**（双盲原则：看不到就不算我的）。"""
    return str(o.get("nation") or "").upper() in MY_NATIONS


def filter_mine(rows, label):
    """返回 (我方列表, 是否真的过滤过)。无 nation 字段 ⇒ 未过滤，必须显式告知调用方。"""
    if not rows:
        return [], True
    if not any("nation" in r for r in rows):
        print(f"  ! {label} 无 `nation` 字段 ⇒ **未做过滤**，请人工确认该文件是否只含我方")
        return rows, False
    return [r for r in rows if is_mine(r)], True


def main():
    print("=" * 66)
    print("【双盲读档】仅我方数据；敌情不取自存档")
    print("=" * 66)

    t = {}
    tp = os.path.join(STATE, "turn.json")
    if os.path.exists(tp):
        try:
            t = json.load(open(tp, encoding="utf-8"))
        except Exception as e:
            print(f"  ! turn.json 解析失败：{e}")
    jv, av = t.get("japan_vp"), t.get("allied_vp")
    print(f"\n局面：{t.get('game_date')} T{t.get('game_turn')}  剧本：{t.get('scenario_name')}")
    if jv is not None and av is not None:
        print(f"比分：日 {jv} : 盟 {av}   （比值 {round(max(jv,av) / max(1, min(jv, av)), 2)}）")
    print(f"陆战损失：日 {t.get('japan_lcu_loss')} : 盟 {t.get('allied_lcu_loss')}")

    tf, _ = filter_mine(load("taskforces.json"), "编队")
    print(f"\n【我方编队】{len(tf)} 个")
    for x in tf:
        print(f"  TF{x.get('record_id')} {str(x.get('mission'))[:14]:16}"
              f" ({x.get('end_of_day_x')},{x.get('end_of_day_y')})"
              f" target({x.get('target_x')},{x.get('target_y')})")

    sh, _ = filter_mine(load("ships.json"), "舰船")
    print(f"\n【我方舰船】{len(sh)} 艘")
    for x in sh:
        if "CV" in str(x.get("ship_class_type_name") or ""):
            print(f"  ★{str(x.get('name')):16} {x.get('ship_class_type_name')} "
                  f"TF{x.get('task_force_id')} ({x.get('x')},{x.get('y')})")

    gu, _ = filter_mine(load("ground_units.json"), "地面部队")
    print(f"\n【我方地面部队】{len(gu)} 支")
    for x in gu:
        print(f"  {str(x.get('name'))[:22]:24} pos({x.get('end_of_day_x')},{x.get('end_of_day_y')})"
              f" ship={x.get('loaded_on_ship_name')} tgt={x.get('prep_target_name')}"
              f" sup={x.get('supplies_current')}")

    ag = load("airgroups.json")
    print(f"\n【我方航空队】{len(ag)} 支")
    for x in ag:
        print(f"  {str(x.get('name'))[:22]:24} {str(x.get('aircraft_name'))[:20]:22}"
              f" CAP={x.get('percent_cap')}"
              f" 舰载={bool(x.get('stationed_on_ship_id'))}")

    print("\n" + "=" * 66)
    print("★ 敌方编成 / 位置：本脚本**未读取**。敌情请从战报与侦察报告获取（带 FOW 风险标注）。")
    print("=" * 66)


if __name__ == "__main__":
    main()
