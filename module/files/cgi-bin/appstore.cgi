#!/system/bin/sh
# TVRemoteWeb — install/manage third-party apps from the phone remote.
#
# Search is proxied server-side because search.f-droid.org and f-droid.org
# send no CORS headers, so the phone browser cannot call them directly.
# Installing requires an explicit INSTALL confirmation from the phone, then
# runs `pm install -r` as root. (Android 11's PackageInstaller only accepts
# content:// URIs, so handing it a file:// path from the shell silently does
# nothing.) Android still verifies the APK, and an update must carry the same
# signature as the installed app.
#
# SPDX-License-Identifier: MIT

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"
STATE="/data/adb/tvremoteweb"
DL_PATH="/data/local/tmp/tvremoteweb-install.apk"
MAX_UPLOAD_BYTES=157286400

urldecode() { "$BB" httpd -d "${1:-}"; }
qget() {
  key="$1"; old_ifs="$IFS"; IFS='&'
  for kv in ${QUERY_STRING:-}; do
    IFS="$old_ifs"; k="${kv%%=*}"; v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$old_ifs"; return 1
}

# install_apk installs $DL_PATH, removes it, and prints a one-line result
# (no quotes or backslashes, so it can go straight into JSON).
install_apk() {
  out="$(pm install -r -g "$DL_PATH" 2>&1 | "$BB" tr -d '"\\' | "$BB" tail -n 1)"
  rm -f "$DL_PATH"
  case "$out" in
    Success*) echo "Installed. Find it on the home screen."; return 0 ;;
    *INSTALL_FAILED_UPDATE_INCOMPATIBLE*) echo "Install failed: an app with this name is already installed with a different signature. Uninstall it first."; return 1 ;;
    *INSTALL_FAILED_VERSION_DOWNGRADE*) echo "Install failed: a newer version is already installed."; return 1 ;;
    *INSTALL_FAILED_NO_MATCHING_ABIS*) echo "Install failed: this APK is not built for the projector's processor (needs armeabi-v7a)."; return 1 ;;
    *) echo "Install failed: ${out:-no output from the package manager}"; return 1 ;;
  esac
}

# upload_install streams a raw binary POST body straight to disk — it must run
# before the generic query/body parser below, which slurps and text-decodes the
# body and would corrupt (and, at its 4096-byte cap, truncate) an APK.
if [ "$(qget action 2>/dev/null || true)" = "upload_install" ]; then
  token_full=""; pin=""
  if [ -s "$TOKEN_FILE" ]; then
    token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
    [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
  fi
  qt="$(qget token 2>/dev/null || true)"
  if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
    echo "Status: 403 Forbidden"; echo "Content-Type: application/json"; echo
    echo '{"status":"err","detail":"forbidden"}'
    exit 0
  fi
  fail() {
    echo "Content-Type: application/json"; echo "Access-Control-Allow-Origin: *"; echo "Cache-Control: no-store"; echo
    printf '{"status":"err","detail":"%s"}\n' "$1"
    exit 0
  }
  [ "${REQUEST_METHOD:-GET}" = "POST" ] || fail "uploading requires POST"
  [ "$(qget confirmation 2>/dev/null || true)" = "INSTALL" ] || fail "uploading requires INSTALL confirmation"
  length="${CONTENT_LENGTH:-0}"
  case "$length" in ''|*[!0-9]*) fail "missing content length" ;; esac
  [ "$length" -gt 0 ] || fail "empty upload"
  [ "$length" -le "$MAX_UPLOAD_BYTES" ] || fail "file too large (150MB limit)"
  rm -f "$DL_PATH"
  : > "$DL_PATH"
  # head -c keeps reading until it has the whole body; dd count= would stop
  # early on the short reads a network socket delivers and truncate the APK.
  "$BB" head -c "$length" > "$DL_PATH"
  size="$("$BB" stat -c%s "$DL_PATH" 2>/dev/null || echo 0)"
  [ "$size" = "$length" ] || { rm -f "$DL_PATH"; fail "upload was cut short ($size of $length bytes)"; }
  magic="$(dd if="$DL_PATH" bs=1 count=2 2>/dev/null)"
  if [ "$size" -lt 4096 ] || [ "$magic" != "PK" ]; then
    rm -f "$DL_PATH"
    fail "uploaded file is not a valid APK"
  fi
  result="$(install_apk)" || fail "$result"
  echo "Content-Type: application/json"; echo "Access-Control-Allow-Origin: *"; echo "Cache-Control: no-store"; echo
  printf '{"status":"ok","detail":"%s"}\n' "$result"
  exit 0
fi

PARAMS="${QUERY_STRING:-}"
if [ "${REQUEST_METHOD:-GET}" = "POST" ]; then
  length="${CONTENT_LENGTH:-0}"
  case "$length" in ''|*[!0-9]*) length=0 ;; esac
  [ "$length" -gt 4096 ] && length=4096
  body="$(dd bs=1 count="$length" 2>/dev/null)"
  [ -n "$body" ] && PARAMS="${PARAMS:+$PARAMS&}$body"
fi

get_param() {
  key="$1"; old_ifs="$IFS"; IFS='&'
  for kv in $PARAMS; do
    IFS="$old_ifs"; k="${kv%%=*}"; v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$old_ifs"; return 1
}

