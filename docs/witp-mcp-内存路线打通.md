# WitP-AE 内存路线：零键鼠操作游戏（已完整打通）

> 2026-10-18 实测完成。TF / 航空队 / 基地 三类对象全部验证通过。

## 结论

**不碰键盘鼠标，直接读写游戏进程内存下达命令，引擎会采纳并持久化到存档。**

最终验收（同一回合内纯内存写入，过一回合后引擎自己写的存档里）：

| 对象 | 字段 | 写入 | 存档结果 |
|---|---|---|---|
| TF7 | mission | AMPHIB(15) | **15** ✓ |
| TF7 | speed | Full(1) | **1** ✓ |
| AG6 | pctCAP | 100 | **100** ✓ |
| AG3 | pctSearch | 100 | **100** ✓ |
| LOC27 | prep | 90 | **91** ✓（回合推进 +1） |
| LOC27 | operationsMode | combat(2) | **2** ✓ |

---

## 一、四个致命坑（每一个都会让人误判"路线不可行"）

### 坑 1：gdb 读内存静默返回全零

```python
gdb -p <pid> -batch -ex "dump binary memory /tmp/x.bin 0xADDR 0xEND"
```

目标页未映射时，gdb **不报错**，直接写一个全零文件。于是"读到零"和"读不到"无法区分。

**修法**：用 `/proc/<pid>/mem`，未映射返回 `EIO`。

```python
os.lseek(fd, addr, os.SEEK_SET)
data = os.read(fd, n)      # 未映射 → OSError
```

### 坑 2：扫错地址区间

真实数据在 `0x0085f000-0x0f0a7000`（232MB 可写段）。
扫 `0x1000000-0x2600000` 是未映射区，配合坑 1 就是稳定读到全零。

**修法**：从 `/proc/pid/maps` 枚举实际可写段。

### 坑 3：记录类型码不可靠

`id % 256` **不是**稳定类型码——实例号进位会污染低位。

实测：同一条 LOCATION 记录
- `wpae001.pws` 里 `id=0x110021` → `low8=33`
- `wpae000.pws` 里 → `low8=19`

**只有解压长度恒定**。所有按类型取记录的地方必须改用 `u_len`：

```python
REC_BY_LEN = {
    2224000: "TASKGROUP",    # 556 x 4000
    20400680: "AIRGROUP",    # 680 x 30001
    21096000: "LOCATION",    # 1172 x 18000
    9280000: "SHIP",
    9000000: "LEADER/PILOT",
}
```

已封装为 `pwsfile.record_by_len(path, ulen)`。

### 坑 4：航空队有**两份**副本，只有一份被引擎采纳

```
copyA  0x59904e8 起 —— 只影响界面显示
copyB  0xbba0c20 起 —— 引擎存盘时读这份
```

只改 copyA → 界面变但过回合后存档不变（**假成功**）。
两份都改 → 存档生效。

TF 只有一份，所以 TF 改完立即生效。这是 TF 与 AG 的关键区别。

---

## 二、三类对象的真值

### TF 数组

| 项 | 值 |
|---|---|
| 基址 | `0x6da5148` |
| 步长 | **556**（= 存档 PWSTaskGroup 长度） |
| 索引 | = TF 号 |
| 副本 | 1 份 |

### 航空队数组

| 项 | 值 |
|---|---|
| copyA 基址 | `0x598f4f8` |
| copyB | 需用 copyA 的特征在内存里搜第二处 |
| 步长 | **680** |
| 索引 | = 航空队槽号 |
| 副本 | **2 份，必须都写** |
| 验证 | 2699/2716 完全吻合（99.4%） |

### 基地数组

| 项 | 值 |
|---|---|
| 基址 | `0x4570c50` |
| 步长 | **1172** |
| 索引 | = Location 槽号 |
| 验证 | 已加载 116 个中 90 个坐标吻合；不吻合的 26 个在 slot 14000+（TF 专用槽） |
| 特点 | 稀疏数组，只有靠近战区的基地被加载，其余槽位是 `(65535,65535)` |

---

## 三、字段偏移

### TF（运行时前段与存档不同，mission 之后一致）

