#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Set up a kaebench host (Ubuntu 22.04/24.04 x86_64): KiCad 10, Freerouting 2.5.0, venv.
#
#   bench/scripts/setup.sh [--no-kicad] [--no-freerouting] [--venv DIR]
#
# Environment: KAE_HOME (default ~/.cache/kaebench) holds Freerouting.
set -euo pipefail

BENCH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KAE_HOME="${KAE_HOME:-$HOME/.cache/kaebench}"
VENV="$BENCH_DIR/.venv"
DO_KICAD=1
DO_FR=1
FR_VERSION="2.5.0"
FR_ZIP_SHA256="e8ffca14914e5307a2fa9aea723fb93d11b99bebda20d126472da5460c03196e"

while [ $# -gt 0 ]; do
  case "$1" in
    --no-kicad) DO_KICAD=0 ;;
    --no-freerouting) DO_FR=0 ;;
    --venv) VENV="$2"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

kicad_major() { kicad-cli version 2>/dev/null | cut -d. -f1; }

if [ "$DO_KICAD" = 1 ]; then
  if [ "$(kicad_major || echo 0)" -ge 10 ] 2>/dev/null; then
    echo "KiCad $(kicad-cli version) already installed"
  elif [ -r /etc/os-release ] && . /etc/os-release && [ "${ID:-}" = ubuntu ]; then
    echo "Installing KiCad 10 from ppa:kicad/kicad-10.0-releases (no recommends)"
    FP=$(curl -fsSL "https://api.launchpad.net/1.0/~kicad/+archive/ubuntu/kicad-10.0-releases" |
         python3 -c "import json,sys; print(json.load(sys.stdin)['signing_key_fingerprint'])")
    curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$FP" |
      $SUDO gpg --dearmor --yes -o /usr/share/keyrings/kicad-10.gpg
    echo "deb [signed-by=/usr/share/keyrings/kicad-10.gpg] https://ppa.launchpadcontent.net/kicad/kicad-10.0-releases/ubuntu ${VERSION_CODENAME} main" |
      $SUDO tee /etc/apt/sources.list.d/kicad-10.list >/dev/null
    $SUDO apt-get update -qq
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends kicad
  else
    echo "Install KiCad 10 for your OS (https://www.kicad.org/download/), then re-run with --no-kicad" >&2
    exit 1
  fi
fi

if [ "$DO_FR" = 1 ]; then
  DEST="$KAE_HOME/freerouting-$FR_VERSION-linux-x64"
  if [ -x "$DEST/bin/freerouting" ]; then
    echo "Freerouting $FR_VERSION already at $DEST"
  else
    mkdir -p "$KAE_HOME"
    ZIP="$KAE_HOME/freerouting-$FR_VERSION-linux-x64.zip"
    curl -fsSL -o "$ZIP" \
      "https://github.com/freerouting/freerouting/releases/download/v$FR_VERSION/freerouting-$FR_VERSION-linux-x64.zip"
    echo "$FR_ZIP_SHA256  $ZIP" | sha256sum -c -
    python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP" "$KAE_HOME"
    chmod +x "$DEST/bin/freerouting" "$DEST/lib/runtime/bin/"* "$DEST/lib/runtime/lib/jspawnhelper" 2>/dev/null || true
    rm -f "$ZIP"
  fi
fi

if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" 2>/dev/null; then
  $SUDO apt-get install -y -qq python3-venv
fi
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$BENCH_DIR[test]"
echo
"$VENV/bin/kaebench" doctor
echo
echo "Activate with: source $VENV/bin/activate"
