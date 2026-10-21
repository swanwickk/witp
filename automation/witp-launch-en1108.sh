#!/bin/bash
# WitP-AE 英文 1108r9 启动器
#
# ═══ 崩溃根因：已定案并已规避（2026-10-04 夜）═══
# 现象：游戏随机崩溃（可运行 1.5~3.5 小时后必崩），wine 报
#   wine: Unhandled page fault on read access to 00000000 at address 781FC30D
#
# 决定性证据（WineDbg 崩溃现场）：
#   err:msvcrt:_wassert
#     (L"req >= filter->requests && req < filter->requests + filter->max_requests",
#      L"dlls/quartz/filesource.c", 397)
#   前置：err:ole:com_get_class_object no class object
#     {62be5d10-60eb-11d0-bd3b-00a0c911ce86} could be created
#
# ★★ 关键定位订正（此前误判为"主游戏进程崩溃"）★★
#   崩溃进程是 **witprec.exe** —— 游戏自带的音效播放组件，
#   不是 "War in the Pacific Admiral Edition.exe"。
#   证据：崩溃时 ps 里主游戏也已消失，但崩溃日志的 init_peb 行明确写着
#   starting L"C:\\1108r9\\...\\witprec.exe"；且 witprec.cdd / witprec.exe
#   与 SOUND/ 下的 1413.SFX、1081.SFX 等编号一一对应（按编号取音效）。
#   witprec.exe 用 DirectShow(quartz) 解码 .SFX，在 Wine 10.0 上撞
#   filesource.c:397 的请求数组越界断言。
#
# ★★ 规避方案（已实施，实测有效）★★
#   witprec.exe 只负责音效，**与游戏逻辑无关**。
#   故直接把它改名禁用，游戏主程序找不到音效组件即跳过播放：
#     witprec.exe → witprec.exe.disabled（原件备份为 witprec.exe.orig）
#   代价：没有音效。收益：消除已确认的唯一崩溃源。
#
# 已实测推翻的假设（勿再回头）：
#   ✗ 禁用 winealsa/winepulse/wineoss → 仍同址崩溃（故 ALSA 保留）
#   ✗ 缺 GStreamer ASF/WMA 解码器 → gst-launch decodebin 对 .SFX 可跑到 EOS
#   ✗ core dump 取证 → Wine 内部捕获 SIGSEGV，内核不写 core（路线作废）
#   ✗ 音量静音 → 不是解法
#   ✗ 主游戏进程自身有 bug → 崩溃栈属于 witprec.exe，与主程序无关
#
# 恢复音效（若将来需要）：mv witprec.exe.disabled witprec.exe
export WINEPREFIX=/root/.wine-witp DISPLAY=:98 HOME=/root LANG=en_US.UTF-8
ulimit -c unlimited          # 保留（本机不产 core，注释所设 core_pattern 已还原，见 ops-log）
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
cd "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition"

