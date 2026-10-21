# WitP-AE MCP 逆向与实测报告

> 对象：War in the Pacific: Admiral's Edition（英文 1108r9）
> 路线：**存档二进制读写**（不依赖鼠标点界面）
> 日期：2026-10-18

---

## 一、结论摘要

| 项 | 结果 |
|---|---|
| 存档格式逆向 | ✅ 完成（gzip + 逐记录 zlib + 固定结构体） |
| 读层（纯 Python） | ✅ 0.15 秒/档，不依赖游戏 DLL |
| 写层（命令注入） | ✅ 12 类命令面可用，写后引擎可读 |
| MCP 服务 | ✅ 14 个工具，default / witp 两 profile 已注册 |
| 手册覆盖 | **37%**（38 条命令面：12 已实现 / 2 部分 / 24 未实现） |
| 完整回合闭环 | ✅ 读态势→下命令→过回合→核对，实测通过 |

---

## 二、容器格式（已逐字节验证）

```
.pws = gzip头(10B) + raw deflate(wbits=-15) + crc32(4B) + 原始长度(4B)
记录串 = { [u16 实例号][u16 记录类型][u32 A][u32 B][zlib流] } × N
```

- 外层是 **raw deflate**，不是 zlib 包装（用 `zlib.compress()` 会多 2 字节头）
- 记录体内层是 zlib（wbits=15）
- 小记录（id<1000）A/B = 解压长度/压缩长度；大记录 A/B 是引擎校验字段，**改动会让 pwsdll 崩溃**

### 解压长度 → 结构体

| 长度 | 结构 | 槽数 | 单槽 |
|---|---|---|---|
| 3000 | 存档头 | — | — |
| 99696 | 剧本块 | — | — |
| 9280000 | PWSShip | 20000 | 464B |
| 9000000 | Leader/Pilot | 50000 | 180B |
| 20400680 | PWSAirGroup | 30001 | 680B |
| 21096000 | PWSLocation | 18000 | 1172B |
| 2224000 | PWSTaskGroup | 4000 | 556B |
| 396000 | PWSAircraft | 1000 | 396B |
| 472000 | PWSDevice | 2000 | 236B |
| 1900000 | PWSShipClass | 5000 | 380B |

---

## 三、写档硬门槛（本次逆向最大障碍）

引擎**逐条校验压缩流长度**，长度变 1 字节即报 `Restore size larger than expected` 并中断读档。

**解法：压缩到精确长度**

```
Z_SYNC_FLUSH 后追加：
  空存储块 5B: 00 00 00 FF FF  (BFINAL=0)
  末块     5B: 01 00 00 FF FF  (BFINAL=1)
  空固定哈夫曼块 2B: 03 00
约束: rest = target - len(body) - 4
      rest % 5 == 0（stored）或 (rest-2) % 5 == 0（fixed）
      rest < 5 无解
```

**三级抖动**（让正文长度落到合适余数）：
1. 参数网格 `level × memLevel × windowBits × strategy`
2. 分段 `Z_SYNC_FLUSH`（1 字节粒度）
3. 填充区残留非零字节清零（实测清 26~36 字节即命中）

**验证**：重打包主实例 `wpae000.pws`（982340B）**字节级完全一致**。

---

## 四、命令字段偏移（全部经引擎回读 + 游戏界面验证）

### PWSTaskGroup（556B）
```python
TF_OFF = dict(
    flagship=44,      # i32 旗舰舰船 id
    home=54,          # u16 母港 Location id
    destBase=58,      # u16 目的基地 id（★仅缓存，改它无效）
    wp=118,           # 航路点数组起点，40 × (u16 x, u16 y)
    wpCount=320,      # u16 有效点数 ★必须写
    wpAlloc=322,      # u16 缓冲区长度 ★必须写
    mission=349,      # u8  任务码
    speed=354,        # u8  速度档
)
```

