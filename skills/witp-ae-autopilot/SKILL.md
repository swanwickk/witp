---
name: witp-ae-autopilot
description: "WitP-AE 参谋指挥与前线操作联动SOP：指挥参谋部（体检/修复/取方案）+ 亲手落子 + 回写因果与知识库。"
version: 3.4.0
platforms: [linux]
metadata:
  hermes:
    tags: [witp, wargaming, staff-commander, ai-agent, field-tools, skb]
    category: wargaming
---

# WitP-AE「参谋—执行」人机协同推演 SOP

- **你的定位**：**前线指挥官兼操作手（手）**。面对人类司令，亲手调度 VNC 鼠标键盘与游戏窗口。
- **参谋部定位**：**你自己的下属参谋单位（脑）**。`witp-cmd staff` / 战略推演看板（18091）/ `witp_staff.py`。

> **核心权属**：参谋部是**下属**，不是外部顾问。它出问题时的正确动作是**命令重做 + 诊断 + 修复**，
> **绝不是绕过它自己单干**。绕过参谋部的决策必须让指挥官看得见。

---

## 一、每回合强制流程（缺一步即失职）

```bash
witp-cmd staff --check      # ① 体检：服务/API/快照新鲜度/与存档一致性（对局待机为提示，非故障）
witp-cmd staff --fix        # ② 不健康时修复：拉服务 + 强制重读存档 + 复验
witp-cmd staff --saves      # ③ 枚举可用存档，确定要读哪一份
witp-cmd staff --save 000   # ③b 指定读 Autosave（当前局面）并取《作战方案建议书》
witp-cmd staff --resync     # ④ 若方案基于过期数据（剧本/日期与实际不符）→ 纠偏后重取
witp-cmd set-dest TF14 103 137   # ⑤ 亲手落子：解析解 + 邻域实测闭环（回读仅作参考）
witp-cmd set-cap VF-2 100        #    设置防空：自动区分舰载(N)/陆基(A)中队，详情页步进加档
witp-cmd end-turn           #    推进过回合（含终局画面保护，杜绝误点黑屏）
witp-cmd record-turn --decision "<决策与理由>" --result "<实际战果>" --orders "<动作1;动作2>"   # ⑥ 回写
```

**新开局/重新启动（★含「第 1 回合就让参谋部到位」的标准流程★）**：

> ★★**先决条件：游戏必须跑在独立 systemd 服务里**★★
> ```bash
> systemctl start witp-game-en      # 独立 cgroup；详见 witp-ae-interface《启动隔离》
> ```
> **不要**从 agent/CLI 的 shell 直接启动游戏 —— 那样游戏会寄生在 `hermes-web-ui.service`
> 的 cgroup 里，该服务重启时 systemd 会 **SIGKILL 整个 cgroup 把游戏一起杀掉**，
> 表现为「跑 1.5~3.5 小时必崩」。
> 每回合开始前建议先跑 `witp_preflight.assert_alive()` 确认实例健康
> （**任何「输入无反应」先查这个，别急着下"机制无效"的结论**）。

```bash
witp-cmd launch                  # 清空并备份旧存档 + 启动剧本 003 → 进入第 1 回合地图
witp-cmd save-game --slot 3      # ★开局立即存档到 003（F 键对话框；必须点【小箭头】）
witp-cmd staff --save 003        # ★让参谋部读取第 1 回合存档 → 第 1 回合即由参谋部驱动
```

> **为何必须这步**：引擎只在**回合结算时**写 `wpae000.pws`/`wpae002.pws`。
> 开局不手动存档，第 1 回合就没有任何 `.pws` 可读，参谋部只能缺位（旧局的抱怨即源于此）。
> `save-game` 的关键是**点小箭头**（栏位箭头 x=65，行 y=123+16×N；SAVE 箭头 (62,546)），
> 点行文字无效——详见 `witp-ae-interface`。

**每局结束（到剧本终局）追加**：
```bash
witp-cmd close-game --outcome "<胜负>" --enemy-score N --own-score N --notes "<要点>"
witp-cmd skb --add "<提炼的教条>" --confidence 0.8 --evidence "<本局实证>"   # 复盘落地
witp-cmd skb                # 查看知识库状态与提交历史（必须递增）
```

---

