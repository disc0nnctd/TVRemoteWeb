#!/bin/sh
# Builds module/files/mediactl.dex (run with app_process, see remote.cgi).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_SDK:-$HOME/.local/android-build/sdk}"
OUT="$(mktemp -d)"
javac --release 8 -cp "$SDK/platforms/android-35/android.jar" -d "$OUT" "$HERE"/com/tvremoteweb/MediaCtl.java
"$SDK/build-tools/34.0.0/d8" --min-api 24 --output "$OUT" "$OUT"/com/tvremoteweb/*.class
cp "$OUT/classes.dex" "$HERE/../../module/files/mediactl.dex"
rm -rf "$OUT"
