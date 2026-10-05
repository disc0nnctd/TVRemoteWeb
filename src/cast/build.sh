#!/usr/bin/env bash
# Builds the "Cast" home-screen tile (com.tvremoteweb.cast) from Java source.
# Needs: a JDK (javac), Android build-tools (aapt2, d8, zipalign, apksigner)
# and an android.jar. Signs with the same key as the QR tile.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_SDK:-$HOME/.local/android-build/sdk}"
BT="${ANDROID_BUILD_TOOLS:-$SDK/build-tools/34.0.0}"
JAR="${ANDROID_JAR:-$SDK/platforms/android-35/android.jar}"
JAVAC="${JAVAC:-javac}"
KEYSTORE="${TVR_KEYSTORE:-$HOME/.tvremoteweb/release.keystore}"
KS_PASS="${TVR_KEYSTORE_PASS:-tvremoteweb}"
OUT="../../module/files/app/tvremoteweb-cast.apk"

rm -rf build && mkdir -p build/classes build/dex
"$BT/aapt2" compile --dir res -o build/res.zip
"$BT/aapt2" link -I "$JAR" --manifest AndroidManifest.xml -o build/base.apk build/res.zip
"$JAVAC" -nowarn -source 8 -target 8 -bootclasspath "$JAR" -classpath "$JAR" -d build/classes $(find java -name '*.java')
"$BT/d8" --min-api 21 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
(cd build/dex && zip -q ../base.apk classes.dex)
"$BT/zipalign" -p -f 4 build/base.apk build/aligned.apk
"$BT/apksigner" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" --out "$OUT" build/aligned.apk
grep -oP 'android:versionCode="\K[0-9]+' AndroidManifest.xml > "$(dirname "$OUT")/cast-versionCode"
rm -rf build
echo "built $OUT"
