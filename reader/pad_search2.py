"""pad_search2.py — 两维搜索：填充量 × 压缩参数网格

对每个 (填充字节数 k, 压缩参数) 组合，检查 rest 是否满足
  rest % 5 == 0  或  (rest-2) % 5 == 0
命中即返回。

比逐字节试快得多：一次性算出 k 的候选，再验证。
"""
import zlib


def _body(data, level, mem, wb, strat, split=None):
    co = zlib.compressobj(level, zlib.DEFLATED, wb, mem, strat)
    out = co.compress(data)
    out += co.flush(zlib.Z_SYNC_FLUSH)
    return bytes(out)


def _assemble(body, rest, data_ref, target):
    if rest < 5:
        return None
    for fixed in (False, True):
        r = rest - (2 if fixed else 0)
        if r < 5 or r % 5:
            continue
        out = bytearray(body)
        n = r // 5
        for i in range(n):
            out += b"\x01\x00\x00\xff\xff" if i == n - 1 else b"\x00\x00\x00\xff\xff"
        out += (zlib.adler32(data_ref) & 0xFFFFFFFF).to_bytes(4, "big")
        blob = bytes(out)
        if len(blob) == target:
            try:
                if zlib.decompress(blob) == data_ref:
                    return blob
            except zlib.error:
                pass
    return None


GRID = [(lv, mem, wb, st)
        for lv in (9, 8, 7, 6, 5, 4)
        for mem in (9, 8, 7, 6, 5)
        for wb in (15, 14, 13, 12, 11)
        for st in (0, 1, 2)]


def search(data, target, pool_offsets, max_pad=600):
    """返回 (blob, pad_count) 或 None。"""
    base = bytes(data)
    for k in range(0, max_pad + 1):
        buf = bytearray(base)
        for i in range(k):
            buf[pool_offsets[i]] = 1
        cand = bytes(buf)
        for lv, mem, wb, st in GRID:
            try:
                body = _body(cand, lv, mem, wb, st)
            except zlib.error:
                continue
            rest = target - len(body) - 4
            blob = _assemble(body, rest, cand, target)
            if blob:
                return blob, k
    return None