respond() {
  status="$1"; detail="$2"; extra="$3"
  echo "Content-Type: application/json"
  echo "Access-Control-Allow-Origin: *"
  echo "Cache-Control: no-store"
  echo
  if [ -n "$extra" ]; then
    printf '{"status":"%s","detail":"%s",%s}\n' "$status" "$detail" "$extra"
  else
    printf '{"status":"%s","detail":"%s"}\n' "$status" "$detail"
  fi
  exit 0
}
respond_error() { respond "err" "$1" ""; }

token_full=""; pin=""
if [ -s "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"; echo "Content-Type: application/json"; echo
  echo '{"status":"err","detail":"forbidden"}'
  exit 0
fi

# Package names only ever come back out as [a-zA-Z0-9_.] — anything else is rejected
# before it ever reaches a shell command.
valid_pkg() {
  case "$1" in
    ''|*[!a-zA-Z0-9_.]*) return 1 ;;
    *) return 0 ;;
  esac
}

# Minimal outbound query encoding: only letters/digits/space/+-. are ever sent;
# anything else is dropped rather than risk building a malformed request URL
# (busybox httpd has no URL-encode applet, only decode).
safe_query() {
  printf '%s' "$1" | "$BB" tr -cd 'A-Za-z0-9 +.-' | "$BB" sed 's/ /%20/g'
}

action="$(get_param action 2>/dev/null || true)"

case "$action" in

  fdroid_search)
    q="$(get_param q 2>/dev/null || true)"
    [ -n "$q" ] || respond_error "empty search"
    q_safe="$(safe_query "$q")"
    [ -n "$q_safe" ] || respond_error "search term has no usable characters"
    json="$("$BB" wget -q -T 8 -O - "https://search.f-droid.org/api/search_apps?q=$q_safe" 2>/dev/null)"
    if [ -z "$json" ]; then
      respond_error "F-Droid search failed. Check the projector's own internet connection."
    fi
    echo "Content-Type: application/json"
    echo "Access-Control-Allow-Origin: *"
    echo "Cache-Control: no-store"
    echo
    printf '%s' "$json"
    exit 0
    ;;

  fdroid_resolve)
    pkg="$(get_param pkg 2>/dev/null || true)"
    valid_pkg "$pkg" || respond_error "invalid package name"
    meta="$("$BB" wget -q -T 8 -O - "https://f-droid.org/api/v1/packages/$pkg" 2>/dev/null)"
    [ -n "$meta" ] || respond_error "could not resolve this app on F-Droid"
    code="$(printf '%s' "$meta" | "$BB" grep -o '"suggestedVersionCode":[0-9]*' | head -1 | cut -d: -f2)"
    [ -n "$code" ] || respond_error "F-Droid did not report a version for this app"
    url="https://f-droid.org/repo/${pkg}_${code}.apk"
    respond "ok" "Resolved." "\"url\":\"$url\""
    ;;

  aptoide_search)
    q="$(get_param q 2>/dev/null || true)"
    [ -n "$q" ] || respond_error "empty search"
    q_safe="$(safe_query "$q")"
    [ -n "$q_safe" ] || respond_error "search term has no usable characters"
    json="$("$BB" wget -q -T 8 -O - "https://ws75.aptoide.com/api/7/apps/search/query=$q_safe/limit=12" 2>/dev/null)"
    if [ -z "$json" ]; then
      respond_error "Aptoide search failed. Check the projector's own internet connection."
    fi
    echo "Content-Type: application/json"
    echo "Access-Control-Allow-Origin: *"
    echo "Cache-Control: no-store"
    echo
    printf '%s' "$json"
    exit 0
    ;;

  installed)
    list="$(pm list packages -3 2>/dev/null | "$BB" sed 's/^package://')"
    first=1
    echo "Content-Type: application/json"
    echo "Access-Control-Allow-Origin: *"
    echo "Cache-Control: no-store"
    echo
    printf '{"status":"ok","packages":['
    for p in $list; do
      [ "$first" = "1" ] || printf ','
      printf '"%s"' "$p"
      first=0
    done
    printf ']}\n'
    exit 0
    ;;

  download_install)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "installing requires POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "INSTALL" ] || respond_error "installing requires INSTALL confirmation"
    url="$(get_param url 2>/dev/null || true)"
    case "$url" in
      https://*) ;;
      *) respond_error "only https:// download links are accepted" ;;
    esac
    rm -f "$DL_PATH"
    if ! "$BB" wget -q -T 20 -O "$DL_PATH" "$url" 2>/dev/null; then
      rm -f "$DL_PATH"
      respond_error "download failed"
    fi
    size="$("$BB" stat -c%s "$DL_PATH" 2>/dev/null || echo 0)"
    magic="$(dd if="$DL_PATH" bs=1 count=2 2>/dev/null)"
    if [ "$size" -lt 4096 ] || [ "$magic" != "PK" ]; then
      rm -f "$DL_PATH"
      respond_error "downloaded file is not a valid APK"
    fi
    result="$(install_apk)" || respond_error "$result"
    respond "ok" "$result" ""
    ;;

  uninstall)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || respond_error "uninstalling requires POST"
    [ "$(get_param confirmation 2>/dev/null || true)" = "UNINSTALL" ] || respond_error "uninstalling requires UNINSTALL confirmation"
    pkg="$(get_param pkg 2>/dev/null || true)"
    valid_pkg "$pkg" || respond_error "invalid package name"
    if pm uninstall "$pkg" >/dev/null 2>&1; then
      respond "ok" "Uninstalled." ""
    else
      respond_error "uninstall failed"
    fi
    ;;

  *) respond_error "unknown action" ;;
esac
