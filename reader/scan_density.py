"""scan_density.py — 找出真正装游戏数据的可写区间

判据：逐块统计非零字节比例。
  · 全零 → 未使用
  · 稀疏非零 → 可能是数据
  · 高度非零 → 代码/常量

先看哪些区间有内容，再在最有希望的区间里定位 TF 结构。
"""
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pid:
        import os
        for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
            try:
                if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                    pid = int(c)
            except OSError:
                pass
    print(f"PID={pid}\n")

    fd = memrw.open_mem(pid)
    rows = []
    try:
        for s, e, perm, name in memrw.regions(pid):
            if "rw" not in perm:
                continue
            size = e - s
            if size < 65536:
                continue
            # 采样：每 4KB 取 256 字节
            total = nz = 0
            step = 4096
            for off in range(0, size, step):
                d = memrw.read_mem(pid, s + off, min(256, size - off), fd)
                if not d:
                    continue
                total += len(d)
                nz += sum(1 for b in d if b)
            if total:
                rows.append((nz / total, s, e, size, perm, name))
    finally:
        import os
        os.close(fd)

    rows.sort(reverse=True)
    print(f"{'非零比':>7} {'区间':>22} {'大小':>9}  名称")
    for r, s, e, size, perm, name in rows:
        if r < 0.01:
            continue
        print(f"{r*100:6.1f}% {s:#010x}-{e:#010x} {size/1048576:8.1f}MB  {name[:40]}")


if __name__ == "__main__":
    main()
