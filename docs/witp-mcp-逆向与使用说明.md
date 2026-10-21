# WitP-AE 逆向与 MCP 操作通道（2026-10-17）

本机英文版《War in the Pacific: Admiral's Edition》1108r9（`/root/.wine-witp/drive_c/1108r9/`）
的存档格式已完整逆向，并封装成 MCP 服务，可直接读写游戏状态与命令，**不再需要模拟鼠标点界面**。

---

## 一、逆向结论（全部实测）

### 1. 存档容器 `.pws`

```
文件 = gzip 头(10B) + raw deflate(整个记录串) + crc32(4B) + 原始长度(4B)
记录串 = { [u16 实例号][u16 记录类型][u32 A][u32 B][zlib 流] } × N
```

- **外层是 gzip，但压缩体是 raw deflate（wbits=-15）**，不是 zlib 包装 —— 用
  `zlib.compressobj(9, DEFLATED, -15)` 才能字节级还原。
- 每条记录体是独立的 **zlib 流**（wbits=15，`78 9c` 开头）。
- 记录头 12 字节：`u16 实例号 | u16 记录类型 | u32 A | u32 B`
  - **记录类型**（第 3-4 字节低 4 位）：1=剧本 8=舰船 19=位置(基地/部队) 20=航空队
    21=指挥官 22=飞行员 27=舰级 30=水雷 31=设备 32=机型 38=存档头
  - **A/B**：`id<1000` 的小记录里 A=解压长度、B=压缩长度；
    大记录（实例号高位置位，如 `0x10001`）里 A/B 是**引擎侧校验字段**，
    实测改它们会让 pwsdll 直接崩（access violation）⇒ **必须原样保留**。
- 记录体长度与游戏 DLL 的 ctypes 结构体**完全对齐**：

| 解压长度 | 结构体 | 说明 |
|---|---|---|
| 3000 | 存档头 | 首 200B 是 `Autosave Date: 05/09/42` 之类的注释 |
| 99696 | 剧本块 | 含剧本名、回合数（u16@30）、双方 VP（i32@112/@120） |
| 9280000 | `PWSShip[20000]` × 464B | 舰船 |
| 9000000 | `PWSLeader/Pilot[50000]` × 180B | 指挥官/飞行员 |
| 20400680 | `PWSAirGroup[30001]` × 680B | 航空队 |
| 21096000 | `PWSLocation[18000]` × 1172B | 基地 + 地面部队 + 指挥部 |
| 2224000 | `PWSTaskGroup[4000]` × 556B | 编队 |
| 396000 | `PWSAircraft[1000]` × 396B | 机型 |
| 472000 | `PWSDevice[2000]` × 236B | 设备 |
| 1900000 | `PWSShipClass[5000]` × 380B | 舰级 |

### 2. ★写档的硬门槛：压缩流长度必须与原档一致★

引擎（`pwsdll.dll`）读档时**逐条校验压缩流长度**。只要某条记录的压缩流长度变了，
就报 `Restore size larger than expected` 并中断读档（实测：改 1 个字节导致 zlib 长度
+1/+2，读档即失败）。

**解法（本项目的核心技巧）**：不靠改游戏数据凑长度，而是往 deflate 流里追加
**空存储块**（`00 00 00 FF FF`，LEN=0，不产生任何解压输出），每块固定 5 字节；
最后一个块置 BFINAL=1。配合参数网格（level × memLevel × windowBits × strategy）
抖动压缩长度，总能凑出 `(目标长度 - 正文 - 4) % 5 == 0` 的组合，把流长度精确顶到原值。

⇒ 改写后的存档**解压内容完全正确、压缩流长度与原档一模一样**，引擎照常接受
（实测 `message=End of file`，且回读到改后的值）。

### 3. 可写命令字段（偏移，均已用游戏 DLL 回读验证）

