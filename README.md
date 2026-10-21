# WitP-AE Autonomous Commander & Neural Staff System
> 《太平洋战争：海军上将篇》（War in the Pacific: Admiral's Edition）通用自动化作战参谋与智能指挥系统

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Wine-orange.svg)](#二在什么环境下使用)
[![Game](https://img.shields.io/badge/Game-WitP--AE%201108r9-green.svg)](#22-游戏本体与运行模式)
[![Protocol](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-purple.svg)](#34-mcp-服务协议接入)

---

> ⚠️ **重要测试现状说明**：
> 本项目的底层内存直控、存档解析读写与 AI 参谋部推理架构均采用战区通用型设计。**但目前仅对官方《珊瑚海》（Scenario 003: The Battle of the Coral Sea）战役剧本进行过实机自动化推演与完整闭环测试**。其他剧本（如大战略战役、中途岛、瓜达尔卡纳尔等）在底层数据结构与控制指令上通用，但涉及更大的地图跨度、基地规模与特殊编制，尚待后续进一步扩展实测与几何标定。

---

## 目录
- [一、这是什么（系统介绍）](#一这是什么系统介绍)
  - [1.1 系统定位与核心价值](#11-系统定位与核心价值)
  - [1.2 核心支柱与技术架构](#12-核心支柱与技术架构)
  - [1.3 通用作战参谋部特性（战术完全解耦）](#13-通用作战参谋部特性战术完全解耦)
- [二、在什么环境下使用（运行环境与前置依赖）](#二在什么环境下使用运行环境与前置依赖)
  - [2.1 基础系统与依赖栈](#21-基础系统与依赖栈)
  - [2.2 游戏本体与运行模式](#22-游戏本体与运行模式)
  - [2.3 关键系统补丁（音效崩溃规避与 cgroup 隔离）](#23-关键系统补丁音效崩溃规避与-cgroup-隔离)
- [三、怎么使用（完整操作指南）](#三怎么使用完整操作指南)
  - [3.1 快速部署与初始化](#31-快速部署与初始化)
  - [3.2 命令行前线工具（witp-cmd）](#32-命令行前线工具witp-cmd)
  - [3.3 参谋部推演系统（Staff Intelligence）](#33-参谋部推演系统staff-intelligence)
  - [3.4 MCP 服务协议接入（AI Agent 工具调用）](#34-mcp-服务协议接入ai-agent-工具调用)
  - [3.5 决策因果日志机制（Causal Logging）](#35-决策因果日志机制causal-logging)
- [四、项目目录结构](#四项目目录结构)
- [五、开源许可证](#五开源许可证)

---

## 一、这是什么（系统介绍）

### 1.1 系统定位与核心价值
《War in the Pacific: Admiral's Edition》（WitP-AE）是硬核兵棋推演的标杆级作品，全图涵盖数以万计的真实舰船、航空中队、基地设施、后勤网络与海空战斗结算。

本项目是面向 WitP-AE 的**通用自动化指挥与 AI 作战参谋框架**。它通过逆向底层二进制数据与内存映射，彻底解耦传统脆弱的屏幕点击，提供毫秒级、零键鼠的游戏状态读写通道，并基于大语言模型（LLM）构建战术可自由配置的通用参谋推理引擎。

### 1.2 核心支柱与技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│                   LLM Commander & AI Agent                       │
└──────────────┬───────────────────────────────────┬───────────────┘
               │                                   │
      [下达战术决策/自由意图]                 [感知态势/研判方案]
               ▼                                   ▲
┌──────────────────────────────┐   ┌──────────────────────────────┐
│     前线操作手 (witp-cmd)      │   │   通用参谋部 (witp_staff.py)   │
│  - 编队航路点内存直写        │   │  - 多维交战威胁客观评估      │
│  - 航空防空分层与扇面设定    │   │  - 动态锚点与机动阵位核算    │
│  - 单键 E+y 注入推进回合     │   │  - 专职化海空侦察网络构建    │
└──────────────┬───────────────┘   └──────────────▲───────────────┘
               │                                   │
      [T1 内存直控 / T2 键盘]             [二进制读层 / 战报解析]
               ▼                                   │
┌──────────────────────────────────────────────────┴──────────────┐
│               WitP-AE 运行时底层 (Wine 1108r9)                   │
│  • .pws 存档二进制流解析 (gzip + raw deflate + zlib)             │
│  • 进程内存双镜像实时读写 (PWSTaskGroup / PWSAirGroup / Ship)    │
│  • 终局模态弹窗自动 OCR 评分与自旋防护 (witp_endgame.py)         │
└─────────────────────────────────────────────────────────────────┘
```

1. **T1 内存直控与二进制读写（Zero-GUI Direct Control）**：
   - 彻底逆向 WitP-AE 的 `.pws` 数据流结构与进程内存映射，实现编队航路点（Waypoints）、航空队主次任务、CAP 防空比例、搜索扇面、地面部队战斗模式的**内存毫秒级直接修改**；
   - 包含双镜像同步与校验机制，杜绝游戏存档覆盖冲突与数据脏化。
2. **T2 极简按键单键推进（Single-Key Turn Advance）**：
   - 依托标准 RFB 键盘通道，以极简的 `E → y` 单键指令完成回合推进，配合全屏哈希变化校验与终局画面拦截保护，告别任何鼠标拖曳。
3. **通用作战参谋系统（Neural Staff Intelligence）**：
   - 参谋部为纯通用代码实现，不预设、不绑定任何特定剧本的固定战术；
   - 指挥官可通过配置自主定义战略重心、交战规则与优先级，参谋部据此进行战场态势研判并出具结构化的《作战方案建议书》。
4. **决策因果三元组留痕（Causal Logging）**：
   - 逐回合记录 $(S, D, R)$（态势认知、决策意图、实际战果），为战役复盘与推演分析提供结构化数据支撑。

### 1.3 通用作战参谋部特性（战术完全解耦）
**参谋部是一个通用的战役决策与方案生成中枢，具体的战术风格完全由使用者掌控：**
- **战术完全解耦**：系统内部不写死特定剧本的死守、决死突击或绝对避战等战术规则。每个指挥官的战术偏好和战略重点各不相同，参谋部提供的是客观的态势研判、兵力统计、威胁圈计算与侦察网规划。
- **自定义战略指导**：支持通过配置文件（`config.yaml`）或环境变量（`WITP_COMMANDER_PRIORITY`）动态注入指挥官的作战指导原则（如重点防御核心基地、优先保全主力航母、积极寻找水面夜袭战机等），参谋部在评估出击代价与航线规划时将严格以此为导向。
- **专职化侦察体系**：根据侦察机种性能（远程巡逻机、舰载侦察机、近距水上机）自动计算最优对海搜索扇面与反潜配比，杜绝全向摊薄。

---

## 二、在什么环境下使用（运行环境与前置依赖）

### 2.1 基础系统与依赖栈
- **操作系统**：Linux x86_64（Ubuntu 22.04 / 24.04 LTS 或 Debian 12 验证通过）。
- **Python 环境**：
  - **宿主环境**：Python 3.10+（运行 MCP 服务端、参谋部推理系统、前线 CLI）。
  - **Wine 虚拟子环境**：内置 32 位 Python 3.11（`C:\py32\python.exe`，用于调用游戏原生 `pwsdll.dll` 解析器）。
- **系统工具包**：
  ```bash
  sudo apt-get update && sudo apt-get install -y \
      wine wine32 wine64 \
      tigervnc-standalone-server x11vnc openbox \
      xdotool imagemagick tesseract-ocr tesseract-ocr-eng \
      git curl jq
  ```

### 2.2 游戏本体与运行模式
- **必须采用官方原版英文 1108r9**：
  - 严禁使用第三方汉化版 EXE（汉化版写入存档时原生 `pwsdll.dll` 会报 `-5` 解密校验失败）。
- **分辨率与桌面规范**：
  - 原生游戏分辨率为 **1024x768**；
  - 虚拟桌面（Xvnc）推荐配置为 `1400x1050x24` 或 `1024x768x24`；
  - **必须运行 Openbox 窗口管理器**：Wine 依赖窗口管理器分配按键焦点，缺失 Openbox 将导致按键静默丢失。

### 2.3 关键系统补丁（音效崩溃规避与 cgroup 隔离）

#### ① quartz.dll 二进制规避补丁（根治随机段错误）
- **现象**：游戏自带音效解码组件 `witprec.exe` 在 Wine 环境下运行 1.5~3.5 小时后必报 `filesource.c:397` 越界断言并发生段错误崩溃。
- **解法**：启动脚本 `automation/witp-launch-en1108.sh` 内置安全出口补丁，将越界跳转重定向至安全释放分支，实现百小时长效稳定运行。

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

### 3.1 快速部署与初始化

1. **克隆项目代码**：
   ```bash
   git clone https://github.com/swanwickk/witp.git /opt/witp
   cd /opt/witp
   ```

2. **配置 Python 虚拟环境与依赖**：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **配置参谋部大模型连接（可选）**：
   ```bash
   cp staff/config.yaml.example staff/config.yaml
   # 填入您的大模型 API Base URL、API Key 与主模型配置
   ```

4. **配置命令行快捷方式**：
   ```bash
   sudo ln -sf /opt/witp/bin/witp-cmd /usr/local/bin/witp-cmd
   ```

---

### 3.2 命令行前线工具（witp-cmd）

`witp-cmd` 提供了开箱即用的指挥官操作集合：

#### ① 参谋部自检与方案获取
```bash
witp-cmd staff --check         # 参谋部服务健康体检（API/快照新鲜度/存档一致性）
witp-cmd staff --fix           # 自动修复：拉起服务 + 强制重读存档
witp-cmd staff --saves         # 枚举当前游戏目录下的可用存档清单
witp-cmd staff --save 000      # 召唤参谋部针对最新 Autosave 产出《作战方案建议书》
```

#### ② 自动开局与游戏控制
```bash
WITP_SIDE=allied witp-cmd launch   # 以盟军视角一键启动战役剧本并进入第 1 回合
WITP_SIDE=japan  witp-cmd launch   # 以日军视角一键启动战役剧本
witp-cmd save-game --slot 3        # 将当前战局手动存档至槽位 003
witp-cmd status                    # 查看当前屏幕画面与战局状态
```

#### ③ 亲手落子与指令下达
```bash
# 编队航路点设置（自动执行邻域校验）
witp-cmd set-dest TF14 100 137

# 战斗机 CAP 防空比例设定
witp-cmd set-cap VF-2 60 --alt 15000

# 侦察中队对海搜索比例与扇面设定
witp-cmd set-search VP-11 100 --arc 315,45
```

#### ④ 推进过回合与因果留痕
```bash
# 单键 E+y 注入推进过回合，并在终局画面时自动保护截屏
witp-cmd end-turn

# 每回合回写因果记录（态势、决策、战果）
witp-cmd record-turn \
  --decision "主力舰队就位封锁线，辅助编队后撤" \
  --result "成功过回合，阻击敌先头部队" \
  --orders "TF14->100,137; TF16->100,137"

# 终局战果台账归档
witp-cmd close-game \
  --outcome "DECISIVE VICTORY" \
  --own-score 1200 \
  --enemy-score 300 \
  --notes "达成战役全歼目标"
```

---

### 3.3 参谋部推演系统（Staff Intelligence）

参谋部负责全局感知与战术方案推演：
- **方案包含板块**：
  1. 战场客观态势与威胁研判（按红/黄/绿标示前沿交战区、交通线与后方基地）；
  2. 核心战略意图与侦察指导；
  3. 己方兵力与战损态势（航母完好度、其他舰种构成）；
  4. 推荐行动清单（含目标编队、动作类型、坐标参数与置信度）。
- **运行看板 API**：
  ```bash
  python3 staff/kev_server.py --port 18091
  ```
  可通过浏览器打开 `dashboard/witp-dashboard.html` 查看推演大屏。

---

### 3.4 MCP 服务协议接入（AI Agent 工具调用）

本系统完整实现了 MCP（Model Context Protocol）标准。在支持 MCP 的 Agent 环境（如 Hermes Agent、Claude Desktop、Cursor）中，只需配置服务入口：

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

#### 常用核心 MCP 工具
- `witp_status`：毫秒级解析当前存档态势，返回双方 VP、编队旗舰、坐标及任务码。
- `witp_taskforces` / `witp_airgroups` / `witp_ships`：直读舰队、航空中队、舰船全量内存字段。
- `witp_mem_set_tf_waypoints`：**【零键鼠】**直接向游戏内存写入编队航路点序列。
- `witp_mem_set_airgroup`：**【零键鼠】**修改航空队 CAP 百分比、搜索比例与扇面。
- `witp_mem_object_set`：**【零键鼠】**通用对象字段内存修改（支持舰船、基地、地面部队战斗模式）。
- `witp_end_turn`：单键注入 `E → y`，安全等待引擎结算并回读新 Autosave。
- `witp_victory_forecast`：依据手册 ch17 公式实时推演胜负判定等级。
- `witp_weather_report`：9 象限气象数据实时预测。

---

### 3.5 决策因果日志机制（Causal Logging）

系统鼓励以结构化数据追踪决策演进：
- 每一回合操作均沉淀为因果记录 JSON（包含时间、回合数、前置态势、决策动作与次日战报结算反馈）；
- 为多局对照分析、战术对比与策略优化提供可信、可复现的事实依据。

---

## 四、项目目录结构

```
witp/
├── README.md                      # 本说明文档
├── LICENSE                        # MIT 开源许可证
├── requirements.txt               # Python 依赖清单
├── .gitignore                     # 运行时临时文件与缓存忽略
├── bin/
│   └── witp-cmd                   # 指挥官前线命令行中枢工具
├── mcp-server/
│   ├── server.py                  # MCP 协议服务端（70+ 零键鼠与内存工具）
│   └── test_*.py                  # 自动化端对端测试套件
├── staff/
│   ├── witp_staff.py              # 通用参谋部方案推理核心
│   ├── witp_cmd_staffops.py       # 参谋部自愈与回写运维模块
│   ├── auto_start_coral_sea.py    # 战役自动化启动器
│   ├── kev_server.py              # 看板后端 API 服务
│   ├── orchestrator.py            # 推演主循环编排
│   ├── witp_models.py             # 参谋大模型调用封装
│   ├── config.yaml.example        # 参谋部配置模板（已脱敏）
│   └── lib/                       # 底层执行、感知、几何计算核心库
├── reader/
│   ├── witp_read.sh               # 存档读层入口（flock 进程锁与原子切换）
│   ├── detect_side.py             # 顶栏阵营权威检测
│   ├── witp_report.py             # 战报解析引擎
│   ├── witp_summarize.py          # 态势中文简报生成
│   └── pywitpaescraper/           # 32 位原生 DLL 存档解析器
├── skills/                        # Hermes Agent 推演技能集
│   ├── witp-ae-autopilot/         # 参谋指挥联动 SOP
│   ├── witp-ae-control/           # MCP 直控操作规范
│   ├── witp-ae-doctrine/          # 太平洋战争推演通用原则
│   ├── witp-ae-interface/         # Wine/VNC 与系统层规范
│   ├── witp-ae-manual/            # 游戏官方手册与机制知识库
│   └── witp-ae-save-format/       # pws 二进制格式逆向说明
├── automation/
│   ├── witp-launch-en1108.sh      # 游戏启动守护与崩溃安全出口补丁
│   ├── witp_endgame.py            # 终局模态弹窗捕获与自旋恢复
│   ├── witp_nav.py                # 地图导航与实体定位
│   └── witp_vnckey.py             # VNC 键盘注入
├── docs/                          # 详细逆向分析报告与手册覆盖表
└── dashboard/                     # Web 可视化仪表盘插件
```

---

## 五、开源许可证

本项目采用 [MIT License](LICENSE) 开源许可证。
欢迎全球太平洋战争兵棋爱好者、AI 游戏智能体与决策智能研究者共同参与贡献！
