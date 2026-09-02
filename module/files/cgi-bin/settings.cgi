#!/system/bin/sh
# TVRemoteWeb — authenticated, allow-listed Android settings control.

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"
PQCLI="/data/adb/modules/tvremoteweb/files/pqcli.dex"
PQAPK="/product/app/HtcSettingsBlue/HtcSettingsBlue.apk"
PQ_BACKUP="/data/adb/tvremoteweb/picture-backup.conf"
PQ_LIVE_BACKUP="/data/adb/tvremoteweb/picture-live-backup.conf"

PARAMS="${QUERY_STRING:-}"
if [ "${REQUEST_METHOD:-GET}" = "POST" ]; then
  length="${CONTENT_LENGTH:-0}"
  case "$length" in ''|*[!0-9]*) length=0 ;; esac
  [ "$length" -gt 4096 ] && length=4096
  body="$(dd bs=1 count="$length" 2>/dev/null)"
  [ -n "$body" ] && PARAMS="${PARAMS:+$PARAMS&}$body"
fi

urldecode() { "$BB" httpd -d "${1:-}"; }

get_param() {
  key="$1"
  old_ifs="$IFS"
  IFS='&'
  for kv in $PARAMS; do
    IFS="$old_ifs"
    k="${kv%%=*}"
    v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$old_ifs"
  return 1
}

respond_error() {
  echo "Status: 400 Bad Request"
  echo "Content-Type: application/json"
  echo "Cache-Control: no-store"
  echo
  printf '{"status":"err","detail":"%s"}\n' "$1"
  exit 0
}

token_full=""
pin=""
if [ -f "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"
  echo "Content-Type: application/json"
  echo
  echo '{"status":"err","detail":"forbidden"}'
  exit 0
fi

number_or() {
  value="$1"; fallback="$2"
  case "$value" in ''|null|*[!0-9]*) printf '%s' "$fallback" ;; *) printf '%s' "$value" ;; esac
}

decimal_or() {
  case "$1" in 0|0.0) printf '0' ;; 0.5) printf '0.5' ;; 1|1.0|null|'') printf '1' ;; *) printf '1' ;; esac
}

pq_status() {
  [ -f "$PQCLI" ] && [ -f "$PQAPK" ] || return 1
  CLASSPATH="$PQCLI:$PQAPK" app_process /system/bin com.tvremote.PqCli status 2>/dev/null
}

pq_get_from() {
  printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n1
}

pq_set() {
  CLASSPATH="$PQCLI:$PQAPK" app_process /system/bin com.tvremote.PqCli set "$1" "$2" >/dev/null 2>&1
}

valid_pq_dump() {
  dump="$1"
  for channel in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
    pqv="$(pq_get_from "$dump" "$channel")"
    case "$pqv" in ''|*[!0-9]*) return 1 ;; esac
  done
  return 0
}

valid_range() {
  value="$1" max="$2"
  case "$value" in ''|*[!0-9]*) return 1 ;; esac
  [ "$value" -le "$max" ] 2>/dev/null
}

picture_json() {
  dump="$1"
  if valid_pq_dump "$dump"; then
    printf 'true,"picture":{"brightness":%s,"contrast":%s,"saturation":%s,"hue":%s,"sharpness":%s,"backlight":%s,"tnr":%s,"snr":%s,"dci":%s,"black_extension":%s,"dynamic_backlight":%s,"color_temperature":%s,"gamma":%s},"picture_backup_available":%s' \
      "$(pq_get_from "$dump" 1)" "$(pq_get_from "$dump" 2)" "$(pq_get_from "$dump" 3)" \
      "$(pq_get_from "$dump" 4)" "$(pq_get_from "$dump" 5)" "$(pq_get_from "$dump" 6)" \
      "$(pq_get_from "$dump" 7)" "$(pq_get_from "$dump" 8)" "$(pq_get_from "$dump" 9)" \
      "$(pq_get_from "$dump" 10)" "$(pq_get_from "$dump" 11)" "$(pq_get_from "$dump" 12)" \
      "$(pq_get_from "$dump" 13)" \
      "$([ -s "$PQ_BACKUP" ] && printf true || printf false)"
  else
    printf 'false,"picture":null,"picture_backup_available":false'
  fi
}

