"""csv_diff_probe.py — 通过 witploadAE 导入反推字段字节偏移

原理（比任何盲猜都准）：
  1. 备份原始 .dat
  2. 改 CSV 里某一行的某一列（只改一个字段）
  3. witploadAE /i 导入，重写 .dat
  4. 对比 .dat 的新旧字节差异 → 差异位置就是该字段的偏移

  由于 .dat 是定长结构体数组，偏移 = 差异地址 % 结构体长度，
  槽号 = 差异地址 // 结构体长度。

用法：
  python3 csv_diff_probe.py <kind> <column> <row_index> <new_value> [scen]
    kind: loc | shp | grp | ldr | plt | cls | dev | air
"""
import csv
import os
import shutil
import subprocess
import sys

GAME = ("/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition")
SCEN = os.path.join(GAME, "SCEN")

# 各表对应的 .dat 文件前缀与记录长度（由已知字段反推）
DAT = {"loc": "wpl", "shp": "wps", "grp": "wpg", "ldr": "wpl",
       "plt": "wpp", "cls": "wpc", "dev": "wpd", "air": "wpa"}
CSV = {"loc": "WITPloc", "shp": "WITPshp", "grp": "WITPgrp", "ldr": "WITPldr",
       "plt": "WITPplt", "cls": "WITPcls", "dev": "WITPdev", "air": "WITPair"}


def run_import(scen):
    env = dict(os.environ, WINEPREFIX="/root/.wine-witp", DISPLAY=":98",
               HOME="/root", LANG="C.UTF-8")
    r = subprocess.run(["wine", "witploadAE.exe", f"/s{scen}", "/i"],
                       cwd=SCEN, capture_output=True, text=True, timeout=300, env=env)
    ok = "loaded successfully" in (r.stdout or "")
    return ok, (r.stdout or "")[-400:]


def main():
    kind = sys.argv[1]
    col = sys.argv[2]
    row = int(sys.argv[3])
    val = sys.argv[4]
    scen = int(sys.argv[5]) if len(sys.argv) > 5 else 3

    dat_name = f"{DAT[kind]}{scen:03d}.dat"
    csv_name = f"{CSV[kind]}{scen:03d}.csv"
    dat_path = os.path.join(SCEN, dat_name)
    csv_path = os.path.join(SCEN, csv_name)
    backup = f"/tmp/{dat_name}.bak"

    shutil.copy(dat_path, backup)
    orig = open(backup, "rb").read()

    rows = list(csv.DictReader(open(csv_path, encoding="latin1")))
    fieldnames = list(rows[0].keys())
    if col not in fieldnames:
        print(f"列 {col} 不存在；可用: {fieldnames[:20]}")
        return
    old = rows[row][col]
    rows[row][col] = val
    with open(csv_path, "w", newline="", encoding="latin1") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"CSV 第{row}行 {col}: {old!r} -> {val!r}")

    ok, tail = run_import(scen)
    if not ok:
        print("导入失败:", tail)
        shutil.copy(backup, dat_path)
        return

    new = open(dat_path, "rb").read()
    print(f".dat 大小 {len(orig)} -> {len(new)}")
    if len(orig) != len(new):
        print("!! 长度变化，无法按结构体定位")
        return
    diffs = [i for i in range(len(orig)) if orig[i] != new[i]]
    print(f"差异 {len(diffs)} 处")
    for i in diffs[:12]:
        print(f"  abs {i}  {orig[i]} -> {new[i]}")
    if len(diffs) == 1:
        print("\n==> 单位置命中！")
    # 用 diff 间距猜记录长度
    if len(diffs) > 1:
        gaps = sorted({diffs[i+1]-diffs[i] for i in range(len(diffs)-1)})
        print("差异间距候选（可能是记录长度）:", gaps[:6])


if __name__ == "__main__":
    main()
