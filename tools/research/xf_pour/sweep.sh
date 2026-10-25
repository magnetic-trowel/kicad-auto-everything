#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# dev6 weight sweep (K = 30, 100, 300) of the coupled maps; old engine (v6.1), run names xf2C-sw-*.
cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && source tools/research/xf_common/env.sh
P=$XF_ROOT/tools/research/xf_pour/pjc.py
run() { $XF_WORK/runext.sh "$P:$1" "$2" 120 $XF_WORK/dev6.txt 2 3 > $XF_WORK/$2.log 2>&1; echo "$2 exit=$?" >> $XF_WORK/xf_pour/sweep.done; }
for K in 30 100 300; do
  run pjc2_k$K xf2C-sw-pjc2-k$K-dev6 &
  run pjc2_lv_nopol_k$K xf2C-sw-pjc2_lv-k$K-dev6 &
done
wait
echo ALL_DONE >> $XF_WORK/xf_pour/sweep.done
