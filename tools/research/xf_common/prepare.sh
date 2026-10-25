#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Prepare the qualified boards into $XF_WORK (default kae-work2) with this branch's harness.
#   prepare.sh [JOBS=8]
# Boards come from $XF_WORK/cache (filled by seed_cache.py, or copied from another work
# dir); nothing is downloaded if the cache is complete. Run it inside the CPU/memory scope.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/../../.."
. tools/research/xf_common/env.sh
ulimit -v 40000000
kaebench --workdir "$XF_WORK" prepare -m bench/manifests/candidates.jsonl \
  --only @bench/suites/qualified-kicad-10.0.7.txt -j "${1:-8}"
