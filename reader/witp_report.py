"""witp_report.py — 综合态势报告（纯内存读取，零键鼠零 OCR）

把已标定的所有字段汇总成可用的参谋视图：
  · 编队（任务/速度/目的地/航路/指挥官/巡逻区）
  · 航空队（任务/百分比/编制/驻留）
  · 基地（坐标/HQ/指挥官/准备度/扩建/港口等级/司令部层级）
  · 舰船（耐久/损伤四值/修理/所属 TF/指挥官）
  · 飞行员（ID/技能/状态）
  · 损伤汇总、指挥官名册

所有字段偏移都是实测验证过的（见技能 witp-ae-save-format）。
"""
import os
import struct
import sys

import pathlib as _pl
READER = str(_pl.Path(__file__).resolve().parent)
if READER not in sys.path:
    sys.path.insert(0, READER)

import witp_obj

# ── Location 附加字段（本轮新标定）──
LOC_EXTRA = {
    "cmdLevel":   (124, "u8"),    # 尚未语义确证的司令部层级候选
    "portSize":   (786, "u8"),    # 尚未语义确证的港口等级候选
    "field430":   (430, "u8"),
    "airfieldLvl": (814, "u8"),
}

# PWSScenInfo stable head fields (from pwsdll.py); scenario record is shorter
# than the ctypes allocation, so only fields fully inside the save block apply.
SCEN_FIELDS = {
    "turn": (30, "u16"),
    "japan_vp": (116, "i32"),
    "allied_vp": (120, "i32"),
}

# PWSLocation facts relevant to the manual's industry/resource availability display.
LOC_ECON_FIELDS = {
    "owner": (26, "u16"), "type": (28, "u16"),
    "port": (420, "u16"), "airfield": (422, "u16"),
    "shipRepair": (496, "i32"),
    "portDamage": (434, "u16"), "airfieldDamage": (436, "u16"),
    "runwayDamage": (438, "u16"),
    "resources": (508, "i32"), "resourcesNeeded": (512, "i32"),
    "oil": (520, "i32"), "oilNeeded": (524, "i32"),
    "fuel": (528, "i32"), "fuelRequested": (532, "i32"),
    "supply": (536, "i32"), "supplyNeeded": (540, "i32"),
    "dailySupply": (824, "u16"), "dailyFuel": (826, "u16"),
    "dailyOil": (828, "u16"), "dailyResources": (830, "u16"),
}
# Economic-device ID -> facility label. Counts and damage are held in the
# base's deviceID/deviceNumber/deviceDis parallel arrays (each 20 u16 slots).
INDUSTRY_DEVICE_IDS = {
    519: "resourceCenters", 520: "manpowerCenters", 521: "heavyIndustry",
    522: "navalShipyard", 523: "merchantShipyard", 524: "repairShipyard",
    525: "armamentAssembly", 526: "vehicleAssembly", 527: "lightIndustry",
    528: "refinery", 518: "oilCenters",
}


SCALAR = {"u8": "<B", "u16": "<H", "i16": "<h", "i32": "<i"}


def _pid():
    return witp_obj.game_pid()


def base_and_pid():
    pid = _pid()
    if not pid:
        return None, None
    return pid, witp_obj.OBJECTS


def read_tfs(pid):
    out = []
    base = witp_obj.OBJECTS["taskforce"]["base"]
    for tf in range(1, 40):
        fl = witp_obj.get(pid, "taskforce", tf, "flagship")
        if not fl:
            continue
        d = witp_obj._read(pid, base + tf * 556, 556)
        if not d:
            continue
        wps = []
        n = witp_obj.get(pid, "taskforce", tf, "wpCount") or 0
        if n:
            raw = witp_obj._read(pid, base + tf * 556 + 118, n * 4)
            if raw:
                wps = [list(struct.unpack_from("<HH", raw, i * 4)) for i in range(n)]
        item = {
            "tf": tf,
            "flagship": fl,
            "flagship_name": witp_obj.get(pid, "ship", fl, "name"),
            "mission_code": witp_obj.get(pid, "taskforce", tf, "mission"),
            "mission": witp_obj.TF_MISSION.get(witp_obj.get(pid, "taskforce", tf, "mission"), "?"),
            "speed": witp_obj.get(pid, "taskforce", tf, "speed"),
            "speedSetting": witp_obj.get(pid, "taskforce", tf, "speedSetting"),
            "routing": witp_obj.get(pid, "taskforce", tf, "routing"),
            "tolerance": witp_obj.get(pid, "taskforce", tf, "tolerance"),
            "maxReact": witp_obj.get(pid, "taskforce", tf, "maxReact"),
            "atBase": witp_obj.get(pid, "taskforce", tf, "atBase"),
            "home": witp_obj.get(pid, "taskforce", tf, "home"),
            "loadState": witp_obj.get(pid, "taskforce", tf, "loadState"),
            "followMode": witp_obj.get(pid, "taskforce", tf, "followMode"),
            "followTF": witp_obj.get(pid, "taskforce", tf, "followTF"),
            "wpCount": n,
            "waypoints": [list(p) for p in wps[:n]] if n else [],
            "endurance": witp_obj.get(pid, "taskforce", tf, "endure"),
            "load": witp_obj.get(pid, "taskforce", tf, "load"),
        }
        # 成员
        members = []
        for i in range(1, 20000):
            if witp_obj.get(pid, "ship", i, "locationID") == 14000 + tf:
                members.append({"ship": i,
                                "name": witp_obj.get(pid, "ship", i, "name"),
                                "endurance": witp_obj.get(pid, "ship", i, "endurance")})
        item["members"] = members
        out.append(item)
    return out


