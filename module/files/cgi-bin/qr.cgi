#!/system/bin/sh
# Dynamic QR splash: reads current wlan0 IP + PIN + SSID on every request.
# Renders fullscreen splash HTML with client-side QR (qrcode.js).

BB="/data/adb/magisk/busybox"
PORT="${TVR_PORT:-8787}"
TOKEN_FILE="/data/adb/tvremoteweb/token"

# ---- PIN ----
pin=""
if [ -f "$TOKEN_FILE" ]; then
  tok="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$tok" ] && pin="$(printf '%s' "$tok" | sha256sum | cut -c1-6)"
fi

# ---- current IP ----
ip="$("$BB" ip -o -4 addr show dev wlan0 scope global 2>/dev/null | "$BB" awk '{print $4}' | "$BB" awk -F/ '{print $1}' | head -n 1)"
[ -z "$ip" ] && ip="$("$BB" ip -o -4 addr show scope global 2>/dev/null | "$BB" awk '{print $4}' | "$BB" awk -F/ '{print $1}' | head -n 1)"
[ -z "$ip" ] && ip="127.0.0.1"

# ---- current wifi SSID ----
# Take only the first whitespace-delimited token after "SSID: " — the raw
# dumpsys line continues with BSSID/nid/state fields that are not comma-separated.
ssid="$(dumpsys wifi 2>/dev/null | "$BB" grep -oE 'SSID: [^ ,]+' | head -n 1 | "$BB" sed 's/^SSID: //; s/"//g')"
[ -z "$ssid" ] || [ "$ssid" = "<unknown" ] && ssid="$(dumpsys wifi 2>/dev/null | "$BB" grep -oE '"[^"]+"' | head -n 1 | "$BB" sed 's/"//g')"
[ -z "$ssid" ] && ssid="?"

# Remote URL is the primary target of the QR
remote_url="http://${ip}:${PORT}/remote.html"
[ -n "$pin" ] && remote_url="${remote_url}?token=${pin}"

# Query params — ?mode=splash for fullscreen boot splash styling
mode="mini"
case "$QUERY_STRING" in *mode=splash*|*splash=1*) mode="splash" ;; esac

echo "Content-Type: text/html; charset=utf-8"
echo "Cache-Control: no-cache"
echo

if [ "$mode" = "splash" ]; then
cat <<EOF
<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Android TV — Phone Remote</title>
<script src="/qrcode.js"></script>
<style>
  html,body{margin:0;padding:0;height:100%;background:#0b0d10;color:#e9edf1;font-family:sans-serif;overflow:hidden}
  .wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:2vh 2vw;box-sizing:border-box;text-align:center}
  h1{font-size:5vh;margin:0 0 1vh;letter-spacing:.5px}
  .sub{font-size:2.6vh;color:#9fb0c6;margin-bottom:2vh}
  .steps{font-size:2.4vh;color:#4c9dff;margin-bottom:2vh;line-height:1.6}
  .steps b{color:#fff}
  .card{background:#fff;padding:2vh;border-radius:2vh;box-shadow:0 20px 60px rgba(0,0,0,.5)}
  .card > div{width:52vh;height:52vh}
  .card svg{width:100%;height:100%;display:block}
  .info{margin-top:2vh;font-size:2vh;color:#c9d1d9;line-height:1.6}
  .info b{color:#4c9dff;font-family:monospace}
  .dismiss{position:fixed;bottom:1.5vh;right:2vw;color:#556677;font-size:1.6vh}
</style>
</head><body>
  <div class="wrap">
    <h1>📱 Control from your phone</h1>
    <div class="sub">Scan the QR below</div>
    <div class="steps">
      1. Join Wi-Fi: <b>${ssid}</b> &nbsp;•&nbsp; 2. Scan QR
    </div>
    <div class="card"><div id="qr"></div></div>
    <div class="info">
      or open <b>${ip}:${PORT}/remote.html</b> &nbsp; PIN: <b>${pin}</b>
    </div>
  </div>
  <div class="dismiss">Press BACK to dismiss</div>
<script>
(function(){
  var host = document.getElementById('qr');
  if (!host || typeof qrcode !== 'function') return;
  var qr = qrcode(0, 'M');
  qr.addData('${remote_url}');
  qr.make();
  host.innerHTML = qr.createSvgTag({cellSize: 8, margin: 4, scalable: true, alt: 'Remote QR'});
})();
</script>
</body></html>
EOF
else
# original compact mode (kept for backward-compat with existing links)
cat <<EOF
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="120">
  <title>TVRemoteWeb QR</title>
  <script src="/qrcode.js"></script>
  <style>
    :root { --bg:#05070b; --txt:#e7eefb; --muted:#9fb0c6; --line:#1f2a3d; --panel:#0f1521; }
    html, body { height:100%; }
    body { margin:0; background:var(--bg); color:var(--txt); font-family:system-ui,sans-serif; display:flex; align-items:center; justify-content:center; }
    .wrap { width:min(92vw,520px); text-align:center; padding:14px; }
    .box { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px; }
    .qr { width:min(84vw,460px); margin:0 auto; border-radius:8px; background:#fff; padding:10px; box-sizing:border-box; }
    .qr svg { width:100%; height:auto; display:block; }
    .url { margin-top:10px; font-size:12px; color:var(--muted); word-break:break-all; }
    .meta { margin-top:6px; font-size:11px; color:var(--muted); }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="box">
      <div id="qr_code" class="qr" aria-label="Dashboard QR"></div>
      <div class="url">${remote_url}</div>
      <div class="meta">Wi-Fi: ${ssid} &nbsp;•&nbsp; PIN: ${pin}</div>
    </div>
  </div>
  <script>
  (function() {
    var host = document.getElementById('qr_code');
    if (!host || typeof qrcode !== 'function') return;
    var qr = qrcode(0, 'M');
    qr.addData('${remote_url}');
    qr.make();
    host.innerHTML = qr.createSvgTag({cellSize: 8, margin: 8, scalable: true, alt: 'Dashboard QR', title: 'TVRemoteWeb dashboard QR'});
  })();
  </script>
</body>
</html>
EOF
fi
