# witp_end_turn：键盘单键过回合（实测记录）

日期：2026-10-20　环境：WitP-AE 英文 1108r9，测试实例 `:97`（Xvnc rfbport 5901，WINEPREFIX=/root/.wine-witp-mcp/prefix）

## 实测结论（可复现链路）

1. 地图界面按 **E** → 弹出 `End the Orders Phase?` 确认框（YES 黄色高亮）。
2. 按 **y** = 确认 YES（**Return/Enter 无效**，实测两次都不关闭对话框）。
3. 引擎开始结算（日志滚动：ROUTINE AIR OPERATIONS COMPLETE / AIR STRIKES / DAMAGE CONTROL 等）。
4. 结算完成回写 **Autosave = `SAVE/wpae000.pws`**（结算开始时先写 wpae002.pws 作 PreTurnSave）。
5. SCENARIO 记录 turn 递增（实测两轮：1→2 手工验证，2→3 经 MCP 工具验证）。

全程只需两次确定按键，无 OCR、无坐标点击、无鼠标。

## MCP 工具实现（server.py）

- `_vnc_key(key)`：优先复用现有 `workspace/witp_vnckey97.py`（VNC RFB 键盘通道，`WITP_VNC_PORT` 环境变量）；
  失败回退 `xdotool key`。只发明键名，绝不涉及坐标。
- `_screen_hash()`：`import -window root png:-` 的 md5，仅作“画面是否变化”判据（弹框检测），不做 OCR。
- `witp_end_turn(confirm, wait_seconds=900)`：
  1. `confirm=false` 直接拒绝（防误触，实测护栏生效）。
  2. 记录 autosave 的 mtime + turn（SCENARIO 偏移 30）。
  3. 发 E，要求整屏 md5 变化（=确认框弹出），最多重试 3 次；否则报“确认框未弹出”。
  4. 发 y；轮询 autosave mtime（每 5s），90s 后若画面仍停在弹框基线则重发 y（最多 2 次）。
  5. mtime 变化 → 读 after_turn，返回 `turn_advanced` 等字段。

## 实测输出（第二轮，经 MCP 工具函数直调）

```json
{"ok": true, "before_turn": 2, "after_turn": 3, "turn_advanced": true,
 "channel": {"e": "vnc", "y": "vnc", "y_resent": 0}, "elapsed_s": 149.8}
```

## 注意事项

- 结算耗时与当天行动量相关：实测 turn1→2 约 4 分钟，turn2→3 约 2.5 分钟。`wait_seconds` 默认 900 足够。
- 工具按环境变量 `WITP_INSTANCE / WITP_DISPLAY / WITP_VNC_PORT` 定位实例；配置默认指向主实例 `:98 / 5902`。
- 若 E 按下时游戏不在地图命令阶段（正在结算/在子界面），工具返回 ok=false 并说明，不会盲目发 y。
- 输入通道实例差异：同一套 Xvnc 参数下，有时 VNC 指针事件失效而 xdotool 正常，有时相反。
  因此键盘走 VNC→xdotool 双通道回退；两个通道都只发单键。
- 首次验证时发现 `witp_vnckey97.py` 的键名表是 `Return`（大写开头），小写 `return` 会报“未知 keysym”。
