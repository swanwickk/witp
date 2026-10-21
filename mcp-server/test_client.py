import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=None)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            for name, args in [
                ("witp_status", {}),
                ("witp_saves", {}),
                ("witp_taskforces", {"limit": 6}),
                ("witp_bases", {"name_like": "Port Moresby", "limit": 3}),
                ("witp_reports", {"kind": "aoperationsreport", "max_chars": 300}),
                ("witp_screen", {"ocr_top_bar": True}),
            ]:
                res = await s.call_tool(name, args)
                txt = res.content[0].text if res.content else ""
                print(f"\n--- {name} ---\n{txt[:900]}")


asyncio.run(main())
