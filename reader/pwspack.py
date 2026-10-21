#!/usr/bin/env python3
"""pwspack.py — .pws 存档容器读写（逆向实现，纯 Python）

★容器格式（实测，英文 1108r9）★
  .pws 文件 = gzip 头(10B) + **raw deflate**(整个记录串) + crc32 + 原始长度
  记录串 = [12B 记录头][zlib 流] × N
  记录头 = u16 实例号 | u16 记录类型 | u32 A | u32 B
      · 记录类型 = 头里第 3-4 字节的低 4 位（1=SCENARIO 8=SHIP 19=LOCATION
        20=AIRGROUP 21=LEADER 22=PILOT 27=SHIPCLASS 30=MINES 31=DEVICE
        32=AIRCRAFT 38=HEADER …）
      · A/B 语义：**id<1000 的小记录里 A=解压长度、B=压缩长度**；大记录（id 高位置位，
        如 0x10001）里 A/B 是引擎侧校验字段，实测改它们会让 pwsdll 直接崩，
        必须原样保留。
  zlib 流用 wbits=15（标准 zlib 包装，78 9c/da 开头）。

★★写回铁律（实测）★★
  引擎（pwsdll）读档时对**每条记录的压缩长度**有硬校验：
  压缩长度与原档不同 → "Restore size larger than expected"，读档中断。
  因此改数据后必须把该记录的压缩流长度**调回原值**（pad/调参/填充字节补偿），
  否则游戏读不了这份档。本模块的 pack_container(..., keep_lengths=True) 实现了该补偿。

用法：
    python3 pwspack.py roundtrip <save.pws> [out.pws]     # 重打包（应字节级一致）
    python3 pwspack.py show <save.pws>                    # 打印记录表
"""
import argparse
import os
import gzip
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pwsfile import read_container  # noqa: E402

TF_SIZE = 556
TF_FLAGSHIP = 44
TF_HOMEPORT = 54
TF_WP = 118
TF_WP_MAX = 8
TF_MISSION = 349
TF_SPEED = 354


# ------------------------------------------------------------------ 压缩辅助
def _deflate_zlib(data, level=9, mem=8, strat=0):
    co = zlib.compressobj(level, zlib.DEFLATED, 15, mem, strat)
    return co.compress(data) + co.flush()


def _sync_len(data, level=9, mem=8, wbits=15, strat=0, split=None):
    co = zlib.compressobj(level, zlib.DEFLATED, wbits, mem, strat)
    if split is None:
        return co.compress(data) + co.flush(zlib.Z_SYNC_FLUSH)
    n = int(len(data) * split)
    return (co.compress(data[:n]) + co.flush(zlib.Z_SYNC_FLUSH)
            + co.compress(data[n:]) + co.flush(zlib.Z_SYNC_FLUSH))


