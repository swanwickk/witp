# WitP-AE MCP 功能覆盖表（v6 · 通道整合版）

> 1108r9 英文版 · 手册来源 `wargaming/witp-ae-manual`
> 判定口径：**已实现** = 纯内存写入 + 过回合后引擎存档保留（无 OCR/键鼠）
> ★2026-10-21 通道整合：T1 直控为主，T2 键盘/T3 为备份；**T3 放行 OCR 动态定位**
> （游戏画面元素坐标经常变化，固定坐标不可靠）。直控失败（游戏进程不存在）时自动恢复
> （拉起+OCR 定位载入 autosave，实测 152s），载入正确性用 TF 航点指纹核验
> （`witp_channel_status.loaded_save_fingerprint`；固定坐标点存档行会载错旧档，已实测）。
> `witp_channel_status` 诊断、`witp_gui_fallback` 手动备份、`WITP_GUI_RECOVERY=0` 关闭。
> 详见技能 wargaming/witp-ae-control。

## 一、按章覆盖率

| 章 | 命令面 | 已实现 | 覆盖率 | 备注 |
|---|---|---|---|---|
| ch06 海军与编队 | 20 | 16 | **80%** | 新增组建/解散 TF、速度档 |
| ch07 航空 | 11 | 8 | **73%** | 新增 Withdraw、空运任务 |
| ch08 地面 | 8 | 6 | **75%** | 新增 Set All |
| ch09 基地 | 4 | 2 | **50%** | HQ 变更不可写 |
| ch11 政治点 | 2 | 0 | **0%** | 换将字段未定位 |
| ch14 舰船修理 | 4 | 4 | **100%** | 新增全港批量修理 |
| ch15 后勤 | 7 | 1 | **14%** | 自动运输船团未做 |
| **合计** | **56** | **37** | **66%** | 上版 54% |

## 二、ch06 编队（80%）

| 手册节 | 内容 | 状态 | 实现 |
|---|---|---|---|
| 6.1.1.1 | TF 任务 25 种 | ✅ | `witp_mem_set_tf(mission=)` |
| 6.1.2.1 | TF 目的地 | ✅ | 航路点数组 + wpCount |
| 6.2.3 | TF 速度档 | ✅ | `witp_mem_set_tf_speed`（off362） |
| 6.2.4 | Patrol/Retreat、Max React | ✅ | routing/tolerance/maxReact |
| 6.2.7.1 | Follow Task Force | ✅ | off447=1 + off486=目标 |
| 6.2.7.2 | Meet Task Force | ✅ | off447=2 |
| 6.2.7.3 | Set Patrol Zone | ✅ | off447=3 + off364-375 |
| 6.2.8 | 舰船在 TF 间转移 | ✅ | `witp_mem_transfer_ship`（ship.off62） |
| 6.2.9 | TF 返回母港 | ✅ | home 字段 |
| 6.2 | **组建 TF** | ✅ | `witp_mem_create_tf` |
| 6.2.2 | **解散 TF** | ✅ | `witp_mem_disband_tf` |
| 6.3 | 装载/卸载 | ✅ | loadState |
| 6.9 | Retirement | ✅ | `witp_set_tf_retirement` / `witp_get_tf_retirement`（off388；CSV 交叉验证 25/25） |
| 6.2.10 | TF 离图移动 | ✅ | `witp_mem_tf_move_offmap`（taskforce.off60 = 离图区 Location ID，写 3 保留）|
| 6.2.15 | Docking | ⚠️ | `TF.off60`=当前基地、`off401/402`=停泊标志（只读，引擎按航路点重算）|
| 6.2.16 | 创建 PT/Barge/Midget | ⚠️ | `witp_mem_clone_object(kind=ship)` 可复制舰船到空槽（含改名）；PT 专用舰级需手工指定 shipClass |
| 6.3.6 | **换将** | ⚠️ | `location.off128` 是指挥官字段；只能显式指定核实后的 Location，禁止从 TF home 推断。`witp_mem_change_commander` 只写内存并即时读回，不处理政治点/资格校验或存档采纳 |
| 6.5 | 舰船损伤 | ✅ 读 | `witp_mem_damage_report`（Sys/Flt/Eng/Fire 汇总；**写入不可行**，派生字段）|

## 三、ch07 航空（73%）

