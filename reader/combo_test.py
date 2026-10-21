"""combo_test.py — 组合改动多个候选字节，一次性验证哪个控制 Retirement

做法：以 TF7 基线档为准，把一组候选偏移同时设成相反值，
载入后看界面 Retirement 是否翻转。命中后再二分缩小。

用法：
  python3 combo_test.py gen <out.pws> off1,off2,...   # 生成测试档
"""
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
from pwsfile import read_container
from pwspack import pack_container

BASE = "/root/.hermes/profiles/witp/workspace/witp-mcp-out/testinst-final/wpae001.pws"
TF_SZ = 556
SLOT = 7


def gen(out_path, offs):
    c = read_container(BASE)
    rec = next(r for r in c["records"] if r["type"] == 70)
    d = bytearray(rec["data"])
    o = SLOT * TF_SZ
    info = []
    for off in offs:
        old = d[o + off]
        d[o + off] = 1 if old == 0 else 0
        info.append((off, old, d[o + off]))
    rec["data"] = bytes(d)
    pack_container(c["records"], out_path, allow_len_change=True)
    return info


if __name__ == "__main__":
    out = sys.argv[1]
    offs = [int(x) for x in sys.argv[2].split(",")]
    for off, a, b in gen(out, offs):
        print(f"off{off}: {a} -> {b}")
    print("saved", out)
