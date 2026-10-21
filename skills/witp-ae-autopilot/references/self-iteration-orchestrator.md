# 来自 default profile 的补充记录：witp-ae-autopilot

> 这份内容原先只存在于 default profile 的同名技能里，witp profile 副本没有。
> 迁移时整份保留，作为历史实测记录/架构说明参考。使用时以 vitp profile 的
> SKILL.md 为准；本文件若与其冲突，以 SKILL.md 为准。

---

---
name: witp-ae-autopilot
description: "Use when orchestrating WitP-AE self-iteration: commanding the staff, targeting a save, writing back."
version: 2.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [witp, wargaming, self-iteration, ai-agent, orchestrator, skb]
    category: wargaming
---

# WitP-AE 自我迭代推演与编排 SOP

本技能用于运维和控制位于 `/root/.hermes/profiles/witp/witp-agent/` 的 WitP-AE 自我迭代智能体系统。

> **两份副本**：witp profile 内另有专属副本 `/root/.hermes/profiles/witp/skills/wargaming/witp-ae-autopilot/`（实际推演会话读的是那份）。`skill_manage` 只作用于默认 profile 这一份；要改 witp profile 的副本必须直接写文件。两边容易漂移，改动后留意同步。

> **权属**：推演的操作手**只限 witp profile 会话内的主 Agent**。默认 profile 只做系统开发与运维，不碰游戏、不杀游戏进程、不注入 VNC 动作。

---

## 核心架构与目录资产

```
/root/.hermes/profiles/witp/witp-agent/
├── config.yaml          # 云 API 与游戏/Kev 运行时配置（热重载）
├── orchestrator.py      # 三层闭环主编排器
├── start_kev.sh         # 本地 Kev-0.8B System 1 决策模型启动脚本
├── skb/                 # 战略知识库（Git 版本控制）
│   ├── doctrines.md     # 高层战略教条（自然语言）
│   ├── patterns.json    # 战术触发-响应模式（结构化模板）
│   └── eval_weights.json # 局面评估多维权重
├── games/               # 对局归档
│   └── game-XXX/
│       ├── memory.json  # 跨回合对局记忆
│       ├── belief.json  # 定性威胁图谱快照
│       └── causal_log/  # 逐回合因果三元组 (S, D, R) JSON
└── lib/                 # 核心计算与执行库
    ├── hex_math.py      # 六角格距离/航程/坐标映射
    ├── fuel_calc.py     # 燃油余量与续航判定
    ├── option_builder.py# 战术闭集选项构建
    ├── verify.py        # 意图落地核验与漂移检测
    ├── belief_update.py # 定性信念更新引擎
    ├── perception.py    # 读层封装 S_t
    └── executor.py      # RFB/VNC 语义命令执行
```

---

## 铁律一：参谋部是下属单位，不是可选顾问

前线主 Agent（唯一的手）与参谋工具（`witp-cmd staff`、`witp_staff.py`、18091 看板）是**指挥关系**，参谋部是下级参谋单位。

- 参谋产出不合格时的正确动作是**命令重做 → 诊断根因 → 修复 → 复验**，绝不是「自己扛枪上阵」绕过它。
- **每回合强制流程**：`staff --check` →（不健康）`staff --fix` → 重新 `--check` → 取方案 → 执行 → `record-turn` 回写。
- 只有修复失败**且已向用户报告**后才允许降级自主决策，且必须在产出中写明「参谋部故障，本次为降级自主决策」。**严禁静默单干。**
- **不得把「参谋部有点小毛病」当作绕过它的理由**：先查 `references/data-pipeline.md` 的故障对照表——绝大多数是数据管道问题（读到过期存档、锁残留、字段名取错），不是参谋部本身故障。绕过之前先修。

## 铁律二：参谋读哪份存档由指挥官指定

参谋部**不得自行猜测**该读哪份存档；不指定时按 mtime 取最新只是兜底。

| 存档 | 语义 |
|---|---|
| `wpae000.pws` | Autosave —— 结算后**新状态**（当前局面） |
| `wpae002.pws` | PreTurnSave —— 结算前**旧状态**（上一回合） |
| `wpae003.pws` | 手动存档槽 |

```bash
witp-cmd staff --saves                          # 枚举（槽位/时间/日期/语义）
witp-cmd staff --save 000                       # 指定读当前局面
witp-cmd staff --save 002                       # 指定读上一回合（对比用）
witp-cmd staff --save /abs/path/wpae003.pws     # 绝对路径亦可
```

