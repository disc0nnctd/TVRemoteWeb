#!/usr/bin/env bash
# Build + sign the QR launcher tile APK.
# Needs: apktool, a JDK, and Android build-tools (zipalign, apksigner).
#
# resources.arsc MUST end up stored-uncompressed and 4-byte aligned or
# Android 11+ refuses the install (INSTALL_PARSE_FAILED ... -124). That is
# why apktool.yml lists it under doNotCompress and why zipalign runs before
# apksigner (apksigner preserves alignment; re-zipping after would not).
set -euo pipefail
cd "$(dirname "$0")"

BT="${ANDROID_BUILD_TOOLS:-$HOME/.local/android-build/sdk/build-tools/34.0.0}"
KEYSTORE="${TVR_KEYSTORE:-$HOME/.tvremoteweb/release.keystore}"
KS_PASS="${TVR_KEYSTORE_PASS:-tvremoteweb}"
OUT="../../module/files/app/tvremoteweb-qr.apk"

mkdir -p "$(dirname "$OUT")" build

apktool b project -o build/unsigned.apk

"$BT/zipalign" -p -f 4 build/unsigned.apk build/aligned.apk
"$BT/zipalign" -c -v 4 build/aligned.apk >/dev/null && echo "alignment ok"

if [ ! -f "$KEYSTORE" ]; then
  echo "generating a signing key at $KEYSTORE"
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair -v -keystore "$KEYSTORE" \
    -storepass "$KS_PASS" -keypass "$KS_PASS" -alias tvremoteweb \
    -keyalg RSA -keysize 2048 -validity 10950 \
    -dname "CN=TVRemoteWeb, O=TVRemoteWeb, C=US"
fi

"$BT/apksigner" sign \
  --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --ks-key-alias tvremoteweb \
  --v1-signing-enabled true --v2-signing-enabled true \
  --out "$OUT" build/aligned.apk

"$BT/apksigner" verify "$OUT" && echo "signed ok"
grep -oP "versionCode: '\K[0-9]+" project/apktool.yml > "$(dirname "$OUT")/versionCode"
aapt dump badging "$OUT" | grep -E "package:|launchable-activity" || true
echo "built $OUT"
