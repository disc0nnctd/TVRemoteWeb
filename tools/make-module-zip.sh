#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(sed -n 's/^version=//p' "$ROOT/module/module.prop")"
OUT="$ROOT/tvremoteweb-v${VER}.zip"
rm -f "$OUT"
cd "$ROOT/module"
zip -r9 "$OUT" . -x '.*' >/dev/null
echo "built $OUT ($(stat -c%s "$OUT") bytes)"
