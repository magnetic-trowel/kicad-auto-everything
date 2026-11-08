# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where pad-entry overhang comes from: every entry kae.route.taut.board_stats counts as overhanging,
by pad kind and what the track is.

    python3 tools/research/routing/overhang_diag.py BOARD.kicad_pcb [--ref A.kicad_pcb] [--json OUT]

Classes (the DFM reading of each):
  smd2     a land of a two-terminal SMD part (passives, diodes): wide copper into it is a tombstoning or
           wicking risk; power copper's necks should keep it at the neck width
  smd      other SMD lands (ICs, connectors, heat pads)
  tht      plated through-hole pads: wide copper into them is normal practice for power
Per entry: net, ref/pad, land short side, track width, overhang mm^2, and with --ref whether the track
is the reference board's own (same uuid) or new copper, and the widest same-net track at that pad in
the reference (a widened track is wider than it)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from shapely.geometry import Point


def entries(board):
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.route import pad_entry as PE
    from kae.route.constraints import _pad_shapes
    b = load(Path(board))
    with tempfile.TemporaryDirectory(prefix="kae-ovd-") as d:
        info = pcbnew_io.export_dsn(Path(board), Path(d) / "board.dsn", probes=False)
    per_fp = {}
    for pd in info.get("pads") or []:
        per_fp.setdefault(pd.get("ref"), []).append(pd)
    pads = {}
    for pd in info.get("pads") or []:
        dsn, real = _pad_shapes(pd)
        sibs = per_fp.get(pd.get("ref"), [])
        cu = [x for x in sibs if x.get("layers")]
        two = len(cu) == 2 and all(x.get("attr") == "smd" for x in cu)
        kind = "tht" if pd.get("attr") != "smd" else ("smd2" if two else "smd")
        for l in pd.get("layers") or []:
            g = real.get(l) or dsn
            if g is not None and not g.is_empty:
                pads.setdefault((pd.get("net") or "", l), []).append((g, pd, kind))
    out = []
    for t in b.tracks:
        if t.mid is not None:
            continue
        for g, pd, kind in pads.get((t.net, t.layer), ()):
            ina, inb = g.contains(Point(t.start)), g.contains(Point(t.end))
            if ina == inb:
                continue
            ov = PE.overhang(g, t.end if ina else t.start, t.start if ina else t.end, t.width)
            if ov > PE.OVER_AREA:
                out.append(dict(uuid=t.uuid, net=t.net, layer=t.layer, ref=pd.get("ref"), pad=pd.get("number"),
                                kind=kind, land=round(PE.land_width(g), 3), w=round(t.width, 3), mm2=round(ov, 4),
                                pad_xy=pd.get("pos")))
    return out, b


def main(argv):
    board = argv[0]
    ref = argv[argv.index("--ref") + 1] if "--ref" in argv else None
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    ents, _b = entries(board)
    refw = {}
    ids = set()
    if ref:
        from kae.board.kicad_file import load
        rb = load(Path(ref))
        ids = {t.uuid for t in rb.tracks}
        for t in rb.tracks:
            refw[t.net] = max(refw.get(t.net, 0.0), t.width)
    by = {}
    for e in ents:
        e["own"] = e["uuid"] in ids if ref else None
        e["widened"] = bool(ref) and e["w"] > refw.get(e["net"], 0.0) + 1e-6
        k = (e["kind"], "widened" if e["widened"] else ("router" if e["own"] else "new"))
        x = by.setdefault(k, dict(n=0, mm2=0.0))
        x["n"] += 1
        x["mm2"] = round(x["mm2"] + e["mm2"], 3)
    summ = dict(total_mm2=round(sum(e["mm2"] for e in ents), 3), n=len(ents),
                by={f"{a}/{b}": v for (a, b), v in sorted(by.items())},
                top=sorted(ents, key=lambda e: -e["mm2"])[:8])
    print(json.dumps(summ, default=str))
    if out_json:
        Path(out_json).write_text(json.dumps(dict(summary=summ, entries=ents), indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
