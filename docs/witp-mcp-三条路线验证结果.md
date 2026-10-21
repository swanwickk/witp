# 三条进阶路线的验证结果（全部已实证，勿重复尝试）

> 目标：突破 60% 覆盖率瓶颈，标定剩余字段。
> 结论：**三条路全部被证伪**。以下每条都有可复现的实测证据。

---

## 路线 A：witploadAE 导入（CSV → .dat）反推偏移

**设想**：改 CSV 里一个字段 → `/i` 导入 → 对比 .dat 前后差异 → 差异地址即字段偏移。

**实测**：

```bash
# 1. 先验证往返是否无损
witploadAE.exe /s3 /e     # 导出 CSV
cp wpl003.dat /tmp/orig.dat
witploadAE.exe /s3 /i     # 原样导入
md5sum /tmp/orig.dat wpl003.dat
# 6867bd11... 6867bd11...  ← 完全一致，往返无损 ✓
```

```bash
# 2. 改一个字段再导入
# WITPloc003.csv 第0行 Planning: 0 -> 77
witploadAE.exe /s3 /i
# "All files have been loaded successfully."
stat wpl003.dat
# 2010-09-13 11:41:26  3901500   ← 时间戳仍是 2010 年，文件没被重写
```

**结论**：`/i` 只**读取并校验** CSV，不写回 .dat（或只在特定条件下写）。CSV→.dat 的反向映射无法用于定位。

补充：`.dat` 是紧凑格式（3901500 字节对应 8499 条 loc 记录，非定长），与存档的定长结构（1172B × 18000）不是同一套布局，不能直接类比。

---

## 路线 B：附加进程改内存

**设想**：gdb 附加 → 在堆里搜 TF 结构体特征 → 直接改运行时字段。

**实测**：

```bash
# 附加成功，PE 基址 0x400000，数据段 rwxp
gdb -p <pid> -ex "info proc mappings"
# 0x400000 - 0x851000  r-xp  .../War in the Pacific Admiral Edition.exe
# 0x851000 - 0x85f000  rwxp  ...   ← 可写

# 搜 TF7 的 4 个连续航路点 (106,125)(107,126)(106,127)(106,128)
# 字节串 6a007d006b007e006a007f006a008000
→ 命中 0 处

# 搜 TF14 的 flagship=3002 (i32)
→ 命中 167 处（全是巧合，附近找不到对应的 home=1282）
```

**结论**：游戏载入存档后，**内存中的数据结构与 .pws 存档的定长布局不同**。
存档是按 556/680/1172 字节的定长数组组织的，运行时很可能是指针/动态容器。
仅凭存档偏移无法映射到运行时地址。

要突破这一层，需要**反汇编载入函数**，找到 `PWSOpenFile` 之后数据被拷贝到哪、
结构体字段如何重排。这是数天级的工作量，且 4.8MB 无符号 PE 难度很高。

---

## 路线 C：witploadAE 直接读存档

**设想**：官方工具也许能 dump .pws。

**实测**：

```bash
strings witploadAE.exe | grep -iE "\.pws|SAVE|wpae"
# 无任何 .pws / wpae / saved game 相关字符串

witploadAE.exe /d"..\SAVE" /s1 /e
# Dumping File ..\SAVE\wpd001.dat
# ..\SAVE\wpd001.dat: No such file or directory
```

**结论**：`witploadAE` 只处理 SCEN 目录的 `wpX###.dat`，**不支持 .pws 存档**。
它给出的字段名（`TFRouting` / `TFReaction` / `TFRetirement` / `LCUStance` 等）
是**剧本数据结构**的字段名，不能直接当作存档偏移的线索。

---

## 已确认「不在存档里」的字段（第一类硬障碍）

用「GUI 改设置 → 存新槽 → 全记录差分」验证，差异**只有存档头的时间戳**：

| 字段 | 差分结果 |
|---|---|
| Follow TF / Meet TF | type=19/70 零差异 |
| TFRetirement（Retirement Allowed ↔ Remain on Station） | type=19/70 零差异，只有 type=38 off1026-1032 的时间戳变化 |

⇒ 这两个是**引擎运行时状态**，存档层无法实现。

---

## 当前的覆盖率瓶颈分解

43 条命令面：已实现 26 / 部分 3 / 未实现 14（**60%**）

未实现的 14 项按障碍分类：

**A. 纯运行时状态，不进存档（2 项）**
- Follow TF / Meet TF
- TFRetirement

**B. 需要多步 GUI 交互，VNC 逐点定位成本极高（6 项）**
- Set Patrol Zone（须先清目的地，但该面板无 Clear 按钮）
- 组建/解散 TF（要逐艘选船）
- 舰船在 TF 间转移（同上）
- Set All（批量设置）
- 政治点换将（将领列表翻页）
- 基地 HQ 变更

**C. 字段偏移已知但语义未验证（2 项）**
- AG `upgradeTo@308` / `agrUpgrade@370`（写入后无法从界面确认对应哪一项）
- TF 速度档 `speed@354`（已知 3=Cruise，其余档位未验证）

**D. 涉及大规模结构改动（4 项）**
- 舰船改装 Conversions（要改舰级、武器、容量）
- 飞行员管理（要写 Pilot 记录并重建索引）
- 部队拆分/合并（要新建 LOC 记录）
- 日本工业生产

---

## 结论

**纯存档读写能做的，已经做完了。** 剩余 14 项各自都有明确的、已实证的技术障碍，
不是"再花时间就能做出来"。

要继续，只有一条路：**反汇编载入函数**，搞清楚存档结构 → 运行时结构的映射关系。
这是目前唯一未尝试的方向，但工作量是数天级。
