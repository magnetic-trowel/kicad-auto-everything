# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigid array macros: LED matrices and series-resistor buses found in the netlist (J47).

A matrix of identical parts is a product of two net groups: every row net meets every column
net in exactly one part (gecko5education's 120 RGB LEDs, 12 x 10, about 165 of its 247 open
connections when the placer scatters them). The annealer's single-part moves have no incentive to keep
that lattice, so the row and column nets end up crossing everywhere. A rigid macro keeps it, and lets the
annealer move the array as one body.

Detection reads only the netlist and the footprints (never the human placement):

- `matrices`: footprints of one lib_id (at least MIN_MATRIX, movable). For a pair of pad numbers
  (a, b), part i has row net a(i) and column net b(i); the pair is a matrix when the (row, column)
  pairs are all different, both nets are signal nets, at least 2 rows and 2 columns exist and they
  fill at least MIN_FILL of rows x columns. Rows and columns are ordered by the lowest reference number on
  them, which designers usually number in matrix order; a rotation of the whole macro is the floorplan's.
- `buses`: at least MIN_BUS identical two-pin SMD parts (R, FB, ...) each joining the same two parts A
  and B by nets that touch no third part (series resistors between an FPGA and a memory): a straight
  line, ordered by the pad numbers at A, so a block fits between its ends.

`macros` turns each group into a kae.place.clusters.Macro with three layouts by the gap between cells
(GAPS_MM: routing room against compactness). `pin` then gives each macro a legal spot near the seed's
position and the parts are held there as fixed parts for the rest of the placement (pipeline's array pre-step,
like the edge connectors), so nothing downstream, annealer or legalizers, can break the lattice.
Radial arrays (LED rings) and daisy chains are not detected: the netlist of a chain cannot say what
shape the designer wants. array_macros (setting, off by default) enables it until array-macro-ab decides.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

MIN_MATRIX = 16              # parts in a matrix: below it the tag's own threshold
MIN_FILL = 0.8               # share of rows x columns that must hold a part
MIN_BUS = 6                  # parts in a series-resistor bus
GAPS_MM = (0.5, 0.25, 1.0)   # the gaps between cells, first layout first
PASSIVE_REF = re.compile(r"^(R|FB|L|C)\d", re.I)


@dataclass
class ArrayGroup:
    kind: str           # "matrix" | "bus"
    cells: dict         # part id -> (row, col)
    rows: int
    cols: int
    pads: tuple = ()


def _num(s):
    m = re.search(r"\d+", str(s))
    return (int(m.group()) if m else 1 << 30, str(s))


def _is_power(net, kinds):
    return kinds.get(net) in ("ground", "power")


def _pad_net(fp):
    """{pad number: net} of a footprint's pads with a net; a number with several nets: none."""
    out = {}
    for p in fp.pads:
        if not p.net:
            continue
        if p.number in out and out[p.number] != p.net:
            out[p.number] = ""
        else:
            out[p.number] = p.net
    return {k: v for k, v in out.items() if v}


def matrices(fps, kinds, exclude=()):
    """[ArrayGroup kind matrix] over footprints `fps` (objects with uuid, ref, lib_id, pads)."""
    by_lib = defaultdict(list)
    for f in fps:
        if f.pads and f.uuid not in exclude:
            by_lib[f.lib_id].append(f)
    out, used = [], set(exclude)
    for lib, parts in sorted(by_lib.items(), key=lambda t: -len(t[1])):
        parts = [f for f in parts if f.uuid not in used]
        if len(parts) < MIN_MATRIX:
            continue
        pn = {f.uuid: _pad_net(f) for f in parts}
        numbers = sorted({k for d in pn.values() for k in d})
        best = None
        for a in numbers:
            for b in numbers:
                if a >= b:
                    continue
                rows, cols = {}, {}
                cells, ok, pairs = {}, True, set()
                for f in parts:
                    d = pn[f.uuid]
                    if a not in d or b not in d or _is_power(d[a], kinds) or _is_power(d[b], kinds):
                        ok = False
                        break
                    pair = (d[a], d[b])
                    if pair in pairs:
                        ok = False
                        break
                    pairs.add(pair)
                    rows.setdefault(d[a], []).append(f.ref)
                    cols.setdefault(d[b], []).append(f.ref)
                    cells[f.uuid] = pair
                if not ok or len(rows) < 2 or len(cols) < 2:
                    continue
                fill = len(parts) / (len(rows) * len(cols))
                if fill >= MIN_FILL and (best is None or (fill, -abs(len(rows) - len(cols))) > best[0]):
                    best = ((fill, -abs(len(rows) - len(cols))), rows, cols, cells, (a, b))
        if best is None:
            continue
        _, rows, cols, cells, pads = best
        order = lambda d: {n: i for i, n in enumerate(sorted(d, key=lambda n: min(_num(r) for r in d[n])))}
        rr, cc = order(rows), order(cols)
        grid = {u: (rr[r], cc[c]) for u, (r, c) in cells.items()}
        out.append(ArrayGroup("matrix", grid, len(rr), len(cc), pads))
        used |= set(grid)
    return out


