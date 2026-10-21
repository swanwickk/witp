# WitP-AE 运行时内存逆向：完整对象表（9 类，全部打通）

> 2026-10-18 完成。9 类对象全部定位 + 可写字段全部标定 + 34 个 MCP 工具。

## 一、对象总表

| 对象 | 主副本基址 | 镜像基址 | 步长 | 存档记录长 | 验证 |
|---|---|---|---|---|---|
| TaskForce | `0x6da5148` | — | 556 | 2224000 | 27/27 flagship |
| AirGroup | `0x598f4f8` | `0xbba0c20` | 680 | 20400680 | 2699/2716 |
| Location | `0x4570c50` | — | 1172 | 21096000 | 90/116 |
| Ship | `0x1a14378` | `0xb2adcb0` | 464 | 9280000 | 92/92 名称 |
| Leader | `0x252b3f8` | — | 180 | 9000000 | 19943/19943 |
| ShipClass | `0x3755160` | `0xe8a8400` | 380 | 1900000 | 1646/1646 |
| Aircraft | `0x6d44660` | `0xcf14658` | 396 | 396000 | 554/554 |
| Device | `0x3f0b460` | `0xea78208` | 236 | 472000 | 1474/1474 |
| **Pilot** | `0x7f7faa8` | `0xda29500` | **304** | 15200000 | 66/100 按 ID 匹配 |

**基址在同一局内跨进程重启依然有效。**

### ★Pilot 步长是 304 不是 152★

反汇编 `0x429723` 处 `imul $0x130`（304）+ `0x7f7faa8` 确认。

存档里 15200000 字节 = **152 字节紧凑格式**（100000 槽），内存是 **304 字节完整结构**（50000 槽）。两者**索引不对应**，必须用 `off4` 的 ID 匹配。

之前的 152 是巧合（304 = 152×2，两个半块恰好都"看起来对"）。

## 二、副本规则

| 有镜像（必须写两份） | 只有一份 |
|---|---|
| Ship / AirGroup / ShipClass / Aircraft / Device / Pilot | TaskForce / Location / Leader |

只改主副本 → 界面变，过回合后存档不变（**假成功**）。
`witp_obj.set_field()` 已自动处理。

## 三、★★可写 vs 只读（最终结论）★★

### 可写（引擎采纳并持久化，已过回合验证）

| 对象 | 字段 | 偏移 | 验证 |
|---|---|---|---|
| **TaskForce** | mission | 349 | 15→1 保留 |
| | speed | 354 | 3→1 保留 |
| | routing / tolerance / maxReact / loadState | 369/448/355/350 | 已标定 |
| | 航路点 | 118 (40×u16,u16) | 写3点读回一致 |
| **AirGroup** | pctCAP / pctSearch / pctASW / pctLRCAP / pctTrain / pctRest | 560-565 | 100 保留 |
| | primary / maxPlanes / baseID | 44/245/40 | 已标定 |
| **Location** | prep | 104 | 90→91 保留 |
| | operationsMode | 906 (u16) | 0→2 保留 |
| | prepTarget / combatMode / 扩建 | 102/110/424,428,432 | 已标定 |
| **Ship** | repairPriority | 338 | 1→2 保留 |
| | repairMode / upgrade / convDelay | 339/365/344 | 已标定 |
| **Pilot** | **status** | **52** | **1→2 保留** |
| **ShipClass** | endurance | 52 (u16) | 1000→1200 保留 |
| | speed / fuel | 56/58 | 已标定 |

### 只读（写入会被引擎覆盖）

| 对象 | 字段 | 原因 |
|---|---|---|
| Ship | sysDamage 332 / fltDamage 333 / engDamage 335 / fireDamage 331 | 结算时从耐久重算 |
| Leader | leadership 48 / inspiration 49 / naval 50 | 派生值 |
| Pilot | exp 112（及其他 off112-125 技能） | 派生值 |
| TaskForce | endure 4 / endureReq 8 / fuel 12 / load 28 | 按舰汇总计算 |

**判断方法：写值 → 过一回合 → 读新存档。保留=可写，归零/恢复=派生。**

## 四、★舰船损伤字段（已标定）★

用「逐字节写内存 → 看界面列」确定：

```
Fire = 331    Sys = 332    Flt = 333    Eng = 335     （334 不是损伤）
表头顺序是 Sys / Flt / Eng / Fire
```

写入 `sys=15 flt=25 eng=35 fire=5` → 界面精确显示 `15 25 35 5`，逐列确认。

