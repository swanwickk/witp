---
name: witp-ae-autoplay
description: "Use when auto-playing WitP-AE Coral Sea on English 1108r9."
---

# WitP-AE 自动推演闭环（英文 1108r9）

> ⚠️ **权威指针（读本节优先于下文全部坐标）**
> 本技能的**机制与坐标**属「历史实测记录」，可能随版本/窗口状态失效。
> 涉及操作机制一律以这三个技能为准，本条仅为场景化补充：
> - **界面/通道/崩溃** → `witp-ae-interface`（含 cgroup 隔离、黄框导航、T 列表标定）
> - **战术与教条** → `witp-ae-doctrine`
> - **每回合参谋—执行 SOP** → `witp-ae-autopilot`

**对局状态：**
- 珊瑚海 003 盟军方已打完三轮：`game-025`（盟军决定性胜利）、`game-028/030/031`（日军边际胜利）。**每局都跑到 05/15/42 第 12 回合终局。**
- `game-031`（2026-10-09 完成）：日军 1720 : 盟军 1209，莫港第 7 回合失守；我方击沉日运输船 14 艘；航母全程无伤。归档见 `witp-agent/games/game-031/summary.json`。
- **新开局时先确认用户选的剧本。**

## 环境
- 游戏：/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition（exe=War in the Pacific Admiral Edition.exe）
- 启动器：/root/.hermes/profiles/witp/workspace/witp-launch-en1108.sh（DISPLAY=:98，必须先确认 openbox 在跑，否则窗口黑/不可见）
- SAVE：该目录下 SAVE/wpae000(自动)/002(上回合)/003(手动).pws
- 读层：/root/.hermes/profiles/witp/workspace/witp-reader/witp_read.sh —— **必须改用英文 DLL 目录与英文 SAVE 路径**（DLL dir = Z:\root\.wine-witp\drive_c\1108r9\...；旧脚本硬编码中文版路径）
- 读层输出：state/ 下 JSON + witp_summarize.py 出中文简报（盟军双盲视角）
- 存档路径含中文会 UnicodeEncodeError，测试样本必须放纯 ASCII 路径

## 闭环流程（每回合）
1. 读当前存档（wpae002 或最新）出中文态势简报
2. 依简报下盟军命令（界面操作：编队任务/航空任务/巡逻扇面）
3. 过回合：战斗动画已关；E 键确认→Y；战斗摘要退出点=完成左侧小箭头(x≈737,y≈257)
4. 引擎写新 wpae002 → 回到第 1 步
5. 剧本 1942-05-01~05-15，推完出终局中文报告（战果/损失/胜负）

## 航空队界面（实测通过的完整操作，2026-09-24 新局重新实测修正）

- **打开**：`python3 witp_vnckey.py escape` → `witp_c 500 500 click`（给键盘焦点）→ `python3 witp_vnckey.py a` → 等 5s。
- **列表行 y（实测，行距=14）**：22ndBG=265 / 3rdBG8th=279 / 3rdBG5th=293 / 3rdBG90th=307 / 49thFG9th=321 / 49thFG7th=335 / No.11=349 / No.23=363 / VP-11=377 / VP-33=391。**开详情 = `witp_c2 215 <行y> click`（点单位名列）**。
- **★坐标随中队变化（关键）★ 任务列表「Group Mission」位于 x≈645-770，但 y 坐标按中队类型不同，必须逐个读，严禁跨中队复用**：
  - 轰炸机/A-20（22nd BG、3rd BG…）：Airfield147 / Port159 / NavalAttack171 / Ground183 / **NavalSearch=207** / ASW219 / Supply231 / City243 / Training256 / StandDown267
  - 水上飞机（No.11 Catalina）：Airfield147 / Port159 / NavalAttack171 / Recon184 / **NavalSearch=195** / Supply219 / TroopTransport231 / …（**无 ASW 项**）
  - 后果：用轰炸机的 y=207 去点 Catalina → 落到 Supply/ASW，实测把 No.11 误设成 `ASW 70`，回读才抓出。
- **必须点文字左侧的图标列 x≈660**（文字从 x≈677 起，点文字无效）。
- **回读核验方法（权威）**：ESC 回列表 → 裁 `im.crop((540, 行y-10, 830, 行y+10))` 放大 5 倍 → tesseract psm 7 → 读 Mission 列（显示 `Search NN` / `Escort NN` / `ASW NN`）。**只信回读，不信点击回执**。
- 扇面（巡逻弧）控制：**Set on map 图标 = (745,377)**（VB2 布局）→ 点后切到地图 → 点两个方位点定义起/止 → ESC 返回；成功标志：Start 由 000° 变为实测值 + 出现 Clockwise。
- Patrol levels 区域：ASW 50% / Search 0% / CAP / LRCAP / Train 各行可调百分比。
- 验证方式（权威）：ESC 回列表 → `xdotool key n` → 读 Mission 列（VB2 由 Naval → Search 即成功）。

