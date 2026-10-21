# ★重大纠正：引擎不校验压缩流长度★

> 2026-10-18 实测推翻此前长期坚持的技术前提。

## 一、此前的错误前提

项目从第一版起就假定：

> 引擎逐条校验压缩流长度，长度变 1 字节即报 `Restore size larger than expected` 并中断读档。

为此写了「空存储块填充 + 三级抖动」一整套 `compress_to_length()` 机制，
还经常因为「无法把压缩流精确调到 N 字节」而写档失败。

## 二、真相

**引擎校验的不是压缩流长度，而是容器头里的 `f3` 字段与实际压缩流长度是否一致。**

`.pws` 记录头：`[u16 实例号][u16 记录类型][u32 f2][u32 f3][zlib流]`
- 小记录（`id < 1000`）：`f2 = 解压长度`，`f3 = 压缩长度`
- 大记录（`id` 高位）：`f2/f3` 是引擎校验字段

只要**写入时把 `f3` 同步更新成实际压缩长度**，压缩流变长变短都能正常载入。

## 三、证据链（严格对照）

### 实验 1：压缩长度 +178 字节，f3 同步更新

```python
# 把 TF 记录 355..500 填成随机值 → 压缩长度 3458 → 3636（+178）
pack_container(records, out, keep_lengths=True, allow_len_change=True)
# 小记录自动 f2=len(data), f3=len(blob)
```

| DLL | 结果 |
|---|---|
| 原版 pwsdll.dll | `records=62` / `End of file` ✅ |
| 游戏本体 | 正常载入，日期 1942-05-04 ✅ |

### 实验 2：故意让 f3 与实际不符（对照组）

手写容器：数据已变但 `f3` 保留原值 3458。

| DLL | 结果 |
|---|---|
| 原版 pwsdll.dll | `Restore size larger than expected` ❌ |
| 打过长度补丁的 DLL | `Restored data size incorrect`（绕过了长度检查，卡在下一层）|

→ 证实报错确实由 **f3 不一致** 触发，而非压缩流本身长度。

## 四、对代码的影响

`pwspack.pack_container()` 新增 `allow_len_change`（**默认 True**）：

1. 优先尝试 `compress_to_length()` 精确回填（保持字节级一致，最保险）
2. 回填失败 → 直接 `_deflate_zlib()` 压缩，小记录自动把 `f3` 写成实际长度
3. 不再抛 `RuntimeError`

`witp_orders.Save.save()` 已固定传 `allow_len_change=True`。

## 五、实际解决掉的问题

之前会失败的场景，现在全部通过：

```python
s.set_tf_routing(1, routing=3, tolerance=3, max_react=6)
s.set_tf_load(7, 'load')
s.set_ag_resize(498, 34)
s.set_ground_order(34, order='shock', operations_mode=0)
s.set_base_build(992, 1, 1, 1)
s.set_ship_repair(91, priority=4, mode=2, upgrade=1)
# → save OK，游戏正常载入
```

## 六、反汇编定位（留档，供后续参考）

`pwsdll.dll` 长度校验相关代码：

| 地址 | 指令 | 含义 |
|---|---|---|
| `0x100028b3` | `cmp esi, edi` | 实际 vs 期望长度 |
| `0x100028b5` | `ja 0x10002b92` | 实际 > 期望 → 报错 |
| `0x100028c6` | `jae 0x100028d7` | 相等/大于 → 继续；否则落空报 -4 |
| `0x100028c8` | `mov [0x17f31c34], 0xfffffffc` | 错误码 -4 = `Restore size larger than expected` |
| `0x1000294e` | `mov [...], 0xfffffffd` | 错误码 -3 = `Restored data size incorrect` |

错误码存储于 `0x17f31c34`，由 `fcn.10002d51` 分派到文案表。

补丁脚本 `patch_pwsdll.py`（jae→jmp、ja→nop）可用但**现已不需要**，
DLL 已从备份还原（md5 `47dfbd48c2d726825e5cdf46f239eb6a`）。

## 七、另一个发现：字段值会被引擎按类型钳制

`Max React@355`：
- AirCombat 编队（TF1）：写入 6 → 界面显示 **6** ✅
- 两栖编队（TF7）：写入 6 → 界面显示 **2**（被上限钳制）

⇒ 字段写入成功 ≠ 值一定被接受，**引擎会对某些字段做业务范围校验**。
验证时必须看界面实际显示值，不能只看存档里的字节。