def buses(fps, kinds, exclude=()):
    """[ArrayGroup kind bus (rows 1)]: series two-pin parts of one lib_id between the same two parts."""
    pins = defaultdict(list)
    for f in fps:
        for p in f.pads:
            if p.net:
                pins[p.net].append((f, p))
    groups = defaultdict(list)
    for f in fps:
        if f.uuid in exclude or not PASSIVE_REF.match(f.ref) or len(f.pads) != 2 or any(p.drill for p in f.pads):
            continue
        n1, n2 = f.pads[0].net, f.pads[1].net
        if not n1 or not n2 or n1 == n2 or _is_power(n1, kinds) or _is_power(n2, kinds):
            continue
        o1 = [(g, p) for g, p in pins[n1] if g.uuid != f.uuid]
        o2 = [(g, p) for g, p in pins[n2] if g.uuid != f.uuid]
        if len(o1) != 1 or len(o2) != 1:
            continue
        (g1, p1), (g2, p2) = o1[0], o2[0]
        if g1.uuid == g2.uuid:
            continue
        a, b = (g1, p1), (g2, p2)
        if a[0].uuid > b[0].uuid:
            a, b = b, a
        groups[(f.lib_id, a[0].uuid, b[0].uuid)].append((f, a[1].number))
    out = []
    for key, members in sorted(groups.items(), key=lambda t: -len(t[1])):
        if len(members) < MIN_BUS:
            continue
        members.sort(key=lambda t: _num(t[1]))
        out.append(ArrayGroup("bus", {f.uuid: (0, c) for c, (f, _) in enumerate(members)}, 1, len(members)))
    return out


def macros(P, used=(), log=None):
    """(Macros for P's arrays, report). `used`: part indices already in other macros."""
    from .clusters import Macro, _layout
    from .problem import net_class_guess
    fps = [p.fp for p in P.parts if p.movable]
    kinds = {n.name: n.kind for n in P.nets}
    for n in {pd.net for p in P.parts for pd in p.fp.pads if pd.net}:
        kinds.setdefault(n, net_class_guess(n, 2, max(1, len(P.parts))))
    uuid_of = {p.fp.uuid: p.i for p in P.parts}
    index_used = {P.parts[i].fp.uuid for i in used}
    mats = matrices(fps, kinds, exclude=index_used)
    taken = index_used | {u for g in mats for u in g.cells}
    bs = buses(fps, kinds, exclude=taken)
    out = []
    rep = dict(matrices=[], buses=[])
    g = P.g
    for grp in mats + bs:
        members = [uuid_of[u] for u in grp.cells]
        cells = {uuid_of[u]: rc for u, rc in grp.cells.items()}
        i0 = members[0]
        a, b, c, d = P.parts[i0].rots[0].g_own
        w, h = b - a, d - c
        r0 = (grp.rows - 1) // 2
        c0 = (grp.cols - 1) // 2
        anchor = min(members, key=lambda i: (abs(cells[i][0] - r0) + abs(cells[i][1] - c0), i))
        ra, ca = cells[anchor]
        layouts, seen = [], set()
        for gap in GAPS_MM:
            px, py = w + int(round(gap / g)), h + int(round(gap / g))
            if (px, py) in seen:
                continue
            seen.add((px, py))
            off = {i: ((cells[i][1] - ca) * px, (cells[i][0] - ra) * py, 0) for i in members}
            layouts.append(_layout(P, off, 0.0))
        out.append(Macro(members=members, anchor=anchor, layouts=layouts, structs=[]))
        rep["matrices" if grp.kind == "matrix" else "buses"].append(
            dict(ref=P.parts[anchor].ref, parts=len(members), rows=grp.rows, cols=grp.cols, lib=P.parts[anchor].fp.lib_id))
    if log and out:
        log(f"array macros: {len(rep['matrices'])} matrices, {len(rep['buses'])} buses "
            f"({sum(len(m.members) for m in out)} parts)")
    return out, rep


