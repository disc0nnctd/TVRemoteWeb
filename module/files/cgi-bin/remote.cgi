#!/system/bin/sh

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"

urldecode() { "$BB" httpd -d "${1:-}"; }

get_param() {
  key="$1"
  OLDIFS="$IFS"
  IFS='&'
  for kv in $QUERY_STRING; do
    IFS="$OLDIFS"
    k="${kv%%=*}"
    v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$OLDIFS"
  return 1
}

# token auth
token_full=""
pin=""
if [ -f "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"
  echo "Content-Type: text/plain"
  echo
  echo "forbidden"
  exit 0
fi

k="$(get_param k 2>/dev/null || true)"
t="$(get_param t 2>/dev/null || true)"
app="$(get_param app 2>/dev/null || true)"
sys="$(get_param sys 2>/dev/null || true)"
tap="$(get_param tap 2>/dev/null || true)"
swipe="$(get_param swipe 2>/dev/null || true)"
mv="$(get_param mv 2>/dev/null || true)"
mc="$(get_param mc 2>/dev/null || true)"
md="$(get_param md 2>/dev/null || true)"
mu="$(get_param mu 2>/dev/null || true)"
mw="$(get_param mw 2>/dev/null || true)"
url="$(get_param url 2>/dev/null || true)"
splash="$(get_param splash 2>/dev/null || true)"
kill_pid="$(get_param kill 2>/dev/null || true)"
admin="$(get_param admin 2>/dev/null || true)"

# sunxi-ir-uinput exposes REL_X/REL_Y + BTN_MOUSE — send raw evdev events for a real cursor
MOUSE_EV="/dev/input/event7"
EV_SYN=0; EV_KEY=1; EV_REL=2
SYN_REPORT=0
REL_X=0; REL_Y=1; REL_WHEEL=8; REL_HWHEEL=6
BTN_LEFT=272; BTN_RIGHT=273; BTN_MIDDLE=274

emit_syn() { sendevent "$MOUSE_EV" $EV_SYN $SYN_REPORT 0; }
btn_code() {
  case "$1" in
    R|RIGHT)  echo $BTN_RIGHT ;;
    M|MIDDLE) echo $BTN_MIDDLE ;;
    *)        echo $BTN_LEFT ;;
  esac
}

status="ok"
detail=""

if [ -n "$k" ]; then
  case "$k" in
    UP|DOWN|LEFT|RIGHT|CENTER) key="DPAD_$k" ;;
    OK|SELECT|ENTER)           key="DPAD_CENTER" ;;
    HOME|BACK|MENU|POWER|SEARCH|VOLUME_UP|VOLUME_DOWN|VOLUME_MUTE|MEDIA_PLAY_PAUSE|MEDIA_NEXT|MEDIA_PREVIOUS|MEDIA_STOP|MEDIA_REWIND|MEDIA_FAST_FORWARD|CAPTIONS|SETTINGS|APP_SWITCH|NOTIFICATION|BRIGHTNESS_UP|BRIGHTNESS_DOWN|SLEEP|WAKEUP|DEL|FORWARD_DEL|TAB|ENTER) key="$k" ;;
    *) key="$k" ;;
  esac
  input keyevent "KEYCODE_$key" >/dev/null 2>&1
  detail="keyevent KEYCODE_$key"
fi

if [ -n "$t" ]; then
  esc="$(printf '%s' "$t" | "$BB" sed -e 's/ /%s/g')"
  input text "$esc" >/dev/null 2>&1
  detail="text: $t"
fi

if [ -n "$url" ]; then
  # If url given + app given, target that app; else system chooser
  if [ -n "$app" ]; then
    am start -a android.intent.action.VIEW -d "$url" "$app" >/dev/null 2>&1
    detail="open $url in $app"
  else
    am start -a android.intent.action.VIEW -d "$url" >/dev/null 2>&1
    detail="open $url"
  fi
elif [ -n "$app" ]; then
  monkey -p "$app" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  detail="launch: $app"
fi

if [ -n "$tap" ]; then
  x="${tap%%,*}"; y="${tap#*,}"
  input tap "$x" "$y" >/dev/null 2>&1
  detail="tap $x,$y"
fi

if [ -n "$mv" ]; then
  dx="${mv%%,*}"; dy="${mv#*,}"
  [ "$dx" != "0" ] && sendevent "$MOUSE_EV" $EV_REL $REL_X "$dx"
  [ "$dy" != "0" ] && sendevent "$MOUSE_EV" $EV_REL $REL_Y "$dy"
  emit_syn
  detail="mouse move $dx,$dy"
fi

if [ -n "$mc" ]; then
  code=$(btn_code "$mc")
  sendevent "$MOUSE_EV" $EV_KEY "$code" 1; emit_syn
  sendevent "$MOUSE_EV" $EV_KEY "$code" 0; emit_syn
  detail="mouse click $mc"
