# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validator prototype for the `physics:` block of pcb-intent/0.3.

Spec: docs/topics/physics/physics-ir.md ("Validation rules"). It proves the
grammar is coherent and is run on every ```yaml block of
docs/topics/physics/physics-ir-examples.md. Checks:

1. closed entity kinds, required fields, no unknown keys;
2. every quantity parses, and budget metrics have the right dimension
   (a small SI dimension algebra; expressions over symbol calls such as
   "0.85*V_abs(U3.VIN)" are dimension-checked, not evaluated);
3. ports are terminal pairs (non-empty `ref`);
4. loops are closed (first and last terminal on the same part) and name a return;
5. coupling mechanism is compatible with aggressor and victim kinds;
6. `alloc` percentages sum to <= 100 %;
7. couplings and antennas name a band.

Usage:
    python vo_ir_check.py FILE.yaml|FILE.md [...]
Exit status 1 if any error. Requires PyYAML (MIT).
"""
import ast
import re
import sys

import yaml

# ---------------------------------------------------------------- dimensions
# vector over (m, kg, s, A, K, log) ; log: 0 linear, 1 dB ratio, 2 dBm
DIM = {
    "1": (0, 0, 0, 0, 0, 0), "m": (1, 0, 0, 0, 0, 0), "s": (0, 0, 1, 0, 0, 0),
    "A": (0, 0, 0, 1, 0, 0), "K": (0, 0, 0, 0, 1, 0), "kg": (0, 1, 0, 0, 0, 0),
    "dB": (0, 0, 0, 0, 0, 1), "dBm": (0, 0, 0, 0, 0, 2),
}


def dmul(a, b, k=1):
    if a[5] or b[5]:
        raise ValueError("log units cannot be multiplied")
    return tuple(x + k * y for x, y in zip(a, b))


def dpow(a, p):
    return tuple(x * p for x in a)


V = (2, 1, -3, -1, 0, 0)
OHM = dmul(V, DIM["A"], -1)
UNITS = {  # base unit token -> (dimension, scale)
    "m": (DIM["m"], 1), "mil": (DIM["m"], 2.54e-5), "in": (DIM["m"], 0.0254),
    "s": (DIM["s"], 1), "A": (DIM["A"], 1), "V": (V, 1), "Vrms": (V, 1),
    "W": (dmul(V, DIM["A"]), 1), "ohm": (OHM, 1), "Ohm": (OHM, 1),
    "H": (dmul(OHM, DIM["s"]), 1), "F": (dmul(DIM["s"], OHM, -1), 1),
    "Hz": (dpow(DIM["s"], -1), 1), "bps": (dpow(DIM["s"], -1), 1),
    "K": (DIM["K"], 1), "degC": (DIM["K"], 1), "S": (dpow(OHM, -1), 1),
    "dB": (DIM["dB"], 1), "dBc": (DIM["dB"], 1), "dBm": (DIM["dBm"], 1),
    "ppm": (DIM["1"], 1e-6), "%": (DIM["1"], 0.01),
}
PREFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
          "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


def unit_token(tok):
    m = re.fullmatch(r"([A-Za-zµ%]+?)(\d*)", tok)
    if not m:
        raise ValueError("bad unit %r" % tok)
    name, exp = m.group(1), int(m.group(2) or 1)
    if name in UNITS:
        d = UNITS[name][0]
    elif name[0] in PREFIX and name[1:] in UNITS and UNITS[name[1:]][0][5] == 0:
        d = UNITS[name[1:]][0]
    else:
        raise ValueError("unknown unit %r" % tok)
    return dpow(d, exp) if exp != 1 else d


def unit_dim(u):
    u = u.replace(" ", "")
    if u in UNITS and UNITS[u][0][5]:
        return UNITS[u][0]  # dB, dBc, dBm stand alone
    parts = re.split(r"([*/])", u)
    d, op = DIM["1"], "*"
    for p in parts:
        if p in "*/":
            op = p
            continue
        d = dmul(d, unit_token(p), 1 if op == "*" else -1)
    return d


NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
QTY = re.compile(r"^\s*(%s)\s*([A-Za-zµ%%][\w/*µ%%]*)?\s*$" % NUM)

# symbol functions -> dimension of their result (arguments are opaque ids)
SYMBOLS = {
    "V_abs": V, "V_max": V, "V_min": V, "V_ref": V, "V_work": V, "LSB": V,
    "I_max": DIM["A"], "Iout": DIM["A"], "tr": DIM["s"], "UI": DIM["s"],
    "f_sw": dpow(DIM["s"], -1), "h": DIM["m"], "er": DIM["1"],
    "vp": dmul(DIM["m"], DIM["s"], -1), "didt": dmul(DIM["A"], DIM["s"], -1),
    "dvdt": dmul(V, DIM["s"], -1), "lambda_g": DIM["m"], "Coss": UNITS["F"][0],
    "ESL": UNITS["H"][0], "R_on": OHM, "hull": DIM["1"],
}


def expr_dim(text):
    """Dimension of an expression such as '0.85*V_abs(U3.VIN) - 2 V'."""
    s = re.sub(r"\b(%s)\(([^()]*)\)" % "|".join(SYMBOLS), r'\1("\2")', text)
    qs = []

    def lit(m):
        qs.append(m.group(0))
        return "__q%d" % (len(qs) - 1)

    s = re.sub(r"(?<![\w.])(%s)\s*([A-Za-zµ%%][\w/µ%%]*)(?![\w(\"])" % NUM, lit, s)
    tree = ast.parse(s, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return DIM["1"]
        if isinstance(n, ast.Name):
            if n.id == "pi":
                return DIM["1"]
            if n.id.startswith("__q"):
                return quantity_dim(qs[int(n.id[3:])])
            raise ValueError("unknown name %r" % n.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id == "sqrt":
                return dpow(ev(n.args[0]), 0.5)
            if n.func.id in SYMBOLS:
                return SYMBOLS[n.func.id]
            raise ValueError("unknown symbol %r" % n.func.id)
        if isinstance(n, ast.UnaryOp):
            return ev(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, (ast.Add, ast.Sub)):
                if a != b:
                    raise ValueError("adding unlike dimensions in %r" % text)
                return a
            if isinstance(n.op, ast.Mult):
                return dmul(a, b)
            if isinstance(n.op, ast.Div):
                return dmul(a, b, -1)
            if isinstance(n.op, ast.Pow) and isinstance(n.right, ast.Constant):
                return dpow(a, n.right.value)
        raise ValueError("unsupported expression %r" % text)

    return ev(tree)


def quantity_dim(v):
    """Dimension of a quantity, bound, interval or expression."""
    if isinstance(v, bool):
        raise ValueError("boolean is not a quantity")
    if isinstance(v, (int, float)):
        return DIM["1"]
    if isinstance(v, list):
        dims = {quantity_dim(x) for x in v}
        if len(dims) != 1:
            raise ValueError("interval with mixed dimensions %r" % v)
        return dims.pop()
    s = str(v).strip()
    s = re.sub(r"^(<=|>=|==|<|>)\s*", "", s)
    if s.startswith("[") and s.endswith("]"):
        return quantity_dim([x.strip() for x in s[1:-1].split(",")])
    m = QTY.match(s)
    if m:
        return unit_dim(m.group(2)) if m.group(2) else DIM["1"]
    return expr_dim(s)


# ---------------------------------------------------------------- schema
COMMON = {"id", "kind", "intent", "budget", "why", "src"}
KINDS = {  # kind -> (required, optional)
    "port": ({"sig", "ref"}, {"use", "fixed", "z", "external"}),
    "node": ({"net"}, {"excite", "sense", "z_src"}),
    "loop": ({"path", "return"}, {"class", "excite"}),
    "channel": ({"from", "to"}, {"through", "z", "ref", "transitions"}),
    "reference": ({"net", "layers"}, {"region", "serves", "bands"}),
    "body": (set(), {"net", "layer", "shape"}),
    "cavity": ({"between"}, {"outline"}),
    "discontinuity": ({"in"}, {"type", "bridge"}),
    "antenna": ({"halves", "band"}, {"drive"}),
    "coupling": ({"aggr", "victim", "mech", "band"}, {"shared"}),
    "exclusion": ({"of"}, {"region", "body", "band"}),
    "shield": ({"protects"}, {"type", "pitch"}),
    "heat_path": ({"source", "P", "sink"}, {"via"}),
    "barrier": ({"between", "V_work"}, {"std", "pd", "mg"}),
    "cell": ({"template", "parts"}, set()),
    "feed": ({"from", "to"}, {"I"}),
}
METRIC = {  # budget metric -> dimension
    "L_loop": "H", "L_mount": "H", "L_cs": "H", "M": "H", "C": "F", "C_m": "F",
    "C_across": "F", "R": "ohm", "R_shared": "ohm", "V_pk": "V", "V_cm": "V", "V": "V",
    "V_noise": "V", "I": "A", "I_cm": "A", "I_through": "A", "IL": "dB", "S11": "dB",
    "skew": "s", "delay": "s", "Z": "ohm", "dT": "K", "Tj": "K", "creepage": "m",
    "clearance": "m", "dist": "m", "J_frac": "%", "P": "dBm", "f_ring": "Hz",
    "df": "ppm", "area": "m2", "E": "V/m",
}
WAVES = {"trapezoid": ["f0", "tr"], "data": ["rate", "tr"], "sine": ["f0"],
         "edge": ["tr"], "dc": [], "sim": ["file"]}
WAVE_DIM = {"V": "V", "I": "A", "f0": "Hz", "tr": "s", "rate": "bps", "duty": "%"}
BUILTIN_BANDS = {"dc", "esd"}
MECH = {  # mechanism -> (allowed aggressor kinds, allowed victim kinds)
    "capacitive": ({"node", "port"}, {"node", "port", "channel", "loop"}),
    "inductive": ({"loop", "channel", "feed"}, {"loop", "channel", "port", "node"}),
    "common_impedance": ({"loop", "feed", "channel"}, {"port", "node", "loop", "channel", "feed"}),
    "radiated": (None, None), "conducted": (None, None),
    "thermal": ({"heat_path", "feed", "cell"}, {"node", "port", "loop"}),
    "leakage": ({"node", "feed"}, {"node", "port"}),
}


class Checker:
    def __init__(self, label):
        self.label, self.errors, self.warnings = label, [], []

    def err(self, eid, msg):
        self.errors.append("%s: %s: %s" % (self.label, eid, msg))

    def warn(self, eid, msg):
        self.warnings.append("%s: %s: %s" % (self.label, eid, msg))

    def dim_is(self, eid, what, value, unit):
        try:
            d = quantity_dim(value)
        except (ValueError, SyntaxError) as e:
            self.err(eid, "%s %r does not parse: %s" % (what, value, e))
            return
        if d != unit_dim(unit):
            self.err(eid, "%s %r has the wrong dimension (want %s)" % (what, value, unit))

    def run(self, doc):
        bands = set((doc.get("bands") or {}).keys()) | BUILTIN_BANDS
        for name, iv in (doc.get("bands") or {}).items():
            self.dim_is("bands." + name, "band edge", iv, "Hz")
        ents = doc.get("physics") or []
        kinds = {e.get("id"): e.get("kind") for e in ents if isinstance(e, dict)}
        for e in ents:
            self.entity(e, kinds, bands)
        for op in doc.get("ops") or []:
            if not {"op", "target"} <= set(op):
                self.err("ops", "operator needs op and target: %r" % op)
        return self

    def band_ok(self, eid, band, bands):
        items = band if isinstance(band, list) else [band]
        if items and all(isinstance(x, str) and re.match(NUM, x.strip()) for x in items):
            self.dim_is(eid, "band", items, "Hz")
            return
        for b in items:
            if b not in bands:
                self.err(eid, "unknown band %r" % b)

    def entity(self, e, kinds, bands):
        eid, kind = e.get("id", "?"), e.get("kind")
        if kind not in KINDS:
            self.err(eid, "unknown kind %r" % kind)
            return
        req, opt = KINDS[kind]
        for k in req - set(e):
            self.err(eid, "missing required field %r" % k)
        for k in set(e) - req - opt - COMMON:
            self.err(eid, "unknown field %r" % k)
        if kind == "port" and not e.get("ref"):
            self.err(eid, "port has no reference terminal (half-port)")
        if kind == "loop":
            path = e.get("path") or []
            part = lambda t: str(t).split(".")[0]
            if len(path) < 3 or part(path[0]) != part(path[-1]):
                self.err(eid, "loop path is not closed: %r" % path)
        for f in ("excite",):
            if f in e:
                self.excite(eid, e[f])
        if "sense" in e:
            s = e["sense"]
            if "threshold" not in s or "band" not in s:
                self.err(eid, "sense needs threshold and band")
            else:
                self.band_ok(eid, s["band"], bands)
        if "band" in e:
            self.band_ok(eid, e["band"], bands)
        if kind == "coupling":
            self.coupling(eid, e, kinds)
        if kind == "heat_path":
            self.dim_is(eid, "P", e.get("P"), "W")
        if kind == "barrier":
            self.dim_is(eid, "V_work", e.get("V_work"), "V")
        if kind == "feed" and "I" in e:
            self.dim_is(eid, "I", e["I"], "A")
        if kind == "shield" and "pitch" in e:
            self.dim_is(eid, "pitch", e["pitch"], "m")
        if "budget" in e:
            self.budget(eid, e["budget"], bands)

    def excite(self, eid, x):
        w = x.get("wave")
        if w not in WAVES:
            self.err(eid, "unknown wave %r" % w)
            return
        for k in WAVES[w]:
            if k not in x:
                self.err(eid, "wave %s needs %r" % (w, k))
        if w not in ("data", "sim") and not ({"V", "I"} & set(x)):
            self.err(eid, "excitation needs V or I")
        for k, v in x.items():
            if k in WAVE_DIM:
                self.dim_is(eid, "excite." + k, v, WAVE_DIM[k])

    def coupling(self, eid, e, kinds):
        mech = e.get("mech")
        if mech not in MECH:
            self.err(eid, "unknown mechanism %r" % mech)
            return
        if mech == "common_impedance" and "shared" not in e:
            self.err(eid, "common_impedance coupling must name the shared conductor")
        ok_a, ok_v = MECH[mech]
        for role, ok in (("aggr", ok_a), ("victim", ok_v)):
            k = kinds.get(e.get(role))
            if k is None:
                self.warn(eid, "%s %r is not defined in this block" % (role, e.get(role)))
            elif ok is not None and k not in ok:
                self.err(eid, "%s mechanism cannot act with %s of kind %s" % (mech, role, k))

    def budget(self, eid, b, bands):
        for k, v in b.items():
            if k == "band":
                self.band_ok(eid, v, bands)
            elif k == "alloc":
                tot = 0.0
                for part, pct in v.items():
                    m = re.fullmatch(r"\s*(%s)\s*%%\s*" % NUM, str(pct))
                    if not m:
                        self.err(eid, "alloc %s=%r is not a percentage" % (part, pct))
                    else:
                        tot += float(m.group(1))
                if tot > 100 + 1e-9:
                    self.err(eid, "alloc sums to %.0f %% > 100 %%" % tot)
            elif k in ("basis", "model"):
                continue
            elif k.split("@")[0] in METRIC:
                self.dim_is(eid, "budget " + k, v, METRIC[k.split("@")[0]])
            else:
                self.err(eid, "unknown budget metric %r" % k)


def blocks(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith(".md"):
        for i, m in enumerate(re.finditer(r"```yaml\n(.*?)```", text, re.S)):
            yield "%s#yaml%d" % (path, i + 1), yaml.safe_load(m.group(1))
    else:
        yield path, yaml.safe_load(text)


if __name__ == "__main__":
    n_err = 0
    for p in sys.argv[1:]:
        for label, doc in blocks(p):
            if not isinstance(doc, dict) or "physics" not in doc:
                continue
            c = Checker(label).run(doc)
            ents = doc["physics"]
            print("%s: %d entities, %d budgets, %d errors, %d warnings"
                  % (label, len(ents), sum(len(e.get("budget", {})) for e in ents),
                     len(c.errors), len(c.warnings)))
            for line in c.errors:
                print("  ERROR " + line)
            for line in c.warnings:
                print("  warn  " + line)
            n_err += len(c.errors)
    sys.exit(1 if n_err else 0)
