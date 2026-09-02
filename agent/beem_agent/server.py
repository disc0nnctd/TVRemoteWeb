from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from mcp.server.fastmcp import FastMCP, Image

from .geometry import DetectedQuads, detect_screen_and_projection, draw_detection, order_quad, solve_insets


STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "beem-agent"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DEVICE_FILE = STATE_DIR / "device.json"
PROPOSAL_FILE = STATE_DIR / "keystone-proposal.json"
BACKUP_FILE = STATE_DIR / "keystone-backups.jsonl"
VIEW_STATE_FILE = STATE_DIR / "keystone-view-state.json"
PICTURE_PROPOSAL_FILE = STATE_DIR / "picture-proposal.json"
PICTURE_BACKUP_FILE = STATE_DIR / "picture-backups.jsonl"

ADB = os.environ.get("ADB", "adb")
MODEL = "ADT_3"
CORRECTION_ACTIVITY = "com.htc.htcsettings/com.htc.activity.CorrectionActivity"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = PROJECT_ROOT / "module"
REMOTE_MODULE = "/data/adb/modules/tvremoteweb"
REMOTE_STATE = "/data/adb/tvremoteweb"
LEGACY_MODULE = "/data/adb/modules/beem470-control"
PQCLI_REMOTE = f"{REMOTE_MODULE}/files/pqcli.dex"
PQ_APK = "/product/app/HtcSettingsBlue/HtcSettingsBlue.apk"

PICTURE_CHANNELS = {
    "brightness": (1, 0, 100),
    "contrast": (2, 0, 100),
    "saturation": (3, 0, 100),
    "hue": (4, 0, 100),
    "sharpness": (5, 0, 100),
    "backlight": (6, 0, 100),
    "tnr": (7, 0, 3),
    "snr": (8, 0, 3),
    "dci": (9, 0, 3),
    "black_extension": (10, 0, 3),
    "dynamic_backlight": (11, 0, 1),
    "color_temperature": (12, 0, 2),
    "gamma": (13, 0, 4),
}
GAMMA_LABELS = ("1.8", "2.0", "2.1", "2.2", "2.4")

# Only files that are safe to refresh on a running installation. ABI selection,
# token generation, and APK installation remain responsibilities of Magisk's
# installer and are deliberately excluded from the live-deploy tool.
RUNTIME_ASSETS = {
    "module.prop": 0o644,
    "service.sh": 0o755,
    "uninstall.sh": 0o755,
    "files/remote.html": 0o644,
    "files/keystone.js": 0o644,
    "files/qrcode.js": 0o644,
    "files/pqcli.dex": 0o644,
    "files/cgi-bin/apps.cgi": 0o755,
    "files/cgi-bin/keystone.cgi": 0o755,
    "files/cgi-bin/qr.cgi": 0o755,
    "files/cgi-bin/remote.cgi": 0o755,
    "files/cgi-bin/settings.cgi": 0o755,
    "files/cgi-bin/stats.cgi": 0o755,
}

INSPECT_ASSETS = (
    "service.sh",
    "files/remote.html",
    "files/keystone.js",
    "files/pqcli.dex",
    "files/cgi-bin/keystone.cgi",
    "files/cgi-bin/settings.cgi",
)

DISPLAY_PROPS = {
    "lb": ("persist.display.keystone_lbx", "persist.display.keystone_lby"),
    "lt": ("persist.display.keystone_ltx", "persist.display.keystone_lty"),
    "rt": ("persist.display.keystone_rtx", "persist.display.keystone_rty"),
    "rb": ("persist.display.keystone_rbx", "persist.display.keystone_rby"),
}

mcp = FastMCP(
    "beem-projector",
    instructions=(
        "Scoped control plane for the rooted Beem 470 reference projector. Prefer read-only tools. "
        "All modifying tools automatically prepare persistent Wi-Fi ADB and prefer the wireless transport; "
        "do not ask the user to reconnect USB unless discovery reports that both cached Wi-Fi and LAN scan failed. "
        "Never call an apply/set tool without the user's explicit confirmation in the current conversation. "
        "For visual keystone correction: show_keystone_view, ask the user to take a phone photo containing "
        "the complete physical screen/frame and projected rectangle, analyze_keystone_photo, show the overlay "
        "and proposed values, then apply_keystone_proposal only after confirmation."
    ),
)


