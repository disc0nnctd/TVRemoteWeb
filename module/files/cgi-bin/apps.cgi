#!/system/bin/sh
# TVRemoteWeb — enumerate launchable apps on this device.
# Returns {"tv":[{pkg,label}],"other":[{pkg,label}]}
#
# "tv"    = advertises LEANBACK_LAUNCHER (proper Android TV apps)
# "other" = advertises LAUNCHER only (phone apps, still launchable)
#
# Labels are derived from the package name because reading the real
# application label needs the framework; a shell CGI cannot. The UI lets
# you rename entries locally.
#
# SPDX-License-Identifier: MIT

BB="/data/adb/magisk/busybox"
STATE="/data/adb/tvremoteweb"
TOKEN_FILE="$STATE/token"

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

# Packages to never surface: our own tile plus obvious system plumbing.
HIDE="com.tvremoteweb.qr
android
com.android.settings.intelligence
com.android.htmlviewer
com.android.providers.media
org.chromium.webview_shell"

query() {
  cmd package query-activities --brief -a android.intent.action.MAIN -c "$1" 2>/dev/null \
    | "$BB" grep -oE '^[[:space:]]*[a-zA-Z0-9_.]+/' \
    | "$BB" sed 's#/##; s/^[[:space:]]*//' \
    | sort -u
}

# Package name -> display label.
# Known apps get their real name; everything else falls back to a heuristic:
# use the last segment, unless that segment is a generic suffix like
# "androidtv" or "stable", in which case the vendor segment reads better
# (org.jellyfin.androidtv -> Jellyfin, not Androidtv).
prettify() {
  pkg="$1"
  case "$pkg" in
    org.jellyfin.*)        printf 'Jellyfin';   return ;;
    com.stremio.*)         printf 'Stremio';    return ;;
    *smarttube*)           printf 'SmartTube';  return ;;
    *.kodi|org.xbmc.*)     printf 'Kodi';       return ;;
    com.plexapp.*)         printf 'Plex';       return ;;
    com.netflix.*)         printf 'Netflix';    return ;;
    com.spotify.*)         printf 'Spotify';    return ;;
    org.videolan.*)        printf 'VLC';        return ;;
    com.topjohnwu.magisk)  printf 'Magisk';     return ;;
    com.tvremoteweb.qr)    printf 'QR Tile';    return ;;
    com.android.tv.settings|com.android.settings) printf 'Settings'; return ;;
    *.youtube|*.youtube.*) printf 'YouTube';    return ;;
  esac
  last="${pkg##*.}"
  rest="${pkg%.*}"
  second="${rest##*.}"
  case "$last" in
    androidtv|androidTV|tv|one|stable|app|android|main|client|player|mobile|free|beta|release|leanback)
      [ -n "$second" ] && [ "$second" != "$pkg" ] && last="$second" ;;
  esac
  printf '%s' "$last" \
    | "$BB" sed 's/[0-9]*$//' \
    | "$BB" awk '{ if (length($0)) print toupper(substr($0,1,1)) substr($0,2); else print "App" }'
}

emit_list() {
  first=1
  for p in $1; do
    echo "$HIDE" | "$BB" grep -qx "$p" && continue
    lbl="$(prettify "$p")"
    [ "$first" = "1" ] || printf ','
    printf '{"pkg":"%s","label":"%s"}' "$p" "$lbl"
    first=0
  done
}

TV="$(query android.intent.category.LEANBACK_LAUNCHER)"
ALL="$(query android.intent.category.LAUNCHER)"

# "other" = ALL minus TV
OTHER=""
for p in $ALL; do
  echo "$TV" | "$BB" grep -qx "$p" || OTHER="$OTHER $p"
done

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo "Cache-Control: no-cache"
echo
printf '{"tv":['
emit_list "$TV"
printf '],"other":['
emit_list "$OTHER"
printf ']}\n'