| 手册节 | 内容 | 状态 | 实现 |
|---|---|---|---|
| 7.2.1.1 | 任务类型 | ✅ | primary/secondary |
| 7.2.1.7 | 目标与目的地 | ✅ | targetX/Y |
| 7.2.1.8 | CAP/Search/ASW/Training 比例 | ✅ | pctCAP..pctRest |
| — | **任务码表** | ✅ | `witp_mem_ag_missions`（12 项，静态反汇编+实测）|
| 7.2.1.9 | 高度选择 | ✅ | alt（u16） |
| arrival / withdrawal | `ship.reinforcementDelay@36`/`arrivalPort@40`/`withdrawal@44`/`return@48`，`AG.delay@220`/`withdraw@392`/`delay2@396`，`LOC.arrive@42`/`delay@564`/`withdrawal@908` | ⚠️ raw 原值只读；AG withdraw 常见 YYMMDD 候选，舰船撤出样本全为0，Location withdrawal 编码未确证；delay 哨兵保留，不转换日历日期 | `witp_mem_reinforcement_report` 实测：3舰 / 495 AG / 33 Location 单位候选 |
| 7.2.2 | **Withdraw** | ⚠️ | `witp_mem_set_ag_withdraw` 写运行时字段 off392；实际撤出结算/存档持久化未端到端验证 |
| 7.2.3 | 转移基地 | ✅ | reinforceBase |
| 7.2.4 | **空运/空投** | ✅ | `witp_mem_ag_transport`（码 10=SUPPLY_TRANSPORT / 11=TROOP_TRANSPORT，实测确认）|
| 7.3 | Air Group Resizing | ✅ | maxPlanes |
| 7.2.2 | Disband | ⚠️ | `witp_mem_clear_object(kind=airgroup)` 可清空记录 |
| 7.3.1 | Detachments 拆分 | ⚠️ | `witp_mem_clone_object(kind=airgroup)` 可复制记录到空槽 |

## 四、ch08 地面（75%）

| 手册节 | 内容 | 状态 | 实现 |
|---|---|---|---|
| 8.2.1.1 | Operations Mode | ✅ | operationsMode（off906） |
| 8.2.1.2 | Combat Orders | ✅ | combatMode（off110） |
| 8.2.1.3 | **Set All Movement** | ✅ | `witp_mem_set_all_ground_orders` |
| 8.2.1.4 | Objectives | ✅ | prepTarget（off102） |
| 8.3.1 | 陆上移动 | ✅ | marchDir/marchLen/destX/destY |
| 8.3.4 | 运输地面部队 | ⚠️ | 通过 TF 装载间接实现 |
| — | 部队拆分/合并 | ⚠️ | `witp_mem_split_ground_unit` 可拆分主记录（device 明细未拆） |
| 8.11 | Squad Upgrades | ✅ | `witp_mem_set_squad_upgrade`（device.off60，写 259 保留）|

## 五、ch09 基地（50%）

| 手册节 | 内容 | 状态 | 实现 |
|---|---|---|---|
| 9.4.2 | 港口/机场/要塞扩建 | ✅ | portExpand/airfieldExpand/fortExpand（u8） |
| 9.3.3 | 港口容量 | ✅ | 只读 |
| 9.5 | **HQ 变更** | ✅ | `witp_mem_set_base_hq`（location.off118，写 5 保留）|
| 9.3.2 | 被占领港口的舰船 | — | 引擎自动处理，无玩家命令 |

## 六、ch11 政治点（0%）

| 手册节 | 内容 | 状态 | 说明 |
|---|---|---|---|
| 11.1 | Changing Leaders | ⚠️ | 命令源 `location.off128` 已定位；禁止从 TF home 自动推断 Location，政治点/存档采纳仍需端到端验证 |
| 11.1.2 | Ship Withdrawals | ⚠️ | 字段 `shipWithdrawal@44` / `shipReturn@48` 已定位，但当前剧本 92 条命名舰船样本全部为0；非零语义/政治点结算未验证，不能称为字段不存在 |

## 七、ch14 舰船修理（100%）

| 手册节 | 内容 | 状态 | 实现 |
|---|---|---|---|
| 14.1.1 | Upgrades | ✅ | upgrade（off365） |
| 14.1.2 | Conversions | ✅ | tempAPConv/convDelay |
| 14.2.2 | 修理优先级/模式 | ✅ | repairPriority/repairMode |
| 14.2.2.2 | **全港批量修理** | ✅ | `witp_mem_repair_all_in_port` |

