#!/system/bin/sh
# Household mode: hand the PIN to any page on the LAN so the remote opens
# without scanning the QR. qr.cgi already shows the same PIN unauthenticated.
TOKEN_FILE="/data/adb/tvremoteweb/token"
pin=""
if [ -s "$TOKEN_FILE" ]; then
  tok="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$tok" ] && pin="$(printf '%s' "$tok" | sha256sum | cut -c1-6)"
fi
printf 'Content-Type: text/plain\r\nCache-Control: no-store\r\n\r\n%s' "$pin"
