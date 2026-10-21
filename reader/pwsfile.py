#!/usr/bin/env python3
"""pwsfile.py — WitP-AE .pws 存档容器逆向解析器（纯 Python，无需游戏 DLL）

逆向结论（2026-10-17 实测，基于本机英文 1108r9 存档 wpae000.pws）：

1) 外层容器
   .pws 文件本身是 **gzip 流**（魔数 1f 8b 08），解压后得到「记录串」。
2) 记录串
   每条记录 = 12 字节记录头 + 一条 **zlib 流**（78 01/9c/da 开头，独立 deflate 块）。
   记录头 = 3 个小端 u32：
       [0] rec_id   —— 低 8 位是 RecType（1=SCENARIO 8=SHIP 19=LOCATION 20=AIRGROUP
                       21=LEADER 22=PILOT 31=DEVICE 32=AIRCRAFT 38=HEADER…），
                       高位是版本/标志（实测 SCENARIO=0x10201，SHIP=0x10208 …）
       [1] unknown  —— 非 CRC32/非 Adler32、非压缩长度（已逐一证伪），疑似按记录生成的
                       校验/密钥字段；读取时无需它，遍历靠 zlib 流的 unused_data 边界。
       [2] unknown  —— 同上；仅 id<=1000 的短记录里恰好等于 12（压缩块长），不可依赖。
3) 记录体
   解压后长度与游戏 DLL 中的 ctypes 结构体**完全对齐**（实测）：
       99696   = PWSScenInfo   (65804? 否 → 见下注)      → 实为场景块，含剧本名
       9280000 = PWSShipInfo   (PWSShip 464 × 20000)
       9000000 = PWSLeaderInfo / PWSPilotInfo (180 × 50000)
       20400680= PWSAirGroupInfo(PWSAirGroup 680 × 30001 定长区)
       21096000= PWSLocationInfo(PWSLocation 1172 × 18000)
       396000  = PWSAircraftInfo(PWSAircraft 396 × 1000)
       472000  = PWSDeviceInfo (236 × 2000)
       2224000 = PWSTaskGroupInfo(556 × 4000)
       1900000 = PWSShipClassInfo(380 × 5000)
   即：**存档 = 定长结构体数组的 zlib 打包**，字段偏移可直接用 pwsdll.py 里的
   ctypes 定义推算，因此“订单字段”（TF 任务/目的地、航空队任务/巡逻比例）在文件里
   有确定地址，可被程序化读写。

用法：
    python3 pwsfile.py <save.pws>                 # 打印记录表
    python3 pwsfile.py <save.pws> --tf            # 打印编队任务/旗舰/母港
    python3 pwsfile.py <save.pws> --dump <id> <out.bin>   # 导出某类记录原始块
"""
import argparse
import gzip
import struct
import sys
import zlib
from pathlib import Path

REC_TYPE = {
    1: "SCENARIO", 8: "SHIP", 19: "LOCATION", 20: "AIRGROUP", 21: "LEADER",
    22: "PILOT", 27: "SHIPCLASS", 30: "MINES", 31: "DEVICE", 32: "AIRCRAFT",
    38: "HEADER",
}

# 记录体长度 → 结构体名（与 pwsdll.py ctypes 尺寸实测一致）
BLOCK_BY_LEN = {
    3000: "HEADER(PWSHeader 1800? 实测 3000)",
    99696: "SCENARIO-BLOCK",
    9280000: "SHIPS(PWSShip 464×20000)",
    9000000: "LEADERS/PILOTS(180×50000)",
    20400680: "AIRGROUPS(PWSAirGroup 680×…)",
    21096000: "LOCATIONS(PWSLocation 1172×…)",
    396000: "AIRCRAFT(396×1000)",
    472000: "DEVICES(236×2000)",
    2224000: "TASKFORCES(PWSTaskGroup 556×4000)",
    1900000: "SHIPCLASSES(380×5000)",
    15200000: "MISC-15.2M",
    360000: "MISC-360K",
    2608000: "MISC-2.6M",
    760960: "MISC-760K",
    190240: "MISC-190K",
    127872: "MISC-128K",
    95120: "MISC-95K",
}


def read_container(path):
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        body = gzip.decompress(raw)
        wrapped = "gzip"
    else:
        body = raw
        wrapped = "raw"
    recs = []
    off = 0
    while off + 12 <= len(body):
        rid, f2, f3 = struct.unpack_from("<III", body, off)
        z = off + 12
        # zlib 头首字节随 windowBits 变化（wb=15→0x78，14→0x68，…，9→0x18），
        # 因此不能只认 0x78；用「CMF 低 4 位=8 且 (CMF<<8|FLG)%31==0」判定合法 zlib 头。
        def is_zlib_hdr(i):
            if i + 1 >= len(body):
                return False
            cmf, flg = body[i], body[i + 1]
            return (cmf & 0x0F) == 8 and ((cmf << 8) | flg) % 31 == 0
        if not is_zlib_hdr(z):
            cand = [i for i in range(z, min(z + 64, len(body))) if is_zlib_hdr(i)]
            if not cand:
                break
            z = cand[0]
        dobj = zlib.decompressobj()
        try:
            out = dobj.decompress(body[z:]) + dobj.flush()
        except zlib.error:
            break
        used = len(body[z:]) - len(dobj.unused_data)
        recs.append({
            "file_off": off, "id": rid, "type": rid & 0xFF,
            "type_name": REC_TYPE.get(rid & 0xFF, "?"),
            "f2": f2, "f3": f3, "hdr_len": z - off,
            "extra": body[off + 12:z],   # 少量记录在 12B 头与 zlib 之间还有不透明字节（实测 id=0x110xxx）
            "z_len": used, "u_len": len(out), "data": out,
            "comp": body[z:z + used],    # 原始压缩流（数据未改动时原样复用，保证字节级一致）
        })
        off = z + used
    return {"wrapped": wrapped, "raw_len": len(raw), "body_len": len(body),
            "consumed": off, "records": recs}


