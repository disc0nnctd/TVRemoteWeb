# Beem Hermes agent

This is a local MCP control plane for a Hermes profile. Hermes and its model run
on `dcmini`/Predator; only ADB commands run on the projector. Nothing resident is
required beyond the projector's existing TCP ADB service.

The installed `beem` profile currently uses `gpt-5.6-luna` at low effort through the local
Codex load balancer, with the local `qwopus3.6-a3b-coder` llama.cpp endpoint as
a fallback. Qwopus is available, but its running server has a 16K context while
Hermes requires at least 64K; restart that server with `--ctx-size 65536` before
making it the primary model.

## Install

```bash
cd /home/notdc/projects/Beem470/agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The Hermes profile config launches the server as:

```yaml
mcp_servers:
  beem-projector:
    command: /home/notdc/projects/Beem470/agent/.venv/bin/python
    args: [-m, beem_agent.server]
    cwd: /home/notdc/projects/Beem470/agent
    timeout: 120
```

Start the dedicated agent from anywhere with:

```bash
beem --in /home/notdc/projects/Beem470 --tui
```

It remembers the projector's wireless ADB address and otherwise scans only the
current `/24` LAN for port 5555. Tailscale is not needed on the projector.
Every modifying MCP tool first runs the Magisk Wi-Fi/ADB preparation helper,
attempts the remembered wireless endpoint, and prefers Wi-Fi when it is
reachable. USB remains a bootstrap/fallback transport rather than a runtime
requirement.

For module maintenance, `inspect_tvremoteweb_install` compares repository,
installed-module, and live asset hashes and reports legacy-service conflicts.
After explicit approval, `deploy_tvremoteweb_runtime` refreshes only the
allow-listed scripts/web assets, disables the predecessor module reversibly,
restarts TVRemoteWeb, and returns a fresh inspection. It does not expose an
arbitrary device shell, replace ABI binaries, install the QR APK, or reboot.

The reference Beem unit also installs `device/beem-wireless-adb.sh` under
Magisk's `service.d` so Wi-Fi stays enabled and authenticated ADB TCP port 5555
returns after reboot. This exposes ADB to the trusted home LAN; never forward
that port to the internet.

## Visual keystone workflow

1. `show_keystone_view` opens the firmware's full-screen four-corner grid.
2. Take a phone photo that includes the complete projected rectangle and the
   complete physical screen/frame. Keep the phone as square to the screen as is
   practical, dim the room, and avoid reflections.
3. Give Hermes the local attachment path. `analyze_keystone_photo` detects the
   two nested quadrilaterals, creates an annotated overlay, and calculates a
   proposal without changing the projector.
4. Review `view_keystone_analysis`. If automatic detection is wrong, provide
   the four screen/projected corners manually as JSON.
5. Only after explicit confirmation, call `apply_keystone_proposal` with the
   returned proposal ID and `confirmation="APPLY"`.
6. `restore_previous_keystone` provides a confirmed rollback.

The firmware represents each corner as two edge insets in the range 0..500.
The server uses the current correction and a projective transform to map the
photographed projected image into the physical screen quadrilateral.

## Picture tuning workflow

`inspect_picture_settings` reads all 13 Allwinner PQ values: brightness,
contrast, saturation, hue, sharpness, backlight, temporal/spatial noise
reduction, dynamic contrast, black extension, dynamic backlight, color
temperature, and gamma. Gamma is enumerated as 1.8, 2.0, 2.1, 2.2, or 2.4.

`analyze_picture_photo` measures the photographed projection and creates a
conservative proposal without changing the device. Phone-camera exposure and
white balance can bias the result, so Hermes must show the metrics and every
proposed change. Only then may `apply_picture_proposal` be called with the
matching proposal ID and explicit `APPLY` confirmation. Each apply records a
complete rollback profile; `restore_previous_picture` requires `RESTORE`.

LTvLauncher's brightness scheduler is separate: it writes Android system
brightness/backlight keys and does not expose the Beem's full hardware PQ
profile.

## Safety

- No unrestricted shell tool is exposed to the model.
- Every write is range/allow-list checked.
- Configuration, keystone, and picture writes require an explicit confirmation token.
- Each keystone apply saves the previous values under
  `~/.local/state/beem-agent/keystone-backups.jsonl`.
- Each picture apply saves the previous values under
  `~/.local/state/beem-agent/picture-backups.jsonl`.
- Android screenshots show the framebuffer, not the physical projection; the
  keystone solver specifically expects a phone/camera photo.