| 字段 | 运行时 | 存档 | 类型 |
|---|---|---|---|
| endure | **4** | 48 | u32 |
| endureReq | **8** | 52 | u32 |
| fuel | **12** | — | u32 |
| load | **28** | 56 | u32 |
| flagship | 44 | 44 | u32 |
| home | 54 | 54 | u16 |
| wp | 118 | 118 | 40×(u16,u16) |
| wpCount | 320 | 320 | u16 |
| wpAlloc | 322 | 322 | u16 |
| mission | 349 | 349 | u8 |
| loadState | 350 | 350 | u8 |
| speed | 354 | 354 | u8 |
| maxReact | 355 | 355 | u8 |
| routing | 369 | 369 | u8 |
| tolerance | 448 | 448 | u8 |

### 航空队（与存档一致）

| 字段 | 偏移 | 类型 |
|---|---|---|
| baseID | 40 | u16 |
| reinforceBase | 42 | u16 |
| primary | 44 | u8 |
| secondary | 46 | u8 |
| targetX / targetY | 192 / 196 | u16 |
| alt | 212 | **u16** |
| maxPlanes | 245 | u8 |
| upgradeTo | 308 | u16 |
| pctCAP / pctLRCAP / pctASW / pctSearch / pctTrain / pctRest | 560–565 | u8 |
| aswArcStart / aswArcEnd | 628 / 629 | u8 |
| navArcStart / navArcEnd | 630 / 631 | u8 |

### 基地（与存档一致）

| 字段 | 偏移 | 类型 |
|---|---|---|
| X / Y | 36 / 38 | u16 |
| prepTarget | 102 | **u16** |
| prep | 104 | u8 |
| combatMode | 110 | u8 |
| portExpand | 424 | **u8** |
| airfieldExpand | 428 | **u8** |
| fortExpand | 432 | **u8** |
| marchDir / marchLen | 651 / 652 | u8 |
| destX / destY | 662 / 664 | u16 |
| operationsMode | 906 | **u16** |

---

## 四、观察方法（曾因此误判"写入无效"）

**改完内存后界面不会立刻变。必须关掉面板再重开，引擎才重新读取。**

我一度以为改内存无效，实际是没重开面板的**假阴性**。关掉再开，Mission 立刻从 Amphibious 变成 Air Combat。

---

## 五、工具

| 文件 | 作用 |
|---|---|
| `memrw.py` | `/proc/pid/mem` 读写 + 段枚举 |
| `pwsfile.py` | 存档解析 + `record_by_len()` 按长度取记录 |
| `witp_mem.py` | TF 数组定位 + 读写 |
| `witp_ag.py` / `witp_ag2.py` | 航空队（后者处理双副本） |
| `witp_loc.py` | 基地数组定位 + 读写 |
| `witp_mem_bridge.py` | MCP 桥接（TF） |
| `witp_mem_bridge2.py` | MCP 桥接（航空队+基地） |

MCP 工具（10 个，已注册进 `witp-ae`，共 30 个工具）：

| 工具 | 作用 |
|---|---|
| `witp_mem_list_tfs` | 读全部 TF 实时状态 |
| `witp_mem_show_tf` | 读单个 TF 全字段 |
| `witp_mem_set_tf` | 改 TF 字段 |
| `witp_mem_set_tf_waypoints` | 写航路点 |
| `witp_mem_airgroups` | 读航空队列表 |
| `witp_mem_show_airgroup` | 读单个航空队 |
| `witp_mem_set_airgroup` | 改航空队（自动写双副本） |
| `witp_mem_show_base` | 读单个基地 |
| `witp_mem_set_base` | 改基地字段 |
| `witp_mem_find_base` | 按六角坐标查基地槽号 |

---

## 六、性能

| 操作 | 耗时 |
|---|---|
| TF 定位+读 | 0.6s |
| 航空队定位+读 | 3.0s |
| 基地定位+读 | 0.2s（已知基址快速验证） |
| 基地全量扫描（首次） | 60–120s |

**优化**：`witp_loc.py` 内置 `KNOWN_BASE = 0x4570c50`，先用它单点验证（~10ms），失败才全量扫。

---

## 七、尚未标定

- 舰船（Ship）运行时结构
- 飞行员（Pilot）运行时结构
- TF 的 fuel 字段（界面显示 237，结构里搜不到，可能按舰汇总）