emit_status() {
  detail="${1:-settings loaded}"
  brightness="$(number_or "$(settings get system screen_brightness 2>/dev/null)" 102)"
  timeout="$(number_or "$(settings get system screen_off_timeout 2>/dev/null)" 300000)"
  screensaver="$(number_or "$(settings get secure screensaver_enabled 2>/dev/null)" 0)"
  stay_awake="$(number_or "$(settings get global stay_on_while_plugged_in 2>/dev/null)" 0)"
  rotation="$(number_or "$(settings get system user_rotation 2>/dev/null)" 0)"
  animation="$(decimal_or "$(settings get global animator_duration_scale 2>/dev/null)")"
  wifi_sleep="$(number_or "$(settings get global wifi_sleep_policy 2>/dev/null)" 2)"
  pq_dump="$(pq_status 2>/dev/null || true)"
  echo "Content-Type: application/json"
  echo "Cache-Control: no-store"
  echo "Access-Control-Allow-Origin: *"
  echo
  printf '{"status":"ok","detail":"%s","values":{"brightness":%s,"screen_timeout":%s,"screensaver":%s,"stay_awake":%s,"rotation":%s,"animation":%s,"wifi_sleep_policy":%s},"picture_supported":' \
    "$detail" "$brightness" "$timeout" "$screensaver" "$stay_awake" "$rotation" "$animation" "$wifi_sleep"
  picture_json "$pq_dump"
  printf '}\n'
}

action="$(get_param action 2>/dev/null || true)"
[ -z "$action" ] && action=status

