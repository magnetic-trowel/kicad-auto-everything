# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route: a KiCad -> Freerouting -> KiCad bridge that carries KiCad's design rules.

Every constraint KiCad's DRC checks either reaches Freerouting through the Specctra DSN
(class widths per layer, a class-to-class clearance matrix, per-pad clearance classes,
exact keepouts for edges, holes, no-net copper and thermal spokes, via padstacks sized to
the rules) or is enforced after routing (KiCad DRC on the imported board, deterministic
widening, rip-up and re-route of the offending nets).

    python -m kae.route.cli route INPUT OUTPUT [--seed N] [--time S]

Modules: specctra (DSN/SES trees), rules (KiCad's rule engine for pairs of items),
constraints (effective constraints per net, layer and pair), translate (DSN augmentation),
freerouting (running the router), repair (post-route DRC repair), bridge (the pipeline),
cli. See docs/topics/routing/freerouting-constraint-bridge.md.
"""
