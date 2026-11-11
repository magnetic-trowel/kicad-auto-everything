# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus scorecard: report-only measurements of a routed board's buses.

Inputs are a board with its copper, and optionally the board's `kicad-cli` DRC report. Output is one record per bus and
one per diff pair: lanes open, coupled share, vias per lane, via parity, skew, layer agreement, the class-keyed limits
of kae.bus.limits with their source, and (with `--decompose`) the skew terms of kae.bus.skew.

Every number here is a description. It feeds no score, no cost and no selection (docs/research/routing/bus-yardstick-2611.md).
Coupled share and bundling are shape, not a target: nothing may reward them.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict, deque
from statistics import median

import numpy as np
from scipy.spatial import cKDTree

from . import copper as C
from . import detect as D
from . import limits as L

DRC_NET = re.compile(r'\[(.*?)\](?= of | on |\s*$)')   # net names may contain brackets (sdram_dq[0])


class Ctx:
    """A board's copper indexed by net, with one lazily built graph per net."""

    def __init__(self, board, bs):
        self.board, self.part, self.cu, self.net_pads = board, bs.part, bs.copper, bs.net_pads
        self.tracks, self.vias = C.flatten_tracks(board)
        self._graph = {}

    def graph(self, net):
        g = self._graph.get(net)
        if g is None:
            g = C.NetGraph(self.tracks.get(net, []), self.vias.get(net, []), [p for _r, p in self.net_pads.get(net, [])])
            self._graph[net] = g
        return g


def lane_pieces(ctx, ln, ra, rb):
    """Ordered pieces of a lane between its terminal pads at ra and rb: [(net, pad_start, pad_end)]."""
    pa = D.line_pad(ln, ra)
    pb = D.line_pad(ln, rb)
    if pa.net == pb.net:
        return [(pa.net, pa, pb)]
    # chain through series parts
    adj = defaultdict(list)   # net -> [(other_net, pad_here, pad_there, ref)]
    for ref in ln.series:
        pi = ctx.part[ref]
        ps = [p for p in pi['pads'] if p.net in ln.nets]
        for i in range(len(ps)):
            for j in range(len(ps)):
                if i != j and ps[i].net != ps[j].net:
                    adj[ps[i].net].append((ps[j].net, ps[i], ps[j], ref))
    # BFS over nets
    prev = {pa.net: None}
    dq = deque([pa.net])
    while dq:
        u = dq.popleft()
        if u == pb.net:
            break
        for v, pu, pv, ref in adj[u]:
            if v not in prev:
                prev[v] = (u, pu, pv)
                dq.append(v)
    if pb.net not in prev:
        return None
    seq = []
    cur = pb.net
    start_pad = pb
    while prev[cur] is not None:
        u, pu, pv = prev[cur]
        seq.append((cur, pv, start_pad))
        start_pad = pu
        cur = u
    seq.append((cur, pa, start_pad))
    seq.reverse()
    return seq


def lane_paths(ctx, ln, ra, rb):
    pieces = lane_pieces(ctx, ln, ra, rb)
    if pieces is None:
        return None, 'no_chain'
    out = []
    for net, p1, p2 in pieces:
        g = ctx.graph(net)
        s = g.attach(p1.x, p1.y, C.pad_layers(p1, ctx.cu), p1.size[0], p1.size[1])
        t = g.attach(p2.x, p2.y, C.pad_layers(p2, ctx.cu), p2.size[0], p2.size[1])
        path = g.dijkstra(s, t)
        if path is None:
            return None, 'open'
        out.append(C.polyline_from(g, path))
    return out, ''


def lane_measure(ctx, ln, ra, rb):
    pieces, err = lane_paths(ctx, ln, ra, rb)
    if pieces is None:
        return dict(open=err)
    r = C.lane_metrics(pieces)
    w = [s[5] for net in ln.nets for s in ctx.tracks.get(net, [])]
    r['w'] = median(w) if w else 0.0
    return r


TPD_OUTER, TPD_INNER = 6.0, 6.8    # ps/mm; FR4 microstrip and stripline, nominal (Tier 1 uses no solver)
BUNDLE_MM = 2.0                    # centre-to-centre, for the fan-in/trunk split and the census's bundled share


def _tpd(layer, cu):
    return TPD_OUTER if layer in ("F.Cu", "B.Cu") or layer == (cu[0] if cu else None) or layer == (cu[-1] if cu else None) else TPD_INNER