**编队 `PWSTaskGroup`（556B）**
| 偏移 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 44 | tfFlagship | i32 | 旗舰舰船号（也是编队标识） |
| 54 | tfHomePort | u16 | 母港位置号 |
| 118 | 航路点数组 | 8×(u16 x, u16 y) | 首点=当前格，末点=目的地，空点=(0,0) |
| 349 | tfMission | u8 | 1=空战 2=水面战 3=炮击 4=快速运输 5=运输 6=海上补给 7=布雷 8=潜艇巡逻 11=货运 15=两栖 18=油船 25=护航… |
| 354 | tfSpeed | u8 | 0=全速 3=巡航… |

**航空队 `PWSAirGroup`（680B）**
| 偏移 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 40 | baseID | u16 | 驻地基地号 |
| 44 | primaryMission | u16 | 1=机场攻击 3=对海攻击 6=护航/CAP 8=海上搜索 9=反潜 16=侦察… |
| 46 | secondaryMission | u16 | 次任务 |
| 192/196 | targetX/Y | u16 | 目标格 |
| 560–565 | acPctCAP / LRCAP / ASW / Search / Train / Rest | u8 | 巡逻比例 % |

**位置（基地/地面部队）`PWSLocation`（1172B）**
| 偏移 | 字段 | 类型 |
|---|---|---|
| 36/38 | X / Y | u16 |
| 104 | prepPercent | u16 |
| 110 | combatMode | u8 |
| 651/652 | marchDir / marchLen | u8 |
| 662/664 | destX / destY | u16 |
| 422/426/430 | port / airfield / fort | u16 |
| 508/520/528/536 | resources / oil / fuel / supply | i32 |
| 960/962 | airgroupStack / aircraftStack | u16 |

### 4. 读层已完全脱离游戏 DLL

`witp_core.py` 纯 Python 解析（不需要 Wine、32 位解释器、游戏进程），
解析 1 份 ~1MB 存档约 **0.15 秒**（DLL 路径约 10 秒且要跑 Wine）。
字段与 DLL 结果逐一核对一致（Truk/Port Moresby/Rabaul 的港口/机场/补给/坐标全对）。

---

## 二、MCP 服务

### 位置与注册

```
服务：/root/.hermes/mcp-servers/witp-mcp/server.py
解释器：/root/.hermes/hermes-agent/venv/bin/python3（mcp 1.28.1）
注册：default 与 witp 两个 profile 的 config.yaml → mcp_servers.witp-ae
```

注册命令（已执行，勿重复）：

```bash
hermes config set mcp_servers.witp-ae.command /root/.hermes/hermes-agent/venv/bin/python3
hermes config set mcp_servers.witp-ae.args '["/root/.hermes/mcp-servers/witp-mcp/server.py"]'
hermes config set mcp_servers.witp-ae.enabled true
```

MCP 工具是**延迟加载**的：直接调用会报 “Tool does not exist”，
须先 `tool_search` / `tool_describe` 发现，再 `tool_call`。

### 13 个工具

**读（纯解析，零副作用）**
| 工具 | 作用 |
|---|---|
| `witp_status` | 中文态势摘要：日期/回合/比分/编队一览 |
| `witp_taskforces` | 编队列表（槽位/旗舰/任务/位置→目的地/航路点） |
| `witp_airgroups` | 航空队（驻地/主任务/巡逻比例/战备机/士气） |
| `witp_bases` | 基地（归属/坐标/港口/机场/补给/燃料/驻机） |
| `witp_ground_units` | 地面部队（坐标/行军/目的地/准备度） |
| `witp_saves` | 存档列表（时间/注释） |
| `witp_reports` | 战报文本（GBK 自动转码） |

**写（只生成新存档，绝不覆盖原档）**
| 工具 | 作用 |
|---|---|
| `witp_set_tf_orders` | 改编队任务 + 目的地（自动做引擎回读校验） |
| `witp_set_airgroup_orders` | 改航空队主任务/目标格/CAP/搜索/反潜/训练比例 |
| `witp_set_ground_orders` | 改地面部队目的地/作战模式 |

