import glob, os, sys

G = "/root/.wine-witp/drive_c/1108r9/War in the Pacific Admiral" + chr(39) + "s Edition"
for pat in ("*.dll", "*.exe"):
    print("==", pat)
    for f in sorted(glob.glob(os.path.join(G, pat))):
        print("%10d  %s" % (os.path.getsize(f), os.path.basename(f)))
