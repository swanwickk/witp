---
name: witp-ae-save-format
description: "Use when reading/writing WitP-AE .pws saves or live game memory."
---

# WitP-AE 存档格式与运行时内存（实测）

## 容器格式
.gzip 外层 + 记录串；每条记录 = [u32 id][u32 f2][u32 f3][zlib 流]
- 小记录 id<1000：f2=解压长, f3=压缩长，**可任意变**
- 大记录（SHIP/AG/LOC/TF）：f2/f3 是**引擎校验值**，压缩长必须回原值
- ★ 记录类型码 `id & 0xFF` **不可靠**（实例号进位会污染）；只有 `u_len` 恒定
  → 用 `pwsfile.record_by_len(path, ulen)`

## 记录长度 → 结构
| u_len | 结构 | 步长 |
|---|---|---|
| 2224000 | PWSTaskGroup | 556 |
| 20400680 | PWSAirGroup | 680 |
| 21096000 | PWSLocation | 1172 |
| 9280000 | PWSShip | 464 |
| 9000000 | PWSLeader/Pilot | 180 |
| 15200000 | Pilot（运行时是 304）| 152/304 |
| 1900000 | PWSShipClass | 380 |
| 396000 | PWSAircraft | 396 |
| 472000 | PWSDevice | 236 |

## 运行时内存（零 OCR/键鼠）

★ 必须用 `/proc/<pid>/mem`，**禁用 gdb**：
gdb `dump binary memory` 在未映射页**静默写全零**，与「读到真零」无法区分。

| 对象 | 基址 | 步长 | 镜像 |
|---|---|---|---|
| TaskForce | 0x6da5148 | 556 | — |
| AirGroup | 0x598f4f8 | 680 | 0xbba0c20 |
| Location | 0x4570c50 | 1172 | 0x9e8f670 |
| Ship | 0x1a14378 | 464 | 0xb2adcb0 |
| Leader | 0x252b3f8 | 180 | — |
| ShipClass | 0x3755160 | 380 | 0xe8a8400 |
| Aircraft | 0x6d44660 | 396 | 0xcf14658 |
| Device | 0x3f0b460 | 236 | 0xea78208 |
| Pilot | 0x7f7faa8 | **304** | 0xda29500 |

★ 步长与存档记录长度一致（TF=556、AG=680、LOC=1172、Ship=464…）
★ 基址在同一局内跨进程重启仍有效
★ 有镜像的 5 类（Ship/AG/ShipClass/Aircraft/Device/Pilot）**必须两份都写**，
  只写一份是假成功（界面变、存档不变）

### 可写字段（全部过回合验证）
```
TF    mission 349 / speedSetting 362 / routing 356 / tolerance 448 / maxReact 389
      ★ retirement 388 (u8: 0=Retire Allowed, 1=Remain on Station)
      followMode 447 (0无/1Follow/2Meet/3Patrol) / followTF 486
      patrol1X/Y 364,366  patrol2X/Y 368,370  patrol3X/Y 372,374
      wp 118 (40×u16,u16) + wpCount 320 + wpAlloc 322
      flagship 44 / home 54 / loadState 350
AG    primary 44 / secondary 46 / pctCAP..pctRest 560-565 / alt 212(u16)
      maxPlanes 245 / baseID 40 / reinforceBase 42 / upgradeTo 308
      withdraw 392 (u32 YYMMDD, 450505=1945-05-05)
LOC   prep 104 / prepTarget 102(u16) / combatMode 110 / operationsMode 906(u16)
      portExpand/airfieldExpand/fortExpand 424,428,432 (都是 u8!)
      ★ attachedHQ 118 (u16, 归属司令部编号 1..30)
Ship  locationID 62 (u16, 14000+TF号 或 Location ID)
      repairPriority 338 / repairMode 339 / upgrade 365
Pilot status 52 (u32 YYMMDD 以外的任务状态 0/1/2)
ShipClass endurance 52(u16) / speed 56 / fuel 58
Device ★ upgradeTo 60 (u16, 升级目标设备 ID，99=无)
```

