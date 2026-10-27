#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Full sweep for experiment C: 4 arms (pjc, pjc_lv_nopol = per-layer maps; pjc2, pjc2_lv_nopol =
# layer-coupled maps), ab33, budget 120, 3 seeds, -j 3 each. Run inside the CPU/memory scope:
#   tmux new -d -s xf3C-runs "systemd-run --user --scope -p AllowedCPUs=80-91 -p MemoryMax=24G \
#     -p MemoryHigh=20G tools/research/xf_pour/runs.sh xf3C > kae-work2/xf_pour/runs.log 2>&1"
PREFIX=${1:?prefix, e.g. xf3C}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/../../.." && source tools/research/xf_common/env.sh
P=$HERE/pjc.py
D=$XF_WORK/xf_pour; mkdir -p $D; rm -f $D/$PREFIX-runs.done
run() { $XF_WORK/runext.sh "$P:$1" "$2" 120 $XF_WORK/ab33.txt 3 3 > $XF_WORK/$2.log 2>&1
        echo "$2 exit=$?" >> $D/$PREFIX-runs.done; }
run pjc $PREFIX-pjc-ab33 &
run pjc_lv_nopol $PREFIX-pjc_lv_nopol-ab33 &
run pjc2 $PREFIX-pjc2-ab33 &
run pjc2_lv_nopol $PREFIX-pjc2_lv_nopol-ab33 &
wait
echo ALL_DONE >> $D/$PREFIX-runs.done
