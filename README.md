# WitP-AE Autonomous Commander & Neural Staff System
> 《太平洋战争：海军上将篇》（War in the Pacific: Admiral's Edition）全自主智能指挥与作战参谋系统

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Wine-orange.svg)](#在什么环境下使用)
[![Game](https://img.shields.io/badge/Game-WitP--AE%201108r9-green.svg)](#游戏本体要求)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-purple.svg)](#mcp-服务协议接入)

---

## 目录
- [一、这是什么（项目介绍）](#一这是什么项目介绍)
  - [1.1 项目背景与核心痛点](#11-项目背景与核心痛点)
  - [1.2 核心支柱与技术架构](#12-核心支柱与技术架构)
- [二、在什么环境下使用（运行环境与前置依赖）](#二在什么环境下使用运行环境与前置依赖)
  - [2.1 基础系统与依赖栈](#21-基础系统与依赖栈)
  - [2.2 游戏本体与 Wine 环境准备](#22-游戏本体与-wine-环境准备)
  - [2.3 关键稳定性补丁（音频崩溃根治与 cgroup 隔离）](#23-关键稳定性补丁音频崩溃根治与-cgroup-隔离)
- [三、怎么使用（完整操作指南）](#三怎么使用完整操作指南)
  - [3.1 快速部署与服务启动](#31-快速部署与服务启动)
  - [3.2 命令行前线工具（witp-cmd）](#32-命令行前线工具witp-cmd)
  - [3.3 参谋部系统（Staff Intelligence）](#33-参谋部系统staff-intelligence)
  - [3.4 MCP 服务接入（Agent 智能体直接调用）](#34-mcp-服务接入agent-智能体直接调用)
  - [3.5 战略知识库与自我迭代机制（SKB）](#35-战略知识库与自我迭代机制skb)
- [四、经典推演与制胜配方实战（以珊瑚海战役为例）](#四经典推演与制胜配方实战以珊瑚海战役为例)
- [五、项目目录结构](#五项目目录结构)
- [六、开源许可证](#六开源许可证)

---

## 一、这是什么（项目介绍）

### 1.1 项目背景与核心痛点
《War in the Pacific: Admiral's Edition》（WitP-AE）作为硬核二战海空战兵棋推演的巅峰之作，地图涵盖整个太平洋与印度洋战场，拥有数以万计的真实舰船、航空中队、地面战备基地以及严密的后勤补给链路。

传统的自动化或辅助方案存在严重瓶颈：
- **GUI 点击脆弱**：依赖 OCR 与屏幕固定坐标点击，在 Wine 窗口重绘、系统字体缩放或焦点丢失时极易发生点击错位或死锁；
- **决策黑盒盲目**：传统脚本缺乏全局战局推演与因果复盘能力，面对复杂双盲环境往往一触即溃；
- **战役数据断层**：战况结算后的损管、补给、侦察情报散落于二进制存档与战报文本，难以形成统一语义感知。

本项目构建了一套**解耦传统 GUI、直达游戏二进制与内存底层、并由大语言模型（LLM）参谋部驱动**的全新自动化推演闭环系统。

### 1.2 核心支柱与技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│                   LLM Commander & Hermes Agent                   │
└──────────────┬───────────────────────────────────┬───────────────┘
               │                                   │
      [语义作战意图/决策审核]               [感知态势/研判方案]
               ▼                                   ▲
┌──────────────────────────────┐   ┌──────────────────────────────┐
│     前线操作手 (witp-cmd)      │   │   作战参谋部 (witp_staff.py)   │
│  - 编队航路点直写            │   │  - 威胁等级三级字典序        │
│  - 航空防空分层与扇面        │   │  - 航母前推打击位动态核算    │
│  - 单键 E+y 注入推进回合     │   │  - 专职化侦察扇面铺设方案    │
└──────────────┬───────────────┘   └──────────────▲───────────────┘
               │                                   │
      [T1 内存直控 / T2 键盘]             [二进制读层 / 战报解析]
               ▼                                   │
┌──────────────────────────────────────────────────┴──────────────┐
│               WitP-AE 运行时底层 (Wine 1108r9)                   │
│  • .pws 存档二进制流逆向解析 (gzip + raw deflate + zlib)         │
│  • 进程内存双镜像实时读写 (PWSTaskGroup / PWSAirGroup 等)        │
│  • 终局模态弹窗自动 OCR 评分与自旋防护 (witp_endgame.py)         │
└─────────────────────────────────────────────────────────────────┘
```

1. **T1 内存直控与零键鼠修改（Zero-GUI Direct Control）**：
   - 彻底逆向 WitP-AE 的底层数据容器与内存映射，实现编队航路点（Waypoints）、航空队主次任务、CAP 比例、搜索扇面、地面部队战斗模式的**内存毫秒级直读直写**；
   - 具备双镜像同步校验技术，杜绝游戏存档覆盖崩溃。
2. **T2 极简按键单键推进（Single-Key Turn Advance）**：
   - 采用标准 RFB 键盘通道，以极简的 `E → y` 单键指令完成回合推进与指令下达，配合截屏哈希变化判据与终局保护，告别任何复杂的鼠标拖曳。
3. **双脑协同参谋推理（Neural Staff Intelligence）**：
   - 参谋部根据最新存档与战报，实时评估交战接触线、计算航母前推打击位（避开岸基轰炸圈并预置退路锚点）、制定 13 个中队的专职化侦察扇面，出具规范的《作战方案建议书》。
4. **因果三元组与自我迭代（Causal Loop & SKB Evolution）**：
   - 逐回合强制留痕记录 $(S, D, R)$（态势认知、决策意图、实际战果），终局自动复盘提炼可证伪的教条，直接沉淀入战略知识库（已积累 120 条实证教条）。

---

## 二、在什么环境下使用（运行环境与前置依赖）

### 2.1 基础系统与依赖栈
- **操作系统**：Linux x86_64（Ubuntu 22.04 / 24.04 LTS 或 Debian 12 验证通过）。
- **Python 环境**：
  - **宿主环境**：Python 3.10+（运行 MCP 服务端、参谋部推理系统、前线 CLI）。
  - **Wine 虚拟子环境**：内置 32 位 Python 3.11（`C:\py32\python.exe`，用于驱动原生 `pwsdll.dll` 解析器）。
- **系统包依赖**：
  ```bash
  sudo apt-get update && sudo apt-get install -y \
      wine wine32 wine64 \
      tigervnc-standalone-server x11vnc openbox \
      xdotool imagemagick tesseract-ocr tesseract-ocr-eng \
      git curl jq
  ```

### 2.2 游戏本体要求
- **必须采用官方原版英文 1108r9**：
  - 严禁使用第三方汉化版 EXE（汉化版写入存档时原生 `pwsdll.dll` 会报 `-5` 解密校验失败）。
- **分辨率与桌面规范**：
  - 原生游戏分辨率为 **1024x768**；
  - 虚拟桌面（Xvnc）推荐配置为 `1400x1050x24` 或 `1024x768x24`；
  - **必须运行 Openbox 窗口管理器**：Wine 依赖窗口管理器分配按键焦点，缺失 Openbox 将导致按键静默丢失。

### 2.3 关键稳定性补丁（音频崩溃根治与 cgroup 隔离）

#### ① quartz.dll 二进制规避补丁（根治随机段错误）
- **现象**：游戏自带音效解码组件 `witprec.exe` 在 Wine 环境下运行 1.5~3.5 小时后必报 `filesource.c:397` 越界断言并发生段错误崩溃。
- **解法**：项目在启动脚本 `automation/witp-launch-en1108.sh` 中集成了安全出口补丁，将越界跳转重定向至安全释放分支，实现 100+ 小时连续推演零崩溃。

#### ② 独立 systemd cgroup 隔离守护
- **先决条件**：游戏必须跑在独立的 systemd 服务中，严禁从交互式 shell 中直接启动：
  ```ini
  # /etc/systemd/system/witp-game-en.service
  [Unit]
  Description=WitP-AE (English 1108r9) game instance - isolated cgroup
  After=witp-xvnc98d.service witp-openbox98.service

  [Service]
  Type=simple
  ExecStart=/bin/bash /path/to/witp/automation/witp-launch-en1108.sh
  WorkingDirectory=/path/to/witp/automation
  Environment=DISPLAY=:98
  Restart=no
  KillMode=control-group
  TimeoutStopSec=5
  SendSIGKILL=yes
  ```

---

## 三、怎么使用（完整操作指南）

### 3.1 快速部署与服务启动

1. **克隆项目代码**：
   ```bash
   git clone https://github.com/swanwickk/witp.git /opt/witp
   cd /opt/witp
   ```

2. **配置 Python 虚拟环境**：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **配置参谋部大模型连接**：
   复制并编辑参谋配置文件：
   ```bash
   cp staff/config.yaml.example staff/config.yaml
   # 填入您的大模型 API Base URL、API Key 与主模型名称
   ```

4. **配置环境变量与软链接**：
   ```bash
   sudo ln -sf /opt/witp/bin/witp-cmd /usr/local/bin/witp-cmd
   ```

---

### 3.2 命令行前线工具（witp-cmd）

`witp-cmd` 是指挥官与自动化 Agent 的前线交互中枢，提供了完备的操作子命令：

#### ① 参谋部自检与方案获取
```bash
witp-cmd staff --check         # 参谋部内部健康体检（API/快照新鲜度/存档一致性）
witp-cmd staff --fix           # 自动修复：拉起服务 + 强制重读存档 + 校验
witp-cmd staff --saves         # 枚举可用存档清单（槽位/时间/日期）
witp-cmd staff --save 000      # 召唤参谋部针对最新 Autosave 出具《作战方案建议书》
```

#### ② 自动开局与游戏控制
```bash
WITP_SIDE=allied witp-cmd launch   # 一键以盟军视角启动珊瑚海剧本并就位第 1 回合
WITP_SIDE=japan  witp-cmd launch   # 一键以日军视角启动珊瑚海剧本
witp-cmd save-game --slot 3        # 将当前战局手动存档至槽位 003
witp-cmd status                    # 查看屏幕画面、窗口偏移与活跃编队状态
```

#### ③ 亲手落子与指令下达
```bash
# 编队航路点设置（自动完成解析解计算与邻域校验）
witp-cmd set-dest TF14 100 137

# 战斗机 CAP 比例设定（自动区分舰载机与陆基航空队并完成详情页步进）
witp-cmd set-cap VF-2 60 --alt 15000

# 侦察中队专职化扇面设定
witp-cmd set-search VP-11 100 --arc 315,45
```

#### ④ 推进过回合与因果留痕
```bash
# 单键 E+y 注入推进过回合，并在终局时自动保护截屏
witp-cmd end-turn

# 每回合强制回写因果三元组（S, D, R）
witp-cmd record-turn \
  --decision "双航母前推打击位(100,137)，辅助编队后撤" \
  --result "成功过回合，SBD 击沉敌驱逐舰 2 艘" \
  --orders "TF14->100,137; TF16->100,137"

# 剧本终局战果归档
witp-cmd close-game \
  --outcome "DECISIVE ALLIED VICTORY" \
  --own-score 1086 \
  --enemy-score 2591 \
  --notes "击沉日舰 5 艘并在莫港坚决阻击"
```

---

### 3.3 参谋部系统（Staff Intelligence）

参谋部是系统的核心智囊，运行机制遵循严格的**字典序指挥原则**：
1. **死守莫尔兹比港（98,130）**：第一级目标，绝不以“保航母”为借口避战；
2. **保全主力舰队与航母**：以第一级未失守为前提的从属考量；
3. **猎杀敌方主力航母**：一旦捕捉到确定战机，毫不犹豫全波出击。

运行看板后端：
```bash
python3 staff/kev_server.py --port 18091
```
参谋看板提供可视化 Web 界面（`dashboard/witp-dashboard.html`），可实时监控舰队态势、战损曲线、兵力配比以及因果日志。

---

### 3.4 MCP 服务接入（Agent 智能体直接调用）

本系统完整实现了 MCP（Model Context Protocol）协议。在支持 MCP 的 Agent 环境（如 Hermes Agent、Claude Desktop、Cursor）中，仅需在配置中声明 `witp-ae`：

```yaml
mcpServers:
  witp-ae:
    command: /opt/witp/venv/bin/python3
    args:
      - /opt/witp/mcp-server/server.py
    env:
      WITP_INSTANCE: /root/.wine-witp/drive_c/1108r9
      WITP_DISPLAY: ":98"
      WITP_VNC_PORT: "5902"
    enabled: true
```

#### 核心 MCP 工具一览
- `witp_status`：毫秒级解析当前存档态势，返回 VP 比分、编队旗舰、坐标及任务码。
- `witp_taskforces` / `witp_airgroups` / `witp_ships`：直读舰队、航空中队、舰船全量字段。
- `witp_mem_set_tf_waypoints`：**【零键鼠】**直接向游戏内存写入编队航路点序列。
- `witp_mem_set_airgroup`：**【零键鼠】**直接修改航空队 CAP 百分比、搜索比例与扇面。
- `witp_mem_object_set`：**【零键鼠】**通用对象字段内存修改（支持舰船、基地、地面部队战斗模式）。
- `witp_end_turn`：单键注入 `E → y`，安全等待引擎结算并回读新 Autosave。
- `witp_victory_forecast`：依据手册 ch17 公式计算当前双方 VP 胜负判定等级。
- `witp_weather_report`：9 象限气象数据实时预测。

---

### 3.5 战略知识库与自我迭代机制（SKB）

推演系统的认知进化沉淀于 `knowledge-base/`：
- **`doctrines.md`**：教条库（已有 120 条可证伪实证教条）；
- **`patterns.json`**：战术模式库（水面夜袭、防空圈、阻击走廊等）；
- **`eval_weights.json`**：态势评估与目标选择权重。

指挥官随时可通过命令行追加新提炼的战术教条：
```bash
witp-cmd skb --add "教条正文内容" --confidence 0.85 --evidence "实战依据"
witp-cmd skb          # 查看知识库教条总数与 Git 提交演进历史
```

---

## 四、经典推演与制胜配方实战（以珊瑚海战役为例）

经过数十局的因果迭代，系统在教条 **D11.30 / D11.51~D11.56** 中确立了盟军珊瑚海的**确定性制胜配方**：

1. **双航母开局即前推至 (100,137) 或 (100,138)**：
   - 距莫尔兹比港正向 7~8 格，SBD 俯冲轰炸机恰好覆盖 Milne Bay / Deboyne 群岛南下走廊；
   - **T1~T12 全程坚决驻留此阵位**，持续截杀日军运输船团，将敌登陆部队扼杀在海里；
   - **绝不得因东面虚假情报擅自脱离封锁线**。
2. **同回合把无 CAP 掩护的支援编队（TF15/TF17/TF18）向后方撤至 (99,153)**，脱离敌舰载机靶场。
3. **舰载战斗机（VF-2、VF-5）CAP 统一定为 60%**（攻防平衡点）。
4. **水面夜袭打断卸载（教条 #120）**：
   - 若日军残存船团在 5/8 强行冲滩，TF18 水面突击群必须当夜决死突入 (98,130) 进行夜战炮击，打碎卸载船只，绝不可后撤避战。

---

## 五、项目目录结构

```
witp/
├── README.md                      # 本说明文档
├── LICENSE                        # MIT 开源许可证
├── .gitignore                     # 运行时与缓存忽略规则
├── bin/
│   └── witp-cmd                   # 前线指挥官命令行工具
├── mcp-server/
│   ├── server.py                  # MCP 协议服务端 (70+ 零键鼠工具)
│   └── tests/                     # 自动化端对端测试脚本
├── staff/
│   ├── witp_staff.py              # 参谋部方案推理核心
│   ├── witp_cmd_staffops.py       # 参谋部自愈与回写运维
│   ├── auto_start_coral_sea.py    # 珊瑚海自动开局
│   ├── kev_server.py              # 看板后端 API 服务
│   ├── orchestrator.py            # 推演主循环编排
│   ├── witp_models.py             # 大模型调用封装
│   ├── config.yaml.example        # 参谋部配置模板
│   └── lib/                       # 底层执行、感知、几何计算库
├── reader/
│   ├── witp_read.sh               # 二进制读层入口 (flock原子化保护)
│   ├── detect_side.py             # 顶栏阵营权威检测
│   ├── witp_report.py             # 战报解析引擎
│   ├── witp_summarize.py          # 态势中文简报生成
│   └── pywitpaescraper/           # 32位原生 DLL 存档解析器
├── knowledge-base/
│   ├── doctrines.md               # 120 条推演实证教条库
│   ├── patterns.json              # 战术模式定义
│   └── eval_weights.json          # 战术评估权重
├── skills/                        # Hermes Agent 推演技能集
│   ├── witp-ae-autopilot/         # 参谋指挥联动 SOP
│   ├── witp-ae-control/           # MCP 直控操作指南
│   ├── witp-ae-doctrine/          # 太平洋战争推演教条
│   ├── witp-ae-interface/         # Wine/VNC 与系统层规范
│   ├── witp-ae-manual/            # 游戏官方手册与机制知识库
│   └── witp-ae-save-format/       # pws 二进制格式逆向说明
├── automation/
│   ├── witp-launch-en1108.sh      # 游戏启动守护与崩溃安全出口补丁
│   ├── witp_endgame.py            # 终局模态弹窗捕获与自旋恢复
│   ├── witp_nav.py                # 地图导航与实体定位
│   └── witp_vnckey.py             # VNC 键盘注入
├── docs/                          # 详细逆向报告与手册覆盖表
└── dashboard/                     # Web 可视化仪表盘插件
```

---

## 六、开源许可证

本项目采用 [MIT License](LICENSE) 开源许可证。
欢迎太平洋战争兵棋爱好者、AI 游戏智能体开发者共同探索更强大的自主推演系统！