### 只读/派生（写入会被引擎覆盖）
```
Ship   sysDamage 332 / fltDamage 333 / engDamage 335 / fireDamage 331
Pilot  exp 112 等技能值
★ Leader 旧标签 leadership 48 / inspiration 49 是【错的】——见 v12：
  off48=politicalPoints、off49=commandsType（CSV 1959/1959 全中）
TF     endure 4 / endureReq 8 / fuel 12 / load 28 / speed 354,356,361
LOC    docked 401/402（按航路点重算）
```

### ★航路点写入的正确认知★
- 对**会移动的 TF**（mission=AMPHIB 在航行）→ 有效，过回合保留
- 对**非移动的 TF**（mission=AIRCOMBAT）→ 引擎托管，会被恢复
之前误判为「无效」，实际是测试对象选错。


## ★v8：换将 + TF 离图（两项从 blocked 转为已实现）★

### 换将 —— `location.off128` (u32) = leader ID
命令源是 Location.off128；`ship.off32`（TF 旗舰）是**派生值**，引擎自动同步。

定位：搜 `Cdr:` 字符串 → 引用 `0x66ec53: mov 0x4570cd0(%ecx),%edx`
      （`0x4570cd0 - 0x4570c50 = 0x80 = 128`）

| Location | off128 | 将领 |
|---|---|---|
| LOC20 4th Fleet | 7064 | Yoshinaka, A. |
| LOC27 Southeast Fleet | 3750 | Kusaka, J. |
| LOC110 Australia Command | 16695 | Blamey, T.A. |

验证：LOC27 写 1 → 过回合保留，且 TF1 旗舰 ship.off32 自动变 1 ✓

### TF 离图移动 —— `taskforce.off60` (u16) = 目的地 Location ID
`0`=海上；`1..29`=离图区（Kwantung/5th Fleet/…）；`992`=Rabaul
验证：TF1 写 3 → 过回合保留 ✓

★ 离图**不用航路点**：航路点写 65535 会被引擎清空（wpCount→0）。
  离图区是非坐标概念，无法用 u16 坐标对承载。

### Ship Withdrawals —— 字段已定位，但语义尚未验证

- `PWSShip` 记录中 `shipWithdrawal@44` 和 `shipReturn@48` 都是 `i32`；先前以日期模式扫描而断言“字段不存在”不成立。
- `wpae000.pws` 中共92条命名舰船，withdrawal/return 字段本次样本均为0；故尚无非零值可用于验证日期格式、政治点惩罚或结算行为。
- 当前只读增援报告保留这两个原始值。**不写、不推断、不再将其称为不存在**；需要其他场景中非零舰船字段与过回合差异才能判断。


### ★批量标记实验的局限★
TF 结构后半段 108 位置全写标记，得到 30 个"保留"但**标记值与位置对不上**
→ 引擎结算时**重排/覆写**这些字段。
★ 批量筛选法**只在结构尾部有效**，不能用于中段字段判定。

### 已证伪为“不存在”的字段结论（证据限定）
| 项 | 证据 |
|---|---|
| ~~换将~~ | **字段已定位但操作未端到端验证**：命令源 location.off128；旧工具从 TF home 推断 Location 不可靠，现安全禁用，需显式指定已核实 HQ/Location |
| Ship Withdrawals | PWSShip `withdrawal@44`/`return@48` 字段存在，但本场景92艘命名舰船值全0；非零语义未验证 |
| ~~TF 离图~~ | **已解决**：真字段是 taskforce.off60，见 v8 |
| 舰船损伤写入 | 派生字段，结算时从耐久重算（**读取已实现**）|
| 基地 HQ（旧判据）| off116 引擎改回、off176 是数组 → **真字段是 off118，已实现** |

### 新建/删除记录（可行）
- 空槽：Location slot 1-10、Ship slot 1-10 等
- 复制记录到空槽 → 过回合保留（实测 LOC110→slot1）
- 工具：`witp_mem_clone_object` / `witp_mem_clear_object` / `witp_mem_split_ground_unit`


