<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pour truth tools

`truth.py BOARD OUT.json` (KiCad's python): after a refill, the pads of every zone net grouped by KiCad's connectivity.
Run on a routed board and on the same board with routing stripped (`pcbnew_ops.py strip-routing`) to tell whether
pads that are apart in the routed board were joined by the bare fill (cut by routing) or were already apart.

`variants.py BOARD OUT.json`: the same on the routed board under changed zone settings (minimum width about 0, solid
pad connections, both), to name which fill rule causes the separation.

Used by [freerouting-pour-truth](../../../../docs/research/routing/freerouting-pour-truth.md).