## ★N 列表（舰载航空队，N 键）与 Patrol levels 实测（2026-09-24 第八局固化，第九局修正）★

### ★★ 行坐标的真相：固定步长扫描必然错位（第九局根因修复）★★
- **N 列表首行中心在 y≈259，行距 14**（即 `245+14k`），数据行：1/VCS-6=259、2/VCS-5=273、2/VCS-6=287、3/VCS-4=301、3/VCS-6=315、4/VCS-5=329、S1/No.9=343、S5/No.9=357、VB-2=371、VB-5=385、**VF-2=399/405**、VF-5=413/419、VS-2=427、VS-5=441、VT-2=455、VT-5=469。
- **旧代码从 y=240 起按步长 14 逐行裁剪 → 每行都跨两行文字 → OCR 全乱码**，导致 `set-cap` 对舰载中队**从未成功过**。
- **正确做法：不要用固定步长**。对名称列 (x=150..440) 做**整块 TSV OCR，按 y 归并成行**再匹配名称 —— 与首行偏移/步长无关。已实现于 `_find_airgroup_row`。

### N 列表交互（与 A 列表不同，严禁套用 A 列表参数）
- **开详情 = 单击图标列 x=190**；`双击 x=215` 实测无响应（A 列表才是双击 x=215）。**旧 set-cap 对两者统一用双击 → 舰载中队全部打不开详情**。
- 行距 14；用法：`witp_c 190 <行y> click` → 等4s → 详情开（验 `Group Mission`）→ 调参 → `escape` 回列表。

### Patrol levels 调节区（详情对话框内固定块，与中队无关）
- **行位**：标题 y=288 / **CAP y=303** / LRCAP y=315 / Tran y=327 / Rest y=339（行距12）。
- **数值读数窗口（唯一可靠）**：`crop (704, 297, 745, 311)` → 放大 8x → tesseract psm7（其他窗口读不出数字）。
- **按钮语义（y 与该行数值同）**：
  - **x=651 → 直接减到 0**（实测 10→0）
  - **x=671 → 每次 −10**（实测 30→20→10）
  - **x=746 → 每次 +10**（实测 0→10）
  - **x=767 → 直接设 100**（实测 10→100）
- **设 CAP 100% 最短路径**：`witp_c 190 <VF行y> click` → 等4s → `witp_c 767 303 click` → 等3s → `escape` → 回读 Mission 列应显示 `Escort 100`（原 `Escort 30`）。
- **回读核验（权威）**：ESC 后裁 `im.crop((460, 行y-8, 760, 行y+8))` 放 5x → psm7 → 看 Patrol 列。
- **高度**：详情内 `current altitude: 10000`（F4F 默认即 10000ft，新打法目标值）；`Maximum Attuc feet] 37.500` 是机型极限非当前值。

### ★CAP 分层高度控制（2026-09-24 第九局实测标定，首次打通）★
详情面板内 `Current Altitude` 行 y≈372，**控件行 y≈387**。逐像素扫描实测的按钮语义：

| x 坐标 | 语义 |
|---|---|
| **647** | 直接设为最低 **100 ft** |
| **667** | 设为 **1000 ft** |
| **732** | **+1000 ft** |
| **752** | **+5000 ft** |
| **772** | 直接设为**最高**（机型上限，如 37000） |

- **读数窗口必须只裁数值本体** `(720,364)-(768,388)` 放 10x + 数字白名单。
  **整行宽裁剪会让 OCR 把 6 读成 S**（实测 `6000`→`S000`）。
- 设值算法：归最低 → 置 1000 → 用 +5000/+1000 步进逼近，**每步读回校验**（读失败不要盲加，否则超调）。
- 命令：`witp-cmd set-cap VF-2 100 --alt 15000` / `witp-cmd set-cap VF-5 100 --alt 6000`
- 实测结果：VF-2 = 100% + 15000 ft，VF-5 = 100% + 6000 ft（教条 #16 分层 CAP 首次可真正落地）。

### ★避免重复找坐标（强制）★
任何现场摸到的控件坐标，**当次操作结束前必须写回本 skill**；下次开工先读本 skill 再动手，不得重新试探。历史教训：第七局 N 列表坐标只存在于一次性脚本未固化 → 第八局从零摸索、反复试错。

## ★截图裁剪铁律★
`witp_shot_game` 裁剪时必须带 `+repage`，否则 ImageMagick 保留页面偏移，后续所有 `-crop` 报
"geometry does not contain image" 或坐标错位（曾导致大量误判）。

## 珊瑚海盟军战术要点（2026-09-23 实战两次对比得出）

两次推演对比（同剧本、同AI，唯—变量是命令）：

| 项目 | 纯自动（默认命令） | 主动指挥 |
|---|---|---|
| 日军得分 | 2520 | **2209（-311）** |
| 盟军得分 | 1139 | 1147 |
| 约克城号 | 沉没 | **幸存**（CAP 100% 之功） |

