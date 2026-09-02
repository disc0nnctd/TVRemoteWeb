#!/system/bin/sh
# TVRemoteWeb — scoped Allwinner four-corner keystone control.
# Mutations are POST-only, token-authenticated, range checked, and backed up.

BB="/data/adb/magisk/busybox"
STATE="/data/adb/tvremoteweb"
TOKEN_FILE="$STATE/token"
BACKUP_FILE="$STATE/keystone-backup.csv"
HISTORY_FILE="$STATE/keystone-history.log"
VIEW_FILE="$STATE/keystone-view.properties"
CALIBRATION_FILE="$STATE/keystone-calibration-backup.csv"
CORRECTION_ACTIVITY="com.htc.htcsettings/com.htc.activity.CorrectionActivity"

PARAMS="${QUERY_STRING:-}"
if [ "${REQUEST_METHOD:-GET}" = "POST" ]; then
  length="${CONTENT_LENGTH:-0}"
  case "$length" in ''|*[!0-9]*) length=0 ;; esac
  [ "$length" -gt 8192 ] && length=8192
  body="$("$BB" head -c "$length" 2>/dev/null)"
  [ -n "$body" ] && PARAMS="${PARAMS}${PARAMS:+&}${body}"
fi

urldecode() { "$BB" httpd -d "${1:-}"; }
get_param() {
  key="$1"; oldifs="$IFS"; IFS='&'
  for kv in $PARAMS; do
    IFS="$oldifs"; k="${kv%%=*}"; v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$oldifs"; return 1
}

json_headers() {
  echo "Content-Type: application/json"
  echo "Access-Control-Allow-Origin: *"
  echo "Cache-Control: no-store"
  echo
}
respond_error() {
  json_headers
  printf '{"status":"err","detail":"%s"}\n' "$1"
  exit 0
}

