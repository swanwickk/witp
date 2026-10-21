import asyncio, json, os, shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"
SAVE = ("/root/.wine-witp-mcp/prefix/drive_c/1108r9/War in the Pacific Admiral"
        + chr(39) + "s Edition/SAVE")
ENV = dict(os.environ,
           WITP_INSTANCE="/root/.wine-witp-mcp/prefix/drive_c/1108r9",
           WITP_DISPLAY=":97", WITP_VNC_PORT="5901",
           WITP_WINEPREFIX="/root/.wine-witp-mcp/prefix")


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=ENV)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, args=None):
                res = await s.call_tool(name, args or {})
                return res.content[0].text if res.content else ""

            # 1) 写四类命令到一个明确槽位
            o = {}
            o["tf"] = json.loads(await call("witp_set_tf_orders", {
                "slot": 7, "mission": "AMPHIB", "dest_x": 98, "dest_y": 130,
                "out_file": "wpae007.pws", "overwrite": True}))
            o["ag"] = json.loads(await call("witp_set_airgroup_orders", {
                "slot": 9, "search": 40, "altitude": 8000,
                "out_file": "wpae007.pws", "overwrite": True}))
            o["gu"] = json.loads(await call("witp_set_ground_orders", {
                "slot": 6062, "order": "deliberate",
                "out_file": "wpae007.pws", "overwrite": True}))
            o["base"] = json.loads(await call("witp_set_base_build", {
                "slot": 992, "port": 1, "airfield": 1, "fort": 1,
                "out_file": "wpae007.pws", "overwrite": True}))
            for k, v in o.items():
                print("write %-4s ok=%s engine=%s out=%s" % (
                    k, v.get("ok"), v.get("engine_verify", {}).get("ok"),
                    os.path.basename(v.get("out", ""))), flush=True)

            # 2) 放进游戏可载入的槽位 001
            shutil.copy(os.path.join(SAVE, "wpae007.pws"), os.path.join(SAVE, "wpae001.pws"))
            print("copied wpae007 -> wpae001", flush=True)


asyncio.run(main())
