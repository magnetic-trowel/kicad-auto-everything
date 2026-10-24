#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Baselines: five methods on ab33, budget 120 CPU-s, 3 seeds, joint tasks, all in parallel
# at -j ${J:-4} each.
#   baselines.sh [PREFIX=xf2]     runs PREFIX-base-<method>-ab33
# Round 2 used xf2, round 3 (engine fixes) xf3. Logs in $XF_WORK/PREFIX-base-*.log, exit
# codes in $XF_WORK/PREFIX-baselines.log (round 2: baselines.log). Run inside the scope.
P=${1:-xf2}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
. "$HERE/env.sh"
LOG="$XF_WORK/$P-baselines.log"
run() { "$HERE/runext.sh" "$1" "$2" 120 "$XF_WORK/ab33.txt" "${J:-4}" 3 > "$XF_WORK/$2.log" 2>&1
        echo "$2 exit=$?" >> "$LOG"; }
run "$R/collapse_joint/jc.py:jc" "$P-base-jc-ab33" &
run "$R/collapse_joint/jc.py:jc_lv_nopol" "$P-base-jc_lv_nopol-ab33" &
run "$R/collapse_joint/jc.py:jc_full" "$P-base-jc_full-ab33" &
run "$R/pnr/methods_combo.py:combo" "$P-base-combo-ab33" &
run "$R/pnr/methods_combo.py:combo_lv" "$P-base-combo_lv-ab33" &
wait
echo BASELINES_DONE >> "$LOG"