## 八、ch15 后勤（14%）

| 手册节 | 内容 | 状态 |
|---|---|---|
| 15.1-15.4 | 补给生成/运输 | ⚠️ 只读 |
| 15.5 | Automatic Convoys | — | 引擎自动行为，无玩家命令字段 |
| 15.6 | 占领基地资源 | — | 引擎自动结算，无玩家命令 |

## 九、MCP 工具（45 个）

**内存工具 25 个**（全部零 OCR/键鼠）：
- 对象通用：`witp_mem_object_list/_show/_set/_find`（9 类）
- TF：`witp_mem_list_tfs` `witp_mem_show_tf` `witp_mem_set_tf` `witp_mem_set_tf_waypoints` `witp_mem_set_tf_follow` `witp_mem_set_tf_speed` `witp_mem_set_tf_leader` `witp_mem_create_tf` `witp_mem_disband_tf` `witp_mem_transfer_ship` `witp_mem_tf_members`
- 航空：`witp_mem_airgroups` `witp_mem_show_airgroup` `witp_mem_set_airgroup` `witp_mem_set_ag_withdraw` `witp_mem_ag_transport`
- 基地：`witp_mem_show_base` `witp_mem_set_base` `witp_mem_find_base` `witp_mem_repair_all_in_port`
- 地面：`witp_mem_set_all_ground_orders`

**存档工具**：`witp_status` `witp_taskforces` `witp_airgroups` `witp_bases` `witp_ground_units` `witp_ships` `witp_saves` `witp_reports` + 9 个存档写入工具 + `witp_end_turn`


## ★v6 新增：新建/删除记录能力（本轮突破）★

之前判定「需新建记录」的项**不可行**，这是错的。实测：

**复制记录到空槽可行** —— 把 LOC110(Australia Command) 复制到空槽 slot1，
过回合后 `wpae000.pws` 完整保留该记录（X=96 Y=160 name='Australia Command'）。

**工具**：
- `witp_mem_clone_object(kind, src_index, dst_index, new_name)` —— 复制任意记录到空槽
- `witp_mem_clear_object(kind, index)` —— 清空任意记录（解散/删除）
- `witp_mem_split_ground_unit(src_loc, dst_loc, keep_fraction)` —— 地面部队拆分基础

**空槽位置**：Location 数组 slot 1-10 等为 `(65535,65535)` 或全零，可直接使用。

**局限**：克隆只复制主记录，**device 明细（部队编制）不随之拆分**，
因此 `split_ground_unit` 是"拆分框架"，不是完整的手册级拆分。

## ★仍未突破的项（2026-10-20 复核后更新）★

> 复核说明：本表曾列 5 项 blocked，其中 3 项已在此后实现，现重新核实如下。

