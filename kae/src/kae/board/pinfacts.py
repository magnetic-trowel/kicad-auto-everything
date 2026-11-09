# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin facts from a board's schematic (pin type and pin name per pad) that the board file never received.

Half the corpus are KiCad 5, Eagle or other imports whose pads carry no pin type or name; kaeres recovers
them from the project's schematic (tools/kaeres/pintypes.py, `kaeres.pintypes/1`). Everything that reads the
circuit off the board (kae.circuit.brief: rails, regulators, switching cells; kae.excite: loads and observers)
must see the same pins, or an intent compiled from one view names sections the evaluator never finds. The
operating facts carry them (`pins`), and kae.excite.evaluate and kae.intent apply them the same way.

    pins = {ref: {pad number: [type, name]}}
"""
from __future__ import annotations


def from_pintypes(doc):
    """The compact `pins` map from a kaeres.pintypes/1 document: {ref: {number: [type, name]}}, pads with
    neither left out."""
    out = {}
    for ref, m in ((doc or {}).get("refs") or {}).items():
        row = {str(n): [p.get("type") or "", p.get("name") or ""] for n, p in (m or {}).items()
               if isinstance(p, dict) and (p.get("type") or p.get("name"))}
        if row:
            out[ref] = row
    return out


def apply(board, pins):
    """Fill each pad's pin type and name from `pins` where the board carries neither (a pad the board's own
    file annotates is left alone). Returns the number of pads filled."""
    n = 0
    for fp in board.footprints if pins else ():
        m = pins.get(fp.ref)
        for pad in fp.pads if m else ():
            pin = m.get(str(pad.number))
            if pin and not pad.pintype and not pad.pinfunction:
                pad.pintype, pad.pinfunction = pin[0] or "", pin[1] or ""
                n += 1
    return n
