# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build pipeline: load design.py → checks → schematic/project/intent/BOM → KiCad validation."""
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import dru
from .checks import Checker, Finding, summarize
from .emit import netlist as nl
from .emit.intent import intent_yaml
from .emit.kicad_sch import SchematicWriter
from .emit.project import NetClasses, dru_text, write_project
from .emit.report import bom_csv, report_md
from .ir import Design
from .kicadlib import FootprintLibs, SymbolLibs, footprint_dir, symbol_dir

# ERC types that reflect this machine's library configuration, not the design
ENV_ERC = {"lib_symbol_issues", "lib_symbol_mismatch", "footprint_link_issues"}


def load_design(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"kaesynth_design_{path.parent.name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(path.parent))
    if not hasattr(mod, "build"):
        raise SystemExit(f"{path}: define build() -> kaesynth.Design")
    d = mod.build()
    if not isinstance(d, Design):
        raise SystemExit(f"{path}: build() returned {type(d).__name__}, not Design")
    return d


def kicad_cli():
    v = os.environ.get("KAE_KICAD_CLI")
    if v:
        return shlex.split(v)
    wrap = os.environ.get("KAE_KICAD_WRAP")
    if wrap:
        return [*shlex.split(wrap), "kicad-cli"]
    p = shutil.which("kicad-cli")
    return [p] if p else None


def kicad_python():
    """A Python interpreter that can import KiCad's pcbnew (KAE_KICAD_PYTHON overrides)."""
    cands = [os.environ.get("KAE_KICAD_PYTHON"), "/usr/bin/python3", shutil.which("python3"),
             "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"]
    for c in cands:
        if c and Path(c).exists():
            r = subprocess.run([c, "-c", "import pcbnew"], capture_output=True)
            if r.returncode == 0:
                return c
    return None


def _env():
    env = dict(os.environ)
    sd, fd = symbol_dir(), footprint_dir()
    if sd:
        env.setdefault("KICAD10_SYMBOL_DIR", str(sd))
    if fd:
        env.setdefault("KICAD10_FOOTPRINT_DIR", str(fd))
    return env


def run_kicad(design, outdir, netclasses):
    cli = kicad_cli()
    if not cli:
        return {"ran": False, "reason": "kicad-cli not found"}
    res = {"ran": True}
    ver = subprocess.run([*cli, "version"], capture_output=True, text=True)
    res["version"] = ver.stdout.strip()
    sch = outdir / f"{design.slug}.kicad_sch"
    erc_json = outdir / "erc.json"
    p = subprocess.run([*cli, "sch", "erc", "--format", "json", "--severity-all", "-o", str(erc_json), str(sch)],
                       capture_output=True, text=True, env=_env(), cwd=outdir)
    items = []
    if erc_json.exists():
        data = json.loads(erc_json.read_text())
        for sheet in data.get("sheets", []):
            for v in sheet.get("violations", []):
                items.append({"sheet": sheet.get("path"), "severity": v["severity"], "type": v["type"],
                              "description": v["description"],
                              "items": [i.get("description", "") for i in v.get("items", [])]})
        # stable output: drop the timestamp and absolute paths
        data.pop("date", None)
        data["source"] = sch.name
        erc_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    else:
        res["erc_error"] = p.stderr.strip() or p.stdout.strip()
    res["erc_items"] = items
    errs = [i for i in items if i["severity"] == "error" and i["type"] not in ENV_ERC]
    warns = [i for i in items if i["severity"] != "error" and i["type"] not in ENV_ERC]
    res["erc_summary"] = (f"{len(errs)} errors, {len(warns)} warnings" if erc_json.exists()
                          else f"failed: {res.get('erc_error', '')[:200]}")
    res["netlist_problems"] = parity(cli, sch, design, netclasses)
    res["dru"] = lint_dru(cli, outdir, design, netclasses)
    prl = outdir / f"{design.slug}.kicad_prl"
    if prl.exists():
        prl.unlink()          # per-user view state written by kicad-cli
    return res


def parity(cli, sch, design, netclasses, blocks=None):
    """Export KiCad's netlist for `sch` and compare it with the IR (empty list = identical)."""
    xml = sch.with_suffix(".net.xml")
    p = subprocess.run([*cli, "sch", "export", "netlist", "--format", "kicadxml", "-o", str(xml), str(sch)],
                       capture_output=True, text=True, env=_env(), cwd=sch.parent)
    if not xml.exists():
        return [f"netlist export failed: {p.stderr.strip()[:300]}"]
    probs = nl.compare(design, xml, blocks) + nl.netclass_mismatches(xml, netclasses)
    xml.unlink()              # derived and timestamped; netlist.json is the committed form
    prl = sch.with_suffix(".kicad_prl")
    if prl.exists():
        prl.unlink()
    return probs


def lint_dru(cli, outdir, design, netclasses):
    """Static grammar lint of the .kicad_dru, then a DRC smoke run on an outlined empty board
    (kicad-cli 10.0.7 ignores bad rules silently, and crashes on creepage rules without an outline)."""
    text = (outdir / f"{design.slug}.kicad_dru").read_text()
    probs = dru.lint(text, set(netclasses.classes) | {"Default"})
    if probs:
        return "FAIL: " + "; ".join(probs[:5])
    py = kicad_python()
    if py is None:
        return "ok (static lint; DRC smoke skipped: no Python with pcbnew)"
    w, h = 100.0, 100.0
    if design.board_spec and design.board_spec.width_mm:
        w, h = design.board_spec.width_mm, design.board_spec.height_mm or design.board_spec.width_mm
    script = ("import pcbnew,sys\n"
              "b=pcbnew.NewBoard(sys.argv[1])\n"
              "s=pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(pcbnew.Edge_Cuts)\n"
              "s.SetStart(pcbnew.VECTOR2I(0,0)); s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(sys.argv[2])),pcbnew.FromMM(float(sys.argv[3]))))\n"
              "s.SetWidth(pcbnew.FromMM(0.1)); b.Add(s); b.Save(sys.argv[1])\n")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        board = tmp / f"{design.slug}.kicad_pcb"
        subprocess.run([py, "-c", script, str(board), str(w), str(h)], capture_output=True, text=True)
        if not board.exists():
            return "ok (static lint; DRC smoke skipped: could not create a board)"
        shutil.copy(outdir / f"{design.slug}.kicad_dru", tmp / f"{design.slug}.kicad_dru")
        shutil.copy(outdir / f"{design.slug}.kicad_pro", tmp / f"{design.slug}.kicad_pro")
        rpt = tmp / "drc.json"
        p = subprocess.run([*cli, "pcb", "drc", "--format", "json", "-o", str(rpt), str(board)],
                           capture_output=True, text=True, env=_env())
        if p.returncode < 0 or not rpt.exists():
            return f"FAIL: kicad-cli pcb drc exited {p.returncode} with these rules"
    return "ok"


def build(design_path, outdir=None, use_kicad=True, date=None):
    d = load_design(design_path) if not isinstance(design_path, Design) else design_path
    outdir = Path(outdir) if outdir else Path(design_path).resolve().parent / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    sd, fd = symbol_dir(), footprint_dir()
    symlibs = SymbolLibs([sd]) if sd else None
    fplibs = FootprintLibs(fd) if fd else None
    d.libs = (symlibs, fplibs) if symlibs else None
    checker = Checker(d, symlibs, fplibs)
    findings = checker.run()
    fatal = [f for f in findings if f.check in ("lib.symbol_missing",) and not f.waived_by]
    netclasses = NetClasses(d, checker).build()
    kicad = {"ran": False, "reason": "not requested"}
    if symlibs and not fatal:
        writer = SchematicWriter(d, symlibs, title_date=date)
        writer.write(outdir)
        write_project(outdir, d, writer.st, netclasses)
        (outdir / f"{d.slug}.kicad_dru").write_text(dru_text(d, netclasses))
        if use_kicad:
            kicad = run_kicad(d, outdir, netclasses)
            for item in kicad.get("erc_items", []):
                if item["type"] in ENV_ERC:
                    continue
                sev = "error" if item["severity"] == "error" else "warning"
                findings.append(Finding(f"kicad.erc.{item['type']}", sev, f"{item['description']}: {'; '.join(item['items'])}",
                                        [item.get("sheet") or ""]))
            for prob in kicad.get("netlist_problems", []):
                findings.append(Finding("kicad.netlist_roundtrip", "error", prob))
            if str(kicad.get("dru", "")).startswith("FAIL"):
                findings.append(Finding("kicad.dru_parse", "error", kicad["dru"]))
            checker.findings = findings
            checker.apply_waivers()
        boards = d.board_names()
        if len(boards) > 1:
            kicad["boards"] = {}
            for name in boards:
                blocks = [b for b in d.blocks if b.board_name == name]
                sub, slug = outdir / f"board-{name}", f"{d.slug}-{name}"
                w = SchematicWriter(d, symlibs, title_date=date, blocks=blocks, slug=slug, board=name)
                w.write(sub)
                write_project(sub, d, w.st, netclasses, slug=slug, parts=[p for b in blocks for p in b.parts])
                (sub / f"{slug}.kicad_dru").write_text(dru_text(d, netclasses))
                (sub / "intent.yaml").write_text(intent_yaml(d, netclasses, board=name))
                if use_kicad and kicad.get("ran"):
                    probs = parity(kicad_cli(), sub / f"{slug}.kicad_sch", d, netclasses, blocks)
                    kicad["boards"][name] = probs
                    for prob in probs:
                        findings.append(Finding("kicad.netlist_roundtrip", "error", f"board {name}: {prob}"))
            checker.findings = findings
            checker.apply_waivers()
    elif not symlibs:
        kicad = {"ran": False, "reason": "KiCad symbol libraries not found; schematic not written"}
    else:
        kicad = {"ran": False, "reason": "missing symbols; schematic not written"}
    (outdir / "netlist.json").write_text(json.dumps(nl.ir_netlist(d), indent=1) + "\n")
    (outdir / "intent.yaml").write_text(intent_yaml(d, netclasses))
    (outdir / "bom.csv").write_text(bom_csv(d))
    s = summarize(findings)
    status = {"ok": s["error"] == 0, **s,
              "blocking_questions": [q.id for q in d.questions if q.blocking and not q.answer]}
    (outdir / "findings.json").write_text(json.dumps(
        {"status": status, "findings": [f.as_dict() for f in findings]}, indent=1) + "\n")
    (outdir / "report.md").write_text(report_md(d, findings, kicad, status))
    return d, findings, status, kicad
