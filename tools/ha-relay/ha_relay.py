#!/usr/bin/env python3
"""Room-light relay between the TVRemoteWeb remote and Home Assistant.

The projector (on Airtel) cannot reach this PC (on N1), but this PC can reach
the projector. So this relay listens on 127.0.0.1 here and keeps an
`adb reverse` tunnel open, making the same port appear on the projector's
loopback, where lights.cgi forwards the remote's requests.

The Home Assistant token never leaves this PC, and only the lights listed in
the config can be read or changed.

Config (JSON, default ~/.config/tvremoteweb-lights.json):
  {"projector": "192.168.1.19:5555", "port": 8790,
   "lights": [{"id": "rikku", "entity": "light.wiz_...", "name": "Rikku"}],
   "scenes": [{"id": "movie", "name": "Movie Mode", "brightness": 10, "kelvin": 2200},
              {"id": "off", "name": "Off", "on": false}]}
Home Assistant URL/token come from HASS_URL / HASS_TOKEN (env or ~/.hermes/.env).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG = Path(os.environ.get("TVR_LIGHTS_CONFIG", Path.home() / ".config/tvremoteweb-lights.json"))
ADB = os.environ.get("ADB", "adb")


def load_env():
    env = {k: os.environ[k] for k in ("HASS_URL", "HASS_TOKEN") if k in os.environ}
    dotenv = Path.home() / ".hermes/.env"
    if len(env) < 2 and dotenv.exists():
        for line in dotenv.read_text().splitlines():
            key, _, value = line.partition("=")
            if key in ("HASS_URL", "HASS_TOKEN") and key not in env:
                env[key] = value.strip().strip('"').strip("'")
    if len(env) < 2:
        sys.exit("HASS_URL and HASS_TOKEN are required")
    return env["HASS_URL"].rstrip("/"), env["HASS_TOKEN"]


cfg = json.loads(CONFIG.read_text())
PORT = int(cfg.get("port", 8790))
LIGHTS = {light["id"]: light for light in cfg["lights"]}
SCENES = {scene["id"]: scene for scene in cfg.get("scenes", [])}
HASS_URL, HASS_TOKEN = load_env()


def hass(method, path, body=None):
    request = urllib.request.Request(
        HASS_URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + HASS_TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read() or b"null")


def light_state(light):
    try:
        state = hass("GET", "/api/states/" + light["entity"])
    except Exception as error:
        return {"id": light["id"], "name": light["name"], "available": False, "error": str(error)}
    attrs = state.get("attributes", {})
    brightness = attrs.get("brightness")
    return {
        "id": light["id"], "name": light["name"],
        "available": state.get("state") not in ("unavailable", "unknown"),
        "on": state.get("state") == "on",
        "brightness": round(brightness * 100 / 255) if brightness is not None else None,
        "kelvin": attrs.get("color_temp_kelvin"),
        "mode": attrs.get("color_mode"),
        "rgb": attrs.get("rgb_color"),
        "min_kelvin": attrs.get("min_color_temp_kelvin", 2200),
        "max_kelvin": attrs.get("max_color_temp_kelvin", 6500),
    }


def apply_scene(scene):
    """One call sets every configured light, so they change together."""
    entities = [light["entity"] for light in LIGHTS.values()]
    if scene.get("on") is False:
        return hass("POST", "/api/services/light/turn_off", {"entity_id": entities})
    data = {"entity_id": entities}
    if "brightness" in scene:
        data["brightness_pct"] = scene["brightness"]
    if "kelvin" in scene:
        data["color_temp_kelvin"] = scene["kelvin"]
    return hass("POST", "/api/services/light/turn_on", data)


def snapshot():
    return {"status": "ok", "lights": [light_state(l) for l in LIGHTS.values()],
            "scenes": [{"id": s["id"], "name": s["name"]} for s in SCENES.values()]}


def apply(light, query):
    on = query.get("on")
    data = {"entity_id": light["entity"]}
    if on == "toggle":
        return hass("POST", "/api/services/light/toggle", data)
    if on == "0":
        return hass("POST", "/api/services/light/turn_off", data)
    if "brightness" in query:
        data["brightness_pct"] = max(1, min(100, int(query["brightness"])))
    if "kelvin" in query:
        data["color_temp_kelvin"] = max(1500, min(7000, int(query["kelvin"])))
    elif "rgb" in query:
        data["rgb_color"] = [max(0, min(255, int(v))) for v in query["rgb"].split(",")[:3]]
    return hass("POST", "/api/services/light/turn_on", data)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path == "/lights":
                return self.reply(200, snapshot())
            if url.path == "/scene":
                scene = SCENES.get(query.get("name", ""))
                if not scene:
                    return self.reply(404, {"status": "err", "detail": "unknown scene"})
                apply_scene(scene)
                time.sleep(0.4)
                return self.reply(200, snapshot())
            if url.path == "/set":
                light = LIGHTS.get(query.get("id", ""))
                if not light:
                    return self.reply(404, {"status": "err", "detail": "unknown light"})
                apply(light, query)
                time.sleep(0.4)   # let Home Assistant record the new state
                return self.reply(200, snapshot())
            return self.reply(404, {"status": "err", "detail": "not found"})
        except Exception as error:
            return self.reply(502, {"status": "err", "detail": "Home Assistant: " + str(error)})

    def log_message(self, *args):
        pass


def adb(*args, timeout=10):
    try:
        return subprocess.run([ADB, *args], capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def find_projector(subnet):
    """Scan subnet (e.g. "192.168.1") for the TVRemoteWeb server; return its IP."""
    import concurrent.futures, socket

    def probe(ip):
        try:
            with socket.create_connection((ip, 8787), timeout=0.6):
                pass
            with urllib.request.urlopen(f"http://{ip}:8787/remote.html", timeout=3) as response:
                return ip if b"/cgi-bin/remote.cgi" in response.read() else None
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(64) as pool:
        for ip in pool.map(probe, (f"{subnet}.{i}" for i in range(1, 255))):
            if ip:
                return ip
    return None


def keep_tunnel():
    """Keep tcp:PORT on the projector's loopback forwarded to this relay.

    The projector's Airtel DHCP address can change; when the saved one stops
    answering, rescan its subnet and remember the new address in the config."""
    serial = cfg["projector"]
    rule = f"tcp:{PORT}"
    failures = 0
    while True:
        if rule not in adb("-s", serial, "reverse", "--list"):
            adb("connect", serial)
            adb("-s", serial, "reverse", rule, rule)
            ok = rule in adb("-s", serial, "reverse", "--list")
            print(f"tunnel {'up' if ok else 'down'} via {serial}", flush=True)
            failures = 0 if ok else failures + 1
            if failures >= 3:
                host, _, port = serial.partition(":")
                found = find_projector(host.rsplit(".", 1)[0])
                if found and found != host:
                    serial = f"{found}:{port or 5555}"
                    cfg["projector"] = serial
                    CONFIG.write_text(json.dumps(cfg, indent=2))
                    print(f"projector moved; now {serial}", flush=True)
                    continue
        time.sleep(20)


if __name__ == "__main__":
    threading.Thread(target=keep_tunnel, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"relay on 127.0.0.1:{PORT} for {', '.join(LIGHTS)}", flush=True)
    server.serve_forever()