def block_of(rec):
    return BLOCK_BY_LEN.get(rec["u_len"], "")


# ---- PWSTaskGroup 字段偏移（由 pwsdll.py ctypes 定义推算）----
TF_SIZE = 556
TF_OFF = {
    "tfEndurance": 4, "tfEnduranceReq": 8, "tfFlagship": 44, "tfHomePort": 54,
    "tfMission": 349, "tfSpeed": 353,
}


def tf_rows(block):
    rows = []
    for i in range(len(block) // TF_SIZE):
        b = block[i * TF_SIZE:(i + 1) * TF_SIZE]
        flagship = struct.unpack_from("<i", b, TF_OFF["tfFlagship"])[0]
        home = struct.unpack_from("<H", b, TF_OFF["tfHomePort"])[0]
        mission = b[TF_OFF["tfMission"]]
        speed = b[TF_OFF["tfSpeed"]]
        if flagship <= 0 and mission == 0 and home == 0:
            continue
        rows.append({"slot": i, "flagship": flagship, "home": home,
                     "mission": mission, "speed": speed})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--tf", action="store_true")
    ap.add_argument("--dump", nargs=2, metavar=("REC_TYPE", "OUT"))
    a = ap.parse_args()

    c = read_container(a.save)
    print(f"# {a.save}")
    print(f"# 外层={c['wrapped']}  文件={c['raw_len']}B  解压后={c['body_len']}B  "
          f"已解析={c['consumed']}B  记录数={len(c['records'])}")
    if a.dump:
        want = int(a.dump[0])
        for r in c["records"]:
            if r["type"] == want:
                Path(a.dump[1]).write_bytes(r["data"])
                print(f"已导出 type={want}({r['type_name']}) {r['u_len']}B → {a.dump[1]}")
                return 0
        print(f"未找到 type={want}", file=sys.stderr)
        return 1

    print(f"{'#':>3} {'id':>7} {'type':>3} {'name':<12} {'hdr':>4} {'zlen':>8} "
          f"{'ulen':>9}  block")
    for i, r in enumerate(c["records"]):
        print(f"{i:3d} {r['id']:7d} {r['type']:3d} {r['type_name']:<12} "
              f"{r['hdr_len']:4d} {r['z_len']:8d} {r['u_len']:9d}  {block_of(r)}")

    if a.tf:
        for r in c["records"]:
            if r["type"] == 8 or r["u_len"] == 2224000:
                if r["u_len"] == 2224000:
                    print("\n# 编队记录（PWSTaskGroup 556B/槽）")
                    for row in tf_rows(r["data"]):
                        print(f"slot {row['slot']:3d} flagship={row['flagship']:6d} "
                              f"home={row['home']:5d} mission={row['mission']:3d} "
                              f"speed={row['speed']:3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ★★ 按解压长度取记录（最可靠）★★
#   记录 id 的低 8 位**不是**稳定类型码：实例号会进位污染。
#   实测 wpae000.pws 里 LOCATION 记录的 id=0x110021（low8=33），
#   而 wpae001.pws 里同一条是 low8=19。只有 u_len 恒定。
#   所以所有按类型取记录的地方都必须改用长度判据。
REC_BY_LEN = {
    3000:      "HEADER",
    99696:     "SCENARIO",
    9280000:   "SHIP",        # 464 x 20000
    9000000:   "LEADER/PILOT",# 180 x 50000
    20400680:  "AIRGROUP",    # 680 x 30001
    21096000:  "LOCATION",    # 1172 x 18000
    2224000:   "TASKGROUP",   # 556 x 4000
    396000:    "AIRCRAFT",    # 396 x 1000
    472000:    "DEVICE",      # 236 x 2000
    1900000:   "SHIPCLASS",   # 380 x 5000
    15200000:  "PILOT",
    2608000:   "TFTEMPLATE",
}


def record_by_len(container_or_path, ulen):
    """按解压长度取记录数据；找不到返回 None。"""
    c = (read_container(container_or_path)
         if isinstance(container_or_path, (str, bytes)) or hasattr(container_or_path, "__fspath__")
         else container_or_path)
    for r in c["records"]:
        if r["u_len"] == ulen:
            return r["data"]
    return None
