"""find_follow.py — 用界面操作 + 全内存差分定位 Follow TF / Patrol Zone 字段

步骤：
  1. dump 全可写段
  2. 界面设置 Follow TF（或 Patrol Zone）
  3. 再 dump，差分
  4. 差异位置即字段

前提：面板已打开到 TF 详情。本脚本只做 dump/diff。
"""
import os
import pickle
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw

CACHE = "/tmp/follow_dump.pkl"


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def dump():
    pid = pid_of()
    segs = {}
    fd = memrw.open_mem(pid)
    try:
        for s, e, perm, name in memrw.regions(pid):
            if "rw" not in perm or (e - s) < (1 << 20):
                continue
            try:
                os.lseek(fd, s, os.SEEK_SET)
                b = os.read(fd, e - s)
            except OSError:
                continue
            if b:
                segs[s] = b
    finally:
        os.close(fd)
    return pid, segs


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    pid, segs = dump()
    print(f"PID={pid} 段数={len(segs)} 共 {sum(len(b) for b in segs.values())//1024//1024}MB")

    if mode == "before":
        with open(CACHE, "wb") as f:
            pickle.dump({"pid": pid, "segs": segs}, f)
        print("基线已存")
        return

    with open(CACHE, "rb") as f:
        prev = pickle.load(f)
    if prev["pid"] != pid:
        print(f"PID 变了 ({prev['pid']}→{pid})，基线失效")
        return

    print("\n差异:")
    total = 0
    for base, old in prev["segs"].items():
        new = segs.get(base)
        if not new or len(new) != len(old):
            continue
        n = len(old)
        i = 0
        while i < n:
            if old[i] != new[i]:
                s = i
                while i < n and old[i] != new[i] and i - s < 32:
                    i += 1
                total += 1
                print(f"  {base+s:#010x} len={i-s:<3} {old[s:i].hex()} -> {new[s:i].hex()}")
            else:
                i += 1
    print(f"\n共 {total} 个差异区间")


if __name__ == "__main__":
    main()