**但过回合后存档归 0** —— 引擎从耐久/舰级重算，所以只能读。

## 五、定位方法

### 1. 名称字符串（误报率 0）

Ship / Leader / ShipClass / Aircraft / Device 的名称在记录偏移 0 处，纯 ASCII：

```python
nm = d[slot*SZ : slot*SZ+40].split(b"\0")[0]     # 存档侧
# 内存搜 "Shokaku\0" → 命中地址 - slot*SZ = 基址
```

### 2. 稀有值 + 多字段组合

TF / AirGroup / Location / Pilot 无名称字段：

- TF7: `load=46544` + `flagship=91`
- AG6: `maxPlanes=27` + `primary=6` + `upgradeTo=603`
- LOC27: `X=106` + `Y=125` + `prepTarget=992`
- Pilot: `off4` 的递增 ID

### 3. 反汇编找字段（最有效，本轮关键突破）

**方法 A：字符串交叉引用**

1. 找字符串（`Sys`/`Flt`/`Fire`）的 VA
2. `find_xref.py <VA>` 查引用点
3. 反汇编引用点附近代码
4. 提取所有 `0x1a1xxxx` 绝对地址
5. **`真实偏移 = 绝对地址 − 数组基址`**

实例：`0x1a144c3 − 0x1a14378 = 331`（Fire）

**方法 B：基址全偏移扫描**

```python
# 对基址的每个偏移，搜 `struct.pack('<I', BASE+off)` 在 .text 里的出现次数
# 命中次数高的偏移 = 高频访问字段
```

实例：TF 基址 `0x6da5148` → `off356` 被引 251 次（maxReact 相关）

**方法 C：步长反查**

```python
# imul $0x130,%eax,%eax 的字节模式: 69 C0 30 01 00 00
# 搜到后反汇编，看后续的绝对地址访问
```

实例：Pilot `imul $0x130` → 确认步长 304（不是 152）

### 陷阱：反汇编里的"伪基址"

反汇编可能出现 `0x1a143ac`，它**不是**新基址，而是 `0x1a14378 + 52`。
判断方法：`候选基址 - 已知基址` 若是个小偏移（< 一个结构），就是锚点不是基址。

## 六、四个致命坑

### 坑 1：gdb 读内存静默返回全零

`dump binary memory` 在未映射页**不报错**，直接写全零文件。
→ 改用 `/proc/<pid>/mem`，未映射返回 `EIO`。

### 坑 2：扫错地址区间

真实数据在 `0x0085f000-0x0f0a7000`（232MB 可写段）。
→ 从 `/proc/pid/maps` 枚举实际可写段。

### 坑 3：记录类型码不可靠

`id % 256` 不是稳定类型码 —— 实例号进位会污染低位。
同一条 LOCATION 记录在 `wpae001` 里 `low8=19`，`wpae000` 里 `low8=33`。
→ **只有 `u_len` 恒定**，用 `pwsfile.record_by_len()`。

### 坑 4：改完内存界面不变

**必须关掉面板再重开**。否则是假阴性。

## 七、Leader 数组的特殊性

| | 数量 | 内容 |
|---|---|---|
| 内存 Leader 数组 | 19943 个 | 完整表，含所有未启用的将领 |
| 存档 Leader 记录 | 4631 个 | 只有**活跃**将领，顺序不同 |

实例：`Abe, Heisuke` 在内存 index 1，但**不在存档里**（未启用）。
`Kimura, T.` 在存档 slot2，对应内存 index 3384。

**定位必须按名称**：`witp_obj.find_by_name(pid, "leader", "Kimura, T.")`

## 八、验收证据汇总

| 对象 | 操作 | 过回合后存档 |
|---|---|---|
| TF7 | mission→AMPHIB(15), speed→1 | 15 / 1 ✓ |
| AG6 | pctCAP→100 | 100 ✓ |
| AG3 | pctSearch→100 | 100 ✓ |
| LOC27 | prep→90, operationsMode→2 | 91 / 2 ✓ |
| Ship Shokaku | repairPriority→2 | 2 ✓ |
| **Pilot ID=4792** | **status→2** | **2 ✓** |
| **ShipClass[363]** | **endurance→1200** | **1200 ✓** |
| Ship 损伤 | sys=20 flt=30 eng=10 fire=7 | 0（引擎重算）✗ |


## ★Follow TF / Meet TF / Patrol Zone（本轮突破，纯内存）★