def _bbox(P, lay, q):
    """Grid bounding box (x0, x1, y0, y1) of a layout turned q quarter turns, about the anchor."""
    xs0, xs1, ys0, ys1 = [], [], [], []
    for i, (dx, dy, k) in lay.offsets.items():
        for _ in range(q):
            dx, dy = dy, -dx
        k2 = P.parts[i].turn[k][q]
        a, b, c, d = P.parts[i].rots[k2].g_own
        xs0.append(dx + a); xs1.append(dx + b); ys0.append(dy + c); ys1.append(dy + d)
    return min(xs0), max(xs1), min(ys0), max(ys1)


def _spot(P, mac, x0, y0, taken, step, max_tries=64):
    """(X, Y, layout, q) of the anchor: the legal spot nearest (x0, y0) (mm): every member's box inside
    the outline, the array's bounding box clear of fixed obstacles and of `taken` (side, grid box)."""
    import numpy as np
    first = P.parts[mac.anchor]
    side = 0 if first.s > 0 else 1
    tht = first.tht
    Xc, Yc = (x0 - P.ox) / P.g, (y0 - P.oy) / P.g
    best = None
    for lay in mac.layouts:
        for q in range(4):
            x_a, x_b, y_a, y_b = _bbox(P, lay, q)
            Xs = np.arange(-x_a, P.ncx - x_b + 1, step)
            Ys = np.arange(-y_a, P.ncy - y_b + 1, step)
            if not len(Xs) or not len(Ys):
                continue
            ok = np.ones((len(Xs), len(Ys)), bool)
            blocks = [ob.g for ob in P.obstacles if ob.side == side or tht] + [b for sd, b in taken if sd == side or tht]
            for (t0, t1, u0, u1) in blocks:
                ok &= ~((Xs + x_a) < t1)[:, None] | ~(t0 < (Xs + x_b))[:, None] | ~((Ys + y_a) < u1)[None, :] | ~(u0 < (Ys + y_b))[None, :]
            dist = np.hypot((Xs - Xc)[:, None], (Ys - Yc)[None, :])
            key = np.where(ok, dist, np.inf)
            for _ in range(max_tries):
                f = int(np.argmin(key))
                if not np.isfinite(key.flat[f]):
                    break
                xi, yi = np.unravel_index(f, key.shape)
                X, Y = int(Xs[xi]), int(Ys[yi])
                if all(P.outside_cells_all(*_at(P, i, lay, q, X, Y)) == 0 for i in lay.offsets):
                    if best is None or key[xi, yi] < best[0]:
                        best = (float(key[xi, yi]), X, Y, lay, q)
                    break
                key[xi, yi] = np.inf
    return best


def _at(P, i, lay, q, X, Y):
    dx, dy, k = lay.offsets[i]
    for _ in range(q):
        dx, dy = dy, -dx
    k2 = P.parts[i].turn[k][q]
    r = P.parts[i].rots[k2]
    return X + dx, Y + dy, r.g_boards or (r.g_board,)


def pin(P, macs, st, step_mm=1.0):
    """{uuid: (x, y, rot, side)} of every member of the macros that fit, largest macro first, and the refs
    of macros with no legal spot. Positions come from the seed `st` (the anchor's position there)."""
    g = P.g
    step = max(1, int(round(step_mm / g)))
    poses, failed, taken = {}, [], []
    for mac in sorted(macs, key=lambda m: -len(m.members)):
        ax, ay = st.xy(mac.anchor)
        spot = _spot(P, mac, float(ax), float(ay), taken, step)
        if spot is None:
            failed.append(P.parts[mac.anchor].ref)
            continue
        _, X, Y, lay, q = spot
        x_a, x_b, y_a, y_b = _bbox(P, lay, q)
        taken.append((0 if P.parts[mac.anchor].s > 0 else 1, (X + x_a, X + x_b, Y + y_a, Y + y_b)))
        for i in lay.offsets:
            dx, dy, k = lay.offsets[i]
            for _ in range(q):
                dx, dy = dy, -dx
            k2 = P.parts[i].turn[k][q]
            p = P.parts[i]
            poses[p.uuid] = (round(P.ox + (X + dx) * g, 6), round(P.oy + (Y + dy) * g, 6), float(p.rots[k2].rot), p.side)
    return poses, failed
