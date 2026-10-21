#!/usr/bin/env python3
"""输入投递通道自检：会「静默吞掉点击」的前置条件是否都满足。

用法（在已启动游戏、DISPLAY 已导出的 shell 里）：

    DISPLAY=:98 python3 input_probe.py [workspace_dir]

为什么需要它：这些前置条件（窗口偏移 / 大位移 / 节拍 / 坐标单位）**都不报错**，
都只表现为「我点了，它没反应」。不先证明通道通，后面所有导航、
落子、读数的排查都建在沙地上。

它依次验证：
  ① 窗口偏移   读 `Wine Desktop` 的 +X+Y，确认换算基准（不说硬编码值）
  ② 大位移     连续 4 次点击是否**每次都**被游戏接受
  ③ 节拍       每次点击的间隔（默认 6.5s）

读数 = 顶栏 `Hex`（视野中心格），**读数发生变化即该次点击被接受**。

判据：
  只有第 1 次生效，后 3 次不动  → ② 没做对：指针没大位移，点击被静默丢弃
  4 次全不动                    → ① 偏移错 / ④ 坐标单位错 / 焦点丢失（先查 openbox 在不在）
  进程中途消失                  → ③ 节拍太急（调大 --interval 重跑）
  4 次全变                      → 通道可用，可以开始导航

⚠ 本脚本**故意走生产入口** `witp_nav.click()`（它自带窗口偏移换算），
  而不是另写一套坐标。**新写排障脚本时也请照做**：绕过统一入口直接调底层注入脚本，
  很容易把「游戏坐标」当「屏幕坐标」传进去，点击全部落在窗口之外，
  于是读出「这条通道不通」的**假否定**——而且所有候选通道会一起假否定、
  互相印证，比真的不通还难识破。详见 perception-channels.md「输入投递通道」④。
"""

import argparse
import os
import re
import subprocess
import sys
import time

# 游戏窗口标题（xwininfo 里报的名字）
WIN_TITLE = 'Wine Desktop'


def win_offset():
    """读游戏窗口左上角在屏幕上的偏移。绝不假设 (0,0)。"""
    out = subprocess.run(['xwininfo', '-root', '-children'],
                         capture_output=True, text=True, timeout=20).stdout
    for line in out.splitlines():
        if WIN_TITLE not in line:
            continue
        m = re.search(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', line)
        if m:
            return int(m.group(3)), int(m.group(4))
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workspace', nargs='?',
                    default=os.path.expanduser('~/.hermes/workspace'))
    ap.add_argument('--interval', type=float, default=6.5,
                    help='点击间隔秒数，默认 6.5（实测下限）')
    args = ap.parse_args()

    sys.path.insert(0, args.workspace)
    try:
        from witp_nav import click, read_topbar, ctr
    except ImportError as e:
        print(f'✗ 无法导入 witp_nav（workspace={args.workspace}）: {e}')
        return 2

    ox, oy = win_offset()
    if ox is None:
        print(f'✗ xwininfo 里找不到 {WIN_TITLE!r} —— 窗口没建立或游戏没在跑')
        print('  → 先按 perception-channels.md 第四节「存活判定」查进程与窗口')
        return 2
    print(f'① 窗口偏移 = ({ox},{oy})'
          f'{"  ← 不是 (0,0)，所有点击必须加这个偏移" if (ox, oy) != (0, 0) else ""}')

    # 四个落在不同方位的探针点（相对画面中心），只要求“彼此位置不同”
    probes = [(212, 300), (800, 300), (300, 600), (700, 520)]
    print(f'③ 节拍 = {args.interval}s，共 {len(probes)} 次点击')

    start = read_topbar().get('hx')
    print(f'   起始读数: {start}')

    fired = 0
    prev = start
    for i, (px, py) in enumerate(probes, 1):
        click(px, py)                      # click() 内部已含大位移 + 节拍
        time.sleep(0.4)
        now = read_topbar().get('hx')
        moved = now is not None and now != prev
        fired += 1 if moved else 0
        print(f'   第{i}次 {px,py} → {now}  {"✓ 生效" if moved else "✗ 无变化"}')
        prev = now
        if 1 <= i < len(probes):
            time.sleep(max(0.0, args.interval - 0.4))

    print()
    if fired == len(probes):
        print(f'✓ ② 通道可用：{fired}/{len(probes)} 次点击全部生效')
        return 0
    if fired == 1:
        print(f'✗ 只有第 1 次生效（{fired}/{len(probes)}）'
              ' ⇒ 指向 ② 大位移：确认 click() 里“移远→停→移目标→停→点”完整执行，'
              '且“移远”的幅度足够（±70px 内的小抖动实测无效）')
        return 1
    print(f'✗ 几乎全不动（{fired}/{len(probes)}）'
          ' ⇒ 指向 ① 偏移 / ④ 坐标单位 / 焦点三类：核对 win_offset 的换算、'
          '确认点击确实加进了偏移（绕过统一入口直接调底层注入脚本时，'
          '把游戏坐标当屏幕坐标传会把整批点击丢到窗口外，'
          '表现与「控件不响应」完全一样），并确认 openbox 在跑'
          '（无窗口管理器时按键/焦点全丢）')
    return 1


if __name__ == '__main__':
    sys.exit(main())
