# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manufacturability columns of one board (report-only; no score effect, not targets).

Run in a venv with the kae package and KiCad reachable through $KAE_KICAD_WRAP (kaeres mfg-job does):

  python mfg_board.py --board BOARD.kicad_pcb --out OUT.json [--human HUMAN.kicad_pcb] [--refill]

--board: a board file in a folder with its .kicad_pro / .kicad_dru, gzip allowed.
--human: the human layout of the same board (phantom_share needs it).
--refill: refill zones with pcbnew first, in a temporary copy (router outputs store no fills). Without it, a board
          whose zones have no stored fill reports the pour-dependent columns as null.

Columns (definitions, threshold sources and limits are in tools/kaeres/README.md, "Manufacturability columns"):
ca_short_per_m_pours, width_at_class_min, copper_pair_diff_pp, copper_flag, vip_small_signal, fab_class_jlcpcb,
phantom_share, exp_breakout_40um, acute_per_m. Ported from the Stage-1 geometry pass (2026-11) with these differences:
board and fills are read here with kae's loader, net class minima with kae's rules, custom pads use their real outline,
and nets are compared by name (Stage 1's extract mapped numeric net names apart from pads, inflating critical area on such boards).
"""
import argparse
import gzip
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import shapely
from shapely import STRtree

X0 = 0.025               # defect-size floor, mm: critical area integrates (x0/s)^2 per unit length (tm_mfg_physics section J)
GAP_MAX = 2.0            # edge gap considered for critical area, mm
SAMPLE = 0.25            # track sample pitch, mm
SHORT_CLAMP = 0.02       # gap floor in the critical-area sum, mm
PLATING = 0.025          # via barrel plating thickness, mm
SIGMA_BREAKOUT = 0.040   # drill position sigma, mm (hv-and-manufacturing-physics)
COPPER_FLAG_PP = 20.0    # copper imbalance flag, percentage points between mirror layers (DFM-27, read as points; source ambiguous)
PAD_SMALL_MM2 = 2.0      # vip_small_signal: small pad, mm^2
PWR_RE = re.compile(r"gnd|vcc|vdd|vss|vbus|vbat|vin|vout|vsys|vcore|^\+|^-|^v\d|pwr|3v3|1v8|5v", re.I)


def Q(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def rd(x, n=4):
    if x is None:
        return None
    x = float(x)
    return round(x, n) if math.isfinite(x) else None


def arc_pts(p0, pm, p1, step_deg=15.0):
    """Points along the circular arc through p0, pm, p1, ends included."""
    (ax, ay), (bx, by), (cx, cy) = p0, pm, p1
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [p0, p1]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0, am, a1 = (math.atan2(y - uy, x - ux) for x, y in (p0, pm, p1))
    norm = lambda a: a % (2 * math.pi)
    sweep = norm(a1 - a0) if norm(am - a0) < norm(a1 - a0) else -norm(a0 - a1)
    n = max(2, int(abs(math.degrees(sweep)) / step_deg) + 1)
    return [(ux + r * math.cos(a0 + sweep * i / n), uy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def read_fills(text):
    """Filled zone polygons of a .kicad_pcb text: [(layer, net name, [(x, y), ...])]. kae's loader skips them."""
    nets = {m.group(1): m.group(2) for m in re.finditer(r'^\s*\(net\s+(-?\d+)\s+"((?:[^"\\]|\\.)*)"\s*\)', text, re.M)}
    out = []
    for z in re.finditer(r'^\s*\(zone\b', text, re.M):
        end = _block_end(text, z.start())
        blk = text[z.start():end]
        cut = blk.find("(filled_polygon")
        if cut < 0:
            continue
        head = blk[:cut]
        if "(keepout" in head:
            continue
        name = ""
        m = re.search(r'\(net_name\s+"((?:[^"\\]|\\.)*)"\)', head)
        m2 = re.search(r'\(net\s+"((?:[^"\\]|\\.)*)"\)', head)
        m3 = re.search(r'\(net\s+(-?\d+)\s*\)', head)
        if m:
            name = m.group(1)
        elif m2:
            name = m2.group(1)
        elif m3:
            name = nets.get(m3.group(1), "")
        for f in re.finditer(r'\(filled_polygon\b', blk):
            fend = _block_end(blk, f.start())
            fb = blk[f.start():fend]
            lay = re.search(r'\(layer\s+"?([^"\s)]+)"?\s*\)', fb)
            pts = [(float(a), float(b)) for a, b in re.findall(r'\(xy\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)', fb)]
            if lay and len(pts) >= 3:
                out.append((lay.group(1), name, pts))
    return out


def _block_end(text, start):
    depth, i, n, in_str = 0, start, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def pad_angle(fp, pad):
    """The pad's absolute rotation in the file (at x y angle): kae stores it relative to the footprint."""
    return fp.rot + (pad.lrot if fp.side == "F" else -pad.lrot)


def pad_poly(fp, pad):
    x, y = pad.x, pad.y
    w, h = pad.size
    ang = pad_angle(fp, pad)
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    if pad.shape == "circle":
        return shapely.Point(x, y).buffer(w / 2, quad_segs=4)
    if pad.shape == "oval":
        if w >= h:
            dx, dy, r = (w - h) / 2, 0, h / 2
        else:
            dx, dy, r = 0, (h - w) / 2, w / 2
        ex, ey = dx * ca + dy * sa, -dx * sa + dy * ca
        if abs(ex) + abs(ey) < 1e-9:
            return shapely.Point(x, y).buffer(r, quad_segs=4)
        return shapely.LineString([(x - ex, y - ey), (x + ex, y + ey)]).buffer(r, quad_segs=4)
    if pad.shape == "custom" and getattr(pad, "outline", None) is not None:
        # real outline of a custom pad, pad frame, placed at the pad
        g = shapely.affinity.rotate(pad.outline, -ang, origin=(0, 0)) if ang else pad.outline
        return shapely.affinity.translate(g, x, y)
    r = min(max(pad.rratio or 0.25, 0.0), 0.5) * min(w, h) if pad.shape == "roundrect" else 0.0
    hw, hh = max(w / 2 - r, 1e-4), max(h / 2 - r, 1e-4)
    pts = []
    for sx_, sy_ in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        lx, ly = sx_ * hw, sy_ * hh
        pts.append((x + lx * ca + ly * sa, y - lx * sa + ly * ca))
    poly = shapely.Polygon(pts)
    return poly.buffer(r, quad_segs=3) if r > 1e-6 else poly


def outline_polygon(b):
    """Board outline polygon (union of the Edge.Cuts polygons, holes kept), None when absent or tiny."""
    try:
        polys = list(b.outline or [])
        if not polys:
            return None
        g = shapely.union_all(np.array(polys, dtype=object))
        return g if g.area > 1.0 else None
    except Exception:
        return None


class Model:
    """Copper of one board, ready for the columns: tracks as line segments, pads, vias, fills per layer."""

    def __init__(self, b, fills):
        self.board = b
        self.cu = list(b.stackup.copper) if b.stackup and b.stackup.copper else ["F.Cu", "B.Cu"]
        nets = {}
        nid = lambda n: 0 if not n else nets.setdefault(n, len(nets) + 1)
        self.nets = nets
        rows, self.straight = [], []
        for t in b.tracks:
            n = nid(t.net)
            if t.mid is None:
                r = (t.start[0], t.start[1], t.end[0], t.end[1], t.width, t.layer, n)
                rows.append(r)
                self.straight.append(r)
            else:
                pts = arc_pts(t.start, t.mid, t.end)
                for p0, p1 in zip(pts[:-1], pts[1:]):
                    rows.append((p0[0], p0[1], p1[0], p1[1], t.width, t.layer, n))
        self.arr = np.array([r[:5] for r in rows], dtype=float) if rows else np.zeros((0, 5))
        self.seg_layer = np.array([r[5] for r in rows], dtype=object) if rows else np.array([], dtype=object)
        self.seg_net = np.array([r[6] for r in rows], dtype=np.int64)
        self.lens = np.hypot(self.arr[:, 2] - self.arr[:, 0], self.arr[:, 3] - self.arr[:, 1]) if rows else np.zeros(0)
        lyr = {l: dict(geom=[], net=[], kind=[], hw=[]) for l in self.cu}
        if rows:
            lines = shapely.linestrings(np.stack([self.arr[:, :2], self.arr[:, 2:4]], axis=1))
            caps = shapely.buffer(lines, self.arr[:, 4] / 2, quad_segs=3, cap_style="round")
            for i, s in enumerate(rows):
                if s[5] in lyr and self.lens[i] > 1e-6:
                    d = lyr[s[5]]
                    d["geom"].append(caps[i])
                    d["net"].append(self.seg_net[i])
                    d["kind"].append(0)
                    d["hw"].append(self.arr[i, 4] / 2)
        self.pads = []
        for fp in b.footprints:
            for p in fp.pads:
                if p.kind == "np_thru_hole":
                    continue
                try:
                    poly = pad_poly(fp, p)
                except Exception:
                    continue
                ls = [l for l in p.layers if l in lyr]
                net = nid(p.net)
                self.pads.append(dict(p=p, poly=poly, net=net, layers=ls))
                for l in ls:
                    d = lyr[l]
                    d["geom"].append(poly)
                    d["net"].append(net)
                    d["kind"].append(1)
                    d["hw"].append(0.0)
        self.vias = []
        for v in b.vias:
            net = nid(v.net)
            poly = shapely.Point(v.x, v.y).buffer(v.size / 2, quad_segs=3)
            ls = [l for l in self.cu if v.type == "through" or not v.layers or l in v.layers]
            if v.type != "through" and len(v.layers) >= 2:
                try:
                    i0, i1 = sorted((self.cu.index(v.layers[0]), self.cu.index(v.layers[-1])))
                    ls = self.cu[i0:i1 + 1]
                except ValueError:
                    ls = list(self.cu)
            self.vias.append(dict(v=v, net=net, layers=ls, poly=poly))
            for l in ls:
                d = lyr[l]
                d["geom"].append(poly)
                d["net"].append(net)
                d["kind"].append(2)
                d["hw"].append(v.size / 2)
        self.zone_polys = {l: [] for l in self.cu}
        for layer, name, pts in fills:
            if layer not in lyr:
                continue
            net = nid(name)
            try:
                g = shapely.Polygon(pts)
                if not g.is_valid:
                    g = g.buffer(0)
                if g.is_empty or g.area <= 0:
                    continue
            except Exception:
                continue
            self.zone_polys[layer].append((g, net))
            for gg in ([g] if g.geom_type == "Polygon" else list(g.geoms)):
                for r in [gg.exterior] + list(gg.interiors):
                    c = shapely.get_coordinates(shapely.simplify(r, 0.01))
                    if len(c) < 2:
                        continue
                    el = shapely.linestrings(np.stack([c[:-1], c[1:]], axis=1))
                    d = lyr[layer]
                    d["geom"].extend(el)
                    d["net"].extend([net] * len(el))
                    d["kind"].extend([3] * len(el))
                    d["hw"].extend([0.0] * len(el))
        for d in lyr.values():
            d["geom"] = np.array(d["geom"], dtype=object)
            d["net"] = np.array(d["net"], dtype=np.int64)
            d["kind"] = np.array(d["kind"], dtype=np.int8)
            d["hw"] = np.array(d["hw"], dtype=float)
            d["tree"] = STRtree(d["geom"]) if len(d["geom"]) else None
        self.lyr = lyr


def _samples(m):
    arr, lens = m.arr, m.lens
    xs, ys, ux, uy, dl, hw, si = [], [], [], [], [], [], []
    for i in range(len(arr)):
        L = lens[i]
        if L < 1e-6:
            continue
        n = max(1, int(L / SAMPLE))
        t = (np.arange(n) + 0.5) / n
        xs.append(arr[i, 0] + (arr[i, 2] - arr[i, 0]) * t)
        ys.append(arr[i, 1] + (arr[i, 3] - arr[i, 1]) * t)
        ux.append(np.full(n, (arr[i, 2] - arr[i, 0]) / L))
        uy.append(np.full(n, (arr[i, 3] - arr[i, 1]) / L))
        dl.append(np.full(n, L / n))
        hw.append(np.full(n, arr[i, 4] / 2))
        si.append(np.full(n, i))
        xs.append(np.array([arr[i, 0], arr[i, 2]]))         # zero-weight end samples: better minimum gaps
        ys.append(np.array([arr[i, 1], arr[i, 3]]))
        ux.append(np.full(2, (arr[i, 2] - arr[i, 0]) / L))
        uy.append(np.full(2, (arr[i, 3] - arr[i, 1]) / L))
        dl.append(np.zeros(2))
        hw.append(np.full(2, arr[i, 4] / 2))
        si.append(np.full(2, i))
    if not xs:
        return None
    return {k: np.concatenate(v) for k, v in dict(x=xs, y=ys, ux=ux, uy=uy, dl=dl, hw=hw, si=si).items()}


def spacing(m, s):
    """Critical area for shorts (mm^2) over track samples, pours included, and the minimum track-track and track-pad
    gaps (mm). Each sample's two sides take the nearest other-net copper within GAP_MAX, summed as L x0^2 / gap."""
    gl, gr = np.full(len(s["x"]), np.inf), np.full(len(s["x"]), np.inf)
    tt_min, tp_min = np.inf, np.inf
    lay = m.seg_layer[s["si"]]
    for l in m.cu:
        mask = np.nonzero(lay == l)[0]
        d = m.lyr[l]
        if not len(mask) or d["tree"] is None:
            continue
        pts = shapely.points(s["x"][mask], s["y"][mask])
        qi, ti = d["tree"].query(pts, predicate="dwithin", distance=GAP_MAX + s["hw"][mask] + 0.01)
        if not len(qi):
            continue
        keep = ~((d["net"][ti] == m.seg_net[s["si"][mask[qi]]]) & (d["net"][ti] != 0))
        qi, ti = qi[keep], ti[keep]
        if not len(qi):
            continue
        gp, items = pts[qi], d["geom"][ti]
        gap = shapely.distance(gp, items) - s["hw"][mask[qi]]
        kinds = d["kind"][ti]
        co = shapely.get_coordinates(shapely.shortest_line(gp, items)).reshape(-1, 4)
        vx, vy = co[:, 2] - co[:, 0], co[:, 3] - co[:, 1]
        idx = mask[qi]
        left = s["ux"][idx] * vy - s["uy"][idx] * vx >= 0
        np.minimum.at(gl, idx[left], gap[left])
        np.minimum.at(gr, idx[~left], gap[~left])
        if (kinds == 0).any():
            tt_min = min(tt_min, float(np.min(gap[kinds == 0])))
        if (kinds == 1).any():
            tp_min = min(tp_min, float(np.min(gap[kinds == 1])))
    ca = 0.0
    for g in (gl, gr):
        ok = g <= GAP_MAX
        ca += float(np.sum(s["dl"][ok] * X0 ** 2 / np.maximum(g[ok], SHORT_CLAMP)))
    return ca, (tt_min if math.isfinite(tt_min) else None), (tp_min if math.isfinite(tp_min) else None)


def copper_diff(m, outl):
    """Worst difference in copper area share between mirrored layer pairs, percentage points, pours included."""
    if outl is None:
        return None
    area = outl.area
    frac = {}
    for l in m.cu:
        d = m.lyr[l]
        polys = list(d["geom"][d["kind"] != 3]) if len(d["geom"]) else []
        zp = [z[0] for z in m.zone_polys[l]]
        items = np.array(polys + zp, dtype=object)
        if not len(items):
            frac[l] = 0.0
            continue
        u = shapely.union_all(items)
        frac[l] = float(shapely.intersection(u, outl).area) / area
    n = len(m.cu)
    diffs = [abs(frac[m.cu[i]] - frac[m.cu[n - 1 - i]]) * 100 for i in range(n // 2)]
    return rd(max(diffs), 2) if diffs else None


def via_in_pad_small_signal(m):
    """Vias in a same-net SMD pad smaller than 2 mm^2 on a signal net (net-name heuristic, as Stage 1)."""
    by_layer = {}
    for q in m.pads:
        if q["p"].kind == "smd":
            for l in q["layers"]:
                by_layer.setdefault(l, []).append(q)
    trees = {l: (STRtree(np.array([q["poly"] for q in v], dtype=object)), v) for l, v in by_layer.items()}
    per_pad = {}
    any_vip = False
    netname = {v: k for k, v in m.nets.items()}
    for vr in m.vias:
        v = vr["v"]
        ends = (v.layers[0], v.layers[-1]) if len(v.layers) >= 2 else (m.cu[0], m.cu[-1])
        for l in ends:
            if l not in trees:
                continue
            t, qs = trees[l]
            for i in t.query(shapely.Point(v.x, v.y), predicate="intersects"):
                q = qs[i]
                if q["net"] and q["net"] == vr["net"]:
                    any_vip = True
                    per_pad.setdefault(id(q), dict(q=q, n=0))["n"] += 1
    n = 0
    for rec in per_pad.values():
        q = rec["q"]
        if q["poly"].area < PAD_SMALL_MM2 and not PWR_RE.search(netname.get(q["net"], "") or ""):
            n += rec["n"]
    return n, any_vip


def fab_class(m, wmin, tt, tp, has_vip):
    """Cheapest JLCPCB class (kae.route.fab) that builds the board's smallest features; None when none does."""
    from kae.route import fab
    table = fab.PROFILES["jlcpcb"]["two_layer" if len(m.cu) <= 2 else "multilayer"]
    vd = min((v["v"].size for v in m.vias), default=None)
    dr = [v["v"].drill for v in m.vias if v["v"].drill > 0]
    vdr = min(dr) if dr else None
    for cls in fab.CLASSES:
        spec = table.get(cls)
        if spec is None:
            continue
        if not ((wmin is None or wmin + 1e-6 >= spec["track"]) and (tt is None or tt + 1e-6 >= spec["space"]) and
                (tp is None or tp + 1e-6 >= spec["pad_track"]) and (vd is None or vd + 1e-6 >= spec["via"][0]) and
                (vdr is None or vdr + 1e-6 >= spec["via"][1])):
            continue
        vp = spec.get("via_in_pad")
        if has_vip and not (vp is True or (isinstance(vp, (int, float)) and not isinstance(vp, bool) and len(m.cu) >= vp)):
            continue
        return cls
    return None


def acute_per_m(m, total_mm):
    """Same-net track junctions with an interior angle under 90 degrees, per m of track (endpoints matched at 0.02 mm;
    straight segments only, arcs are smooth by construction)."""
    tol = 0.02
    ends = {}
    for s in m.straight:
        for x, y, ox, oy in ((s[0], s[1], s[2], s[3]), (s[2], s[3], s[0], s[1])):
            ends.setdefault((round(x / tol), round(y / tol), s[5], s[6]), []).append((ox - x, oy - y))
    n = 0
    for vs in ends.values():
        if len(vs) == 2:
            (ax, ay), (bx, by) = vs
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            if la > 1e-6 and lb > 1e-6 and (ax * bx + ay * by) / (la * lb) > 0.0001:
                n += 1
    return rd(n / (total_mm / 1000), 4) if total_mm else None


def layers_used(b):
    """Track length per layer and the layers carrying zones of a board (for phantom_share)."""
    tr = {}
    for t in b.tracks:
        L = math.dist(t.start, t.end)
        tr[t.layer] = tr.get(t.layer, 0.0) + L
    zones = set()
    for z in b.zones:
        zones.update(z.layers)
    return tr, zones


def refill(src, wrap):
    """A copy of src with its zones filled by pcbnew under $KAE_KICAD_WRAP, in a folder of its own with src's project
    files (the filler reads the net classes' clearances from them); returns its path."""
    src = Path(src)
    d = src.parent / "refilled"
    d.mkdir(exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        if src.with_suffix(ext).exists():
            shutil.copy2(src.with_suffix(ext), d / f"board{ext}")
    q = d / "board.kicad_pcb"
    code = ("import pcbnew,sys\nb=pcbnew.LoadBoard(sys.argv[1])\nzs=pcbnew.ZONES()\n"
            "[zs.append(pcbnew.Cast_to_ZONE(b.GetArea(i))) for i in range(b.GetAreaCount())]\n"
            "pcbnew.ZONE_FILLER(b).Fill(zs) if len(zs) else None\npcbnew.SaveBoard(sys.argv[2],b)\n")
    subprocess.run(wrap.split() + ["python3", "-c", code, str(src), str(q)], check=True, capture_output=True, timeout=int(os.environ.get("REFILL_TIMEOUT", "1500")))
    return q


def load(path, workdir):
    """A kae Board of path (gzip allowed), loaded next to the project files already beside path."""
    from kae.board.kicad_file import load as kload
    p = Path(path)
    if p.suffix == ".gz":
        q = Path(workdir) / "board.kicad_pcb"
        with gzip.open(p, "rb") as f, open(q, "wb") as g:
            shutil.copyfileobj(f, g)
        for e in (".kicad_pro", ".kicad_dru"):
            sib = p.with_name(p.name.replace(".kicad_pcb.gz", e))
            if sib.exists():
                shutil.copy2(sib, q.with_suffix(e))
        p = q
    return kload(p), p


def compute(path, human=None, do_refill=False, wrap=None, workdir=None):
    """The columns of one board. Fields are null where the board cannot support them (no tracks, no outline)."""
    workdir = workdir or tempfile.mkdtemp(prefix="mfg-")
    b, p = load(path, workdir)
    refilled = False
    if do_refill and b.zones:
        p = Path(refill(p, wrap or os.environ["KAE_KICAD_WRAP"]))
        b, p = load(p, workdir)
        refilled = True
    text = Path(p).read_text(encoding="utf-8", errors="replace")
    fills = read_fills(text)
    m = Model(b, fills)
    total = float(m.lens.sum())
    has_zones = bool(b.zones)
    pours_ok = not has_zones or bool(fills)           # a board with zones but no fill stored cannot say anything about pours
    out = dict(cu_layers=len(m.cu), track_mm=rd(total, 2), zones=len(b.zones), refilled=refilled, pours_available=pours_ok,
               ca_short_per_m_pours=None, width_at_class_min=None, copper_pair_diff_pp=None, copper_flag=None,
               vip_small_signal=None, fab_class_jlcpcb=None, phantom_share=None, exp_breakout_40um=None, acute_per_m=None)
    s = _samples(m)
    wmin = float(m.arr[:, 4].min()) if len(m.arr) else None
    if s is not None:
        ca, tt, tp = spacing(m, s)
        if pours_ok:
            out["ca_short_per_m_pours"] = rd(ca / (total / 1000), 4)
    else:
        tt, tp = None, None
    # width: share of length within 2 % of the smallest track width any net class asks for
    # (needs the board's own classes: with no .kicad_pro and no legacy (net_class ...) the loader only has KiCad's default)
    has_classes = Path(p).with_suffix(".kicad_pro").exists() or "(net_class " in text
    widths = [nc.track_width for nc in (b.rules.netclasses or {}).values() if nc.track_width] if has_classes else []
    if total > 0 and widths:
        floor = min(widths)
        out["width_at_class_min"] = rd(float(m.lens[m.arr[:, 4] <= floor * 1.02].sum() / total))
    n_vip, has_vip = via_in_pad_small_signal(m)
    out["vip_small_signal"] = n_vip
    if s is not None:
        out["fab_class_jlcpcb"] = fab_class(m, wmin, tt, tp, has_vip)
    rings = [(v["v"].size - v["v"].drill) / 2 for v in m.vias if v["v"].drill > 0]
    out["exp_breakout_40um"] = rd(sum(Q(r / SIGMA_BREAKOUT) for r in rings), 6)
    if total:
        out["acute_per_m"] = acute_per_m(m, total)
    if pours_ok:
        d = copper_diff(m, outline_polygon(b))
        out["copper_pair_diff_pp"] = d
        out["copper_flag"] = bool(d is not None and d >= COPPER_FLAG_PP)
    if human is not None:
        hb, _ = load(human, tempfile.mkdtemp(prefix="mfg-h-", dir=workdir))
        h_tr, h_z = layers_used(hb)
        used = {l for l, L in h_tr.items() if L > 0} | h_z | ({"F.Cu", "B.Cu"} & set(m.cu))
        tr, _ = layers_used(b)
        tot = sum(tr.values())
        out["phantom_share"] = rd(sum(L for l, L in tr.items() if l not in used and L > 0) / tot, 4) if tot else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--human")
    ap.add_argument("--out", required=True)
    ap.add_argument("--refill", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    res = compute(a.board, human=a.human, do_refill=a.refill)
    res["wall_s"] = round(time.time() - t0, 2)
    Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
