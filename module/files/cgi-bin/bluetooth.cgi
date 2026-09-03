#!/system/bin/sh
# TVRemoteWeb — on-demand Bluetooth controls backed by Android system services.

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"

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

available() {
  pm list features 2>/dev/null | "$BB" grep -q 'android.hardware.bluetooth'
}
enabled() {
  value="$(settings get global bluetooth_on 2>/dev/null)"
  [ "$value" = "1" ] && return 0
  dumpsys bluetooth_manager 2>/dev/null | "$BB" grep -Eq '(^|[[:space:]])enabled:[[:space:]]*true'
}
as_bool() { if "$@"; then printf true; else printf false; fi; }
set_power() {
  mode="$1"
  svc bluetooth "$mode" >/dev/null 2>&1
}
open_settings() {
  target="$1"
  component="$(cmd package resolve-activity --brief -a "$target" 2>/dev/null | "$BB" grep -m1 -E '^[a-zA-Z0-9_.]+/')"
  if [ -z "$component" ] && [ "$target" != "android.settings.BLUETOOTH_SETTINGS" ]; then
    component="$(cmd package resolve-activity --brief -a android.settings.BLUETOOTH_SETTINGS 2>/dev/null | "$BB" grep -m1 -E '^[a-zA-Z0-9_.]+/')"
  fi
  if [ -z "$component" ]; then
    component="$(cmd package resolve-activity --brief -a android.settings.SETTINGS 2>/dev/null | "$BB" grep -m1 -E '^[a-zA-Z0-9_.]+/')"
  fi
  [ -n "$component" ] && am start --user 0 -n "$component" >/dev/null 2>&1
}

action="$(get_param action 2>/dev/null || true)"
status="ok"; detail="Bluetooth status loaded."
if ! available; then
  status="err"; detail="This device does not report Bluetooth hardware."
else
  case "$action" in
    ''|status) ;;
    enable)
      if set_power enable; then detail="Bluetooth is turning on."; else status="err"; detail="Bluetooth could not be enabled."; fi ;;
    disable)
      if set_power disable; then detail="Bluetooth is turning off."; else status="err"; detail="Bluetooth could not be disabled."; fi ;;
    pair)
      if open_settings android.settings.BLUETOOTH_PAIRING_SETTINGS; then detail="Bluetooth pairing settings opened on the projector."; else status="err"; detail="Bluetooth pairing settings could not be opened."; fi ;;
    settings)
      if open_settings android.settings.BLUETOOTH_SETTINGS; then detail="Bluetooth devices opened on the projector."; else status="err"; detail="Bluetooth settings could not be opened."; fi ;;
    *) status="err"; detail="Unknown Bluetooth action." ;;
  esac
fi

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo "Cache-Control: no-store"
echo
printf '{"status":"%s","detail":"%s","available":%s,"enabled":%s}\n' \
  "$status" "$detail" "$(as_bool available)" "$(as_bool enabled)"
