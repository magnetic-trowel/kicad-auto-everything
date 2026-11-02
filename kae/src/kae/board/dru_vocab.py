# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The .kicad_dru vocabulary of one KiCad version, generated from KiCad's source and
verified against a running KiCad; kae.board.dru_check reads it.

    python -m kae.board.dru_vocab fetch REF [--dir D]      sparse clone of KiCad at a tag/branch
    python -m kae.board.dru_vocab sync SRC LABEL [--verify] write dru_vocab/<LABEL>.json
    python -m kae.board.dru_vocab diff SRC LABEL            what changed vs the committed file

Sources read (relative to a KiCad checkout):
    pcbnew/drc/drc_rule_parser.cpp   constraint types, deprecated aliases, disallow items,
                                     zone connections, severities, layer keywords
    pcbnew/pcbexpr_functions.cpp     condition functions (RegisterFunc), deprecated ones
    pcbnew/**, common/** *.cpp       properties (PROPERTY<...>( _HKI( "Name" ) ))
    pcbnew/pcbexpr_evaluator.cpp     fast-path properties, accepted-units message

--verify asks the installed kicad-cli about every function and property (one probe each,
kae.board.dru_check.kicad_check) and keeps only those KiCad accepts; candidates it rejects
are recorded under "rejected". Run `sync ... --verify` when KiCad is bumped; a failing
`diff` or the drift tests in kae/tests/test_board_dru_check.py say it is due.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "dru_vocab"
MIRROR = "https://github.com/KiCad/kicad-source-mirror.git"


def _read(src: Path, rel: str) -> str:
    return (src / rel).read_text(encoding="utf-8", errors="ignore")


def _cases(block: str) -> list[str]:
    return re.findall(r"case\s+T_(\w+)\s*:", block)


def extract(src: Path) -> dict:
    """Vocabulary from a KiCad source checkout (no KiCad needed)."""
    src = Path(src)
    p = _read(src, "pcbnew/drc/drc_rule_parser.cpp")
    constraints = re.findall(r"case\s+T_(\w+)\s*:\s*c\.m_Type\s*=", p)
    deprecated = dict(re.findall(r'reportDeprecation\(\s*wxT\(\s*"(\w+)"\s*\)\s*,\s*wxT\(\s*"(\w+)"\s*\)', p))
    dis = p[p.index("DISALLOW_CONSTRAINT )"):]
    disallow = [t for t in _cases(dis[:dis.index("T_EOF")]) if t != "EOF"]
    zc = p[p.index("c.m_ZoneConnection") - 400:]
    zone = [t for t in _cases(zc[:zc.index("T_EOF")]) if t != "EOF"]
    sev = re.findall(r"case\s+T_(\w+)\s*:\s*retVal\s*=\s*RPT_SEVERITY", p)
    layers = re.findall(r"token\s*==\s*T_(outer|inner)", p)
    f = _read(src, "pcbnew/pcbexpr_functions.cpp")
    funcs, dep_funcs, sigs = [], [], {}
    for name, args, dep in re.findall(r'RegisterFunc\(\s*wxT\(\s*"(\w+)\(([^)]*)\)(\s+DEPRECATED)?"', f):
        (dep_funcs if dep else funcs).append(name)
        sigs[name] = f"({args})"
    props = set()
    for path in [*src.glob("pcbnew/**/*.cpp"), *src.glob("common/**/*.cpp")]:
        s = path.read_text(encoding="utf-8", errors="ignore")
        if "AddProperty" in s:
            props.update(re.findall(r'PROPERTY(?:_ENUM)?\s*<[^;]*?>\s*\(\s*(?:_HKI|wxT)\(\s*"([^"]+)"', s, re.S))
    e = _read(src, "pcbnew/pcbexpr_evaluator.cpp")
    fast = re.findall(r'aField\.CmpNoCase\(\s*wxT\(\s*"(\w+)"\s*\)\s*\)', e)
    units = re.search(r'return _\(\s*"must be ([^"]+)"\s*\)', e)
    return {
        "constraints": sorted(set(constraints)),
        "deprecated_constraints": dict(sorted(deprecated.items())),
        "disallow_items": sorted(set(disallow)),
        "zone_connections": sorted(set(zone)),
        "severities": sorted(set(sev)),
        "layer_keywords": sorted(set(layers)),
        "functions": sorted(set(funcs)),
        "deprecated_functions": sorted(set(dep_funcs)),
        "function_args": dict(sorted(sigs.items())),
        "properties": sorted({x.replace(" ", "_") for x in props} | set(fast)),
        "units_message": units.group(1) if units else "",
    }


