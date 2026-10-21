# 来自 default profile 的补充记录：witp-ae-autoplay

> 这份内容原先只存在于 default profile 的同名技能里，witp profile 副本没有。
> 迁移时整份保留，作为历史实测记录/架构说明参考。使用时以 vitp profile 的
> SKILL.md 为准；本文件若与其冲突，以 SKILL.md 为准。

---

---
name: witp-ae-autoplay
description: "Use when auto-playing WitP-AE Coral Sea on English 1108r9."
---

# WitP-AE 自动推演闭环（英文 1108r9）

**对局状态：珊瑚海 003 盟军方已打完（1942-05-01~05-15，三轮对比见下）。当前无进行中对局；新开局时先确认用户选的剧本。**

## 环境
- 游戏：/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral's Edition（exe=War in the Pacific Admiral Edition.exe）
- 启动器：/root/.hermes/workspace/witp-launch-en1108.sh（DISPLAY=:98，必须先确认 openbox 在跑，否则窗口黑/不可见）
- SAVE：该目录下 SAVE/wpae000(自动)/002(上回合)/003(手动).pws
- 读层：/root/.hermes/workspace/witp-reader/witp_read.sh —— **必须改用英文 DLL 目录与英文 SAVE 路径**（DLL dir = Z:\root\.wine-witp\drive_c\1108r9\...；旧脚本硬编码中文版路径）
- 读层输出：state/ 下 JSON + witp_summarize.py 出中文简报（盟军双盲视角）
- 存档路径含中文会 UnicodeEncodeError，测试样本必须放纯 ASCII 路径

## 闭环流程（每回合）
1. 读当前存档（wpae002 或最新）出中文态势简报
2. 依简报下盟军命令（界面操作：编队任务/航空任务/巡逻扇面）
3. 过回合：战斗动画已关；E 键确认→Y；战斗摘要退出点=完成左侧小箭头(x≈737,y≈257)
4. 引擎写新 wpae002 → 回到第 1 步
5. 剧本 1942-05-01~05-15，推完出终局中文报告（战果/损失/胜负）

## 航空队界面（实测通过的完整操作，2026-09-22）

- 打开：`witp_c 300 500 click`（点地图给键盘焦点）→ `xdotool key n` → `witp_c2 <行x> <行y>` 双击中队。
- **可点区域在文字左侧的图标列**（任务列表 x≈660，而文字从 x≈677 开始）——**直接点文字无效，必须点图标**。同理 TF 界面的菜单项：文字 x≈713、图标 x≈704。
- 任务列表行坐标（游戏内，行距≈12）：Airfield Attack y=146 / Port y=158 / Naval Attack y=170 / Ground Attack y=182 / Sweep y=194 / Recon y=206 / **Naval Search y=218** / **ASW Patrol y=230** / City y=242 / Training y=254。
- 扇面（巡逻弧）控制：**Set on map 图标 = (745,377)**（VB2 布局）→ 点后切到地图 → 点两个方位点定义起/止 → ESC 返回；成功标志：Start 由 000° 变为实测值 + 出现 Clockwise。
- Patrol levels 区域：ASW 50% / Search 0% / CAP / LRCAP / Train 各行可调百分比。
- 验证方式（权威）：ESC 回列表 → `xdotool key n` → 读 Mission 列（VB2 由 Naval → Search 即成功）。

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
5. 反算真目标：`cx=500+(TX-HX)*42.86`，`cy=500+(TY-HY)*37.5`（**横42.86/纵37.5 px每格恒定**）
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
- 标定参数：**横 42.86 px/格、纵 37.5 px/格**；探针位 **(500,500)**；目的地模式下顶栏 Hex 隐藏无法悬停。
- 流程：开编队表(psm6 整行 OCR，按“行内第一个数字==TF编号”识别，避免同名 Air Combat/列值误匹配) → 双击行 → 点箭头(534,204) → [按需滚动] → 探针(500,500) → ESC → 读行取 hex → `cx=500+(tx-hx)*42.86, cy=500+(ty-hy)*37.5` → 复现同一滚动序列 → 点 (cx,cy) → ESC → 读行验收。
- **地图视野会在回合结算后重置、进详情时漂移：标定不可跨操作复用，探针与设置必须同会话完成。**
- 滚动必须逐键发送(间隔 0.6s)，批量发送丢键；up=视野北移(内容下移)、left=视野西移(内容右移)。