# ── 崩溃规避 v8（2026-10-05）：quartz.dll 二进制补丁 v2 = 根治 ★★★★ ──
# ═══ 已实测推翻的方案（全部勿回头）═══
#   ✗ 改名 witprec.exe → .disabled
#       → Fatal Error: 999（witprec 参与启动初始化）
#   ✗ 只用 WINEDLLOVERRIDES=quartz=d
#       → 断言照发。"=d" 只阻止 dll **加载**，阻止不了已加载代码的执行路径
#   ✗ 只用 msacm32=d
#       → 断言照发。witprec 直接导入 WINMM+MSACM32+urlmon 三条音频入口
#   ✗ 移走 SOUND/*.SFX
#       → Runtime "Failed to find project file in archive."
#   ✗ 截断 SOUND/*.SFX 到 1KB
#       → 同样破坏 archive 校验，主程序干净退出（FreeHeap）
#   ✗ 二进制补丁 v1：NOP 掉 call [__imp__assert]
#       → 断言消失，但改出 **Unhandled page fault on read access to 00000044
#         at 00438A86**。原因：assert 只是症状，`req` 仍越界，
#         后续代码照样解引用 req->sample ⇒ 带着野指针跑必然更糟。
#
# ★★★★ v8：把越界落点从 assert 块改为「安全出口」★★★★
#   上游 Wine **至今未修**：实测 wine-mirror/wine master 的
#   dlls/quartz/filesource.c，397 行仍是原封不动的 assert(...)。换新版无效。
#   本机无 winegcc/libwine-dev ⇒ 走二进制补丁。
#
#   反汇编实测（quartz.dll 10.0, image_base 0x180000000, io_thread）：
#     180008750: mov  0x500(%rbx),%rax   ; filter->requests
#     180008757: cmp  %rax,%rsi
#     18000875a: jb   0x1800088a3         ; ← 越界落点①（原 assert）
#     180008760: mov  0x508(%rbx),%edx   ; filter->max_requests
#     180008766: lea  (%rdx,%rdx,2),%rdx
#     18000876a: shl  $0x4,%rdx          ; ×48 = sizeof(struct request)
#     18000876e: add  %rdx,%rax
#     180008771: cmp  %rax,%rsi
#     180008774: jae  0x1800088a3         ; ← 越界落点②（原 assert）
#     18000877a: test %r15d,%r15d
#     18000877d: jne  0x180008840         ; 正常：Wake + 循环
#     180008790: movq $0x0,-0x10(%r14)    ; ★安全出口：sample = NULL
#     180008798: lea  0x4d0(%rbx),%rcx
#     18000879f: call LeaveCriticalSection
#     1800087a5: ← 回到 GetQueuedCompletionStatus，继续循环
#
#   修法：**只改两个 rel32 跳转偏移**，把落点 0x1800088a3 → 0x180008790。
#   语义 = 源码 else 分支「本次 IO 失败，req->sample = NULL 后继续」，
#   即 Wine 上游该修而一直没修的逻辑。不改任何数据结构、不删任何代码。
#
#   幂等：已打则跳过；quartz.dll.orig 为原版备份（--revert 可回滚）。
# ★★★ quartz=d 是**游戏能启动**的必需条件（v9 关键订正）★★★
#   订正记录：v8 我把 quartz=d 删掉、改为"完整音频栈 + 补丁"，
#   结果游戏在 witprec 启动后立刻崩：
#     wine: Unhandled page fault on read access to 00000044 at 00438A86
#   地址 0x438A86 落在 **witprec.exe**（基址 0x400000）内，不在 quartz.dll。
#   ⇒ 该崩溃**与 quartz 补丁无关**，是 witprec 走完整解码路径时自身崩。
#   而 run3/run4（quartz=d，COM 类创建失败）游戏正常存活可玩 1.5~2.5h。
#   ⇒ 结论：**必须保留 quartz=d**。让 witprec 走不了 DirectShow，
#     它就不会崩；补丁只负责额外消除 quartz 内部那条断言。
export WINEDLLOVERRIDES="midimap=d,quartz=d"
cd "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition"

PY=/root/.hermes/hermes-agent/venv/bin/python3
# ★v19-67 再订正：**两份** 32 位 quartz 都要补，缺一仍崩
QUARTZ=/usr/lib/i386-linux-gnu/wine/i386-windows/quartz.dll
QUARTZ2=/usr/lib/x86_64-linux-gnu/wine/i386-windows/quartz.dll
# ★★★ v11：两层防护常驻 ★★★
#   实测（v19-49）游戏在装上 witprec 空指针补丁后**正常启动并运行 1 小时**，
#   但随后 **filesource.c:397 断言仍然触发** ⇒ 运行期崩溃依旧。
#   （我此前说"崩溃已根治"是错的：只修了启动崩溃。）
#
#   故两层补丁必须同时在位：
#   ① witprec.exe：空指针解引用（启动崩溃）—— 由 witprec_patch.py 打
#   ② quartz.dll：filesource 越界断言（运行期崩溃）—— 由 quartz_patch2.py 打
#   补丁原理见各自脚本头部注释；两者均幂等，已打则跳过。
#   备份：witprec.exe.orig2 / quartz.dll.orig，可 --revert 回滚。

