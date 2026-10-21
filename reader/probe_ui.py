"""probe_ui.py — 差分采集台：GUI 操作前后存档对比，精确定位字段

用途：在游戏里改一个设置，存档，然后自动差分出"改了哪几个字节"。
      这是标定剩余命令字段的唯一可靠方法。

用法（宿主机，需游戏已载入存档）：
  python3 probe_ui.py snapshot base          # 采集基线快照
  python3 probe_ui.py snapshot after         # GUI 改完设置后采集
  python3 probe_ui.py diff base after --type tf
  python3 probe_ui.py save 03                # 让游戏存到槽 003（GUI 操作）

差分输出只列"变化槽数 <= 该结构体在用数的 10%"的偏移，
并按变化槽数升序，命令字段通常只影响 1~2 个槽。
"""
import os
import sys
import json
import struct
import subprocess
import time
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

WS = "/root/.hermes/profiles/witp/workspace"
SNAP_DIR = "/root/.hermes/profiles/witp/workspace/witp-probe"
VNCPORT = os.environ.get("WITP_VNC_PORT", "5901")
DISPLAY = os.environ.get("WITP_DISPLAY", ":97")

REC = {"tf": 2224000, "ag": 20400680, "loc": 21096000, "ship": 9280000}
SZ = {"tf": 556, "ag": 680, "loc": 1172, "ship": 464}


def game_save_dir():
    cands = glob.glob("/root/.wine-witp-mcp/prefix/drive_c/1108r9/*/SAVE")
    cands += glob.glob("/root/.wine-witp/drive_c/1108r9/*/SAVE")
    for c in cands:
        if os.path.isdir(c):
            return c
    raise SystemExit("找不到 SAVE 目录")


SAVE = game_save_dir()


def vnc_click(x, y, act="click"):
    subprocess.run(["python3", f"{WS}/witp_vncclick2.py", str(x), str(y), act],
                   capture_output=True,
                   env=dict(os.environ, WITP_VNC_PORT=VNCPORT))


def vnc_key(k):
    subprocess.run(["python3", f"{WS}/witp_vnckey2.py", k],
                   capture_output=True,
                   env=dict(os.environ, WITP_VNC_PORT=VNCPORT))


def latest_save(exclude=("wpae000.pws",)):
    files = [f for f in glob.glob(os.path.join(SAVE, "*.pws"))
             if os.path.basename(f) not in exclude]
    files.sort(key=os.path.getmtime)
    return files[-1] if files else None


def snapshot(tag):
    """把当前最新存档复制成快照。"""
    os.makedirs(SNAP_DIR, exist_ok=True)
    src = latest_save()
    if not src:
        raise SystemExit("没有可用存档")
    dst = os.path.join(SNAP_DIR, f"{tag}.pws")
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(data)
    print(f"snapshot {tag} <- {os.path.basename(src)} ({len(data)}B)")
    return dst


def blocks(path):
    c = read_container(path)
    out = {}
    for kind, ln in REC.items():
        for r in c["records"]:
            if len(r["data"]) == ln:
                out[kind] = r["data"]
                break
    return out


def alive_idx(blk, kind):
    sz = SZ[kind]
    out = []
    for i in range(len(blk) // sz):
        b = i * sz
        if kind == "tf":
            ok = struct.unpack_from("<i", blk, b + 44)[0] > 0
        elif kind == "ship":
            ok = blk[b:b + 20].split(b"\x00")[0] != b""
        else:
            ok = blk[b:b + 25].split(b"\x00")[0] != b""
        if ok:
            out.append(i)
    return out


def names(blk, kind):
    """返回 槽 -> 名称（用于按名字对齐，规避槽位互换）。"""
    sz = SZ[kind]
    out = {}
    for i in range(len(blk) // sz):
        b = i * sz
        nm = blk[b:b + (20 if kind == "ship" else 25)].split(b"\x00")[0]
        if nm:
            out[nm] = i
    return out


def diff(path_a, path_b, kind):
    A, B = blocks(path_a), blocks(path_b)
    if kind not in A or kind not in B:
        raise SystemExit(f"{kind} 记录缺失")
    a, b = A[kind], B[kind]
    sz = SZ[kind]
    na, nb = names(a, kind), names(b, kind)
    common = sorted(set(na) & set(nb))          # bytes 排序稳定
    total = len(na)
    print(f"{kind}: 在用 {total} 槽，按名对齐 {len(common)} 槽")
    if kind == "tf":
        # TF 没有名字，退回按槽号
        idx = [(i, i) for i in alive_idx(a, kind) if i in set(alive_idx(b, kind))]
        label = lambda i, j: f"TF{i}"
    else:
        idx = [(na[nm], nb[nm]) for nm in common]
        label = lambda i, j: (a[i * sz:i * sz + 20].split(b"\x00")[0].decode("latin1", "replace")[:22]
                              or f"#{i}")

    rows = []
    for off in range(sz):
        ch = []
        for i, j in idx:
            va, vb = a[i * sz + off], b[j * sz + off]
            if va != vb:
                ch.append((label(i, j), va, vb))
        if ch:
            rows.append((len(ch), off, ch))
    rows.sort()
    print(f"{'off':>4} {'槽':>4}  变化")
    for n, off, ch in rows:
        show = ", ".join(f"{nm}:{x}->{y}" for nm, x, y in ch[:4])
        more = "" if len(ch) <= 4 else f" …(+{len(ch)-4})"
        print(f"{off:>4} {n:>4}  {show}{more}")
    if not rows:
        print("  无差异")
    return rows


def gui_save(slot):
    """让游戏存到指定槽位（F 键 → 行箭头 → SAVE）。"""
    vnc_key("Escape")
    time.sleep(1.5)
    vnc_key("f")
    time.sleep(3)
    y = 123 + 16 * int(slot)
    vnc_click(65, y)
    time.sleep(1)
    vnc_click(62, 546)
    time.sleep(6)
    print(f"saved to slot {slot} (y={y})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "snapshot":
        snapshot(sys.argv[2])
    elif cmd == "diff":
        kind = "tf"
        if "--type" in sys.argv:
            kind = sys.argv[sys.argv.index("--type") + 1]
        diff(os.path.join(SNAP_DIR, sys.argv[2] + ".pws"),
             os.path.join(SNAP_DIR, sys.argv[3] + ".pws"), kind)
    elif cmd == "save":
        gui_save(sys.argv[2])
    elif cmd == "dir":
        print(SAVE)
    else:
        print(__doc__)
