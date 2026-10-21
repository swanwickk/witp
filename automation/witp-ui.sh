#!/bin/bash
# WitP-AE 界面操作脚本库（每个函数 = 一次实测验证的操作）
# 用法: source witp-ui.sh && witp_screenshot
# 所有坐标基于 1400x1050 的 X display :98，游戏窗口 1.0.6.1108r9
#   ★坐标基线(2026-09-24 实测)：屏幕=1400x1050，游戏窗口=1024x768，偏移(188,150)★
#   旧记录的 1360x768 是 2026-09-22 迁移到虚拟桌面模式【之前】的基线，已废弃。

export DISPLAY=:98
export WINEPREFIX=/root/.wine-witp
export HOME=/root
GAME_DIR="/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition"
SAVE_DIR="$GAME_DIR/SAVE"
SHOT=/tmp/witp_shot.png

# ---------- 基础设施 ----------

# 确保窗口可见（IsUnMapped 黑屏救活）+ 分辨率守护
# 【分辨率铁律 2026-09-24 修订】屏幕=1400x1050，游戏窗口=1024x768，偏移=(188,150)。
#   窗口层级：openbox frame → Wine Desktop(受管) → 游戏窗口(override-redirect, 不受管)。
#   ★ 严禁用 xrandr 改分辨率 ★ —— XRandR 模式切换会使 Wine 的 InputOnly 鼠标捕获窗口
#   与新屏幕尺寸不匹配，导致鼠标点击全部失效（键盘仍正常）。症状=点任何按钮无反应。
#   屏幕尺寸不符时：先 xrandr 确认当前模式，再用 witp_recenter 归位容器；不要盲改分辨率。
witp_check_res() {
  # 实测基线 = 1400x1050（虚拟桌面模式，保证 1024x768 窗口完整可见）
  local CUR=$(xdpyinfo | grep -oP 'dimensions:\s+\K[0-9]+x[0-9]+')
  if [ "$CUR" != "1400x1050" ]; then
    echo "[witp] ⚠ 屏幕分辨率=$CUR（基线应为1400x1050）——坐标全盘失准，勿在该状态下点击；禁止 xrandr 硬改，重启游戏进程恢复" >&2
    return 1
  fi
  return 0
}

# 【裁剪边界守卫】2026-09-24
#   窗口偏移一旦出界（OX<0 / OY<0 / 右下越界），convert -crop 的起点会伸出图像外，
#   ImageMagick 会给出错位/截断的图——把错位截图当真数据读，是本轮最贵的教训。
#   → 出界时直接报错拒拍，绝不输出可疑画面。
witp_crop_ok() {
  local SX SY
  SX=$(xdpyinfo | grep -oP 'dimensions:\s+\K[0-9]+' | head -1)
  SY=$(xdpyinfo | grep -oP 'dimensions:\s+\K[0-9]+x\K[0-9]+' | head -1)
  if [ "$WITP_OX" -lt 0 ] || [ "$WITP_OY" -lt 0 ] \
     || [ $((WITP_OX+1024)) -gt "$SX" ] || [ $((WITP_OY+768)) -gt "$SY" ]; then
    echo "[witp] ✗ 窗口偏移出界 OX=$WITP_OX OY=$WITP_OY 屏幕=${SX}x${SY} → 拒绝截图/点击" >&2
    return 1
  fi
  return 0
}

# 【归位】只允许归位 openbox 管理的 "Wine Desktop"(override-redirect=no)
#   游戏窗口本身 override-redirect=yes，openbox 不管它，对它做 windowmove 是
#   「相对父窗口移动」，会把父窗口位置和自己设的值叠加 → 越修越漂。
witp_recenter() {
  local DW=$(xdotool search --name "Wine Desktop" | head -1)
  [ -z "$DW" ] && { echo "[witp] 未找到 Wine Desktop 窗口" >&2; return 1; }
  wmctrl -i -r "$DW" -e 0,187,130,1024,768   # openbox 在 1400x1050 上的居中位
  sleep 2
  witp_sync_offset
  echo "[witp] 归位后 OX=$WITP_OX OY=$WITP_OY（期望 188,150）"
}

