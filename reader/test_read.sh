#!/bin/bash
# 读档测试器：test_read.sh <存档(nix路径)> <pwsdll所在目录(nix路径)> <输出目录>
# 用 Wine 内 32 位 Python + 指定 pwsdll 版本 尝试解析存档，成功则列出产出的 JSON
set -u
SAVE_NIX="${1:?存档路径}"
DLL_NIX="${2:?pwsdll 目录}"
OUT="${3:-/tmp/readtest-out}"
READER=/root/.hermes/profiles/witp/workspace/witp-reader
REPO="$READER/pywitpaescraper"
SAVE_WIN='Z:'"${SAVE_NIX//\//\\}"
DLL_WIN='Z:'"${DLL_NIX//\//\\}"
OUT_WIN='Z:'"${OUT//\//\\}"
rm -rf "$OUT"; mkdir -p "$OUT"
cd "$REPO" || exit 1
export DISPLAY=:98 WINEPREFIX=/root/.wine-witp HOME=/root LANG=zh_CN.GBK LC_ALL=zh_CN.GBK
export WITP_SKIP_SAMPLE_VALIDATION=1
timeout 300 /usr/bin/wine C:\\py32\\python.exe pywitpaescraper.py \
  --dll-dir "$DLL_WIN" \
  --start-of-day-file "$SAVE_WIN" --end-of-day-file "$SAVE_WIN" \
  --allied --output-dir "$OUT_WIN" --log-level WARNING > "$OUT/../readtest.log" 2>&1
rc=$?
n=$(ls "$OUT" 2>/dev/null | wc -l)
echo "  退出码=$rc 产出文件=$n"
if [ "$n" -gt 0 ]; then ls "$OUT"; else tail -4 "$OUT/../readtest.log" 2>/dev/null; fi