**有效命令（已验证）**：
1. **战斗机 CAP 拉满**——默认是 Escort 30%（只有 13 架升空），改为 **CAP 100%** 后航母生存率显著提高。
   - 操作：航空队界面 → Patrol levels 区 → CAP 行右侧按钮（x≈763，y≈302）连点 4 次（每次 +20%）。
2. **指定专职搜索中队**——SBD 中队 Patrol 值调到 100%（同一个按钮，y≈338）作为专用搜索，其余 SBD 保持 20% 作打击。
3. **两航母同格集中**（互为防空支援）。

**为何仍败（下次改进方向）**：
- 日军登陆船团直趋莫尔兹比港(98,130)，盟军航母在(106,142)相距约 14 格，**远超 SBD 打击半径(4-5格)**，无法阻止登陆；
- 日军航母始终未被持续跟踪，无法先手打击；
- 下次应提前 1-2 天把航母推至路易西亚德群岛附近（约 103,137），并强化 PBY/岸基搜索持续跟踪日航母。
- 日军情报损失（本次 9 艘）：CL Tenryu/Yubari、AV Kamikawa Maru/Kiyokawa Maru、CM Okinoshima、APD Yuzuki + 3 运输船。

## ★★战报文本：免 OCR 的情报金矿（2026-09-23 实测）★★

游戏每回合结算时在 `SAVE/` 下写出 GBK 文本，`iconv -f GBK -t UTF-8` 直读：
- **aoperationsreport.txt** —— 逐日行动报告：**全部日舰目击（坐标/航速/航向）、击沉确认
  （"xxx is reported to have been sunk near ... on ..."，且为累计清单，终局战果必须读最后一天那份）、
  飞行员伤亡、TF 拆分/改道事件**。
- **combatreport.txt** —— AFTER ACTION 详报：每次空战/海战/地面战完整序列（攻方兵力、命中数、
  CAP 参与、**地面战双方 Assault Value 与 odds**）。
- **asigint.txt / CombatEvents.txt** —— 侦听与结算流水；逐日归档为 `*_420507.txt` 日期后缀可回溯。
- **读档简报管我方状态，战报文本管敌情与战果，两者缺一不可。**

## ★★设置编队目的地（探针法，2026-09-23 三次实测成功）★★

**难点**：点 `Set TF Destination` 箭头 **(534,204)** 后进入全屏地图模式，**整个 UI 框架（含顶栏
Hex 读数）被隐藏**，无法悬停标定；且 **TF 面板打开会改变地图视野**，上次坐标不可复用。

1. `T` 开编队表 → 双击该 TF 行（实测行 y：TF3=246/TF6=260/TF14=274/TF16=288/TF17=302/TF18=316，以 OCR 为准）
2. 点箭头 `(534,204)` 进目的地模式
3. 需调整视野时：**先点地图给焦点，再逐键发送方向键、每键间隔 0.7s**（批量发送会丢键）
4. **点探针 (500,500)** → ESC → OCR 该行目的地得 hex(HX,HY)
5. 反算真目标：`cx=512+(TX-CX)*37.0`，`cy=384+(TY-CY)*37.0`
   ⚠️ **2026-10-09 订正**：旧的 `42.86/37.5` **已作废**（权威值 **37.0/37.0**）；
   且 `CX/CY` 不能靠探针回读求（回读不可靠），须用**小地图黄框**读视野中心。
   详见 `witp-ae-interface`《视野导航：小地图黄框法》。
6. **复现同一序列**（再开同一 TF → 箭头 → 同样按键）→ 点 (cx,cy) → ESC → OCR 列表核验
- 核验只认列表上的 `moveto X,Y` 或基地名（如 `Port Moresby, moveto`）。
- 实测：TF14→PM 探针(500,500)=(100,130)→真目标(414,500) ✓；TF18 探针(243,313)=(105,150)→(72,500) ✓。
- **编队 moveto 到达目的地后会回退为回母港**——要长期驻守某格须反复重设。

## ★★陆基航空队改任务（2026-09-23 五次实测全部成功）★★

1. `xdotool key a` 开陆基航空队列表
2. **双击单位名称列**（x≈230；行 y 用 TSV OCR 联合定位：name 列含 `3rd` 且 location 列含 `Townsville`）
3. 任务单选按钮 **x=653**，y=任务文本 y+5：Airfield Attack 144 / Port Attack 155 /
   **Naval Attack 167** / Ground Attack 179 / Recon 191 / **Naval Search 203** / ASW 215 /
   Supply 226 / City 239 / Training 251 / Stand Down 263
4. 点击 → ESC → 回列表读 **Mission 列**（x 656-670）核验
- OCR 须宽松匹配：`Naval Attack` 常被切成 `Naval`+`Attack` 两词，按 `^NavalAttack$` 会漏。
- 详情页 Patrol levels：+10 档 x≈744、大幅增加 x≈766、**左侧为减档箭头**；同区有 Set on map/Reset arc/Show arcs。
- **存档任务码实测映射**：1=Airfield、3=Naval Attack、6=Escort/CAP、8=Naval Search、9=ASW。