**游戏进程（有副作用，需 confirm）**
| 工具 | 作用 |
|---|---|
| `witp_screen` | 截图 + 顶栏 OCR（日期/天气/鼠标格） |
| `witp_game_key` | 发按键（白名单 t/a/b/n/esc），需 `confirm=true` |
| `witp_end_turn` | 过回合（E → YES → 等 autosave），需 `confirm=true` |

### 典型闭环

```
1. witp_status()                                    → 看当前态势
2. witp_taskforces(with_ships=true)                 → 找目标编队槽位
3. witp_set_tf_orders(slot=14, mission="BOMBARDMENT",
                      destination_x=108, destination_y=148)
   → 生成 wpaeNNN.pws，engine_verify.ok=true
4. 游戏内载入该存档（主菜单 → LOAD A SAVED GAME → 选槽 → SELECT SAVE GAME）
5. witp_end_turn(confirm=true)                      → 推进一回合
6. witp_status() + witp_reports()                   → 核对结果
```

---

## 三、实测证据（可复核）

```
A) 重打包字节一致：True            （原档 → 解析 → 重打包，逐字节相同）
B) 改写 TF14 任务 1→3、目的地→(108,148)、AG9 CAP 0→60 / 搜索 10→20
C) 游戏引擎 pwsdll.dll 回读改写档：
   ag9_name=Genzan Ku K-1  ag9_cap=60  ag9_search=20  ag9_primary=3  ag9_base=992
   tf14_mission=3  tf14_flagship=3002  tf14_home=1282
   records=62  message=End of file          ← 引擎完整接受
D) MCP 客户端（stdio + ClientSession）实测：13 个工具全部 list 成功，
   witp_status / witp_taskforces / witp_bases / witp_airgroups /
   witp_ground_units / witp_reports / witp_saves / witp_screen 均返回真实数据；
   witp_set_tf_orders 与 witp_set_airgroup_orders 写档 + engine_verify.ok=true；
   witp_set_ground_orders 改 144th Infantry 目的地 (0,0)→(98,128)、作战模式 0→1，
   写档后回读一致、引擎 pwsdll 回读 `End of file`；
   witp_game_key(keys="t", confirm=true) 实测在游戏内打开编队列表（截图确认）。
```

---

## 四、文件清单

```
/root/.hermes/profiles/witp/workspace/witp-reader/
├── pwsfile.py      .pws 容器解析（纯 Python）
├── pwspack.py      容器打包 + 压缩流长度精确回填（空存储块技巧）
├── witp_core.py    纯 Python 读层（GameState：tfs/airgroups/bases/ground_units/ships）
├── witp_orders.py  命令写层（Save：set_tf_mission / set_tf_destination / set_ag / set_loc）
└── dllverify.py    用游戏 pwsdll.dll 回读校验（Wine 32 位 Python 下运行）

/root/.hermes/mcp-servers/witp-mcp/
├── server.py       MCP 服务（13 工具）
├── test_client.py  读工具冒烟测试
├── test_write.py   写工具测试
├── test_e2e.py     端到端测试（status → 改编队 → 改航空队）
└── test_tools.py   参数校验/防护测试
```

---

## 五、已知边界

- 写档要求**改动后压缩流能回到原长度**。极端改动（如把大片零区改成随机数据）可能
  找不到等长组合 → `RuntimeError`，MCP 会返回 `ok=false` 并提示；此时可减少改动量。
- 记录头 A/B 校验字段（大记录）语义仍未解，但**不需要解**：原样保留即可通过引擎校验。
- 汉化版 exe 写出的珊瑚海存档旧结论（任何 DLL 都读不了）与本次逆向无关：
  本次全部基于英文 1108r9 自生成的存档。
- 过回合、载入存档仍需游戏进程在跑；本 MCP 提供 `witp_end_turn` 与截图 OCR，
  但“在主菜单里选槽载入”这一步尚未自动化（受 VNC 注入与菜单布局变化影响）。
