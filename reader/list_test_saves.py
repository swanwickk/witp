import sys, glob, os
sys.path.insert(0, '/root/.hermes/profiles/witp/workspace/witp-reader')
from witp_core import load

S = "/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral" + chr(39) + "s Edition/SAVE"
files = sorted(glob.glob(os.path.join(S, "*.pws")))
print("dir:", S)
print("count:", len(files))
for f in files:
    try:
        g = load(f)
        s = g.summary()
        print(os.path.basename(f), s.get('date'), 'turn', s.get('turn'), os.path.getsize(f))
    except Exception as e:
        print(os.path.basename(f), 'ERR', type(e).__name__, e)