## ★★终局画面（2026-09-23）★★
- 剧本结束弹 DRAW/VICTORY/DEFEAT 框：`FINAL SCORE / JAPANESE: n / ALLIED: n`，
  **以 tesseract TSV 为准**（视觉模型会把 1089 误读成 1029）。
- 按钮 `View End Game Status`≈game(735,477)、`Quit Game`≈(735,499)：**OCR 读不到按钮文字**
  （绿字压红蓝旗徽），须视觉模型定位；该对话框上悬停扫描法无效（光标不渲染、diff 全 0）。

## 珊瑚海第三轮结果（四条战术铁律，2026-09-23）

| 轮次 | 指挥方式 | 结果 | 日军 | 盟军 |
|---|---|---|---|---|
| 1 | 纯自动 | 日军决定性胜利 | 2520 | 1139 |
| 2 | 主动指挥(CAP100%) | 日军决定性胜利 | 2209 | 1147 |
| **3** | **四条铁律** | **DRAW，盟军分反超** | **1089** | **1172** |

**胜负手不是我方得分（三轮接近），而是把日军从 2520 打到 1089**——莫尔兹比港自始至终未失、
登陆船团被歼（我方直接击沉 7 艘运输/扫雷舰）。关键三招：①全侦察链使日船团逐日被跟踪；
②TF14 夜袭 PM 迫其“中断卸载起锚撤退”；③岸炮持续压制使日登陆场 AV 由 96 崩到 34。
**代价**：双航母尽失（Lexington 5/9、Yorktown 5/10）——**CAP 100% 只能减损不能免打**，
必须在发现日航母当天先手出击；且**莫尔兹比港是日军空袭磁石，破登陆后应及时把舰撤出该格**。

## ★★第四局复盘（2026-09-23，日军决定性胜利 2086:1119，PM 5/10 失守）★★

四局对比：纯自动 2520:1139 败 / 主动指挥 2209:1147 败 / **第三局四条铁律 1089:1172 平（盟军分反超）** / 第四局 2086:1119 败。
**四局差异全部集中在一点：莫尔兹比港是否守住。** 第三局日军 1089 分（目标未达成），本局 2086（占领成功）。

### 决定胜负的第一铁律：必须派一支水面编队去 PM 做“夜间抵近—打乱卸载—撤离”
- 本局我因 5/5 发现 8 艘航速20 日舰距我舰队 1.4 格，把全部精力用于撤航母，**没有任何一艘船去过 PM**；
  日军 5/10 累计卸下 6016 兵(AV152)，对我守军(AV100、堡垒0)打出 **5:1 → 失守**。
- 第三局正是 TF14 夜袭抵近 2000 码迫其“中断卸载起锚撤退”，后续部队再未上岸，登陆场 AV 被磨到 34 而守住。
- **结论：PM 是本剧本唯一胜负点。撤退可做，但必须留一支水面编队执行 PM 打扰卸载循环，哪怕只去一趟。**

### 第二铁律：整片海域清空，不能只撤高价值单位
5/5 只撤主力、把补给 TF15/TF17 留在 (106,142) → 5/7 被日机空袭：**油船×2 + 驱逐×1 当场沉没，Sims 次日弃舰（共4艘）**。

### 第三铁律：写操作只以“列表结果列”或“视觉”验收，OCR 中间态判定必然假阴性
本局大量时间浪费在“详情页明明开着却判未开”（连坐 8 次双击全被判失败）：
- 全屏 psm11 OCR 漏读 `Set TF Destination / Group Mission / Patrol levels`；
- 词形不稳：`SurfaceCombat` vs `Surface Combat`（有空格）→ grep 落空；
- 数字识成 `1i11` → sed 解析出 (1,11) → 算出 4400,5487 的荒谬点击位。
**修正：①中间态用局部高倍裁剪 OCR（列表行区 `700x190+150+240 @300%` psm6）或视觉模型；②验收只认列表 Mission/目的地列的实测变化；③解析出的 hex 必做范围校验 x∈[85,125]、y∈[125,170]。**

### 第四铁律：检测失败后禁止盲目重试
按 t/ESC 重开界面会把已打开的详情关掉，形成“检测失败→重试→破坏→再失败”死循环。重试前先确认当前态；能按结果验证就不按中间态重试。

### 目的地探针法（第四局多次实测可用）
- 标定参数：**横 37.0 px/格、纵 37.0 px/格**（2026-10-09 权威值；旧的 42.86/37.5 已作废）。
  视野中心用**小地图黄框**读，不用探针（探针回读不可靠）。
