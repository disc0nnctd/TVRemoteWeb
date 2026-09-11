#!/system/bin/sh
# TVRemoteWeb — authenticated launcher for the Beem/SoftWinner HDMI inputs.

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"
LIVE_PKG="com.softwinner.awlivetv"
LIVE_ACTIVITY="$LIVE_PKG/.MainActivity"
SOURCE_ACTIVITY="com.softwinner.awsource/.MainActivity"

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
  echo "Status: 403 Forbidden"; echo "Content-Type: application/json"; echo; echo '{"status":"err","detail":"forbidden"}'; exit 0
fi

installed() { pm path "$1" >/dev/null 2>&1; }
disabled() { pm list packages -d 2>/dev/null | "$BB" grep -qx "package:$1"; }
as_bool() { if "$@"; then printf true; else printf false; fi; }

action="$(get_param action 2>/dev/null || true)"
status="ok"; detail="HDMI inputs are ready."

case "$action" in
  ''|status) ;;
  picker)
    if am start --user 0 -n "$SOURCE_ACTIVITY" --activity-new-task >/dev/null 2>&1; then
      detail="Input selector opened on the projector."
    else
      status="err"; detail="The built-in input selector could not open."
    fi ;;
  hdmi1|hdmi2|hdmi3)
    if ! installed "$LIVE_PKG"; then
      status="err"; detail="AwLiveTV is missing from the projector firmware."
    else
      if disabled "$LIVE_PKG"; then pm enable --user 0 "$LIVE_PKG" >/dev/null 2>&1; fi
      source="$(printf '%s' "$action" | tr '[:lower:]' '[:upper:]')"
      if am start --user 0 -n "$LIVE_ACTIVITY" \
          --es input_source "$source" --ez manual_set_source true \
          --activity-new-task --activity-clear-top >/dev/null 2>&1; then
        detail="$source selected."
      else
        status="err"; detail="$source could not be selected."
      fi
    fi ;;
  *) status="err"; detail="Unknown HDMI action." ;;
esac

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo "Cache-Control: no-store"
echo
printf '{"status":"%s","detail":"%s","available":%s,"enabled":%s}\n' \
  "$status" "$detail" "$(as_bool installed "$LIVE_PKG")" "$(if installed "$LIVE_PKG" && ! disabled "$LIVE_PKG"; then printf true; else printf false; fi)"
