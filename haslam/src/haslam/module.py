# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout modules: a reference layout (part poses, copper, vias) held around one anchor part.

    python -m haslam.module apply IN.kicad_pcb OUT.kicad_pcb MODULE.json --anchor REF [--at X,Y,ROT] [--report R.json]

A module file (schema "haslam.module/1", JSON) is drawn in the anchor footprint's library frame:

- anchor: {"pins": {pad number: role}}: roles name the anchor's nets; a role's board net is the net of that pad.
- slots: [{"pads": [{"net": role, "x": mm, "y": mm}, ...]}]: one part each. The board part filling a slot has exactly
  those roles' nets on its pads; its pose is fitted so each of its pads lands on its role's point (rotation searched in
  1 degree steps, position by least squares), and the best fit within fit_tol wins.
- copper: [{"layer": "F.Cu", "net": role, "outline": [[x, y], ...]}]: written as zones (solid pad connection,
  priority `priority`), filled by KiCad like any zone.
- vias: [{"x", "y", "net": role, "size", "drill"}], written locked.
- applies: what the reference layout assumed (layers, copper weight, plane under it); recorded, not enforced.

`apply` moves the matched parts (haslam.board.pcbnew_io.write_poses), then locks them and the anchor and adds the
copper and vias in one pcbnew pass. A locked part is a fixed obstacle for the placer (haslam.place.problem), locked
vias are fixed wiring for the bridge, and zones are connection targets for the routers, so the rest of the flow places
and routes around the module unchanged. Opt-in: nothing in haslam reads a module unless asked.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .board import transform as T

SCHEMA = "haslam.module/1"


def load(path):
    m = json.loads(Path(path).read_text())
    if m.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {m.get('schema')!r}, expected {SCHEMA!r}")
    for k in ("anchor", "slots"):
        if k not in m:
            raise ValueError(f"{path}: no {k!r}")
    return m


def _fit(fp, targets):
    """Pose (x, y, rot) of footprint `fp` putting each pad on targets[pad number] (board mm); (pose, rms mm)."""
    pads = [p for p in fp.pads if p.number in targets]
    if not pads:
        return None, math.inf
    best = (None, math.inf)
    tx = sum(targets[p.number][0] for p in pads) / len(pads)
    ty = sum(targets[p.number][1] for p in pads) / len(pads)
    for deg in range(360):
        # with the footprint at (0, 0, deg) its pads sit at to_board(local); shift so the centroids meet
        pts = [T.to_board(p.lx, p.ly, 0.0, 0.0, float(deg), fp.side) for p in pads]
        cx = sum(u for u, _ in pts) / len(pts)
        cy = sum(v for _, v in pts) / len(pts)
        x, y = tx - cx, ty - cy
        err = math.sqrt(sum((u + x - targets[p.number][0]) ** 2 + (v + y - targets[p.number][1]) ** 2
                            for (u, v), p in zip(pts, pads)) / len(pads))
        if err < best[1] - 1e-9:
            best = ((x, y, float(deg)), err)
    return best


def plan(board, module, anchor, at=None, fit_tol=0.4, via_clearance=0.2):
    """{moves: {uuid: (x, y, rot, side)}, refs, zones, vias, slots, unmatched} for `module` held at `anchor` (a ref).
    at: (x, y, rot) of the anchor; default its pose on `board`. A part fills a slot only when its pads fit the slot's points
    within fit_tol mm rms (another package has another pad pitch: a 1206 in an 0603 slot fits at 0.78 mm and would sit
    on its neighbours); the best fit wins."""
    fps = {f.ref: f for f in board.footprints}
    if anchor not in fps:
        raise ValueError(f"anchor {anchor} not on the board")
    a = fps[anchor]
    ax, ay, arot = (a.x, a.y, a.rot) if at is None else at
    side = a.side
    role_net = {}
    for p in a.pads:
        r = module["anchor"]["pins"].get(p.number)
        if r and p.net:
            role_net.setdefault(r, p.net)

    def B(x, y):
        return T.to_board(x, y, ax, ay, arot, side)
    moves = {a.uuid: (ax, ay, arot, side)}
    refs = [anchor]
    used = {anchor}
    out_slots, unmatched = [], []
    for i, s in enumerate(module["slots"]):
        nets = [role_net.get(p["net"]) for p in s["pads"]]
        if None in nets:
            unmatched.append(dict(slot=i, why="a role has no net on the anchor"))
            continue
        want = sorted(nets)
        best = None
        for f in board.footprints:
            if f.ref in used:
                continue
            if sorted(p.net for p in f.pads if p.net) != want or len(f.pads) != len(s["pads"]):
                continue
            # each slot pad -> the part's pad on that net (two pads on one net: in order)
            targets, taken = {}, set()
            for sp in s["pads"]:
                n = role_net[sp["net"]]
                for p in f.pads:
                    if p.net == n and p.number not in taken:
                        targets[p.number] = B(sp["x"], sp["y"])
                        taken.add(p.number)
                        break
            pose, err = _fit(f, targets)
            if err <= fit_tol and (best is None or err < best[0]):
                best = (err, f, pose)
        if best is None:
            unmatched.append(dict(slot=i, nets=want, why=f"no part with these nets whose pads fit within {fit_tol} mm"))
            continue
        err, f, pose = best
        ref = f.ref
        moves[f.uuid] = (*pose, f.side)
        used.add(ref)
        refs.append(ref)
        out_slots.append(dict(slot=i, ref=ref, rms_mm=round(err, 3)))
    zones = []
    flip = (lambda l: {"F.Cu": "B.Cu", "B.Cu": "F.Cu"}.get(l, l)) if T.side_sign(side) < 0 else (lambda l: l)
    for c in module.get("copper") or []:
        n = role_net.get(c["net"])
        if n is None:
            continue
        zones.append(dict(net=n, layer=flip(c["layer"]), outline=[B(x, y) for x, y in c["outline"]]))
    # the held parts' pads at their new poses: a module via on (or within via_clearance of) a pad of another net is
    # dropped (the reference layout's pads may be smaller than the board's footprints')
    from shapely.geometry import Point, Polygon
    held_pads = []
    for f in board.footprints:
        if f.uuid not in moves:
            continue
        x0, y0, r0, s0 = moves[f.uuid]
        for p in f.pads:
            w, h = p.size
            c = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            pts = []
            for u, v in c:
                u, v = T.rotate(u, v, p.lrot or 0.0)
                pts.append(T.to_board(p.lx + u, p.ly + v, x0, y0, r0, s0))
            held_pads.append((p.net, Polygon(pts)))
    vias, dropped = [], 0
    for v in module.get("vias") or []:
        n = role_net.get(v["net"])
        if n is None:
            continue
        x, y = B(v["x"], v["y"])
        disk = Point(x, y).buffer(v.get("size", 0.6) / 2 + via_clearance)
        if any(net != n and poly.intersects(disk) for net, poly in held_pads):
            dropped += 1
            continue
        vias.append(dict(net=n, x=x, y=y, size=v.get("size", 0.6), drill=v.get("drill", 0.3)))
    return dict(moves=moves, refs=refs, zones=zones, vias=vias, vias_dropped=dropped, slots=out_slots,
                unmatched=unmatched)