def compress_to_length(data, target_len, filler_offsets=None):
    """把 data 压成**恰好 target_len 字节**的 zlib 流（引擎对压缩流长度有硬校验）。

    ★原理★ zlib 流 = 2B 头 + deflate 块 + 4B adler32。
      Z_SYNC_FLUSH 之后流已字节对齐，可追加「空存储块」（5B，无解压输出）或
      「空固定哈夫曼块」（2B）把长度精确补足。实测本机 zlib 只接受
      rest % 5 ∈ {0, 2}，因此还需让正文长度本身抖动到合适余数：
        · 参数网格 level×memLevel×windowBits×strategy
        · 分段 Z_SYNC_FLUSH（1 字节粒度抖动）
        · 最后手段：在 filler_offsets（语义无关的空槽零区）上写 0/0x41 微调
    """
    # 快路径：原样压缩长度正好等于目标（重打包时必须走这条，才能字节级一致）
    for level in (9, 8, 7, 6):
        blob = _deflate_zlib(data, level, 8, 0)
        if len(blob) == target_len:
            return blob, []

    adler_of = lambda d: struct.pack(">I", zlib.adler32(d) & 0xFFFFFFFF)

    def finish(body, rest, tail_fixed, data_ref):
        out = bytearray(body)
        if tail_fixed:
            for _ in range((rest - 2) // 5):
                out += b"\x00\x00\x00\xff\xff"
            out += b"\x03\x00"
        else:
            a = rest // 5
            for i in range(a):
                out += (b"\x01" if i == a - 1 else b"\x00") + b"\x00\x00\xff\xff"
        return bytes(out) + adler_of(data_ref)

    def try_body(body, data_ref):
        rest = target_len - len(body) - 4
        if rest < 5:
            return None
        for tail_fixed in (False, True):
            r = rest - (2 if tail_fixed else 0)
            if r < 5 or r % 5:
                continue
            blob = finish(body, rest, tail_fixed, data_ref)
            if len(blob) == target_len:
                try:
                    if zlib.decompress(blob) == data_ref:
                        return blob
                except zlib.error:
                    pass
        return None

    # 最后手段：在语义无关的填充区微调正文长度（写 0 或 0x41）
    if filler_offsets:
        # ★实测最有效的一招★：把填充区（空槽）里残留的**非零历史字节**逐步清零。
        #   每清一个字节通常让压缩流缩短 0~1 字节，按 1 字节粒度逼近目标余数；
        #   实测算例：清 36 字节后 rest 正好落到 5，一次命中。
        buf = bytearray(data)
        pool = set(filler_offsets)
        nz = [o for o in range(len(buf)) if buf[o] != 0 and o in pool]
        # 先试「整体一次性清空所有填充区非零字节」——实测这一击常直接命中
        cand_all = bytearray(buf)
        for o in nz:
            cand_all[o] = 0
        cand_all = bytes(cand_all)
        try:
            blob = try_body(_sync_len(cand_all, 9, 8, 15, 0, None), cand_all)
        except zlib.error:
            blob = None
        if blob:
            return blob, [(o, 0) for o in nz]
        if nz:
            step = 1                            # 逐字节试（实测 26 字节即命中，成本可接受）
            for i, off in enumerate(nz):
                buf[off] = 0
                if (i + 1) % step:
                    continue
                cand = bytes(buf)
                try:
                    body = _sync_len(cand, 9, 8, 15, 0, None)
                except zlib.error:
                    continue
                blob = try_body(body, cand)
                if blob:
                    return blob, [(o, 0) for o in nz[:i + 1]]
            # 全部清零仍不命中：再扫一遍剩余余数（用 0x41 回填微调）
            for i, off in enumerate(nz):
                if buf[off] != 0:
                    continue
                buf[off] = 0x41
                cand = bytes(buf)
                try:
                    body = _sync_len(cand, 9, 8, 15, 0, None)
                except zlib.error:
                    buf[off] = 0
                    continue
                blob = try_body(body, cand)
                if blob:
                    return blob, [(off, 0x41)]
                buf[off] = 0
    big = len(data) > 5_000_000
    if big:
        grid = [(lv, mem, wb, st) for lv in (9, 8, 7, 6)
                for mem in (9, 8, 7, 6, 5) for wb in (15, 14, 13, 12, 11)
                for st in (0, 1)]
    else:
        grid = [(lv, mem, wb, st) for lv in (9, 8, 7, 6, 5, 4, 3, 2, 1)
                for mem in (9, 8, 7, 6, 5, 4, 3, 2, 1)
                for wb in (15, 14, 13, 12, 11, 10, 9) for st in (0, 1, 2)]
    splits = (None, 0.1, 0.25, 0.5, 0.75, 0.9, 0.33, 0.66)
    for level, mem, wbits, strat in grid:
        for split in splits:
            try:
                body = _sync_len(data, level, mem, wbits, strat, split)
            except zlib.error:
                continue
            blob = try_body(body, data)
            if blob:
                return blob, []

    raise RuntimeError(f"无法把压缩流精确调到 {target_len} 字节")


# ------------------------------------------------------------------ 打包
def pack_container(records, out_path, keep_lengths=True, allow_len_change=True):
    """records: [{'id','f2','f3','extra','data','z_len'(可选)}] → 写 gzip 容器

    ★关键区别（2026-10-18 实测）★

    · **小记录**（`id < 1000`，如 TF=326 / 舰级 / 剧本）：
      `f2/f3` = 解压长/压缩长，写档时同步更新即可，**压缩长度可任意变化**。
      实测：TF 记录压缩 3458→3636（+178）后，原版 DLL 与游戏本体均正常载入。

    · **大记录**（`id` 高位，如 SHIP=65800 / AG=1114401 / LOC=65811）：
      `f2/f3` 是**引擎校验值**（不是长度），改数据后必须让压缩长度回到原值，
      否则报 `Restore size larger than expected`。
      实测：改 SHIP 记录 1 字节使压缩 +3，未回填 → 读档 records=9 即中断。

    因此 `allow_len_change` **只对小记录生效**，大记录一律强制长度回填。
    """
    body = bytearray()
    for r in records:
        data = r["data"]
        target = r.get("z_len")
        pad_used = []
        orig_comp = r.get("comp")
        if keep_lengths and target:
            # 数据未改动 → 原样复用原始压缩流（保证重打包字节级一致，也最安全）
            if orig_comp and zlib.decompress(orig_comp) == data:
                blob = orig_comp
            else:
                try:
                    blob, pad_used = compress_to_length(data, target,
                                                        r.get("filler_offsets"))
                except RuntimeError:
                    # 大记录（f2/f3 是校验值）必须回填。用「清零空槽残留」把长度压回去。
                    if r["id"] < 1000 and allow_len_change:
                        blob = _deflate_zlib(data, 9, 8, 0)
                        r["_len_delta"] = len(blob) - target
                    else:
                        import shrink as _shrink
                        rec_size = {"ship": 464, "ag": 680, "loc": 1172}.get(
                            r.get("kind"), 0)
                        pool = r.get("filler_offsets")
                        got = None
                        if pool:
                            got = _shrink.shrink_to_target(data, target, pool)
                        if got is None and rec_size:
                            pool2 = _shrink.empty_slot_offsets(data, rec_size)
                            got = _shrink.shrink_to_target(data, target, pool2)
                        if got is None:
                            raise
                        blob, _cleared = got
        else:
            blob = _deflate_zlib(data, 9, 8, 0)
        if len(blob) != (target or len(blob)):
            # allow_len_change=True 时不校验（配合打过补丁的 pwsdll.dll 使用，
            # 补丁已跳过引擎的 "Restore size larger than expected" 检查）
            if not allow_len_change:
                raise RuntimeError(
                    f"记录 {r['id']} 压缩长度 {len(blob)} ≠ 原档 {target}，引擎会拒绝读档")
            r["_len_delta"] = len(blob) - (target or len(blob))
        rid = r["id"]
        if rid < 1000:
            f2, f3 = len(data), len(blob)
        else:
            f2, f3 = r["f2"], r["f3"]
        body += struct.pack("<HHII", rid & 0xFFFF, (rid >> 16) & 0xFFFF, f2, f3)
        body += r.get("extra", b"") or b""
        body += blob
        if pad_used:
            r["_pad_used"] = pad_used
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    deflated = co.compress(bytes(body)) + co.flush()
    gz = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x0b" + deflated
    gz += struct.pack("<II", zlib.crc32(bytes(body)) & 0xFFFFFFFF, len(body) & 0xFFFFFFFF)
    Path(out_path).write_bytes(gz)
    return len(gz), len(body)


# ------------------------------------------------------------------ 编队航路点
def tf_block(records):
    for r in records:
        if len(r["data"]) == 2224000:
            return r
    raise SystemExit("未找到编队记录（2224000B）")


def set_waypoints(block, slot, points):
    off = slot * TF_SIZE + TF_WP
    for i in range(TF_WP_MAX):
        x, y = points[i] if i < len(points) else (0, 0)
        struct.pack_into("<HH", block, off + i * 4, x, y)


def get_waypoints(block, slot):
    off = slot * TF_SIZE + TF_WP
    pts = []
    for i in range(TF_WP_MAX):
        x, y = struct.unpack_from("<HH", block, off + i * 4)
        if x == 0 and y == 0:
            break
        pts.append((x, y))
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["roundtrip", "show"])
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    a = ap.parse_args()
    c = read_container(a.src)
    if a.cmd == "show":
        print(f"{'#':>3} {'type':>4} {'ulen':>9} {'zlen':>8}  head")
        for i, r in enumerate(c["records"]):
            print(f"{i:3d} {r['type']:4d} {r['u_len']:9d} {r['z_len']:8d}  "
                  f"{r['data'][:20]!r}")
        return 0
    recs = [{"id": r["id"], "f2": r["f2"], "f3": r["f3"], "extra": r["extra"],
             "data": r["data"], "z_len": r["z_len"]} for r in c["records"]]
    out = a.dst or "/tmp/_rt.pws"
    n, body = pack_container(recs, out)
    same = Path(a.src).read_bytes() == Path(out).read_bytes()
    print(f"重打包 {n}B（body {body}B）；与原文件字节完全一致 = {same}")
    return 0 if same else 2


if __name__ == "__main__":
    raise SystemExit(main())