### v10 复核补记
- `witp_mem_situation_report` 重复注册已清理。MCP `list_tools()` 及 AST 均为唯一工具，无 GUI/OCR/点击路径调用。
- `witp_mem_ag_missions` 的过回合说明已纠正：任务名表是静态映射；码 8/9/10 已验证保留，码 11 需目标格，16=TRAINING；不再声称 12/13 验证。
- 经济读层明确为存档快照；设备设施映射不包含 Aircraft/Engine factory、R&D/生产池或未来增援时序。不要将候选/未定位状态标成完成。

### ★v11：CSV 逐列比对法（最重要方法论）★

**教训**：我曾用「静态反汇编 ±2000B 内没找到结构访问」断言 Retirement 字段不存在，
并把它写进技能当结论。后来用 **CSV 列名 → 记录偏移** 逐列比对，一次就找到了。

办法：
1. `/root/.wine-witp/drive_c/1108r9/.../SCEN/WITPloc003.csv`（另一份安装里有导出表；
   两份安装的 `.dat` SHA-256 完全一致，所以 CSV 可直接用来解读目标安装）。
2. CSV 的 `UnitNumber` 与存档 Location 槽号**一一对应**（slot 4635 ↔ UnitNumber 4635）。
   TF 显示记录在 Location 槽 `14000+TF号`，但 CSV 里 TF 段需按 **Name 匹配**，不能按行号硬套。
3. 对每个候选字段：遍历记录 0..size-1，要求该字节在**全部样本**上都等于 CSV 列值。
   必须用**运行内存**比对，不要用磁盘存档（存档可能过期，实测有 3 个 TF 不一致）。

结果：`TFRetirement@388`、`TFReaction@389`、`TFRouting@356` 全部 25/25 命中。
旧的 369/355 是错的（369 恒 0；355 只偶发非零）。

★ 方法论要记住的是这条：**先找有没有现成的导出表能当 ground truth，
再谈反汇编**。纯静态反汇编既慢又容易得出「不存在」的错误结论。


### 测试实例路由
- `witp_obj.game_pid()` 现在优先使用独立变量 `WITP_GAME_WINEPREFIX`；未指定时从 `WITP_INSTANCE` 中 `/drive_c` 前缀推导，再兼容 `WITP_WINEPREFIX/WINEPREFIX`。
- 运行验证：即使 `WITP_WINEPREFIX=/root/.wine-witp`（32 位 DLL 辅助前缀），仍选中 `:97` 对应 PID `3453887`，并核实其 `/proc/<pid>/environ` 中为 `/root/.wine-witp-mcp/prefix`。不触碰 `:98` 主实例。

### MCP 键鼠/OCR 路径审计
- 已将 `witp_clear_tf_destination`、`witp_set_tf_retirement`、`witp_get_tf_retirement` 改为明确返回未实现；`witp_end_turn` 也关闭了 XTEST/VNC 输入路径。
- 将旧名 `witp_mem_set_tf_leader` 安全禁用：TF 的 home Location 不必然是指挥链 Location。只能在调用方已核实具体 HQ/Location 后明确调用 `witp_mem_change_commander(loc, leader_id)`；该字段的存档基线与引擎政治点合法性仍需独立验证。
- 对 `server.py` AST 逐工具函数扫描：0 个端点调用 GUI/click/mouse/VNC/screenshot/OCR/xdotool 路径。GUI helper 仅残留未被工具调用的导入，不应通过 MCP 间接触发。
- ★2026-10-20 更新口径：过回合只需一次确定按键（E→y），VNC 单键注入属合规通道（用户明确）；
  witp_end_turn 已重写为 VNC 键盘实现并经 ：97 三轮实测。AST 审计口径更新为：除 end_turn 的单键注入外无其它键鼠路径。
- 集成实测：上述禁用工具返回 `ok=false` 和明确原因；未改变游戏状态。

