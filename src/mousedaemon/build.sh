#!/usr/bin/env bash
# Build static mousedaemon binaries for each supported ABI.
#   apt install gcc-arm-linux-gnueabihf gcc-aarch64-linux-gnu
set -euo pipefail
cd "$(dirname "$0")"
OUT="../../module/files/bin"
mkdir -p "$OUT"
FLAGS="-static -O2 -Wall -Wno-unused-result"

build() {  # $1=cc  $2=suffix
  if command -v "$1" >/dev/null 2>&1; then
    "$1" $FLAGS -o "$OUT/mousedaemon-$2" mousedaemon.c
    echo "built $2  ($(stat -c%s "$OUT/mousedaemon-$2") bytes)"
  else
    echo "skip $2 — $1 not installed"
  fi
}

build arm-linux-gnueabihf-gcc armv7
build aarch64-linux-gnu-gcc   arm64
build x86_64-linux-gnu-gcc    x86_64
