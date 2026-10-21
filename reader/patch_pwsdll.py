"""patch_pwsdll.py — 给 pwsdll.dll 打补丁

补丁 1（len_check）：跳过"解压长度不足"校验
  0x100028c6: 73 0f   jae 0x100028d7   →   eb 0f   jmp 0x100028d7
  效果：改动后压缩流比原长稍短时也能载入（原来直接报
        "Restore size larger than expected"）。

补丁 2（len_check_gt）：跳过"解压长度超出"校验
  0x100028b5: 0f 87 d7 02 00 00   ja 0x10002b92  →  90*6
  效果：压缩流变长时也放行。

用法：
  python3 patch_pwsdll.py /path/to/pwsdll.dll len          # 只打长度不足
  python3 patch_pwsdll.py /path/to/pwsdll.dll both         # 两个都打
  python3 patch_pwsdll.py /path/to/pwsdll.dll restore      # 还原
"""
import hashlib
import os
import shutil
import sys

BASE = 0x10001000     # .text 段 VA
FOFF = 0x1000         # .text 段文件偏移

PATCHES = {
    # name: (file_offset, expected_bytes, new_bytes, desc)
    "len_lt": (0x100028c6 - BASE + FOFF, bytes.fromhex("730f"),
               bytes.fromhex("eb0f"),
               "跳过解压长度不足校验 (jae->jmp)"),
    "len_gt": (0x100028b5 - BASE + FOFF, bytes.fromhex("0f87d7020000"),
               bytes.fromhex("909090909090"),
               "跳过解压长度超额校验 (ja->nop)"),
}

BACKUP = "/root/.hermes/profiles/witp/workspace/witp-mcp-out/pwsdll.dll.orig"


def main():
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "both"

    if mode == "restore":
        if not os.path.exists(BACKUP):
            print("!! 没有备份", BACKUP)
            return 1
        shutil.copy(BACKUP, path)
        print("已还原自", BACKUP)
        print("md5:", hashlib.md5(open(path, "rb").read()).hexdigest())
        return 0

    if not os.path.exists(BACKUP):
        shutil.copy(path, BACKUP)
        print("已备份 ->", BACKUP)

    data = bytearray(open(path, "rb").read())
    names = ["len_lt", "len_gt"] if mode == "both" else [mode]
    for n in names:
        off, exp, new, desc = PATCHES[n]
        cur = bytes(data[off:off + len(exp)])
        print(f"[{n}] off=0x{off:x} 当前={cur.hex(' ')} 期望={exp.hex(' ')}")
        if cur == new:
            print(f"     已是补丁状态，跳过")
            continue
        if cur != exp:
            print(f"     !! 字节不匹配，拒绝打补丁")
            continue
        data[off:off + len(new)] = new
        print(f"     ✓ 已修改 -> {new.hex(' ')}  ({desc})")

    open(path, "wb").write(data)
    print("写入完成，md5:", hashlib.md5(bytes(data)).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