### 读层新增：增援/撤出候选字段
- `ship`: `reinforcementDelay@36` i32、`arrivalPort@40` u16(Location ID)、`withdrawal@44`/`returnDate@48` i32 候选；与 ship repair delay 是不同字段。
- `airgroup`: `delay@220` i32、`delayReinforcement@224` u8、`withdraw@392` u32(见已验证航空撤出日期字段)、`delay2@396` i32。
- `location`: `arrive@42` u16(Location ID，不是日期)、`delay@564` i32、`withdrawal@908` u16候选。
- `witp_mem_reinforcement_report(save)` 只返回原始数值。测试样本 `wpae000.pws`：3个舰船到达候选、495个航空队增援/撤出候选、33个Location单位候选；S-39 delay=2/arrival Location 913；AG Chitose Ku K-1 withdraw=430315；Location Maizuru 1st arrive=471、delay=9999。
- 哨兵与编码保持原值，不将 delay 自动转换成日期/剩余天数。Location withdrawal=10002等编码、舰船非零撤出/返航、未来计划列表仍未端到端确证。

### 新增手册信息读层
- `witp_mem_victory_report(save)` 读取 SCENARIO 回合/VP，已与 `witp_core.GameState` 对同存档比对一致。
- `witp_mem_economy_report(save)` 读取库存与部分行业设备快照，不代表完整生产系统。
- `witp_mem_information_report(save)` 聚合存档目录中的文本战报、SIGINT 与作战事件文件。
- 报告读工具实测成功；MCP `list_tools()` 与源码 AST 均实测为64个唯一工具；重复 `witp_mem_situation_report` 已清理，重测无重复注册警告。

### 明确剩余项（仍未完成，不得标为全覆盖）
- ch13：Aircraft/Engine factories、R&D progress、factory conversion/expansion、ship construction settings 未定位到可安全写入的运行时/存档命令表；当前只读资源库存与部分设施配置。
- ch16：候选 arrival/withdrawal 原始字段已读；到达日历换算、完整未来计划、飞机/引擎/设备替换池尚未解码。
- ch17：已读当前动态 VP/回合；自动胜利触发阈值与完整公式尚未验证。
- ch05：各类信息聚合并非每一个 UI 子屏的逐字段复刻；飞行员池、飞机/引擎生产池仍待逆向。
- ch06 Retirement 已实现（off388）；TF 结束回合已实现（witp_end_turn：VNC 键盘 E→y，见 docs/witp-mcp-endturn.md）；
  清除目的地已实现（witp_clear_tf_destination：wpCount=0 持久，AMPHIB/SUBPATROL 结算时被任务重推）。
- 航空队 detach/disband 及 PT/Barge 完整新建语义仍未做到端到端。
- Ground Unit device 明细拆分已实现（v12，实测 60→30/30）。
- Ship Withdrawals：字段已定位但样本未见非零，结算与PP惩罚语义未验证。


### ★铁律一：MCP 操作禁止 OCR + 键鼠★
所有能力必须纯二进制实现。界面只能用于**人工验证**。
遇到「静态查不到」时不得退回键鼠 —— 先检查 VA 换算（`{va:#x}` 必须加 `#x`）、
再看字段是否在 `.data` 段、最后用「值域 + 静态引用 + 成对特征」组合判据。

### ★铁律二：计划范围 = 用户要求的全部范围★
**教训**：曾把计划只列为「有把握的 8 项」，跑完当成完成并反问用户，
而用户原话是「剩余没实现的全部完成」。

1. **立项前先完整枚举**：对照手册逐节列出全部剩余项，计划条目必须覆盖全部
2. **阻塞项必须显式标注 `blocked: <原因>`**，不允许从计划里悄悄去掉
3. **收尾前做完整性自检**：重新枚举全部条目逐条对照；有缺口就不许说完成，也不许反问

### ★铁律三：发起后台任务 ≠ 完成★
**第二次犯的错**：发起 background 任务（重启游戏）后，回合直接结束。

- 发起后台任务后，**同一回合必须继续做不依赖它的工作**
  （等游戏重启时继续做纯静态反汇编、字段扫描、文档更新）
- 后台任务带 notify，收到通知自动继续
- 「等外部事件」绝不能作为停下来的理由

## 工具与运行时依赖
| 文件 | 作用 |
|---|---|
| `witp-reader/witp_obj.py` | 9 类对象统一读写 |
| `witp-reader/witp_report.py` | 综合态势、经济、VP、增援候选原始字段报告 |
| `mcp-servers/witp-mcp/server.py` | 当前 MCP 注册工具清单以 list_tools 为准（本轮77项） |

