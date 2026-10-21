# 来自 default profile 的补充记录：witp-ae-interface

> 这份内容原先只存在于 default profile 的同名技能里，witp profile 副本没有。
> 迁移时整份保留，作为历史实测记录/架构说明参考。使用时以 vitp profile 的
> SKILL.md 为准；本文件若与其冲突，以 SKILL.md 为准。

---

---
name: witp-ae-interface
description: "Use when driving WitP-AE under Wine on Linux."
---

# WitP-AE 界面与读层（重起炉灶后重新实测，仅收实测通过的条目）

2026-09 用户判定旧路线经验不可采用、要求重起炉灶。以下每条均带实测证据；未实测的不写。

## ★读层已升级为纯 Python（2026-10-17）★

`/root/.hermes/workspace/witp-reader/witp_core.py` 直接解析 `.pws`（gzip+逐记录 zlib+定长结构体），
**不需要 Wine / 32 位 Python / pwsdll.dll**，1MB 存档约 0.15s（旧 DLL 路径约 10s）。
用法：`python3 witp_core.py <存档> [--json]`，或 `import witp_core; g=witp_core.load(p)`
（`g.tfs / g.airgroups / g.bases() / g.ground_units() / g.ships / g.brief_cn()`）。
命令写入见 `witp_orders.py`；容器格式与写档硬门槛见技能 `witp-ae-save-format`。
MCP 服务：`witp-ae`（`/root/.hermes/mcp-servers/witp-mcp/server.py`，13 个工具）。

## 读层（已打通：一条命令出中文态势简报）

- 工具：GitHub `drwilliamroney/pywitpaescraper`（MIT），本地副本 `/root/.hermes/workspace/witp-reader/pywitpaescraper`。
- 入口脚本：`/root/.hermes/workspace/witp-reader/witp_read.sh [存档路径]`，默认取游戏 SAVE 下的 `wpae002.pws`；产出 JSON 到 `state/` 并打印中文参谋简报。简报生成器 `witp_summarize.py`。
- **关键前提：必须用安装包里的原版英文 exe**（md5 `23101256a938`）写出的存档。**汉化 exe（md5 `f0d6a77f7ca9`）写的存档这个 pwsdll.dll 读不了**：探针第 2 条记录即返回 -5（内嵌 CryptoPP，属解密/校验失败）。A/B 实测：同一脚本、同一 DLL、同一机器，换 exe 后一份可读一份不可读；包内 2012 年的 9 份旧档（原版 exe 所写）全部可读。两份存档结构几乎一致（SCENARIO 记录均 99696 字节、逐字节差异仅 0.6%），改记录头标志位无效。
- 32 位 Windows Python 3.11.9（embeddable，从华为镜像下）装在 prefix 的 `C:\py32`；**必须在 `python311._pth` 里加一行仓库绝对路径**（该发行版忽略 PYTHONPATH）。
- 本地补丁（均在我们副本内，已注释）：① 去掉 `rich` 依赖（改标准库日志）；② `pwsdll7.dll` 改为可选（实测 `objdump -p pwsdll.dll` 只导入 KERNEL32，二进制内也无 pwsdll7 字样）；③ 样本校验可跳过（上游写死找“企业号/Nimitz”，珊瑚海这类小剧本会误报失败，用环境变量 `WITP_SKIP_SAMPLE_VALIDATION=1`）；④ 名字解码改为先试 GBK（否则中文名全是 U+FFFD）；⑤ 四个战报文本解析器改按 GBK 读（否则战报里的中文地名乱码）。
- 产出 8 个 JSON：ships / ground_units / airgroups / bases / taskforces / minefields / turn / threats。已实测有价值的字段：编队带 **指挥官、旗舰、当日始末位置、目标格 target_x/y**；舰船带损伤四值（系统-进水-起火-引擎）、舰级、编成；航空队带可用/编制、驻地（舰载或基地）、主/次任务码、搜索比例与扇面；基地带港口/机场/补给/燃料/油料/资源及各自需求、驻军与驻机、指挥部；threats 由战报+SIGINT 推导出潜艇/水面/航母/登陆威胁区。
- **航空队“主任务码”尚未做过中文映射**（存档原始数字），简报里故意不译。
- 基地归属判定：存档里没有归属字段，用两项特征——有本方驻军/驻机，或 `area_command` 含“司令部”（实测：本方=南太平洋/西南太平洋/澳大利亚司令部；敌方=中国派遣军/东南方面舰队）。离图基地坐标为 65535，须滤掉。