def _via_delay(board, spans, cu):
    """Vias' flight delay (ps) of a lane's layer changes, from the stackup, at inner-layer speed."""
    st = board.stackup
    total = 0.0
    if st and st.copper and st.gaps and len(st.gaps) == len(st.copper) - 1:
        pos = {n: i for i, n in enumerate(st.copper)}
        for a, b in spans:
            if a in pos and b in pos:
                i, j = sorted((pos[a], pos[b]))
                total += sum(st.gaps[i:j]) * TPD_INNER
    else:
        total = len(spans) * (board.thickness or 1.6) * TPD_INNER
    return total


def _nearest_siblings(samples):
    """For each lane's samples, centre distance to the nearest sample of another lane of the bus on the same layer."""
    pts = [(x, y, lay, s, i) for i, smp in enumerate(samples) for x, y, lay, s in smp]
    if not pts:
        return None, None, None
    layers = sorted({p[2] for p in pts})
    laycode = np.array([layers.index(p[2]) for p in pts], dtype=int)
    arr = np.array([(p[0], p[1], p[3], p[4]) for p in pts], dtype=float)
    nearest = np.full(len(arr), np.inf)
    for li in range(len(layers)):
        idx = np.nonzero(laycode == li)[0]
        if len(idx) < 2:
            continue
        tree = cKDTree(arr[idx, :2])
        d, nb = tree.query(arr[idx, :2], k=min(25, len(idx)))
        lane_of = arr[idx, 3]
        d, nb = np.atleast_2d(d), np.atleast_2d(nb)
        for pos in range(len(idx)):
            for dd, ii in zip(d[pos], nb[pos]):
                if int(lane_of[ii]) != int(lane_of[pos]):
                    nearest[idx[pos]] = dd
                    break
    return arr, nearest, laycode


def _trunk_span(s_, nn_):
    """(start, end) arc of a lane's sustained bundled stretch (samples <= BUNDLE_MM from a sibling for at least 3 of 4 mm),
    or None when the lane never runs with a sibling."""
    win = 16
    if len(s_) < win:
        return None
    flag = (nn_ <= BUNDLE_MM).astype(int)
    cf = np.cumsum(np.concatenate([[0], flag]))
    rate = (cf[win:] - cf[:-win]) / win
    ok = np.nonzero(rate >= 0.75)[0]
    if not len(ok):
        return None
    return float(s_[ok[0]]), float(s_[min(ok[-1] + win - 1, len(s_) - 1)])


def _sum_f(headings, s0, s1):
    """(sum of 2 tan(theta/2), net turning) of a lane's vertices between arc s0 and s1 (A2; docs/research/routing/bus-yardstick-2611.md)."""
    sf = net = 0.0
    for (sa, ha, _), (sb, hb, _) in zip(headings, headings[1:]):
        if sb < s0 or sb > s1:
            continue
        t = (hb - ha + math.pi) % (2 * math.pi) - math.pi
        if abs(t) > 3.0:
            continue
        sf += 2 * math.tan(t / 2) if abs(t) < 2.6 else t
        net += t
    return sf, net


