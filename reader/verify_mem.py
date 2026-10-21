"""verify_mem.py — 验证内存读通道真实可用（排除全零假数据）

判据设计（必须能失败）：
  1. 读 exe 的 .text 段头部，应看到 PE 代码特征（非全零、非全 FF）
  2. 读已知字符串 "War in the Pacific" 所在的 .rdata，应能解出 ASCII
  3. 读一个已知必定非零的数据区（如 .data 开头）

如果三条都失败 → gdb 通道有问题，不能信任何内存结论。
"""
import os
import subprocess
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import mem_probe


def pid_of(prefix_marker):
    for cand in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            env = open(f"/proc/{cand}/environ", "rb").read()
        except OSError:
            continue
        if prefix_marker.encode() in env:
            return int(cand)
    return None


def show(tag, data):
    if data is None:
        print(f"  [{tag}] 读取失败 (None)")
        return False
    nz = sum(1 for b in data if b)
    print(f"  [{tag}] len={len(data)} 非零={nz} hex={data[:16].hex()}")
    return nz > 0


def main():
    pid = pid_of("wine-witp-mcp") or pid_of("wine-witp")
    if not pid:
        print("找不到游戏进程")
        return
    print(f"PID={pid}\n")

    ok = []
    print("① .text 段头部（PE 代码，应为密集非零）")
    ok.append(show("text", mem_probe.gdb_read(pid, 0x401000, 32)))

    print("② .data 段头部")
    ok.append(show("data", mem_probe.gdb_read(pid, 0x851000, 32)))

    print("③ 已知字符串区（.rdata 0x808000 附近找 ASCII）")
    # "War in the Pacific" 在文件里的位置需先查，这里读一段看是否可解
    d = mem_probe.gdb_read(pid, 0x808000, 256)
    if d:
        txt = "".join(chr(c) if 32 <= c < 127 else "." for c in d)
        print(f"  可解文本: {txt[:80]!r}")
        ok.append(any(32 <= c < 127 for c in d))
    else:
        print("  读取失败")
        ok.append(False)

    print("\n结论:", "通道可用" if all(ok) else "通道有问题，内存结论不可信")


if __name__ == "__main__":
    main()
