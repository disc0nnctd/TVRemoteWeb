#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v smali >/dev/null || { echo "smali is required" >&2; exit 1; }
smali assemble "$ROOT/src/pqcli" -o "$ROOT/module/files/pqcli.dex"
echo "built $ROOT/module/files/pqcli.dex"
