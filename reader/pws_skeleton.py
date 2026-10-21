"""Dump the record skeleton of a WitP-AE .pws save (gzip outer + per-record zlib streams).

Each record we have seen starts with three little-endian uint32s, then a zlib stream:
    <type> <second> <third> 78da.....
This walks the chain and prints type + both fields + compressed/decompressed sizes,
and flags any record whose declared sizes look inconsistent (truncation detector).
"""
import gzip
import struct
import sys
import zlib


def walk(path: str, limit: int = 30) -> None:
    raw = open(path, "rb").read()
    data = gzip.decompress(raw)
    print(f"\n== {path.split('/')[-1]}  压缩={len(raw)}  解压={len(data)}")
    off = 0
    n = 0
    while off + 12 <= len(data) and n < limit:
        t, a, b = struct.unpack("<III", data[off:off + 12])
        body = data[off + 12:]
        try:
            d = zlib.decompressobj()
            out = d.decompress(body)
            out += d.flush()
            used = len(body) - len(d.unused_data)
        except zlib.error as exc:
            print(f"  [{n:02d}] off={off:8d} type={t:5d} a={a:6d} b={b:6d}  zlib 解压失败: {exc}")
            break
        flag = ""
        if a != len(out) and b != len(out):
            flag = f"  <-- 两个尺寸字段都≠解压长度({len(out)})"
        print(f"  [{n:02d}] off={off:8d} type={t:5d} a={a:6d} b={b:6d} 压缩={used:8d} 解压={len(out):8d}{flag}")
        if used == 0:
            break
        off += 12 + used
        n += 1
    print(f"  ...共走到 {n} 条记录，末尾偏移 {off}/{len(data)}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            walk(p)
        except Exception as exc:  # keep going through the list
            print(f"\n== {p}: 失败 {type(exc).__name__}: {exc}")
