#!/system/bin/sh
# Room lights: forwards the remote's requests to the Home Assistant relay
# (tools/ha-relay on the owner's PC), which keeps tcp:8790 on this device's
# loopback open with `adb reverse`. The relay holds the Home Assistant token
# and only knows the configured lights; this side only checks the remote PIN.

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"
RELAY="http://127.0.0.1:8790"

urldecode() { "$BB" httpd -d "${1:-}"; }
get_param() {
  key="$1"; OLDIFS="$IFS"; IFS='&'
  for kv in $QUERY_STRING; do
    IFS="$OLDIFS"; k="${kv%%=*}"; v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$OLDIFS"; return 1
}

token_full=""; pin=""
if [ -s "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"; echo "Content-Type: text/plain"; echo; echo "forbidden"; exit 0
fi

# Pass everything except the PIN on to the relay.
forward=""
OLDIFS="$IFS"; IFS='&'
for kv in $QUERY_STRING; do
  case "${kv%%=*}" in token|action) ;; *) forward="${forward:+$forward&}$kv" ;; esac
done
IFS="$OLDIFS"
case "$(get_param action 2>/dev/null || true)" in
  set) path="/set" ;;
  scene) path="/scene" ;;
  *)   path="/lights" ;;
esac

echo "Content-Type: application/json"
echo "Cache-Control: no-store"
echo
"$BB" wget -q -T 10 -O - "$RELAY$path${forward:+?$forward}" 2>/dev/null ||
  printf '{"status":"err","detail":"Lights are offline: the PC running Home Assistant is not connected to the projector."}\n'