### 结果
- 损失5艘：Tippecanoe/Neosho/Worden(5/7 同一片海域)、Sims(弃舰)、Yorktown(5/11)；
  **列克星敦全程无损并入港汤斯维尔——四局首次保全航母**（但 PM 失守使分数大幅倒退）。
- 击沉日舰 8 艘：Tenryu/Yubari/Mutsuki/Kiyokawa Maru/Hagoromo Maru/Noshiro Maru#2/Kansai Maru/Kagu Maru。
- 战报文本（GBK）读取、陆基改任务流程、探针法均验证可用（见上文各节）。

## ★★过回合铁律（2026-09-23 关键突破）★★

**“过回合卡死”根本不是卡死，是确认框在等回答！**

- 按 `E`（结束命令阶段）后，游戏弹出 **"End the Orders Phase? YES/NO"** 确认框，**YES 按钮在固定位置 (508,422)**。
- 不回答它 → 游戏 CPU 80% 空转、画面冻结、不写存档，看起来就像死循环（我曾误判为 d3d/ALSA 死循环并反复重启）。
- 正确流程：`witp_vnckey.py e` → 等 3s → `witp_c 508 422 click`（盲点，无弹窗时落在图上也只选中格子，无副作用）→ 等 autosave 更新。
- **每回合结算耗时 90-165 秒**，以 `SAVE/wpae000.pws` 时间戳变化为准。
- 结算后引擎依次写：`wpae002.pws`（PreTurnSave=旧状态）→ `wpae000.pws`（Autosave=新状态）。
- 推演脚本：`/root/.hermes/workspace/witp-run-campaign.sh`（循环至 5/15 自动停）。
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
  - 脚本 `/root/.hermes/workspace/witp_vncclick.py`（最小 RFB 客户端，连 127.0.0.1:5902，
    握手后发 PointerEvent；含 8 步插值移动模拟真实鼠标轨迹 + 按下保持 80ms）。
  - 用法：`python3 witp_vncclick.py <屏幕x> <屏幕y> [click|dblclick|rclick|move]`
  - `witp-ui.sh` 的 `witp_c` / `witp_c2` / `witp_cr` 已全部改走该通道——**新写脚本一律用它们，禁止直接用 xdotool click**。
- 键盘（xdotool key）不受影响，可继续使用。

## 操作脚本库（2026-09-22用户指示：边操作边固化，禁止重复找坐标）
- `/root/.hermes/workspace/witp-ui.sh` **已固化 20 个函数**（2026-09-22 全部 bash -n 验证+加载测试通过）：
  - 基础：witp_ensure_window(救活黑屏) / witp_screenshot / witp_ocr / witp_get_date(读档头日期) / witp_wait_visible(等结算)
  - 导航：witp_to_main_menu(子页MAIN MENU拨杆877,698) / witp_gamoptions_to_main / witp_open_scenario(665,574) / witp_open_load(665,627)
  - 流程：witp_launch(含openbox检查) / witp_fix_res(分辨率守护) / witp_disable_audio / witp_load_slot 179(载入法) / witp_select_coral_sea(全流程一键开局) / witp_brief(读层简报) / witp_end_turn(E过回合+等结算) / witp_close_summaries(逐页点Done 566,255)
- **Xvnc 分辨率会被重置为 1024x768**（游戏重启后），修复：`xrandr --output VNC-0 --mode 1360x768`；所有坐标基于 1360x768。
- 主菜单按钮需**双击**（单击只悬停高亮）；按钮列 x=665：PREFERENCES(481-525) / SCENARIO(552-596) / LOAD A SAVED GAME(618-637) / EXIT(646-662)。
- **载入法（用户指教）**：SAVE MENU 的 SELECT SAVE GAME 按钮(337,577) = 载入按钮；单击存档行（变绿高亮）→ 点按钮即载入。002 行（5/4 PreTurnSave）y=179。
- 卡死根因（5/5 结算）：d3d cpu_blitter_blit 失败 + ALSA underrun 死循环；已用 `wine reg add "HKCU\Software\Wine\Drivers" /v Audio /d ""` 禁音频解决。
- 记忆库写入纪律：每任务最多一次，禁止进度性写入，防死循环。

## 红线
- 汉化版 exe 写的存档任何 DLL 都 -5，勿再试；只用英文版自生成存档
- 界面主菜单按 Esc 会退出游戏
- 主菜单按钮：选择战役剧本≈(880,574)；003 行 y≈240；选择剧本(500,569)；开始游戏(875,533)