_PCBNEW = r'''
import json, sys, pcbnew
src, spec, dst = sys.argv[1:4]
s = json.load(open(spec))
io = pcbnew.PCB_IO_MGR
b = io.Load(io.KICAD_SEXP, src)
mm = pcbnew.FromMM
for f in b.GetFootprints():
    if f.GetReference() in set(s["refs"]):
        f.SetLocked(True)
lay = {b.GetLayerName(i): i for i in range(pcbnew.PCB_LAYER_ID_COUNT)}
for z in s["zones"]:
    zone = pcbnew.ZONE(b)
    zone.SetLayer(lay[z["layer"]])
    zone.SetNetCode(b.FindNet(z["net"]).GetNetCode())
    zone.SetAssignedPriority(int(s.get("priority", 10)))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetIsRuleArea(False)
    ol = zone.Outline()
    ol.NewOutline()
    for x, y in z["outline"]:
        ol.Append(mm(x), mm(y))
    zone.SetZoneName("module")
    b.Add(zone)
for v in s["vias"]:
    via = pcbnew.PCB_VIA(b)
    via.SetPosition(pcbnew.VECTOR2I(mm(v["x"]), mm(v["y"])))
    via.SetWidth(mm(v["size"]))
    via.SetDrill(mm(v["drill"]))
    via.SetNetCode(b.FindNet(v["net"]).GetNetCode())
    via.SetLocked(True)
    b.Add(via)
io.Save(io.KICAD_SEXP, dst, b)
print(json.dumps({"locked": len(s["refs"]), "zones": len(s["zones"]), "vias": len(s["vias"])}))
'''


def apply(src, dst, module_path, anchor, at=None, priority=10, report=None):
    from .board import pcbnew_io
    from .board.kicad_file import load as load_board
    m = load(module_path)
    p = plan(load_board(Path(src)), m, anchor, at=at)
    with tempfile.TemporaryDirectory(prefix="haslam-module-") as d:
        moved = Path(d) / "moved.kicad_pcb"
        pcbnew_io.write_poses(src, moved, {u: dict(x=x, y=y, rot=r, side=sd) for u, (x, y, r, sd) in p["moves"].items()})
        spec = Path(d) / "spec.json"
        spec.write_text(json.dumps(dict(refs=p["refs"], zones=p["zones"], vias=p["vias"], priority=priority)))
        script = Path(d) / "module_apply.py"
        script.write_text(_PCBNEW)
        r = subprocess.run([*pcbnew_io.kicad_python(), str(script), str(moved), str(spec), str(Path(dst).resolve())],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"module apply failed: {r.stderr[-2000:]}")
    rep = dict(module=m.get("name"), anchor=anchor, at=at, slots=p["slots"], unmatched=p["unmatched"],
               zones=len(p["zones"]), vias=len(p["vias"]), vias_dropped=p["vias_dropped"], locked=p["refs"], applies=m.get("applies"))
    if report:
        Path(report).write_text(json.dumps(rep, indent=1))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m haslam.module", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="hold a module around an anchor part")
    a.add_argument("input")
    a.add_argument("output")
    a.add_argument("module")
    a.add_argument("--anchor", required=True)
    a.add_argument("--at", help="X,Y,ROT of the anchor (default: its pose on the input)")
    a.add_argument("--priority", type=int, default=10, help="zone priority of the module's copper")
    a.add_argument("--report")
    a = ap.parse_args(argv)
    at = tuple(float(v) for v in a.at.split(",")) if a.at else None
    rep = apply(a.input, a.output, a.module, a.anchor, at=at, priority=a.priority, report=a.report)
    print(json.dumps({k: rep[k] for k in ("slots", "unmatched", "zones", "vias")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
