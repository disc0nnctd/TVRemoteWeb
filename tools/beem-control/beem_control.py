#!/usr/bin/env python3
"""Beem Control: the TVRemoteWeb phone remote plus projector updates, served on dcmini.

The projector (Airtel LAN) is reachable from dcmini but not from the tailnet, so
this listens on 127.0.0.1 and `tailscale serve` publishes it over HTTPS:

  /               Beem Control shell (Remote + Updates tabs)
  /_bc/api/*      status, deploy the repo's runtime, install an APK, screenshot
  /ws             WebSocket proxy to the projector's mouse daemon (:8788)
  everything else HTTP proxy to the projector's TVRemoteWeb (:8787)

Deploys reuse beem_agent.server, so this must run with agent/.venv's python.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import aiohttp
from aiohttp import web

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "agent"))
import beem_agent.server as beem  # noqa: E402

PORT = int(os.environ.get("BEEM_CONTROL_PORT", "8796"))
HTTP_PORT, WS_PORT = 8787, 8788
LIGHTS_CFG = Path.home() / ".config/tvremoteweb-lights.json"
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-encoding",
               "content-length", "host", "upgrade"}
WS_ORIGINAL = "const url = `ws://${location.hostname}:8788/`;"
WS_PROXIED = "const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;"
deploy_lock = asyncio.Lock()


def projector_serial() -> str:
    try:
        return beem._resolve_device(scan=False)
    except Exception:
        return json.loads(LIGHTS_CFG.read_text())["projector"]


def projector_host() -> str:
    return projector_serial().rsplit(":", 1)[0]


async def blocking(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


def ok(data) -> web.Response:
    return web.json_response({"ok": True, **data})


def fail(err: Exception) -> web.Response:
    return web.json_response({"ok": False, "error": str(err)}, status=500)


# ------------------------------------------------------------------ api ----
async def api_status(request):
    try:
        serial = await blocking(projector_serial)
        inspect = json.loads(await blocking(beem.inspect_tvremoteweb_install))
        return ok({"serial": serial, "install": inspect})
    except Exception as e:
        return fail(e)


async def api_deploy(request):
    if deploy_lock.locked():
        return web.json_response({"ok": False, "error": "a deploy is already running"}, status=409)
    async with deploy_lock:
        try:
            result = json.loads(await blocking(beem.deploy_tvremoteweb_runtime, "DEPLOY"))
            return ok({"install": result})
        except Exception as e:
            return fail(e)


async def api_apk(request):
    reader = await request.multipart()
    part = await reader.next()
    if part is None or not (part.filename or "").lower().endswith(".apk"):
        return web.json_response({"ok": False, "error": "choose an .apk file"}, status=400)
    with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as tmp:
        while chunk := await part.read_chunk(1 << 20):
            tmp.write(chunk)
    try:
        serial = await blocking(projector_serial)
        proc = await asyncio.create_subprocess_exec(
            beem.ADB, "-s", serial, "install", "-r", tmp.name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), 180)
        text = out.decode(errors="replace").strip()
        if proc.returncode or "Success" not in text:
            return web.json_response({"ok": False, "error": text[-500:]}, status=500)
        return ok({"detail": f"{part.filename} installed"})
    except Exception as e:
        return fail(e)
    finally:
        os.unlink(tmp.name)


async def api_screen(request):
    try:
        serial = await blocking(projector_serial)
        proc = await asyncio.create_subprocess_exec(
            beem.ADB, "-s", serial, "exec-out", "screencap", "-p",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        png, _ = await asyncio.wait_for(proc.communicate(), 20)
        if not png:
            raise RuntimeError("projector returned an empty screenshot (HDMI video can't be captured)")
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})
    except Exception as e:
        return fail(e)


# ---------------------------------------------------------------- proxy ----
async def ws_proxy(request):
    client = web.WebSocketResponse(heartbeat=20)
    await client.prepare(request)
    session = request.app["session"]
    try:
        upstream = await session.ws_connect(f"ws://{projector_host()}:{WS_PORT}/", timeout=aiohttp.ClientWSTimeout(ws_close=5))
    except Exception:
        await client.close(code=1011)
        return client

    async def pump(src, dst):
        async for msg in src:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await dst.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await dst.send_bytes(msg.data)
            else:
                break

    tasks = [asyncio.create_task(pump(client, upstream)), asyncio.create_task(pump(upstream, client))]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in tasks:
        t.cancel()
    await upstream.close()
    await client.close()
    return client


async def http_proxy(request):
    url = f"http://{projector_host()}:{HTTP_PORT}{request.rel_url}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
    body = await request.read()
    try:
        async with request.app["session"].request(
                request.method, url, headers=headers, data=body or None,
                timeout=aiohttp.ClientTimeout(total=120), allow_redirects=False) as up:
            payload = await up.read()
            out = {k: v for k, v in up.headers.items() if k.lower() not in HOP_HEADERS}
            if request.path == "/remote.html":
                payload = payload.replace(WS_ORIGINAL.encode(), WS_PROXIED.encode())
            return web.Response(status=up.status, body=payload, headers=out)
    except Exception as e:
        return web.Response(status=502, text=f"Projector unreachable: {e}")


async def index(request):
    return web.FileResponse(HERE / "index.html", headers={"Cache-Control": "no-store"})


async def on_startup(app):
    app["session"] = aiohttp.ClientSession(auto_decompress=True)


async def on_cleanup(app):
    await app["session"].close()


def main():
    app = web.Application(client_max_size=512 * 1024 * 1024)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/_bc/api/status", api_status)
    app.router.add_post("/_bc/api/deploy", api_deploy)
    app.router.add_post("/_bc/api/apk", api_apk)
    app.router.add_get("/_bc/api/screen", api_screen)
    app.router.add_get("/ws", ws_proxy)
    app.router.add_route("*", "/{tail:.*}", http_proxy)
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)


if __name__ == "__main__":
    main()
