---
name: witp-ae-control
description: "Use when calling WitP-AE MCP tools; direct-control first."
version: "1.0"
author: "hermes-agent"
license: "internal"
metadata:
  hermes:
    tags: [witp, mcp, fallback]
    related_skills: [witp-ae-save-format, witp-ae-interface, gui-automation-verification]
---

# WitP-AE 通道整合：直控为主，键鼠为备份（2026-10-21）

## When to Use
- 任何通过 MCP 操作 WitP-AE 的会话（下令/读态势/过回合/恢复）。
- 内存直控报「游戏未运行/无法定位」时——先看本技能的恢复语义，勿盲目重试。

## 通道层级（服务器已实现，见 server.py 顶部注释）

| 层 | 通道 | 覆盖 |
|---|---|---|
| T1 直控 | `/proc/<pid>/mem` + 存档解析 | **全部 71+ 工具的默认路径** |
| T2 键盘 | VNC RFB 单键（`witp_gui.vnc_key`） | 引擎动作（过回合 E→y；Return 无效必须 y） |
| T3 菜单 | 固定坐标（`witp_gui.load_autosave`） | 恢复场景：主菜单 LOAD→Autosave→SELECT |

## 铁律
1. **能用 T1 绝不用 T2/T3**。直控失败（游戏进程不存在）时，server 内的
   `game_pid` 恢复钩子会自动走 T3：拉起实例 → 等主菜单（整屏 md5 稳定）→
   固定坐标载入 autosave → 重试直控。实测 122s 完成整链。
2. **T3 放行 OCR 动态定位**（2026-10-21 用户决定：游戏画面元素坐标会变，固定坐标不可靠）：
   工具 `witp_gui_fallback` 的 `click_text`/`find_text`/`read_screen` 走 tesseract。
   T1 直控工具内部仍零 OCR/键鼠；能用 T1 完成的事不要走 T3。
3. **恢复钩子不复用 launcher 脚本**：脚本会点 ALLIED COMPUTER 进新剧本，
   与「主菜单载入 autosave」冲突。恢复序列自建（Xvnc→openbox→wine reg→游戏→菜单→载入）。
4. 主菜单实测：LOAD 按钮文字是 **“LOAD A SAVED GAME”**；对话框标题 “SAVE GAME MENU”；
   存档行 000=Autosave(y≈210)、002=PreTurnSave(y≈238)；SELECT 在 (≈286,578)。
   ★ 固定坐标点存档行会**载错旧档**（实测载到 05/04）；必须 OCR 找 “Autosave” 字样，
   否则解析 MM/DD/YY 取最新日期行。
5. **载入正确性判据 = TF 航点指纹**（不是 OCR 日期，也不是 TF mission/flagship 签名——
   三份存档前 6 个 TF 签名完全相同，签名匹配区分不了回合）。
   `witp_channel_status` 返回 `loaded_save_fingerprint`；正常态 = wpae000 且 ≥80% 槽吻合
   （巡逻 TF 载入后被引擎重推航点，允许 2-3 槽差异）。
6. `WITP_GUI_RECOVERY=0` 可整体关闭自动回退（纯直控模式）。

## 工具路由

| 意图 | 主通道工具 | 备份 |
|---|---|---|
| 诊断通道 | `witp_channel_status` | — |
| 过回合 | `witp_end_turn`（T2，唯一键盘工具） | 人工 GUI |
| 任意 TF/AG/LOC/Ship 命令 | `witp_mem_*` / `witp_set_*`（T1） | 失败时自动 T3 恢复后重试 |
| 手动键鼠 | `witp_gui_fallback(action,...)`（load_autosave/key/click/click_text/find_text/read_screen/screen_md5） | — |
| 态势/天气/胜利/增援/经济 | `witp_status` / `witp_weather_report` / `witp_victory_forecast` / `witp_base_vp_report` / `witp_mem_reinforcement_report` / `witp_mem_economy_report`（T1 只读） | — |

## 闭环核验（每次落子后必做）
- 写后即时读回（工具内置 verified 字段）
- 航空队 CAP 双镜像持久化实证：`witp_mem_set_airgroup` 对 `pctCAP` 的写入会同步更新 copyA（运行时）与 copyB（存盘区）；实测改写后经 `witp_end_turn` 结算生成的新 Autosave 中 CAP 保持改写值，确认持久化生效。
- 地面部队防御模式直控实证：`witp_mem_object_set(kind='location', index=loc_slot, field='combatMode', value=0)` 直接将阵地从炮击骚扰（1=bombardment）置为坚决抗登陆防御（0=combat/defend），写后即时 verified，无需通过 UI 点击。
- 过回合后 `witp_mem_orders_snapshot/diff` 检测漂移（引擎每回合重排 8-13 TF 航点属正常）
- 恢复发生后先 `witp_channel_status` 确认 T1，再继续操作

## 已知边界与避坑
- 开局第 1 回合 Autosave 基线：引擎在第 1 回合结算前不会生成 `wpae000.pws`；`witp_end_turn` 自动识别首回合无 autosave 状态，改用最新手动存档建立基线，结算后捕获新生成的 autosave。
- 存盘对话框阻塞顶栏：手工或脚本 `save-game` 后，画面停留在 SAVE 对话框，顶栏被 `SAVE GAME` 覆盖，`detect_side.py` 会判定为 UNKNOWN；必须发送 `Escape` 关闭对话框返回战术地图后再检测阵营或出参谋建议。
- 阵营切换参数对齐：执掌美军（盟军）需设置 `WITP_SIDE=allied` 且 `WITP_GAMESTYLE=japan`（即选择 JAPANESE COMPUTER，电脑控制日军，人类控制盟军）。
- 恢复钩子对主实例(:98)同样生效：游戏未运行时首次内存工具调用会自动拉起主实例游戏
  （约 2 分钟）。不希望自动拉起时设 `WITP_GUI_RECOVERY=0`。
- 定位按 WINEPREFIX 精确匹配（witp_obj.game_pid 唯一实现），双实例并存不会写错目标。