def _run(args: list[str], timeout: int = 20, check: bool = True, binary: bool = False) -> str | bytes:
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode != 0:
        message = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise RuntimeError(message or f"command failed with exit code {result.returncode}")
    return result.stdout if binary else result.stdout.decode(errors="replace").strip()


def _adb_devices() -> list[dict[str, str]]:
    output = str(_run([ADB, "devices", "-l"]))
    devices: list[dict[str, str]] = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2 or fields[1] != "device":
            continue
        record = {"serial": fields[0], "state": fields[1]}
        record.update(item.split(":", 1) for item in fields[2:] if ":" in item)
        devices.append(record)
    return devices


def _save_device(serial: str) -> None:
    DEVICE_FILE.write_text(json.dumps({"serial": serial, "updated_at": int(time.time())}, indent=2) + "\n")


def _cached_serial() -> str | None:
    try:
        return json.loads(DEVICE_FILE.read_text())["serial"]
    except (OSError, KeyError, ValueError, TypeError):
        return None


def _connect_candidate(host: str) -> bool:
    try:
        with socket.create_connection((host, 5555), timeout=0.08):
            return True
    except OSError:
        return False


def _lan_candidates() -> list[str]:
    route = str(_run(["ip", "-4", "route", "show", "default"], check=False))
    match = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", route)
    if not match:
        return []
    network = ipaddress.ip_network(match.group(1) + "/24", strict=False)
    hosts = [str(ip) for ip in network.hosts()]
    with ThreadPoolExecutor(max_workers=48) as pool:
        return [host for host, open_ in zip(hosts, pool.map(_connect_candidate, hosts)) if open_]


def _resolve_device(scan: bool = True) -> str:
    devices = _adb_devices()
    cached = _cached_serial()
    for device in devices:
        if device["serial"] == cached:
            return cached
    for device in devices:
        if ":" in device["serial"] and device.get("model") == MODEL:
            _save_device(device["serial"])
            return device["serial"]
    for device in devices:
        if device.get("model") != MODEL:
            continue
        serial = device["serial"]
        ip_output = str(_run([ADB, "-s", serial, "shell", "ip", "-o", "-4", "addr", "show", "wlan0"]))
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", ip_output)
        if match:
            wireless = match.group(1) + ":5555"
            _run([ADB, "connect", wireless], check=False)
            if any(item["serial"] == wireless for item in _adb_devices()):
                _save_device(wireless)
                return wireless
        return serial
    if cached:
        _run([ADB, "connect", cached], timeout=5, check=False)
        if any(item["serial"] == cached for item in _adb_devices()):
            return cached
    if scan:
        for host in _lan_candidates():
            serial = host + ":5555"
            _run([ADB, "connect", serial], timeout=5, check=False)
            try:
                model = str(_run([ADB, "-s", serial, "shell", "getprop", "ro.product.model"], timeout=5))
            except RuntimeError:
                continue
            if model == "ADT-3":
                _save_device(serial)
                return serial
    raise RuntimeError("Beem 470 not found over USB, cached wireless ADB, or the local /24 network")


def _adb_shell(serial: str, command: str, root: bool = False, timeout: int = 20) -> str:
    interpreter = "su" if root else "sh"
    # adb shell flattens argv into a remote command line. Quote the complete
    # script once so sh/su receives it as the single argument to -c.
    remote = f"{interpreter} -c {shlex.quote(command)}"
    args = [ADB, "-s", serial, "shell", remote]
    return str(_run(args, timeout=timeout))


def _prepare_device_for_change() -> str:
    """Ensure Wi-Fi ADB is persistent and prefer it before changing the unit."""
    serial = _resolve_device()
    helper = "/data/adb/service.d/beem-wireless-adb.sh"
    setup = (
        "settings put global wifi_sleep_policy 2; "
        "setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.port 5555; "
        f"if [ -r {helper} ]; then sh {helper}; "
        "else cmd wifi set-wifi-enabled enabled >/dev/null 2>&1; "
        "cmd wifi start-scan >/dev/null 2>&1; fi"
    )
    _adb_shell(serial, setup, root=True, timeout=30)

    ip_output = _adb_shell(serial, "ip -o -4 addr show wlan0", timeout=10)
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", ip_output)
    if match:
        wireless = match.group(1) + ":5555"
        _run([ADB, "connect", wireless], timeout=5, check=False)
        if any(item["serial"] == wireless for item in _adb_devices()):
            _save_device(wireless)
            return wireless
    return serial


