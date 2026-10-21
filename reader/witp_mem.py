"""witp_mem.py — WitP-AE 运行时内存操作库（纯二进制，零键鼠）

═══════════════════════════════════════════════════════════════
★★ 本文件的所有常量都是实测验证过的，不是推测 ★★
═══════════════════════════════════════════════════════════════

【通道】
  必须用 /proc/<pid>/mem，**不能用 gdb**。
  gdb 的 `dump binary memory` 在目标页未映射时静默写出全零文件，
  与"读到真实的零"完全无法区分 —— 这曾导致连续多轮"内存全零"的假结论。
  /proc/pid/mem 在未映射页返回 EIO，能明确区分。

【TF 数组】
  基址  0x6da5148   （实测：过回合后仍稳定；但每次仍应现场校验）
  步长  556         （= 存档 PWSTaskGroup 记录长度，不是 464）
  索引  = TF 号
  字段偏移与存档**完全一致**（已用 12/12 槽 flagship 交叉验证）

【验证链】
  flagship@44   → 12/12 槽与存档逐一吻合
  mission@349   → 写 15→1，界面 Mission 列变 Air Combat
  speed@354     → 写 3→1，过回合后 wpae002.pws 里保留 1
  ⇒ 引擎采纳内存写入并持久化到存档，全程零键鼠

【名称表】
  0x2de79c0 起，20 字节/条，索引 = TF 号
  但地址会随游戏状态漂移，仅作辅助确认。

用法:
  python3 witp_mem.py list
  python3 witp_mem.py show 7
  python3 witp_mem.py set 7 mission 1
"""
import os
import re
import struct
import sys

TF_BASE_HINT = 0x6da5148
TF_SZ = 556

# 已实测验证的偏移（与存档 PWSTaskGroup 一致）
TF_OFF = {
    # ★ 运行时布局与存档不同，以下为实测值（见 witp-ae-save-format 技能）
    "endure":     (4,   "u32"),   # 续航（TF8=14000 与界面 Endure 吻合）
    "endureReq":  (8,   "u32"),   # 续航需求（TF8=1200 与界面 Needed 吻合）
    "fuel":       (12,  "u32"),   # 燃料（TF2=7030 与界面 Fuel 吻合）
    "load":       (28,  "u32"),   # 补给装载（TF7=30953 与界面 Supply 吻合）
    "flagship":   (44,  "u32"),
    "home":       (54,  "u16"),
    "mission":    (349, "u8"),
    "loadState":  (350, "u8"),
    "speed":      (354, "u8"),
    "maxReact":   (355, "u8"),
    "routing":    (369, "u8"),
    "tolerance":  (448, "u8"),
    "wpCount":    (320, "u16"),
    "wpAlloc":    (322, "u16"),
    "wp":         (118, "wp40"),   # 40 个 (x,y) u16 对
}

FMT = {"u8": "<B", "u16": "<H", "u32": "<I"}

# TF 任务枚举（pwsdll.py:296-318）
MISSION = {
    1: "AIRCOMBAT", 2: "SURFACE", 3: "BOMBARDMENT", 4: "FASTTRANSPORT",
    5: "TRANSPORT", 6: "REPLENISHMENT", 7: "MINELAYING", 8: "SUBPATROL",
    9: "SUBMINELAYING", 10: "SUBTRANSPORT", 11: "CARGO",
    13: "AIRTRANSPORT", 14: "CVESCORT", 15: "AMPHIB", 16: "ASWCOMBAT",
    17: "PTBOAT", 18: "TANKER", 19: "MINESWEEPING", 20: "LANDINGCRAFT",
    22: "SUPPORT", 23: "LOCALMINESWEEPING", 25: "ESCORT",
}
MISSION_R = {v: k for k, v in MISSION.items()}


def game_pid():
    """找当前实例的游戏进程。

    ★ 必须按 WINEPREFIX 精确匹配（与 witp_obj.game_pid 同一实现）：
      主实例(:98, /root/.wine-witp) 与测试实例(:97, /root/.wine-witp-mcp)
      可能同时在跑，旧的 "wine-witp" 子串模糊匹配会选错进程，
      导致读写到另一个实例的内存（2026-10-20 实测发生过）。
    """
    from witp_obj import game_pid as _precise
    return _precise()


def rw_regions(pid, min_size=1 << 20):
    out = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s*(.*)", line)
            if not m:
                continue
            s, e = int(m.group(1), 16), int(m.group(2), 16)
            if "rw" in m.group(3) and (e - s) >= min_size and not m.group(4).strip():
                out.append((s, e))
    return out


def _read(pid, addr, n):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.read(fd, n)
    except OSError:
        return None
    finally:
        os.close(fd)


