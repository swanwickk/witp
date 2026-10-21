import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"
ENV = dict(os.environ,
           WITP_INSTANCE="/root/.wine-witp-mcp/prefix/drive_c/1108r9",
           WITP_DISPLAY=":97",
           WITP_VNC_PORT="5901",
           WITP_WINEPREFIX="/root/.wine-witp")

LOG = []


def add(s):
    LOG.append(s)
    print(s, flush=True)


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=ENV)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, args=None):
                res = await s.call_tool(name, args or {})
                txt = res.content[0].text if res.content else ""
                return txt

            add("=== 1) 开局态势 ===")
            add((await call("witp_status"))[:600])

            add("\n=== 2) 查日军可动编队 ===")
            tfs = json.loads(await call("witp_taskforces", {"with_ships": False}))
            for t in tfs[:6]:
                add(f"  slot {t['slot']:>3} {t['mission']:<12} pos={t['position']} dest={t['destination']}")

            add("\n=== 3) 编队命令：TF7 两栖 → 莫港(98,130) 保持两栖 ===")
            r = await call("witp_set_tf_orders", {
                "slot": 7, "mission": "AMPHIB", "destination_x": 98, "destination_y": 130,
                "out_file": "wpae040.pws", "overwrite": True})
            d = json.loads(r)
            add(f"  ok={d['ok']} out={os.path.basename(d.get('out',''))} "
                f"engine={d.get('engine_verify')}")
            add(f"  after={d.get('after')}")

            add("\n=== 4) 航空队命令：拉包尔陆攻改高度 6000 + 搜索 30% ===")
            ags = json.loads(await call("witp_airgroups", {"base_id": 992, "limit": 6}))
            for a in ags[:4]:
                add(f"  slot {a['slot']:>3} {a['name']:<20} {a['primary']:<8} "
                    f"cap={a['cap']} search={a['search']} alt={a['alt']}")
            target = next((a for a in ags if a["primary_code"] == 3), ags[0])
            r = await call("witp_set_airgroup_orders", {
                "slot": target["slot"], "altitude": 6000, "search": 30,
                "search_arc": "0,90", "out_file": "wpae041.pws", "overwrite": True})
            d = json.loads(r)
            add(f"  ok={d['ok']} engine={d.get('engine_verify')}")

            add("\n=== 5) 地面部队命令：莫港守军改 deliberate ===")
            gus = json.loads(await call("witp_ground_units", {"name_like": "Port Moresby"}))
            for u in gus:
                add(f"  slot {u['slot']} {u['name']} ({u['x']},{u['y']}) order={u['combat_order']}")
            gu = gus[0]
            r = await call("witp_set_ground_orders", {
                "slot": gu["slot"], "order": "deliberate",
                "out_file": "wpae042.pws", "overwrite": True})
            d = json.loads(r)
            add(f"  ok={d['ok']} engine={d.get('engine_verify')}")

            add("\n=== 6) 基地扩建：拉包尔港口停止建设 ===")
            bases = json.loads(await call("witp_bases", {"name_like": "Rabaul"}))
            b = bases[0]
            add(f"  {b['name']} slot={b['slot']} port={b['port']} af={b['airfield']}")
            r = await call("witp_set_base_build", {
                "slot": b["slot"], "port": 0,
                "out_file": "wpae043.pws", "overwrite": True})
            d = json.loads(r)
            add(f"  ok={d['ok']} engine={d.get('engine_verify')}")

            add("\n=== 7) 战报读取 ===")
            add((await call("witp_reports", {"kind": "aoperationsreport", "max_chars": 260}))[:300])

    open("/tmp/e2e_round.txt", "w", encoding="utf-8").write("\n".join(LOG))


asyncio.run(main())
