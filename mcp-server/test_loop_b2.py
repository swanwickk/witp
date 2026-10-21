import asyncio, json, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/root/.hermes/mcp-servers/witp-mcp/server.py"
PY = "/root/.hermes/hermes-agent/venv/bin/python3"
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

            print("BEFORE:", (await call("witp_status"))[:200], flush=True)
            r = await call("witp_end_turn", {"confirm": True, "wait_seconds": 300})
            print("END_TURN:", r, flush=True)


asyncio.run(main())
