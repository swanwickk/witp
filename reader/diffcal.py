"""diffcal.py — 通用字段标定：GUI 改一次 → 存档差分 → 定位偏移

为什么需要它：
  存档里的字段偏移不能靠猜，也不能只看社区 ctypes（它们有大量 skip 空洞）。
  唯一可靠办法是「控制变量实验」：保持其它一切不变，只改目标设置，
  存盘两次，diff 出变化的字节区间。

用法：
  python3 diffcal.py --base A.pws --new B.pws            # 只差分
  python3 diffcal.py --base A.pws --new B.pws --json     # 输出 JSON
  python3 diffcal.py --base A.pws --new B.pws --type 8   # 只看某类记录

★ 记录 id 的坑（实测）：
  rid 低 8 位 = 记录类型，次 8 位 = **实例号**。
  实例号每次存盘递增（HEADER 1→2、SHIP 0x101→0x102…），
  所以不能按 rid 配对，只能按「类型 + 解压长度 + 同类型内序号」配对。
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pwsfile


def rec_type(rid):
    return rid & 0xFF


def load_records(path):
    """返回 {类型: [(rid, 数据), ...]}，保持文件内顺序"""
    c = pwsfile.read_container(path)
    grouped = {}
    for r in c["records"]:
        grouped.setdefault(rec_type(r["id"]), []).append((r["id"], r["data"]))
    return grouped


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0] if o + 2 <= len(b) else None


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0] if o + 4 <= len(b) else None


def build_runs(changed):
    """把变化字节下标合并成区间（间隔<=3 归并，便于看多字节值）"""
    runs = []
    start = prev = changed[0]
    for c in changed[1:]:
        if c - prev <= 3:
            prev = c
        else:
            runs.append((start, prev))
            start = prev = c
    runs.append((start, prev))
    return runs


def diff(base, new, only_type=None):
    A = load_records(base)
    B = load_records(new)

    results = []
    for t in sorted(set(A) | set(B)):
        if only_type is not None and t != only_type:
            continue
        la, lb = A.get(t, []), B.get(t, [])
        if len(la) != len(lb):
            results.append({"rec_type": t, "error":
                            f"记录数不同 base={len(la)} new={len(lb)}"})
            continue
        for seq, ((ria, ra), (rib, rb)) in enumerate(zip(la, lb)):
            if len(ra) != len(rb):
                results.append({"rec_type": t, "seq": seq, "error":
                                f"长度不同 {len(ra)}->{len(rb)}"})
                continue
            if ra == rb:
                continue
            changed = [i for i in range(len(ra)) if ra[i] != rb[i]]
            info = {"rec_type": t, "seq": seq, "rec_len": len(ra),
                    "rid_old": ria, "rid_new": rib, "runs": []}
            for (s, e) in build_runs(changed):
                seg = {"off": s, "end": e, "nbytes": e - s + 1,
                       "old_hex": ra[s:e + 1].hex(),
                       "new_hex": rb[s:e + 1].hex()}
                for w, fn, name in ((1, lambda x, o: x[o], "u8"),
                                    (2, u16, "u16"), (4, u32, "u32")):
                    if e - s + 1 >= w:
                        ov, nv = fn(ra, s), fn(rb, s)
                        if ov is not None and nv is not None:
                            seg[f"{name}_old"] = ov
                            seg[f"{name}_new"] = nv
                info["runs"].append(seg)
            results.append(info)
    return results


def report(results, base, new):
    print(f"base: {base}")
    print(f"new : {new}")
    real = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    total = sum(len(r["runs"]) for r in real)
    print(f"变化记录数: {len(real)}  变化区间数: {total}\n")
    for r in errs:
        print(f"[!] type={r['rec_type']} {r['error']}")
    if errs:
        print()
    for r in real:
        print(f"--- type={r['rec_type']} seq={r['seq']} len={r['rec_len']} "
              f"区间={len(r['runs'])} ---")
        for seg in r["runs"]:
            extra = ""
            if seg["nbytes"] == 1 and "u8_old" in seg:
                extra = f"  u8 {seg['u8_old']}->{seg['u8_new']}"
            elif seg["nbytes"] == 2 and "u16_old" in seg:
                extra = f"  u16 {seg['u16_old']}->{seg['u16_new']}"
            elif seg["nbytes"] == 4 and "u32_old" in seg:
                extra = f"  u32 {seg['u32_old']}->{seg['u32_new']}"
            print(f"  off={seg['off']:>8} len={seg['nbytes']:<3} "
                  f"{seg['old_hex']} -> {seg['new_hex']}{extra}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--type", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for p in (a.base, a.new):
        if not os.path.exists(p):
            sys.exit(f"不存在: {p}")
    res = diff(a.base, a.new, a.type)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        report(res, a.base, a.new)


if __name__ == "__main__":
    main()