def _shell(command: str, root: bool = False, timeout: int = 20, prepare_change: bool = False) -> str:
    serial = _prepare_device_for_change() if prepare_change else _resolve_device()
    return _adb_shell(serial, command, root=root, timeout=timeout)


def _getprop(name: str) -> str:
    return _shell(f"getprop {shlex.quote(name)}")


def _parse_pair(value: str, default: list[int] | None = None) -> list[int]:
    try:
        pair = [int(part.strip()) for part in value.split(",")]
        if len(pair) == 2:
            return pair
    except ValueError:
        pass
    return list(default or [0, 0])


def _current_insets() -> dict[str, list[int]]:
    zoom = _getprop("persist.sys.zoom.value")
    try:
        values = [int(part) for part in zoom.split(",")]
    except ValueError:
        values = []
    if len(values) == 8:
        return {"lb": values[0:2], "lt": values[2:4], "rt": values[4:6], "rb": values[6:8]}
    result: dict[str, list[int]] = {}
    for corner, props in DISPLAY_PROPS.items():
        result[corner] = [int(_getprop(props[0]) or 0), int(_getprop(props[1]) or 0)]
    return result


def _display_keystone_properties() -> dict[str, str]:
    return {prop: _getprop(prop) for props in DISPLAY_PROPS.values() for prop in props}


def _restore_display_keystone_properties(values: dict[str, str]) -> None:
    commands = [f"setprop {shlex.quote(prop)} {shlex.quote(value)}" for prop, value in values.items()]
    _shell("; ".join(commands), root=True, prepare_change=True)


def _validate_insets(insets: dict[str, list[int]]) -> None:
    if set(insets) != {"lt", "rt", "rb", "lb"}:
        raise ValueError("insets must contain lt, rt, rb, and lb")
    for corner, pair in insets.items():
        if len(pair) != 2 or any(not isinstance(value, int) for value in pair):
            raise ValueError(f"{corner} must be two integers")
        if any(value < 0 or value > 500 for value in pair):
            raise ValueError(f"{corner} values must stay in firmware range 0..500")


def _apply_insets(insets: dict[str, list[int]]) -> None:
    _validate_insets(insets)
    before = _current_insets()
    backup = {"timestamp": int(time.time()), "serial": _resolve_device(), "before": before, "after": insets}
    with BACKUP_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(backup, sort_keys=True) + "\n")
    ordered = insets["lb"] + insets["lt"] + insets["rt"] + insets["rb"]
    csv = ",".join(str(value) for value in ordered)
    floats = " ".join(f"f {value / 500.0:.6f}" for value in ordered)
    command = f"setprop persist.sys.zoom.value {shlex.quote(csv)}; service call SurfaceFlinger 1050 {floats}"
    _shell(command, root=True, prepare_change=True)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _parse_module_prop(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in value.splitlines():
        if "=" not in line:
            continue
        key, item = line.split("=", 1)
        result[key.strip()] = item.strip()
    return result


def _local_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remote_hash(serial: str, path: str) -> str | None:
    quoted = shlex.quote(path)
    value = _adb_shell(
        serial,
        f"if [ -f {quoted} ]; then sha256sum {quoted} | cut -d ' ' -f 1; fi",
        root=True,
    )
    return value or None


def _picture_command(arguments: str, *, prepare_change: bool = False) -> str:
    classpath = f"{PQCLI_REMOTE}:{PQ_APK}"
    command = f"CLASSPATH={shlex.quote(classpath)} app_process /system/bin com.tvremote.PqCli {arguments}"
    return _shell(command, root=True, prepare_change=prepare_change)


def _picture_status() -> dict[str, int]:
    output = _picture_command("status")
    by_channel: dict[int, int] = {}
    for line in output.splitlines():
        match = re.fullmatch(r"(\d+)=(\d+)", line.strip())
        if match:
            by_channel[int(match.group(1))] = int(match.group(2))
    values = {name: by_channel[channel] for name, (channel, _, _) in PICTURE_CHANNELS.items() if channel in by_channel}
    if len(values) != len(PICTURE_CHANNELS):
        missing = sorted(set(PICTURE_CHANNELS) - set(values))
        raise RuntimeError(f"vendor picture service returned an incomplete profile: {missing}")
    return values


def _validate_picture_values(values: dict[str, int], *, complete: bool = True) -> dict[str, int]:
    if complete and set(values) != set(PICTURE_CHANNELS):
        missing = sorted(set(PICTURE_CHANNELS) - set(values))
        extra = sorted(set(values) - set(PICTURE_CHANNELS))
        raise ValueError(f"picture profile mismatch; missing={missing}, extra={extra}")
    validated: dict[str, int] = {}
    for name, value in values.items():
        if name not in PICTURE_CHANNELS or isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"invalid picture setting {name!r}")
        _, low, high = PICTURE_CHANNELS[name]
        if not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}")
        validated[name] = value
    return validated


