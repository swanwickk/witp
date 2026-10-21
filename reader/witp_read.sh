#!/bin/bash
# WitP-AE 读层入口：一条命令读存档 → 出 JSON + 中文态势简报
#   用法: witp_read.sh [存档路径]     不给参数则自动取游戏 SAVE 目录里最新的 .pws
# 依赖：Wine 内 32 位 Python（C:\py32）+ 游戏目录里的 pwsdll.dll + 本目录下的 pywitpaescraper 副本
#
# ★2026-09-25 根治「并发写导致 state JSON 脏化」★
#   病象：witp-watcher(服务) 与 staff --save / 看板 会**并发运行读层**；
#        旧实现开头就 `rm -rf state/` 再往里写，两进程互相删写 →
#        产出「完整 JSON + 尾部残留半段」的脏文件（实测 airgroups.json 尾部多 81KB），
#        感知层 json.load 抛 Extra data → 参谋部**静默失明**（搜索方案/机队数据全空，却不报错）。
#   三处根治：
#     ① **flock 串行化**：同一时刻只允许一个读层实例；后来者等锁。
#     ② **新鲜度复用**：若 state/ 已是同一存档（路径+mtime）的成品，直接跳过重读（省时且免竞争）。
#     ③ **原子切换**：先写 state.new/，再目录 rename 换入，读者永远看不到半成品。
set -u
GAME_WIN="Z:\\root\\.wine-witp\\drive_c\\1108r9\\War in the Pacific Admiral's Edition"
GAME_NIX="/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition"
READER="/root/.hermes/profiles/witp/workspace/witp-reader"
REPO="$READER/pywitpaescraper"
OUT="$READER/state"
TMP="$READER/state.new"
OLD="$READER/state.old"
LOCK="$READER/.read.lock"
MARK="$OUT/.source"

# 1) 选存档
SAVE_NIX="${1:-}"
if [ -z "$SAVE_NIX" ]; then
  # ★ 必须取"最新状态"存档，而非固定的 wpae002 ★
  # 引擎结算后依次写 wpae002.pws(PreTurnSave=旧) 与 wpae000.pws(Autosave=新)；
  # 固定读 wpae002 会让态势永远落后一回合。故按 mtime 取最新。
  SAVE_NIX=$(ls -t "$GAME_NIX/SAVE/"*.pws 2>/dev/null | head -1)
fi
if [ -z "$SAVE_NIX" ] || [ ! -f "$SAVE_NIX" ]; then
  echo "找不到存档；请先在游戏里过一回合（引擎会写 wpae002.pws），或显式给出存档路径。" >&2
  exit 1
fi
SAVE_WIN='Z:'"${SAVE_NIX//\//\\\\}"
BASE=$(basename "$SAVE_NIX"); MTIME=$(stat -c %y "$SAVE_NIX" | cut -d. -f1)
STAMP="$SAVE_NIX|$MTIME"

# 2) ★串行化★：同一时刻只跑一个读层实例
exec 9>"$LOCK"
if ! flock -w 900 9; then
  echo "另一个读层实例仍在运行，等待 900s 超时 → 放弃本次重读。" >&2
  exit 1
fi

# ★2026-10-11 修（换阵营后读层不更新的真因）★
#   旧缓存判据只用「存档路径|mtime」。换阵营（重开一局、同一存档名 wpae003.pws
#   但玩家从盟军变日军）时，若 mtime 恰好相同/被复用，就会跳过重读，
#   于是 side.txt 与 state/ 一直停留在**旧阵营** ⇒ 读层给出另一方的编队，
#   且**不会报错**（两侧都有编队）。⇒ 缓存键加入「当前实际阵营」。
#   ★2026-10-17 修★ 缓存键必须用**最终判定出的阵营**（SIDE_NAME），
#   不能再用顶栏检测结果——否则 WITP_SIDE 强制切阵营时缓存键不变，
#   会命中缓存而跳过重读（热座下同一存档要读两个视角，必踩此坑）。
#   ⇒ 阵营判定块整体上移到缓存检查之前。

