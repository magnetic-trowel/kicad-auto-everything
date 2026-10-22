#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only audit: footprints that carry Edge.Cuts in kaebench place tasks.

A footprint's Edge.Cuts graphics (card edges, slots, cut-outs) are part of the board
outline. kaebench's place task stages every unlocked footprint off-board, so such a
footprint takes its piece of the outline with it. For each task this reports:

  (a) unlocked footprints carrying Edge.Cuts that are staged off-board;
  (b) whether the place input's outline differs from the reference's, by closure or area;
  (c) whether the place input's outline is open.

"Outline as KiCad sees it" = board-level Edge.Cuts plus every footprint's (staged ones
included), as pcbnew's GetBoardPolygonOutlines builds it; "loader outline" = Board.outline
(board-level plus on-board footprints). Polygons come from kae.board.geom (KiCad's
chaining and nesting; verified against pcbnew on the corpus).

    edgecuts_place_audit.py [--tasks kae-work-v2/tasks] [--json OUT]
"""
import argparse
import json
import sys
from pathlib import Path

from shapely.ops import unary_union

from kae.board import geom, kicad_file, sexpr

ROOT = Path(__file__).resolve().parents[2]
AREA_TOL = 1e-3  # mm^2


def kicad_outline(path, board):
    """Outline from board-level Edge.Cuts plus all footprints' (pcbnew's view)."""
    tree = sexpr.parse(sexpr.strip_blocks(Path(path).read_text(encoding="utf-8", errors="replace")))
    opens, rings = kicad_file._outline_pieces(tree, geom.ARC_TOL, [])
    fp_edges = [pl for fp in board.footprints if fp.edge_cuts for pl in kicad_file._place_edges(fp)]
    if not (opens or rings or fp_edges):
        return [], dict(open_ends=0)
    return geom.polygons(opens + fp_edges, rings, eps=kicad_file.CHAIN_EPS)


def describe(polys, info):
    area = sum(p.area for p in polys)
    return dict(polygons=len(polys), holes=sum(len(p.interiors) for p in polys), area=round(area, 4),
                open_chains=info.get("open_ends", 0), closed=bool(polys) and not info.get("open_ends", 0))


def differs(a_polys, a, b_polys, b):
    if a["closed"] != b["closed"] or a["polygons"] != b["polygons"] or a["holes"] != b["holes"]:
        return True
    if abs(a["area"] - b["area"]) > AREA_TOL:
        return True
    if a_polys and b_polys:
        return unary_union(a_polys).symmetric_difference(unary_union(b_polys)).area > AREA_TOL
    return False


def audit(task_dir):
    ref_p = task_dir / "reference" / "board.kicad_pcb"
    pl_p = task_dir / "place" / "input" / "board.kicad_pcb"
    ref, pl = kicad_file.load(ref_p, rules=False), kicad_file.load(pl_p, rules=False)
    edge_fps = [f for f in pl.footprints if f.edge_cuts]
    staged = [f for f in edge_fps if not f.locked and not f.on_board]
    rk, rk_info = kicad_outline(ref_p, ref)
    pk, pk_info = kicad_outline(pl_p, pl)
    ref_d, pl_d = describe(rk, rk_info), describe(pk, pk_info)
    loader_d = describe(pl.outline, dict(open_ends=sum(1 for w in pl.warnings if "do not close" in w)))
    return dict(
        id=task_dir.name,
        edge_footprints=[dict(ref=f.ref, locked=f.locked, on_board=f.on_board, pieces=len(f.edge_cuts))
                         for f in edge_fps],
        staged_edge_footprints=[f.ref for f in staged],
        reference_outline=ref_d, place_outline_kicad=pl_d, place_outline_loader=loader_d,
        differs_kicad=differs(rk, ref_d, pk, pl_d),
        differs_loader=differs(rk, ref_d, pl.outline, loader_d),
        open_kicad=not pl_d["closed"], open_loader=not loader_d["closed"],
        reference_open=not ref_d["closed"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", default=str(ROOT / "kae-work-v2" / "tasks"))
    ap.add_argument("--json", default=str(ROOT / "kae-work" / "kae-board" / "acceptance" / "edgecuts_place_audit.json"))
    a = ap.parse_args(argv)
    rows = [audit(d) for d in sorted(Path(a.tasks).iterdir()) if (d / "place" / "input" / "board.kicad_pcb").exists()]
    summary = dict(
        boards=len(rows),
        boards_with_edge_footprints=[r["id"] for r in rows if r["edge_footprints"]],
        a_staged_edge_footprints={r["id"]: r["staged_edge_footprints"] for r in rows if r["staged_edge_footprints"]},
        b_outline_differs_kicad=[r["id"] for r in rows if r["differs_kicad"]],
        b_outline_differs_loader=[r["id"] for r in rows if r["differs_loader"]],
        c_open_kicad=[r["id"] for r in rows if r["open_kicad"]],
        c_open_loader=[r["id"] for r in rows if r["open_loader"]],
        reference_open=[r["id"] for r in rows if r["reference_open"]],
    )
    for k in list(summary):
        if isinstance(summary[k], (list, dict)):
            summary[f"n_{k}"] = len(summary[k])
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(dict(summary=summary, boards=rows), indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