- 底层通道：`GET /saves`、`POST /refresh-state {"save":"000"}`、`witp_staff.py brief --save/--saves`。
- 指定不存在的存档会**明确报错**，不静默回退；报错后先 `--saves` 核对槽位。
- 提案书首部打印**数据来源存档**，用它核对参谋部实际读了哪一份。

## 铁律三：回写是自我迭代的判定标准

参谋部**只读不回写**等于自我迭代没有发生。每回合与每局必须回写：

```bash
witp-cmd record-turn --game <id> --decision ... --result ... --orders ...   # 逐回合因果三元组 (S,D,R)
witp-cmd close-game  --game <id> --outcome ... --enemy-score N --own-score N # 局末归档战果 + 台账
witp-cmd skb --add "<教训>"                                                  # 追加教条并自动 git 提交
witp-cmd skb                                                                 # 查看知识库与提交历史
```

- **判定标准**：一局打完若 `witp-cmd skb` 的提交次数没有增加，则本局的「自我迭代」视为**未发生**。
- 战果数据只能来自游戏与前线会话，**严禁代为编造比分或胜负**。

---

## 常用运维与执行命令

### 1. 单回合推演测试
```bash
python3 /root/.hermes/profiles/witp/witp-agent/orchestrator.py
```
- 自动读取当前原生存档与战报；
- 结合定性威胁图谱与 SKB 教条生成意图；
- 下发语义级战术订单并核验；
- 输出并保存因果三元组至 `games/<game_id>/causal_log/turn_XX.json`。

### 2. 检查与配置云 API（多 Provider 池化与动态拉取）
查看或修改 `/root/.hermes/profiles/witp/witp-agent/config.yaml`。支持 Hermes Studio 式多 Provider 管理：
```yaml
strategy_model:
  provider_id: "硅基流动"
  model: "deepseek-ai/DeepSeek-V4-Flash"
  base_url: "https://api.siliconflow.cn/v1"
  api_key: "sk-..."

providers_pool:
  - id: "gg"
    name: "gg"
    base_url: "https://gcli.ggchan.dev/v1"
    api_key: "gg-..."
    models: ["agy-claude-sonnet-4-6", "gemini-2.5-pro"]
  - id: "硅基流动"
    name: "硅基流动"
    base_url: "https://api.siliconflow.cn/v1"
    api_key: "sk-..."
```
- **动态获取模型列表**：看板提供 `/providers/fetch-models` 接口，自动携带 API Key 远程调用 `{base_url}/models`，返回全部可用模型供下拉单选。
- **热生效机制**：编排器在每回合开始时会自动重读 `strategy_model`，随时热生效，无需重启服务。

### 3. 查看与更新战略知识库 (SKB)
```bash
cd /root/.hermes/profiles/witp/witp-agent/skb
git log --oneline --graph
git status
```
当复盘提炼出新的教训后：
1. 编辑 `doctrines.md` 或 `patterns.json`；
2. 提交更新：`git commit -am "局末复盘：增补第X条教条"`。

### 4. 本地 Kev-0.8B 决策服务 (System 1)
```bash
systemctl status witp-kev.service
```
- 服务端口：`18090`，以 systemd 守护进程常驻（`witp-kev.service`）；
- 协议遵循 TypeSafe System One（`POST /v1/systemone`，`GET /v1/models`）；
- 支持 Choice（候选 Hex 与任务 Softmax 置信度判定）、Score（威胁评分）、Noul（布尔规则/油料校验），毫秒级响应；
- **若看板显示 Kev「待命」**：说明 18090 端口未监听，执行 `systemctl restart witp-kev.service` 即可。

### 5. 后台 API 看板服务与公网访问
```bash
systemctl status witp-dashboard.service
```
- 端口 `18091`，提供完整的 REST 控制端点及静态页面；
- **公网专属安全域名**：`https://witp-agent.swanwick.site`（走 Cloudflare Tunnel 穿透至 18091）；
- **HTTPS 混合内容铁律**：严禁在 HTTPS 前端页面中请求 `http://...:18091`（会被浏览器直接拦截 Mixed Content 导致按钮点击无反应），所有 API 调用必须走同源或 `https://witp-agent.swanwick.site`。