fi

if [ -n "$md" ]; then
  code=$(btn_code "$md")
  sendevent "$MOUSE_EV" $EV_KEY "$code" 1; emit_syn
  detail="mouse down $md"
fi

if [ -n "$mu" ]; then
  code=$(btn_code "$mu")
  sendevent "$MOUSE_EV" $EV_KEY "$code" 0; emit_syn
  detail="mouse up $mu"
fi

if [ -n "$mw" ]; then
  sendevent "$MOUSE_EV" $EV_REL $REL_WHEEL "$mw"
  emit_syn
  detail="wheel $mw"
fi

if [ -n "$swipe" ]; then
  IFS=',' read -r x1 y1 x2 y2 dur << EOF
$swipe
EOF
  [ -z "$dur" ] && dur=200
  input swipe "$x1" "$y1" "$x2" "$y2" "$dur" >/dev/null 2>&1
  detail="swipe $x1,$y1->$x2,$y2 ${dur}ms"
fi

if [ -n "$splash" ]; then
  FLAG=/data/adb/tvremoteweb/no-splash
  case "$splash" in
    off|disable) : > "$FLAG"; detail="boot-splash disabled" ;;
    on|enable)   rm -f "$FLAG"; detail="boot-splash enabled" ;;
    show|now)    am start -a android.intent.action.VIEW -d file:///sdcard/tvr-splash.png -t image/png >/dev/null 2>&1; detail="splash shown" ;;
    status)      if [ -f "$FLAG" ]; then detail="splash: disabled"; else detail="splash: enabled"; fi ;;
    *)           status="err"; detail="unknown splash: $splash" ;;
  esac
fi

if [ -n "$kill_pid" ]; then
  case "$kill_pid" in
    ''|*[!0-9]*) status="err"; detail="bad pid" ;;
    *) if kill "$kill_pid" 2>/dev/null; then
         detail="killed $kill_pid"
       elif kill -9 "$kill_pid" 2>/dev/null; then
         detail="force-killed $kill_pid"
       else
         status="err"; detail="kill failed $kill_pid"
       fi ;;
  esac
fi

if [ -n "$admin" ]; then
  case "$admin" in
    trim_cache)   pm trim-caches 1G >/dev/null 2>&1; detail="cache trimmed" ;;
    restart_httpd)
      pkill -f "busybox httpd.*8787" 2>/dev/null
      sleep 1
      sh /data/adb/modules/tvremoteweb/service.sh >/dev/null 2>&1 &
      detail="httpd restart triggered" ;;
    restart_mouse)
      MD=/data/adb/modules/tvremoteweb/files/bin/mousedaemon
      pkill -f "$MD" 2>/dev/null
      [ -x "$MD" ] && TVR_WS_PORT=8788 TVR_TOKEN="$pin" nohup "$MD" > /data/adb/tvremoteweb/mousedaemon.log 2>&1 &
      detail="mousedaemon restarted" ;;
    wifi_reconnect)
      svc wifi disable 2>/dev/null; sleep 1; svc wifi enable 2>/dev/null
      detail="wifi cycled" ;;
    drop_caches)
      sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
      detail="page cache dropped" ;;
    logcat)
      echo "Content-Type: text/plain"; echo "Access-Control-Allow-Origin: *"; echo
      logcat -d -t 100 2>/dev/null | tail -100
      exit 0 ;;
    *) status="err"; detail="unknown admin: $admin" ;;
  esac
fi

if [ -n "$sys" ]; then
  case "$sys" in
    reboot)        (sleep 1; reboot) & detail="rebooting" ;;
    screen_off)    input keyevent KEYCODE_POWER; detail="screen off" ;;
    home)          input keyevent KEYCODE_HOME; detail="home" ;;
    back)          input keyevent KEYCODE_BACK; detail="back" ;;
    volup)         input keyevent KEYCODE_VOLUME_UP; detail="vol+" ;;
    voldown)       input keyevent KEYCODE_VOLUME_DOWN; detail="vol-" ;;
    mute)          input keyevent KEYCODE_VOLUME_MUTE; detail="mute" ;;
    recent)        input keyevent KEYCODE_APP_SWITCH; detail="recent apps" ;;
    notif)         cmd statusbar expand-notifications; detail="notif" ;;
    settings)      am start -a android.settings.SETTINGS; detail="settings" ;;
    wifi_settings) am start -a android.settings.WIFI_SETTINGS; detail="wifi settings" ;;
    *)             status="err"; detail="unknown sys: $sys" ;;
  esac
fi

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo
printf '{"status":"%s","detail":"%s"}\n' "$status" "$detail"
