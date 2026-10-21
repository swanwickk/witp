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


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=ENV)
    out = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            out.append("TOOLS(%d): %s" % (len(tools.tools),
                                          ", ".join(t.name for t in tools.tools)))
            calls = [
                ("witp_status", {}),
                ("witp_ground_units", {"limit": 4}),
                ("witp_set_ground_orders", {"slot": 6062, "order": "deliberate",
                                            "out_file": "wpae030.pws", "overwrite": True}),
                ("witp_set_base_build", {"slot": 992, "port": 0, "airfield": 1,
                                         "out_file": "wpae031.pws", "overwrite": True}),
                ("witp_set_airgroup_orders", {"slot": 9, "altitude": 6000,
                                              "search": 30, "search_arc": "0,90",
                                              "out_file": "wpae032.pws", "overwrite": True}),
            ]
            for name, args in calls:
                res = await s.call_tool(name, args)
                txt = res.content[0].text if res.content else ""
                out.append(f"--- {name} ---\n{txt[:1200]}")
    open("/tmp/e2e_new.txt", "w", encoding="utf-8").write("\n\n".join(out))


asyncio.run(main())