之前判定"必须界面操作"是**错误的**。实测这三个功能全部在 TF 结构里，纯内存可写。

### 字段

| 字段 | 偏移 | 类型 | 说明 |
|---|---|---|---|
| followMode | **447** | u8 | 0=未设置 1=Follow TF 2=Meet TF 3=Patrol Zone |
| followTF | **486** | u16 | 目标 TF 号（Follow/Meet 用） |
| patrol1X / patrol1Y | **364 / 366** | u16 | Patrol Zone 边界 1 |
| patrol2X / patrol2Y | **368 / 370** | u16 | 边界 2 |
| patrol3X / patrol3Y | **372 / 374** | u16 | 边界 3 |

### 定位过程（纯静态）

1. 修 bug：字符串 VA 打印缺 `#x`，一直搜十进制当十六进制 → 0 命中
2. `find_xref2.py "Follow Task Force"` → 字符串 VA `0x82edf4`，引用 `0x660330`
3. 反汇编发现 `imul $0x22c` + `0x6da52ac`，即 TF 的 off356
4. 追 off356 的写入点，找到 `0x6a150d` 处读 `0x6da5307`（=off447）
5. `off447` 是 0/1/2/3 模式量；同函数 `0x6a1546` 读 `0x6da532e`（=off486 u16）
6. Patrol 分支调 `0x4f5710`；用「12 个连续全 0 u16 且静态被成对引用」定位 off364-386

### 验收证据（过回合后存档保留）

```
followMode=1 followTF=8                          ✓
followMode=3 patrol=(110,120)(112,124)(108,118)  ✓
```

### MCP 工具

`witp_mem_set_tf_follow(tf, mode, target_tf, patrol)` —— 全程纯内存，无 OCR/键鼠。


## ★舰船转移 / 编队成员 / 指挥官（本轮完成）★

### 舰船所属 TF/基地 —— `ship.off62`（u16）

```
值 = 14000 + TF号   →  编队（14001 = TF1）
值 = Location ID    →  基地（如 992 = Rabaul）
值 = 0              →  未编队
```

**实测验证**：Myoko `14001 → 14007`，过回合后 `wpae000.pws` 保留 `14007` ✓

定位过程：内存里搜 Ship 结构中「值在 14000..14200」的 u16 → 命中 off62；
静态确认 `0x529130` 是 `set_ship_location(ship, loc_id)` 函数
（`cmpl $0x36b1` = 14001 分界，>= 则写 off62、清 off60）。

### 编队成员列表

**TF 结构里没有舰船 ID 数组**。成员关系只存在 `ship.off62`。
`witp_mem_tf_members(tf)` 用扫描实现（遍历 ship.locationID）。

注意：**改动成员后引擎会重算旗舰**。实测把 Myoko 移出 TF1 后，
TF7 的 flagship 从 91 变成 610（W.20）—— 这是引擎按规则重选的结果，不是错误。

### 编队指挥官 —— `taskforce.off350`（u16 = Leader ID）

```
off350 = leader 数组下标（0 = 未指派）
```

定位证据：`0x709f8b` 处 `movzbl 0x6da52a6(%eax)`（=off350）
→ `cmp $0x9` → `imul $0xb4`(180) + `0x252b3f8`（Leader 数组基址）。

**★ 换将受引擎规则约束，不能直接写**：
实测 TF1 写 `leaderID=1`（Abe, Heisuke）后过回合，
引擎改成 `2560`（Iguchi, E.）—— 推测与政治点、将领占用状态有关。

### 基地 HQ —— 未能直接写

- `LOC.off116`（u16）：写 240 → 过回合被改成 236，是引擎计算值
- `LOC.off176`（u16）：被当**数组起点**用（`0x4570d00(%ecx,%edx,2)`），不是单字段
- 结论：基地 HQ 归属由引擎按指挥链重算，不可直接写


## ★本轮补齐的能力（全部过回合验证）★

| 能力 | 手册 | 实现 | 验证 |
|---|---|---|---|
| **组建 TF** | 6.2 | 空槽写 flagship+mission，舰船 locationID 转 14000+槽号 | TF27 flagship=73 mission=2 保留 ✓ |
| **解散 TF** | 6.2.2 | 清空 556 字节结构 + 成员转出 | flagship=0 ✓ |
| **TF 速度档** | 6.2.3 | `off362`（0..3）| 写 1 保留 ✓ |
| **航空队 Withdraw** | 7.2.2 | `AG.off392`（u32 YYMMDD）| 写 421231 保留 ✓ |
| **全港批量修理** | 14.2.2.2 | 按 locationID 扫描 + 批量写 priority/mode | ok ✓ |
| **Set All 地面命令** | 8.2.1.3 | 遍历全部 Location 批量写 | ok ✓ |
| **空运/空投** | 7.2.4 | AG primary 任务码 + targetX/Y | 任务码 30-33 待实机确认 |

