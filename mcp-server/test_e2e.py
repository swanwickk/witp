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
            res = await s.call_tool("witp_status", {})
            out.append("=== witp_status ===\n" + res.content[0].text[:800])

            res = await s.call_tool("witp_set_tf_orders", {
                "slot": 14, "mission": "BOMBARDMENT",
                "destination_x": 108, "destination_y": 148,
                "out_file": "/tmp/e2e_tf.pws", "overwrite": True})
            out.append("=== witp_set_tf_orders ===\n" + res.content[0].text[:1600])

            res = await s.call_tool("witp_set_airgroup_orders", {
                "slot": 9, "cap": 60, "search": 20,
                "out_file": "/tmp/e2e_ag.pws", "overwrite": True})
            out.append("=== witp_set_airgroup_orders ===\n" + res.content[0].text[:1200])
    open("/tmp/e2e_result.txt", "w", encoding="utf-8").write("\n\n".join(out))


asyncio.run(main())