case "$action" in
  status)
    emit_status "settings loaded"
    ;;
  set)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "setting changes require POST"
    setting="$(get_param setting 2>/dev/null || true)"
    value="$(get_param value 2>/dev/null || true)"
    case "$setting" in
      brightness)
        case "$value" in ''|*[!0-9]*) respond_error "brightness must be an integer" ;; esac
        [ "$value" -ge 1 ] 2>/dev/null && [ "$value" -le 255 ] 2>/dev/null || respond_error "brightness must be from 1 to 255"
        settings put system screen_brightness "$value" || respond_error "brightness update failed"
        ;;
      screen_timeout)
        case "$value" in 300000|900000|1800000|3600000|2147483647) ;; *) respond_error "unsupported sleep timeout" ;; esac
        settings put system screen_off_timeout "$value" || respond_error "sleep timeout update failed"
        ;;
      screensaver)
        case "$value" in 0|1) ;; *) respond_error "screensaver must be on or off" ;; esac
        settings put secure screensaver_enabled "$value" || respond_error "screensaver update failed"
        ;;
      stay_awake)
        case "$value" in 0|7) ;; *) respond_error "stay awake must be on or off" ;; esac
        settings put global stay_on_while_plugged_in "$value" || respond_error "stay-awake update failed"
        ;;
      rotation)
        case "$value" in 0|1|2|3) ;; *) respond_error "rotation must be 0, 90, 180, or 270 degrees" ;; esac
        settings put system accelerometer_rotation 0 || respond_error "rotation lock failed"
        settings put system user_rotation "$value" || respond_error "rotation update failed"
        ;;
      animation)
        case "$value" in 0|0.5|1) ;; *) respond_error "animation scale must be off, fast, or normal" ;; esac
        settings put global window_animation_scale "$value" || respond_error "animation update failed"
        settings put global transition_animation_scale "$value" || respond_error "animation update failed"
        settings put global animator_duration_scale "$value" || respond_error "animation update failed"
        ;;
      picture_brightness|picture_contrast|picture_saturation|picture_hue|picture_sharpness|picture_backlight|picture_tnr|picture_snr|picture_dci|picture_black_extension|picture_dynamic_backlight|picture_color_temperature|picture_gamma)
        [ "$(get_param confirmation 2>/dev/null || true)" = "APPLY" ] || respond_error "picture changes require APPLY confirmation"
        case "$setting" in
          picture_brightness) channel=1 ;;
          picture_contrast) channel=2 ;;
          picture_saturation) channel=3 ;;
          picture_hue) channel=4 ;;
          picture_sharpness) channel=5 ;;
          picture_backlight) channel=6 ;;
          picture_tnr) channel=7 ;;
          picture_snr) channel=8 ;;
          picture_dci) channel=9 ;;
          picture_black_extension) channel=10 ;;
          picture_dynamic_backlight) channel=11 ;;
          picture_color_temperature) channel=12 ;;
          picture_gamma) channel=13 ;;
        esac
        case "$value" in ''|*[!0-9]*) respond_error "picture value must be an integer" ;; esac
        case "$channel" in
          1|2|3|4|5|6) [ "$value" -le 100 ] 2>/dev/null || respond_error "picture value must be from 0 to 100" ;;
          7|8|9|10) [ "$value" -le 3 ] 2>/dev/null || respond_error "enhancement level must be from 0 to 3" ;;
          11) [ "$value" -le 1 ] 2>/dev/null || respond_error "dynamic backlight must be on or off" ;;
          12) [ "$value" -le 2 ] 2>/dev/null || respond_error "color temperature must be standard, cool, or warm" ;;
          13) [ "$value" -le 4 ] 2>/dev/null || respond_error "gamma must be one of the five supported curves" ;;
        esac
        pq_dump="$(pq_status 2>/dev/null || true)"
        valid_pq_dump "$pq_dump" || respond_error "vendor picture service unavailable"
        printf '%s\n' "$pq_dump" > "$PQ_BACKUP" || respond_error "could not save picture backup"
        chmod 600 "$PQ_BACKUP" 2>/dev/null || true
        pq_set "$channel" "$value" || respond_error "vendor picture update failed"
        ;;
      *) respond_error "unknown setting" ;;
    esac
    emit_status "setting updated"
    ;;
  device_apply)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "setting changes require POST"
    d_timeout="$(get_param screen_timeout 2>/dev/null || true)"
    d_screensaver="$(get_param screensaver 2>/dev/null || true)"
    d_stay_awake="$(get_param stay_awake 2>/dev/null || true)"
    d_rotation="$(get_param rotation 2>/dev/null || true)"
    d_animation="$(get_param animation 2>/dev/null || true)"
    case "$d_timeout" in 300000|900000|1800000|3600000|2147483647) ;; *) respond_error "unsupported sleep timeout" ;; esac
    case "$d_screensaver" in 0|1) ;; *) respond_error "screensaver must be on or off" ;; esac
    case "$d_stay_awake" in 0|7) ;; *) respond_error "stay awake must be on or off" ;; esac
    case "$d_rotation" in 0|1|2|3) ;; *) respond_error "rotation must be 0, 90, 180, or 270 degrees" ;; esac
    case "$d_animation" in 0|0.5|1) ;; *) respond_error "animation scale must be off, fast, or normal" ;; esac
    settings put system screen_off_timeout "$d_timeout" || respond_error "sleep timeout update failed"
    settings put secure screensaver_enabled "$d_screensaver" || respond_error "screensaver update failed"
    settings put global stay_on_while_plugged_in "$d_stay_awake" || respond_error "stay-awake update failed"
    settings put system accelerometer_rotation 0 || respond_error "rotation lock failed"
    settings put system user_rotation "$d_rotation" || respond_error "rotation update failed"
    settings put global window_animation_scale "$d_animation" || respond_error "animation update failed"
    settings put global transition_animation_scale "$d_animation" || respond_error "animation update failed"
    settings put global animator_duration_scale "$d_animation" || respond_error "animation update failed"
    emit_status "device settings applied"
    ;;
  picture_preview)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "picture preview requires POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "PREVIEW" ] || respond_error "picture preview requires PREVIEW confirmation"
    name="$(get_param name 2>/dev/null || true)"
    value="$(get_param value 2>/dev/null || true)"
    case "$name" in
      brightness) channel=1; max=100 ;; contrast) channel=2; max=100 ;;
      saturation) channel=3; max=100 ;; hue) channel=4; max=100 ;;
      sharpness) channel=5; max=100 ;; backlight) channel=6; max=100 ;;
      tnr) channel=7; max=3 ;; snr) channel=8; max=3 ;; dci) channel=9; max=3 ;;
      black_extension) channel=10; max=3 ;; dynamic_backlight) channel=11; max=1 ;;
      color_temperature) channel=12; max=2 ;; gamma) channel=13; max=4 ;;
      *) respond_error "unknown picture preview control" ;;
    esac
    valid_range "$value" "$max" || respond_error "picture preview value is invalid"
    pq_dump="$(pq_status 2>/dev/null || true)"
    valid_pq_dump "$pq_dump" || respond_error "vendor picture service unavailable"
    live_before="$(cat "$PQ_LIVE_BACKUP" 2>/dev/null)"
    if ! valid_pq_dump "$live_before"; then
      printf '%s\n' "$pq_dump" > "$PQ_LIVE_BACKUP" || respond_error "could not save live preview baseline"
      printf '%s\n' "$pq_dump" > "$PQ_BACKUP" || respond_error "could not save picture backup"
      chmod 600 "$PQ_LIVE_BACKUP" "$PQ_BACKUP" 2>/dev/null || true
    fi
    [ "$(pq_get_from "$pq_dump" "$channel")" = "$value" ] || pq_set "$channel" "$value" || respond_error "vendor picture preview failed"
    emit_status "live picture preview updated"
    ;;
  picture_apply)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "picture changes require POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "APPLY" ] || respond_error "picture changes require APPLY confirmation"
    p_brightness="$(get_param brightness 2>/dev/null || true)"
    p_contrast="$(get_param contrast 2>/dev/null || true)"
    p_saturation="$(get_param saturation 2>/dev/null || true)"
    p_hue="$(get_param hue 2>/dev/null || true)"
    p_sharpness="$(get_param sharpness 2>/dev/null || true)"
    p_backlight="$(get_param backlight 2>/dev/null || true)"
    p_tnr="$(get_param tnr 2>/dev/null || true)"
    p_snr="$(get_param snr 2>/dev/null || true)"
    p_dci="$(get_param dci 2>/dev/null || true)"
    p_black="$(get_param black_extension 2>/dev/null || true)"
    p_dynamic="$(get_param dynamic_backlight 2>/dev/null || true)"
    p_temperature="$(get_param color_temperature 2>/dev/null || true)"
    p_gamma="$(get_param gamma 2>/dev/null || true)"
    for spec in "1:$p_brightness:100" "2:$p_contrast:100" "3:$p_saturation:100" \
                "4:$p_hue:100" "5:$p_sharpness:100" "6:$p_backlight:100" \
                "7:$p_tnr:3" "8:$p_snr:3" "9:$p_dci:3" "10:$p_black:3" \
                "11:$p_dynamic:1" "12:$p_temperature:2" "13:$p_gamma:4"; do
      old_ifs="$IFS"; IFS=:; set -- $spec; IFS="$old_ifs"
      valid_range "$2" "$3" || respond_error "one or more picture values are invalid"
    done
    pq_dump="$(pq_status 2>/dev/null || true)"
    valid_pq_dump "$pq_dump" || respond_error "vendor picture service unavailable"
    live_before="$(cat "$PQ_LIVE_BACKUP" 2>/dev/null)"
    if valid_pq_dump "$live_before"; then backup_dump="$live_before"; else backup_dump="$pq_dump"; fi
    printf '%s\n' "$backup_dump" > "$PQ_BACKUP" || respond_error "could not save picture backup"
    chmod 600 "$PQ_BACKUP" 2>/dev/null || true
    for spec in "1:$p_brightness" "2:$p_contrast" "3:$p_saturation" "4:$p_hue" \
                "5:$p_sharpness" "6:$p_backlight" "7:$p_tnr" "8:$p_snr" \
                "9:$p_dci" "10:$p_black" "11:$p_dynamic" "12:$p_temperature" "13:$p_gamma"; do
      old_ifs="$IFS"; IFS=:; set -- $spec; IFS="$old_ifs"
      [ "$(pq_get_from "$pq_dump" "$1")" = "$2" ] && continue
      pq_set "$1" "$2" || respond_error "vendor picture update failed"
    done
    rm -f "$PQ_LIVE_BACKUP"
    emit_status "picture settings applied"
    ;;
  picture_restore)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "restore requires POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "RESTORE" ] || respond_error "restore requires RESTORE confirmation"
    [ -s "$PQ_BACKUP" ] || respond_error "no picture backup is available"
    backup="$(cat "$PQ_BACKUP" 2>/dev/null)"
    valid_pq_dump "$backup" || respond_error "picture backup is invalid"
    current="$(pq_status 2>/dev/null || true)"
    valid_pq_dump "$current" || respond_error "vendor picture service unavailable"
    for channel in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
      restore_value="$(pq_get_from "$backup" "$channel")"
      [ "$(pq_get_from "$current" "$channel")" = "$restore_value" ] && continue
      pq_set "$channel" "$restore_value" || respond_error "picture restore failed"
    done
    rm -f "$PQ_LIVE_BACKUP"
    emit_status "previous picture settings restored"
    ;;
  *) respond_error "unknown action" ;;
esac