def _write_picture_values(values: dict[str, int], *, save_backup: bool = True) -> dict[str, int]:
    values = _validate_picture_values(values)
    before = _picture_status()
    if save_backup:
        record = {"timestamp": int(time.time()), "serial": _resolve_device(), "before": before, "after": values}
        with PICTURE_BACKUP_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    changed: list[str] = []
    try:
        for name, (channel, _, _) in PICTURE_CHANNELS.items():
            if values[name] == before[name]:
                continue
            _picture_command(f"set {channel} {values[name]}", prepare_change=True)
            changed.append(name)
    except Exception:
        for name in changed:
            channel = PICTURE_CHANNELS[name][0]
            _picture_command(f"set {channel} {before[name]}", prepare_change=True)
        raise
    return _picture_status()


def _suggest_picture_settings(metrics: dict[str, float], current: dict[str, int]) -> tuple[dict[str, int], list[str]]:
    proposed = dict(current)
    reasons: list[str] = []
    p5, p50, p95 = metrics["luma_p5"], metrics["luma_p50"], metrics["luma_p95"]
    if p50 < 82:
        proposed["brightness"] = min(100, current["brightness"] + 7)
        proposed["gamma"] = max(0, current["gamma"] - 1)
        reasons.append("dark midtones: raise brightness and, when possible, use a brighter gamma curve")
    elif p50 > 178:
        proposed["brightness"] = max(0, current["brightness"] - 7)
        proposed["gamma"] = min(4, current["gamma"] + 1)
        reasons.append("over-bright midtones: reduce brightness and use a darker gamma curve")
    if metrics["highlight_clip"] > 0.045:
        proposed["contrast"] = max(0, current["contrast"] - 6)
        reasons.append("highlight clipping: lower contrast")
    elif p95 - p5 < 105:
        proposed["contrast"] = min(100, current["contrast"] + 5)
        proposed["dci"] = min(2, max(1, current["dci"]))
        reasons.append("low tonal spread: add modest contrast and dynamic contrast")
    if metrics["shadow_clip"] > 0.075:
        proposed["black_extension"] = max(0, current["black_extension"] - 1)
        proposed["dci"] = max(0, current["dci"] - 1)
        reasons.append("crushed shadows: reduce black extension and dynamic contrast")
    if metrics["mean_saturation"] < 42:
        proposed["saturation"] = min(100, current["saturation"] + 5)
        reasons.append("low color saturation: add a small saturation increase")
    elif metrics["mean_saturation"] > 125:
        proposed["saturation"] = max(0, current["saturation"] - 5)
        reasons.append("excessive color saturation: reduce saturation")
    if metrics["laplacian_variance"] < 65:
        proposed["sharpness"] = min(65, current["sharpness"] + 5)
        reasons.append("soft edges: add limited sharpening")
    red, blue = metrics["mean_red"], metrics["mean_blue"]
    if blue > red * 1.14:
        proposed["color_temperature"] = 2
        reasons.append("strong blue cast: propose the warm color-temperature preset")
    elif red > blue * 1.14:
        proposed["color_temperature"] = 1
        reasons.append("strong red cast: propose the cool color-temperature preset")
    return _validate_picture_values(proposed), reasons or ["photo metrics are balanced; keep the current picture profile"]


