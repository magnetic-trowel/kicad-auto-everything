# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference loop inductance of real board copper: every conductor meshed, no plane assumed.

The fast models make assumptions a routed board can break: the router's loop
(kae.route.critical_physics.Loop) runs a pour's current along one strip and takes the
nearest ground layer as a perfect image plane; the SPICE extraction (kae.sim.extract)
meshes pours but drops mutual inductance between pieces and also assumes an ideal plane.
This tool checks both against the copper itself: the nets' copper on every layer in a
window (tracks, pads, filled zones, the ground plane with its slots) is rasterized on a
square grid, each pair of neighbouring copper cells joined by a bar of one filament, vias
as barrels, and the network solved by pw_peec (nodal PEEC, full partial-inductance matrix,
inductive limit, free space: no plane is assumed anywhere).

    python pt_mesh_loop.py validate
    python pt_mesh_loop.py loop BOARD.kicad_pcb --nets +5V,Net-(D3-A),GND --port D3.2 D3.1 \
        --short IC1.1 IC1.2 --short C5.1 C5.2 --window 200 62 222 88 --pitch 0.5

The port's two pads are the source; --short pairs are zero-impedance links (a switch that
conducts, a capacitor's terminals). Parts' internal paths are not included: the result is the
copper's share, to compare with the fast models' copper-only values.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw_peec as pw  # noqa: E402

MM = 1e-3
T_CU = 0.035


class Mesh:
    """Copper cells on a grid per layer: node (net, layer, i, j); bars between 4-neighbours of one
    net. A layer's pitch may differ (fine where tracks are thin, coarser on a plane); vias join the
    nearest cells of the two layers."""

    def __init__(self, x0, y0, x1, y1, pitch, layer_pitch=None):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.pitch, self.layer_pitch = pitch, dict(layer_pitch or {})
        self.cells = {}                  # (net, layer) -> bool array [nx, ny] of the layer's grid
        self.z = {}

    def grid(self, layer):
        p = self.layer_pitch.get(layer, self.pitch)
        return p, int(math.ceil((self.x1 - self.x0) / p)), int(math.ceil((self.y1 - self.y0) / p))

    def xy(self, layer, i, j):
        p = self.grid(layer)[0]
        return self.x0 + (i + 0.5) * p, self.y0 + (j + 0.5) * p

    def add(self, net, layer, geom, z):
        """Mark the cells of geom (shapely) on layer as copper of net."""
        import shapely
        p, nx, ny = self.grid(layer)
        xs = self.x0 + (np.arange(nx) + 0.5) * p
        ys = self.y0 + (np.arange(ny) + 0.5) * p
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        inside = shapely.contains_xy(geom, X, Y)
        key = (net, layer)
        self.cells[key] = self.cells.get(key, np.zeros((nx, ny), bool)) | inside
        self.z[layer] = z

    def nearest(self, net, layer, x, y):
        c = self.cells.get((net, layer))
        if c is None or not c.any():
            return None
        p = self.grid(layer)[0]
        ii, jj = np.nonzero(c)
        px = self.x0 + (ii + 0.5) * p
        py = self.y0 + (jj + 0.5) * p
        k = int(np.argmin((px - x) ** 2 + (py - y) ** 2))
        return f"{net}|{layer}|{ii[k]}|{jj[k]}"

    def bars(self):
        """[(node a, node b, p0, axis, pitch m)] for every pair of neighbouring cells of one net."""
        out = []
        for (nm, layer), c in self.cells.items():
            p = self.grid(layer)[0] * MM
            z = self.z[layer] * MM - T_CU * MM / 2
            for i, j in zip(*np.nonzero(c[:-1, :] & c[1:, :])):
                x, y = self.xy(layer, i, j)
                out.append((f"{nm}|{layer}|{i}|{j}", f"{nm}|{layer}|{i + 1}|{j}", (x * MM, y * MM - p / 2, z), 0, p))
            for i, j in zip(*np.nonzero(c[:, :-1] & c[:, 1:])):
                x, y = self.xy(layer, i, j)
                out.append((f"{nm}|{layer}|{i}|{j}", f"{nm}|{layer}|{i}|{j + 1}", (x * MM - p / 2, y * MM, z), 1, p))
        return out


