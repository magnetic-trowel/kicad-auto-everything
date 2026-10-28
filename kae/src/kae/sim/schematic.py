# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Component values and fields from a KiCad 6+ schematic, through `kicad-cli sch export netlist`.

Some boards carry no values in their footprints (the value lives only on the schematic symbol, e.g.
boards exported from other tools). `fields(root)` returns {reference: {"Value": ..., field: ...}} for
every component of the schematic hierarchy, read from KiCad's own netlist export (kicadsexpr), so
sheet instances and multi-unit symbols resolve as KiCad resolves them. KiCad 5 `.sch` files are not
read by kicad-cli 10 (it returns an empty netlist); their boards need a schematic upgrade in KiCad first.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from kae.board import sexpr


def fields(root, timeout=300):
    from kae.route.drc import kicad_cli
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(dir=root.parent) as td:
        out = Path(td) / "netlist.net"
        p = subprocess.run(list(kicad_cli()) + ["sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(root)],
                           capture_output=True, text=True, timeout=timeout)
        if not out.exists():
            raise RuntimeError(f"kicad-cli netlist export failed: {(p.stdout + p.stderr)[-500:]}")
        tree = sexpr.parse(out.read_text())
    comps = sexpr.first(tree, "components")
    res = {}
    for c in sexpr.kids(comps, "comp") if comps else ():
        ref = sexpr.value(c, "ref")
        if not ref:
            continue
        d = {"Value": sexpr.value(c, "value") or ""}
        fp = sexpr.value(c, "footprint")
        if fp:
            d["Footprint"] = fp
        fl = sexpr.first(c, "fields")
        for f in sexpr.kids(fl, "field") if fl else ():
            nm = sexpr.value(f, "name")
            if nm and len(f) > 2 and isinstance(f[-1], str):
                d[nm] = f[-1]
        res[ref] = d
    return res


def fill_values(board, comp_fields):
    """Give footprints with an empty value their schematic value; returns how many were filled."""
    n = 0
    for fp in board.footprints:
        v = (comp_fields.get(fp.ref) or {}).get("Value")
        if v and not (fp.value or "").strip():
            fp.value = v
            fp.fields["Value"] = v
            n += 1
    return n