- 流程：开编队表 → 双击行（**必须校验面板标题的 TF 编号**，否则会静默操作错误编队）
  → 点箭头(534,204) → [按需滚动] → 读**小地图黄框**取视野中心 → `cx=512+(tx-cx)*37.0, cy=384+(ty-cy)*37.0`
  → 点 (cx,cy) → ESC → 验收。
  ⚠️ 旧流程的「探针(500,500) + 42.86/37.5」已作废（比例 37.0，且回读不可靠）。
  ⚠️ **验收以结算后读层 `target_x/y` 为准**。
- **地图视野会在回合结算后重置、进详情时漂移：标定不可跨操作复用，探针与设置必须同会话完成。**
- 滚动必须逐键发送(间隔 0.6s)，批量发送丢键；up=视野北移(内容下移)、left=视野西移(内容右移)。

### 结果
- 损失5艘：Tippecanoe/Neosho/Worden(5/7 同一片海域)、Sims(弃舰)、Yorktown(5/11)；
  **列克星敦全程无损并入港汤斯维尔——四局首次保全航母**（但 PM 失守使分数大幅倒退）。
- 击沉日舰 8 艘：Tenryu/Yubari/Mutsuki/Kiyokawa Maru/Hagoromo Maru/Noshiro Maru#2/Kansai Maru/Kagu Maru。
- 战报文本（GBK）读取、陆基改任务流程、探针法均验证可用（见上文各节）。

## ★★第五局复盘（2026-09-24，PM 5/9 失守；击沉日舰9艘为五局之最）★★

### 铁律A：witp-cmd 回报 != 生效，每条 set-dest 后必须存档回读
第五局三次出现 `witp-cmd set-dest TFxx X Y` 打印“✓ 完成”，但读层 taskforces.json 的 target_x/y 未变（TF14/TF18/TF4 全中）。其内部只验证界面文字、不验证存档。
**铁律：① set-dest 后立即 `witp_read.sh <wpae000.pws>` 核对 target_x/y；② 未生效则重发或手动；③ 绝不能用 witp-cmd 的 stdout 作为落子凭据。**

### 铁律B：界面状态以读层为唯一事实源，T 列表只能当辅助
T 列表会只显示 6 个潜艇行（TF20-25），Human 大舰队不在视口——极易误判“编队消失”。方向键滚动列表需先点击列表获焦；双击行/编号列均不保证开详情。
**铁律：判断舰队位置/目的地/损伤一律读 taskforces.json / ships.json；界面列表只用于最终目视复核。**

### 铁律C：写操作优先 witp-cmd，手搓脚本是兜底
第五局最大失分：5/8 已见 8 艘日船团锚泊 PM，因手工找 T 列表行耗时 40+ 分钟，夜袭迟到一天，PM 5/9 失守。`witp-cmd set-dest` 同样动作 3 秒完成。
**铁律：命令阶段先 witp-cmd，只有它失效时才上手搓脚本；时间成本本身就是指挥质量。**

### 铁律D：PM 夜袭窗口只有一天——见到日船团当天就派水面舰
5/8 目击 8 艘日船 (98,130) → 应 5/8 当天派 TF18/TF4 向 PM 外海机动，5/9 凌晨抵近打乱卸载（第三局 TF14 夜袭即此战术，迫其“中断卸载起锚撤退”而守住）。晚一天=PM 失守。

### 铁律E：判定某海域被定位时，同海域所有主力同时撤
约克城 5/7 沉没根源：5/5 只撤了 TF14，把 TF16 留在 (106,142) 被日舰载机打掉（3弹2雷）。
**铁律："撤"是编队级动作，不是挑着撤。**

### 已知可用操作路径（第五局重新验证）
- 打开 TF 面板：地图上点击该 TF 图标（或 T 列表行 x≈200 编号列单击）；面板含 “Set TF Destination / Set TF Routing / Form New TF / Disband TF” 按钮列（右侧 x≈547-830, y≈201-480）。
- 地图滚动：**点地图中心 + 方向键**（每次 1 hex，需循环点击获焦）；自写 VNC 拖拽握手中断不可用；右键拖动无效。
- 每日战报留存：`SAVE/aoperationsreport_YYMMDD.txt`、`Combat_Events_YYMMDD.txt` 可回溯全程累计击沉。

## ★★第六局复盘（2026-09-24，DEISIVE JAPANESE VICTORY 2215:1116）★★

### 铁律F：witp-cmd set-dest 曾是完全的假实现——凡工具必验源码
第六局实测：`witp-cmd set-dest` 连续 9 次打印“✓ 完成”，但读层 target_x/y 从未改变。读源码发现：**它从未点击目标 hex**（tx,ty 参数完全未使用）——只做了 focus_map→t→双张第一行→点(534,204)→focus_map→escape→打印成功。
**铁律：① 任何执行器“✓”回执都不能直接采信，必须存档回读或界面回读双验证；② 关键工具先读源码再依赖；③ 已修复（第六局重写）：按 TF 编号 OCR 定位列表行→双击→点(570,201) Set TF Destination→按当前光标 hex 换算点击目标格→回读列表目的地列验证，未确认则报 ⚠️。**

