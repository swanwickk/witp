"""shrink.py — 大记录压缩长度"收缩"策略

背景（实测）：
  SHIP/AG/LOC 等大记录（id 高位）的 f2/f3 是引擎校验值，
  改数据后压缩长度必须回到原值。
  但往空槽写 1/0x41 只会让长度**增加**（+6..+8 字节）；
  要把长度**减小**，得清零空槽里的历史残留非零字节。

实测：SHIP 记录（9280000B）改 1 字节后压缩 33953→33959（+6），
      清零 24 个空槽残留字节 → 精确回到 33953。

用法：
    import shrink
    blob = shrink.shrink_to_target(data, target_len, pool_offsets)
"""
import zlib


def _sync_body(data, level=9, mem=8, wb=15, strat=0):
    co = zlib.compressobj(level, zlib.DEFLATED, wb, mem, strat)
    return bytes(co.compress(data) + co.flush(zlib.Z_SYNC_FLUSH))


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


def _zlib_blob(data, level=9):
    """标准 zlib 压缩（与引擎/校验口径一致），末尾已含 adler32。"""
    return zlib.compress(data, level)


def shrink_to_target(data, target_len, pool_offsets, max_steps=4000):
    """清零 pool_offsets 里的非零字节，逼近 target_len。

    返回 (blob, cleared_offsets) 或 None。
    """
    data = bytes(data)

    # 先直接试：标准 zlib 压缩长度正好等于目标就直接用
    z = _zlib_blob(data)
    if len(z) == target_len:
        return z, []

    buf = bytearray(data)
    nz = [o for o in pool_offsets if buf[o] != 0]
    cleared = []
    best = None
    for off in nz[:max_steps]:
        buf[off] = 0
        cleared.append(off)
        cand = bytes(buf)
        # 标准 zlib 压缩长度正好等于目标 → 直接返回（最稳，实测有效）
        z = _zlib_blob(cand)
        if len(z) == target_len:
            return z, cleared
        if len(z) <= target_len:
            if best is None:
                best = cleared[:]
            if len(z) < target_len - 12:
                break
    # 若清零过头，用"写 1"回补
    if best:
        buf2 = bytearray(data)
        for off in best:
            buf2[off] = 0
        for off in pool_offsets[:max_steps]:
            if buf2[off] != 0:
                continue
            buf2[off] = 1
            body = _sync_body(bytes(buf2))
            cand = bytes(buf2)
            blob = _assemble(body, target_len - len(body) - 4, cand, target_len)
            if blob:
                return blob, best + [off]
            buf2[off] = 0
    return None


def empty_slot_offsets(data, rec_size, name_len=20, limit=4000000):
    """找出空槽（前 name_len 字节全零）的所有字节偏移，作为填充/清零池。"""
    out = []
    for i in range(len(data) // rec_size):
        base = i * rec_size
        if data[base:base + name_len].strip(b"\x00"):
            continue
        out.extend(range(base, base + rec_size))
        if len(out) >= limit:
            break
    return out