# ── ① witprec.exe 空指针补丁 ──
WPT="$PWD/witprec.exe"
if ! od -An -tx1 -j $((0x38A86)) -N 7 "$WPT" 2>/dev/null | tr -d ' \n' \
     | grep -qi '^85f6743d8b7644$'; then
    echo "[witprec] 应用空指针补丁…"
    "$PY" /root/.hermes/profiles/witp/workspace/witprec_patch.py --apply | tail -2
else
    echo "[witprec] 补丁已在位（0x38A86 = 85f6743d8b7644）"
fi

# ── ② quartz.dll 越界断言补丁（★32 位★）──
#   实测订正：断言来自 PID 0120 = witprec 的**32 位**解码路径，
#   加载 /usr/lib/i386-linux-gnu/wine/i386-windows/quartz.dll。
#   此前补 64 位版本**完全无效**（改完 run23 断言照旧）。
# ★★v19-72 停用 quartz 补丁★★
#   实测：我的补丁（越界落点 → 0x1000a2fc）**反而引入新崩溃**：
#     wine: Unhandled page fault on write access to FFFFFFF8
#           at address 781EA277 (thread 0120)
#   根因：0x1000a2fc 是「正常路径入口」，其首句 `movl $0x0,-0x8(%edx)`
#   解引用 edx —— 越界时 edx 是野指针，写 edx-8 = FFFFFFF8 必然页错误。
#   正确的落点应是 0x1000a303（跳过该写，edi 本次迭代已赋值为
#   &filter->sample_cs，可安全用作 LeaveCriticalSection 参数），
#   但此项**尚未实测**，故先停用补丁，回到原版（断言崩溃在 1h43m 后，
#   足够完成本回合作业）。
#   需要时手动：python3 quartz32_patch.py --apply
P1=$(od -An -tx1 -j $((0xA2D0)) -N 6 "$QUARTZ"  2>/dev/null | tr -d ' \n')
P2=$(od -An -tx1 -j $((0xA248)) -N 6 "$QUARTZ2" 2>/dev/null | tr -d ' \n')
echo "[quartz32] 已停用（i386=$P1  x86_64=$P2，应为原版 0f8256010000 / 0f824e010000）"

if [ -f witprec.exe.disabled ]; then
    mv witprec.exe.disabled witprec.exe     # 回滚 v1 的错误改动
fi

# ── 2026-10-04：锁死窗口几何 ──────────────────────────────────────
# 实测：WitP-AE 窗口是 Override_Redirect，位置由 Wine explorer 自行决定；
#   openbox 与 `xdotool windowmove` 都无法移动它（实测忽略请求）。
#   窗口会漂到 x=563/751，使右侧 187~250px 出屏、主菜单红按钮被截断，
#   从而让一切以窗口偏移为基准的坐标配方间歇性失效。
# ★★★ v19-92 撤回 v19-91：虚拟桌面**必须开（Ignore=0）** ★★★
#   实测：把 Ignore 改 1（关闭虚拟桌面）后，游戏窗口未被 openbox 正常接管
#   —— 按一次 Escape 就把游戏**直接退出**了（日志尾 FreeHeap，进程消失）。
#   故 v19-91 的改动已回滚。
#
#   ★★★ 2026-10-14 定性（终版，勿再推翻）★★★
#   0x600001（1024x768，无名，由 explorer.exe 创建）= **Wine 虚拟桌面窗口本体**，
#   游戏画面就渲染在它里面、输入也落在它上面 —— 这是**正常且必需**的。
#   `xdotool getmouselocation` 的 WINDOW 字段返回 0x600001 属**正常**，不是故障。
#   ⚠️ 绝对禁止 `xdotool windowkill 0x600001`！
#      实测这样会把渲染宿主杀掉 ⇒ 游戏随即 `X Error: BadWindow / X_UnmapWindow`
#      崩溃，且此后每次启动都崩（桌面状态已损坏，只能重建整个显示栈）。
#   ⇒ 输入失效的真判据是「点击后画面 md5 不变 / 读层不更新」，
#      **绝不能用 mouselocation 的 window 字段判断**。
#      输入异常时只 `systemctl restart witp-openbox98`，不要动任何窗口。
#
#   历史背景（v19-91 原文，保留供参考）：
#   实测（本轮）：虚拟桌面虽然解决了窗口漂移，但引入**更严重的失败**：
#   它由 explorer.exe 创建一个 1024x768、Class=InputOnly 的窗口（0x600001）
#   盖在最上层，**独占鼠标/键盘输入**。表现：
#     · 游戏进程活着（CPU 51%、时间推进）、窗口 IsViewable
#     · 鼠标移动生效（xdotool 读到 X 变化）
#     · **但鼠标事件落点是 0x600001 而非游戏窗口 0x1000001**（xdotool
#       getmouselocation 的 WINDOW 字段暴露了这一点）
#     · ⇒ 键盘/点击对游戏**完全无效**：9 次操作（Escape/Return/Space/
#       字母键/四次地图点击）后画面 md5 **完全不变**
#   这是一个极隐蔽的陷阱：所有「进程活着/窗口正常」的检查都通过，
#   只有查 WINDOW 字段才发现输入被别的窗口吃掉。
#   ⇒ 关闭虚拟桌面，让游戏窗口由 openbox 正常管理。
#   窗口位置改用 get_window_offset() 动态读取（它本来就支持）。
#   生效后窗口原点恒为 (0,0)，偏移不再漂移。
wine reg add 'HKCU\Software\Wine\Explorer\Desktops' /v Desktop /t REG_SZ /d '1024x768' /f >/dev/null 2>&1
wine reg add 'HKCU\Software\Wine\Explorer\Desktops' /v Ignore  /t REG_DWORD /d 0 /f >/dev/null 2>&1