def read_ags(pid, limit=200):
    out = []
    for a in range(1, 30001):
        mp = witp_obj.get(pid, "airgroup", a, "maxPlanes")
        if not mp:
            continue
        out.append({
            "ag": a,
            "primary": witp_obj.get(pid, "airgroup", a, "primary"),
            "primary_name": witp_obj.AG_MISSION.get(witp_obj.get(pid, "airgroup", a, "primary"), "?"),
            "secondary": witp_obj.get(pid, "airgroup", a, "secondary"),
            "maxPlanes": mp,
            "baseID": witp_obj.get(pid, "airgroup", a, "baseID"),
            "reinforceBase": witp_obj.get(pid, "airgroup", a, "reinforceBase"),
            "pctCAP": witp_obj.get(pid, "airgroup", a, "pctCAP"),
            "pctLRCAP": witp_obj.get(pid, "airgroup", a, "pctLRCAP"),
            "pctASW": witp_obj.get(pid, "airgroup", a, "pctASW"),
            "pctSearch": witp_obj.get(pid, "airgroup", a, "pctSearch"),
            "pctTrain": witp_obj.get(pid, "airgroup", a, "pctTrain"),
            "pctRest": witp_obj.get(pid, "airgroup", a, "pctRest"),
            "alt": witp_obj.get(pid, "airgroup", a, "alt"),
            "upgradeTo": witp_obj.get(pid, "airgroup", a, "upgradeTo"),
            "withdraw": witp_obj.get(pid, "airgroup", a, "withdraw"),
            "navArc": [witp_obj.get(pid, "airgroup", a, "navArcStart"),
                       witp_obj.get(pid, "airgroup", a, "navArcEnd")],
            "aswArc": [witp_obj.get(pid, "airgroup", a, "aswArcStart"),
                       witp_obj.get(pid, "airgroup", a, "aswArcEnd")],
        })
        if len(out) >= limit:
            break
    return out


def read_bases(pid, limit=120):
    out = []
    for l in range(1, 14000):
        x = witp_obj.get(pid, "location", l, "X")
        y = witp_obj.get(pid, "location", l, "Y")
        if not x or not y:
            continue
        d = witp_obj._read(pid, 0x4570c50 + l * 1172, 1172)
        if not d:
            continue
        nm = d[0:24].split(bytes([0]))[0].decode("ascii", "replace")
        hq = witp_obj.get(pid, "location", l, "attachedHQ")
        lid = witp_obj.get(pid, "location", l, "leaderID")
        out.append({
            "loc": l, "name": nm, "hex": [x, y],
            "offmap": (x == 65535),
            "hq": hq,
            "commander_id": lid,
            "commander": witp_obj.get(pid, "leader", lid, "name") if lid else None,
            "prep": witp_obj.get(pid, "location", l, "prep"),
            "prepTarget": witp_obj.get(pid, "location", l, "prepTarget"),
            "combatMode": witp_obj.get(pid, "location", l, "combatMode"),
            "operationsMode": witp_obj.get(pid, "location", l, "operationsMode"),
            "portExpand": witp_obj.get(pid, "location", l, "portExpand"),
            "airfieldExpand": witp_obj.get(pid, "location", l, "airfieldExpand"),
            "fortExpand": witp_obj.get(pid, "location", l, "fortExpand"),
            "cmdLevel": d[LOC_EXTRA["cmdLevel"][0]],
            "portSize": d[LOC_EXTRA["portSize"][0]],
        })
        if len(out) >= limit:
            break
    return out


def read_ships(pid, limit=400):
    out = []
    for i in range(1, 20000):
        nm = witp_obj.get(pid, "ship", i, "name")
        if not nm:
            continue
        loc = witp_obj.get(pid, "ship", i, "locationID")
        out.append({
            "ship": i, "name": nm,
            "locationID": loc,
            "tf": (loc - 14000) if loc and loc >= 14000 else None,
            "endurance": witp_obj.get(pid, "ship", i, "endurance"),
            "sys": witp_obj.get(pid, "ship", i, "sysDamage") or 0,
            "flt": witp_obj.get(pid, "ship", i, "fltDamage") or 0,
            "eng": witp_obj.get(pid, "ship", i, "engDamage") or 0,
            "fire": witp_obj.get(pid, "ship", i, "fireDamage") or 0,
            "repairPriority": witp_obj.get(pid, "ship", i, "repairPriority"),
            "repairMode": witp_obj.get(pid, "ship", i, "repairMode"),
            "leaderID": witp_obj.get(pid, "ship", i, "leaderID"),
        })
        if len(out) >= limit:
            break
    return out


def read_pilots(pid, limit=200):
    out = []
    for i in range(1, 20000):
        pidv = witp_obj.get(pid, "pilot", i, "id")
        if not pidv:
            continue
        out.append({
            "pilot": i, "id": pidv,
            "status": witp_obj.get(pid, "pilot", i, "status"),
            "exp": witp_obj.get(pid, "pilot", i, "exp"),
            "skillA": [witp_obj.get(pid, "pilot", i, "read160"),
                        witp_obj.get(pid, "pilot", i, "read185")],
        })
        if len(out) >= limit:
            break
    return out


