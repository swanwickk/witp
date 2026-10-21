import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=None)
    out = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            out.append("TOOLS: " + ", ".join(t.name for t in tools.tools))
            for name, args in [
                ("witp_ground_units", {"name_like": "Australian", "limit": 5}),
                ("witp_airgroups", {"base_id": 992, "limit": 4}),
                ("witp_game_key", {"keys": "t"}),
                ("witp_end_turn", {}),
                ("witp_set_tf_orders", {"slot": 14, "mission": "BOGUS"}),
            ]:
                res = await s.call_tool(name, args)
                txt = res.content[0].text if res.content else ""
                out.append(f"--- {name} ---\n{txt[:700]}")
    open("/tmp/mcp_tools_result.txt", "w", encoding="utf-8").write("\n\n".join(out))


asyncio.run(main())