### 铁律G：列表行 OCR 定位要求列表当前视图包含该行——否则需先滚动/筛选
T 列表常驻显示 6 个潜艇行（TF20-25），Human 大舰队在滚动区外；`_find_tf_row` 扫描 (235-500) 区域找不到 TF14 就默认 246（第一行），双张会打开错误编队。
**铁律：定位失败时必须先滚动列表到目标可见区（或点 Show 的 Human 复选框过滤），禁止静默回退默认行。修复版已加 ESC+t 重开兜底，但滚动仍未实现——下次应补“Home/End 键或拖滚动条”后再定位。**

### 铁律H：夜袭/急袭窗口的界面故障要有熔断
第六局 5/8 已见 9 艘日船抵 PM，但因 witp-cmd 失效+地图滚动失效（方向键无焦点不响应、拖拽握手中断），夜袭队 TF18 始终没派出，在原地 (106,142) 被日机打残（Australia 3弹1雷、Hobart 2雷沉没）。
**铁律：① 下达关键指令连续 2 次失败即切换方案（换工具/换路径），不允许在同一路径反复重试耗尽窗口；② 界面级故障（滚动/输入失效）时优先保编队脱离，不要留在原地吃伤害。**

### 铁律I：船团持续压制能推迟登陆，但挡不住最终卸载
第六局 5/9-5/12 四天里 9 艘日船始终锚泊 PM，岸炮+SBD 连续命中（Kagu/Aso Maru 等），登陆一再推迟；5/12 仍被 CAPTURE。**压制只能推迟，不能阻止**——必须靠水面舰抵近打乱卸载（第三局 TF14 夜袭）或持续空袭清零船团。

### 第六局结果
- 击沉日舰 10 艘（六局之最）：AMc Wa-2、APD Kikuzuki、E Oite、Azumasan/Canberra/Ikushima/Kagu/Koei/Seikai/Sinsei Maru 等；
- 我损失：CA Astoria、CA Chicago、CL Hobart、DD Morris；
- TF14 列克星敦完好生存，终局 24 艘；PM 5/12 失守；
- **另发现“点击 SCENARIO SELECTION 时游戏崩溃退出”的坑：SAVE 目录残留上一局 .pws 时会崩，开局前须把旧 .pws 移出 SAVE 目录（已备份 saves_r5_backup/）。**

## ★★参谋工具（witp-cmd / witp_staff）修复记录 —— 2026-09-24 第六局后★★

用户要求：充分利用参谋工具、把经验教训写入、修正工具错误。以下为已完成的修复与新增能力。

### 修复 1：`witp-cmd staff` 不再读陈旧缓存——默认强制读最新存档
- **病**：cmd_staff 只跑 `witp_staff.py brief`，而 perception 不跑读层（run_scraper=False），永远返回 `witp-reader/state/` 里的旧 JSON → 参谋建议书基于几小时前的数据。
- **修**：`cmd_staff` 默认自动找 SAVE 目录最新 .pws，转成槽位号传给 `--save <slot>` 并加 `--scraper`；新增 `--no-scraper` 可显式关闭（调试用）。建议书标题栏现显示 `数据来源存档：wpae000.pws`。

### 修复 2：`witp-cmd set-dest` 假实现（本命修复）
- **病**：原实现只做 focus_map→t→双击第一行→点(534,204)→ESC→打印✓，**tx,ty 参数完全未使用**。第六局连续 9 次假成功。
- **修**（重写）：OCR 定位目标 TF 列表行 → 双击开面板 → 点 (570,201) Set TF Destination → 读顶栏光标 hex 换算像素**真正点击目标格** → 回读列表目的地列验证；未确认打印 `⚠️ 需人工复核`。
- **配套防误击**：`_find_tf_row` 找不到行时先 End/Home 滚动重扫，仍失败返回 None → **明确中止**（不再静默双击第一行，那会打开错误编队甚至误击主菜单按钮）。

### 修复 3：参谋模型链路（fallbacks）
- **病**：config 里 opencode/mimo-v2.6-flash 已 401/403；单模型无 fallback，失败直接掉兜底建议。
- **修**：主模型改 `antigravity/gemini-3.7-flash-high`（实测返回干净），fallbacks 依次 `claude-sonnet-4-6` → `stepfun/step-5-preview`；`call_strategic_model` 改为多候选循环逐个尝试。
- **注意**：gemini-3-flash 已被 antigravity 下线（返回 `Gemini 3.5 Flash is no longer available`），gemini-3.7-flash-high / gemini-3.6-flash-high / claude-sonnet-4-6 可用。

### 修复 4：perception 静默失败 → 显式健康度
- **病**：读层 subprocess 异常被 `except: pass` 吞掉，静默返回旧 state（假新鲜）。
- **修**：capture_state 增加 `perception_health`（scraper_ok/state_fresh/warnings）；读层失败或 `state/` 日期与存档头不一致时**拒绝返回陈旧数据**；建议书 markdown 头部展示 `⚠️ 数据源健康告警` 与 `SKB：N 条教条 / M 个模式`。