def _unpack(record: bytes, offset: int, kind: str) -> int:
    return struct.unpack_from(SCALAR[kind], record, offset)[0]


def _scenario_record(save_path=None):
    """Load the compact scenario payload selected by the game's current save."""
    try:
        import pwsfile
        save_path = _resolve_save(save_path)
        c = pwsfile.read_container(save_path)
        return next(r["data"] for r in c["records"]
                    if r["u_len"] == 99696 and (r["id"] & 0xFF) == 1)
    except Exception:
        return None


def economy_report(save_path=None):
    """Read per-location stocks and daily production values from a PWS save."""
    try:
        import pwsfile
        save_path = _resolve_save(save_path)
        blk = pwsfile.record_by_len(save_path, 21096000)
    except Exception as exc:
        return {"ok": False, "error": f"读取 Location 存档记录失败：{exc}"}
    rows = []
    facility_array = []
    for loc in range(1, len(blk) // 1172):
        raw = blk[loc * 1172:(loc + 1) * 1172]
        name_bytes = raw[:25].split(bytes([0]), 1)[0]
        if not name_bytes:
            continue
        x, y = struct.unpack_from("<HH", raw, 36)
        loc_type = _unpack(raw, 28, "u16")
        # Base records are valid off-map entries; at-base ground/TF/HQ records
        # share the same structure but are not economic locations.
        if loc_type != 1 or loc == 0:
            continue
        name = name_bytes.decode("ascii", "replace")
        row = {"loc": loc, "name": name, "hex": [x, y]}
        for key, (off, kind) in LOC_ECON_FIELDS.items():
            row[key] = _unpack(raw, off, kind)
        row["deviceID"] = list(struct.unpack_from("<20H", raw, 136))
        row["deviceNumber"] = list(struct.unpack_from("<20H", raw, 176))
        row["deviceDis"] = list(struct.unpack_from("<20H", raw, 216))
        # Industry device arrays are present on bases; do not count ground-unit
        # equipment records (the same PWSLocation structure is reused there).
        industry_indices = [j for j, did in enumerate(row["deviceID"]) if did in INDUSTRY_DEVICE_IDS]
        for label in INDUSTRY_DEVICE_IDS.values():
            row[label] = 0
            row[label + "_damaged"] = 0
        stock_resources = row["resources"]
        stock_oil = row["oil"]
        stock_fuel = row["fuel"]
        stock_supply = row["supply"]
        for j in industry_indices:
            label = INDUSTRY_DEVICE_IDS[row["deviceID"][j]]
            if label not in ("resourceCenters", "manpowerCenters"):
                row[label] += row["deviceNumber"][j]
                row[label + "_damaged"] += row["deviceDis"][j]
        row.update(resources=stock_resources, oil=stock_oil, fuel=stock_fuel, supply=stock_supply)
        row["resourceCenters"] = sum(struct.unpack_from("<H", raw, 176 + 2*j)[0] for j in range(20) if struct.unpack_from("<H", raw, 136 + 2*j)[0] == 519)
        row["manpowerCenters"] = sum(struct.unpack_from("<H", raw, 176 + 2*j)[0] for j in range(20) if struct.unpack_from("<H", raw, 136 + 2*j)[0] == 520)
        row["oilCenters"] = sum(struct.unpack_from("<H", raw, 176 + 2*j)[0] for j in range(20) if struct.unpack_from("<H", raw, 136 + 2*j)[0] == 518)
        row["resourceCenters_damaged"] = sum(row["deviceDis"][j] for j in range(20) if row["deviceID"][j] == 519)
        row["manpowerCenters_damaged"] = sum(row["deviceDis"][j] for j in range(20) if row["deviceID"][j] == 520)
        row["oilCenters_damaged"] = sum(row["deviceDis"][j] for j in range(20) if row["deviceID"][j] == 518)
        rows.append(row)
    totals = {k: sum(r[k] for r in rows) for k in
              ("resources", "oil", "fuel", "supply")}
    # Keep stock totals separate from industry facility counts and avoid
    # accidentally reusing keys named "resources" for Resource Center counts.
    facility_totals = {k: sum(r[k] for r in rows) for k in ("resourceCenters", "manpowerCenters", "oilCenters")}
    facility_damage = {k: sum(r[k + "_damaged"] for r in rows) for k in facility_totals}
    industry = {label: 0 for label in INDUSTRY_DEVICE_IDS.values() if label not in ("oilCenters",)}
    damaged_industry = {label: 0 for label in industry}
    for row in rows:
        for label in industry:
            industry[label] += row[label]
            damaged_industry[label] += row[label + "_damaged"]
    return {"ok": True, "save": str(save_path), "count": len(rows),
            "totals": totals, "facility_totals": facility_totals,
            "facility_damaged": facility_damage,
            "industry": industry, "industry_damaged": damaged_industry,
            "locations": rows,
            "note": "库存与设施读自存档 PWSLocation；行业类别 ID 按游戏 Device 名称表映射。飞机工厂/引擎工厂、R&D、生产/增援池和到达日程不由本报告覆盖。"}


def _classify_ship_delay(delay):
    """Ship shipDelay@36 semantics, verified across wpae001(t1)/wpae002(t4)/wpae000(t5)."""
    if delay == 0:
        return "in_service"
    if delay == 19999:
        return "sunk"
    if 0 < delay < 1000:
        return "arriving"
    return "other"


def _classify_ag_delay(delay, base_id, reinf_base):
    """AirGroup delay@220 semantics, verified against baseID/reinforceBaseID distribution."""
    if delay == 0:
        return "on_map" if base_id else "active_no_base"
    if delay == 19999:
        return "withdrawn"
    if 0 < delay < 1000:
        return "arriving"
    if delay == 9999:
        # 2039 rows have neither base nor reinforcement base -> no scheduled arrival
        return "unplanned_reserve" if not reinf_base else "scheduled_reserve_no_base"
    return "other"


def _classify_loc_delay(delay, xy, troop_devices):
    """Location delay@564 semantics for non-base units."""
    if delay == 0:
        return "on_map" if xy not in ((0, 0), (65535, 65535)) else "active_offmap"
    if delay == 29999:
        return "not_formed" if not troop_devices else "not_formed_has_devices"
    if delay == 9999:
        return "unplanned_reserve"
    if 0 < delay < 1000:
        return "arriving"
    return "other"


def reinforcement_report(save_path):
    """Reinforcement / withdrawal status from ship, airgroup and Location records.

    Field semantics below were verified against three saves of the same scenario
    (wpae001 turn 1, wpae002 turn 4, wpae000 turn 5):
      · ship.shipDelay@36 counts DOWN one per day for arriving ships
        (S-39: 6 @t1 -> 3 @t4 -> 2 @t5), 0 = in service, 19999 = sunk
        (all 15 ships with 19999 also carry a sunk Y/M/D, 0 exceptions).
      · airgroup.delay@220: 0 = on map, 1..999 = arrivals (VF-5 = 14 with
        reinforceBase 21004), 19999 = withdrawn, 9999 = reserve with no
        scheduled arrival.
      · location.delay@564: 0 = on map, 9999 = off-map reserve,
        29999 = not yet formed (no troop devices).
    Raw values are also returned; no calendar conversion is inferred.
    """
    try:
        import pwsfile
        c = pwsfile.read_container(save_path)
        by_len = {r["u_len"]: r["data"] for r in c["records"]}
        ships = by_len[9280000]
        airgroups = by_len[20400680]
        locations = by_len[21096000]
        scen = by_len[99696]
        turn = struct.unpack_from("<H", scen, 30)[0]
    except Exception as exc:
        return {"ok": False, "error": f"读取增援字段记录失败：{exc}"}

    location_names = {}
    for i in range(len(locations) // 1172):
        r = locations[i * 1172:(i + 1) * 1172]
        name = r[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if name:
            location_names[i] = name

    def loc_label(lid):
        if not lid:
            return None
        if lid >= 14000:
            return f"TF{lid - 14000}"
        return location_names.get(lid)

    ship_rows = []
    for i in range(len(ships) // 464):
        r = ships[i * 464:(i + 1) * 464]
        name = r[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if not name:
            continue
        delay = struct.unpack_from("<i", r, 36)[0]
        port = struct.unpack_from("<H", r, 40)[0]
        withdrawal = struct.unpack_from("<i", r, 44)[0]
        ret = struct.unpack_from("<i", r, 48)[0]
        status = _classify_ship_delay(delay)
        sunk = [r[358], r[359], r[360]]
        # Report every named ship; status carries the classification.
        ship_rows.append({
            "slot": i, "name": name,
            "status": status,
            "delay_raw": delay,
            "days_until_arrival": delay if status == "arriving" else None,
            "arrival_location_id": port,
            "arrival_location_name": loc_label(port),
            "withdrawal_raw": withdrawal,
            "return_raw": ret,
            "sunk_date": sunk if any(sunk) else None,
        })

    ag_rows = []
    for i in range(len(airgroups) // 680):
        r = airgroups[i * 680:(i + 1) * 680]
        name = r[:26].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if not name:
            continue
        delay = struct.unpack_from("<i", r, 220)[0]
        reinf = r[224]
        withdrawal = struct.unpack_from("<i", r, 392)[0]
        delay2 = struct.unpack_from("<i", r, 396)[0]
        base_id = struct.unpack_from("<H", r, 40)[0]
        reinf_base = struct.unpack_from("<H", r, 42)[0]
        status = _classify_ag_delay(delay, base_id, reinf_base)
        ag_rows.append({
            "slot": i, "name": name,
            "status": status,
            "delay_raw": delay,
            "days_until_arrival": delay if status == "arriving" else None,
            "delay_reinforcement_flag_raw": reinf,
            "withdrawal_date_yymmdd": withdrawal or None,
            "delay2_raw": delay2,
            "base_id": base_id, "base_name": loc_label(base_id),
            "reinforcement_base_id": reinf_base,
            "reinforcement_base_name": loc_label(reinf_base),
        })

    loc_rows = []
    for i in range(len(locations) // 1172):
        r = locations[i * 1172:(i + 1) * 1172]
        name = r[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if not name:
            continue
        typ = struct.unpack_from("<H", r, 28)[0]
        if typ in (0, 1, 4, 5, 12):
            continue
        delay = struct.unpack_from("<i", r, 564)[0]
        arrival = struct.unpack_from("<H", r, 42)[0]
        withdrawal = struct.unpack_from("<H", r, 908)[0]
        xy = struct.unpack_from("<HH", r, 36)
        ids = struct.unpack_from("<20H", r, 136)
        nums = struct.unpack_from("<20H", r, 176)
        troop_devices = sum(nums[j] for j in range(20) if 0 < ids[j] < 500)
        status = _classify_loc_delay(delay, xy, troop_devices)
        loc_rows.append({
            "slot": i, "name": name,
            "location_type": typ,
            "status": status,
            "delay_raw": delay,
            "days_until_arrival": delay if status == "arriving" else None,
            "arrival_location_id": arrival,
            "arrival_location_name": loc_label(arrival),
            "withdrawal_code_raw": withdrawal or None,
            "hex": list(xy),
            "troop_device_count": troop_devices,
        })

    def tally(rows):
        out = {}
        for row in rows:
            out[row["status"]] = out.get(row["status"], 0) + 1
        return out

    arriving_ships = [r for r in ship_rows if r["status"] == "arriving"]
    arriving_ags = [r for r in ag_rows if r["status"] == "arriving"]

    # ★日历换算：delay = 距到达的天数（跨 3 存档实测每日递减），
    #   到达日期 = 存档头日期 + delay 天。哨兵值（9999/19999/29999）不换算。
    import datetime as _dt, re as _re
    def _game_date():
        try:
            import witp_core as _wc
            h = _wc.load(str(save_path)).header
            m = _re.search(r"(\d{2})/(\d{2})/(\d{2})", h)
            if m:
                mm, dd, yy = (int(x) for x in m.groups())
                return _dt.date(1900 + yy, mm, dd)
        except Exception:
            pass
        return None
    gd = _game_date()
    def _eta(days):
        if gd and isinstance(days, int) and 0 < days < 900:
            return str(gd + _dt.timedelta(days=days))
        return None
    for r in arriving_ships + arriving_ags:
        r["eta_date"] = _eta(r["days_until_arrival"])

    return {
        "ok": True, "save": str(save_path), "turn": turn,
        "game_date": str(gd) if gd else None,
        "arriving_ships": sorted(arriving_ships, key=lambda x: x["days_until_arrival"]),
        "arriving_airgroups": sorted(arriving_ags, key=lambda x: x["days_until_arrival"]),
        "ships": ship_rows, "airgroups": ag_rows, "ground_units": loc_rows,
        "counts": {
            "ships": len(ship_rows), "airgroups": len(ag_rows),
            "location_units": len(loc_rows),
            "ships_arriving": len(arriving_ships),
            "airgroups_arriving": len(arriving_ags),
        },
        "status_totals": {
            "ships": tally(ship_rows),
            "airgroups": tally(ag_rows),
            "ground_units": tally(loc_rows),
        },
        "field_notes": {
            "ship": "shipDelay@36 i32 (countdown / 0 in service / 19999 sunk), "
                    "shipArrivalPort@40 u16 Location ID, shipWithdrawal@44 i32, shipReturn@48 i32",
            "airgroup": "delay@220 i32, delayReinforcement@224 u8, withdraw@392 i32 YYMMDD, delay2@396 i32",
            "location": "arrive@42 u16 Location ID (not a date), delay@564 i32, withdrawal@908 u16 code",
            "verified_over": "wpae001 t1 / wpae002 t4 / wpae000 t5 (same scenario)",
        },
    }


def production_report(save_path):
    """Aircraft / engine factory status read from base Location records.

    Verified on wpae000.pws:
      · base deviceID >= 2000 encodes an aircraft factory for aircraft (id - 2000);
        the aircraft list index offsets line up exactly (e.g. 2762 -> Ki-43-IIa Oscar,
        2487 -> SBD-3 Dauntless). 1402 live factory points across 53 aircraft types.
      · device type 27 marks engine factories; Tokyo holds Hitachi Amakaze 180,
        Hitachi (early) 120, Kawasaki Ha-60 20, Mitsubishi Ha-33 10 => 1405 total.
      · deviceNumber@176 is the live factory size; deviceDis@216 the damaged part.
    """
    try:
        import pwsfile
        c = pwsfile.read_container(save_path)
        by_len = {r["u_len"]: r["data"] for r in c["records"]}
        loc = by_len[21096000]
        dev = by_len[472000]
        air = by_len[396000]
    except Exception as exc:
        return {"ok": False, "error": f"读取生产记录失败：{exc}"}

    def dev_at(i, size, blob):
        if not (0 <= i < len(blob) // size):
            return ""
        return blob[i * size:i * size + 25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()

    def aircraft_meta(idx):
        if not (0 <= idx < len(air) // 396):
            return {}
        r = air[idx * 396:(idx + 1) * 396]
        return {
            "build_rate": struct.unpack_from("<H", r, 188)[0],
            "upgrade_to": struct.unpack_from("<H", r, 192)[0],
            "off194": struct.unpack_from("<H", r, 194)[0],  # 语义未确证（非研发进度）
            "available": [r[184], r[185]],
        }

    bases = []
    ac_by_type = {}
    eng_by_type = {}
    for b in range(len(loc) // 1172):
        r = loc[b * 1172:(b + 1) * 1172]
        if struct.unpack_from("<H", r, 28)[0] != 1:
            continue
        name = r[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if not name:
            continue
        ids = struct.unpack_from("<20H", r, 136)
        nums = struct.unpack_from("<20H", r, 176)
        dis = struct.unpack_from("<20H", r, 216)
        ac, eng = [], []
        for j in range(20):
            did, num, dmg = ids[j], nums[j], dis[j]
            if not did or not (num or dmg):
                continue
            if did >= 2000:
                idx = did - 2000
                ac_name = dev_at(idx, 396, air) or f"aircraft#{idx}"
                ac.append({"device_id": did, "aircraft_index": idx, "aircraft": ac_name,
                           "factories": num, "damaged": dmg, **aircraft_meta(idx)})
                t = ac_by_type.setdefault(ac_name, {"factories": 0, "damaged": 0, "bases": []})
                t["factories"] += num
                t["damaged"] += dmg
                t["bases"].append(name)
            elif struct.unpack_from("<H", dev, did * 236 + 26)[0] == 27:
                eng_name = dev_at(did, 236, dev) or f"engine#{did}"
                eng.append({"device_id": did, "engine": eng_name,
                            "factories": num, "damaged": dmg})
                t = eng_by_type.setdefault(eng_name, {"factories": 0, "damaged": 0, "bases": []})
                t["factories"] += num
                t["damaged"] += dmg
                t["bases"].append(name)
        if ac or eng:
            bases.append({"slot": b, "name": name, "hex": list(struct.unpack_from("<HH", r, 36)),
                          "aircraft_factories": ac, "engine_factories": eng})

    research_types = []
    for i in range(len(air) // 396):
        r = air[i * 396:(i + 1) * 396]
        nm = r[:25].split(bytes([0]), 1)[0].decode("latin1", "replace").strip()
        if not nm:
            continue
        rs = struct.unpack_from("<H", r, 194)[0]
        br = struct.unpack_from("<H", r, 188)[0]
        if rs or br:
            research_types.append({"aircraft_index": i, "aircraft": nm,
                                   "build_rate": br, "off194": rs,
                                   "available": [r[184], r[185]]})

    return {
        "ok": True, "save": str(save_path),
        "bases_with_factories": bases,
        "aircraft_factory_totals": ac_by_type,
        "engine_factory_totals": eng_by_type,
        "aircraft_types_with_rate_or_research": research_types,
        "totals": {
            "aircraft_factories": sum(v["factories"] for v in ac_by_type.values()),
            "aircraft_factories_damaged": sum(v["damaged"] for v in ac_by_type.values()),
            "engine_factories": sum(v["factories"] for v in eng_by_type.values()),
            "bases_with_factories": len(bases),
        },
        "field_notes": {
            "aircraft_factory": "base deviceID>=2000 -> aircraft index (id-2000); "
                                "deviceNumber@176 live size, deviceDis@216 damaged",
            "engine_factory": "device record type@26 == 27; same count/damage arrays",
            "aircraft_static": "CSV 231/231 验证：type@25, alt@28, speed@30/32, climb@34, "
                               "maneuver@36, armour@40, durability@41, maxLoad@182, "
                               "avail M/Y@184-185, buildRate@188, upgradeTo@192, svcRating@229",
            "not_covered": "工厂转换/扩建写入命令未定位。船舶建造与研发为引擎自动行为"
                           "（本剧本无在研机型时 off194 全 0，无进度可读）；"
                           "舰船到港倒计时见 reinforcement_report 的 ship.reinforcementDelay@36",
        },
    }



def _resolve_save(save_path=None):
    if save_path is None:
        from pathlib import Path
        root = os.environ.get("WITP_INSTANCE", "").strip()
        if not root:
            root = "/root/.wine-witp/drive_c/1108r9"
        root = Path(root)
        if root.name.upper() == "SAVE":
            save_path = root / "wpae000.pws"
        else:
            save_path = root / "War in the Pacific Admiral's Edition" / "SAVE" / "wpae000.pws"
    return save_path


WEATHER_LEVELS = ("clear", "partly cloudy", "overcast", "rain", "thunderstorms")
MAP_W, MAP_H = 230, 197  # WITPloc003.csv 坐标范围推断（0..229 / 0..196）


def weather_report(save_path=None):
    """ch12.1 天气预报：9 象限 × 5 档（存档 u_len=9 记录）。

    证据链：
    - 该记录 3 存档逐日变化（05/04: [3,0,0,1,2,0,0,0,0] → 05/11: [2,2,3,0,2,3,0,2,4]）
    - ground truth: :97 菜单栏 'Forecast: Overcast'(=2) @ hex(115,160) Noumea
      → row-major 象限 idx7 = 2 ✓（col-major 映射不吻合，已排除）
    档位排序按手册 ch12.1：clear < partly cloudy < overcast < rain < thunderstorms。
    """
    import pwsfile
    sp = _resolve_save(save_path)
    c = pwsfile.read_container(str(sp))
    rec = next((r["data"] for r in c["records"] if r["u_len"] == 9), None)
    if rec is None or len(rec) != 9:
        return {"ok": False, "error": "u_len=9 天气记录不存在或长度异常"}
    quads = list(rec)

    def hex_quadrant(x, y):
        qx = min(int(x) * 3 // MAP_W, 2)
        qy = min(int(y) * 3 // MAP_H, 2)
        return qy * 3 + qx

    return {"ok": True, "save": str(sp),
            "levels": list(WEATHER_LEVELS),
            "quadrants": [{"index": i,
                           "level": v,
                           "level_name": WEATHER_LEVELS[v] if v < len(WEATHER_LEVELS) else f"?{v}"}
                          for i, v in enumerate(quads)],
            "hex_to_quadrant": f"row-major: (y*3//{MAP_H})*3 + (x*3//{MAP_W})",
            "ground_truth": "Forecast:Overcast(2) @hex(115,160) -> idx7=2 ✓ (:97 截图 05/11)",
            "note": "单点验证；象限边界（地图 3×3 均分）未逐点核验"}


def base_vp_report(save_path=None, limit=40):
    """ch17.0 基地 VP 终局计分：Basic VP × (port + airfield*2)。

    Basic VP 取 SCEN/WITPloc003.csv 的 Jvictory/Avictory 列（静态），
    port/airfield 取存档 LOC 的当前规模（off420/422），
    补给折减：手册只给端点（满补给=100%、0 补给=25%），中间按线性插值【假设】。
    仅控制方得分（owner: 0=日本 1=盟军）。
    """
    import pwsfile, csv
    from pathlib import Path
    sp = Path(_resolve_save(save_path))
    blk = pwsfile.record_by_len(str(sp), 21096000)
    scen_csv = sp.parent.parent / "SCEN" / "WITPloc003.csv"
    vp = {}
    with open(scen_csv, encoding="latin1") as f:
        for row in csv.DictReader(f):
            try:
                vp[int(row["UnitNumber"])] = (int(row["Jvictory"] or 0),
                                              int(row["Avictory"] or 0))
            except Exception:
                continue
    rows = []
    for i in range(len(blk) // 1172):
        r = blk[i * 1172:(i + 1) * 1172]
        name = r[:25].split(b"\0", 1)[0].decode("latin1", "replace").strip()
        if not name:
            continue
        jv, av = vp.get(i, (0, 0))
        if not (jv or av):
            continue
        owner = struct.unpack_from("<H", r, 26)[0]
        port = struct.unpack_from("<H", r, 420)[0]
        air = struct.unpack_from("<H", r, 422)[0]
        supply = struct.unpack_from("<i", r, 536)[0]
        need = struct.unpack_from("<i", r, 540)[0]
        mult = port + air * 2
        ratio = 1.0
        if need > 0 and supply < need:
            ratio = max(0.25, supply / need)
        side = "JAPAN" if owner == 0 else ("ALLIED" if owner == 1 else f"?{owner}")
        basic = jv if owner == 0 else av
        rows.append({"loc": i, "name": name, "owner": side,
                     "basic_vp": basic, "port": port, "airfield": air,
                     "supply": supply, "supply_needed": need,
                     "supply_factor": round(ratio, 3),
                     "final_vp_if_held_to_end": int(round(basic * mult * ratio))})
    rows.sort(key=lambda x: -x["final_vp_if_held_to_end"])
    total_j = sum(x["final_vp_if_held_to_end"] for x in rows if x["owner"] == "JAPAN")
    total_a = sum(x["final_vp_if_held_to_end"] for x in rows if x["owner"] == "ALLIED")
    return {"ok": True, "save": str(sp),
            "count": len(rows),
            "totals_if_nothing_changes": {"japan": total_j, "allied": total_a},
            "formula": "Basic VP × (port + airfield*2)，补给<需求按 25%..100% 线性折减（端点出自手册，中间为假设）",
            "top": rows[:limit],
            "note": "中盘比值≠终局比值：基地 VP 终局才结算（ch17.0）"}


def victory_report(save_path=None):

    """Read dynamic campaign VP and turn from the current compact SCENARIO record."""
    data = _scenario_record(save_path)
    if data is None:
        return {"ok": False, "error": "无法读取当前存档的 SCENARIO 记录"}
    return {"ok": True, "turn": _unpack(data, 30, "u16"),
            "japan_vp": _unpack(data, 112, "i32"),
            "allied_vp": _unpack(data, 120, "i32"),
            "source": "SCENARIO record; offsets verified against witp_core.GameState.vp"}


def victory_forecast(save_path=None):
    """手册 ch17 胜利判定推演：当前胜负等级 + 自动胜利门槛（派生工具，非内存字段）。

    判据全部来自手册 ch17.1 / 17.2（已入知识库 17-victory-conditions.md）：
      - 胜利等级（比值 = 大分/小分）: >=1.75 决定性 / >=1.25 边缘 / 否则平局
      - 自动胜利（须已进行 365 天）: 1943=4×, 1944=3×, 1945 及以后=2×；
        达成方获决定性胜利，但 1945-08-31 后达成仅边缘胜利（17.2）
      - 1946 到时结束 → 等级向日方移 2 级（17.1.1）；≥3 枚原子弹再移 1 级（17.1.2）
    注：当前 VP 只计已击毁单位；基地 VP 在剧本终局结算（ch17.0），
    故中盘比值 ≠ 终局比值。原子弹数读不到，相关调整仅列出不判定。
    """
    import datetime as _dt, re as _re
    base = victory_report(save_path)
    if not base.get("ok"):
        return base
    jp, al = base["japan_vp"], base["allied_vp"]

    game_date = None
    try:
        import witp_core as _wc
        h = _wc.load(str(_resolve_save(save_path))).header
        m = _re.search(r"(\d{2})/(\d{2})/(\d{2})", h)
        if m:
            mm, dd, yy = (int(x) for x in m.groups())
            game_date = _dt.date(1900 + yy, mm, dd)
    except Exception:
        pass

    def _level(a, b):
        """(leader, level) 按比值；a、b 为两方 VP。"""
        if a == b:
            return "DRAW", "draw"
        hi, lo = max(a, b), min(a, b)
        r = hi / lo if lo else float("inf")
        leader = "ALLIED" if a > b else "JAPAN"
        if r >= 1.75:
            return leader, "decisive"
        if r >= 1.25:
            return leader, "marginal"
        return "DRAW", "draw"

    leader, level = _level(al, jp)
    ratio = (max(al, jp) / min(al, jp)) if min(al, jp) else float("inf")

    year = game_date.year if game_date else None
    mult_by_year = {1943: 4, 1944: 3, 1945: 2, 1946: 2}
    mult = mult_by_year.get(year) if year else None
    auto = {
        "active_year_multiplier": mult,
        "note": "手册 17.2：须已进行 365 天；1942 年不触发自动胜利",
        "allied_auto_victory_if_allied_vp_ge": (jp * mult) if mult else None,
        "japan_auto_victory_if_japan_vp_ge": (al * mult) if mult else None,
    }

    return {"ok": True, "turn": base["turn"],
            "game_date": str(game_date) if game_date else None,
            "japan_vp": jp, "allied_vp": al,
            "ratio_big_over_small": round(ratio, 3),
            "leader": leader, "current_level": level,
            "auto_victory": auto,
            "endgame_adjustments": [
                "1946 到时结束：等级向日方移 2 级（17.1.1）",
                "盟军使用 >=3 枚原子弹：等级向日方移 1 级（17.1.2，原子弹数本读层暂无来源）",
            ],
            "source": "手册 ch17 公式 + SCENARIO 记录 VP（offsets 已验证）"}



def full_report():
    pid = _pid()
    if not pid:
        return {"ok": False, "error": "游戏未运行"}
    tfs = read_tfs(pid)
    ags = read_ags(pid)
    bases = read_bases(pid)
    ships = read_ships(pid)
    pilots = read_pilots(pid)
    damaged = [s for s in ships if (s["sys"] + s["flt"] + s["eng"] + s["fire"]) > 0]
    damaged.sort(key=lambda s: -(s["sys"] + s["flt"] + s["eng"] + s["fire"]))
    return {
        "ok": True,
        "pid": pid,
        "summary": {
            "tfs": len(tfs),
            "airgroups": len(ags),
            "bases": len(bases),
            "ships": len(ships),
            "pilots": len(pilots),
            "damaged_ships": len(damaged),
        },
        "taskforces": tfs,
        "airgroups": ags,
        "bases": bases,
        "ships": ships,
        "pilots": pilots,
        "damaged": damaged,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(full_report(), ensure_ascii=False, indent=1))


def ships_by_tf():
    """舰船按所属 TF / 基地分组（手册 5.2.4 LIST ALL ACTIVE SHIPS）。"""
    pid = _pid()
    groups = {}
    for i in range(1, 20000):
        loc = witp_obj.get(pid, "ship", i, "locationID")
        if not loc:
            continue
        nm = witp_obj.get(pid, "ship", i, "name")
        key = ("TF%d" % (loc - 14000)) if loc >= 14000 else ("BASE%d" % loc)
        groups.setdefault(key, []).append({
            "ship": i, "name": nm,
            "endurance": witp_obj.get(pid, "ship", i, "endurance"),
            "sys": witp_obj.get(pid, "ship", i, "sysDamage") or 0,
            "flt": witp_obj.get(pid, "ship", i, "fltDamage") or 0,
            "eng": witp_obj.get(pid, "ship", i, "engDamage") or 0,
            "fire": witp_obj.get(pid, "ship", i, "fireDamage") or 0,
            "leaderID": witp_obj.get(pid, "ship", i, "leaderID"),
        })
    return groups


def detection_levels():
    """列出 off135 非零的 Location（★2026-10-21 复核：这不是手册 10.1.1 的侦测等级）。

    实测：off135 全图只有 10 个非零，且全部是顶级司令部（type=4：
    Kwantung/5th Fleet/US Pacific Fleet/South Pacific/ABDA 等），值域 1..5
    —— 这是**司令部层级候选**，不是全图敌情侦测度。
    手册 10.1.1 的 Detection Level（0..5，按情报屏）数据源仍未定位，
    疑存于独立数组（2608000/760960 等未识别记录候选），本函数保留只读原样输出。
    """
    pid = _pid()
    out = []
    for l in range(1, 14000):
        d = witp_obj._read(pid, 0x4570c50 + l * 1172, 140)
        if not d:
            continue
        dl = d[135]
        if not dl:
            continue
        nm = d[0:24].split(bytes([0]))[0].decode("ascii", "replace")
        x, y = struct.unpack_from("<HH", d, 36)
        out.append({
            "loc": l, "name": nm, "hex": [x, y],
            "off135": dl,
            "owner_base": struct.unpack_from("<H", d, 134)[0],
            "interpretation": "仅司令部非零 → off135 疑为 HQ 层级，非 ch10.1.1 侦测等级；DL 数据源仍未定位",
        })
    return out


def offmap_areas():
    """列出全部离图区（Off-Map Area）。"""
    pid = _pid()
    out = []
    for l in range(1, 400):
        x = witp_obj.get(pid, "location", l, "X")
        y = witp_obj.get(pid, "location", l, "Y")
        if x == 65535 and y == 65535:
            d = witp_obj._read(pid, 0x4570c50 + l * 1172, 140)
            nm = d[0:24].split(bytes([0]))[0].decode("ascii", "replace") if d else ""
            out.append({
                "loc": l, "name": nm,
                "cmdLevel": d[124] if d else 0,
                "hq": witp_obj.get(pid, "location", l, "attachedHQ"),
            })
    return out