@mcp.tool()
def discover_projector(scan_local_network: bool = True) -> str:
    """Find Beem over USB/cached Wi-Fi; optionally scan only the current /24 for ADB port 5555."""
    serial = _resolve_device(scan=scan_local_network)
    return _json({"serial": serial, "wireless": ":" in serial, "model": _shell("getprop ro.product.model")})


@mcp.tool()
def projector_status() -> str:
    """Read device, network, memory, root, camera, and keystone status."""
    serial = _resolve_device()
    mem = _shell("awk '/MemTotal|MemAvailable/ {print $1 $2}' /proc/meminfo")
    ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", _shell("ip -o -4 addr show wlan0"))
    return _json(
        {
            "serial": serial,
            "wireless_ip": ip_match.group(1) if ip_match else None,
            "model": _shell("getprop ro.product.model"),
            "android": _shell("getprop ro.build.version.release"),
            "abi": _shell("getprop ro.product.cpu.abi"),
            "memory": mem.splitlines(),
            "root": "uid=0" in _shell("id", root=True),
            "camera_ok": _getprop("persist.sys.camok") == "1",
            "onboard_auto_keystone": _getprop("persist.sys.tpryauto") == "1",
            "keystone_insets": _current_insets(),
        }
    )


@mcp.tool()
def get_projector_configuration() -> str:
    """Read the approved user-facing configuration and keystone state."""
    values = {
        "screen_brightness": _shell("settings get system screen_brightness"),
        "screen_off_timeout": _shell("settings get system screen_off_timeout"),
        "user_rotation": _shell("settings get system user_rotation"),
        "screensaver_enabled": _shell("settings get secure screensaver_enabled"),
        "onboard_auto_keystone": _getprop("persist.sys.tpryauto"),
        "camera_ok": _getprop("persist.sys.camok"),
        "keystone_insets": _current_insets(),
    }
    return _json(values)


@mcp.tool()
def set_projector_configuration(name: str, value: int, confirmation: str) -> str:
    """Set one approved config value. Requires confirmation='APPLY' after showing the proposed change."""
    if confirmation != "APPLY":
        raise ValueError("show the proposed change and obtain explicit user confirmation, then pass confirmation='APPLY'")
    settings = {
        "screen_brightness": ("system", 1, 255),
        # 2^31-1 ms is Android's conventional practical "never" value.
        "screen_off_timeout": ("system", 60_000, 2_147_483_647),
        "user_rotation": ("system", 0, 3),
        "screensaver_enabled": ("secure", 0, 1),
    }
    if name == "onboard_auto_keystone":
        if value not in (0, 1):
            raise ValueError("onboard_auto_keystone must be 0 or 1")
        if value == 1 and _getprop("persist.sys.camok") != "1":
            raise ValueError("firmware reports no onboard camera; auto keystone cannot be enabled")
        _shell(f"setprop persist.sys.tpryauto {value}", root=True, prepare_change=True)
    elif name in settings:
        namespace, low, high = settings[name]
        if not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}")
        _shell(f"settings put {namespace} {shlex.quote(name)} {value}", root=True, prepare_change=True)
    else:
        raise ValueError(f"unsupported setting {name!r}; use get_projector_configuration")
    return get_projector_configuration()


@mcp.tool()
def inspect_picture_settings() -> str:
    """Read the Beem's complete Allwinner hardware picture-quality profile without changing it."""
    values = _picture_status()
    return _json({"values": values, "gamma_label": GAMMA_LABELS[values["gamma"]], "ranges": PICTURE_CHANNELS})