| 项 | 手册 | 状态 |
|---|---|---|
| ~~换将~~ | 11.1 | ✅ **已打通**：指挥链 = `Location.off128`（TF.off32 为派生只读）。政治点字段已定位 = Leader **off48**（CSV PoliticalPoints 1959/1959 全中）；实测换将挺过结算但**引擎不扣政治点**（扣点在 GUI 命令路径）——`witp_mem_change_commander` |
| ~~基地 HQ 变更~~ | 9.5 | ✅ **已打通**：`attachedHQ@118`（off116 是计算值）——`witp_mem_set_base_hq` |
| ~~舰船损伤写入~~ | 6.5 | ✅ **已有替代**：`witp_mem_repair_all_in_port`（修理模式），损伤本身确为派生字段不可直写 |
| ~~TF 离图移动~~ | 6.2.10 | ✅ **已打通**：`TF.off60` u16 = 离图区 Location ID（1..29）——`witp_mem_tf_move_offmap` |
| 舰船 Withdrawal | 11.1.2 | ⛔ 仍 blocked：字段已定位（`withdrawal@44`/`return@48`）但本剧本 92 舰样本全 0，非零语义无 ground truth |
| TF Docking | 6.2.15 | ⛔ 仍 blocked：未定位状态字段 |
| 舰船损伤直写 | 6.5 | ⛔ 派生字段，引擎结算重算（设计如此） |
| 替换池（飞行员/装备） | ch16 | ⛔ blocked：pilot 数组 20000 槽仅 466 在用，池计数器未定位。10-21 新进展：已枚举存档全部记录类型并锁定随回合演变的候选记录（180000/190240/360000/120000/760960/2608000B），池状态必在其中之一；SCEN 目录有官方 AE Editor.exe 可读池初值（需跑 GUI，未做） |
| ~~自动胜利阈值~~ | ch17 | ✅ **已实现（手册公式派生）**：ch17.1/17.2 给出完整判定——比值 ≥1.75 决定性 / ≥1.25 边缘；自动胜利 1943=4×、1944=3×、1945+=2×（须已进行 365 天）；1946 到时向日方移 2 级、≥3 原子弹再移 1 级。`witp_victory_forecast`（MCP 工具已注册；实测 main t12：ALLIED 8.73×=decisive、1942 年不触发自动胜利）。注：这是公式复算，非引擎内存字段——引擎内部无需逆向 |
| DL 数据源 | ch10 | ⛔ blocked：**且旧标签已证伪**——off135 全图仅 10 个顶级司令部非零（值 1..5），是司令部层级候选，不是侦测等级；真 DL 数据源疑在未识别记录（2608000/760960） |
| ~~天气（ch12.1）~~ | ch12 | ✅ **已实现**：存档 u_len=9 记录 = 9 象限预报（3 存档逐日变化）；ground truth = :97 菜单栏 Forecast:Overcast(2) @Noumea → row-major idx7=2 ✓；`witp_weather_report` |
| ~~基地 VP~~ | ch17.0 | ✅ **已实现**：SCEN CSV `Jvictory/Avictory`（Basic VP）× (LOC off420 port + off422 airfield×2)，补给折减端点 100%/25%（中间线性为假设）；实测 main t12：1124 基地，日 1394 / 盟 10141；`witp_base_vp_report` |

**2026-10-20 本轮新增结论**：
- 研发进度累积 / 船舶建造：确证为**引擎自动行为**，无玩家命令字段（aircraft off194 全 0，与 CSV 无对应）；旧标签 "research@194" 已纠正为未确证字段。
- `clear_tf_destination` 已启用：wpCount=0 写入持久；AMPHIB/SUBPATROL 结算时引擎按任务重推路径（与界面清除行为一致）。
- 到达日期换算已实现：`eta_date = 存档日期 + delay`（S-39 系列三存档验证公式成立）。
- `split_ground_unit` 已补写 device 明细（5×20 槽并行数组按比例拆分，实测 60→30/30）。
- 过回合闭环核验已自动化：`witp_mem_orders_snapshot` / `witp_mem_orders_diff`（实测捕获引擎航路点重排 8-13 处/回合）。

## 十、剩余项的真实障碍

| 类别 | 项 | 障碍 |
|---|---|---|
| 字段未定位 | 换将（ch11）、舰船 Withdraw | Leader↔TF 映射不在 TF 结构里 |
| 引擎计算 | 基地 HQ、舰船损伤 | 写后过回合被引擎覆盖 |
| 需新建记录 | 部队拆分、航空队 Disband/Detach、PT 艇/Barge | 要新建 Location/AirGroup 记录并重建索引 |
| 未研究 | TF 离图移动、Docking、自动运输船团 | 本轮未涉及 |


## ★最终状态（v6）★

| 类别 | 数量 | 说明 |
|---|---|---|
| ✅ 已实现并验证 | 31 | 过回合后引擎存档保留 |
| ⚠️ 部分实现 | 8 | 有工具但有限制（如 device 明细未拆、停泊标志只读）|
| — 引擎自动/只读 | 5 | 无玩家命令，或派生字段（损伤读取已实现）|
| ❌ 未实现 | 6 | 见下 |

### 剩余 6 项的真实性质

| 项 | 性质 | 证据 |
|---|---|---|
| 换将（6.3.6 / 11.1）| **字段不存在** | TF 结构无 leaderID；off350=loadState；Leader 无反向指针；leader ID 在内存命中 1029 处无法收敛 |
| Ship Withdrawals（11.1.2）| **字段不存在** | Ship 结构无任何 YYMMDD 日期字段，引擎按剧本自动排定 |
| HQ 变更（9.5）| **引擎计算** | LOC.off116 写值被改回；off176 是数组起点 |
| Squad Upgrades（8.11）| **需改 device 记录** | Device 结构已定位（236B），upgrade 字段未标定 |
| TF 离图（6.2.10）| **剧本限制** | LOC.off760 是离图区编号，珊瑚海剧本无离图基地（全为 0）|