## 一之二、主动指挥参谋部读取「指定存档」

**参谋部读哪份存档由指挥官决定，不由参谋部自行猜测。**

| 存档 | 语义 |
|---|---|
| `wpae000.pws` | Autosave —— 结算后**新状态**（当前局面） |
| `wpae002.pws` | PreTurnSave —— 结算前**旧状态**（上一回合） |
| `wpae003.pws` | 手动存档槽 |

```bash
witp-cmd staff --saves                          # 枚举（槽位/时间/日期）
witp-cmd staff --save 000                       # 指定读当前局面
witp-cmd staff --save 002                       # 指定读上一回合（对比用）
witp-cmd staff --save /abs/path/wpae003.pws     # 绝对路径亦可
```

- 不带 `--save` 时按 mtime 自动取最新，**仅作兜底**。
- 指定不存在的存档会**明确报错**，不会静默回退；报错后先 `--saves` 核对槽位。
- 提案书首部打印**数据来源存档**，用于核对参谋部实际读了哪一份。
- 底层通道：`POST /refresh-state {"save":"000"}`；枚举 `GET /saves`；`witp_staff.py brief --save/--saves`。

---

## 一之三、指挥官战役指导与航母机动核算

**参谋部支持根据指挥官意图进行自适应机动核算**：

1. **核心战略目标**：由指挥官根据战局自主指定战略重点（如要塞防守、两栖夺取、航运走廊维系等）。
2. **主力舰队机动安全核算**：
   - 参谋部每回合按当回合读层推导出的敌情与基地信息，动态计算航母前推打击位；
   - 自动避开最近敌方陆基机场的轰炸作战半径；
   - 自动推导并预置最近的己方补给与后方退路锚点。
3. **敌航母突击出击评估**：
   - 当侦察到敌主力航母时，参谋部计算舰载机打击半径（通常为 4~5 格）内的机动打击位，评估出击风险与收益，供指挥官决策。

```bash
witp-cmd staff --save 000 --json     # 读 carrier_station / carrier_advisories
```

| 字段 | 含义 |
|---|---|
| `carrier_station.mode` | 战区前推打击位 / 机会打击位 / 常规待机 |
| `carrier_station.hex` | 前推位（距目标锚点 = 舰载机出击半径内，便于次日实施打击） |
| `carrier_station.distance_to_enemy_air_hex` | 岸基威胁判据（距敌方陆基机场距离）——锚点由当回合读层动态推导 |
| `carrier_station.enemy_air_anchor` / `friendly_support_anchor` | 威胁 / 退路锚点数据及推导来源 |
| `carrier_advisories` | 编队机动与风险警示提示 |


---

## 一之四、侦察纪律（指挥官指正：「从未发现敌航母」= 侦察策略有缺陷）

**原则：侦察不能靠运气；搜索必须专职化并设扇面；发现敌情就寻机打击，不许一味退让。**

### 敌人头顶线索：舰载机出现 = 敌航母就在附近

> 指挥官原话：「当己方头顶出现日军舰载机时，说明日军航母就在附近了，此时应当加强机动和空中侦察，
> 根据战局寻找打击机会，而不是一味退让。」

**识别纪律（容易误判，必须守）**：
- ✅ 唯一可靠证据 = **D3A（九九舰爆）/ B5N（九七舰攻）** 等舰载攻击机出现；
- ❌ **A6M2 零战陆基/舰载通用，单独出现不作数**；
- ❌ **G3M/G4M（Nell/Betty）是陆基，必须排除**。

```bash
witp-cmd staff --save 000 --json   # 读 recon_contacts / carrier_proximity / search_plan
```

| 字段 | 含义 |
|---|---|
| `recon_contacts.detected` | 战报窗口（当前回合+前 5 游戏日）内是否出现日军舰载攻击机 |
| `carrier_proximity.verdict` | 接触点升级为「敌航母邻近」判定（推定半径 6 格） |
| `search_plan.assignments[]` | 逐中队搜索方案：角色 / 对海% / ASW% / 扇面起止角 |
| `search_plan.theater_axis` | 战区主威胁轴（自 PM 看最近的敌方**机场**基地；排除 PM 本身） |

### 搜索专职化配比（已入库，禁止再摊薄）