def _write(pid, addr, data):
    fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)
    try:
        os.lseek(fd, addr, os.SEEK_SET)
        return os.write(fd, data) == len(data)
    except OSError:
        return False
    finally:
        os.close(fd)


def find_tf_base(pid, expect):
    """现场定位 TF 数组基址。

    expect: {tf号: flagship}，来自当前存档。至少 5 个吻合才认。
    ★ 不要缓存结果 —— 地址会随游戏内操作漂移。
    """
    for _ in range(3):
        if not expect:
            return None
        tf0, fl0 = next(iter(expect.items()))
        pat = struct.pack("<I", fl0)
        for s, e in rw_regions(pid):
            fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
            try:
                os.lseek(fd, s, os.SEEK_SET)
                blob = os.read(fd, e - s)
            except OSError:
                continue
            finally:
                os.close(fd)
            if not blob:
                continue
            pos = 0
            while True:
                i = blob.find(pat, pos)
                if i < 0:
                    break
                pos = i + 1
                base = i - TF_OFF["flagship"][0] - tf0 * TF_SZ
                if base < 0:
                    continue
                ok = sum(
                    1 for t, f in expect.items()
                    if 0 <= base + t * TF_SZ + 44 < len(blob) - 4
                    and struct.unpack_from("<I", blob, base + t * TF_SZ + 44)[0] == f
                )
                if ok >= 5:
                    return s + base
    return None


def get(pid, base, tf, field):
    off, kind = TF_OFF[field]
    if kind == "wp40":
        d = _read(pid, base + tf * TF_SZ + off, 160)
        if not d:
            return []
        return [struct.unpack_from("<HH", d, i * 4) for i in range(40)]
    d = _read(pid, base + tf * TF_SZ + off, 4)
    if not d:
        return None
    return struct.unpack_from(FMT[kind], d, 0)[0]


def set_field(pid, base, tf, field, value):
    off, kind = TF_OFF[field]
    if kind == "wp40":
        raise ValueError("航路点请用 set_waypoints")
    return _write(pid, base + tf * TF_SZ + off, struct.pack(FMT[kind], value))


def set_waypoints(pid, base, tf, pts):
    """写航路点：必须同时更新 wpCount / wpAlloc。"""
    if len(pts) > 40:
        raise ValueError("最多 40 个航路点")
    buf = b"".join(struct.pack("<HH", x, y) for x, y in pts)
    buf = buf.ljust(160, b"\0")
    ok = _write(pid, base + tf * TF_SZ + TF_OFF["wp"][0], buf)
    ok &= _write(pid, base + tf * TF_SZ + TF_OFF["wpCount"][0],
                 struct.pack("<H", len(pts)))
    ok &= _write(pid, base + tf * TF_SZ + TF_OFF["wpAlloc"][0],
                 struct.pack("<H", len(pts)))
    return ok


def occupied(pid, base):
    return [t for t in range(1, 200) if get(pid, base, t, "flagship")]


def main():
    pid = game_pid()
    if not pid:
        print("游戏未运行")
        return
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd in ("list", "show", "set"):
        save = os.environ.get("WITP_SAVE")
        if not save:
            print("需要环境变量 WITP_SAVE 指向当前存档（用于定位基址）")
            return
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import pwsfile
        c = pwsfile.read_container(save)
        expect = {}
        for r in c["records"]:
            if r["u_len"] == 2224000:
                for s in range(200):
                    b = s * TF_SZ
                    fl = struct.unpack_from("<I", r["data"], b + 44)[0]
                    if fl:
                        expect[s] = fl
                break
        base = find_tf_base(pid, expect)
        if base is None:
            print("定位失败（存档与内存不匹配？）")
            return
        print(f"PID={pid}  TF数组基址={base:#x}  步长={TF_SZ}")

    if cmd == "list":
        for tf in occupied(pid, base):
            m = get(pid, base, tf, "mission")
            print(f"  TF{tf:<3} flagship={get(pid,base,tf,'flagship'):<6} "
                  f"home={get(pid,base,tf,'home'):<5} "
                  f"mission={m}({MISSION.get(m,'?')}) "
                  f"speed={get(pid,base,tf,'speed')} "
                  f"load={get(pid,base,tf,'load')}")
    elif cmd == "show":
        tf = int(sys.argv[2])
        for k in TF_OFF:
            v = get(pid, base, tf, k)
            print(f"  {k:<12} = {v}")
    elif cmd == "set":
        tf, field, val = int(sys.argv[2]), sys.argv[3], sys.argv[4]
        if field == "mission" and not val.isdigit():
            val = MISSION_R[val.upper()]
        else:
            val = int(val)
        old = get(pid, base, tf, field)
        ok = set_field(pid, base, tf, field, val)
        print(f"TF{tf}.{field}: {old} -> {get(pid,base,tf,field)} (ok={ok})")


if __name__ == "__main__":
    main()