### SKB 知识库已从 4 条教条扩展到 13 条 + 10 模式
- 新增教条 #5~#12：PM夜袭当天派（含禁令：压制不能阻止登陆）、发现日航母当天先手、被定位海域全船同撤、受损编队坚决撤、执行器回执必须读层验证、开局前清 SAVE 旧档、单航母不突双航母半径。
- patterns.json 从 2 条扩到 10 条，全部带 evidence 字段（指向 game-00X 与具体日期战果）。
- eval_weights.json：port_defense 5→10、新增 night_interdiction=10、supply_line_security 4→6。
- CLI 通路：`witp-cmd skb --add "教条正文" --confidence 0.93 --evidence "..."` 自动追加并 git 提交（自我迭代闭环）。

### 参谋 CLI 现有能力（验证通过）
| 命令 | 作用 |
|---|---|
| `witp-cmd staff` | 出建议书（默认读最新存档 + 引用 SKB 教条 + 健康度警示）|
| `witp-cmd staff --saves` | 枚举存档（槽位/时间/日期）|
| `witp-cmd staff --save 002` | 指挥读指定存档 |
| `witp-cmd staff --check / --fix / --resync` | 参谋部体检 / 修复 / 强制重读 |
| `witp-cmd skb` / `--add` | 看知识库状态 / 追加教条并 git 提交 |
| `witp-cmd record-turn --decision --result --orders` | 回写因果三元组 (S,D,R) |
| `witp-cmd close-game --outcome --enemy-score --own-score --notes` | 归档对局战果到 games/results.json |
| `witp-cmd set-dest TFxx X Y` | 真·设置编队目的地 + 回读验证 |

### 参谋建议书实例（修复后，引用教条推理）
第12回合建议书输出（gemini-3.7-flash-high）：引用 Doctrine #1/#2/#5/#6/#7/#8，给出 TF14 规避潜艇+前出、TF16 屏卫、TF22/23/24 三潜艇前出 PM/Jomard 航道、VS-5/VB-5 CAP 0 准备打击的协同方案——**已具备真正的参谋智囊行为**。

## ★★过回合铁律（2026-09-23 关键突破）★★

**“过回合卡死”根本不是卡死，是确认框在等回答！**

- 按 `E`（结束命令阶段）后，游戏弹出 **"End the Orders Phase? YES/NO"** 确认框，**YES 按钮在固定位置 (508,422)**。
- 不回答它 → 游戏 CPU 80% 空转、画面冻结、不写存档，看起来就像死循环（我曾误判为 d3d/ALSA 死循环并反复重启）。
- 正确流程：`witp_vnckey.py e` → 等 3s → `witp_c 508 422 click`（盲点，无弹窗时落在图上也只选中格子，无副作用）→ 等 autosave 更新。
- **每回合结算耗时 90-165 秒**，以 `SAVE/wpae000.pws` 时间戳变化为准。
- 结算后引擎依次写：`wpae002.pws`（PreTurnSave=旧状态）→ `wpae000.pws`（Autosave=新状态）。
- 推演脚本：`/root/.hermes/profiles/witp/workspace/witp-run-campaign.sh`（循环至 5/15 自动停）。
- **诊断提示**：判断“卡死”前先 OCR 全屏找 `YES/NO`（不要只 grep 日期关键词，否则永远看不到弹窗）。

## 环境配置（软硬件层，已验证）

- **渲染**：Xvnc 无硬件 GL，必须 `LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe` +
  `wine reg add "HKCU\Software\Wine\Direct3D" /v renderer /d gdi`（否则日志报 pixel format 失败）。
- **音频**：`wine reg add "HKCU\Software\Wine\Drivers" /v Audio /d ""`（须写入 user.reg 落盘）+
  启动器加 `WINEDLLOVERRIDES="midimap=d;wineoss.drv=d;winealsa.drv=d;winepulse.drv=d"`。
- **窗口模式**：普通模式（不用 explorer /desktop）；虚拟桌面非必需且增加坐标偏移麻烦。
- **分辨率**：屏幕 1400x1050，游戏窗口 1024x768；窗口位置每次启动可能不同 → 用 `witp_sync_offset` 动态取偏移。

## ★点击注入通道铁律（2026-09-22，用户亲测对比后定位）★

**WitP-AE 在 Wine 下不认 xdotool 的 XTEST 注入事件**——这是 DirectDraw/DirectInput 老游戏的典型症状。

