"""pad_search.py — 主动填充搜索：给大记录找压缩长度精确值

背景：SHIP/AG/LOC 等大记录的 f2/f3 是引擎校验值，改数据后
压缩长度必须回到原值。若填充区本来全是零（没东西可清），
就主动往空槽里写 0/1，制造可控的长度抖动。

用法（作为库）：
    import pad_search
    blob = pad_search.find_blob(data, target_len, pool_offsets)
"""
import zlib


def _sync_len(data, level=9, mem=8, wb=15, strat=0, split=None):
    co = zlib.compressobj(level, zlib.DEFLATED, wb, mem, strat)
    out = co.compress(data)
    out += co.flush(zlib.Z_SYNC_FLUSH)
    return bytes(out)


def _try_body(body, data_ref, target_len):
    rest = target_len - len(body) - 4
    if rest < 5:
        return None
    for tail_fixed in (False, True):
        r = rest - (2 if tail_fixed else 0)
        if r < 5 or r % 5:
            continue
        out = bytearray(body)
        n = r // 5
        for i in range(n):
            last = (i == n - 1)
            out += b"\x01\x00\x00\xff\xff" if last else b"\x00\x00\x00\xff\xff"
        ad = zlib.adler32(data_ref) & 0xFFFFFFFF
        out += ad.to_bytes(4, "big")
        blob = bytes(out)
        if len(blob) == target_len:
            try:
                if zlib.decompress(blob) == data_ref:
                    return blob
            except zlib.error:
                pass
    return None


def find_blob(data, target_len, pool_offsets, max_try=4000):
    """在 pool_offsets 里写 0/1 制造抖动，凑出 target_len。

    pool_offsets: 可安全写入的偏移列表（空槽区域）。
    返回 (blob, used_offsets) 或 None。
    """
    data = bytes(data)
    base = _try_body(_sync_len(data), data, target_len)
    if base:
        return base, []

    buf = bytearray(data)
    step = 1
    used = []
    # 逐字节把 0 -> 1（增加熵 → 压缩流变长），也可反过来
    for i, off in enumerate(pool_offsets[:max_try]):
        if buf[off] != 0:
            continue
        buf[off] = 1
        used.append(off)
        if (i + 1) % step:
            continue
        cand = bytes(buf)
        blob = _try_body(_sync_len(cand), cand, target_len)
        if blob:
            return blob, used
    # 再试 0 -> 0x41
    for off in used:
        buf[off] = 0
    for i, off in enumerate(pool_offsets[:max_try]):
        buf[off] = 0x41
        cand = bytes(buf)
        blob = _try_body(_sync_len(cand), cand, target_len)
        if blob:
            return blob, [off]
        buf[off] = 0
    return None
