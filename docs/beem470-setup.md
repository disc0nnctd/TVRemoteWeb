# Beem 470 setup and recovery

This records firmware-specific behavior confirmed on the rooted Beem 470 reference projector (Android 11, `armeabi-v7a`). Discover the current ADB serial with `adb devices`; do not assume its Wi-Fi address is permanent.

## HDMI inputs

The projector already contains both required system packages:

- `com.softwinner.awsource` — the HDMI/CVBS source picker
- `com.softwinner.awlivetv` — renders the selected external input

If the picker says **AwLiveTV is not installed**, the package is normally present but disabled. Restore it instead of downloading an APK:

```sh
adb -s SERIAL shell su -c 'pm enable --user 0 com.softwinner.awlivetv'
```

The vendor source picker opens with:

```sh
adb -s SERIAL shell input keyevent KEYCODE_TV_INPUT
```

Reverse-engineering the installed `AwSource.apk` confirmed its direct-input contract:

```sh
adb -s SERIAL shell am start --user 0 \
  -n com.softwinner.awlivetv/.MainActivity \
  --es input_source HDMI2 --ez manual_set_source true \
  --activity-new-task --activity-clear-top
```

Valid values are `HDMI1`, `HDMI2`, and `HDMI3`. TVRemoteWeb exposes the same allow-listed actions through `cgi-bin/hdmi.cgi`. The Phone Remote APK provides four entries in LTV Launcher: **HDMI Inputs** opens the firmware picker, while **HDMI 1**, **HDMI 2**, and **HDMI 3** switch directly to that port. These are short-lived activities and do not add a resident process.

Do not disable `com.softwinner.awlivetv` as a general RAM optimization: it consumes meaningful resources only while active, and disabling it breaks every HDMI port.

## Casting and remote recovery

Miracast changes the Wi-Fi radio into direct-display mode, so the LAN remote cannot remain reachable on this hardware. AirPlay and DLNA normally preserve LAN access.

To recover after Miracast, exit the receiver or reopen the projector's **Phone Remote QR** tile. Its local CGI request stops all firmware cast receivers, restores their disabled state, enables Wi-Fi, and releases receiver RAM. Reopening the phone browser alone cannot recover a Wi-Fi link that is already offline.

## Mouse reconnect behavior

The native pointer path is WebSocket port `8788` to `mousedaemon`. A newly visible browser replaces any stale controller connection, and hidden tabs close their socket. If movement feels delayed, confirm the header connection dot is online; HTTP fallback mouse events are substantially slower.

## Bluetooth

Pairing a phone to the projector does not transport TVRemoteWeb's browser/WebSocket traffic. Projector Bluetooth is useful for speakers, remotes, and keyboards. If audio is already paired directly to the laptop feeding HDMI, keep projector Bluetooth off to save memory and avoid routing ambiguity.

## Play Store and Prime Video

The RAM-saving configuration may disable these preinstalled Google packages:

- `com.android.vending`
- `com.google.android.gms`
- `com.google.android.gsf`

They may be temporarily enabled for a trusted Play Store installation, but Play requires a Google account. Never collect account credentials through ADB or automation. Restore the prior enabled/disabled states after installation; first verify that the installed streaming app still launches and completes DRM playback without the Google services it requires.

Prime Video was not installed during the 2026-09-03 check because Play Store sign-in was unavailable. Do not sideload an unverified APK as a shortcut.

## Safe state checks

Prefer read-only checks before changing firmware state:

```sh
adb -s SERIAL shell su -c 'pm list packages -d | grep -E "awlivetv|vending|com.google.android.gms|com.google.android.gsf"'
adb -s SERIAL shell su -c 'dumpsys tv_input'
adb -s SERIAL shell su -c 'ps -A -o PID,ARGS | grep -E "httpd.*8787|mousedaemon|miracastReceiver|eairplay|emedia" | grep -v grep'
```

Avoid killing system processes from the process monitor unless their role is known. The monitor is intentionally collapsed at the bottom of Tools and requires the remote PIN again.
