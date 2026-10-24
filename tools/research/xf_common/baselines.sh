#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Round-2 baselines: five methods on ab33, budget 120 CPU-s, 3 seeds, joint tasks, all in
# parallel at -j ${J:-4} each. Logs in $XF_WORK/xf2-base-*.log. Run inside the scope.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
. "$HERE/env.sh"
run() { "$HERE/runext.sh" "$1" "$2" 120 "$XF_WORK/ab33.txt" "${J:-4}" 3 > "$XF_WORK/$2.log" 2>&1
        echo "$2 exit=$?" >> "$XF_WORK/baselines.log"; }
run "$R/collapse_joint/jc.py:jc" xf2-base-jc-ab33 &
run "$R/collapse_joint/jc.py:jc_lv_nopol" xf2-base-jc_lv_nopol-ab33 &
run "$R/collapse_joint/jc.py:jc_full" xf2-base-jc_full-ab33 &
run "$R/pnr/methods_combo.py:combo" xf2-base-combo-ab33 &
run "$R/pnr/methods_combo.py:combo_lv" xf2-base-combo_lv-ab33 &
wait
echo BASELINES_DONE >> "$XF_WORK/baselines.log"
