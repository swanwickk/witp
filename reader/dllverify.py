"""dllverify.py — 用游戏自带 pwsdll.dll 回读存档，验证引擎可解析（在 Wine 32 位 Python 下运行）。

用法（宿主机调用）：
    wine C:\\py32\\python.exe Z:\\root\\.hermes\\workspace\\witp-reader\\dllverify.py <存档 Windows 路径> [--ag N] [--tf N]

输出（每行 key=value，便于调用方解析）：
    records=<记录数>
    message=<DLL 的最后一条消息，正常为 End of file>
    tf<N>_mission=<任务码>   tf<N>_wp=<航路点逗号分隔>
    ag<N>_name / ag<N>_cap / ag<N>_search / ag<N>_primary
"""
import ctypes
import pathlib
import sys

sys.path.insert(0, r"Z:\root\.hermes\workspace\witp-reader\pywitpaescraper")
import pwsdll as P  # noqa: E402

dll_dir = pathlib.Path(r"Z:\root\.wine-witp\drive_c\1108r9") / (
    "War in the Pacific Admiral" + chr(39) + "s Edition")

save = sys.argv[1]
tf_slot = 14
ag_slot = None
if "--tf" in sys.argv:
    tf_slot = int(sys.argv[sys.argv.index("--tf") + 1])
if "--ag" in sys.argv:
    ag_slot = int(sys.argv[sys.argv.index("--ag") + 1])

pw = P.PWSDll(dll_dir)
ctx = pw.new_context()
pw.pws_open_file(ctx, save, 0)
n = 0
while True:
    pw.pws_get_next_item(ctx)
    n += 1
    if ctx.PWSid == 70 and ctx.PWSaddress.taskgroups:
        tg = ctypes.cast(ctx.PWSaddress.taskgroups, ctypes.POINTER(P.PWSTaskGroupInfo)).contents
        t = tg.taskgroup[tf_slot]
        print("tf%d_mission=%d" % (tf_slot, ord(t.tfMission)))
        wps = []
        # 航路点在结构体尾部 opaque 区，DLL 不直接暴露；这里只报任务/母港/旗舰
        print("tf%d_flagship=%d" % (tf_slot, t.tfFlagship))
        print("tf%d_home=%d" % (tf_slot, t.tfHomePort))
    if ag_slot is not None and ctx.PWSid == 20 and ctx.PWSaddress.airgroups:
        ag = ctypes.cast(ctx.PWSaddress.airgroups, ctypes.POINTER(P.PWSAirGroupInfo)).contents
        a = ag.airgroup[ag_slot]
        name = a.groupname.decode("latin1").split("\x00")[0]
        print("ag%d_name=%s" % (ag_slot, name))
        print("ag%d_cap=%d" % (ag_slot, a.acPctCAP[0]))
        print("ag%d_search=%d" % (ag_slot, a.acPctSearch[0]))
        print("ag%d_primary=%d" % (ag_slot, a.primaryMission))
        print("ag%d_base=%d" % (ag_slot, a.baseID))
    if ctx.PWSopened == -1:
        break
    if n > 200:
        break
msg = ctx.PWSMessage
pw.pws_close_file(ctx)
print("records=%d" % n)
try:
    print("message=%s" % (msg.decode("latin1") if isinstance(msg, bytes) else msg))
except Exception:
    print("message=?")
