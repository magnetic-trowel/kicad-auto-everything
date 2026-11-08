# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What copper area price (kae.intent.route AREA_COST) the human layouts imply.

For every rail net of a routed board that carries DC current in kae's DC plan (kae.excite.dc, the
evaluator's plan, at its corners), compare the human track widths with the closed-form width the
neutral intent policy gives, w* = sqrt(k_R rho / (t a)) with k_R = 1 mW_eq/mW x cvar20(I^2), and with
IPC-2221 at 10 K and 20 K. The implied price is the a that makes w* equal the human width:
a = k_R rho / (t w^2). Nets with a pour are skipped (their copper is not a track width), as are nets under
0.1 A (the class width binds there, whatever a is).

    python tools/research/physics/area_cost_widths.py BOARD... --out rows.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback

RHO = 1.72e-5          # ohm mm (kae.intent.route.RHO_CU_OHM_MM)


def rows_of(path, n_corners=16, seed=0):
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.excite import dc as DC
    from kae.excite import models as M
    from kae.excite import sources as S
    from kae.excite.beliefs import corners
    from kae.excite.evaluate import ledger_for
    from kae.intent import objective as OB
    from kae.route.critical_physics import ipc2221_width
    b = load(path)
    brief = B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    P, _ = ledger_for(bd, brief, srcs, None)
    cval = {s.name: [{k[1]: v for k, v in c.items()} for c in corners(P[s.name].values(), n=n_corners, seed=seed)]
            for s in srcs}
    pl = DC.plan(b, brief, bd, P, srcs, None)
    if not pl.loads:
        return []
    ncp = n_corners + 3
    own = corners(pl.params, n=n_corners, seed=seed + 1) if pl.params else [{} for _ in range(ncp)]
    dcv = [dict(own[c], **{s.name: cval[s.name][c] for s in srcs if s.kind == "cell"}) for c in range(ncp)]
    inj = [DC.injections(pl, cv) for cv in dcv]
    net_of = {f"{fp.ref}.{p.number}": p.net for fp in b.footprints for p in fp.pads if p.net}
    poured = {z.net for z in b.zones if z.net}
    tracks = {}
    for t in b.tracks:
        if t.net:
            L = math.dist(t.start, t.end)
            tracks.setdefault(t.net, []).append((t.width, L, t.layer))
    out = []
    for net in sorted({n for n in net_of.values()} - set(bd.grounds)):
        # the current the net carries: what its sources inject into it (positive side), per corner
        I = [sum(a for q, a in j.items() if a > 0 and net_of.get(q) == net) for j in inj]
        Imax = max(I, default=0.0)
        if Imax < 0.1 or net not in tracks or net in poured:
            continue
        ws = sorted(tracks[net])
        tot = sum(L for _, L, _ in ws)
        if tot < 5.0:
            continue
        acc, p50, p90 = 0.0, None, None
        for w, L, _ in ws:
            acc += L
            if p50 is None and acc >= 0.5 * tot:
                p50 = w
            if p90 is None and acc >= 0.9 * tot:
                p90 = w
        kR = 1000.0 * OB._agg([x * x for x in I], "cvar20")    # mW_eq per ohm: 1 mW_eq/mW = 1000 mW_eq/W
        t = 0.035
        implied = kR * RHO / (t * p90 ** 2)
        out.append(dict(board=str(path), net=net, I_max=round(Imax, 3), I_rms_cvar=round(math.sqrt(kR / 1000), 3),
                        w_p50=p50, w_p90=p90, w_max=ws[-1][0], length_mm=round(tot, 1),
                        ipc10=round(ipc2221_width(Imax, 10.0, t), 3), ipc20=round(ipc2221_width(Imax, 20.0, t), 3),
                        w_star_005=round(math.sqrt(kR * RHO / (t * 0.05)), 3), implied_a=round(implied, 4),
                        role=(brief.get("nets") or {}).get(net, {}).get("role")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.out, "w") as f:
        for p in a.boards:
            try:
                for r in rows_of(p):
                    f.write(json.dumps(r) + "\n")
                f.flush()
            except Exception:                    # noqa: BLE001 - one board's failure is reported, not fatal
                print(f"{p}: {traceback.format_exc(limit=2)}", file=sys.stderr)


if __name__ == "__main__":
    main()
