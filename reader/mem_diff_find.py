"""mem_diff_find.py — 通过「操作前后内存差分」定位字段（不依赖任何结构假设）

为什么这是唯一可靠的定位法：
  猜基址/猜偏移全部失败（0x1a143ac 全零、0x1976700 是指针数组、
  存档偏移映射到内存零命中）。根因是运行时结构与存档**不同构**。

  那就不要假设结构 —— 直接观测：
    ① 操作前 dump 一大片内存
    ② 用界面做一次操作（唯一的键鼠用途）
    ③ 操作后 dump 同一片
    ④ 差出来的字节就是该操作真正改动的字段

  这是"黑盒差分"，不预设任何偏移，因此不可能被错误假设误导。

用法:
  python3 mem_diff_find.py before          # 存基线
  # ... 做一次界面操作 ...
  python3 mem_diff_find.py after           # 对比
"""
import os
import pickle
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe

LO = 0x860000
HI = 0xF000000
CACHE = "/tmp/memdump.pkl"


def pid_of():
    best = None
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            env = open(f"/proc/{cand}/environ", "rb").read()
        except OSError:
            continue
        if b"wine-witp-mcp" in env:
            # 取 PID 最大的（最新启动的那个）
            best = max(best or 0, int(cand))
    return best


def dump():
    pid = pid_of()
    if not pid:
        print("找不到进程")
        return None, None
    blob = mem_probe.gdb_read(pid, LO, HI - LO)
    if not blob or len(blob) < (HI - LO):
        print(f"读取不完整 {len(blob) if blob else 0}")
        return pid, None
    return pid, blob


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    pid, blob = dump()
    if blob is None:
        return

    if mode == "before":
        with open(CACHE, "wb") as f:
            pickle.dump({"pid": pid, "lo": LO, "blob": blob}, f)
        nz = sum(1 for b in blob[::64] if b)
        print(f"基线已存: PID={pid} {len(blob)//1024//1024}MB 抽样非零={nz}/{len(blob)//64}")
        return

    if not os.path.exists(CACHE):
        print("没有基线，先跑 before")
        return
    with open(CACHE, "rb") as f:
        prev = pickle.load(f)
    if prev["pid"] != pid:
        print(f"⚠ PID 变了 ({prev['pid']} → {pid})，基线失效")
        return

    old = prev["blob"]
    n = min(len(old), len(blob))
    diffs = []
    i = 0
    while i < n:
        if old[i] != blob[i]:
            s = i
            while i < n and old[i] != blob[i] and i - s < 64:
                i += 1
            diffs.append((s, i))
        else:
            i += 1

    print(f"差异区间 {len(diffs)} 个")
    for s, e in diffs[:40]:
        o = old[s:e].hex()
        nw = blob[s:e].hex()
        print(f"  {LO+s:#010x} len={e-s:<3} {o} -> {nw}")


if __name__ == "__main__":
    main()