witp_ensure_window() {
  witp_check_res || true
  local WID=$(xdotool search --name "War in the Pacific" | head -1)
  [ -z "$WID" ] && { echo "ERROR: 无游戏窗口"; return 1; }
  local ST=$(xwininfo -id $WID | grep -c IsViewable)
  if [ "$ST" = "0" ]; then
    wmctrl -i -a $WID; sleep 2
    ST=$(xwininfo -id $WID | grep -c IsViewable)
  fi
  [ "$ST" = "1" ] && return 0 || return 1
}

# 【鼠标健康自检】点击一个已知会改变画面的位置(点地图空地)，判断鼠标是否被吞
witp_mouse_alive() {
  import -window root /tmp/_ma1.png 2>/dev/null
  xdotool mousemove 500 400 click 1
  sleep 1.2
  import -window root /tmp/_ma2.png 2>/dev/null
  local D=$(python3 -c "
from PIL import Image
a=Image.open('/tmp/_ma1.png').convert('RGB'); b=Image.open('/tmp/_ma2.png').convert('RGB')
c=0
for y in range(0,768,8):
    for x in range(0,1024,8):
        p,q=a.getpixel((x,y)),b.getpixel((x,y))
        if abs(p[0]-q[0])+abs(p[1]-q[1])+abs(p[2]-q[2])>60: c+=1
print(c)" 2>/dev/null)
  echo "[witp] 鼠标自检变化采样=$D"
  [ "${D:-0}" -gt 0 ] && return 0 || { echo "[witp] ✗ 鼠标点击无效（Wine输入窗口异常）→ 需重启游戏进程" >&2; return 1; }
}

# 截屏 + 可选OCR（输出前N行）
witp_screenshot() { import -window root $SHOT; }
witp_ocr() { convert $SHOT -resize 150% -colorspace Gray -contrast-stretch 2%x2% /tmp/_wx.png; tesseract /tmp/_wx.png - --psm 11 2>/dev/null | grep -v '^$'; }
witp_ocr_head() { witp_ocr | head -${1:-10}; }

# 获取游戏内日期（vision 式可靠法：返回如 "05/04/42"）
witp_get_date() {
  local p="${1:-$SAVE_DIR/wpae002.pws}"
  python3 - "$p" <<'PY'
import gzip, struct, zlib, re, sys
p = sys.argv[1]
try:
    raw = gzip.open(p,'rb').read()
    t,u,c = struct.unpack_from('<III', raw, 0)
    inner = zlib.decompress(raw[12:12+c])
    m = re.search(rb'Date:\s*([0-9/]+)', inner)
    print(m.group(1).decode() if m else "UNKNOWN")
except Exception as e:
    print("ERR", e)
PY
}

# ---------- 已验证的界面坐标（1108r9 英文版，屏幕基线 1400x1050，偏移(188,150)）----------
# 主菜单:
#   SCENARIO SELECTION ≈ (740,555)  → 需要点击后用 OCR 确认进入 SCENARIO MENU
#   LOAD SAVED GAME   ≈ (552,483)  → 需双击（单击只悬停高亮）
#   PREFERENCES       ≈ (576,378)
#   EXIT GAME         ≈ (586,538)
# 剧本菜单:
#   列表行: 001=217, 行距14 → 003 Coral Sea = 245；行点击用 双击(x=300, y)
#   SELECT SCENARIO 红按钮 = (336,565)
# 剧本详情页:
#   START GAME = (610,549)
#   SCENARIO MENU(返回列表) = (320,602)
# 命令阶段(地图):
#   [E] = End Orders Phase；[F9] = 下次机会进入 Orders Phase
#   战斗摘要 Done 按钮 ≈ (566,255)（vision 定位，每页位置可能微移）
# 加载页:
#   （待验证：槽位行坐标）

# ---------- 高层动作 ----------

# 双击主菜单按钮（WitP 菜单按钮单击=高亮，双击=进入）
witp_click_menu() { xdotool mousemove $1 $2 click 1 click 1; }

# 等待窗口从黑屏(unmap/结算)恢复，最多 N 秒
witp_wait_visible() {
  local max=${1:-180} WID ST
  WID=$(xdotool search --name "War in the Pacific" | head -1)
  for ((i=0;i<max/5;i++)); do
    sleep 5
    ST=$(xwininfo -id $WID 2>/dev/null | grep -c IsViewable)
    if [ "$ST" = "1" ]; then
      wmctrl -i -a $WID; sleep 1
      import -window root $SHOT 2>/dev/null
      local M=$(convert $SHOT -format "%[fx:mean]" info: 2>/dev/null)
      # 均值>0.05 认为有内容（黑屏≈0）
      if [ "$(echo "$M > 0.05" | bc -l)" = "1" ]; then return 0; fi
    fi
  done
  return 1
}

# ---------- 主菜单/子页面 布局坐标（屏幕基线 1400x1050, 1108r9英文版，实测） ----------
# GAME OPTIONS页:
#   MAIN MENU 拨杆开关 = (877,698) —— 单击即触发（红色拨杆头）
#   注意：主菜单的MAIN MENU(558,538)是另一个页面的按钮，勿混淆
witp_gamoptions_to_main() { xdotool mousemove 877 698 click 1; sleep 2.5; }

# 主菜单按钮列（x=665）：PREF=(665,496) SCENARIO=(665,568) LOAD=(665,636) 双击进入
# SAVE MENU = 载入页（含SAVE和LOAD两个标签）
witp_open_load_menu() { xdotool mousemove 665 636 click 1 click 1; sleep 2.5; }
witp_to_main_menu() { xdotool mousemove 877 698 click 1; sleep 2.5; }  # 子页面通用返回

# ============ 已验证操作固化（2026-09-22）============

# [载入存档] SAVE MENU 页：单击存档行(变绿) → 点 SELECT SAVE GAME 按钮 = 载入
#   存档行y坐标：000=158, 002=179, 003=200 左右（行距约21px，以OCR为准）
#   SELECT SAVE GAME 按钮 = (337,577)
witp_load_slot() {  # 用法: witp_load_slot 179   （参数=存档行y坐标）
  xdotool mousemove 200 $1 click 1          # 单击选中（变绿）
  sleep 1
  xdotool mousemove 337 577 click 1         # 点SELECT SAVE GAME=载入
  sleep 2
}

# [分辨率] ★已废弃切换★ 保持 1024x768（游戏原生窗口尺寸），仅检查不修改
witp_fix_res() { witp_check_res && echo "[witp] 分辨率正常 1024x768"; }

# [禁音频] 结算卡死(d3d blit+ALSA underrun)的修复，已生效无需重复
witp_disable_audio() {
  WINEPREFIX=/root/.wine-witp wine reg add "HKCU\\Software\\Wine\\Drivers" /v Audio /t REG_SZ /d "" /f
}

# [启动游戏] 含openbox检查
witp_launch() {
  pgrep -x openbox >/dev/null || (DISPLAY=:98 openbox >/tmp/openbox.log 2>&1 &)
  sleep 1
  cd "$GAME_DIR" && DISPLAY=:98 WINEPREFIX=/root/.wine-witp HOME=/root LANG=en_US.UTF-8 \
    nohup wine "War in the Pacific Admiral Edition.exe" >/tmp/witp_game.log 2>&1 &
  sleep 20
  witp_ensure_window
}

# [主菜单按钮列] x=665，双击进入（红像素扫描+vision双验证）
#   PREFERENCES=481-525 | SCENARIO SELECTION=552-596 | LOAD A SAVED GAME=618-637 | EXIT=646-662
witp_open_scenario() { xdotool mousemove 665 574 click 1 click 1; sleep 2.5; }   # 剧本选择
witp_open_load()     { xdotool mousemove 665 627 click 1 click 1; sleep 2.5; }   # 载入菜单

# [剧本选择页] 列表行001=y217 行距14 → 003 Coral Sea=y245；双击选中；SELECT=(336,565)
witp_select_coral_sea() {
  xdotool mousemove 300 245 click 1 click 1   # 双击003行
  sleep 1
  xdotool mousemove 336 565 click 1           # SELECT SCENARIO
  sleep 2
  xdotool mousemove 610 549 click 1           # START GAME
  sleep 5
}

# [读层] 出中文态势简报（需先改 witp_read.sh 路径适配英文版——已改）
witp_brief() {
  bash /root/.hermes/profiles/witp/workspace/witp-reader/witp_read.sh "$SAVE_DIR/wpae002.pws" 2>&1 | head -60
}

# ★[过回合] 2026-09-23 关键修复★
# 按 E 后会弹出确认框 "End the Orders Phase? YES / NO"（YES=(508,422)），
# 必须点 YES 才会真正结算——这就是之前"卡死"(CPU空转)的真因！
# 结算完成后引擎依次写 wpae002.pws(PreTurnSave=旧状态) 与 wpae000.pws(Autosave=新状态)。
witp_end_turn() {
  python3 /root/.hermes/profiles/witp/workspace/witp_vnckey.py e
  sleep 4
  # 确认框 "End the Orders Phase? YES/NO" 出现在固定位置 (508,422)；
  # OCR 检测不稳定，改为盲点（无弹窗时该点落在地图上，仅选中格子，无副作用）
  sleep 3
  witp_c 508 422 click
  sleep 3
  # 等结算：轮询 autosave 文件时间戳变化（最多 8 分钟）
  local before=$(stat -c%Y "$SAVE_DIR/wpae000.pws" 2>/dev/null)
  for i in $(seq 1 32); do
    sleep 15
    local now=$(stat -c%Y "$SAVE_DIR/wpae000.pws" 2>/dev/null)
    if [ "$now" != "$before" ]; then
      echo "[witp] 结算完成（autosave 已更新，用时约 $((i*15))s）"
      return 0
    fi
  done
  echo "[witp] ⚠ 结算超时（8分钟未见新存档）" >&2
  return 1
}

# [战斗摘要关闭] 摘要页Done按钮≈(566,255)（vision定位，逐页点直到回地图）
witp_close_summaries() {
  for i in $(seq 1 15); do
    witp_screenshot
    local T=$(witp_ocr | grep -ciE "summary|combat")
    local M=$(convert $SHOT -format "%[fx:mean]" info:)
    # 回地图判定：无摘要词 且 画面均值稳定在地图特征值
    if [ "$T" = "0" ]; then break; fi
    xdotool mousemove 566 255 click 1
    sleep 2
  done
}

# ============ 已验证的战术指令操作（2026-09-22 实测）============

# 【键盘焦点铁律】按任何游戏快捷键前，必须先点击地图给游戏输入焦点：
#   xdotool mousemove 300 500 click 1; sleep 1; xdotool key <键>
#   否则按键无效（Wine 需要窗口有焦点才接收 XTEST 键盘事件）
witp_focus_map() { xdotool mousemove 300 500 click 1; sleep 1; }

# 【任务部队列表】(按T打开；需先 witp_focus_map)
#   行坐标(y)：TF14=251 TF15=266 TF16=281 TF17=296 TF18=311
#              TF20=326 TF21=341 TF22=356 TF23=371 TF24=386 TF25=401
#   列：编号x≈165 | 任务x≈200-280 | 舰数 | 控制x≈630 | 目的地x≈755
witp_open_tf_list() { witp_focus_map; xdotool key t; sleep 2.5; }

# 【打开某TF】双击列表行
witp_open_tf() { xdotool mousemove 200 $1 click 1 click 1; sleep 2.5; }

# 【指令① 变更舰队目的地】★已实测通过★
#   TF界面内 "Set TF Destination" 行左侧箭头 '>' = (534,204)
#   流程：点箭头 → 地图进入选格模式 → 点目标格 → 完成
#   验证：重开TF列表，目的地列从 "move to 旧坐标" 变为 "move to 新坐标"
witp_set_tf_destination() {   # 用法: witp_set_tf_destination <目标格x> <目标格y>
  xdotool mousemove 534 204 click 1   # 点目的地箭头
  sleep 2
  xdotool mousemove $1 $2 click 1     # 点地图目标格
  sleep 2
}

# 【指令② 拆分编队】Form New TF = (746,219)
witp_form_new_tf() { xdotool mousemove 746 219 click 1; sleep 2.5; }

# 【指令③ 合并/转移舰船】Transfer Ships to/from TF = (736,233)
witp_transfer_ships() { xdotool mousemove 736 233 click 1; sleep 2.5; }

# TF界面其他按钮坐标：
#   Set TF Routing=(554,232) Disband=(742,247) Dock=(728,261)
#   Replenish from Port=(787,275) / at Sea=(745,290)
#   Load Supplies=(728,303) Load Fuel=(728,317) Load Oil/Resources=(728,345)
#   Unload Cargo/Troops=(732,359) Max React=(746,467) Change HQ=(734,482)
#   Next TF in Hex=(644,519) Back=(788,519) Exit=(845,519)

# 【鼠标失效修复】★2026-09-22实测有效★
#   症状：点击任何按钮无反应（变化=0），但键盘(ESC/T)仍有效。
#   原因：Wine 的鼠标捕获状态异常（InputOnly 窗口 0x400001 存在是正常的，不是根因）
#   修复：ESC×3 清 modal → wmctrl 激活+置顶 → windowraise → 测试点击
witp_fix_mouse() {
  # ★2026-09-24 修正★ 必须操作受 openbox 管理的 "Wine Desktop"，
  #   而非游戏窗口本身（override-redirect=yes，openbox 不管理，操作它会触发错位）
  local WID=$(xdotool search --name "Wine Desktop" | head -1)
  for i in 1 2 3; do xdotool key Escape; sleep 0.8; done
  wmctrl -i -a $WID; sleep 1
  wmctrl -i -r $WID -b add,above; sleep 1
  xdotool windowraise $WID; sleep 1
  echo "[witp] 鼠标修复执行完毕（ESC×3 + 激活 + 置顶）"
}

# 【界面无响应修复】★2026-09-22关键发现★
#   症状：某些全屏对话框（Form New TF / 航空队界面）鼠标+键盘都无响应，但 ESC 有效。
#   原因：游戏有第二个 X 窗口（0x1000001 主窗口 + 另一个无名 1024x768 InputOutput 窗口）；
#         某些对话框的输入需要那个窗口有焦点。
#   修复：xdotool windowfocus <第二窗口ID>
#     第二窗口ID 通过：xwininfo -root -children | grep 1024x768 找非 0x400001 的那个
witp_focus_dialog() {
  local D=$(xwininfo -root -children 2>/dev/null | grep "1024x768" | grep -v "0x400001" | awk '{print $1}' | head -1)
  if [ -n "$D" ]; then
    xdotool windowfocus $D 2>/dev/null
    echo "[witp] 已把焦点切到对话框窗口 $D"
  else
    echo "[witp] 未找到对话框窗口" >&2; return 1
  fi
}

# 【虚拟桌面模式坐标偏移】2026-09-22
#   启用 Wine 虚拟桌面(VirtualDesktop)后，游戏窗口被 Openbox 装饰，位于 (1,20)，
#   wmctrl/xdotool windowmove 均无法移动（Wine 特殊窗口）。
#   → 所有游戏内坐标需加偏移：屏幕坐标 = 游戏坐标 + (1,20)
#   屏幕分辨率设为 1400x1050 以保证 1024x768 窗口完整可见(范围 x=1..1025, y=20..788)
# 动态偏移：虚拟桌面窗口的位置每次启动都不同，必须实时读取
WITP_OX=0
WITP_OY=0
witp_sync_offset() {
  local WID=$(xdotool search --name "War in the Pacific" | head -1)
  local BRD_X=0 BRD_Y=0
  if [ -z "$WID" ]; then
    # ★2026-09-26 兜底★ 新局启动后游戏窗口可能是**无名窗口**（xwininfo 显示 has no name），
    #   按名字搜不到 → 偏移读成 0,0 → 之后所有点击全错位（本次即因此连点错十几下）。
    #   改按几何特征找顶层窗口：带宽 1020~1032、高 764~792 者即游戏窗口/其边框。
    local LINE=$(DISPLAY=${WITP_DISPLAY:-:98} xwininfo -root -children 2>/dev/null \
      | grep -E '^\s+0x[0-9a-f]+' \
      | awk '{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+\+[0-9-]+\+[0-9-]+$/){split($i,a,"[x+]"); if(a[1]>=1020 && a[1]<=1032 && a[2]>=764 && a[2]<=792){print $1" "a[1]" "a[2]" "$2; exit}}}')
    WID=$(echo "$LINE" | awk '{print $1}')
    local WW=$(echo "$LINE" | awk '{print $2}')
    # 若匹配到的是带边框的框架窗（宽 1026x789），客户区要内缩 (1,20)
    if [ -n "$WW" ] && [ "$WW" -gt 1024 ]; then BRD_X=1; BRD_Y=20; fi
  fi
  [ -z "$WID" ] && return 1
  WITP_OX=$(( $(xwininfo -id $WID | grep 'Absolute upper-left X' | awk '{print $NF}') + BRD_X ))
  WITP_OY=$(( $(xwininfo -id $WID | grep 'Absolute upper-left Y' | awk '{print $NF}') + BRD_Y ))
  # 兜底：若读不到则用0
  WITP_OX=${WITP_OX:-0}; WITP_OY=${WITP_OY:-0}
}
# ★关键修复(2026-09-22)★ 点击必须走 VNC(RFB) 通道！
#   WitP-AE 是 DirectDraw/DirectInput 老游戏，Wine 不认 xdotool 的 XTEST 注入事件
#   （部分界面点击完全丢失，如航空队界面/Form New TF 对话框）；
#   而 VNC 客户端注入的事件被 Xvnc 当真实设备处理，游戏正常响应
#   （用户在 noVNC 网页点击一直有效，原因即此）。
VNC_CLICK=/root/.hermes/profiles/witp/workspace/witp_vncclick.py
witp_c() {  # 用法: witp_c <游戏坐标x> <游戏坐标y> [click|dblclick|rclick|move]
  witp_sync_offset
  python3 $VNC_CLICK $(( $1 + WITP_OX )) $(( $2 + WITP_OY )) ${3:-click} >/dev/null
}
witp_c2() { # 双击（VNC 通道）
  witp_sync_offset
  python3 $VNC_CLICK $(( $1 + WITP_OX )) $(( $2 + WITP_OY )) dblclick >/dev/null
}
witp_cr() { # 右键
  witp_sync_offset
  python3 $VNC_CLICK $(( $1 + WITP_OX )) $(( $2 + WITP_OY )) rclick >/dev/null
}
# 游戏区截图（自动裁掉窗口外区域，得到 1024x768 纯游戏画面）
witp_shot_game() {
  witp_sync_offset
  witp_crop_ok || return 1
  import -window root /tmp/_full.png
  convert /tmp/_full.png -crop 1024x768+$WITP_OX+$WITP_OY +repage /tmp/witp_shot.png
  # 出图后断言：尺寸必须精确 1024x768，否则视为错位图
  local WH=$(identify -format "%wx%h" /tmp/witp_shot.png 2>/dev/null)
  if [ "$WH" != "1024x768" ]; then
    echo "[witp] ✗ 截图尺寸异常=$WH（应 1024x768）→ 图像已错位，禁止读取" >&2
    return 1
  fi
}
witp_ocr_game() {
  convert /tmp/witp_shot.png -resize 200% -colorspace Gray -normalize /tmp/_g.png
  tesseract /tmp/_g.png - --psm 11 2>/dev/null | grep -v '^$'
}