**★核心教训**：设置目的地必须**同步写路径数组 + wpCount + wpAlloc**。
只改 `destBase`(58) 无效；只改末航路点会被引擎重算覆盖；只改 wpCount 不写 wpAlloc 也会回退。

实测对照（游戏自己设目的地产生的存档）：
| | destBase | wpCount | wpAlloc |
|---|---|---|---|
| 原始（莫港 98,130） | 981 | 19 | 36 |
| 游戏设（99,127） | 0 | 11 | 21 |

### PWSAirGroup（680B）
```python
AG_OFF = dict(
    baseID=40, primary=44, secondary=46, targetID=48,
    targetX=192, targetY=196, alt=212,
    pctCAP=560, pctLRCAP=561, pctASW=562,
    pctSearch=563, pctTrain=564, pctRest=565,
    aswArcStart=628, aswArcEnd=629,
    navArcStart=630, navArcEnd=631,
)
```

### PWSLocation（1172B）
```python
LOC_OFF = dict(
    X=36, Y=38, prep=104, combatMode=110,
    portExpand=424, airfieldExpand=428, fortExpand=432,
    marchDir=651, marchLen=652, destX=662, destY=664,
)
```

### combatMode 枚举（差分实证）
`0=defend 1=bombardment 2=deliberate 3=shock`

---

## 五、MCP 工具清单（14 个）

### 读（7）
| 工具 | 说明 |
|---|---|
| `witp_status` | 态势摘要（日期/剧本/VP/编制数） |
| `witp_taskforces` | 编队列表（任务/位置/目的地/航路点） |
| `witp_airgroups` | 航空队（驻地/任务/比例/高度/扇面/士气） |
| `witp_bases` | 基地（港口/机场/要塞+SPS+扩建%/补给） |
| `witp_ground_units` | 地面部队（番号/位置/战斗命令/准备度/行军） |
| `witp_saves` | 存档列表 |
| `witp_reports` | 战报文本（GBK 自动转 UTF-8） |

### 写（4，均带 `engine_verify` 引擎回读）
| 工具 | 能力 |
|---|---|
| `witp_set_tf_orders` | 任务 + 目的地 + **显式航路点** `"x1,y1;x2,y2;..."` |
| `witp_set_airgroup_orders` | 主任务/目标/6 种比例/高度/搜索扇面 |
| `witp_set_ground_orders` | 战斗命令/行军目的地/准备目标 |
| `witp_set_base_build` | 港口/机场/要塞扩建 |

### 交互（3）
| 工具 | 说明 |
|---|---|
| `witp_screen` | 截图 + 顶栏 OCR |
| `witp_game_key` | 白名单按键（t/a/b/n/esc/space） |
| `witp_end_turn` | 过回合（按 E → 点 YES → 等 autosave） |

---

## 六、完整回合闭环实测

**环境**：独立测试实例（`:97` / VNC 5901 / 独立 WINEPREFIX），不影响主实例 `:98`

| 步 | 动作 | 结果 |
|---|---|---|
| 1 | 读态势 | 1942-05-04 珊瑚海第 1 回合，日军视角 |
| 2 | 写 TF7：任务→SURFACE，目的地→(99,126) | `ok=true` `engine_verify.ok=true` |
| 3 | 写 AG9：search=60，alt=12000 | 同上 |
| 4 | 载入游戏，界面核对 | 编队表显示 `Surface Combat` |
| 5 | `witp_end_turn` | `ok=true`，120 秒，新 autosave 生成 |
| 6 | 读新档核对 | **日期 05/04→05/05，turn 1→2** |
| 7 | 命令保留核对 | TF7 mission=AMPHIB ✅；**目的地 (99,127) 保留** ✅；AG9 search=60 / alt=12000 ✅ |

> 注：任务在步骤 6 显示 AMPHIB 是因该轮又下了一次 AMPHIB 命令，非回退。