def _src_ref(src: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(src), "describe", "--tags", "--always"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except OSError:
        return ""


def verify(vocab: dict, cli: list, workers: int = 12) -> dict:
    """Keep the functions and properties the installed KiCad accepts."""
    from kae.board.dru_check import kicad_check
    def probe(cond):
        return kicad_check(f'(version 1)\n(rule "p" (condition "{cond}") (constraint clearance (min 1mm)))',
                           cli, workers=1).accepted
    out = dict(vocab)
    sig = vocab.get("function_args", {})
    tests = {
        "functions": [f"{'AB' if n == 'isCoupledDiffPair' else 'A'}.{n}{sig.get(n, '()')}" for n in vocab["functions"]],
        "deprecated_functions": [f"A.{n}{sig.get(n, '()')}" for n in vocab["deprecated_functions"]],
        "properties": [f"A.{n} == 'x'" for n in vocab["properties"]],
    }
    out["rejected"] = {}
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for key, conds in tests.items():
            ok = list(ex.map(probe, conds))
            out[key] = [n for n, good in zip(vocab[key], ok) if good]
            out["rejected"][key] = [n for n, good in zip(vocab[key], ok) if not good]
    from kae.board.dru_check import kicad_version
    out["verified_with"] = kicad_version(cli)
    return out


def load(label: str) -> dict:
    return json.loads((HERE / f"{label}.json").read_text())


def labels() -> list[str]:
    return sorted(p.stem for p in HERE.glob("*.json"))


def diff(old: dict, new: dict) -> list[str]:
    lines = []
    for k in sorted(set(old) | set(new)):
        if k in ("source_ref", "verified_with", "rejected"):
            continue
        a, b = old.get(k), new.get(k)
        if isinstance(a, list) or isinstance(b, list):
            a, b = set(a or []), set(b or [])
            if b - a:
                lines.append(f"{k}: + {', '.join(sorted(b - a))}")
            if a - b:
                lines.append(f"{k}: - {', '.join(sorted(a - b))}")
        elif isinstance(a, dict) or isinstance(b, dict):
            a, b = a or {}, b or {}
            for key in sorted(set(a) | set(b)):
                if a.get(key) != b.get(key):
                    lines.append(f"{k}.{key}: {a.get(key)!r} -> {b.get(key)!r}")
        elif a != b:
            lines.append(f"{k}: {a!r} -> {b!r}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m kae.board.dru_vocab", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="sparse clone of KiCad's source (pcbnew, common) at REF")
    f.add_argument("ref", help="tag or branch, e.g. 10.0.7 or master")
    f.add_argument("--dir", help="target directory (default: ./kicad-src-REF)")
    s = sub.add_parser("sync", help="write dru_vocab/LABEL.json from a KiCad checkout")
    s.add_argument("src")
    s.add_argument("label", help="e.g. 10.0 or master")
    s.add_argument("--verify", action="store_true", help="probe functions and properties with kicad-cli")
    d = sub.add_parser("diff", help="changes between a checkout and the committed LABEL.json (exit 1 if any)")
    d.add_argument("src")
    d.add_argument("label")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        dest = Path(a.dir or f"kicad-src-{a.ref}")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", "-b", a.ref,
                        MIRROR, str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", "pcbnew", "common"], check=True)
        print(dest)
        return 0
    new = extract(Path(a.src))
    new["source_ref"] = _src_ref(Path(a.src))
    if a.cmd == "diff":
        old = load(a.label) if (HERE / f"{a.label}.json").exists() else {}
        if old.get("rejected"):  # compare like with like: verified lists vs raw source lists
            for k, rej in old["rejected"].items():
                new[k] = [n for n in new[k] if n not in rej]
        changes = diff(old, new)
        print("\n".join(changes) if changes else f"{a.label}: no vocabulary changes ({new['source_ref']})")
        return 1 if changes else 0
    if a.verify:
        from kae.route.drc import kicad_cli
        new = verify(new, kicad_cli())
    HERE.mkdir(exist_ok=True)
    (HERE / f"{a.label}.json").write_text(json.dumps(new, indent=1) + "\n")
    print(f"wrote {HERE / (a.label + '.json')}: {len(new['constraints'])} constraints, "
          f"{len(new['functions'])} functions, {len(new['properties'])} properties")
    return 0


if __name__ == "__main__":
    sys.exit(main())
