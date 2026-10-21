#!/usr/bin/env bash
# 批量测试候选偏移：改 → 载入 → 截图 → OCR
set -u
WS=/root/.hermes/profiles/witp/workspace
SAVE="/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral's Edition/SAVE"
PREF=/root/.wine-witp-mcp/prefix
GAMEDIR="$SAVE/../"
export WITP_VNC_PORT=5901 DISPLAY=:97

kill_game() {
  for p in $(pgrep -f "War in the Pacific Admiral Edition.exe"); do
    cwd=$(readlink /proc/$p/cwd 2>/dev/null)
    case "$cwd" in *wine-witp-mcp*) kill -9 $p 2>/dev/null ;; esac
  done
  sleep 2
}

launch() {
  cd "$GAMEDIR" && WINEPREFIX=$PREF DISPLAY=:97 HOME=/root LANG=en_US.UTF-8 \
    LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
    WINEDLLOVERRIDES="midimap=d,quartz=d" \
    nohup wine "War in the Pacific Admiral Edition.exe" >/tmp/witp_run.log 2>&1 &
  sleep 30
}

loadsave() {
  python3 "$WS/witp_vncclick2.py" 620 168 click >/dev/null; sleep 1
  python3 "$WS/witp_vncclick2.py" 718 634 click >/dev/null; sleep 1
  python3 "$WS/witp_vncclick2.py" 718 634 click >/dev/null; sleep 5
  python3 "$WS/witp_vncclick2.py" 65 220 click >/dev/null; sleep 1
  python3 "$WS/witp_vncclick2.py" 336 570 click >/dev/null; sleep 16
}

check_tf7() {
  python3 "$WS/witp_vnckey2.py" t >/dev/null 2>&1; sleep 3
  python3 "$WS/witp_vncclick2.py" 250 330 click >/dev/null; sleep 1
  python3 "$WS/witp_vncclick2.py" 250 330 click >/dev/null; sleep 5
  import -window root /tmp/_chk.png
  tesseract /tmp/_chk.png - --psm 11 2>/dev/null | grep -iE "retire|remain" | head -2
}

for OFF in "$@"; do
  echo "===== 测试 off$OFF ====="
  kill_game
  cd /root/.hermes/profiles/witp/workspace/witp-reader
  python3 brute_flags.py test "$OFF" 1 "/tmp/flag_$OFF.pws" || continue
  rm -f "$SAVE"/*.pws
  cp "/tmp/flag_$OFF.pws" "$SAVE/wpae001.pws"
  launch
  loadsave
  check_tf7
done
