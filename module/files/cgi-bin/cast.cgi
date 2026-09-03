#!/system/bin/sh
# TVRemoteWeb — zero-idle-overhead launcher for firmware casting receivers.
# No receiver is bundled or kept resident by this module.

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"
STATE="/data/adb/tvremoteweb"
ENABLED_BY_US="$STATE/cast-enabled-by-tvremoteweb"
WATCHDOG_PID="$STATE/cast-watchdog.pid"

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

MIRACAST_PKG="com.softwinner.miracastReceiver"
AIRPLAY_PKG="com.ecloud.eairplay"
DLNA_PKG="com.ecloud.emedia"

installed() { pm path "$1" >/dev/null 2>&1; }
running() { pidof "$1" >/dev/null 2>&1; }
as_bool() { if "$@"; then printf true; else printf false; fi; }
disabled() { pm list packages -d 2>/dev/null | "$BB" grep -qx "package:$1"; }
enable_for_cast() {
  pkg="$1"
  if disabled "$pkg"; then
    pm enable --user 0 "$pkg" >/dev/null 2>&1 || return 1
    printf '%s\n' "$pkg" > "$ENABLED_BY_US"
  fi
}
restore_disabled() {
  pkg="$1"
  if [ -s "$ENABLED_BY_US" ] && [ "$(cat "$ENABLED_BY_US" 2>/dev/null)" = "$pkg" ]; then
    pm disable-user --user 0 "$pkg" >/dev/null 2>&1
    rm -f "$ENABLED_BY_US"
  fi
}
stop_pkg() {
  am force-stop "$1" >/dev/null 2>&1
  restore_disabled "$1"
}
stop_watchdog() {
  if [ -s "$WATCHDOG_PID" ]; then
    watchdog_pid="$(cat "$WATCHDOG_PID" 2>/dev/null)"
    case "$watchdog_pid" in ''|*[!0-9]*) ;; *) kill "$watchdog_pid" >/dev/null 2>&1 ;; esac
    rm -f "$WATCHDOG_PID"
  fi
}
start_miracast_watchdog() {
  (
    sleep 12
    checks=0
    while [ "$checks" -lt 5760 ]; do
      top="$(dumpsys activity activities 2>/dev/null | "$BB" grep -m1 'mResumedActivity')"
      printf '%s' "$top" | "$BB" grep -q "$MIRACAST_PKG" || break
      sleep 5
      checks=$((checks + 1))
    done
    am force-stop "$MIRACAST_PKG" >/dev/null 2>&1
    restore_disabled "$MIRACAST_PKG"
    rm -f "$WATCHDOG_PID"
  ) </dev/null >/dev/null 2>&1 &
  printf '%s\n' "$!" > "$WATCHDOG_PID"
}
stop_others() {
  keep="$1"
  for pkg in "$MIRACAST_PKG" "$AIRPLAY_PKG" "$DLNA_PKG"; do
    [ "$pkg" = "$keep" ] || stop_pkg "$pkg"
  done
}

action="$(get_param action 2>/dev/null || true)"
status="ok"; detail="Casting receivers ready."
case "$action" in
  ''|status) ;;
  miracast)
    if installed "$MIRACAST_PKG"; then
      stop_watchdog
      stop_others "$MIRACAST_PKG"
      if enable_for_cast "$MIRACAST_PKG" && am start --user 0 -n "$MIRACAST_PKG/.Miracast" >/dev/null 2>&1; then
        start_miracast_watchdog
        detail="Miracast ready. Open Cast, Smart View, or Wireless display on your Android or Windows device."
      else restore_disabled "$MIRACAST_PKG"; status="err"; detail="The built-in Miracast receiver could not start."; fi
    else status="err"; detail="No built-in Miracast receiver was found."; fi ;;
  airplay)
    if installed "$AIRPLAY_PKG"; then
      stop_watchdog
      stop_others "$AIRPLAY_PKG"
      if enable_for_cast "$AIRPLAY_PKG" && am start --user 0 -n "$AIRPLAY_PKG/.MainActivity" >/dev/null 2>&1; then
        detail="AirPlay ready. Choose Beem 470 from Screen Mirroring on your Apple device."
      else restore_disabled "$AIRPLAY_PKG"; status="err"; detail="The built-in AirPlay receiver could not start."; fi
    else status="err"; detail="No built-in AirPlay receiver was found."; fi ;;
  dlna)
    if installed "$DLNA_PKG"; then
      stop_watchdog
      stop_others "$DLNA_PKG"
      if enable_for_cast "$DLNA_PKG" && am startservice --user 0 -n "$DLNA_PKG/.DlnaServer" >/dev/null 2>&1; then
        detail="DLNA ready. Choose Beem 470 from a DLNA media app."
      else restore_disabled "$DLNA_PKG"; status="err"; detail="The built-in DLNA receiver could not start."; fi
    else status="err"; detail="No built-in DLNA receiver was found."; fi ;;
  stop)
    stop_watchdog
    stop_pkg "$MIRACAST_PKG"
    stop_pkg "$AIRPLAY_PKG"
    stop_pkg "$DLNA_PKG"
    input keyevent KEYCODE_HOME >/dev/null 2>&1
    detail="Casting stopped and receiver memory released." ;;
  *) status="err"; detail="Unknown casting action." ;;
esac

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo "Cache-Control: no-store"
echo
printf '{"status":"%s","detail":"%s","available":{"miracast":%s,"airplay":%s,"dlna":%s},"running":{"miracast":%s,"airplay":%s,"dlna":%s}}\n' \
  "$status" "$detail" \
  "$(as_bool installed "$MIRACAST_PKG")" "$(as_bool installed "$AIRPLAY_PKG")" "$(as_bool installed "$DLNA_PKG")" \
  "$(as_bool running "$MIRACAST_PKG")" "$(as_bool running "$AIRPLAY_PKG")" "$(as_bool running "$DLNA_PKG")"