**地面战斗命令**：过回合后被重置为 `defend`。查手册 8.2.1.2 确认——**无敌军时不允许攻击令**，属游戏规则而非工具缺陷。

### 最终端到端验收（MCP 真实调用）

```
1 态势: Autosave Date: 05/05/42 turn 2 VP {'japan': 149, 'allied': 1066}
2 编队: 29 | TF7: AMPHIB
3 航空队: 40
4 拉包尔: port=3(5) af=3(6) exp=5/5/5
5 写TF7: ok=True engine=True
   路径: [[106,125],[105,128],[103,128],[101,127],[99,126]]
```

14 个工具全部对外暴露（`ListTools` 实测），default 与 witp 两个 profile 均 `✓ enabled`。

---

## 七、本次修掉的真实缺陷

| # | 缺陷 | 后果 | 修法 |
|---|---|---|---|
| 1 | MCP 子进程 stdout 未捕获 | VNC 点击脚本的 `print` 污染 JSON-RPC 通道，会话断链 | 统一 `_run()` 封装，强制 `capture_output` |
| 2 | 测试实例前缀无 `C:\py32` | `engine_verify` 静默失败，一直返回 false | `_py32_prefix()` 自动回退到装 py32 的前缀 |
| 3 | 航路点只标定 8 个 | 实际 40 个，写入被截断 | 改 `wpMax=40` + 按 `wpCount` 读取 |
| 4 | 目的地只改末航路点 | 引擎结算时重算覆盖 | 同步写 路径数组+wpCount+wpAlloc |
| 5 | 读层按 `type` 取记录 | 游戏重写存档后航空队 type 20→33，`KeyError` | 改按**解压长度**索引 |
| 6 | `set_tf_mission` 被误删 | `AttributeError` | 补回 |
| 7 | `witp_set_ground_orders` 缺 `engine_verify` | 写入无法验证 | 补齐 |

---

## 八、已知未解 / 风险

1. **`operationsMode`(offset 906) 语义未解** —— 全部 41585 条记录均为 0，无法通过界面操作触发变化，**主动不写**
2. **`destBase`(58) 是缓存** —— 只能读不能作为命令源，容易误判（已写入覆盖表警示）
3. **地面部队 slot 与 Location slot 混用** —— 同一存档里 `6062` 既是"盟军莫港"又是"地面部队编号"的取值区间，命令前必须核对 `owner`
4. **测试实例存档槽位会漂移** —— 存档对话框点行左箭头时行偏移可能差 1，存到相邻槽

---

## 九、复现命令

```bash
# 引擎回读校验（复制即用）
export WINEPREFIX=/root/.wine-witp HOME=/root LANG=zh_CN.GBK DISPLAY=:97
wine C:\\py32\\python.exe 'Z:\root\.hermes\workspace\witp-reader\dllverify.py' \
  'Z:\tmp\xxx.pws' --tf 7 --ag 9

# MCP 闭环测试
cd /root/.hermes/mcp-servers/witp-mcp
/root/.hermes/hermes-agent/venv/bin/python3 test_loop_d.py
```

---

## 十、相关文件

| 路径 | 用途 |
|---|---|
| `/root/.hermes/profiles/witp/workspace/witp-reader/pwsfile.py` | 容器解析 |
| `/root/.hermes/profiles/witp/workspace/witp-reader/pwspack.py` | 打包 + 精确长度压缩 |
| `/root/.hermes/profiles/witp/workspace/witp-reader/witp_core.py` | 纯 Python 读层 |
| `/root/.hermes/profiles/witp/workspace/witp-reader/witp_orders.py` | 命令写层 |
| `/root/.hermes/profiles/witp/workspace/witp-reader/dllverify.py` | 引擎回读校验 |
| `/root/.hermes/mcp-servers/witp-mcp/server.py` | MCP 服务（14 工具） |
| `/root/.hermes/profiles/witp/workspace/witp-mcp-手册覆盖表.md` | 手册逐条对照 |