@mcp.tool()
def analyze_picture_photo(image_path: str, projection_corners_json: str = "") -> str:
    """Analyze a phone photo of the projected image and create a conservative picture proposal; never applies it.

    Camera exposure and white balance can bias the measurements. For best results, show a known test image,
    include the full projected rectangle, avoid reflections, and review the proposal before applying.
    Optionally pass four projection corners as a JSON array of [x,y] points when automatic detection is ambiguous.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"image not found: {path}")
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError("unsupported or unreadable image")
    if projection_corners_json.strip():
        projection = order_quad(json.loads(projection_corners_json)).astype(np.float32)
        confidence = 1.0
    else:
        detected = detect_screen_and_projection(image)
        projection = detected.projection.astype(np.float32)
        confidence = float(detected.confidence)
    tl, tr, br, bl = projection
    width = max(64, int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    height = max(64, int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    matrix = cv2.getPerspectiveTransform(projection, target)
    crop = cv2.warpPerspective(image, matrix, (width, height))
    margin_y, margin_x = max(1, height // 20), max(1, width // 20)
    sample = crop[margin_y : height - margin_y, margin_x : width - margin_x]
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
    p1, p5, p50, p95, p99 = np.percentile(gray, [1, 5, 50, 95, 99])
    mean_blue, mean_green, mean_red = sample.reshape(-1, 3).mean(axis=0)
    metrics = {
        "luma_p1": round(float(p1), 2),
        "luma_p5": round(float(p5), 2),
        "luma_p50": round(float(p50), 2),
        "luma_p95": round(float(p95), 2),
        "luma_p99": round(float(p99), 2),
        "shadow_clip": round(float(np.mean(gray <= 5)), 4),
        "highlight_clip": round(float(np.mean(gray >= 250)), 4),
        "mean_saturation": round(float(hsv[:, :, 1].mean()), 2),
        "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
        "mean_red": round(float(mean_red), 2),
        "mean_green": round(float(mean_green), 2),
        "mean_blue": round(float(mean_blue), 2),
    }
    current = _picture_status()
    proposed, reasons = _suggest_picture_settings(metrics, current)
    digest = hashlib.sha256((str(path) + json.dumps(metrics, sort_keys=True) + str(time.time_ns())).encode()).hexdigest()[:16]
    proposal = {
        "proposal_id": digest,
        "source_image": str(path),
        "projection_corners": projection.tolist(),
        "detection_confidence": round(confidence, 3),
        "metrics": metrics,
        "current": current,
        "proposed": proposed,
        "gamma_current": GAMMA_LABELS[current["gamma"]],
        "gamma_proposed": GAMMA_LABELS[proposed["gamma"]],
        "reasons": reasons,
        "warning": "Phone cameras auto-adjust exposure and white balance. Treat this as a proposal, inspect the image, and apply only after explicit confirmation.",
    }
    PICTURE_PROPOSAL_FILE.write_text(_json(proposal) + "\n")
    return _json(proposal)


@mcp.tool()
def apply_picture_proposal(proposal_id: str, confirmation: str) -> str:
    """Apply the latest photo-derived picture proposal. Requires its ID and confirmation='APPLY'."""
    if confirmation != "APPLY":
        raise ValueError("show the complete picture proposal and obtain explicit confirmation, then pass confirmation='APPLY'")
    proposal = json.loads(PICTURE_PROPOSAL_FILE.read_text())
    if proposal_id != proposal["proposal_id"]:
        raise ValueError("proposal ID does not match the latest picture analysis")
    applied = _write_picture_values(proposal["proposed"])
    return _json({"applied": proposal_id, "values": applied, "backup_file": str(PICTURE_BACKUP_FILE)})


@mcp.tool()
def restore_previous_picture(confirmation: str) -> str:
    """Restore the most recent pre-apply hardware picture profile. Requires confirmation='RESTORE'."""
    if confirmation != "RESTORE":
        raise ValueError("obtain explicit user confirmation, then pass confirmation='RESTORE'")
    lines = [line for line in PICTURE_BACKUP_FILE.read_text().splitlines() if line.strip()]
    if not lines:
        raise ValueError("no picture backup exists")
    backup = json.loads(lines[-1])
    restored = _write_picture_values(backup["before"], save_backup=False)
    return _json({"restored": restored})


@mcp.tool()
def inspect_tvremoteweb_install() -> str:
    """Compare repository, installed-module, and live TVRemoteWeb assets without changing the projector."""
    serial = _resolve_device()
    module_prop = _parse_module_prop(
        _adb_shell(serial, f"cat {REMOTE_MODULE}/module.prop 2>/dev/null", root=True)
    )
    legacy_state = _adb_shell(
        serial,
        f"if [ ! -d {LEGACY_MODULE} ]; then echo absent; "
        f"elif [ -e {LEGACY_MODULE}/disable ]; then echo disabled; else echo enabled; fi",
        root=True,
    )
    processes = _adb_shell(
        serial,
        "ps -A -o PID,ARGS 2>/dev/null | grep -E 'httpd.*8787|mousedaemon' | grep -v grep || true",
        root=True,
    ).splitlines()

    assets: dict[str, dict[str, Any]] = {}
    for relative in INSPECT_ASSETS:
        source = MODULE_SOURCE / relative
        installed = f"{REMOTE_MODULE}/{relative}"
        live_relative = relative.removeprefix("files/")
        publicly_served = relative.startswith("files/cgi-bin/") or source.suffix in {".html", ".js", ".json"}
        live = f"{REMOTE_STATE}/www/{live_relative}" if publicly_served else None
        source_hash = _local_hash(source) if source.is_file() else None
        installed_hash = _remote_hash(serial, installed)
        live_hash = _remote_hash(serial, live) if live else None
        assets[relative] = {
            "source": source_hash,
            "installed": installed_hash,
            "live": live_hash,
            "installed_matches_source": bool(source_hash and installed_hash == source_hash),
            "live_matches_source": None if live is None else bool(source_hash and live_hash == source_hash),
        }

    return _json(
        {
            "serial": serial,
            "module": module_prop or None,
            "legacy_module": legacy_state,
            "processes": processes,
            "assets": assets,
        }
    )


@mcp.tool()
def deploy_tvremoteweb_runtime(confirmation: str) -> str:
    """Deploy allow-listed runtime assets and restart TVRemoteWeb. Requires confirmation='DEPLOY'."""
    if confirmation != "DEPLOY":
        raise ValueError("inspect first and obtain explicit deployment approval, then pass confirmation='DEPLOY'")

    serial = _prepare_device_for_change()
    present = _adb_shell(
        serial,
        f"if [ -d {REMOTE_MODULE} ]; then echo yes; else echo no; fi",
        root=True,
    )
    if present != "yes":
        raise RuntimeError("TVRemoteWeb is not installed; flash the repository module ZIP through Magisk first")

    temporary: list[str] = []
    try:
        for index, (relative, mode) in enumerate(RUNTIME_ASSETS.items()):
            source = MODULE_SOURCE / relative
            if not source.is_file():
                raise RuntimeError(f"required runtime asset is missing: {relative}")
            temp = f"/data/local/tmp/tvremoteweb-deploy-{index}"
            temporary.append(temp)
            _run([ADB, "-s", serial, "push", str(source), temp], timeout=30)
            destination = f"{REMOTE_MODULE}/{relative}"
            _adb_shell(
                serial,
                f"mkdir -p {shlex.quote(str(Path(destination).parent))}; "
                f"cp {shlex.quote(temp)} {shlex.quote(destination)}; "
                f"chmod {mode:o} {shlex.quote(destination)}",
                root=True,
            )
    finally:
        if temporary:
            quoted = " ".join(shlex.quote(path) for path in temporary)
            _adb_shell(serial, f"rm -f {quoted}", root=True, timeout=10)

    _adb_shell(
        serial,
        f"if [ -d {LEGACY_MODULE} ]; then touch {LEGACY_MODULE}/disable; fi; "
        "pkill mousedaemon 2>/dev/null || true; "
        f"sh {REMOTE_MODULE}/service.sh </dev/null >/dev/null 2>&1",
        root=True,
        timeout=30,
    )
    time.sleep(0.5)
    return inspect_tvremoteweb_install()


@mcp.tool()
def show_keystone_view() -> str:
    """Open the firmware's full-screen four-corner correction grid for a phone photo."""
    VIEW_STATE_FILE.write_text(_json({"display_properties": _display_keystone_properties()}) + "\n")
    result = _shell(f"am start -W -n {CORRECTION_ACTIVITY}", root=True, timeout=30, prepare_change=True)
    return _json({"shown": "Status: ok" in result, "instructions": "Photograph the complete physical screen/frame and all four projected corners."})