# ★2026-10-02 修复★ 阵营判定改为「**顶栏自动检测优先**」。
#   病象：side.txt 由人工写入，与实际在玩的一方脱节（实测屏幕是 ALLIED PLAYER、
#         side.txt 却是 japan）⇒ 读层给出的编队/舰船与屏幕完全对不上，
#         而两侧都有编队，**不会报错**，只会静默给出另一方的数据。
#   对策：优先自动检测顶栏 PLAYER 字段；检测失败才回退 side.txt；再失败回退 ALLIED。
SIDE_FILE="$READER/side.txt"
SIDE_NOW=""
# ★2026-10-17 新增：WITP_SIDE 环境变量强制指定阵营（热座模式必需）★
#   热座（HEAD TO HEAD）下同一台机轮流扮演双方，但游戏顶栏随时只显示"当前正在下令的一方"，
#   而读层需要能读【任意一方】的视角（例如：盟方下令阶段要评估日军态势）。
#   顶栏自动检测优先会把手动设置覆盖掉 ⇒ 必须提供显式覆盖入口。
#   用法：WITP_SIDE=JAPAN bash witp_read.sh <存档>
#   优先级：WITP_SIDE > 顶栏自动检测 > side.txt > 缺省 ALLIED
FORCED=$(echo "${WITP_SIDE:-}" | tr -d ' \n\r' | tr 'a-z' 'A-Z')
if [ -n "$FORCED" ]; then
  case "$FORCED" in
    JAPAN|JAPANESE|IJN|IJA) SIDE_NOW="JAPAN" ;;
    ALLIED|US|USA|ALLIES)   SIDE_NOW="ALLIED" ;;
  esac
  [ -n "$SIDE_NOW" ] && SIDE_FROM="WITP_SIDE 强制指定"
fi
if [ -z "$SIDE_NOW" ]; then
  DETECTED=$(env -u LANG -u LC_ALL LANG=C.UTF-8 PYTHONIOENCODING=utf-8 \
               python3 "$READER/detect_side.py" 2>/dev/null | tr -d ' \n\r' | tr 'a-z' 'A-Z')
  case "$DETECTED" in
    JAPAN|ALLIED) SIDE_NOW="$DETECTED"; SIDE_FROM="顶栏自动检测" ;;
  esac
fi
if [ -z "$SIDE_NOW" ]; then
  if [ -f "$SIDE_FILE" ]; then
    SIDE_NOW=$(tr -d ' \n\r' < "$SIDE_FILE" | tr 'a-z' 'A-Z')
    SIDE_FROM="$SIDE_FILE（自动检测失败，回退）"
  else
    SIDE_NOW="ALLIED"
    SIDE_FROM="缺省（无 side.txt 且检测失败）"
  fi
fi
case "$SIDE_NOW" in
  JAPAN|JAPANESE|IJN|IJA) SIDE_FLAG="--japan"; SIDE_NAME="JAPAN" ;;
  *)                      SIDE_FLAG="--allied"; SIDE_NAME="ALLIED" ;;
esac
echo "读层阵营：$SIDE_NAME（$SIDE_FROM）" >&2

# 3) ★新鲜度复用★：已是同一存档+同一阵营的成品就直接返回
if [ -f "$MARK" ] && [ -f "$OUT/turn.json" ] && [ "$(cat "$MARK" 2>/dev/null)" = "$STAMP|$SIDE_NAME" ]; then
  echo "state/ 已是该存档（$BASE，$SIDE_NAME 视角）的最新解析结果，跳过重读。" >&2
  exit 0
fi

echo "读取存档：$BASE（$MTIME）" >&2

# 4) 调用解析器（32 位 Python + 游戏 DLL），先写临时目录
rm -rf "$TMP"; mkdir -p "$TMP"
TMP_WIN='Z:'"${TMP//\//\\\\}"
cd "$REPO" || exit 1
export DISPLAY=:98 WINEPREFIX=/root/.wine-witp HOME=/root LANG=zh_CN.GBK
export WITP_SKIP_SAMPLE_VALIDATION=1
# 顺带把检测结果写回 side.txt，便于事后追查与其它工具复用
printf '%s\n' "$(echo "$SIDE_NAME" | tr 'A-Z' 'a-z')" > "$SIDE_FILE" 2>/dev/null || true
/usr/bin/wine C:\\py32\\python.exe pywitpaescraper.py \
  --dll-dir "$GAME_WIN" \
  --start-of-day-file "$SAVE_WIN" \
  --end-of-day-file "$SAVE_WIN" \
  $SIDE_FLAG \
  --output-dir "$TMP_WIN" \
  --log-level WARNING > "$READER/state.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
  echo "解析失败（退出码 $rc），日志尾部：" >&2
  tail -12 "$READER/state.log" >&2
  rm -rf "$TMP"
  exit $rc
fi

# 5) 生成中文简报（写进临时目录，随目录一起换入）
unset LANG LC_ALL; export LANG=C.UTF-8
python3 "$READER/witp_summarize.py" "$TMP" "$(dirname "$SAVE_NIX")" | tee "$TMP/brief.txt" >/dev/null

# 6) ★原子切换★：state.old ← state ← state.new
rm -rf "$OLD" 2>/dev/null
[ -d "$OUT" ] && mv "$OUT" "$OLD"
mv "$TMP" "$OUT"
printf '%s' "$STAMP" > "$OUT/.source"
rm -rf "$OLD" 2>/dev/null
echo "state/ 已更新（原子切换）；来源标记：$BASE" >&2
