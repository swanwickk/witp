"""field_probe.py — 从存档统计中反推命令字段（不依赖 GUI）

原理：
  命令字段（任务/速度/巡逻比例/开关）在存档里呈现三种可识别特征之一：
    A. 取值域极小（0/1/2/3，或 0..100 的百分数），且分布不均（多数为默认值）
    B. 在同任务/同类型单位间高度一致，跨类型差异明显
    C. 在两个"只改了某个命令"的同日期存档之间发生改变

用法：
  python3 field_probe.py scan <save> --type tf|ag|loc
  python3 field_probe.py diff <saveA> <saveB> --type tf|ag|loc
"""
import sys
import os
import struct
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container

SIZE = {"tf": 556, "ag": 680, "loc": 1172, "ship": 464}
REC_LEN = {"tf": 2224000, "ag": 20400680, "loc": 21096000, "ship": 9280000}


def _block(path, kind):
    c = read_container(path)
    want = REC_LEN[kind]
    for r in c["records"]:
        if len(r["data"]) == want:
            return r["data"]
    raise SystemExit(f"{path}: 找不到长度 {want} 的记录")


def _slots(blk, kind, alive_only=True):
    sz = SIZE[kind]
    n = len(blk) // sz
    out = []
    for i in range(n):
        base = i * sz
        if alive_only:
            if kind == "tf":
                alive = struct.unpack_from("<i", blk, base + 44)[0] > 0
            elif kind == "ag":
                alive = blk[base:base + 25].split(b"\x00")[0] != b""
            else:
                alive = blk[base:base + 25].split(b"\x00")[0] != b""
            if not alive:
                continue
        out.append(base)
    return out


def scan(path, kind):
    """列出每个偏移的取值分布，挑出"像命令字段"的。"""
    blk = _block(path, kind)
    sz = SIZE[kind]
    bases = _slots(blk, kind)
    print(f"{kind}: {len(bases)} 个在用槽，结构 {sz}B")
    print(f"{'off':>4} {'nz':>4} {'uniq':>5}  values(top6)")
    for off in range(sz):
        vals = [blk[b + off] for b in bases]
        c = Counter(vals)
        nz = sum(1 for v in vals if v)
        if nz == 0:
            continue
        uniq = len(c)
        # 命令字段特征：取值种类少、有明确默认值
        if uniq > 12:
            continue
        top = " ".join(f"{v}x{n}" for v, n in c.most_common(6))
        print(f"{off:>4} {nz:>4} {uniq:>5}  {top}")


def diff(a, b, kind):
    """两个存档逐字节差分，只报差异集中的偏移。"""
    ba, bb = _block(a, kind), _block(b, kind)
    sz = SIZE[kind]
    bases = _slots(ba, kind)
    print(f"diff {os.path.basename(a)} vs {os.path.basename(b)} ({kind})")
    changed = defaultdict(list)
    for base in bases:
        slot = base // sz
        for off in range(sz):
            if ba[base + off] != bb[base + off]:
                changed[off].append((slot, ba[base + off], bb[base + off]))
    if not changed:
        print("  无差异")
        return
    for off in sorted(changed):
        items = changed[off]
        pairs = Counter((o, n) for _, o, n in items)
        desc = " ".join(f"{o}->{n}x{c}" for (o, n), c in pairs.most_common(4))
        print(f"  off {off:>4}  槽{len(items):>3}  {desc}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "scan":
        kind = "tf"
        if "--type" in sys.argv:
            kind = sys.argv[sys.argv.index("--type") + 1]
        scan(sys.argv[2], kind)
    elif cmd == "diff":
        kind = "tf"
        if "--type" in sys.argv:
            kind = sys.argv[sys.argv.index("--type") + 1]
        diff(sys.argv[2], sys.argv[3], kind)
    else:
        print(__doc__)