@mcp.tool()
def close_keystone_view() -> str:
    """Return Home and restore vendor properties saved before opening the correction UI."""
    _shell("input keyevent KEYCODE_HOME", prepare_change=True)
    restored = False
    if VIEW_STATE_FILE.is_file():
        state = json.loads(VIEW_STATE_FILE.read_text())
        _restore_display_keystone_properties(state["display_properties"])
        VIEW_STATE_FILE.unlink()
        restored = True
    return _json({"closed": True, "method": "HOME", "vendor_properties_restored": restored})


@mcp.tool()
def capture_projector_screen() -> Image:
    """Capture Android's framebuffer for UI diagnostics (not a photo of the physical projection)."""
    serial = _resolve_device()
    path = STATE_DIR / f"screen-{int(time.time())}.png"
    data = _run([ADB, "-s", serial, "exec-out", "screencap", "-p"], timeout=30, binary=True)
    path.write_bytes(bytes(data))
    return Image(path=str(path))


def _parse_corners(value: str) -> list[list[float]] | None:
    if not value.strip():
        return None
    parsed = json.loads(value)
    return order_quad(parsed).tolist()


@mcp.tool()
def analyze_keystone_photo(
    image_path: str,
    screen_corners_json: str = "",
    projection_corners_json: str = "",
) -> str:
    """Analyze a phone photo and propose firmware insets; does not change the projector.

    By default detects the nested physical-screen and projected-image quadrilaterals.
    If detection is ambiguous, pass either/both corners as JSON arrays of four [x,y]
    points; point order may be arbitrary.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"image not found: {path}")
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError("unsupported or unreadable image")
    screen = _parse_corners(screen_corners_json)
    projection = _parse_corners(projection_corners_json)
    confidence = 1.0
    if screen is None or projection is None:
        detected = detect_screen_and_projection(image)
        screen = screen or detected.screen.tolist()
        projection = projection or detected.projection.tolist()
        confidence = detected.confidence
    current = _current_insets()
    proposed = solve_insets(projection, screen, current)
    detection = DetectedQuads(order_quad(screen), order_quad(projection), confidence)
    overlay = draw_detection(image, detection)
    digest = hashlib.sha256((str(path) + json.dumps(proposed, sort_keys=True) + str(time.time_ns())).encode()).hexdigest()[:16]
    overlay_path = STATE_DIR / f"keystone-{digest}.jpg"
    cv2.imwrite(str(overlay_path), overlay, [cv2.IMWRITE_JPEG_QUALITY, 92])
    proposal = {
        "proposal_id": digest,
        "source_image": str(path),
        "overlay_image": str(overlay_path),
        "confidence": round(float(confidence), 3),
        "screen_corners": screen,
        "projection_corners": projection,
        "current_insets": current,
        "proposed_insets": proposed,
        "warning": "Review the overlay. Applying correction shrinks/crops the image and should only follow explicit confirmation.",
    }
    PROPOSAL_FILE.write_text(_json(proposal) + "\n")
    return _json(proposal)


@mcp.tool()
def view_keystone_analysis() -> Image:
    """Return the most recent annotated phone photo for visual verification."""
    proposal = json.loads(PROPOSAL_FILE.read_text())
    return Image(path=proposal["overlay_image"])


@mcp.tool()
def apply_keystone_proposal(proposal_id: str, confirmation: str) -> str:
    """Apply the last analyzed correction. Requires matching ID and confirmation='APPLY'."""
    if confirmation != "APPLY":
        raise ValueError("obtain explicit user confirmation after showing the overlay, then pass confirmation='APPLY'")
    proposal = json.loads(PROPOSAL_FILE.read_text())
    if proposal_id != proposal["proposal_id"]:
        raise ValueError("proposal ID does not match the latest analysis; analyze the photo again")
    _apply_insets(proposal["proposed_insets"])
    return _json({"applied": proposal_id, "keystone_insets": _current_insets(), "backup_file": str(BACKUP_FILE)})


@mcp.tool()
def restore_previous_keystone(confirmation: str) -> str:
    """Restore the most recent pre-apply corner state. Requires confirmation='RESTORE'."""
    if confirmation != "RESTORE":
        raise ValueError("obtain explicit user confirmation, then pass confirmation='RESTORE'")
    lines = [line for line in BACKUP_FILE.read_text().splitlines() if line.strip()]
    if not lines:
        raise ValueError("no keystone backup exists")
    backup = json.loads(lines[-1])
    _apply_insets(backup["before"])
    return _json({"restored": backup["before"], "keystone_insets": _current_insets()})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
