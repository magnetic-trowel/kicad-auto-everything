# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent electrical and manufacturing recheck of a board kae hands back, as hazards.

A project's .kicad_pro may set DRC checks such as shorting_items, clearance or
copper_edge_clearance to "warning" or "ignore". KiCad (and so kae's repair loops and the
benchmark's scorer, which take severities from the board's project) then call a board clean
that has a short in it. KiCad's DRC does not run an ignored check at all: its JSON lists the
check under `ignored_checks` and reports none of its violations, even with --severity-all
(measured on KiCad 10.0.7, kae/tests/test_board_hazards.py). Checks set to "warning" are
reported, at warning severity.

`recheck(output, project_board)` therefore runs one kicad-cli DRC (kae.route.drc, as the
scorer runs it: zones refilled, all severities) on a scratch copy of the output board whose
project has every check in DRC_CHECKS forced to at least the severity KiCad ships with
(error for the block class), and turns every violation of those checks into a hazard with
the severity of DRC_CHECKS, whatever the project said. The board and its project are never
edited; scoring is untouched (the scorer still uses the board's own severities, register B1).

`static_hazards(board_path, brief)` needs no KiCad: checks the project downgrades, custom
rules that downgrade their own severity, a .kicad_dru KiCad drops, design minimums below
what mainstream fabs build, and net classes whose clearance is below IPC-2221B Table 6-1
for the voltage kae.circuit assigns the net. The list and its reasons:
docs/topics/kicad/mcp-tool-surface-spec.md ("Hazards").
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from kae import hazards as H

# DRC check -> (hazard severity, category, what it means for the board, fix). block: the board
# would not work or cannot be built as drawn. Sources: KiCad 10.0 drc_item.cpp (the keys),
# board_design_settings.cpp (KiCad's own defaults, KICAD_DEFAULTS below), dfm-fab-limits.md.
DRC_CHECKS = {
    # electrical: the circuit is not the one drawn
    "shorting_items": ("block", "electrical", "copper of two different nets touches (a short)",
                       "move or re-route the items so the nets are separated"),
    "tracks_crossing": ("block", "electrical", "tracks of different nets cross on one layer (a short)",
                        "re-route one of the tracks"),
    "unconnected_items": ("block", "electrical", "connections the netlist requires are not routed (open nets)",
                          "route the open connections"),
    "clearance": ("block", "electrical", "copper of different nets is closer than the board's clearance rule",
                  "re-route to the clearance, or confirm the rule and lower it in the net class"),
    "creepage": ("block", "safety", "surface creepage between nets is below the board's creepage rule",
                 "increase the spacing or add a slot"),
    "hole_clearance": ("block", "manufacturing", "a drilled hole is closer to other copper than the rule allows",
                       "move the copper or the hole"),
    "copper_edge_clearance": ("block", "manufacturing",
                              "copper is closer to the board edge than allowed: the fab's router cuts or exposes it",
                              "pull the copper back from the edge (fabs need 0.2-0.4 mm)"),
    "annular_width": ("block", "manufacturing", "a via or pad ring is thinner than the minimum: drill breakout opens it",
                      "use a larger via pad or a smaller drill"),
    "drill_out_of_range": ("block", "manufacturing", "a hole size is outside the board's drill limits",
                           "use a drill size within the limits"),
    "microvia_drill_out_of_range": ("block", "manufacturing", "a microvia drill is outside its limits",
                                    "use a microvia size within the limits"),
    "via_diameter": ("block", "manufacturing", "a via is smaller than the minimum diameter", "use a larger via"),
    "track_width": ("block", "manufacturing", "a track is narrower than the minimum width",
                    "widen the track to the minimum"),
    "invalid_outline": ("block", "manufacturing", "the board outline is not one closed shape: it cannot be cut",
                        "close the Edge.Cuts outline"),
    # warn: buildable, but a risk the caller should see
    "hole_to_hole": ("warn", "manufacturing", "two holes are closer than the minimum (drill breakage, torn walls)",
                     "move the holes apart"),
    "holes_co_located": ("warn", "manufacturing", "two holes are drilled at one place", "remove the duplicate"),
    "connection_width": ("warn", "electrical", "a copper connection narrows below the minimum width",
                         "widen the neck"),
    "zones_intersect": ("warn", "electrical", "zones of different nets overlap with equal priority (fill is undefined)",
                        "give the zones distinct priorities or separate them"),
    "items_not_allowed": ("warn", "electrical", "copper sits inside a rule area (keepout) that forbids it",
                          "move it out of the keepout"),
    "starved_thermal": ("warn", "thermal", "a thermal relief has too few spokes connected",
                        "add room for the spokes or use a solid connection"),
    "solder_mask_bridge": ("warn", "assembly", "a solder mask opening joins pads of different nets (solder bridges)",
                           "separate the pads or restore the mask web"),
    "courtyards_overlap": ("warn", "assembly", "part courtyards overlap (assembly and rework clearance)",
                           "move the parts apart"),
    # info: 90 % of the corpus's projects (6,519 of 7,226) ignore these two, KiCad 6-9's default;
    # a part-to-part conflict also shows as courtyards_overlap
    "pth_inside_courtyard": ("info", "assembly", "a plated hole sits inside another part's courtyard",
                             "move the hole or the part"),
    "npth_inside_courtyard": ("info", "assembly", "a mounting hole sits inside a part's courtyard",
                              "move the hole or the part"),
    "copper_sliver": ("warn", "manufacturing", "a thin copper sliver can lift off during etching",
                      "change the zone or the clearance"),
    "length_out_of_range": ("warn", "electrical", "a net's length is outside its rule", "tune the length"),
    "skew_out_of_range": ("warn", "electrical", "skew between nets is outside its rule", "tune the lengths"),
    "diff_pair_gap_out_of_range": ("warn", "electrical", "a differential pair's gap is outside its rule",
                                   "route the pair at its gap"),
    "diff_pair_uncoupled_length_too_long": ("warn", "electrical", "a differential pair runs uncoupled too long",
                                            "route the pair together"),
    "too_many_vias": ("warn", "electrical", "a net has more vias than its rule allows", "re-route with fewer vias"),
    "assertion_failure": ("warn", "data", "a custom rule's assertion fails", "read the rule and fix the board"),
    "track_on_post_machined_layer": ("warn", "manufacturing", "a track lies on a post-machined (counterbored) layer",
                                     "move the track"),
    "silk_over_copper": ("warn", "manufacturing", "silkscreen lies on exposed copper (the fab clips it)",
                         "move the silkscreen"),
    "silk_edge_clearance": ("warn", "manufacturing", "silkscreen is too close to the board edge", "move the silkscreen"),
    "isolated_copper": ("info", "manufacturing", "an isolated copper island (antenna, wasted copper)",
                        "remove the island or connect it"),
    "via_dangling": ("info", "electrical", "a via connects to nothing", "remove it"),
    "track_dangling": ("info", "electrical", "a track end connects to nothing", "remove the stub"),
    "silk_overlap": ("info", "manufacturing", "silkscreen items overlap", "move the silkscreen"),
    "text_height": ("info", "manufacturing", "text is smaller than the minimum height", "enlarge the text"),
    "text_thickness": ("info", "manufacturing", "text strokes are thinner than the minimum", "thicken the text"),
}
# KiCad 10.0's own default severities for the checks above that are not "error"
# (BOARD_DESIGN_SETTINGS constructor, pcbnew/board_design_settings.cpp @10.0)
KICAD_DEFAULTS = dict(hole_to_hole="warning", holes_co_located="warning", track_dangling="warning",
                      via_dangling="warning", copper_sliver="warning", isolated_copper="warning",
                      connection_width="warning", silk_over_copper="warning", silk_edge_clearance="warning",
                      silk_overlap="warning", text_height="warning", text_thickness="warning",
                      missing_courtyard="ignore")
_RANK = dict(ignore=0, warning=1, error=2)

# Smallest absolute limits among JLCPCB (2L and multilayer), PCBWay standard and OSH Park
# (dfm-fab-limits.md, fab pages read 2026-10-20): a design minimum below these is not
# standard capability at any of them (advanced/HDI services may still build it).
FAB_FLOORS = dict(clearance=0.09, track_width=0.09, hole=0.15, annular=0.10, edge_clearance=0.2,
                  hole_to_hole=0.127)

# IPC-2221B Table 6-1, minimum conductor spacing (mm) by peak voltage between conductors:
# B1 internal, B2 external uncoated (<= 3050 m). Rows: (upper V, B1, B2); above 500 V per volt.
# (isolation-creepage.md; EMA reproduction of Table 6-1.) Functional spacing only, not safety.
IPC2221B = ((15, 0.05, 0.1), (30, 0.05, 0.1), (50, 0.1, 0.6), (100, 0.1, 0.6), (150, 0.2, 0.6),
            (170, 0.2, 1.25), (250, 0.2, 1.25), (300, 0.2, 1.25), (500, 0.25, 2.5))
IPC2221B_PER_V = (0.0025, 0.005)
HV_VOLTS = 30.0               # register RC10: warn above 30 V, where B2 jumps from 0.1 to 0.6 mm


def ipc2221b_spacing(volts, external=True):
    """IPC-2221B Table 6-1 spacing (mm) for `volts` (peak) between conductors."""
    v = abs(float(volts))
    for top, b1, b2 in IPC2221B:
        if v <= top:
            return b2 if external else b1
    return v * IPC2221B_PER_V[1 if external else 0]


def project_severities(board_path):
    """{check: severity} the project beside the board sets (only keys it sets)."""
    try:
        pro = json.loads(Path(board_path).with_suffix(".kicad_pro").read_text(encoding="utf-8"))
        sev = pro["board"]["design_settings"]["rule_severities"]
        return {str(k): str(v) for k, v in sev.items() if v in _RANK}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def required_severity(check):
    """The least severity at which the recheck runs `check`: error for the block class,
    otherwise KiCad's own default (never below warning, so the check runs)."""
    sev = DRC_CHECKS[check][0]
    if sev == "block":
        return "error"
    d = KICAD_DEFAULTS.get(check, "error")
    return "warning" if d == "ignore" else d


def downgraded(severities):
    """{check: (project severity, required)} for the checks the project runs below the recheck."""
    out = {}
    for k in DRC_CHECKS:
        have = severities.get(k, KICAD_DEFAULTS.get(k, "error"))
        need = required_severity(k)
        if _RANK[have] < _RANK[need]:
            out[k] = (have, need)
    return out


# ---- static: the project's own settings ------------------------------------------------

def static_hazards(board_path, brief=None, board=None):
    """Hazards from the project's settings alone (no KiCad needed)."""
    out = []
    sev = project_severities(board_path)
    for k, (have, need) in sorted(downgraded(sev).items()):
        hs, cat, what, _ = DRC_CHECKS[k]
        if hs == "info":
            continue
        out.append(H.make("drc_check_downgraded", "warn" if hs == "block" else "info", "data",
                          f"The project sets DRC check '{k}' to {have}, so KiCad and the benchmark treat "
                          f"'{what}' as acceptable; kae's recheck runs it at {need}.",
                          objects=[k], evidence=dict(project=have, recheck=need, kicad_default=KICAD_DEFAULTS.get(k, "error"),
                                                     source=".kicad_pro rule_severities"),
                          fix=f"Set '{k}' back to {need} in Board Setup > Violation Severity unless it is deliberate."))
    dru = Path(board_path).with_suffix(".kicad_dru")
    if dru.exists():
        out += _dru_hazards(dru, board_path)
    rules = getattr(board, "rules", None) if board is not None else None
    if rules is None:
        try:
            from kae.board.kicad_file import read_rules
            rules = read_rules(board_path)
        except Exception:      # noqa: BLE001 - static hazards must never stop a report
            rules = None
    if rules is not None:
        out += _fab_floor_hazards(rules)
        out += _voltage_hazards(rules, brief, board)
    return out


def _dru_hazards(dru, board_path):
    out = []
    try:
        from kae.board.dru_check import rejection
        why = rejection(str(dru), str(board_path))
    except Exception:          # noqa: BLE001
        why = None
    if why:
        out.append(H.make("dru_rejected", "warn", "data",
                          "KiCad drops the board's .kicad_dru custom rules file, so none of its rules "
                          "were applied or checked.", objects=[".kicad_dru"], evidence=dict(reason=str(why)[:200]),
                          fix="Fix the rules file (kae dru-check names the error) and run again."))
        return out
    try:
        text = dru.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for name, body in _dru_rules(text):
        m = re.search(r"\(severity\s+(\w+)\)", body)
        if m and m.group(1) in ("ignore", "warning", "exclusion"):
            out.append(H.make("dru_rule_downgraded", "warn", "data",
                              f"Custom rule '{name}' sets its own severity to {m.group(1)}, so its violations "
                              "do not count as errors (and are not checked at all when ignored).",
                              objects=[name], evidence=dict(severity=m.group(1), source=".kicad_dru"),
                              fix="Check the rule is meant to be waived; otherwise remove its severity line."))
    return out


def _dru_rules(text):
    """(name, text) of each top-level (rule ...) of a .kicad_dru, comments dropped."""
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    out = []
    for m in re.finditer(r"\(rule\s+(\"[^\"]*\"|\S+)", text):
        depth, i = 0, m.start()
        for j in range(m.start(), len(text)):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    i = j + 1
                    break
        out.append((m.group(1).strip('"'), text[m.start():i]))
    return out


_FLOOR_FIELDS = (("clearance", "clearance", "board minimum clearance"),
                 ("track_min", "track_width", "board minimum track width"),
                 ("via_drill_min", "hole", "board minimum through-hole size"),
                 ("annular_min", "annular", "board minimum annular ring"),
                 ("edge_clearance", "edge_clearance", "board copper-to-edge clearance"),
                 ("hole_to_hole", "hole_to_hole", "board minimum hole-to-hole"))
_DRU_FLOOR = dict(clearance="clearance", track_width="track_width", hole_size="hole", annular_width="annular",
                  edge_clearance="edge_clearance", hole_to_hole="hole_to_hole")


def _fab_floor_hazards(rules):
    """Design minimums below every mainstream fab's absolute limit (FAB_FLOORS)."""
    out = []

    def flag(obj, what, val, floor, src):
        out.append(H.make("below_fab_floor", "warn", "manufacturing",
                          f"{what} is {val:g} mm, below the {floor:g} mm that JLCPCB, PCBWay and OSH Park build "
                          "at standard capability; copper drawn to it needs an advanced (HDI) fab.",
                          objects=[obj], evidence=dict(value_mm=val, floor_mm=floor, source=src,
                                                       limit_source="dfm-fab-limits.md fab profiles"),
                          fix=f"Raise it to at least {floor:g} mm, or confirm the fab and its capability."))
    for f, key, what in _FLOOR_FIELDS:
        v = getattr(rules, f, None)
        if v and 0 < v < FAB_FLOORS[key] - 1e-9:
            flag(f, what, round(v, 4), FAB_FLOORS[key], ".kicad_pro design rules")
    for name, nc in (getattr(rules, "netclasses", None) or {}).items():
        if "," in name:
            continue
        for f, key in (("clearance", "clearance"), ("track_width", "track_width"), ("via_drill", "hole")):
            v = getattr(nc, f, None)
            if v and 0 < v < FAB_FLOORS[key] - 1e-9:
                flag(f"netclass {name}", f"net class '{name}' {f.replace('_', ' ')}", round(v, 4), FAB_FLOORS[key],
                     ".kicad_pro net class")
    for r in getattr(rules, "custom", None) or []:
        for c in r.get("constraints") or []:
            key = _DRU_FLOOR.get(c.get("type"))
            v = c.get("min")
            if key and v is not None and 0 < v < FAB_FLOORS[key] - 1e-9:
                flag(f"rule {r.get('name')}", f"custom rule '{r.get('name')}' {c.get('type')} minimum", round(v, 4),
                     FAB_FLOORS[key], ".kicad_dru")
    return out


def _voltage_hazards(rules, brief, board):
    """Nets kae.circuit puts above HV_VOLTS whose class clearance is below IPC-2221B B2 for the
    voltage to the lowest net on the board (register RC10). A custom rule naming the net or its
    class with a clearance at least that large clears the flag."""
    nets = (brief or {}).get("nets") or {}
    volts = {n: d.get("volts") for n, d in nets.items() if isinstance(d, dict) and d.get("volts") is not None}
    if not volts:
        return []
    low = min(0.0, min(volts.values()))
    classes = getattr(rules, "netclasses", None) or {}
    board_nets = getattr(board, "nets", None) or {}
    custom = getattr(rules, "custom", None) or []
    out = []
    for n, v in sorted(volts.items()):
        dv = max(abs(v), abs(v - low))
        if dv <= HV_VOLTS:
            continue
        need = ipc2221b_spacing(dv, external=True)
        bn = board_nets.get(n)
        cls = getattr(bn, "netclass", None) or "Default"
        nc = classes.get(cls) or classes.get("Default")
        have = max(getattr(nc, "clearance", None) or 0.0, getattr(rules, "clearance", 0.0) or 0.0)
        if have + 1e-9 >= need:
            continue
        if any(c.get("type") == "clearance" and (c.get("min") or 0) + 1e-9 >= need
               and (n in (r.get("condition") or "") or cls in (r.get("condition") or ""))
               for r in custom for c in r.get("constraints") or []):
            continue
        out.append(H.make("hv_clearance_below_ipc", "warn", "safety",
                          f"Net {n} is believed to carry about {dv:g} V, but its net class '{cls}' allows "
                          f"{have:g} mm clearance; IPC-2221B asks {need:g} mm on uncoated outer layers.",
                          objects=[n, f"netclass {cls}"],
                          evidence=dict(volts=round(dv, 2), clearance_mm=have, ipc2221b_b2_mm=round(need, 3),
                                        ipc2221b_b1_mm=round(ipc2221b_spacing(dv, external=False), 3),
                                        volts_source="kae.circuit brief (inferred)",
                                        limit_source="IPC-2221B Table 6-1 B2 (functional, not safety)"),
                          fix=f"Put {n} in a net class with at least {need:g} mm clearance (mains or user-touchable "
                              "circuits need the safety standard's creepage and clearance instead), or confirm the "
                              "voltage is lower."))
    return out


# ---- the recheck: one DRC with the safety checks forced on ------------------------------

def forced_project(pro):
    """A copy of a .kicad_pro dict with every DRC_CHECKS check at least at required_severity."""
    pro = json.loads(json.dumps(pro or {}))
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    sev = ds.setdefault("rule_severities", {})
    for k in DRC_CHECKS:
        need = required_severity(k)
        have = sev.get(k, KICAD_DEFAULTS.get(k, "error"))
        if _RANK.get(have, 2) < _RANK[need]:
            sev[k] = need
    return pro


_NET = re.compile(r"\[([^\]]+)\]")
_REF = re.compile(r"(?:\bof |^Footprint )(\S+)")


def _objects(items):
    nets, refs = [], []
    for it in items or []:
        d = it.get("description") or ""
        for m in _NET.finditer(d):
            if m.group(1) not in nets and m.group(1) != "<no net>":
                nets.append(m.group(1))
        for m in _REF.finditer(d):
            if m.group(1) not in refs:
                refs.append(m.group(1))
    return refs + nets


def drc_hazards(report, severities=None, unconnected=None):
    """Hazards from a DRC JSON report (kicad-cli drc.v1), one per check type with its count,
    the objects involved, and a few locations. `severities` (the project's) go into the
    evidence, so the caller sees which findings the project would have hidden."""
    severities = severities or {}
    groups = {}
    for v in report.get("violations") or []:
        t = v.get("type")
        if t not in DRC_CHECKS or v.get("excluded"):
            continue
        groups.setdefault(t, []).append(v)
    unc = report.get("unconnected_items") or []
    if unc:
        groups["unconnected_items"] = unc
    out = []
    for t, vs in groups.items():
        hs, cat, what, fix = DRC_CHECKS[t]
        objs = []
        for v in vs:
            for o in _objects(v.get("items")):
                if o not in objs:
                    objs.append(o)
        n = len(vs)
        if t == "unconnected_items":
            n = report.get("unconnected_count", n) if unconnected is None else unconnected
        proj = severities.get(t, KICAD_DEFAULTS.get(t, "error"))
        hidden = _RANK.get(proj, 2) < _RANK["error"] and hs == "block"
        locs = []
        for v in vs[:3]:
            p = ((v.get("items") or [{}])[0]).get("pos") or {}
            if "x" in p:
                locs.append([round(p["x"], 3), round(p["y"], 3)])
        ev = dict(count=n, project_severity=proj, example=(vs[0].get("description") or "")[:160])
        if locs:
            ev["at_mm"] = locs
        if hidden:
            ev["hidden_by_project"] = True
        out.append(H.make(f"drc_{t}", hs, cat,
                          f"{n} x {what}" + (f" (the project sets this check to {proj}, so KiCad's own DRC would "
                                             "not call it an error)" if hidden else "") + ".",
                          objects=objs, evidence=ev, fix=fix))
    return out


def recheck(output, project_board=None, timeout=900, workdir=None, log=None):
    """(hazards, meta): one kicad-cli DRC of `output` with `project_board`'s project files
    (default: the ones beside `output`), forced to the safety severities. meta records what
    ran: seconds, forced checks, or why it was skipped (no KiCad, a DRC failure: then a
    `recheck_failed` hazard says the board is unverified)."""
    from kae.route import drc as kdrc
    project_board = project_board or output
    meta = dict(ran=False)
    sev = project_severities(project_board)
    forced = downgraded(sev)
    meta["forced"] = sorted(forced)
    try:
        kdrc.kicad_cli()
    except Exception as e:      # noqa: BLE001
        meta["skipped"] = f"no kicad-cli: {str(e)[:120]}"
        return [H.make("recheck_unavailable", "warn", "data",
                       "KiCad was not available, so the board kae wrote was not rechecked for shorts, "
                       "clearance and opens.", evidence=dict(reason=meta["skipped"]),
                       fix="Run kicad-cli pcb drc on the output before ordering.")], meta
    own = workdir is None
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-recheck-"))
    t0 = time.monotonic()
    try:
        staged = kdrc.stage_board(output, project_board, wd)
        pro_path = staged.with_suffix(".kicad_pro")
        try:
            pro = json.loads(pro_path.read_text(encoding="utf-8")) if pro_path.exists() else {}
        except ValueError:
            pro = {}
        pro_path.write_text(json.dumps(forced_project(pro), indent=1))
        rep = kdrc.run(staged, wd / "drc.json", timeout=timeout)
    except Exception as e:      # noqa: BLE001 - a recheck that fails must say so, not raise
        meta.update(seconds=round(time.monotonic() - t0, 1), error=f"{type(e).__name__}: {str(e)[:160]}")
        if log:
            log(f"recheck failed: {meta['error']}")
        return [H.make("recheck_failed", "warn", "data",
                       "The independent DRC recheck of the output board failed, so shorts, clearance and "
                       "opens hidden by the project's severities are unverified.", evidence=dict(error=meta["error"]),
                       fix="Run kicad-cli pcb drc on the output with the checks set to error.")], meta
    finally:
        if own:
            shutil.rmtree(wd, ignore_errors=True)
    meta.update(ran=True, seconds=round(time.monotonic() - t0, 1))
    hz = drc_hazards(rep, sev)
    meta["counts"] = {h["code"]: h["evidence"]["count"] for h in hz}
    if log:
        log(f"recheck: {len(hz)} hazard types in {meta['seconds']}s (forced {','.join(meta['forced']) or 'none'})")
    return hz, meta


def board_hazards(output, project_board=None, brief=None, board=None, drc=True, timeout=900, log=None):
    """(hazards, meta) for a board kae wrote: static_hazards of the project, plus recheck."""
    project_board = project_board or output
    out = []
    try:
        out += static_hazards(project_board, brief=brief, board=board)
    except Exception as e:      # noqa: BLE001
        out.append(H.make("static_hazards_failed", "info", "data", f"Static project checks failed: {e}"))
    meta = dict(ran=False, skipped="off")
    if drc and output and Path(output).exists():
        hz, meta = recheck(output, project_board, timeout=timeout, log=log)
        out += hz
    return out, meta


def final_summary(report):
    """The last DRC summary a kae report carries for its output ({unconnected, by_type}), or None:
    the joint loop's final card, the bridge's (repair) final, critical routing's bridge."""
    for path in (("final",), ("repair", "final"), ("bridge", "repair", "final"), ("bridge", "final")):
        d = report
        for k in path:
            d = d.get(k) if isinstance(d, dict) else None
        if isinstance(d, dict) and ("by_type" in d or "errors_by_type" in d) and d.get("unconnected") is not None:
            return dict(unconnected=d.get("unconnected"), by_type=d.get("by_type") or d.get("errors_by_type") or {},
                        path=".".join(path))
    return None


def summary_hazards(report, skip=()):
    """Hazards from the report's own final DRC summary (counts only, the project's severities):
    the fallback when the recheck did not run."""
    fs = final_summary(report)
    if fs is None:
        return []
    by = dict(fs["by_type"])
    if fs["unconnected"] and "unconnected_items" not in skip:
        by["unconnected_items"] = fs["unconnected"]
    out = []
    for t, n in sorted(by.items()):
        if t not in DRC_CHECKS or t in skip or not n:
            continue
        hs, cat, what, fix = DRC_CHECKS[t]
        out.append(H.make(f"drc_{t}", hs, cat, f"{n} x {what}.", evidence=dict(count=n, source=f"report {fs['path']} "
                                                                                "(kae's own DRC, project severities)"),
                          fix=fix))
    return out


# kinds of output: what the recheck leaves out. A placement is not routed: its opens and the
# stubs of moved parts are the router's job, not a hazard of the placement.
SKIP_BY_KIND = dict(place=("unconnected_items", "track_dangling", "via_dangling"))
MIN_RECHECK_S = 20.0      # less time than this left: the recheck is skipped (and says so)


def add_arguments(ap):
    """--recheck on|off|auto for a CLI that writes a board (auto: when kicad-cli is found)."""
    ap.add_argument("--recheck", default="auto", choices=("auto", "on", "off"),
                    help="independent KiCad DRC of the output with the safety checks forced on; findings go to "
                         "the report's hazards (auto: when kicad-cli is found and time is left)")


def finish(report, output=None, project_board=None, kind="route", mode="auto", deadline=None, brief=None,
           board=None, log=None):
    """Close `report` for the LLM: static project hazards, the forced-severity recheck of
    `output` (mode on|auto|off; within `deadline`, a time.monotonic() value), then
    kae.hazards.finalize (nested lists hoisted, flags derived, capped, summary). The
    recheck's meta goes to report["recheck"]. Never raises: a report is always written."""
    extra = []
    project_board = project_board or output
    try:
        if project_board:
            extra += static_hazards(project_board, brief=brief, board=board)
    except Exception as e:      # noqa: BLE001
        extra.append(H.make("static_hazards_failed", "info", "data", f"Static project checks failed: {e}"[:200]))
    meta = dict(ran=False)
    try:
        if mode == "off" or not output:
            meta["skipped"] = "off" if mode == "off" else "no output"
        elif not Path(output).exists():
            meta["skipped"] = "no output board"
        else:
            left = None if deadline is None else deadline - time.monotonic()
            if left is not None and left < MIN_RECHECK_S and mode != "on":
                meta["skipped"] = f"time ({left:.0f} s left)"
                hidden = {k: v for k, v in downgraded(project_severities(project_board)).items()
                          if DRC_CHECKS[k][0] != "info"}
                extra.append(H.make("recheck_skipped", "warn" if hidden else "info", "data",
                                    "No time was left to recheck the output board with the safety checks forced on"
                                    + ("; the project downgrades " + ", ".join(sorted(hidden)) + ", so violations "
                                       "of those are unverified." if hidden else
                                       "; the project downgrades none of them, so kae's own DRC counts stand."),
                                    objects=sorted(hidden), evidence=dict(seconds_left=round(left, 1)),
                                    fix="Run again with --recheck on, or run kicad-cli pcb drc with the checks set "
                                        "to error."))
            else:
                timeout = 900.0 if left is None else max(MIN_RECHECK_S, min(900.0, left - 5.0))
                hz, meta = recheck(output, project_board, timeout=timeout, log=log)
                skip = {f"drc_{t}" for t in SKIP_BY_KIND.get(kind, ())}
                extra += [h for h in hz if h["code"] not in skip]
    except Exception as e:      # noqa: BLE001
        meta = dict(ran=False, error=f"{type(e).__name__}: {e}"[:200])
    if not meta.get("ran"):
        extra += summary_hazards(report, skip=SKIP_BY_KIND.get(kind, ()))
    report["recheck"] = meta
    return H.finalize(report, extra=extra)