def _decompose(lanes, nearest, arr, cu, board):
    """A2: a complete group's lane-length differences as additive terms (physics.md X2)."""
    n = len(lanes)
    trunk, offs, sfs, turned = [None] * n, [None] * n, [], []
    for i, lv in enumerate(lanes):
        sel = arr[:, 3] == i
        s_, nn_ = arr[sel, 2], nearest[sel]
        o = np.argsort(s_)
        ts = _trunk_span(s_[o], nn_[o])
        if ts is None:
            continue
        trunk[i] = ts
        f, _ = _sum_f(lv["headings"], *ts)
        sfs.append(f)
        # lane position at the middle of its trunk
        mid = (ts[0] + ts[1]) / 2
        j = int(np.argmin(np.abs(arr[sel, 2] - mid)))
        offs[i] = (arr[sel, 0][j], arr[sel, 1][j])
    have = [i for i in range(n) if trunk[i] is not None]
    L = np.array([lv["length"] for lv in lanes])
    fan = np.zeros(n)                # fan-in: path length of the end stretches beyond their straight line
    for i in have:
        sel = arr[:, 3] == i
        s_, xy = arr[sel, 2], arr[sel, :2]
        for s0, s1 in ((0.0, trunk[i][0]), (trunk[i][1], L[i])):
            p0 = xy[np.argmin(np.abs(s_ - s0))]
            p1 = xy[np.argmin(np.abs(s_ - s1))]
            fan[i] += max(0.0, (s1 - s0) - float(np.hypot(*(p1 - p0))))
    serp = np.array([lv["serp"]["excess"] for lv in lanes])
    chord = np.array([lv["straight"] for lv in lanes])   # pad to pad in a straight line: placement and pin positions
    turn = np.zeros(n)
    if len(have) >= 2:
        # the bus's direction at the median lane's mid-trunk; lane offsets are measured across it
        m = np.array([offs[i] for i in have])
        c = m.mean(axis=0)
        med = sorted(have, key=lambda k: L[k])[len(have) // 2]
        mid = (trunk[med][0] + trunk[med][1]) / 2
        h = next((h for s_a, h, seg in lanes[med]["headings"] if s_a <= mid <= s_a + seg), lanes[med]["headings"][-1][1])
        nrm = np.array([-math.sin(h), math.cos(h)])     # left of the direction of travel, in the board's own coordinates
        d = (m - c) @ nrm
        sum_f = float(median(sfs))
        for k, i in enumerate(have):
            turn[i] = -d[k] * sum_f
    terms = {"chord": chord, "fan": fan, "meander": serp, "turn": turn}
    y = L - L.mean()
    t = {k: v - v.mean() for k, v in terms.items()}
    t["other"] = y - t["chord"] - t["fan"] - t["meander"] - t["turn"]
    tpds = [sum(v * _tpd(l, cu) for l, v in lv["layer_len"].items()) for lv in lanes]
    delays = np.array(tpds)
    tbar = float(delays.sum() / L.sum()) if L.sum() else TPD_INNER
    via = np.array([_via_delay(board, lv["spans"], cu) for lv in lanes])
    y_ps = (delays + via) - (delays + via).mean()
    t_ps = {"length": tbar * y, "layer": delays - tbar * L, "via": via}
    t_ps["layer"] -= t_ps["layer"].mean()
    t_ps["via"] -= t_ps["via"].mean()
    out = {"n": n, "trunked": len(have), "tbar_ps_mm": round(tbar, 3)}
    out["mm"] = {k: [round(float((v * y).sum()), 4), round(float((v * v).sum()), 4), round(float(v.max() - v.min()), 3)] for k, v in t.items()}
    out["mm_yy"] = round(float((y * y).sum()), 4)
    out["ps"] = {k: [round(float((v * y_ps).sum()), 2), round(float((v * v).sum()), 2), round(float(v.max() - v.min()), 2)] for k, v in t_ps.items()}
    out["ps_yy"] = round(float((y_ps * y_ps).sum()), 2)
    return out


def measure_bus(ctx, row, lanes, opens, limit, decompose=False):
    """One bus: lanes open, and for lanes with a pad-to-pad copper path, the measurements."""
    res = dict(width=len(lanes), lanes_open=0, open_items=0, measured=0)
    a, b = row["a"], row["b"]
    measured = []
    for ln in lanes:
        items = sum(opens.get(n, 0) for n in ln.nets)
        if items:
            res["lanes_open"] += 1
            res["open_items"] += items
        if b is None or a not in ln.terms or b not in ln.terms:
            continue
        lm = lane_measure(ctx, ln, a, b)
        if "open" in lm or lm["length"] <= 0:
            continue
        lm["straight"] = math.dist(*(((p := D.line_pad(ln, x)).x, p.y) for x in (a, b)))
        measured.append(lm)
    res["complete"] = res["lanes_open"] == 0
    res["measured"] = len(measured)
    if len(measured) < 2:
        return res
    lens = [m["length"] for m in measured]
    vias = [m["vias"] for m in measured]
    res["len_mean"] = round(sum(lens) / len(lens), 2)
    res["vias_lane"] = round(sum(vias) / len(vias), 3)
    res["via_max"] = max(vias)
    res["via_spread"] = max(vias) - min(vias)
    res["via_equal"] = int(max(vias) == min(vias))
    spans = defaultdict(int)
    for m in measured:
        spans[tuple(sorted(m["spans"]))] += 1
    res["via_span_mismatch"] = len(measured) - max(spans.values())
    res["skew_mm"] = round(max(lens) - min(lens), 3)
    res["skew_rel"] = round(res["skew_mm"] / (sum(lens) / len(lens)), 4)
    total = sum(lens)
    bylay = defaultdict(float)
    for m in measured:
        for k, v in m["layer_len"].items():
            bylay[k] += v
    res["layers_used"] = len(bylay)
    res["layer_agreement"] = round(max(bylay.values()) / total, 3)    # share of the length on the bus's modal layer
    res["lanes_one_layer"] = round(sum(1 for m in measured if len(m["layer_len"]) == 1) / len(measured), 3)
    cu = ctx.cu
    res["stripline_share"] = round(sum(v for k, v in bylay.items() if _tpd(k, cu) == TPD_INNER) / total, 3)
    delays = [sum(v * _tpd(k, cu) for k, v in m["layer_len"].items()) + _via_delay(ctx.board, m["spans"], cu) for m in measured]
    res["skew_ps"] = round(max(delays) - min(delays), 2)
    arr, nearest, _lc = _nearest_siblings([m["samples"] for m in measured])
    if nearest is None:
        return res
    w = median(m["w"] for m in measured)
    res["track_w"] = round(w, 3)
    res["coupled_3w"] = round(float((nearest <= 4 * w).mean()), 3)   # edge gap within 3 trace widths: shape only, no target
    res["bundled_2mm"] = round(float((nearest <= BUNDLE_MM).mean()), 3)
    res["serp_lanes"] = sum(1 for m in measured if m["serp"]["n"] > 0)
    if limit.skew_mm is not None:
        res["skew_margin"] = round(limit.skew_mm / max(res["skew_mm"], 1e-3), 3)
        res["skew_ok"] = int(res["skew_mm"] <= limit.skew_mm)
    if limit.via_max is not None:
        res["via_ok"] = int(res["via_max"] <= limit.via_max and (limit.via_spread is None or res["via_spread"] <= limit.via_spread))
    if decompose and len(measured) >= 3 and res["measured"] == res["width"] and row.get("multi_lanes", 0) == 0 and "lanes_open" in res:
        res["skew_decomp"] = _decompose(measured, nearest, arr, cu, ctx.board)
    return res


def open_items_from_drc(drc):
    """net -> number of `unconnected_items` entries in a kicad-cli DRC report that name it, and whether the report's list hit KiCad's cap."""
    items = (drc or {}).get("unconnected_items") or []
    counts = defaultdict(int)
    for it in items:
        for sub in it.get("items", []):
            m = DRC_NET.search(sub.get("description", ""))
            if m:
                counts[m.group(1)] += 1
    return counts, len(items) >= 499


def board_scorecard(board, drc=None, decompose=False, bs=None):
    """The scorecard of one routed board: dict with `buses`, `pairs` and the source of the open counts.

    `drc` is the kicad-cli report of this board (dict). Where it is missing or its unconnected list hit KiCad's 499-item
    cap, opens come from this module's copper graph (zones ignored) and `opens_src` says "copper".
    """
    bs = bs or D.detect_board(board)
    ctx = Ctx(board, bs)
    opens, capped = open_items_from_drc(drc)
    if drc is None or capped:
        opens, src = defaultdict(int), "copper"
        for net in bs.sig:
            m = ctx.graph(net).missing_connections()
            if m:
                opens[net] = m
    else:
        src = "drc"
    out = dict(opens_src=src, opens_capped=bool(capped), n_buses=len(bs.buses), cu_layers=len(bs.copper))
    rows = []
    for row, m in zip(bs.buses, bs.raw):
        lanes = m["lanes"]
        rec = {k: row[k] for k in ("kind", "width", "a", "b", "ev", "multi_lanes", "dist", "a_type", "b_type", "a_cls", "b_cls",
                                   "names", "nets") if k in row}
        perm = row.get("perm")
        if perm:
            rec["lds"], rec["inv"] = perm["lds"], perm["inv"]
        lim = L.for_bus(row, bs.part)
        rec["limit"] = lim.asdict()
        rec.update(measure_bus(ctx, row, lanes, opens, lim, decompose))
        rows.append(rec)
    pair_rows = []
    for pr in bs.pairs:
        rec = {k: pr[k] for k in ("kind", "iface", "width", "a", "b", "ev", "dist", "names", "nets") if k in pr}
        rec["multi_lanes"] = 0
        lim = L.for_bus(dict(pr, kind="pair"), bs.part)
        rec["limit"] = lim.asdict()
        lanes = pr.get("_lanes")
        if lanes is None:
            nets = {n for ns in pr["nets"] for n in ns}
            rec["lanes_open"] = sum(1 for ns in pr["nets"] if any(opens.get(n, 0) for n in ns))
            rec["open_items"] = sum(opens.get(n, 0) for n in nets)
            rec["complete"] = rec["lanes_open"] == 0
        else:
            rec.update(measure_bus(ctx, pr, list(lanes), opens, lim, decompose))
        pair_rows.append(rec)
    out["buses"], out["pairs"] = rows, pair_rows
    return out


def main(argv=None):
    """`python -m kae.bus.scorecard BOARD [--drc drc.json] [--decompose]` prints the scorecard as JSON."""
    import argparse, gzip, json
    from kae.board.kicad_file import load
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--drc")
    ap.add_argument("--decompose", action="store_true")
    a = ap.parse_args(argv)
    drc = None
    if a.drc:
        with (gzip.open(a.drc, "rt") if a.drc.endswith(".gz") else open(a.drc)) as f:
            drc = json.load(f)
    print(json.dumps(board_scorecard(load(a.board), drc=drc, decompose=a.decompose)))


if __name__ == "__main__":
    main()
