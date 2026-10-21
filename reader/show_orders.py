import sys, json
sys.path.insert(0, '/root/.hermes/profiles/witp/workspace/witp-reader')
from witp_core import load

S = "/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral" + chr(39) + "s Edition/SAVE/"
for slot in ("015", "040"):
    g = load(S + "wpae%s.pws" % slot)
    print("=== wpae%s ===" % slot)
    tf = {t['slot']: t for t in g.tfs}
    for n in (7, 14):
        t = tf.get(n)
        if t:
            print("  TF%-3d mission=%-10s dest=%s wp_end=%s pos=%s speed=%s endur=%s" % (
                n, t['mission'], t['destination'], t['waypoints'][-1] if t['waypoints'] else None,
                t['position'], t['speed'], t['endurance']))
    ags = {a['slot']: a for a in g.airgroups}
    for n in (9, 8, 10):
        a = ags.get(n)
        if a:
            print("  AG%-3d %-18s base=%s prim=%-8s alt=%-5s search=%-3s cap=%-3s arc=%s" % (
                n, a['name'][:18], a['base_id'], a['primary'], a['alt'],
                a['search'], a['cap'], a['search_arc']))
    locs = {l['slot']: l for l in g.locations}
    for n in (992,):
        l = locs.get(n)
        if l:
            print("  LOC%-4d %-12s port=%s(%s) af=%s(%s) fort=%s(%s) exp=%s/%s/%s" % (
                n, l['name'][:12], l['port'], l['port_sps'], l['airfield'], l['airfield_sps'],
                l['fort'], l['fort_expand'], l['port_expand'], l['airfield_expand'],
                l['fort_expand']))
    gu = {u['slot']: u for u in g.ground_units()}
    for n in (6062,):
        u = gu.get(n)
        if u:
            print("  GU%-4d %-20s order=%-10s march=%s dest=%s prep=%s" % (
                n, u.get('name', '')[:20], u.get('combat_order'), u.get('march_len'),
                u.get('dest'), u.get('prep')))
