# WitP-AE 逆向：能力边界与字段标定实况

> 2026-10-18 更新。本文件记录**已证实**与**已证伪**的结论，不含推测。

---

## 〇、更正声明（2026-10-18 二轮）

**本文档 v1 里的"两条硬边界"结论作废。**

错误原因：在主菜单按 `t` 无反应（主菜单是旋钮式，本就不响应 `t`），
被错误归因为"引擎不响应注入"。实际 `witp_end_turn` 用 `xdotool key e` +
VNC 点 YES，在游戏内过回合**一直有效**（本轮再次实测成功，05/04→05/05）。

正确做法见文末「七、更正后的结论」。

---

## 一、~~两条硬边界~~（已作废，仅留档）

### ~~边界 1：引擎不接受任何程序化按键注入~~

对主窗口（`CSPClass` / hwnd 131204）做的全部尝试：

| 手段 | 结果 | 证据 |
|---|---|---|
| `PostMessage(WM_KEYDOWN/UP)` | 返回 1，界面不动 | winmsg3.py 实测 |
| `PostMessage(WM_CHAR)` | 返回 1，界面不动 | 同上 |
| `PostMessage(WM_SYSKEYDOWN)` | 返回 1，界面不动 | 同上 |
| `SendMessage` | 返回 0 | 同上 |
| `SetForegroundWindow` + `AttachThreadInput` + `SetFocus` | 焦点确认为该窗口，仍不动 | winmsg4.py：`active=131204 focus=131204` |
| `xdotool key`（XTEST 真实 X 事件） | 界面不动 | 主实例实测 |

**结论**：`过回合`（按 E）这一步，目前只能由人手动完成。

> 排除的假设：不是焦点问题、不是消息路由问题、不是窗口句柄找错（进程内只有 1 个可见窗口）。
> 引擎只导入 `GetMessageA/PeekMessageA/DispatchMessageA/TranslateMessage`，**没有任何键状态查询函数**，
> 却又不响应投递的键盘消息——具体原因未查明，但现象稳定可复现。

### 边界 2：没有 GUI 操作就产生不了「命令变更」的差分样本

字段标定的唯一可靠方法是「游戏自己改命令 → 存档差分 → 定位字段」。
既然无法驱动 GUI，就只能靠**过回合前后差分**，但它只能暴露引擎重算的派生量，暴露不了命令字段。

实测验证：`type=53`（2608000B = 4000×652，与 TF 槽位一一对应，曾以为是 TF 扩展命令块）
过一回合后**零字节变化** ⇒ 它是静态数据，不是命令块。

---

## 二、已确证的字段（可直接用）

### PWSTaskGroup 556B

```python
TF_OFF = dict(
    flagship=44,    # i32 旗舰舰船 id
    home=54,        # u16 母港 Location id
    destBase=58,    # u16 目的基地 id —— 仅界面缓存，改它无效
    wp=118,         # 40 × (u16 x,u16 y) 航路点数组
    wpCount=320,    # u16 路径有效点数 ★必须写
    wpAlloc=322,    # u16 路径缓冲长度 ★必须写
    mission=349,    # u8  任务码
    speed=354,      # u8  速度档
)
```

**目的地写法**：路径数组 + wpCount + wpAlloc 三者同步写，缺一必被引擎覆盖。
验收判据：**过回合后目的地仍在**。

### PWSAirGroup 680B

```python
AG_OFF = dict(
    baseID=40, primary=44, secondary=46, targetID=48,
    targetX=192, targetY=196, alt=212,
    pctCAP=560, pctLRCAP=561, pctASW=562,
    pctSearch=563, pctTrain=564, pctRest=565,
    aswArcStart=628, aswArcEnd=629,
    navArcStart=630, navArcEnd=631,
    withdraw=392,   # u32 撤编日期 YYMMDD（440710=1944-07-10）；引擎排定，只读
)
```

实测分布样例：`Genzan Ku K-1 prim=3 alt=15000 search=10`、`Chitose Ku S-1 prim=6 alt=10000 cap=30`。

### PWSLocation 1172B

```python
LOC_OFF = dict(
    X=36, Y=38,
    prep=104,          # u16 准备度 %
    combatMode=110,    # u8  0=defend 1=bombardment 2=deliberate 3=shock
    portExpand=424, airfieldExpand=428, fortExpand=432,  # u16 扩建指令
    marchDir=651, marchLen=652,
    objX=662, objY=664,   # ★未来目标 Future Objective，不是行军目的地
)
```

**语义修正**：`662/664` 是**未来目标**。证据：珊瑚海档里 10 个 LOC 的 obj=(56,62)/(78,77)
而 `marchLen=0`（未在行军）——远处基地坐标 + 无行军 ⇒ 只能是准备目标。

### 已证伪 / 不可写

| 字段 | 结论 | 证据 |
|---|---|---|
| `operationsMode`@906 | **全档 5947 条全为 0**，无法标定 | 多次统计 |
| `destBase`@58 单独改 | 界面完全不变 | 实测 wpae001 载入后仍显示旧港 |
| `type=53` 块 | 过回合零变化，非命令块 | 差分实测 |
| TF `off 388/389` | 所有存档恒定，是静态属性 | 4 个同日期档对比 |
| TF `off 551` | 所有存档恒定 {0:15,1:1,2:1,3:9}，非命令 | 同上 |
| TF `off 318/326/328` | 每回合被重算（0 → 1..5），是派生量 | 过回合差分 |
| LOC `off 590/591` | 所有基地统一变化，全局派生量 | 过回合差分 |

