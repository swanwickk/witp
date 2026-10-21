"""mem_tf.py — 直接读写运行时 TF 结构（464B，基址 0x1a14000）

实测（wine 32 位进程）：
  · TF 数组基址 0x1a14000，步长 0x1d0（464）
  · 槽 0..29 对应 TF1..TF30
  · off 424.. 是编队名（ASCII）
  · off 12..39 续航、66..78 位置、110..114 任务等

用法：
    import mem_tf
    mem_tf.read_all()          # 读全部槽
    mem_tf.snapshot('a')       # 快照
    mem_tf.diff('a','b')       # 差分
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mem_probe as M

BASE = 0x1a14ae0   # 实测：slot0 = TF1(Shokaku)
SZ = 0x1D0
SLOTS = 40


def game_pid():
    out = subprocess.run(["pgrep", "-f", "War in the Pacific Admiral Edition.exe"],
                         capture_output=True, text=True).stdout.split()
    for p in out:
        exe = os.readlink(f"/proc/{p}/exe") if os.path.exists(f"/proc/{p}/exe") else ""
        if "wine" not in exe:
            continue
        try:
            cwd = os.readlink(f"/proc/{p}/cwd")
        except OSError:
            continue
        if "wine-witp-mcp" in cwd:
            return int(p)
    return None


def read_all(pid=None):
    pid = pid or game_pid()
    d = M.gdb_read(pid, BASE, SZ * SLOTS)
    return d


def slot_data(raw, slot):
    return raw[slot * SZ:(slot + 1) * SZ]


def tf_name(raw, slot):
    c = slot_data(raw, slot)
    if len(c) < SZ:
        return ""
    return c[424:464].split(b"\x00")[0].decode("latin1", "replace").strip()


def snapshot(tag):
    pid = game_pid()
    raw = read_all(pid)
    open(f"/tmp/memtf_{tag}.bin", "wb").write(raw)
    print(f"snapshot {tag}: {len(raw)}B pid={pid}")
    return raw


def diff(tag_a, tag_b):
    a = open(f"/tmp/memtf_{tag_a}.bin", "rb").read()
    b = open(f"/tmp/memtf_{tag_b}.bin", "rb").read()
    print(f"{'slot':<6}{'name':<20}{'off':>6}  a -> b")
    for s in range(SLOTS):
        ca, cb = slot_data(a, s), slot_data(b, s)
        if len(ca) < SZ or len(cb) < SZ:
            continue
        nm = tf_name(a, s)
        for i in range(SZ):
            if ca[i] != cb[i]:
                print(f"{s:<6}{nm[:20]:<20}{i:>6}  {ca[i]} -> {cb[i]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == "snap":
        snapshot(sys.argv[2])
    else:
        raw = read_all()
        for s in range(SLOTS):
            nm = tf_name(raw, s)
            c = slot_data(raw, s)
            nz = sum(1 for x in c if x)
            if nz > 2:
                print(f"slot{s:<3} {nm[:24]:<24} nonzero={nz}")