其中「换将」「Ship Withdrawals」「HQ 变更」经多轮静态分析确认**不存在可写字段**，不是实现缺陷。
「Squad Upgrades」和「TF 离图」属本剧本无法验证（前者需改静态数据，后者剧本无离图区）。

### 本轮新增工具（48 个总计，其中内存工具 28 个）

`witp_mem_clone_object` / `witp_mem_clear_object` / `witp_mem_split_ground_unit`
/ `witp_mem_create_tf` / `witp_mem_disband_tf` / `witp_mem_set_tf_speed`
/ `witp_mem_set_ag_withdraw` / `witp_mem_repair_all_in_port` / `witp_mem_set_all_ground_orders`
/ `witp_mem_ag_transport`


## ★最终状态（v7）★

| 类别 | 数量 |
|---|---|
| ✅ 已实现并过回合验证 | **34** |
| ⚠️ 部分实现（有限制）| 9 |
| — 引擎自动/派生字段 | 6 |
| ❌ 未实现 | **4**（换将重复计 2 次，实为 3 项）|

### 剩余 3 项的性质（均已穷尽静态手段）

| 项 | 性质 | 穷尽的证据 |
|---|---|---|
| 换将（6.3.6 = 11.1）| **字段不存在** | ① TF 结构无 leaderID（逐偏移扫描，各 TF 值必须互不相同 → 0 命中）② off350 是 loadState（TF2=99，其余 0）③ Leader 结构无反向指针 ④ leader ID 内存命中 1029 处无法收敛 ⑤ TF↔Leader 配对代码仅 2 处且是存档加载函数 |
| Ship Withdrawals（11.1.2）| **字段不存在** | Ship 结构 464 字节全扫描，无任何 YYMMDD 格式日期（400000-460000）|
| TF 离图移动（6.2.10）| **编码未知** | ① 离图区是 Location 1-29，坐标 65535 ② 航路点写 65535 被引擎清空（wpCount→0）③ destBase 写 Location ID 被改回 0 ④ Location.off760（离图编号）全为 0，本剧本无离图区 |

### 本轮新增（v6→v7）

| 能力 | 字段 | 验证 |
|---|---|---|
| Squad Upgrades | `device.off60`（upgrade 目标设备 ID）| 写 259 保留 ✓ |
| 基地 HQ 变更 | `location.off118`（归属司令部编号）| 写 5 保留 ✓ |
| TF 航路点写入复核 | `taskforce.wp/wpCount/wpAlloc` | TF7 写 3 点保留 ✓（TF1 失败因其 mission=AIRCOMBAT 不移动）|

MCP 工具 **50 个**，内存工具 **30 个**，全部零 OCR/键鼠。

## ★v7 新增字段（2026-10-19）★

| 字段 | 偏移 | 类型 | 说明 |
|---|---|---|---|
| `device.upgradeTo` | **60** | u16 | Squad/设备升级目标（99=无）。实测所有舰炮指向 41 |
| `location.attachedHQ` | **118** | u16 | 基地归属的司令部编号（1..30）。实测 4th Fleet=5, Southeast Fleet=5 |
| `taskforce.atBase` | **60** | u16 | TF 当前所在基地（0=海上） |
| `taskforce.docked` | **401/402** | u8 | 停泊标志（引擎按航路点重算，只读） |

★ 新增工具：`witp_mem_set_squad_upgrade` / `witp_mem_set_base_hq`

★ 航路点写入复核：TF7（mission=AMPHIB，在航行）写 3 点过回合保留；
  TF1（mission=AIRCOMBAT）写入会被恢复 —— **非移动 TF 的航路点由引擎托管**。


## ★v8 突破：换将 + TF 离图移动（两项原本 blocked）★

### 换将 —— `location.off128` (u32) = leader ID

**定位过程**（纯静态）：
1. 搜字符串 `Cdr:` → VA `0x830c74`，引用点 `0x66ed52` / `0x66f100`（TF 详情面板显示指挥官）
2. 反汇编 `0x66ec46-0x66ec59`：
   ```
   0x66ec4d: imul  $0x494,%ecx,%ecx      ; Location 步长 1172
   0x66ec53: mov  0x4570cd0(%ecx),%edx    ; → 0x4570cd0 - 0x4570c50 = 0x80 = 128
   0x66ec59: mov  %edx,-0x18(%ebp)         ; 存为 leaderID
   ```