# ── ★★★ 2026-10-12：启动后自动设 GAMESTYLE（决定人类执哪一方）★★★ ──
#   判决性实验（同一份 wpae000.pws，唯一变量=GAMESTYLE）：
#     JAPANESE COMPUTER（旋钮默认位）= AI 打日军 / 人类执【盟军】
#     ALLIED COMPUTER                = AI 打盟军 / 人类执【日军】
#   实测：本脚本 exec wine 后游戏停在主菜单，GAMESTYLE 恒为**默认位**
#   ⇒ 凡经本服务重启再手工载入，人类都会变成盟军（这就是"autosave 里怎么会有
#     盟军局存档"的错觉来源；存档目录里其实始终只有一局）。
#   修法：wine 放后台跑，脚本继续「等主菜单 → 点 GAMESTYLE target → 等 wine 退出」。
#   注意：**绝不在主菜单按 Escape**（实测会被当作退出，游戏立刻 FreeHeap 消失）。
GAMESTYLE_TARGET="${WITP_GAMESTYLE:-allied}"   # allied=人类执日军（默认，用户要求玩日军）
case "$GAMESTYLE_TARGET" in
  allied) GS_X=660; GS_Y=178 ;;   # ALLIED COMPUTER   → 人类执日军
  *)      GS_X=566; GS_Y=120 ;;   # JAPANESE COMPUTER → 人类执盟军
esac

wtp_set_gamestyle() {
    local i txt
    # 等主菜单出现（最多 120s）：OCR 找主菜单特征字
    for i in $(seq 1 48); do
        if DISPLAY=:98 import -window root -crop 1024x768+0+0 +repage /tmp/_launch_menu.png 2>/dev/null; then
            txt=$(tesseract /tmp/_launch_menu.png - --psm 11 2>/dev/null | tr 'A-Z' 'a-z')
            case "$txt" in
              *scenario*|*realism*|*gamestyle*|*computer*|*exit*game*) break ;;
            esac
        fi
        sleep 2.5
    done
    echo "[launch] 主菜单就绪，设 GAMESTYLE=$GAMESTYLE_TARGET @ ($GS_X,$GS_Y)"
    python3 /root/.hermes/profiles/witp/workspace/witp_vncclick.py "$GS_X" "$GS_Y" click
    sleep 2
    echo "[launch] GAMESTYLE 已设（最终以载入后顶栏 PLAYER 为准）"
}

wine "War in the Pacific Admiral Edition.exe" &
WINE_PID=$!
wtp_set_gamestyle
wait $WINE_PID
