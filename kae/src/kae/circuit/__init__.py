# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Comprehension: what each part, net and structure of a board is doing physically.

`kae.circuit.brief.build(board)` returns the physics brief (Contract 2 of
docs/topics/architecture/month-plan.md) for a kae.board Board: net roles, part roles and
structures (commutation cells, decoupling, crystals, connector chains, victims, heat,
antennas), each with a confidence and its evidence. It reads only what the board file
states (names, values, footprints, lib ids, pin functions and types, fields, net classes,
sheet names), never positions. Rules and measured accuracy:
docs/topics/physics/comprehension.md.

Modules: values (parsers), evidence (the evidence model), netlist (the board view),
roles (part and net roles), structures (physical structures), brief (assembly, JSON).
"""
__all__ = ['build', 'write']


def __getattr__(name):
    # lazy, so `python -m kae.circuit.brief` does not import the module twice
    if name in __all__:
        from . import brief
        return getattr(brief, name)
    raise AttributeError(name)