3. 同一函数 `0x66ecc0` 还比对 `Ship.off32`（`0x1a14398 - 0x1a14378 = 32`）
   → 证实逻辑：**TF 指挥官 = 其驻留 Location 的 leader**

**验证**：`LOC27.off128` 写 1（Abe, Heisuke）→ 过回合存档保留 1 ✓
**且**：`TF1` 旗舰 `ship.off32` 自动同步为 1 ⇒ 证明 off128 是命令源、off32 是派生值

| Location | 名称 | off128 | 对应将领 |
|---|---|---|---|
| LOC20 | 4th Fleet | 7064 | Yoshinaka, A. |
| LOC27 | Southeast Fleet | 3750 | Kusaka, J. |
| LOC110 | Australia Command | 16695 | Blamey, T.A. |
| LOC6062 | Port Moresby | 18382 | Morris B. M. |

### TF 离图移动 —— `taskforce.off60` (u16) = 目的地 Location ID

```
0 = 海上
1..29 = 离图区（General Defence / Kwantung / 5th Fleet / …）
992 = Rabaul（正常坐标基地）
```

**验证**：`TF1.off60` 写 3（Kwantung 离图区）→ 过回合存档保留 3 ✓
（`off58` 同时变为 196608，是引擎设置的伴随标志）

**关键教训**：离图移动**不用航路点表达**。
航路点写 65535 会被引擎清空（wpCount→0），因为 TF 航路点是 u16 坐标对，
无法承载「离图区」这一非坐标概念。

**新增工具**：`witp_mem_list_offmap_areas` / `witp_mem_tf_move_offmap`
（实测本剧本有 188 个离图区槽位）

### ★Ship Withdrawals —— 已穷尽，确认无可写字段★

四项独立证据：
1. Ship 结构 464 字节全扫描，**无任何 YYMMDD 格式日期**（400000-460000）
2. `ship[5] off360-463` 批量写入唯一标记 → 仅末尾边界保留
   （那是结构尾部未被覆写区，不是字段）
3. `Withdraw Ship` 字符串引用点 `0x658968` 的 ±1200 字节范围内，
   **无任何 Ship/Location 结构访问**
4. 该路径调用的 5 个子函数（`0x4f5400` `0x4f4f80` `0x4f1320` `0x54c800` `0x6b46a0`）
   内部**也不触碰** Ship/Location 结构

★ 结论：舰船撤编**不通过可写结构字段实现**，由引擎按政治点在结算时动态处理。

### 批量标记实验的局限（教训）

对 TF 结构后半段做「108 个位置全写标记」实验时，得到 30 个"保留"，
但标记值与位置**对不上**（off348 得到 2304 而非 2348）——
说明引擎在结算时**重排/覆写**了这些字段。
★ 因此**批量筛选法只在结构尾部有效**，不能用于中段字段判定。


## ★v9 修正与新增（2026-10-19）★

### ★重大修正：航空任务码（之前是我凭空猜的）★

我在 v7 给 `witp_mem_ag_transport` 写的任务码 **30-33 是错的**（凭空推断，未验证）。

**实测确认的正确码表**（来源：内存任务名指针表 `@0x85406c`，12 项）：

| 码 | 任务 | 码 | 任务 |
|---|---|---|---|
| 1 | AIRFIELD_ATTACK | 8 | NAVAL_SEARCH |
| 2 | PORT_ATTACK | 9 | ASW_PATROL |
| 3 | NAVAL_ATTACK | 10 | SUPPLY_TRANSPORT |
| 4 | GROUND_ATTACK | 11 | TROOP_TRANSPORT |
| 5 | SWEEP | 16 | TRAINING |
| 6 | ESCORT | | |
| 7 | RECON | | |

验证方式：给 5 个 AG 分别写入 8/9/10/12/13，过回合后 4 个保留（AG3 的 11→10 是因它本就为 10，被引擎重置）。
码 11（TROOP_TRANSPORT）**需配合 targetX/targetY** 才不被重置。

新增 `witp_mem_ag_missions` 工具返回此表。

### 舰船损伤读取工具化

