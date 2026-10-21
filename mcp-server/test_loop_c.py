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

# 从"过回合前"的干净档 wpae001 出发不可靠（它已含上次命令）。
# 用 wpae015（原始 05/04 第 1 回合、未改过的档）作为基线。
BASE = "wpae015.pws"


async def main():
    params = StdioServerParameters(command=PY, args=[SERVER], env=ENV)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, args=None):
                res = await s.call_tool(name, args or {})
                return res.content[0].text if res.content else ""

            # 用 wpae015 当输入：先复制到固定槽位，再让工具以它为源
            shutil.copy(os.path.join(SAVE, BASE), os.path.join(SAVE, "wpae002.pws"))

            out = "wpae008.pws"
            steps = []

            # 1) TF7：改任务为水面战 + 目的地 Lae(99,126)
            r1 = json.loads(await call("witp_set_tf_orders", {
                "slot": 7, "mission": "SURFACE",
                "destination_x": 99, "destination_y": 126,
                "out_file": out, "overwrite": True}))
            steps.append(("TF7 SURFACE->Lae(99,126)", r1))

            # 2) 航空队 AG9：搜索 50% + 高度 10000
            r2 = json.loads(await call("witp_set_airgroup_orders", {
                "slot": 9, "search": 50, "altitude": 10000,
                "out_file": out, "overwrite": True}))
            steps.append(("AG9 search50 alt10000", r2))

            # 3) 日军地面部队 slot 4635（"1st" 在 109,131）改为 shock
            r3 = json.loads(await call("witp_set_ground_orders", {
                "slot": 4635, "order": "shock",
                "out_file": out, "overwrite": True}))
            steps.append(("GU4635 shock", r3))

            # 4) 基地 992 拉包尔：停止扩建（0,0,0）
            r4 = json.loads(await call("witp_set_base_build", {
                "slot": 992, "port": 0, "airfield": 0, "fort": 0,
                "out_file": out, "overwrite": True}))
            steps.append(("LOC992 stop expand", r4))

            for name, r in steps:
                print("%-28s ok=%-5s engine=%-5s" % (
                    name, r.get("ok"), r.get("engine_verify", {}).get("ok")), flush=True)
                if not r.get("ok"):
                    print("   ERR:", r.get("error"), flush=True)

            # 复制成游戏可载入槽位
            shutil.copy(os.path.join(SAVE, out), os.path.join(SAVE, "wpae001.pws"))
            print("staged wpae001 <-", out, flush=True)


asyncio.run(main())