def assemble(m, bars, vias, ties, port):
    """pw.Net of the bars and vias in the port's connected component (copper not connected to the
    port, inside the window, carries no current and would leave the nodal matrix singular).
    vias: [(a, b, x, y, z_top, z_bot)] in metres; ties: [(a, b)]. Returns (net, dropped bars)."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)
    for a, b, *_ in bars:
        union(a, b)
    for a, b, *_ in vias:
        union(a, b)
    for a, b in ties:
        union(a, b)
    if find(port[0]) != find(port[1]):
        raise ValueError(f"open loop: no copper path between the port's ends {port} in the window (the window "
                         "cuts the return, or the pitch breaks a track)")
    root = find(port[0])
    net = pw.Net(plane_z=None)
    kept = 0
    for a, b, p0, axis, p in bars:
        if find(a) == root:
            net.bar(a, b, p0, axis, p, p, T_CU * MM)
            kept += 1
    for a, b, x, y, zt, zb in vias:
        if find(a) == root:
            net.via(a, b, x, y, zt, zb, r=0.15 * MM, n=6)
    for a, b in ties:
        net.tie(a, b)
    return net, len(bars) - kept


def port_L(net, a, b, f=1e8):
    """Inductance (nH) at the port a-b, inductive limit, no image plane."""
    Z, _ = net.solve(a, b, f=f, inductive=True, extra_ground=())
    return Z.imag / (2 * math.pi * f) * 1e9


# ----------------------------------------------------------------------------- validation
def validate(pitch=0.5):
    """A 10 mm x 1 mm strip 1.6 mm over a meshed 30 x 30 mm plane, a via down at each end:
    the meshed plane must give what pw_peec gives over a perfect image plane."""
    from shapely.geometry import box
    h, L, w = 1.6, 10.0, 1.0
    # reference: the same strip and vias over pw_peec's image plane
    ref = pw.Net(plane_z=0.0)
    ref.bar("A", "B", (0.0, -w / 2 * MM, h * MM - T_CU * MM / 2), 0, L * MM, w * MM, T_CU * MM, nw=8)
    ref.via("B", "PLANE", L * MM, 0.0, h * MM, 0.0)
    ref.via("A", "P0", 0.0, 0.0, h * MM, 0.0)
    l_ref = ref.L_port("P0", "PLANE", f=1e8) * 1e9
    # meshed: strip on top, plane below, vias between
    m = Mesh(-10, -15, 20, 15, pitch)
    m.add("S", "top", box(0, -w / 2, L, w / 2), h)
    m.add("G", "bot", box(-10, -15, 20, 15), 0.0)
    a = m.nearest("S", "top", 0, 0)
    b = m.nearest("S", "top", L, 0)
    ga = m.nearest("G", "bot", 0, 0)
    gb = m.nearest("G", "bot", L, 0)
    vias = [(b, gb, L * MM, 0.0, h * MM, 0.0), (a, "PORT", 0.0, 0.0, h * MM, 0.0)]
    net, _ = assemble(m, m.bars(), vias, [], ("PORT", ga))
    l_mesh = port_L(net, "PORT", ga)
    print(f"strip over plane: image {l_ref:.3f} nH, meshed plane at {pitch} mm {l_mesh:.3f} nH "
          f"({100 * (l_mesh / l_ref - 1):+.1f}%), {len(net.f)} filaments")
    return l_ref, l_mesh


# ----------------------------------------------------------------------------- a board loop
def board_loop(path, nets, port, shorts, window, pitch, layers=None, layer_pitch=None, solid=None):
    sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))
    from shapely.geometry import Point, box
    from shapely.ops import unary_union

    from kae.board import transform
    from kae.board.kicad_file import load
    from kae.place.legalize import pad_shape
    from kae.route.critical_recheck import fills_of
    b = load(path)
    fills = fills_of(path)
    cu = list(b.stackup.copper)
    thick = b.stackup.thickness if getattr(b.stackup, "thickness", None) else 1.6
    zl = {l: thick * (1 - k / max(1, len(cu) - 1)) for k, l in enumerate(cu)}   # F.Cu on top, B.Cu at 0
    layers = layers or cu
    win = box(*window)
    m = Mesh(*window, pitch, layer_pitch)
    fp = {f.ref: f for f in b.footprints}
    for net in nets:
        for layer in layers:
            g = []
            g += [x for x in (fills.get(net) or {}).get(layer, [])]
            g += [__import__("shapely.geometry", fromlist=["LineString"]).LineString([t.start, t.end]).buffer(t.width / 2)
                  for t in b.tracks if t.net == net and t.layer == layer]
            for f in b.footprints:
                for p in f.pads:
                    if p.net == net and layer in p.layers:
                        g.append(transform.place_geom(pad_shape(p, layer), f.x, f.y, f.rot, f.side))
            for v in b.vias:
                if v.net == net:
                    xy = getattr(v, "at", None) or (v.x, v.y)
                    g.append(Point(xy).buffer(getattr(v, "size", 0.6) / 2))
            if solid and (net, layer) == solid:
                g = [win]                     # what-if: this net's copper on this layer as a solid plane
            g = unary_union(g).intersection(win) if g else None
            if g is not None and not g.is_empty:
                m.add(net, layer, g, zl[layer])
    vias = []
    for v in b.vias:
        if v.net not in nets:
            continue
        xy = getattr(v, "at", None) or (v.x, v.y)
        if not win.contains(Point(xy)):
            continue
        vl = [l for l in layers if (v.net, l) in m.cells]
        for la, lb in zip(vl[:-1], vl[1:]):
            a, c = m.nearest(v.net, la, *xy), m.nearest(v.net, lb, *xy)
            if a and c:
                vias.append((a, c, xy[0] * MM, xy[1] * MM, zl[la] * MM, zl[lb] * MM))

    def pad_node(token):
        ref, num = token.rsplit(".", 1)
        f = fp[ref]
        p = next(q for q in f.pads if q.number == num)
        x, y = transform.pad_xy(f, p)
        layer = next(l for l in layers if l in p.layers)
        return m.nearest(p.net, layer, x, y)
    ties = [(pad_node(a), pad_node(c)) for a, c in shorts]
    pp, pn = pad_node(port[0]), pad_node(port[1])
    bars = m.bars()
    net, dropped = assemble(m, bars, vias, ties, (pp, pn))
    t0 = time.time()
    L = port_L(net, pp, pn)
    return L, dict(bars=len(bars) - dropped, dropped_bars=dropped, vias=len(vias), filaments=len(net.f),
                   seconds=round(time.time() - t0, 1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--pitch", type=float, default=0.5)
    lp = sub.add_parser("loop")
    lp.add_argument("board")
    lp.add_argument("--nets", required=True)
    lp.add_argument("--port", nargs=2, required=True)
    lp.add_argument("--short", nargs=2, action="append", default=[])
    lp.add_argument("--window", nargs=4, type=float, required=True)
    lp.add_argument("--pitch", type=float, default=0.5)
    lp.add_argument("--layer-pitch", nargs=2, action="append", default=[], metavar=("LAYER", "MM"))
    lp.add_argument("--solid", nargs=2, metavar=("NET", "LAYER"), help="what-if: fill NET solid on LAYER in the window")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        validate(a.pitch)
    else:
        L, info = board_loop(a.board, a.nets.split(","), a.port, a.short, a.window, a.pitch,
                             layer_pitch={k: float(v) for k, v in a.layer_pitch}, solid=tuple(a.solid) if a.solid else None)
        print(f"loop {L:.3f} nH (copper only) {info}")


if __name__ == "__main__":
    main()