★ 读层 Wine 32 位 Python 依赖：
- `drive_c/py32/python311._pth` 必须包含当前 profile 路径（如 `Z:\root\.hermes\profiles\witp\workspace\witp-reader\pywitpaescraper`），否则 Wine 执行器报 `No module named 'witpae_today'`。
- `witp_read.sh` 中传递给 Wine 的 `--output-dir` 必须是基于当前 profile 的动态绝对 Windows 路径，不可硬编码旧 profile 路径。

当前覆盖率不设全局百分比：历史表中的章节计数与完成标记已过期；参见 `/root/.hermes/profiles/witp/workspace/witp-mcp-手册覆盖表.md` 的 v10 复核及剩余缺口。

## ★v9 修正：航空任务码表（之前是我凭空猜的）★

**我在 v7 给 `witp_mem_ag_transport` 写的任务码 30-33 是错的**（凭空推断、未验证）。

正确码表（来源：内存任务名指针表 `@0x85406c`，12 项，已过回合验证）：

| 码 | 任务 | 码 | 任务 |
|---|---|---|---|
| 1 | AIRFIELD_ATTACK | 8 | NAVAL_SEARCH |
| 2 | PORT_ATTACK | 9 | ASW_PATROL |
| 3 | NAVAL_ATTACK | 10 | SUPPLY_TRANSPORT |
| 4 | GROUND_ATTACK | 11 | TROOP_TRANSPORT |
| 5 | SWEEP | 16 | TRAINING |
| 6 | ESCORT | | |
| 7 | RECON | | |

码 11 需配合 `targetX/targetY` 才不被引擎重置。
工具：`witp_mem_ag_missions` 返回此表。

★ 教训：**不要在代码里写没验证过的常量**。宁可先用占位并标注
  「未验证」，也不要编造看似合理的数字 —— 会误导后续所有验证。

## 舰船损伤字段

```
fire 331 / sys 332 / flt 333 / eng 335
```
★ 注意界面表头顺序是 **Sys/Flt/Eng/Fire**，与内存偏移顺序**不同**。
这四项是派生字段（引擎从耐久重算），**只能读**。
工具：`witp_mem_damage_report`

## ★TF Retirement 已实现（v11 更正）★

旧结论「Retirement 只能走界面、无内存路径」**是错的**，根因是当时只做静态反汇编，
没有拿 WITPloc003.csv 的 `TFRetirement` 列去反查记录偏移。

| 字段 | 偏移 | 取值 | 验证 |
|---|---|---|---|
| `retirement` | **388** u8 | 0=Retire Allowed, 1=Remain on Station | 运行内存 vs CSV：**25/25**（第1回合存档 26/26） |
| `maxReact` | **389** u8 | 反应半径 | 运行内存 vs CSV `TFReaction`：**25/25** |
| `routing` | **356** u8 | 0=Normal 3=Direct | 运行内存 vs CSV `TFRouting`：**25/25** |

★ 旧文档把 `routing` 记在 369、`maxReact` 记在 355，两者都错：
  369 恒为 0，355 只在个别 TF 非零并存疑；356/389 才是命令源。
★ 不要再用「静态反汇编 ±2000B 没找到结构访问」去否定字段存在。
  **CSV 列名 → 记录偏移**的逐列比对是最快的字段定位法：同一列在一个存档的
  全部 TF 上必须同时命中，这比手工反汇编可靠得多。
★ 存档 (wpae000) 有 3 个 TF 的 retirement 与 CSV 不同 —— 那是存档过期，
  运行内存才是当前真值。比对时**必须用运行内存**，不是磁盘存档。

## ★实验方法教训：批量标记法★

用「给 N 个位置各写唯一标记 → 过回合 → 看哪些保留」来筛字段时，
**标记值必须不可能与任何真实值重合**。

实例：216 个位置全写标记，off349 写入 1，而 TF1 的真实值也是 1
⇒ 我误读为「其他 TF 的值」，实际是「自己的标记被保留」。
★ 用 `(偏移量 * 3 + 7) & 0xFF` 这类公式仍可能撞车；
  应改用**远大于真实值域**的标记（如 200+offset）。

## ★v12：Leader/Aircraft 字段标定 + 过回合闭环核验（2026-10-20）★