## 中文字体：游戏 GUI 只认 Wine 内置 System 位图字体（实测）

- 症状：航空队/编队列表里中文名整片空白，只剩名字里的 ASCII 部分（“澳大利亚空军第23中队”→只显示 `23`；机型“挑战”→完全空白）。
- 根因（`WINEDEBUG=+font` 日志，53,972 条请求）：游戏 GUI 走 `CreateFontA("System", h=16, weight=700, charset=134)`，Wine 把它匹配到内置位图字体 `/usr/share/wine/fonts/svgasys.fon`（只有拉丁字形）。注册表 `HKCU\Software\Wine\Fonts\Replacements` 里的 `System=SimSun` 被 Wine 静默忽略（日志中 `add_family_replacement ... to L"System"` 计数为 0）；把改名字体的 TTF 放进前缀 `C:\windows\Fonts` 也不够——同族里内置位图面仍胜出（`Chosen: L"System Regular" (svgasys.fon)`）。
- **修法（进程级、不动系统文件）**：① 用 fontTools 把文泉驿正黑（`/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc` 第 0 个字体）name 表改成 family/fullname=`System`、subfamily=`Regular`，另存到前缀 `C:\windows\Fonts\system-cjk.ttf`（OS/2 代码页已含 CP936 位 0x40000）；② `witp-launch.sh` 里 `unshare -m --propagation private` 后 `mount --bind <只排除 svgasys.fon 的软链目录> /usr/share/wine/fonts`。实测日志变为 `Chosen: L"System" (C:\windows\fonts\system-cjk.ttf)`，菜单/选项/状态栏等 GDI 文字中文正常。用 `ls /proc/<游戏PID>/root/usr/share/wine/fonts` 可验证命名空间生效。
- **但列表/详情页的中文仍显示不出来——这是英文原版 exe 的固有限制**：字体日志里游戏向 GDI 只发过 512 次单字符 `NtGdiExtTextOutW`，字符一路到 `\007f` 为止，**一次中文都没请求**（600k+ 行日志里高于 0x2000 的转义计数为 0）。即游戏自己按 ASCII 建字形表绘制对话文本，与 Wine 字体无关；菜单里看到的中文是汉化版替换的位图美术（ART/*.bmp）。
- 结论：想让游戏内名称可见，只能走“数据改英文”路线（见下），或接受中文名在对话界面为空、由读层从存档取中文名（报告仍是中文）。

## 中文数据与英文数据的边界（实测）

- `SCEN/wpa001..010.dat` 等是**汉化过的中文数据**（含“挑战”“澳大利亚空军”）；`wpa011..014.dat` 是**英文原版数据**。剧本 003 的原始英文数据不在本机（安装包内 SCEN 与已安装目录逐文件同 md5）。
- 官方 CSV 往返工具 `witploadAE.exe`（Beta2/ 与 SCEN/ 各有一份）可用：`cd <含 wpa003.dat 等场景文件的目录>` 后 `wine witploadAE.exe /e /s3`（`/d <路径>` 参数实测报 `Directory "" not accessible`，改用默认“当前目录”即可）。导出 GBK 编码 CSV：WITPshp(舰)、WITPgrp(航空队)、WITPair(机型)、WITPcls(舰级)、WITPloc(基地/位置)、WITPdev(设备)、WITPldr(指挥官)、WITPplt(飞行员)。导入为同目录下 `wine witploadAE.exe /s3`。改数据前必须备份 `.dat`（包内副本可作还原源）。
- 中文名行数（剧本 003 全库）：舰 6297、位置 5371、舰级 2345、航空队 1835、设备 1477、机型 556 —— 全量翻译不现实；只为“剧本 003 实际用到的单位”译名才可行（单位清单可从存档 JSON 取）。
- **【已纠正的错误结论】汉化版 exe 的存档是可以读的**。实测：让汉化版（最初始发行包 exe）现场过一回合写出的新存档，用主目录 pwsdll（2014-06-07）与 Beta2 的 pwsdll（2012-11-04）都能完整解析（8 个 JSON + 20 万字节中文简报：`turn.json` 日期 12/08/41、剧本“太平洋战争：12月8日大战役”、49 编队/1432 舰/1168 地面部队，舰名等全为中文），所以“汉化版玩 + AI 读档”**可行**。之前判它不可读，是被一份旧样本（`exe-backup/wpae002-CN-hanhua.pws`）误导了——该样本在三个 DLL 上都报 `Missing RecType values ...`，需单独复核（不能据此否定汉化版存档）。
- **`tools/witpstaff/pwsdll.dll`（2011-12-10, 487424B）不可用**：它会直接让调用它的进程崩溃（`Unhandled exception 0xc0000008`）。常用只用主目录与 Beta2 两版。
- **读层进程崩溃会抢走游戏的 VNC 画面**：读档脚本带着 `DISPLAY=:98` 跑，若是崩溃，Wine 会在 :98 上弹出“程序错误/WineDbg”窗口叠在游戏画面上，**看上去很像游戏崩了**（用户会据此报障）。判别方法：看游戏自己的进程是否还在、游戏启动日志有无 `Unhandled exception`；对比 `$OUT/../readtest.log` 里是否正是读层崩的。要避免干扰，可给读层换一个 display 或在前缀里关掉 WineDbg 弹窗（`HKCU\\Software\\Wine\\WineDbg\\ShowCrashDialog=0`）。

## 剧本数据英文化（实测可行，已落地）

为什么需要：英文原版 exe 的对话文字渲染器只处理 ASCII（见上节），所以汉化数据里的中文名在列表/详情页显示为空；要看得见名字，只能把剧本数据改成英文。

- **关键发现：中文数据文件与英文数据文件同尺寸、同字节布局**（wpa/wps/wpg/wpl/wpd/wph/wpp 的 003 与 011 逐文件等长），名字是 **20 字节定长字段**，所以同一偏移就是同一实体（实测：@61960 003='澳大利亚空军第23中队' ↔ 011='No.23 Sqn RAAF'；@4360 '挑战'↔'Wirraway'；@60040 '列克星敦'↔'Lexington'）。但名池在局部会错位（例：第2舰载侦察机中队那一槽 011 是 'VF(N)-76 Det 1'），**不能全局照搬，必须逐条核实**。
- **权威英文名来源**：① 英文剧本 011-014 的名池（同偏移）；② **剧本003 自己的飞行员文件 wpp003.dat** 里带 `标识=====飞行员名` 的记录（如 `VF-2================Banks, J.L.`、`VS-2================Leppla, J.A.`）——这是 003 自身的英文标识，最可信。
- **脚本**：`/root/.hermes/workspace/witp-scen003-csv/`（`patch_csv_names.py` 改 CSV 第2列 Name；`sandbox/` 做导入验证；`backup-orig/`、`backup-csv-原版/` 是原始备份）。改名必须同时满足“英文名见于官方英文数据”才会写入。
- **导入验证**：`witploadAE.exe /s3`（当前目录需含场景 .dat 与 CSV）导入后重新导出，与改前导出逐格对比 → 实测只改动了 67 行且全在 Name 列，其余表 0 变化。（未改名的空白导入会有少量字节差异：尾部填充空格被归一化为 0，语义不变；wph/wpl 各约 1111/92 字节。）
- **游戏会提示数据库变更**：加载已有战役时弹 `Add database changes to this edited campaign (#3)?` —— 说明改动已被引擎识别。选 YES 可把 DB 变更写入当前战役。
- **重要限制：单位名在存档里是烤死的**。载入旧战役后，机型列会立即变英文（机型由 DB 解析），但**航空队名仍是中文（显示为空）**，因为组名早已写进存档。要在屏幕上看到英文组名，**必须开新局**。
- 场景菜单操作要点：主菜单→“选择战役剧本”进的是**剧本菜单**页（左侧 001-021 列表 + 右侧摘要 + 红色“选择剧本”按钮）；**单击某行**即改选（摘要日期区间会变，如 Coral Sea = 1942051-19420515，可据此确认），再点“选择剧本”→详情页→“开始游戏”。主菜单上按 Esc 会直接退出游戏，慎用。

## 存档与过回合（实测）

- 用户指令(0922)：重测前必须**删掉全部Wine侧WitP目录、从汉化压缩包全新解压，不保留旧备份目录**——避免任何历史文件干扰读档测试。
- 战斗摘要退出点：不是「完成」文字，是它**左侧小箭头**（实测 x≈737,y≈257）；点文字无反应。
- 关闭「显示战斗动画」后 ASF 媒体卡死消失（插件 gstreamer1.0-plugins-ugly+libav 已装，动画关仍是保险）。
- 主菜单按 Esc 会直接退出游戏；读档槽位行用文字 OCR 定位行 y 再点，点击后以摘要日期区间变化确认选中。

- 引擎自动写的 `wpae002.pws` 是可靠输入（每次结算新回合时刷新）；读它无需游戏在运行。
- 英文版 exe 的保存对话框（F）对方才试过的鼠标点击/回车/方向键组合均未落盘（未解决）；**可靠做法是过一回合让引擎写档**。
- 汉化版 exe 写的中文注释档头（如“祥凤…日期: 05/04/42”）与本 DLL 不兼容，同前。**2026-09-22 终局结论：汉化版 exe 写的珊瑚海存档记录1(99696B场景块)在任何 DLL 下都 -5（汉化版 DLL、1108r9 英文 DLL 均验证）⇒ 汉化版 exe 写档时对场景块的加密/校验与标准格式不符，非 DLL 单方问题。【英文 1108r9 自己写的珊瑚海存档（wpae000/002/003.pws）用 1108r9 DLL 全部完整可读】⇒ 读层路线对英文版走通，AI 参谋闭环用英文版。英文 1108r9 安装于 /root/.wine-witp/drive_c/1108r9/，启动器 witp-launch-en1108.sh，SAVE 目录独立。****2026-09-22 全新环境复测坐实：汉化版 exe 写的珊瑚海存档场景块(记录1)在任何 DLL 下都 -5（汉化版 DLL、1108r9 英文 DLL 均验证）；大战役存档任何 DLL 可读；1108r9 SCEN 自带 wpae014 可读 ⇒ 汉化版 exe 写档时对场景块的加密/校验与标准格式不符，非 DLL 单方问题。1108r9 已解压至 /root/.wine-witp/drive_c/1108r9/。**

## 启动（实测）

- **工作目录必须是游戏目录**，否则进游戏即弹 `Error : Unable to find PW data !!!`；启动器放工作区不放游戏目录（`/root/.hermes/workspace/witp-launch.sh`）。
- 中文版界面需 `LANG=LC_ALL=zh_CN.GBK` 否则 ANSI 代码页=1252，界面文本变拉丁乱码（摘要：本文件旧版记过，仍成立）。
- 专用显示：`Xvnc :98 -geometry 1360x768 -rfbport 5902` + openbox；对外看画面用 frp（本机 6081 → 云 26080，已放行）。
- 开场视频缺 GStreamer ASF 插件会刷错误，不影响流程。

## 输入通道（实测）

- 游戏内键盘可用（T 编队表 / A 空基航空队 / N 舰载航空队 / B 基地表 / E-Y 过回合 / Esc 关窗）。
- 菜单类界面键盘无效，必须鼠标点击；X 层注入（xdotool）在原生窗口模式下可用（旧“点不动”的结论是在 Wine 虚拟桌面下得出的，已证伪）。
- 控件定位方法：悬停扫描（固定基线截图，逐点移动并比对像素差），可框出按钮范围；红色/棕色按钮可用颜色掩膜+连通域。中文界面 OCR 不可靠，写操作一律以存档回读为凭。
