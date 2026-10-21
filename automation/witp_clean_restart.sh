#!/bin/bash
# WitP 显示栈 + 游戏服务「干净重建」（可复用）
# 铁律：绝不 kill 单个窗口（0x600001 是 Wine 虚拟桌面宿主，kill 它会崩游戏）
# 正确做法：停服务 → 清全部 wine 进程 → 重建 Xvnc → 起 openbox → 起游戏
set -u
echo "=== 1) 停服务 ==="
systemctl stop witp-game-en 2>/dev/null
systemctl stop witp-openbox98 2>/dev/null
sleep 2

echo "=== 2) 清理全部 wine 进程（按 /proc/<pid>/exe，不用 pkill -f）==="
for p in $(ls /proc | grep -E '^[0-9]+$'); do
  exe=$(readlink /proc/$p/exe 2>/dev/null)
  case "$exe" in
    *wine*|*Pacific*) kill -9 "$p" 2>/dev/null ;;
  esac
done
sleep 3
left=$(for p in $(ls /proc | grep -E '^[0-9]+$'); do
  exe=$(readlink /proc/$p/exe 2>/dev/null)
  case "$exe" in *wine*|*Pacific*) echo x ;; esac
done | wc -l)
echo "  wine 残余: $left"

echo "=== 3) 重建 Xvnc（清掉陈旧窗口 id）==="
systemctl restart witp-xvnc98d 2>/dev/null || echo "  (xvnc restart 失败)"
sleep 3
DISPLAY=:98 xdpyinfo 2>&1 | grep -o 'dimensions.*' | head -1

echo "=== 4) 起 openbox ==="
systemctl start witp-openbox98
sleep 2
echo "  openbox=$(systemctl is-active witp-openbox98)"

echo "=== 5) 起游戏服务 ==="
systemctl reset-failed witp-game-en 2>/dev/null
systemctl start witp-game-en
sleep 10
echo "  game=$(systemctl is-active witp-game-en) win=$(DISPLAY=:98 xdotool search --name 'War in the Pacific' 2>/dev/null | head -1)"
