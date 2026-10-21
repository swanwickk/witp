import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=None)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            calls = [
                ("witp_set_tf_orders", {"slot": 14, "mission": "SURFACE",
                                        "destination_x": 110, "destination_y": 150,
                                        "out_file": "wpae020.pws", "overwrite": True}),
                ("witp_set_airgroup_orders", {"slot": 9, "cap": 60, "search": 20,
                                              "out_file": "wpae021.pws", "overwrite": True}),
            ]
            out = []
            for name, args in calls:
                res = await s.call_tool(name, args)
                txt = res.content[0].text if res.content else ""
                out.append(f"--- {name} ---\n{txt}")
            open("/tmp/mcp_write_result.txt", "w", encoding="utf-8").write("\n\n".join(out))


asyncio.run(main())