`witp_mem_damage_report` — 全舰队 Sys/Flt/Eng/Fire 汇总，按损伤总量排序。
损伤四值偏移：`fire 331 / sys 332 / flt 333 / eng 335`（**注意界面表头顺序是 Sys/Flt/Eng/Fire，与内存偏移顺序不同**）。

### ★TF Retirement 确认不可走内存★

反汇编定位：字符串 `Remain on Station`(0x82c750) / `Retirement Allowed`(0x82c764)
的引用点在 `0x640638` / `0x640677`，其所在函数入口 `0x640550`。

**该函数体内（往后 2000 字节）完全没有 TF 结构字段访问**，
且 ±3KB 范围内也搜不到任何 `0x6da5xxx` 引用。

★ 结论：Retirement 状态存在 **UI 层局部变量**（唯一相关全局 `0x8529c8`），
  不在 TF 结构里 —— 因为它是「每个 TF 一个」的状态而全局变量只有一份。
  ⇒ 只能通过界面操作，无法纯内存写入。

### 实验方法教训

批量标记实验（216 个 u8 位置全写标记）后，把 TF7 的 211/216「保留」误读为其他 TF 的值。
真实原因是**我的标记值恰好与其他 TF 的真实值重合**（如 off349 写入 1，
而 TF1 真实值也是 1）⇒ 误判为「其他 TF 的值」。
★ 批量标记必须用**不会与真实值重合**的标记（如大偏移量 + 校验位）。



## v10 当前状态复核（2026-10-20）

> 前文 v5-v9 是历史过程记录，数字和若干状态已被后续证据推翻；不应拿它们计算当前覆盖率。当前 MCP 实测 66 个唯一工具，但“工具存在”不等于功能完整。

### v10 已验证新增（更新）

| 功能 | 实测证据 | 边界 |
|---|---|---|
| 测试实例进程路由 | `WITP_INSTANCE` 指向 :97、`WITP_WINEPREFIX` 故意指向主辅助前缀时，`game_pid()` 仍选 PID 3453887；进程环境核实实际 prefix 为 `/root/.wine-witp-mcp/prefix` | 该时点实例验证；PID 会变化 |
| Victory Points | `witp_mem_victory_report(wpae000.pws)` 与 `witp_core.GameState` 一致：turn=5, Japan=149, Allied=1293 | 当前分值可读；自动胜利阈值/完整公式未验证 |
| 经济/行业快照 | MCP `witp_mem_economy_report` 对存档返回 585 个基地位置；资源 1,527,089、油 2,129,946、燃油 11,221,527、补给 5,123,831；设施与行业设备数已映射 | 指定存档快照；航空器/引擎工厂、R&D、生产池及到达日程不覆盖；设施损坏语义需另做校验 |
| 信息报告聚合 | MCP `witp_mem_information_report` 成功返回 5 份最新战报/SIGINT/作战事件等文件 | 不等于完整复刻 ch05 所有信息子屏 |
| MCP 工具集合 | MCP `list_tools()`=66，名称唯一；源码 AST 也是66个唯一 `@mcp.tool()` | 仅代表接口数量与注册，不等于功能全实现 |


### MCP 无 GUI 路径审计

- AST 按每个 `@mcp.tool()` 函数检查：当前无 GUI、OCR、截图、VNC、xdotool、鼠标/点击调用；MCP 工具函数定义 66 个且唯一。
- `witp_clear_tf_destination` 与 `witp_end_turn` 仍为明确拒绝执行；`witp_set_tf_retirement` / `witp_get_tf_retirement` **已启用**（off388，CSV 交叉验证 25/25）。集成测试确认拒绝项返回 `ok=false`、启用项返回真实数据。
- 代价：结束回合与清除目的地暂时不提供操作功能。不得宣称“所有命令可操作”。
- `gui_commands` 模块仍有未使用 import，可进一步清理，但 MCP 工具函数中无调用链。

### 仍未闭环实现（按手册缺口）