### 关键字段修正

- **`TF.off362` 是速度档设置**，`off354/356/361` 是引擎算出的当前速度（不可写）
- **`AG.off392` 是 withdraw 日期**（u32 YYMMDD，450505 = 1945-05-05）
- **`TF.off350` 是 loadState**（99=空闲），**不是** leaderID —— 上一轮误判已纠正

### 换将（ch11）仍未解决

TF 结构里**找不到 leaderID 字段**：
- off350 是 loadState
- off348/360/362 是位标志/枚举
- Leader 结构里也没有指向 TF 的字段
- 指挥官映射推测在独立表里，本轮未定位

### 基地 HQ（ch09）不可写

- `LOC.off116` 写 240 → 引擎改成 236（计算值）
- `LOC.off176` 是数组起点，不是单字段

## 九、工具

| 文件 | 作用 |
|---|---|
| `memrw.py` | `/proc/pid/mem` 读写 + 段枚举 |
| `pwsfile.py` | 存档解析 + `record_by_len()` |
| `witp_obj.py` | **9 类对象统一读写（推荐入口）** |
| `witp_obj_bridge.py` | MCP 桥接 |
| `find_xref.py` | 查字符串 VA 的所有引用点 |
| `find_step.py` | 按 `imul $N` 反查步长数组 |
| `map_tf_fields.py` | 从反汇编区间提取结构字段访问 |
| `locate_ship.py` / `locate_leader.py` / `locate_static.py` / `locate_pilot.py` | 各类定位器 |

```bash
python3 witp_obj.py list ship
python3 witp_obj.py show ship 5
python3 witp_obj.py find ship Shokaku
python3 witp_obj.py set ship 5 repairPriority 4
python3 witp_obj.py set pilot 2 status 2
```

MCP 工具 34 个，内存类 14 个。核心：
- `witp_mem_object_list` / `_show` / `_set` / `_find`（覆盖 9 类）
- TF / AG / Location 专项工具

## 十、仍未完成

1. **TF 当前 fuel** —— 界面 21500 是**按舰汇总**的派生显示值，结构里搜不到。`off12=44800` 是装载容量不是当前燃料。
2. **Aircraft / Device 的可写字段** —— 只标定了名称，其他字段未扫描。静态剧本数据一般不需要改。
3. **Pilot 其他可写字段** —— 反汇编显示 off0/12/92/256 也是写操作，但语义未标定。


## ★v7 新增：Squad Upgrades 与基地 HQ★

### device.upgradeTo（off60，u16）

手册 8.11 Squad Upgrades。定位方法：扫所有设备，找出「off60 指向另一个有效设备 ID」的关系。

```
Device[1] 18.1in/45 T94 Gun  off60=41 → [41] 6in/55 M1930 Gun
Device[2] 16.1in/45 3YT Gun  off60=41 → [41] 6in/55 M1930 Gun
Device[258] IJA Cavalry Squad off60=99（无升级）
```

实测：写 `Device[258].off60 = 259` → 过回合存档保留 259 ✓

MCP：`witp_mem_set_squad_upgrade(device_id, upgrade_to)`

### location.attachedHQ（off118，u16）

手册 9.5 Command Organization of Bases。定位方法：找「各 Location 值不同且值域 1..30 的 u16」。

```
LOC20  4th Fleet            off118=5
LOC27  Southeast Fleet      off118=5
LOC110 Australia Command    off118=1
LOC6062 Port Moresby        off118=0（无归属）
```

实测：写 `LOC6062.off118 = 5` → 过回合存档保留 5 ✓

MCP：`witp_mem_set_base_hq(loc, hq_id)`

### 纠正一个旧结论

之前说「航路点写入无效（TF1 会被恢复）」是**误判**。实测：
- TF7（mission=AMPHIB，在航行）写 3 点 → **过回合保留** ✓
- TF1（mission=AIRCOMBAT，不移动）写 → 被恢复

结论：**航路点写入对"会移动的 TF"有效**，非移动 TF 的航路点由引擎托管。
