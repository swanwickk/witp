#!/usr/bin/env python3
"""ground_diff.py — 界面改一次地面部队命令 → 存档前后 LOCATION 块字节差分 → 反推字段偏移。

用法：
  WITP_VNC_PORT=5901 WITP_DISPLAY=:97 python3 ground_diff.py <slot> <x> <y> <label>
  例：先点地面部队详情屏的 Combat Orders 左箭头，再存到槽 16，对比槽 15 与 16。
"""
import ctypes
import os
import subprocess
import sys
import time

WS = "/root/.hermes/profiles/witp/workspace"
sys.path.insert(0, WS + "/witp-reader")
sys.path.insert(0, WS + "/witp-reader/pywitpaescraper")
DISPLAY = os.environ.get("WITP_DISPLAY", ":97")
PORT = os.environ.get("WITP_VNC_PORT", "5901")
GAME = os.environ.get(
    "WITP_GAME_DIR",
    "/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral's Edition")
SAVE = GAME + "/SAVE"

import pwsfile            # noqa: E402
import pwsdll as P        # noqa: E402

LOC_SIZE = ctypes.sizeof(P.PWSLocation)


def vnc(x, y, mode="click"):
    subprocess.run([sys.executable, f"{WS}/witp_vncclick2.py", str(x), str(y), mode],
                   check=False, timeout=60,
                   env=dict(os.environ, WITP_VNC_PORT=PORT))
    time.sleep(0.9)


def key(k):
    subprocess.run([sys.executable, f"{WS}/witp_vnckey2.py", k],
                   check=False, timeout=60,
                   env=dict(os.environ, WITP_VNC_PORT=PORT))
    time.sleep(0.7)


def loc_block(path):
    c = pwsfile.read_container(path)
    for r in c["records"]:
        if r["u_len"] == LOC_SIZE * 18000:
            return r["data"]
    raise SystemExit("no LOCATION block")


def save_to(slot):
    """F 打开存档框 → 点行箭头 → 点 SAVE 箭头 → ESC 关闭"""
    key("f")
    time.sleep(3)
    vnc(65, 123 + 16 * slot)
    time.sleep(1)
    vnc(62, 546)
    time.sleep(4)
    key("escape")
    time.sleep(1.5)


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    slot = int(sys.argv[1])
    x, y = int(sys.argv[2]), int(sys.argv[3])
    label = sys.argv[4]
    base_slot = slot - 1
    before_path = f"{SAVE}/wpae{base_slot:03d}.pws"
    after_path = f"{SAVE}/wpae{slot:03d}.pws"

    if not os.path.exists(before_path):
        raise SystemExit(f"缺基准存档 {before_path}")
    a = loc_block(before_path)

    print(f"[diff] 点击 ({x},{y}) = {label}")
    vnc(x, y)
    time.sleep(1.5)

    # 存档（先删旧的 after，避免误读）
    if os.path.exists(after_path):
        os.remove(after_path)
    save_to(slot)
    if not os.path.exists(after_path):
        print("[diff] 存档未生成，检查槽位/对话框")
        return 3
    b = loc_block(after_path)

    print(f"[diff] 存档 {base_slot:03d} → {slot:03d}")
    rows = []
    for i in range(len(a) // LOC_SIZE):
        base = i * LOC_SIZE
        if a[base:base + LOC_SIZE] == b[base:base + LOC_SIZE]:
            continue
        name = a[base:base + 25].split(b"\x00")[0].decode("latin1", "replace")
        changes = [(o, a[base + o], b[base + o])
                   for o in range(LOC_SIZE) if a[base + o] != b[base + o]]
        rows.append((i, name, changes))
    print(f"[diff] 变化的记录数 = {len(rows)}")
    for i, name, ch in rows[:12]:
        print(f"  slot {i:5d} {name:24s} " +
              ", ".join(f"+{o}: {o1}→{o2}" for o, o1, o2 in ch[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
