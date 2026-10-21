"""verify_ship.py — 验证 Ship 数组基址

候选：0x1a14378、0xb2adcb0（均 6/6 舰名吻合）

判据：对存档所有舰船，检查内存同槽的名称是否完全一致。
      名称是唯一字符串，比数值判据可靠得多。
"""
import os
import struct
import sys

sys.path.insert(0, "/root/.hermes/profiles/witp/workspace/witp-reader")
import memrw
import pwsfile

SH = 464


def pid_of():
    for c in os.popen("pgrep -f 'Pacific Admiral Edition.exe'").read().split():
        try:
            if b"wine-witp-mcp" in open(f"/proc/{c}/environ", "rb").read():
                return int(c)
        except OSError:
            pass
    return None


def save_ships(path):
    d = pwsfile.record_by_len(path, 9280000)
    out = {}
    if not d:
        return out
    for s in range(20000):
        b = s * SH
        nm = d[b:b + 20].split(b"\0")[0]
        if len(nm) < 2 or not all(32 <= c < 127 for c in nm):
            continue
        out[s] = nm.decode("ascii")
    return out


def main():
    save = sys.argv[1]
    ships = save_ships(save)
    pid = pid_of()
    fd = memrw.open_mem(pid)

    for base in (0x1a14378, 0xb2adcb0):
        print(f"\n=== 基址 {base:#x} ===")
        ok = 0
        bad = []
        for s, nm in ships.items():
            d = memrw.read_mem(pid, base + s * SH, 20, fd)
            if not d:
                bad.append((s, "读失败"))
                continue
            mem = d.split(b"\0")[0].decode("ascii", "replace")
            if mem == nm:
                ok += 1
            else:
                bad.append((s, f"mem={mem!r} save={nm!r}"))
        print(f"名称吻合 {ok}/{len(ships)}")
        if bad and ok < len(ships) * 0.5:
            print(f"  不吻合示例: {bad[:3]}")
        elif bad:
            print(f"  不吻合 {len(bad)} 个，示例: {bad[:3]}")
        else:
            print("  ★ 全部吻合")

    os.close(fd)


if __name__ == "__main__":
    main()