token_full=""; pin=""
if [ -s "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
[ -z "$token_full" ] && respond_error "projector token is unavailable"
if [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"; json_headers; printf '{"status":"err","detail":"forbidden"}\n'; exit 0
fi

valid_csv() {
  value="$1"; oldifs="$IFS"; IFS=','; set -- $value; IFS="$oldifs"
  [ "$#" -eq 8 ] || return 1
  for n in "$@"; do
    case "$n" in ''|*[!0-9]*) return 1 ;; esac
    [ "$n" -le 500 ] 2>/dev/null || return 1
  done
  return 0
}

read_current() {
  current="$(getprop persist.sys.zoom.value 2>/dev/null)"
  valid_csv "$current" && { printf '%s' "$current"; return 0; }
  lbx="$(getprop persist.display.keystone_lbx)"; lby="$(getprop persist.display.keystone_lby)"
  ltx="$(getprop persist.display.keystone_ltx)"; lty="$(getprop persist.display.keystone_lty)"
  rtx="$(getprop persist.display.keystone_rtx)"; rty="$(getprop persist.display.keystone_rty)"
  rbx="$(getprop persist.display.keystone_rbx)"; rby="$(getprop persist.display.keystone_rby)"
  current="$lbx,$lby,$ltx,$lty,$rtx,$rty,$rbx,$rby"
  valid_csv "$current" && { printf '%s' "$current"; return 0; }
  return 1
}

csv_json() {
  oldifs="$IFS"; IFS=','; set -- $1; IFS="$oldifs"
  printf '{"lb":[%s,%s],"lt":[%s,%s],"rt":[%s,%s],"rb":[%s,%s]}' \
    "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8"
}

apply_csv() {
  values="$1"
  valid_csv "$values" || return 1
  oldifs="$IFS"; IFS=','; set -- $values; IFS="$oldifs"
  args=""
  for n in "$@"; do
    fraction="$("$BB" awk -v n="$n" 'BEGIN { printf "%.6f", n / 500 }')"
    args="$args f $fraction"
  done
  setprop persist.sys.zoom.value "$values" || return 1
  # Word splitting is intentional: SurfaceFlinger expects eight `f value` pairs.
  service call SurfaceFlinger 1050 $args >/dev/null 2>&1 || return 1
  return 0
}

save_backup() {
  after="$1"; operation="$2"
  printf '%s\n' "$current" > "$BACKUP_FILE" || return 1
  chmod 600 "$BACKUP_FILE"
  printf '%s operation=%s before=%s after=%s\n' "$(date +%s)" "$operation" "$current" "$after" >> "$HISTORY_FILE"
}

action="$(get_param action 2>/dev/null || echo status)"
current="$(read_current 2>/dev/null || true)"
supported=false; [ -n "$current" ] && supported=true
view_available=false
pm path "${CORRECTION_ACTIVITY%%/*}" >/dev/null 2>&1 && view_available=true

case "$action" in
  status)
    json_headers
    printf '{"status":"ok","supported":%s,"view_available":%s,"current":' "$supported" "$view_available"
    if [ "$supported" = true ]; then csv_json "$current"; else printf 'null'; fi
    printf ',"backup_available":%s}\n' "$([ -s "$BACKUP_FILE" ] && echo true || echo false)"
    ;;
  apply)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "apply requires POST"
    [ "$supported" = true ] || respond_error "four-corner firmware interface not detected"
    [ "$(get_param confirmation 2>/dev/null || true)" = "APPLY" ] || respond_error "explicit APPLY confirmation required"
    proposal="$(get_param values 2>/dev/null || true)"
    valid_csv "$proposal" || respond_error "values must be eight integers in firmware range 0-500"
    calibration_before="$(cat "$CALIBRATION_FILE" 2>/dev/null)"
    if valid_csv "$calibration_before"; then
      printf '%s\n' "$calibration_before" > "$BACKUP_FILE" || respond_error "could not preserve pre-calibration rollback values"
      chmod 600 "$BACKUP_FILE"
      printf '%s operation=keystone-calibrated before=%s calibration=%s after=%s\n' "$(date +%s)" "$calibration_before" "$current" "$proposal" >> "$HISTORY_FILE"
      rm -f "$CALIBRATION_FILE"
    else
      save_backup "$proposal" keystone || respond_error "could not save rollback values"
    fi
    apply_csv "$proposal" || respond_error "SurfaceFlinger rejected the correction"
    json_headers
    printf '{"status":"ok","detail":"keystone applied","current":'; csv_json "$proposal"; printf '}\n'
    ;;
  reset)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "reset requires POST"
    [ "$supported" = true ] || respond_error "four-corner firmware interface not detected"
    [ "$(get_param confirmation 2>/dev/null || true)" = "RESET" ] || respond_error "explicit RESET confirmation required"
    reset_values="0,0,0,0,0,0,0,0"
    save_backup "$reset_values" reset || respond_error "could not save rollback values"
    apply_csv "$reset_values" || respond_error "SurfaceFlinger rejected the reset"
    rm -f "$CALIBRATION_FILE"
    json_headers
    printf '{"status":"ok","detail":"keystone and zoom reset to full size","current":'; csv_json "$reset_values"; printf '}\n'
    ;;
  calibrate)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "calibrate requires POST"
    [ "$supported" = true ] || respond_error "four-corner firmware interface not detected"
    [ "$(get_param confirmation 2>/dev/null || true)" = "CALIBRATE" ] || respond_error "explicit CALIBRATE confirmation required"
    size="$(get_param size 2>/dev/null || true)"
    case "$size" in 55|65|75) ;; *) respond_error "calibration size must be 55, 65, or 75 percent" ;; esac
    inset="$("$BB" awk -v size="$size" 'BEGIN { printf "%d", ((100 - size) * 2.5) + 0.5 }')"
    calibration_values="$inset,$inset,$inset,$inset,$inset,$inset,$inset,$inset"
    original="$(cat "$CALIBRATION_FILE" 2>/dev/null)"
    if ! valid_csv "$original"; then original="$current"; fi
    printf '%s\n' "$original" > "$CALIBRATION_FILE" || respond_error "could not preserve pre-calibration values"
    chmod 600 "$CALIBRATION_FILE"
    printf '%s\n' "$original" > "$BACKUP_FILE" || respond_error "could not preserve rollback values"
    chmod 600 "$BACKUP_FILE"
    printf '%s operation=calibration-%s before=%s after=%s\n' "$(date +%s)" "$size" "$original" "$calibration_values" >> "$HISTORY_FILE"
    apply_csv "$calibration_values" || respond_error "SurfaceFlinger rejected the calibration size"
    json_headers
    printf '{"status":"ok","detail":"%s%% centered calibration image active","current":' "$size"; csv_json "$calibration_values"; printf '}\n'
    ;;
  zoom)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "zoom requires POST"
    [ "$supported" = true ] || respond_error "four-corner firmware interface not detected"
    [ "$(get_param confirmation 2>/dev/null || true)" = "ZOOM" ] || respond_error "explicit ZOOM confirmation required"
    size="$(get_param size 2>/dev/null || true)"
    case "$size" in ''|*[!0-9]*) respond_error "image size must be an integer from 50 to 100" ;; esac
    [ "$size" -ge 50 ] 2>/dev/null && [ "$size" -le 100 ] 2>/dev/null || respond_error "image size must be from 50 to 100 percent"
    # Equal edge insets create a centered rectangle: inset=(1-size/100)*250.
    inset="$("$BB" awk -v size="$size" 'BEGIN { printf "%d", ((100 - size) * 2.5) + 0.5 }')"
    zoom_values="$inset,$inset,$inset,$inset,$inset,$inset,$inset,$inset"
    save_backup "$zoom_values" "zoom-${size}" || respond_error "could not save rollback values"
    apply_csv "$zoom_values" || respond_error "SurfaceFlinger rejected the image size"
    rm -f "$CALIBRATION_FILE"
    json_headers
    printf '{"status":"ok","detail":"image size set to %s%%","current":' "$size"; csv_json "$zoom_values"; printf '}\n'
    ;;
  restore)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "restore requires POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "RESTORE" ] || respond_error "explicit RESTORE confirmation required"
    previous="$(cat "$BACKUP_FILE" 2>/dev/null)"
    valid_csv "$previous" || respond_error "no valid keystone backup exists"
    apply_csv "$previous" || respond_error "SurfaceFlinger rejected the restore"
    rm -f "$CALIBRATION_FILE"
    printf '%s restored=%s\n' "$(date +%s)" "$previous" >> "$HISTORY_FILE"
    json_headers
    printf '{"status":"ok","detail":"previous keystone restored","current":'; csv_json "$previous"; printf '}\n'
    ;;
  view_open)
    [ "$view_available" = true ] || respond_error "vendor correction view is unavailable"
    : > "$VIEW_FILE"
    for prop in \
      persist.display.keystone_lbx persist.display.keystone_lby \
      persist.display.keystone_ltx persist.display.keystone_lty \
      persist.display.keystone_rtx persist.display.keystone_rty \
      persist.display.keystone_rbx persist.display.keystone_rby; do
      value="$(getprop "$prop")"; [ -n "$value" ] && printf '%s=%s\n' "$prop" "$value" >> "$VIEW_FILE"
    done
    chmod 600 "$VIEW_FILE"
    am start -W -n "$CORRECTION_ACTIVITY" >/dev/null 2>&1 || respond_error "could not open correction view"
    json_headers; printf '{"status":"ok","detail":"correction grid shown"}\n'
    ;;
  view_close)
    input keyevent KEYCODE_HOME >/dev/null 2>&1
    if [ -s "$VIEW_FILE" ]; then
      while IFS='=' read -r prop value; do
        case "$prop" in persist.display.keystone_*) setprop "$prop" "$value" ;; esac
      done < "$VIEW_FILE"
      rm -f "$VIEW_FILE"
    fi
    # The vendor activity otherwise remains the high-memory previous process.
    am force-stop com.htc.htcsettings >/dev/null 2>&1
    json_headers; printf '{"status":"ok","detail":"grid closed; vendor values restored"}\n'
    ;;
  *) respond_error "unknown keystone action" ;;
esac