### Leader 头部全标定（CSV WITPldr003 逐列比对，1959/1959 全中）
```
name 0 str24 / rank 25 / skill 26 / morale 27
surfaceAction 28 / airAction 29 / landAction 30 / administration 31 / aggressiveness 32
nationality 42 / ★politicalPoints 48 / commandsType 49
```
- CSV UnitNumber ↔ 内存 leader 数组索引一一对应（53/53 名字验证）；leader[0] 是空白记录。
- Delay/Rank 列无命中（运行时已推进），属预期。
- ★换将语义实测：Location.off128 写入后**挺过结算**，但政治点**不被引擎扣减**
  （PP 7/30 结算前后不变）——扣点发生在 GUI 命令路径。内存换将=免费换将。

### Aircraft 头部标定（CSV WITPair003，231/231）
```
type 25 / maxAltitude 28 / maxSpeed 30 / cruiseSpeed 32 / climbRate 34 / maneuver 36
armour 40 / durability 41 / maxLoad 182 / availMonth 184 / availYear 185
buildRate 188 / upgradeTo 192 / serviceRating 229
```
- off194 旧标签 "research" 是错的：全部 0 且与 CSV 无对应；研发/船舶建造确证为**引擎自动行为**，
  无玩家命令字段。本剧本无在研机型时无进度可读。

### 到达日期换算
`eta_date = 存档头日期 + delay 天`（S-39：t1 delay6/t4 delay3/t5 delay2 → 均指向 5/10，公式成立）。
哨兵值（9999/19999/29999）不换算。reinforcement_report 已返回 eta_date + game_date。

### 过回合闭环核验（新工具）
- `witp_mem_orders_snapshot` / `witp_mem_orders_diff`：对比过回合前后全部 TF 的
  mission/speed/routing/maxReact/retirement/loadState/home/flagship/航路点。
- 实测：每回合引擎重排 8-13 个 TF 的航路点（SUBPATROL 巡逻圈、AMPHIB 滩头路径），
  mission 字段稳定。这是「漂移检测」的 ground truth。

### 替换池：blocked（证据）
pilot 数组 20000 槽仅 466 条非空（idx≤639）——池不是以飞行员记录存储，
按国籍的池计数器未定位。不要声称已解码。

### 胜利阈值 / DL / 舰船 Withdrawal：仍 blocked
- scen 记录 80-400B 无阈值，公式疑硬编码；DL 仅只读候选 0..5；
  withdrawal@44/return@48 本剧本 92 舰全 0，无非零 ground truth。

### ★双实例路由：已修复★
四个模块旧用 "wine-witp" 子串模糊匹配会写错实例；已统一委托 `witp_obj.game_pid()`
（WITP_GAME_WINEPREFIX/WITP_INSTANCE → WINEPREFIX 精确匹配）。server.py 把派生前缀
导出到环境。实测：主前缀无游戏→None（不再误中 :97）；测试前缀→精确命中。

### ★存档记录类型补充（2026-10-21）★
- **u_len=9 = 天气预报**：9 象限 × 5 档（clear..thunderstorms），逐日变化；
  hex→象限 row-major `(y*3//197)*3 + (x*3//230)`（地图 230×197 由 CSV 坐标范围推断）；
  ground truth：菜单栏 Forecast:Overcast(2) @Noumea(115,160) → idx7=2 ✓
- **u_len=76**：跨回合不变（气候/季风配置候选，未确证）
- 未识别记录全部枚举见 docs/witp-mcp-手册覆盖表.md；随回合演变候选：
  180000（含 (装备ID,装备ID,数量) 三元组，疑地面装备池）/190240/360000/120000/760960/2608000
- **off135 = HQ 层级候选，不是 ch10.1.1 侦测等级**（全图仅 10 个顶级司令部非零，值 1..5）；
  DL 数据源仍未定位
- **基地 VP（ch17.0）**：SCEN CSV `Jvictory/Avictory` 列 = 双方 Basic VP；
  终局 = Basic × (LOC off420 port + off422 airfield×2)，补给折减端点 100%/25%
- 年份解析：存档头两位年份一律 1900+yy（1941..1946）

