# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The critical router's module stage under --physics-fidelity fast, multi and exact
(kae.physics.exact; docs/topics/physics/exact-physics-in-kae.md section 4).

For one placed board (a route task's input), every loop module (cells, power paths, decaps,
protection chains) is routed by critical_modules.route_module once per fidelity, from the
same Session setup (brief, DSN info and place terms shared). Per module and fidelity:
seconds, PEEC calls, multi's decisions and changed choices, the vias chosen, and the fast
(closed-form) and exact (PEEC) values of the copper it ended with. Per evaluation: the
closed-form and PEEC quote times on the fast run's final copper (cold and warm block cache).

    kae/.venv/bin/python tools/research/physics/ex_fidelity.py BOARD.kicad_pcb [--k 4]
        [--modes fast,multi,exact] [--out kae-work-v3/physics/exact-fidelity/NAME.json]

Needs KiCad's Python for the DSN export (as the critical router). One core; a board of a few
dozen modules takes 1-10 minutes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kae" / "src"))

from kae.physics import exact as EX  # noqa: E402

KINDS = ("cell", "path", "decap", "chain")


def _vias(m):
    return sorted((k, round(x, 3), round(y, 3)) for k, vs in m.vias.items() for (x, y, *_r) in vs)


def run_mode(path, mode, k, shared, log):
    from kae.board.kicad_file import load
    from kae.route.critical import Session
    from kae.route.critical_modules import modules_from_brief, route_module
    from kae.route.critical_rails import rail_currents
    rows = {}
    with EX.scope(mode, k=k):
        EX.clear_cache()
        t0 = time.process_time()
        s = Session(path, brief=shared["brief"], info=shared["info"], board=load(path), terms=shared["terms"],
                    opts=dict(kinds=KINDS, rails="none"), log=lambda *a: None)
        try:
            s.ctx.rail_I = rail_currents(s.ctx)
        except Exception:  # noqa: BLE001
            s.ctx.rail_I = {}
        setup = time.process_time() - t0
        mods = modules_from_brief(s.brief, KINDS)
        for m in mods:
            EX.stats(reset=True)
            t1 = time.process_time()
            route_module(s.ctx, m)
            dt = time.process_time() - t1
            st = EX.stats()
            vf, ve = EX.module_values(s.ctx, m)
            rows[m.id] = dict(kind=m.kind, status=m.status, seconds=round(dt, 3), exact_calls=st["exact_calls"],
                              exact_s=round(st["exact_s"], 3), decisions=st["decisions"], changed=st["changed"],
                              failures=st["failures"], what=st["what"], gain=st["gain"],
                              vias=_vias(m), fast=vf, exact=ve, alloc=(m.physics or {}).get("alloc"))
            log(f"  {mode:5s} {m.id[:48]:48s} {m.status:8s} {dt:6.2f}s fast {vf} exact {ve} "
                f"dec {st['decisions']} chg {st['changed']} peec {st['exact_calls']}")
    return dict(setup_s=round(setup, 2), modules=rows), s, mods


def timing(sess, mods, n=3):
    """Closed-form and PEEC quote CPU times on each loop module's final copper."""
    from kae.route.critical_modules import quote
    out = {}
    for m in mods:
        if m.kind not in ("cell", "path", "decap") or m.status not in ("routed", "partial"):
            continue
        with EX.scope("fast"):
            t0 = time.process_time()
            for _ in range(n):
                quote(sess.ctx, m, store=False)
            tf = (time.process_time() - t0) / n
        EX.clear_cache()
        with EX.exact_now():
            t0 = time.process_time()
            quote(sess.ctx, m, store=False)
            cold = time.process_time() - t0
            t0 = time.process_time()
            quote(sess.ctx, m, store=False)
            warm = time.process_time() - t0
        st = EX.stats(reset=True)
        out[m.id] = dict(kind=m.kind, fast_ms=round(1e3 * tf, 3), exact_cold_ms=round(1e3 * cold, 2),
                         exact_warm_ms=round(1e3 * warm, 2), loops=st["exact_calls"] // 2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--modes", default="fast,multi,exact")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    path = Path(a.board).resolve()
    name = path.parent.parent.parent.name if path.parent.name == "input" else path.stem
    out = Path(a.out) if a.out else ROOT / "kae-work-v3" / "physics" / "exact-fidelity" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        print(msg, flush=True)
    import tempfile

    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.route.critical_modules import place_terms
    t0 = time.process_time()
    b = load(path)
    brief = build(b)
    with tempfile.TemporaryDirectory(prefix="kae-exf-") as d:
        info = pcbnew_io.export_dsn(path, Path(d) / "board.dsn")
    terms = place_terms(b, brief)
    shared = dict(brief=brief, info=info, terms=terms)
    rep = dict(board=name, k=a.k, prep_s=round(time.process_time() - t0, 2), modes={})
    log(f"{name}: prep {rep['prep_s']} s")
    sess = None
    for mode in a.modes.split(","):
        r, s, mods = run_mode(path, mode, a.k, shared, log)
        rep["modes"][mode] = r
        if mode == "fast":
            sess, fmods = s, mods
    if sess is not None:
        rep["timing"] = timing(sess, fmods)
    out.write_text(json.dumps(rep, indent=1, default=str))
    log(f"wrote {out}")


if __name__ == "__main__":
    main()
