import asyncio, json, os, sys, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"
ENV = dict(os.environ,
           WITP_INSTANCE="/root/.wine-witp-mcp/prefix/drive_c/1108r9",
           WITP_DISPLAY=":97",
           WITP_VNC_PORT="5901",
           WITP_WINEPREFIX="/root/.wine-witp-mcp/prefix")

RES = {}


def rec(k, v):
    RES[k] = v
    print("\n### %s ###" % k, flush=True)
    print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1), flush=True)


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=ENV)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, args=None):
                res = await s.call_tool(name, args or {})
                return res.content[0].text if res.content else ""

            st = json.loads(await call("witp_status"))
            rec("1_开战态势", st)

            tfs = json.loads(await call("witp_taskforces", {"with_ships": False}))
            jap = [t for t in tfs if t.get("control") == "Human"]
            rec("2_人类可控编队", [{"slot": t["slot"], "mission": t["mission"],
                              "pos": t["position"], "dest": t["destination"]}
                             for t in jap[:8]])

            # --- 下命令 ---
            o1 = json.loads(await call("witp_set_tf_orders", {
                "slot": 7, "mission": "AMPHIB", "dest_x": 98, "dest_y": 130}))
            rec("3_TF7_两栖莫港", {"ok": o1.get("ok"), "engine": o1.get("engine_verify", {}).get("ok")})

            o2 = json.loads(await call("witp_set_airgroup_orders", {
                "slot": 9, "search": 40, "altitude": 8000, "search_arc": "0,90"}))
            rec("4_AG9_搜索40_高8000", {"ok": o2.get("ok"), "engine": o2.get("engine_verify", {}).get("ok")})

            o3 = json.loads(await call("witp_set_ground_orders", {
                "slot": 6062, "order": "deliberate"}))
            rec("5_地面6062_deliberate", {"ok": o3.get("ok"), "engine": o3.get("engine_verify", {}).get("ok")})

            o4 = json.loads(await call("witp_set_base_build", {
                "slot": 992, "port": 0, "airfield": 0, "fort": 1}))
            rec("6_拉包尔_扩要塞1", {"ok": o4.get("ok"), "engine": o4.get("engine_verify", {}).get("ok")})

            rec("7_写档产物", [o.get("out") for o in (o1, o2, o3, o4)])

            with open("/root/.hermes/profiles/witp/workspace/witp-mcp-out/round_result.json", "w") as f:
                json.dump(RES, f, ensure_ascii=False, indent=1)


asyncio.run(main())
