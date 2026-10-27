#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# usage: merge_runs.sh NEW_RUN RUN1 RUN2 ...   (symlinks every board of the runs into one run
# directory so compare.py / physics_score.py see a single all-board run; same config only)
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
cd $REPO/kae-work/results
new=$1; shift
mkdir -p "$new/x-$new/place"
for r in "$@"; do
  for d in "$r"/*/place/*; do
    ln -sfn "$PWD/$d" "$new/x-$new/place/$(basename "$d")"
  done
done
ls "$new/x-$new/place" | wc -l