| 机种 | 角色 | 对海 | ASW |
|---|---|---|---|
| PBY / 巡逻机（VP） | 远程搜索核心 | **100%** | 0% |
| 舰载侦察机（VS / SBD） | 舰载专职侦察 | **100%** | 0% |
| 巡洋舰水上飞机（VCS / FP） | 近距/反潜 | 50% | 50% |

- **扇面必须设**：按敌情罗盘方位角 ±45°，禁止无扇面全向摊薄（全向 = 效率减半）。
- 主轴优先级：**舰载机接触点 > 日军目击报告 > 最近的敌方机场基地**。
- 敌航母接触点会同时并入 `carrier_opportunity` 情报源——即「被打」本身就是打击线索。

### 搜索指令通道（已打通：`witp-cmd set-search`）

```bash
witp-cmd set-search "No.11" 100              # 对海搜索 → 100%
witp-cmd set-search "VP-33" 50 --asw         # 反潜搜索 → 50%
witp-cmd set-search "VS-2" 100 --row 385     # 名字 OCR 匹配失败时用 --row 旁路
```

**执行要点（已踩过的坑）**：
- 面板行**运行时 OCR 动态定位**，不可硬编码（行名与整块 y 随内容位移）。
- 清单行 y 有 ±6px 抖动，工具已内置邻近重试；仍失败时先 `A`/`N` 列表 OCR 自行量出行 y 再用 `--row`。
- **读回 OCR 可能读不出但点击已生效**——**权威校验只能靠读层**：过回合后查
  `witp-reader/state/airgroups.json` 的 `percent_search` / `percent_asw`。

---

## 一之五、方法论总则（一般性经验 + 随机应变，严禁剧本推定）

> 指挥官原话：「WitP 是一款模拟性较强的二战海空兵棋游戏，很多指挥策略可以根据二战的实战经验进行敲定，
> 但剧本每回合存在随机性，所以不能想当然认为对手就会按历史策略行动和历史位置部署，
> 而是要从一般性经验出发，根据战局随机应变。」

**两条并用**：①**一般性经验**（侦察优先、兵力集中、任务式指挥、保全兵力、压制机场与后勤、夜战避险、潜艇破交）；
②**随机应变**（计划按当回合实际态势重算，不沿用上一局或历史套路）。

**三条禁令**：
- **严禁剧本推定**——不得假设敌某日必现于某地；
- **严禁预设敌方兵力构成**——不写「翔鹤瑞鹤必在」，以当回合侦察为准；
- **禁止编造**——情报不足写「未知」，回退兜底时必须标注来源。

**工程落地**：

| 项 | 做法 |
|---|---|
| 敌岸基威胁锚点 | `lib/theater.py::nearest_enemy_air_anchor(bases, from_hex, exclude_hex=…)`——最近的敌方**机场**基地；`exclude_hex` 排除打击目标本身，避免逻辑循环 |
| 我方退路锚点 | `nearest_friendly_support_anchor(bases, from_hex, min_port=2)`——前沿小港（port 1）不可作退路 |
| 航母识别 | `theater.is_carrier_ship` / `tf_has_carrier`——按 `ship_type` 前缀 `CV`，**不硬编码舰名** |
| 报告透明度 | 输出 `anchor_derivation` / `enemy_air_anchor` / `friendly_support_anchor`，读层无数据时显式标注回退 |

**已清除的剧本推定硬编码**（改前 → 改后）：`RABAUL_HEX(106,125)` → 读层推导 Lae(99,126)；
`TOWNSVILLE_HEX(92,144)` → 读层推导 Cairns(92,140)；硬编码美舰名 → `ship_type` 通用判定；
「双鹤为已知存在」断言 → 删除。

---

## 二、参谋部故障处置手册（禁止跳过、禁止默默绕过）

### 症状 → 处置对照表