---

## 三、MCP 工具（12 个，零 GUI 依赖）

已移除 `witp_screen` / `witp_game_key`（截图 OCR、按键注入）。

### 读（7）
`witp_status` `witp_taskforces` `witp_airgroups` `witp_bases`
`witp_ground_units` `witp_saves` `witp_reports`

### 写（4，均带 `engine_verify`）
| 工具 | 能力 |
|---|---|
| `witp_set_tf_orders` | 任务 / 目的地 / **显式航路点** `"x1,y1;x2,y2;..."` |
| `witp_set_airgroup_orders` | 主任务 / 目标 / 6 种比例 / 高度 / 搜索扇面 |
| `witp_set_ground_orders` | 战斗命令 / **未来目标** / 准备度 / 行军方向与距离 |
| `witp_set_base_build` | 港口 / 机场 / 要塞扩建 |

### 结算（1）
`witp_end_turn` —— **当前依赖人工按 E**（见边界 1）。

---

## 四、手册覆盖实况

38 条命令面中：**已实现 12 / 部分 2 / 未实现 24（37%）**

已实现的可写命令：TF 任务、TF 目的地+航路点、AG 主任务/目标/6 比例/高度/扇面、
地面战斗命令/未来目标/准备度/行军方向距离、基地三项扩建。

未实现且**已确认无法用差分标定**的：TF 路由安全等级、巡逻区、Max React、Patrol/Retreat、
TF 速度档、装载卸载、Follow/Meet、组建解散、AG 转移/升级/Resize、地面 Operations Mode、
基地修理优先级、政治点、工业生产。

---

## 五、要把覆盖率提上去，只有三条路

1. **反汇编引擎**（ghidra/IDA）：找到 WndProc 里处理 `WM_KEYDOWN` 的分支，或找到读命令的函数，
   直接定位字段偏移。成本高（4.8MB PE，无符号），但不依赖 GUI。
2. **内存读写**：运行时附加进程，改内存里的命令结构体。需要先知道结构体布局——鸡生蛋问题。
3. **接受人工介入**：过回合与 GUI 专属命令由人操作，MCP 负责批量读态势、批量写存档命令。
   这是当前已交付的形态。

---

## 六、工具链

```
/root/.hermes/profiles/witp/workspace/witp-reader/
  pwsfile.py      容器解析
  pwspack.py      打包 + 精确长度压缩
  witp_core.py    纯 Python 读层（按解压长度索引，不按 type）
  witp_orders.py  命令写层
  dllverify.py    引擎回读校验
  field_probe.py  字段统计扫描
  turn_diff.py    过回合差分（按名字对齐，规避槽位互换噪声）
  winmsg*.py      Win32 消息投递实验（已证伪，留档）
```

---

## 七、更正后的结论（2026-10-18 二轮实测）

### 1. 按键注入有效，过回合可自动化

```
过回合 = xdotool key e → 等 4s → VNC 点 (508,422) 确认 YES → 等 autosave 更新
```

实测：本轮再次跑通，`wpae000.pws` 在 180 秒内生成，日期 05/04→05/05。
注意 Wine 不认 XTEST 点击，**点击必须走 VNC 注入**，键盘用 xdotool 即可。

### 2. 字段标定不要盲猜，先查社区结构体定义

`/root/.hermes/profiles/witp/workspace/witp-reader/pywitpaescraper/pwsdll.py` 已有完整 ctypes 结构体。
先读字段名，再去存档验证，比统计扫描快两个数量级。

### 3. 本轮新增的字段（全部过回合验证保留）

| 字段 | 偏移 | 语义 | 验证 |
|---|---|---|---|
| `locNear` | LOC 102 | 准备目标基地 Location ID | prep 40→**41** 真增长 |
| `destX/destY` | LOC 662/664 | 行军目的地（六角坐标） | 结算后清零（部队未动，符合预期） |
| `reinforceBaseID` | AG 42 | 航空队转场目标 | 结算后保留 471 |
| `shipRepairPriority` | SHIP 338 | 修理优先级 | 结算后保留 4 |
| `shipRepairMode` | SHIP 339 | 修理模式 | 结算后保留 2 |
| `shipUpgrade` | SHIP 365 | 升级开关 | 结算后保留 1 |

### 4. 覆盖率 37% → 45%

38→42 条命令面中，已实现 12→19 项。

### 5. 仍未解决

- `operationsMode`@906 全档为 0，无法标定（地面 Operations Mode 6 种状态）
- TF 巡逻区 / 路由安全等级 / Max React / Patrol-Retreat：`PWSTaskGroup` 的 `skip4`(56..347) 区
  实测除航路点与 destBase 外几乎全零，这些字段可能不在该结构体内
- `combatMode` 过回合后回到 0：手册 8.2.1.2 规定无敌军时不能保持攻击令，属规则非缺陷