| 章节 | 尚缺功能 | 当前状态 |
|---|---|---|
| ch05 信息显示 | 飞行员补充池、飞机/引擎生产池、完整撤出清单 | `witp_mem_information_report` 文本聚合、`witp_mem_reinforcement_report` 状态分类、`witp_mem_production_report` 工厂清单已有；飞行员/机组补充池与生产池余量未解码 |
| ch06 海军 | 清除 TF 目的地、程序化结束回合、完整 Docking、PT/Barge/Midget 新建端到端 | **Retirement 已完成**（off388）；清目的地/结束回合仍禁用；结构克隆不等于完整语义 |
| ch07 航空 | 完整 Detach/Disband、空运全约束验证 | clone/clear 只是主记录；运输任务码已按实测码表实现 |
| ch08 地面 | 拆分时同步写 device 明细；完整运输上船/下船 | `witp_mem_ground_unit_roster` 已可读 5 组并行数组与缺编；`witp_mem_split_ground_unit` 仍只复制主记录 |
| ch10 DL | DL 只读候选（0..5） | 数据源与写入语义均未确证；当前仅作为候选值读出 |
| ch13 生产 | 工厂转换/扩建写入、研发进度累积、船舶建造队列 | 工厂与机型研发**读层已实现**（1402/1405 点、27 基地、292 机型）；写入类命令未定位 |
| ch16 增援 | 替换池、日历换算 | 到达/沉没/撤编/预备/未组建状态分类已实现并跨 3 存档验证；飞行员与装备替换池未解码 |
| ch17 胜利条件 | 战后胜利等级与完整计分公式 | **等级判定已实现**（`witp_victory_forecast`，手册 ch17 比值公式 + 已验证的 VP 读层）；基地 VP 终局计分、原子弹计数读层暂无来源 |

### 当前不应计入完成的历史条目纠错

- `witp_mem_change_commander` 仅写入调用者显式指定的 Location `off128` 并即时读回；不执行政治点扣款、合法性/占用校验，也不保证结算或存档采纳。
- `witp_mem_reinforcement_report(save)`：raw-field 候选汇总已实现并经 MCP 实测：3 舰 / 495 AG / 33 Location 单位；实际到达计划、替换池和日期换算仍未完整实现。MCP 当前共64个唯一工具。
- `witp_mem_economy_report` 当前回读 585 个基地及库存/行业设备数量；行业 Device ID 映射只是一部分生产信息，飞机/引擎工厂、R&D 队列、生产池与设施损坏语义尚未证明覆盖完整。
- `witp_mem_ag_missions` 的验证说明已更新：任务名表静态反汇编；8/9/10 保留，11 需目标格，16=TRAINING；未经验证的码不作保证。
- ch06 Retirement 只能通过 GUI 的旧历史说法**已被推翻**：off388 是真实字段，运行内存与 CSV 25/25 一致，`witp_set_tf_retirement` / `witp_get_tf_retirement` 已启用。
- 旧字段表把 `routing` 记在 369、`maxReact` 记在 355，**都是错的**：369 恒 0、355 存疑；真实值为 routing=356、maxReact=389，均 25/25 命中。
- `witp_mem_ground_unit_roster` 已用 WITPloc003.csv 的 WpnDevID/TOEDevID 列逐项核对，确认 Location 记录含 5 组 20 槽并行数组（136/176/216/336/376）。`split_ground_unit` 尚未写 device 明细。
- `witp_mem_production_report` 已确认「基地 deviceID≥2000 → 机型索引(id−2000)」与「device type 27 = 引擎厂」，均用真实存档数据验证；工厂转换/扩建写入仍未实现。
- `witp_mem_reinforcement_report` 的 delay 语义已跨 3 个存档验证：舰船每日递减、19999 与沉没日期 0 例外、航空队 9999/19999 区别明确。

**结论（v11）**：MCP 现为 **66 个唯一工具**，工具体 AST 扫描 0 处 GUI/OCR/键鼠调用。本轮完成：
① 修复 i32/字符串字段类型缺失；② 新增 `witp_mem_production_report`（飞机/引擎工厂+机型研发）；
③ 新增 `witp_mem_ground_unit_roster`（5 组装备并行数组+缺编）；④ 增援报告改为跨 3 存档验证的状态分类；
⑤ **推翻旧结论**：TF Retirement 不是 UI 局部变量，而是 `off388`，运行内存 vs CSV 25/25，
   并纠正 `routing`(356) 与 `maxReact`(389) 的旧误记。

仍未闭环：结束回合、清除目的地、工厂转换/扩建写入、研发进度累积、船舶建造队列、
替换池、自动胜利触发逻辑、航空队 Detach/Disband 完整语义、拆分部队时写 device 明细。
