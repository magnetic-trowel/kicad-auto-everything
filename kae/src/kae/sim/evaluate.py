# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulate each test of a testbench on the ideal circuit and on the routed copper, and judge it.

Per test and per corner of its `*@range` parameters (all 2^k corners for k <= 3, else all-low and
all-high), plus the typical point:

- ideal deck: every pin of a net on one node; the board's passives touching the test's nets;
- routed deck: the test's nets replaced by their extracted copper (extract.py).

A requirement passes when it holds at every corner, fails when it holds at none, and is marginal
otherwise. Its ideal verdict says whether the circuit itself passes; `layout` is routed minus ideal at
the typical point. A test with `*@unknown` reasons reports values with status "unknown"; one whose
referenced pins sit on separate copper islands is "incomplete"; a measurement that does not come back
is "error". Capability: rail_dc reports the load scale at which the first pin reaches its bound (DC is
linear in the load), i2c the fastest mode whose rise-time limit holds at every corner, pair the skew.
"""
from __future__ import annotations

import itertools
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import ngspice
from .autotb import I2C_MODES
from .extract import GROUND, extract
from .names import Namer
from .testbench import TOKEN, fmt, num

_RAW_NODE = re.compile(r"^[a-z][a-z0-9_]*$")


class Context:
    def __init__(self, board, brief, design, rb=None, workdir="kae-sim"):
        self.b, self.brief, self.design, self.rb = board, brief, design, rb
        self.workdir = Path(workdir)
        self.gnd = {n for n, r in (brief.get("nets") or {}).items() if (r or {}).get("role") == "ground"}
        self.refs = {f.ref: {p.number for p in f.pads} for f in board.footprints}
        self.nets = set(design.pin_net.values())
        self._ext = {}

    def network(self, nets, profile="signal"):
        key = (tuple(sorted(nets)), profile)
        if key not in self._ext:
            self._ext[key] = extract(self.rb, list(key[0]), profile=profile)
        return self._ext[key]


def corners(params):
    ps = list(params.values())
    typ = {p.name: p.typ for p in ps}
    if not ps:
        return [("typ", typ)]
    out = [("typ", typ)]
    if len(ps) <= 3:
        for combo in itertools.product(*[(("lo", p.lo), ("hi", p.hi)) for p in ps]):
            out.append((",".join(f"{p.name}={c[0]}" for p, c in zip(ps, combo)), {p.name: c[1] for p, c in zip(ps, combo)}))
    else:
        out.append(("all=lo", {p.name: p.lo for p in ps}))
        out.append(("all=hi", {p.name: p.hi for p in ps}))
    return out


def _pin(token, ctx):
    if "." in token:
        ref, pad = token.rsplit(".", 1)
        if ref in ctx.refs and pad in ctx.refs[ref]:
            return f"pin:{ref}.{pad}"
    return None


def build_deck(test, mode, values, ctx, net=None):
    """(deck text, Namer, referenced pin keys) for one test, mode 'ideal' or 'routed'."""
    nm = Namer()
    used_pins = set()
    extracted = set(test.nets) if mode == "routed" else set()
    if mode == "routed":
        net = net or ctx.network(test.nets, test.extract)

    def pin_node(key):
        n = ctx.design.pin_net.get(key)
        if n is None:
            return nm.node(key)                       # a pad without a net: its own node
        used_pins.add(key)
        if n in extracted:
            k = net.node_of(key)
            return GROUND if k == GROUND else nm.node(k)
        return GROUND if n in ctx.gnd else nm.node(f"net:{n}")

    def tok(m):
        t = m.group(1)
        k = _pin(t, ctx)
        if k is not None:
            return pin_node(k)
        if t in ctx.gnd:
            return GROUND
        if t in extracted:
            raise ValueError(f"<{t}> names an extracted net; name a pin of it instead")
        if t not in ctx.nets:
            raise ValueError(f"<{t}> is neither a pin nor a net of this board")
        return nm.node(f"net:{t}")

    out = [f"* kae.sim {test.id} ({mode})", ".option rshunt=1e12 method=gear"]
    # board passives whose every terminal is in the test's scope: its nets, ground, or a net the
    # testbench names (a passive into an undriven net would leave that node floating behind its ESL)
    scope = set(test.nets) | ctx.gnd
    for ln in test.lines:
        for m in TOKEN.finditer(ln):
            k = _pin(m.group(1), ctx)
            scope.add(ctx.design.pin_net.get(k) if k else m.group(1))
    excl = set(test.exclude)
    for p in ctx.design.touching(test.nets):
        if p.ref in excl or not all(ctx.design.pin_net.get(k) in scope for k in p.pins):
            continue
        a, b = (pin_node(k) for k in p.pins)
        if p.kind == "R":
            out.append(f"{nm.element('R', p.ref)} {a} {b} {fmt(p.value)}")
        elif p.kind == "C":
            x, y = nm.node(f"x:{p.ref}.c"), nm.node(f"x:{p.ref}.r")
            out.append(f"{nm.element('C', p.ref)} {a} {x} {fmt(p.value)}")
            out.append(f"{nm.element('R', p.ref + '.esr')} {x} {y} {fmt(p.esr)}")
            out.append(f"{nm.element('L', p.ref + '.esl')} {y} {b} {fmt(p.esl)}")
        else:
            x = nm.node(f"x:{p.ref}.l")
            out.append(f"{nm.element('L', p.ref)} {a} {x} {fmt(p.value)}")
            out.append(f"{nm.element('R', p.ref + '.dcr')} {x} {b} {fmt(max(p.esr, 1e-6))}")
    # routed copper
    stats = {}
    if mode == "routed":
        stats = net.stats
        lname = {}
        for e in net.elements:
            a = GROUND if e.a == GROUND else nm.node(e.a)
            b = GROUND if e.b == GROUND else nm.node(e.b)
            if e.kind == "K":
                continue
            name = nm.element(e.kind, e.key)
            if e.kind == "L":
                lname[e.key] = name
            out.append(f"{name} {a} {b} {e.value:.6g}")
        for e in net.elements:
            if e.kind == "K" and e.l1 in lname and e.l2 in lname:
                out.append(f"{nm.element('K', e.key)} {lname[e.l1]} {lname[e.l2]} {e.value:.4f}")
    # the testbench, with corner values
    for ln in test.lines:
        m = re.match(r"(\s*\.param\s+)(\w+)(\s*=\s*)(\S+)(.*)", ln, re.I)
        if m and m.group(2) in values:
            ln = f"{m.group(1)}{m.group(2)}{m.group(3)}{fmt(values[m.group(2)])}{m.group(5)}"
        ln = TOKEN.sub(tok, ln)
        out.append(ln)
    out.append(".end")
    return "\n".join(out) + "\n", nm, used_pins, stats


def _status(vals, op, bound):
    ok = [_holds(v, op, bound) for v in vals]
    if all(ok):
        return "pass"
    if not any(ok):
        return "fail"
    return "marginal"


def _holds(v, op, b):
    return {"<=": v <= b, ">=": v >= b, "<": v < b, ">": v > b}[op]


def evaluate(tests, ctx, jobs=8, timeout=300, only=None):
    t0 = time.time()
    tests = [t for t in tests if not only or t.id in only]
    plan = []
    nets = {}
    split_of = {}
    for t in tests:
        if t.unknown and not t.lines:
            continue
        for mode in ("ideal", "routed"):
            if mode == "routed":
                if ctx.rb is None:
                    continue
                net = nets[t.id] = ctx.network(t.nets, t.extract)
                # pins the test uses that sit on separate copper islands: not simulated (a load on an
                # island has no return but the 1e12 ohm leak; the solver would chase 1e11 V)
                try:
                    _, _, used, _ = build_deck(t, mode, {p.name: p.typ for p in t.params.values()}, ctx, net)
                except ValueError:
                    used = set()
                split = []
                for n in t.nets:
                    groups = [g for g in net.groups.get(n, []) if any(p in used for p in g)]
                    if len(groups) > 1:
                        split.append(dict(net=n, islands=[[p for p in g if p in used] for g in groups]))
                if split:
                    split_of[t.id] = split
                    continue
            for cname, vals in corners(t.params):
                plan.append((t, mode, cname, vals))

    def one(job):
        t, mode, cname, vals = job
        try:
            deck, nm, used, stats = build_deck(t, mode, vals, ctx, nets.get(t.id))
        except ValueError as e:
            return job, None, str(e), set()
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{t.id}_{mode}_{cname}")[:120]
        r = ngspice.run(deck, ctx.workdir / safe, t.meas_names(), timeout=timeout)
        return job, r, None, used

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for job, r, err, used in ex.map(one, plan):
            t, mode, cname, _ = job
            results.setdefault(t.id, {}).setdefault(mode, {})[cname] = (r, err, used)

    report = []
    for t in tests:
        rec = dict(id=t.id, kind=t.kind, nets=t.nets, notes=t.notes, unknown=t.unknown,
                   params={p.name: dict(typ=p.typ, lo=p.lo, hi=p.hi, src=p.src) for p in t.params.values()},
                   requirements=[], info={}, problems=[])
        res = results.get(t.id, {})
        status = "unknown" if t.unknown else None
        # copper islands among the pins this test uses (routed runs skipped)
        if t.id in nets:
            if t.id in split_of:
                rec["incomplete"] = split_of[t.id]
                status = status or "incomplete"
            rec["extraction"] = nets[t.id].stats
        for mode, byc in res.items():
            for cname, (r, err, _) in byc.items():
                if err:
                    rec["problems"].append(f"{mode} {cname}: {err}")
                elif r.failed or r.problems:
                    rec["problems"].append(f"{mode} {cname}: failed {r.failed} " + "; ".join(r.problems[:3]))

        def vals(mode, m):
            byc = res.get(mode, {})
            v = {c: r.meas.get(m.lower()) for c, (r, err, _) in byc.items() if r is not None}
            return v

        worst = []
        for q in t.requires:
            iv, rv = vals("ideal", q.meas), vals("routed", q.meas)
            row = dict(meas=q.meas, op=q.op, bound=q.bound, src=q.src)
            for mode, v in (("ideal", iv), ("routed", rv)):
                got = [x for x in v.values() if x is not None]
                if not v:
                    continue
                if len(got) < len(v):
                    row[f"{mode}_status"] = "error"
                else:
                    row[f"{mode}_status"] = _status(got, q.op, q.bound)
                row[mode] = dict(typ=v.get("typ"), lo=min(got) if got else None, hi=max(got) if got else None)
            if rv.get("typ") is not None and iv.get("typ") is not None:
                row["layout"] = rv["typ"] - iv["typ"]
            row["status"] = row.get("routed_status") or row.get("ideal_status") or "error"
            rec["requirements"].append(row)
            worst.append(row["status"])
        for m in t.info:
            iv, rv = vals("ideal", m), vals("routed", m)
            rec["info"][m] = dict(ideal=iv, routed=rv)
        if rec.get("incomplete"):
            # a pin on a separate copper island: its routed values are not physical
            for row in rec["requirements"]:
                if "routed_status" in row:
                    row["routed_status"] = row["status"] = "incomplete"
            rec["capability"] = None
        else:
            rec["capability"] = _capability(t, rec)
        if status is None:
            order = ["error", "fail", "marginal", "pass"]
            status = next((s for s in order if s in worst), "info")
        rec["status"] = status
        report.append(rec)
    summary = {}
    for r in report:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return dict(schema="kae.sim.evaluation/1", seconds=round(time.time() - t0, 1), simulations=len(plan),
                summary=summary, tests=report)


def _capability(t, rec):
    if t.kind == "rail_dc" and list(t.params) == ["SCALE"]:
        # DC with current loads is linear in SCALE: the line through the low and high corners
        p = t.params["SCALE"]
        scale = []
        for q in rec["requirements"]:
            r = q.get("routed") or {}
            if q["op"] != ">=" or r.get("lo") is None or r.get("hi") is None:
                continue
            v_lo_load, v_hi_load = r["hi"], r["lo"]          # more load, lower voltage
            slope = (v_lo_load - v_hi_load) / (p.hi - p.lo)
            if slope > 1e-15:
                scale.append((p.lo + (v_lo_load - q["bound"]) / slope, q["meas"]))
        if scale:
            s, m = min(scale)
            return dict(load_scale_at_limit=round(s, 3), limiting=m,
                        note="multiple of the IC current prior at which the first pin reaches its bound (DC is linear)")
    probe = next((ln.split() for ln in t.lines if ln.split()[:2] == ["Rpu", "vpu"]), None)
    if t.kind == "i2c" and probe and not t.requires:
        # 30-70% rise of an RC is 0.8473 R C: bus capacitance from the probe pull-up, then the largest
        # pull-up per mode (worst corner of the pin capacitance)
        rp = num(probe[3])
        out = {}
        for mode in ("ideal", "routed"):
            tr = [x for d in rec["info"].values() for x in d[mode].values() if x is not None]
            if tr:
                cb = max(tr) / (0.8473 * rp)
                out[f"{mode}_bus_capacitance_F"] = cb
                out[f"{mode}_max_pullup_ohm"] = {name: lim / (0.8473 * cb) for name, lim in I2C_MODES}
        return out or None
    if t.kind == "i2c":
        worst = max((q.get("routed", {}).get("hi") or q.get("ideal", {}).get("hi") or math.inf) for q in rec["requirements"]) \
            if rec["requirements"] else math.inf
        best = None
        for name, lim in I2C_MODES:
            if worst <= lim:
                best = name
        return dict(fastest_mode=best, worst_rise_s=None if worst == math.inf else worst)
    if t.kind == "pair":
        out = {}
        pre = {n: f"td{k}_" for k, n in enumerate(t.nets[:2])}
        for mode in ("ideal", "routed"):
            per = {}
            for m, d in rec["info"].items():
                v = [x for x in d[mode].values() if x is not None]
                net = next((n for n, pf in pre.items() if m.startswith(pf)), None)
                if v and net:
                    per.setdefault(net, []).append(max(v))
            if len(per) == 2:
                a, b = (max(v) for v in per.values())
                out[f"{mode}_delay_s"] = max(a, b)
                out[f"{mode}_skew_s"] = abs(a - b)
        return out or None
    return None


def questions(report):
    """What to research, ranked: marginal verdicts (a prior's range spans the bound), unknowns, then
    verdicts that rest only on priors. Each lists the inputs to replace with cited facts."""
    out = []
    for t in report.get("tests", []):
        priors = [n for n, p in (t.get("params") or {}).items() if str(p.get("src", "")).startswith("prior")]
        req_src = sorted({q["src"] for q in t.get("requirements", []) if str(q.get("src", "")).startswith("prior")})
        if t["status"] == "marginal":
            out.append(dict(rank=1, test=t["id"], why="verdict flips within the prior ranges", inputs=priors,
                            bounds_from_priors=req_src))
        elif t["status"] == "unknown":
            out.append(dict(rank=2, test=t["id"], why="; ".join(t.get("unknown") or []), inputs=priors))
        elif t["status"] in ("pass", "fail") and (priors or req_src):
            out.append(dict(rank=3, test=t["id"], why=f"{t['status']} on priors only", inputs=priors,
                            bounds_from_priors=req_src))
    return sorted(out, key=lambda q: (q["rank"], q["test"]))


def write(report, path):
    Path(path).write_text(json.dumps(report, indent=1, default=lambda o: None))
