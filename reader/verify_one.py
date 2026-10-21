import os
import pathlib
import sys

sys.path.insert(0, r"Z:\root\.hermes\workspace\witp-reader\pywitpaescraper")
import pwsdll as P  # noqa: E402

APOS = chr(39)
ROOT = os.environ.get("PWS_ROOT",
                      r"Z:\root\.wine-witp-mcp\prefix\drive_c\1108r9")
# 允许 DLL 目录与存档目录分离（用来做 原版DLL vs 补丁DLL 的严格对照）
DLLROOT = os.environ.get("PWS_DLLROOT", ROOT)
SAVE = os.environ.get("PWS_SAVEFILE", "wpae001.pws")

dll_dir = pathlib.Path(DLLROOT) / ("War in the Pacific Admiral" + APOS + "s Edition")
save_dir = pathlib.Path(ROOT) / ("War in the Pacific Admiral" + APOS + "s Edition")
save_path = str(save_dir / "SAVE" / SAVE)
print("dll_dir :", dll_dir)
print("save    :", save_path)

pw = P.PWSDll(dll_dir)
ctx = pw.new_context()
pw.pws_open_file(ctx, save_path, 0)
n = 0
last = ""
while n < 300:
    pw.pws_get_next_item(ctx)
    n += 1
    if ctx.PWSMessage:
        m = ctx.PWSMessage
        if isinstance(m, bytes):
            m = m.decode("latin1", "replace")
        last = m
        if "End of file" in m or "rror" in m or "pect" in m or "size" in m:
            break
print("records=%d" % n)
print("message=%s" % last)
