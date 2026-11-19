# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A fast quote of each switching cell's hot loop: the evaluator's cell window (kae.excite.hotloop) solved alone,
without the board solve, so without its truncation correction.

    python -m kae.excite.cellquote BOARD.kicad_pcb [--intent OPERATING.json] [--pitch 0.125] [--drc drc.json] [-o OUT]

It is for ranking two layouts of one placement, not for absolute values: the window is set by the parts that carry
the cell's current in the copper-free circuit (hotloop.window_pads), so two layouts of one placement get the same
window, raster and pads, and differ only in their copper. What the window leaves out (the truncation the evaluator
adds back from the board solve) is the same copper outside the window for both when the layouts differ only near
the cell. On the hotloop-ab cells the raw window ordered pairs of kae layouts as the full evaluator did in 36 of 43
L_loop pairs and 33 of 37 R_loop pairs at 0.0625 mm (33 of 43 and 30 of 37 at the board's 0.25 mm), 50 of 56 when
the quotes differ by more than 10 %. A cell is "open" when its loop does not close in the window (grown up to
hotloop.MAX_GROW times) or when the DRC report lists a loop member as unconnected (as the evaluator does).

Rows: {source, state ok|open|invalid|not_computed, L_nH, R_mohm (at f_sw, skin-corrected unless --no-skin), window,
pitch, seconds}. `score(rows)` turns them into one number per board for a portfolio's tie-break."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

from . import hotloop as HL

PITCH = 0.125                # mm: the quote's raster (4x fewer cells than the evaluator's 0.0625, 16x faster)
MAX_CELLS = 6e5              # raster budget of one quote window (cells x copper layers): the pitch doubles past it


def _physical(z, f_fund, f_edge):
    """A window value a loop can have: 0 < L < 1 uH and 0 < R < 100 ohm."""
    L = z[f_edge].imag / (2 * math.pi * f_edge)
    return 0 < L < 1e-6 and 0 < z[f_fund].real < 100


def quote_cells(path, intent=None, pitch=PITCH, nsub=2, skin=True, drc=None, max_cells=MAX_CELLS, log=print, only=None):
    """One row per switching cell of the board at `path` (see the module doc); `only`: the cell ids (brief
    structure ids) to quote, the others left out (kae.route.hotloop.clear quotes one cell at a time)."""
    from kae.board import pinfacts as PF
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em.kicad import BoardMesh, canonical_order
    from kae.route.critical_recheck import fills_of
    from . import models as M
    from . import observe as O
    from . import sources as S
    from .evaluate import assume_stackup, board_window, coarsen_pitch, drc_open_cells, ledger_for, load_drc
    t0 = time.time()
    b = load(path)
    canonical_order(b)
    PF.apply(b, (intent or {}).get("pins"))
    b.stackup, _, _ = assume_stackup(b)
    brief = B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    cells = [s for s in srcs if s.kind == "cell" and (only is None or s.meta.get("cell") in set(only))]
    if not cells:
        return []
    obs = O.observers(bd, brief, srcs)
    P, _ = ledger_for(bd, brief, srcs, intent)
    fills = fills_of(path)
    bw = board_window(b)
    n_cu = len(b.stackup.gaps) + 1 if getattr(b, "stackup", None) is not None else 2
    bm0 = BoardMesh(path, bw, 1.0, nsub=1, b=b, fills=fills)        # pad shapes only
    drc_rep, _ = load_drc(path, drc)
    open_cells = drc_open_cells(drc_rep, brief, srcs) if drc_rep else {}
    gaps = list(getattr(b.stackup, "gaps", None) or [1.5])
    margin0 = max(HL.MARGIN_MM, HL.MARGIN_H * max(gaps[0], gaps[-1]))
    log(f"quote: setup {time.time() - t0:.1f}s, {len(cells)} cells")
    rows = []
    for s in cells:
        t1 = time.time()
        row = dict(source=s.name, cell=s.meta.get("cell"))
        if s.name in open_cells:
            rows.append(dict(row, state="open", why=open_cells[s.name]))
            continue
        o = next((x for x in obs if x.kind == "overshoot" and x.meta.get("source") == s.name), None)
        if o is None:
            rows.append(dict(row, state="not_computed", why="no overshoot observer"))
            continue
        f_fund = P[s.name]["f_sw"].typ
        f_edge = O.gentle_f(s)
        f_edge = max(f_edge, 2 * f_fund) if f_fund >= f_edge else f_edge
        box = HL._pad_box(bm0, HL.window_pads(bd, s, o, [f_fund, f_edge]))
        if box is None:
            rows.append(dict(row, state="not_computed", why="no pad of the cell in the copper model"))
            continue
        margin, z, grown = margin0, None, 0
        while True:
            win = (max(bw[0], box[0] - margin), max(bw[1], box[1] - margin),
                   min(bw[2], box[2] + margin), min(bw[3], box[3] + margin))
            pc, _ = coarsen_pitch(win, pitch, n_cu, max_cells)
            z, _, _ = HL._solve_window(path, b, bd, s, o, win, pc, nsub, fills, [f_fund, f_edge], skin, lambda *a: None)
            # a window that leaves the loop open, or reads a non-physical share (the return it cut off carried
            # part of the pattern: esp32's U6 read R = -61 mOhm in a 29 x 20 mm window), grows like the evaluator's
            if (z is not None and _physical(z, f_fund, f_edge)) or win == tuple(bw) or grown >= HL.MAX_GROW:
                break
            margin, grown = margin * 2, grown + 1
        if z is None:
            rows.append(dict(row, state="open", why=f"the loop does not close in its window grown {grown} times"))
            continue
        L = z[f_edge].imag / (2 * math.pi * f_edge)
        Pc = P[s.name]
        bad = unphysical(L, z[f_fund].real, Pc["V"].typ if "V" in Pc else 0.0, Pc["I"].typ if "I" in Pc else 0.0, f_edge)
        if bad:
            rows.append(dict(row, state="invalid", why=bad, L_raw_nH=round(L * 1e9, 4),
                             R_raw_mohm=round(z[f_fund].real * 1e3, 4), window=[round(x, 3) for x in win], pitch=pc))
            continue
        rows.append(dict(row, state="ok", L_nH=round(L * 1e9, 4), R_mohm=round(z[f_fund].real * 1e3, 4),
                         window=[round(x, 3) for x in win], pitch=pc, grown=grown, seconds=round(time.time() - t1, 1)))
        log(f"quote {s.name}: L {L * 1e9:.3f} nH, R {z[f_fund].real * 1e3:.3f} mOhm at {pc:g} mm ({time.time() - t1:.1f}s)")
    return rows


def unphysical(L, R, V, I, f_edge):
    """Why a quote's window values are no working loop's, or None: L_loop not positive (the window misses where the
    loop closes), or its resistance at f_sw or reactance at the edge band above the cell's load V / I (it closes
    through a part: the evaluator's open-cell bound, kae.excite.evaluate.OPEN_R_FRAC)."""
    from .evaluate import OPEN_R_FRAC
    if L <= 0:
        return f"L_loop {L * 1e9:.3g} nH is not positive: the window misses where the loop closes"
    if V > 0 and I > 0 and (R > OPEN_R_FRAC * V / I or L * 2 * math.pi * f_edge > V / I):
        return f"R {R:.3g} ohm or X {L * 2 * math.pi * f_edge:.3g} ohm above the load's V / I = {V / I:.3g} ohm"
    return None


def compare(a, b, tol=0.1):
    """Which of two quotes (rows of one placement) is better, per cell: -1 (a), 1 (b) or 0 (within `tol` on both
    L and R, or not comparable). A cell open in one only is decided for the other. Returns ({source: verdict}, sum)."""
    rb = {r["source"]: r for r in b}
    out = {}
    for x in a:
        y = rb.get(x["source"])
        if y is None or {"not_computed", "invalid"} & {x["state"], y["state"]}:
            continue
        if x["state"] == "open" or y["state"] == "open":
            out[x["source"]] = 0 if x["state"] == y["state"] else (1 if x["state"] == "open" else -1)
            continue
        v = 0.0
        for k in ("L_nH", "R_mohm"):
            p, q = max(x[k], 1e-6), max(y[k], 1e-6)
            r = math.log(q / p)
            if abs(r) > math.log(1 + tol):
                v += r
        out[x["source"]] = 0 if v == 0 else (-1 if v > 0 else 1)     # b larger: a is the better
    return out, sum(out.values())


OPEN_PENALTY = 5.0            # an open cell's score: e^5 ~ 150 x a closed one's L and R


def score(rows):
    """One number per board, lower better, for a portfolio's tie-break between layouts of one placement: the sum
    over its cells of ln L_nH + ln R_mohm, OPEN_PENALTY per open cell (cells not computed count 0); None when a
    cell's quote is not physical (state "invalid"). Two boards'
    difference is the sum of their cells' log ratios: 0.1 is about a 10 % change of one cell's L or R."""
    t = 0.0
    if any(r["state"] == "invalid" for r in rows):
        return None                      # no ranking from a board one of whose cells could not be quoted
    for r in rows:
        if r["state"] == "open":
            t += 2 * OPEN_PENALTY
        elif r["state"] == "ok":
            t += math.log(max(r["L_nH"], 1e-3)) + math.log(max(r["R_mohm"], 1e-3))
    return round(t, 4)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.excite.cellquote", description=__doc__.split("\n\n")[0])
    ap.add_argument("board")
    ap.add_argument("--intent", help="operating facts JSON (its pin facts and the cells' f_sw)")
    ap.add_argument("--pitch", type=float, default=PITCH)
    ap.add_argument("--no-skin", action="store_true")
    ap.add_argument("--drc", help="KiCad DRC report of this board (a loop member unconnected: the cell is open; "
                                  "default: drc.json beside the board, if any)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--score-out", help="also write {score, rows} here (score(): a portfolio's tie-break)")
    a = ap.parse_args(argv)
    intent = json.load(open(a.intent)) if a.intent else None
    rows = quote_cells(a.board, intent, pitch=a.pitch, skin=not a.no_skin, drc=a.drc or None,
                       log=lambda *x: print(*x, file=sys.stderr))
    txt = json.dumps(rows, indent=1)
    if a.out:
        open(a.out, "w").write(txt)
    if a.score_out:
        open(a.score_out, "w").write(json.dumps(dict(score=score(rows), rows=rows)))
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