- 症状：xdotool 点击对某些界面（航空队界面、Form New TF 对话框）**完全丢失**（像素变化=0，试过 6 个坐标/单击/双击/加延迟全部无效）；而**用户在 noVNC 网页上点同一个界面完全正常**。
- 原因：浏览器→noVNC→Xvnc 把事件当**真实设备输入**注入；xdotool 走 **XTEST 扩展**通道，Wine 的 DirectInput/raw-input 路径不接收。
- **解法：走 VNC(RFB) 协议注入鼠标事件**（复刻用户路径）：
  - 脚本 `/root/.hermes/profiles/witp/workspace/witp_vncclick.py`（最小 RFB 客户端，连 127.0.0.1:5902，
    握手后发 PointerEvent；含 8 步插值移动模拟真实鼠标轨迹 + 按下保持 80ms）。
  - 用法：`python3 witp_vncclick.py <屏幕x> <屏幕y> [click|dblclick|rclick|move]`
  - `witp-ui.sh` 的 `witp_c` / `witp_c2` / `witp_cr` 已全部改走该通道——**新写脚本一律用它们，禁止直接用 xdotool click**。
- 键盘（xdotool key）不受影响，可继续使用。

## 操作脚本库（2026-09-22用户指示：边操作边固化，禁止重复找坐标）
- `/root/.hermes/profiles/witp/workspace/witp-ui.sh` **已固化 20 个函数**（2026-09-22 全部 bash -n 验证+加载测试通过）：
  - 基础：witp_ensure_window(救活黑屏) / witp_screenshot / witp_ocr / witp_get_date(读档头日期) / witp_wait_visible(等结算)
  - 导航：witp_to_main_menu(子页MAIN MENU拨杆877,698) / witp_gamoptions_to_main / witp_open_scenario(665,574) / witp_open_load(665,627)
  - 流程：witp_launch(含openbox检查) / witp_fix_res(分辨率守护) / witp_disable_audio / witp_load_slot 179(载入法) / witp_select_coral_sea(全流程一键开局) / witp_brief(读层简报) / witp_end_turn(E过回合+等结算) / witp_close_summaries(逐页点Done 566,255)
- **坐标基线（2026-09-24 修订）**：屏幕 = **1400x1050**，游戏窗口 = 1024x768，偏移 = **(188,150)**。游戏重启后偏移会变，**必须 `witp_sync_offset` 实时读取**，不得沿用记忆值。
- **旧基线 1360x768 / 1024x768 已废弃**（2026-09-22 迁到虚拟桌面模式前的值）。改环境后若基线不符，用 `witp_recenter` 归位容器，**严禁 xrandr 硬改**（会让 Wine 鼠标捕获窗口与屏幕尺寸失配 → 点击全失效）。
- 主菜单按钮需**双击**（单击只悬停高亮）；按钮列 x=665：PREFERENCES(481-525) / SCENARIO(552-596) / LOAD A SAVED GAME(618-637) / EXIT(646-662)。
- **载入法（用户指教）**：SAVE MENU 的 SELECT SAVE GAME 按钮(337,577) = 载入按钮；单击存档行（变绿高亮）→ 点按钮即载入。002 行（5/4 PreTurnSave）y=179。
- 卡死根因（5/5 结算）：d3d cpu_blitter_blit 失败 + ALSA underrun 死循环；已用 `wine reg add "HKCU\Software\Wine\Drivers" /v Audio /d ""` 禁音频解决。
- 记忆库写入纪律：每任务最多一次，禁止进度性写入，防死循环。

## 存档机制（2026-09-24 重开新局实测，勿再走弯路）

- **开局后 SAVE 目录无 `.pws` 是正常的**：引擎只在**过回合结算时**自动写 `wpae002.pws`(PreTurnSave) + `wpae000.pws`(Autosave)。
- 因此**读层/参谋部在第 1 回合无法读档**——参谋部体检会显示「实际存档: None」，这是预期状态，不是故障，过一次回合即恢复。
- **不要去折腾游戏内 F 键存档对话框**：该对话框鼠标点击不响应（VNC 与 xdotool 两通道实测均无像素变化），键盘 Up/Down 有效但无法激活 SAVE。上一个模型在此反复摸索属无效劳动。
- 正确流程：开局 → 直接部署第 1 回合命令 → `witp-cmd end-turn` 过回合 → 引擎自动写档 → 读层/参谋部立即可用。
- **窗口漂移自愈**：若发现点击全部落空，先 `xdotool search --name "War in the Pacific"` 读 Absolute upper-left X/Y，正常应为 **(188,150)**；漂移后用 `wmctrl -i -r <WineDesktop窗口ID> -e 0,0,0,1024,768` 归位桌面窗口（游戏窗口是其子窗口，会随之回位）。**严禁直接对游戏窗口用 `xdotool windowmove`（会被当作相对位移，导致二次漂移）**。

## 红线
- 汉化版 exe 写的存档任何 DLL 都 -5，勿再试；只用英文版自生成存档
- 界面主菜单按 Esc 会退出游戏
- 主菜单按钮：选择战役剧本≈(880,574)；003 行 y≈240；选择剧本(500,569)；开始游戏(875,533)