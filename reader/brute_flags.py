"""brute_flags.py — 暴力枚举 TF 结构里的标志字节，找出控制 Retirement 的那个

做法：一次只改一个偏移（0/1 互换），载入游戏看 Retirement 行文字是否变。
自动化：改 → 载入 → 截图 OCR → 比对。

因为每次载入约 40 秒，50 个候选要 30+ 分钟。先缩小范围：
PWSTaskGroup 里 26 个 TF 上"既有 0 又有 1"的偏移才是候选。

用法：
  python3 brute_flags.py list          # 列出候选偏移
  python3 brute_flags.py test <off>    # 生成测试档
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pwsfile import read_container
from pwspack import pack_container

BASE = "/root/.hermes/profiles/witp/workspace/witp-mcp-out/testinst-final/wpae001.pws"
TF = 70
TF_SZ = 556
SLOT = 7          # TF7 = MO Landing Force，界面显示 Remain on Station


def tf_block(path):
    c = read_container(path)
    return c, next(r for r in c["records"] if r["type"] == TF)


def candidates():
    c, rec = tf_block(BASE)
    d = rec["data"]
    alive = [s for s in range(4000)
             if struct.unpack_from("<i", d, s * TF_SZ + 44)[0] > 0]
    out = []
    for off in range(TF_SZ):
        vals = {d[s * TF_SZ + off] for s in alive}
        # 只要 0/1 两值、且都出现过 → 布尔标志候选
        if vals == {0, 1}:
            out.append(off)
        elif vals <= {0, 1} and len(vals) == 1:
            pass   # 全同值，改了不好判断
    return out


def make_test(off, val, out_path):
    c, rec = tf_block(BASE)
    d = bytearray(rec["data"])
    o = SLOT * TF_SZ
    old = d[o + off]
    d[o + off] = val
    rec["data"] = bytes(d)
    pack_container(c["records"], out_path, allow_len_change=True)
    return old, val


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "list":
        cs = candidates()
        print(f"候选布尔标志偏移（{len(cs)} 个）:")
        print(" ", cs)
    elif cmd == "test":
        off = int(sys.argv[2])
        val = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        out = sys.argv[4] if len(sys.argv) > 4 else "/tmp/flagtest.pws"
        old, new = make_test(off, val, out)
        print(f"TF{SLOT} off{off}: {old} -> {new}  => {out}")
