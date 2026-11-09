#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the bus-alone Freerouting install: the fork at the commit the stored `fr-fork master` control used, with the
# bus-net filter wrapper and this experiment's bus-net lists. Usage: install.sh BUSNETS_DIR
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HOME/.cache/kaebench/kae-freerouting-fork-06d2686
DEST=$HOME/.cache/kaebench/kae-freerouting-fork-06d2686-busalone-v1
BUSNETS=$1
rm -rf "$DEST.tmp"
cp -a "$SRC" "$DEST.tmp"
mv "$DEST.tmp/bin/freerouting" "$DEST.tmp/bin/freerouting.real"
cp "$HERE/wrapper/freerouting" "$HERE/wrapper/filter_dsn.py" "$DEST.tmp/bin/"
mkdir "$DEST.tmp/busnets"
# the lists only (kaeres keeps the whole install as the method's binary): names are net names of public boards
find "$BUSNETS" -maxdepth 1 -name '*.txt' -exec cp -t "$DEST.tmp/busnets" {} +
rm -rf "$DEST"
mv "$DEST.tmp" "$DEST"
echo "$DEST"
