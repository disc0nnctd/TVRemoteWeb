#!/system/bin/sh
# TVRemoteWeb — boot service.
# Publishes the web remote over LAN and starts the pointer daemon.
# SPDX-License-Identifier: MIT

MODDIR="${0%/*}"
BB="/data/adb/magisk/busybox"
STATE="/data/adb/tvremoteweb"
WWW="$STATE/www"
CGI="$WWW/cgi-bin"
PORT="${TVR_PORT:-8787}"
WSPORT="${TVR_WS_PORT:-8788}"
LOG="$STATE/httpd.log"
TOKEN_FILE="$STATE/token"
URL_FILE="$STATE/url.txt"
CONFIG_FILE="$STATE/settings.conf"

mkdir -p "$CGI"

# settings.conf may override PORT / WSPORT / SPLASH
if [ -f "$CONFIG_FILE" ]; then
  v="$("$BB" sed -n 's/^port=//p' "$CONFIG_FILE" 2>/dev/null | head -n1)";    [ -n "$v" ] && PORT="$v"
  v="$("$BB" sed -n 's/^ws_port=//p' "$CONFIG_FILE" 2>/dev/null | head -n1)"; [ -n "$v" ] && WSPORT="$v"
fi

# ------------------------------------------------ sync assets into www ----
for c in "$MODDIR"/files/cgi-bin/*.cgi; do
  [ -f "$c" ] || continue
  cp "$c" "$CGI/$(basename "$c")"
  chmod 755 "$CGI/$(basename "$c")"
done
for a in "$MODDIR"/files/*.js "$MODDIR"/files/*.html "$MODDIR"/files/*.json; do
  [ -f "$a" ] || continue
  cp "$a" "$WWW/$(basename "$a")"
  chmod 644 "$WWW/$(basename "$a")"
done

# ------------------------------------------------------------- token ----
PIN=""
if [ -s "$TOKEN_FILE" ]; then
  TOKEN="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$TOKEN" ] && PIN="$(printf '%s' "$TOKEN" | sha256sum | cut -c1-6)"
fi

# ---------------------------------------------------------------- IP ----
resolve_ip() {
  for dev in wlan0 eth0; do
    addr="$("$BB" ip -o -4 addr show dev "$dev" scope global 2>/dev/null | "$BB" awk '{print $4}' | "$BB" awk -F/ '{print $1}' | head -n1)"
    [ -n "$addr" ] && { echo "$addr"; return 0; }
  done
  addr="$("$BB" ip -o -4 addr show scope global 2>/dev/null | "$BB" awk '{print $4}' | "$BB" awk -F/ '{print $1}' | head -n1)"
  [ -n "$addr" ] && { echo "$addr"; return 0; }
  return 1
}

IP=""
i=0
while [ "$i" -lt 30 ]; do
  IP="$(resolve_ip)"
  [ -n "$IP" ] && break
  sleep 1
  i=$((i + 1))
done
[ -z "$IP" ] && IP="127.0.0.1"

REMOTE_URL="http://${IP}:${PORT}/remote.html"
[ -n "$PIN" ] && REMOTE_URL="${REMOTE_URL}?token=${PIN}"
QR_URL="http://${IP}:${PORT}/cgi-bin/qr.cgi?mode=splash"

# ------------------------------------------------------------- httpd ----
ps -A -o PID,ARGS 2>/dev/null \
  | "$BB" grep -F "httpd -p 0.0.0.0:${PORT}" \
  | "$BB" grep -v "grep -F" \
  | "$BB" awk '{print $1}' \
  | while read -r pid; do [ -n "$pid" ] && kill "$pid" >/dev/null 2>&1; done

"$BB" httpd -p "0.0.0.0:${PORT}" -h "$WWW"
echo "[$("$BB" date)] httpd on ${REMOTE_URL}" >> "$LOG"

cat > "$URL_FILE" <<EOF
remote_url=${REMOTE_URL}
qr_url=${QR_URL}
ip=${IP}
port=${PORT}
ws_port=${WSPORT}
token_pin=${PIN}
generated_at=$("$BB" date)
EOF
chmod 600 "$URL_FILE"

command -v log >/dev/null 2>&1 && log -t tvremoteweb "remote_url=${REMOTE_URL}"

# ------------------------------------------------------- mousedaemon ----
MOUSED="$MODDIR/files/bin/mousedaemon"
if [ -x "$MOUSED" ]; then
  ps -A -o PID,ARGS 2>/dev/null \
    | "$BB" grep -F "$MOUSED" \
    | "$BB" grep -v "grep -F" \
    | "$BB" awk '{print $1}' \
    | while read -r pid; do [ -n "$pid" ] && kill "$pid" >/dev/null 2>&1; done

  MP="$STATE/mousedaemon.log"
  TVR_WS_PORT="$WSPORT" TVR_TOKEN="$PIN" nohup "$MOUSED" >> "$MP" 2>&1 &
  echo "[$("$BB" date)] mousedaemon on ${WSPORT}" >> "$MP"
fi

# ------------------------------------------------------- boot splash ----
# Opens the QR page in a browser ~25 s after boot so the address is visible
# on the TV itself. Disable by creating $STATE/no-splash, or from the
# remote's Apps tab.
if [ ! -f "$STATE/no-splash" ]; then
  (
    sleep 25
    [ -f "$STATE/no-splash" ] && exit 0
    am start -a android.intent.action.VIEW \
      -d "http://127.0.0.1:${PORT}/cgi-bin/qr.cgi?mode=splash" \
      -c android.intent.category.BROWSABLE \
      --activity-clear-top --activity-new-task >/dev/null 2>&1
    echo "[$("$BB" date)] splash launched" >> "$STATE/service.log" 2>/dev/null
  ) &
fi
