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

            # 干净基线：wpae015 复制成 wpae001（工具读"最新存档"，用绝对路径更稳）
            shutil.copy(os.path.join(SAVE, "wpae015.pws"),
                        os.path.join(SAVE, "wpae001.pws"))
            src = os.path.join(SAVE, "wpae001.pws")
            out = "wpae010.pws"

            r1 = json.loads(await call("witp_set_tf_orders", {
                "slot": 7, "mission": "SURFACE",
                "destination_x": 99, "destination_y": 126,
                "out_file": out, "overwrite": True}))
            print("TF7 ->", json.dumps({
                "ok": r1.get("ok"), "engine": r1.get("engine_verify", {}).get("ok"),
                "dest": r1.get("changes", {}).get("destination", {}).get("new"),
                "after": {k: r1.get("after", {}).get(k)
                          for k in ("mission", "destination", "dest_base")}},
                ensure_ascii=False), flush=True)

            r2 = json.loads(await call("witp_set_airgroup_orders", {
                "slot": 9, "search": 60, "altitude": 12000,
                "out_file": out, "overwrite": True}))
            print("AG9 ->", r2.get("ok"), r2.get("engine_verify", {}).get("ok"), flush=True)

            shutil.copy(os.path.join(SAVE, out), os.path.join(SAVE, "wpae001.pws"))
            print("staged", flush=True)


asyncio.run(main())
