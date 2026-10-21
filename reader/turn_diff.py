"""turn_diff.py — 过回合前后的字段级差分，定位真正的命令/状态字段

关键洞察：
  · 游戏结算会读命令、写状态。凡"结算前有值、结算后保留"的字段 = 命令字段；
  · 凡"结算前有值、结算后被重算"的字段 = 派生状态；
  · 凡"两档都相同"的 = 静态属性。

用法：
  python3 turn_diff.py <before.pws> <after.pws> --type tf|ag|loc
输出按"变化槽数/总在用槽数"排序，聚焦于真正的动态字段。
"""
import sys
import os
import struct
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

REC = {"tf": 2224000, "ag": 20400680, "loc": 21096000}
SZ = {"tf": 556, "ag": 680, "loc": 1172}


def blk(path, kind):
    for r in read_container(path)["records"]:
        if len(r["data"]) == REC[kind]:
            return r["data"]
    raise SystemExit(f"{path}: 无 {kind} 记录")


def alive(blk, kind):
    sz = SZ[kind]
    out = []
    for i in range(len(blk) // sz):
        b = i * sz
        if kind == "tf":
            ok = struct.unpack_from("<i", blk, b + 44)[0] > 0
        else:
            ok = blk[b:b + 25].split(b"\x00")[0] != b""
        if ok:
            out.append(i)
    return out


def run(a, b, kind):
    ba, bb = blk(a, kind), blk(b, kind)
    sz = SZ[kind]
    slots = alive(ba, kind)
    print(f"{kind}: {len(slots)} 个在用槽  ({os.path.basename(a)} -> {os.path.basename(b)})")
    print(f"{'off':>4} {'变化槽':>6} {'前值分布':<28} {'后值分布'}")
    rows = []
    for off in range(sz):
        ch = [(s, ba[s * sz + off], bb[s * sz + off]) for s in slots
              if ba[s * sz + off] != bb[s * sz + off]]
        if not ch:
            continue
        before = Counter(o for _, o, _ in ch)
        after = Counter(n for _, _, n in ch)
        rows.append((len(ch), off, before, after))
    rows.sort(reverse=True)
    for n, off, before, after in rows:
        bs = " ".join(f"{v}x{c}" for v, c in before.most_common(4))
        as_ = " ".join(f"{v}x{c}" for v, c in after.most_common(4))
        print(f"{off:>4} {n:>6}  {bs:<28} {as_}")


if __name__ == "__main__":
    kind = "tf"
    if "--type" in sys.argv:
        kind = sys.argv[sys.argv.index("--type") + 1]
    run(sys.argv[1], sys.argv[2], kind)