| 症状 | 诊断 | 处置 |
|---|---|---|
| 建议书剧本/日期与游戏不符 | `staff --check` 看"快照 vs 实际存档" | `staff --resync` 强制重读 |
| 云端模型超时/返回不可解析 | 看 `staff` 输出首行的异常提示 | `staff --fix`（含 API 可达性检查） |
| 看板接口不可达 / 服务挂了 | `staff --check` 看服务项 | `staff --fix` 自动重启三服务 |
| 快照滞后存档 >180s | `staff --check` 看"快照滞后" | `staff --resync` |
| 刷新报「已有刷新任务在执行」 | 查 `/tmp/witp_refresh.lock` 是否存在且陈旧 | `staff --fix`（清锁）；后端已加 600s 残留锁自愈 |
| 参谋部给出不存在的部队编号 | 比对 `taskforces.json` 的 `record_id` | 已修正：编号取 `record_id`（即游戏内 TF 号），旗舰名作显示 |
| 体检退出码非 0 | —— | 先 `staff --fix`，仍失败则向指挥官报告故障 |

### 铁律
1. **先诊断再修复再复验**：`--check` → `--fix` → `--check`，确认转健康。
2. **修复失败且已向指挥官报告故障后**，才允许临时自主决策，且报告须写明「参谋部故障，本次为降级自主决策」。
3. **严禁静默单干**。

---

## 三、看板数据管道（拉取式，不是推送式）

看板读的是读层快照 `witp-reader/state/turn.json`，**游戏推进不会自动更新快照**。

| 组件 | 作用 |
|---|---|
| `witp-watcher.service` | 监视存档 mtime 变动，自动重跑读层 |
| `witp-dashboard.service` | 看板 API 与页面（18091） |
| `state_lastgood/` | 良好快照备份（空窗期/失败兜底） |

**★ 两个必须知道的陷阱 ★**

