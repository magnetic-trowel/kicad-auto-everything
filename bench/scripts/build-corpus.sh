#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the local board corpus (~13.8k boards, ~26 GB) from the reviewed manifests:
# fetches every board at its pinned commit or hash, converts and load-fixes it with the
# pinned KiCad image, runs DRC, and writes OUT_DIR/boards/<id>/ + OUT_DIR/manifest.jsonl.
# Resumable: rerun the same command. See docs/topics/data/local-board-corpus.md.
#
#   bench/scripts/build-corpus.sh [OUT_DIR] [WORKDIR]     (defaults ~/kae-boards ~/kae-boards-work)
#   J=8 bench/scripts/build-corpus.sh                      (parallel jobs; keep it modest, hosts rate-limit)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$HOME/kae-boards}"
WORK="${2:-$HOME/kae-boards-work}"
J="${J:-8}"
if [ ! -f "$ROOT/bench/.venv/bin/activate" ]; then
  echo "No venv: run bench/scripts/setup.sh --no-freerouting first" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$ROOT/bench/.venv/bin/activate"
kaebench doctor >/dev/null || { echo "kaebench doctor failed: KiCad 10 is not available" >&2; exit 1; }
ulimit -v 40000000  # 40 GB per process: a runaway DRC must not take the host down
BS="$ROOT/tools/research/board-sourcing"
M="$ROOT/bench/manifests"
# host-robots-restricted rows (hosts whose robots.txt disallows raw/git paths) are never fetched;
# they are included only if WORKDIR/cache already holds them.
python "$BS/corpus.py" "$OUT" -j "$J" --fetch-missing --drc --prune --no-fetch-tag host-robots-restricted \
  "wide=$M/wide.jsonl@$WORK" \
  "wide-noncommercial=$M/wide-noncommercial.jsonl@$WORK" \
  "candidates=$M/candidates.jsonl@$WORK"
