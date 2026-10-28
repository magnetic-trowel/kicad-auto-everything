# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Functional evaluation by circuit simulation (docs/topics/physics/functional-evaluation.md).

A board's operating intent is a testbench: SPICE text with `*@` annotations (testbench.py), written
by code (autotb.py), a human or an LLM, naming pins and nets as KiCad does (`<U5.12>`, `<+3V3>`).
Each test is simulated twice per corner of its parameter intervals:

- ideal: every pin of a net on one node (the schematic);
- routed: the nets the test names replaced by their extracted copper (extract.py): per piece
  series R and L, C to the reference plane, via barrels, coupling C and mutual L to neighbours.

The simulator never sees KiCad names: names.py maps them to safe nodes (ngspice folds case, shorts a
top-level `x1.n` to subcircuit X1's node n, and reads "10uF 35V" as 35 F). evaluate.py turns the
measurements into verdicts with intervals, the layout's effect (routed minus ideal) and capability.
"""