1. **读层会清空 state/**：`witp_read.sh` 开头 `rm -rf state/` 再重建，存在空窗期。
   此刻读 `turn.json` 会拿到空值，看板显示「未知剧本」。故：备份到 `state_lastgood/` + 两级兜底读取。

2. **存档必须取"最新状态"那份**：引擎结算后依次写
   `wpae002.pws`（PreTurnSave = **结算前旧状态**）与 `wpae000.pws`（Autosave = **结算后新状态**）。
   读层原先硬编码读 `wpae002` → **态势永远落后一回合**（曾导致参谋部给出的剧本/日期与实际不符）。
   已修正为按 mtime 取最新 `.pws`。若发现"快照比存档旧一天"，先查这一点。

**存档字段要点**（避免编造标识）：
- 编队：**没有 `id`/`name` 字段**，标识用 `record_id`（= 游戏内 TF 编号，如 14→TF14），显示名用 `flagship_name`。
- 航空队：标识用 `record_id`，名称为 `name`（可能为空，空的不可执行，应跳过）。

**排障命令**：
```bash
systemctl status witp-watcher.service witp-dashboard.service
tail -20 /root/.hermes/profiles/witp/witp-agent/logs/watcher.log
stat -c '%y' /root/.hermes/profiles/witp/workspace/witp-reader/state/turn.json
curl -s localhost:18091/api/plugins/witp-dashboard/status   # 看 freshness.staleness_s
```

---

## 四、回写产物与自检标准

| 命令 | 产出 | 位置 |
|---|---|---|
| `record-turn` | 因果三元组 `(S,D,R)` | `games/<game>/causal_log/turn_NN.json` |
| `close-game` | 对局战果摘要 + 全局台账 | `games/<game>/summary.json`、`games/results.json` |
| `skb --add` | 教条追加 + 自动 git 提交 | `skb/doctrines.md` |

**自检**：一局打完，若 `witp-cmd skb` 的**提交次数没有增加**，则本局「自我迭代」视为**未发生**。

---

## 五、前线工具底层实现规范与避坑铁律

### 1. `set-dest`：**小地图跳转 + 点中心法**（v23，2026-10-10 地面真值标定）

> ★★**2026-10-15 重大缺陷与修复（务必先读）**★★
> `set-dest` 对**小地图红框外**的目标（如珊瑚海剧本的 PM(98,130)）**不可用**：
> - 小地图可点区＝红框 x∈[939,964] y∈[715,744]，只覆盖 hex 约 x∈[100,111]、y∈[116,152]；
> - PM 在红框**左侧之外** ⇒ `jump_minimap` 被 **clamp 到 (105,125)**，每轮都差 7 格；
> - 而每轮的 `_enter_pick_mode` 内含 3~6 次 `open_tf_panel`（每次几十次点击+OCR）
>   ⇒ 累计数百次 GUI 操作 ⇒ **整个调用挂死数分钟、stdout 为空**，进而整局卡住。
> **已修**：`set_tf_dest(..., deadline=140)` 加总时限，超时即返回当前最佳结果并告警，
> 绝不无限重试（`witp-cmd set-dest ... --deadline 100` 可覆盖）。
> **对策**：目标在红框外时**不要用 set-dest**。可用替代：
> ① `witp_setdest_auto.py`（读视野中心→点像素→回读 自校正闭环）；
> ② 战略图（Ctrl+A）点目标位置 `witp_stratjump.py`；
> ③ **最优：不动它** —— 见 1b。

```bash
witp-cmd set-dest TF6 98 130 --deadline 100   # 目标在小地图红框外时务必加时限
```

### 1b. ★不要干预剧本已设好的编队指令★（2026-10-15 重大教训）

珊瑚海剧本开局**已把** TF6(BOMBARDMENT)→PM(98,130)、TF7(AMPHIB)→PM 设好。
我曾在整局脚本里「每回合纠正 TF6 目标」，结果用有偏差的 set-dest 把正确目标**改坏**
（改成 100,129 / 106,125），那些局**全回合 0 次炮击 PM**（日方得分仅 342~364）。
撤掉干预后（game-069）恢复正常炮击、得分 1232。

⇒ **原则：先读层核对现状，已正确就不要动；只有明显偏离时才修。**
```bash
witp-cmd staff --save 000 --json   # 看 taskforces.json 的 mission / target_x / target_y
```

### 1c. ★`lib/tfpanel.open_tf_panel` 曾因「编号 OCR 读不出」永久跳过 TF6★

实测扫描日志：`y=306→TF5, y=320→TFNone, y=334→TF7` —— 中间那行正是 **TF6**，
但编号小字 OCR **恒读不出**，旧逻辑「None 一律视为不匹配」⇒ TF6 永远打不开。
**已修**：读不出编号时**按行序推断**（`ROW_Y0=250, ROW_DY=14`，T 列表恒按编号升序），
推断值 == 目标即采用。这是「TF6 长期定位失败」的最后一块拼图。

### 1d. 判「基地是否已被攻占」**必须用 `area_command`**

`bases.json` 的 `relations.stationed_ground.names` 是**假阳性**（表示「关联的本方部队」，
敌方基地只要我方部队在该格也会列出 → 曾据此误判 PM 已占领、白扔一回合）。
`nation` 也**不可靠**（易主后仍写原属国）。**唯一权威 = `area_command`**
（盟军 Southwest Pacific / 日军 Southeast Fleet）。

### 1e. ★终局屏会造成「假死」——已自动处理★

结算后若停在 `VICTORY LEVEL / FINAL SCORE` 模态屏：**只认鼠标点按钮**，
Return/Space/Tab/Esc 全无响应，主线程在 EXE 0x3cd8xx 定点自旋、画面冻结、autosave 停写。
`end_turn` 现已自动：OCR 记分 → 写 `game_ended.json` / `endgame_scores.json` → 重建显示栈回主菜单。
**判「卡死」不能用「截图两帧相同」**（地图静置本就不重绘）——先点工具条按钮看画面是否变。

### 2. `set-cap`：舰载 (N) / 陆基 (A) 双列表分流
- **模型**：进入选格模式（点 `Set TF Destination` 箭头 → 面板关闭）后，
  点击像素 (x,y) 设定的目的地 = `视野中心 C + ((x−512)/37.0, (y−384)/37.0)`。
  **C = 视野中心格**，由「点屏幕正中 (512,384) → 面板回读 `Hex:`」**直接测得**（屏幕正中恒为视野中心）。
- **流程**：① `jump_minimap(J)` 小地图绝对粗定位 → ② 进选格模式点屏幕正中读 D=C →
  ③ `|D−T|≤2` 即命中，否则 `J += (T−D)` 再跳，2~3 轮收敛。
- ⛔ **旧「黄框法」失败根因**：黄框映射有约 **(+3.24,+3.06) 格**系统偏差，
  落点整体偏约 **9 格** ⇒ 报成功但设错格。黄框**只可用于相对粗调**，不可用于绝对定位。
- **★C 随所选 TF 变化★**：打开某 TF 面板时游戏会把视野重定心到该 TF，故每轮必须重读 C，**禁止跨 TF 复用**。
- **核验时序铁律**：UI 只改内存不写档 ⇒ 「下完令立刻读层」必读到**上次存档旧值**。
  正确顺序 = **下完令 → `save-game` → 核对实际 .pws 文件名 → `staff --save <该档>` → 读 `taskforces.json`**。
- **★`save-game --slot N` 有槽位映射 bug★**：实测 `--slot 3` 有时写到 `wpae087.pws`，
  必须 `ls` 核对实际文件名，不要假定 `--slot 3 == wpae003`。
- ⛔ 旧文写的 `CX = 500 + (TX−PHX) × 42.86`、`CY = … × 37.5` **已作废**（比例是 37.0）。
- **列表防误击**：T 列表常驻显示潜艇行，定位不到目标 TF 时先滚顶重扫，仍失败必须**明确中止**，严禁静默双击第一行！

### 2. `set-cap`：舰载 (N) / 陆基 (A) 双列表分流
- **中队归属**：航母战斗机（VF-2、VF-5 等）必须按 `n` 打开舰载机列表；陆基中队（49th FG 等）按 `a` 打开陆基列表。
- **步进调档**：详情页点击 `(766, 302)` 步进加档（每档 20%），禁止盲点。

### 3. `launch`：启动前清空 SAVE 目录旧档
- **闪退根因**：SAVE 目录下若残留上局 `.pws` 存档，在主菜单点击 `SCENARIO SELECTION` 游戏会崩溃退出 (SIGKILL)。
- **规则**：启动前必须自动将旧 `.pws` 移入备份目录。START GAME 点击坐标精确中心为 `(695, 525)`。

### 4. 读层与核验底层映射 (Grounding Verification)
- **任务部队**：标识为 `record_id`（对应游戏内 TF 编号，如 14），目标格为 `target_x`/`target_y`。
- **航空中队**：标识为 `record_id` 与 `name`，CAP 比例字段为 `percent_cap`，任务码为 `primary_mission_code`（6=CAP, 3=Naval Attack, 8=Naval Search）。
- **情报解析**：`threats.json` 的有效载荷为 `position: {x,y}` 与 `sample_texts`，参谋部通过此结构提取敌舰坐标与地名标签（如 `[Koumac]`、`[Port Moresby]`）。

---

## 六、前线指令速查

| 命令 | 功能 |
|---|---|
| `witp-cmd staff` | 取《作战方案建议书》（默认读最新存档并引用 SKB 教条/模式） |
| `witp-cmd staff --model <M>` | 司令单次指令临时指定参谋主模型（如 `step-5-preview`） |
| `witp-cmd staff --fallbacks <F1,F2>` | 司令单次指令临时指定备用模型链（逗号分隔） |
| `witp-cmd model` / `model list` | 查看模型池、当前主模型与备用链（加 `--test` 测延迟） |
| `witp-cmd model test` | 一键测试当前主模型与各 Fallbacks 的实际连通性与耗时 |
| `witp-cmd model set --primary <M>` | 持久化指定主模型与备用链（写入 `config.yaml`） |
| `witp-cmd staff --saves` | 枚举存档（槽位/时间/日期） |
| `witp-cmd staff --save 000` | 指定读 Autosave（当前局面） |
| `witp-cmd staff --check/--fix/--resync` | 参谋部体检 / 修复 / 强制重读存档 |
| `witp-cmd set-dest <TF> <X> <Y>` | 设编队航向（解析解 + 邻域实测；**回读仅参考，真值看结算后读层**） |
| `witp-cmd set-cap <AG> <PCT> [--alt FT]` | 设中队 CAP 比例（自动分流 N/A 列表）+ 分层高度 |
| `witp-cmd set-search <AG> <PCT> [--asw] [--row Y]` | 设对海/反潜搜索比例（侦察纪律，面板行运行时动态定位） |
| `witp-cmd end-turn` | E+YES 过回合并等待结算（含终局画面自动截屏保护） |
| `witp-cmd record-turn / close-game / skb` | 回写因果 / 归档战果 / 知识库维护与 Git 提交 |
| `witp-cmd save-game --slot N` | 存到槽位 N（F 键对话框：先点栏位小箭头变绿，再点 SAVE 小箭头） |
| `witp-cmd status` | 查看屏幕画面与窗口偏移状态 |
