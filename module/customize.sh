#!/system/bin/sh
# TVRemoteWeb — Magisk install script.
# Runs once at flash time (Magisk sources this with $MODPATH set).
#
# Responsibilities:
#   1. pick the mousedaemon binary matching this device's ABI
#   2. generate a random access token (never shipped in the repo)
#   3. install the bundled "Phone Remote QR" launcher tile APK
#
# SPDX-License-Identifier: MIT

SKIPUNZIP=0

STATE=/data/adb/tvremoteweb
BINDIR="$MODPATH/files/bin"

ui_print " "
ui_print "  TVRemoteWeb"
ui_print "  browser remote for Android TV"
ui_print " "

# ---------------------------------------------------------------- ABI ----
ABI="$(getprop ro.product.cpu.abi)"
ui_print "- device ABI: $ABI"

case "$ABI" in
  arm64*|aarch64*) PICK=mousedaemon-arm64 ;;
  armeabi*|armv7*) PICK=mousedaemon-armv7 ;;
  x86_64)          PICK=mousedaemon-x86_64 ;;
  *)               PICK="" ;;
esac

if [ -n "$PICK" ] && [ -f "$BINDIR/$PICK" ]; then
  mv -f "$BINDIR/$PICK" "$BINDIR/mousedaemon"
  ui_print "- pointer daemon: $PICK"
else
  ui_print "! no mousedaemon build for $ABI"
  ui_print "  the remote will still work; the touchpad will fall"
  ui_print "  back to the slower HTTP path"
fi
rm -f "$BINDIR"/mousedaemon-*
[ -f "$BINDIR/mousedaemon" ] && chmod 755 "$BINDIR/mousedaemon"

# -------------------------------------------------------------- token ----
mkdir -p "$STATE"
if [ ! -s "$STATE/token" ]; then
  TOKEN=""
  # prefer the kernel CSPRNG
  if [ -r /dev/urandom ]; then
    TOKEN="$(head -c 32 /dev/urandom 2>/dev/null | sha256sum 2>/dev/null | cut -c1-24)"
  fi
  # fall back to whatever entropy we can reach
  [ -z "$TOKEN" ] && TOKEN="$(printf '%s%s%s' "$(date +%s%N 2>/dev/null)" "$$" "$(getprop ro.serialno)" | sha256sum | cut -c1-24)"
  printf '%s' "$TOKEN" > "$STATE/token"
  chmod 600 "$STATE/token"
  ui_print "- generated a fresh access token"
else
  ui_print "- keeping the existing access token"
fi
PIN="$(cat "$STATE/token" | sha256sum | cut -c1-6)"
ui_print "- your PIN: $PIN"

# ---------------------------------------------------------------- APK ----
APK="$MODPATH/files/app/tvremoteweb-qr.apk"
if [ -f "$APK" ]; then
  # Only (re)install when absent or older than what we ship.
  NEED=1
  CUR="$(dumpsys package com.tvremoteweb.qr 2>/dev/null | grep -m1 versionCode | sed 's/.*versionCode=\([0-9]*\).*/\1/')"
  NEW="$(cat "$MODPATH/files/app/versionCode" 2>/dev/null || echo 1)"
  if [ -n "$CUR" ] && [ "$CUR" -ge "$NEW" ] 2>/dev/null; then NEED=0; fi

  if [ "$NEED" = "1" ]; then
    ui_print "- installing the QR launcher tile"
    if pm install -r -g "$APK" >/dev/null 2>&1; then
      ui_print "  installed: com.tvremoteweb.qr"
    else
      ui_print "! tile install failed (not fatal)"
      ui_print "  install it by hand later:"
      ui_print "  pm install -r $MODPATH/files/app/tvremoteweb-qr.apk"
    fi
  else
    ui_print "- QR tile already current (v$CUR)"
  fi
fi

# --------------------------------------------------------- permissions ----
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm_recursive "$MODPATH/files/cgi-bin" 0 0 0755 0755
[ -f "$BINDIR/mousedaemon" ] && set_perm "$BINDIR/mousedaemon" 0 0 0755
set_perm "$MODPATH/service.sh" 0 0 0755
[ -f "$MODPATH/action.sh" ] && set_perm "$MODPATH/action.sh" 0 0 0755

ui_print " "
ui_print "  Reboot, then browse to the address shown"
ui_print "  by the 'Phone Remote QR' tile on your home"
ui_print "  screen, or run:"
ui_print "    su -c cat $STATE/url.txt"
ui_print " "
