# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Buses: nets meant to be routed as one object, and report-only measurements of them.

`detect` finds buses from what a new board has (netlist, names, footprints, part data, pin
geometry); it never reads tracks or vias, so it works on a board no human has routed.
`scorecard` measures a routed board's buses. The scorecard is a report: it changes no score
and does not reward bundling (see docs/research/routing/bus-yardstick-2611.md).
"""
from .detect import detect_board, BusSet

__all__ = ["detect_board", "BusSet"]
