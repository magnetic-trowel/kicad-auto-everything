# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finish: the final shape and fill of a routed board, behind one journaled KiCad DRC gate.

    from kae.route import finish
    rep = finish.run("routed.kicad_pcb", "out.kicad_pcb", project="task.kicad_pcb", time_s=300)

    python -m kae.route.finish IN OUT [--project TASK] [--time S] [--parts tails,taut,power]
                                      [--input-drc DRC.json] [--report R.json]

Stage 7 of docs/topics/routing/routing-stages.md, on the board an attempt (or the portfolio)
keeps. In this order, each pass exactly checked inside (critical_space.Space), none running
KiCad's DRC itself (`gate=False`: each returns its changes as kae.route.journal entries):

  (a) `tails`: rule D tails (kae.route.pad_reroute, centre-line targets) on copper whose pad
      entries break the rule. Copper kae's grid router drew born right is not a candidate (its
      entries already meet rule D), so in effect this finishes Freerouting's copper;
  (b) `taut`: every unlocked branch pulled to its homotopic shortest path with true arcs
      (kae.route.taut, its own pad tails on);
  (c) `power`: power copper (kae.route.power_copper): widening with current-proportional sharing
      and necks at small lands, rails above `zone_above_a` (5 A) as pours, ground vias at decap
      and IC ground pads, stitching;
  (d) one gate (journal.gate): KiCad's DRC of the input (the caller's report when it has one) and
      of the output, compared by violation identity; noisy checks found by a second run of the
      input; reverts by attribution, then ddmin by stage, net and entry, each revert taking the
      entries that built on it. The board kept is never worse than the input (DRC by type, and
      unconnected);
  (e) hazards (kae.hazards schema): the passes' land hazards, parts skipped for time, noisy
      checks, entries reverted.

`pad_trim` (`trim`) can be added to `parts` (the bridge's pad_entry=edge cut).

Time (`time_s`): finish never runs past it. It plans against `time_s` less a safety margin
(`safety_margin`: 15 s + 5 %, at most a quarter) for a gate DRC started late and the exit. Each part
runs only when its estimate from the board's size (`estimate`) and the gate's fit in what is left; a
part gets what is left less the gate's estimate, and the taut pass checks it between branches and
passes, keeping (and journaling) what it finished. A board too big for its time runs (a) and (b)
and reports (c) as skipped (`finish_part_skipped`). The result is cached in the step cache (KAE_STEP_CACHE) by input board, project files,
code and options, unless a part was skipped or the gate stopped for time.
"""
from __future__ import annotations

from kae.budget import start_run as _start_run
from kae.budget import now as clock_now
import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from . import journal as J

PARTS = ("tails", "taut", "power")
DEFAULTS = dict(
    parts=PARTS,
    zone_above_a=5.0,       # A: power copper pours rails above this instead of widening their tracks
    drc_budget=32,          # KiCad DRC runs the gates may spend beyond the input's (both gates together)
    recover=16,             # of them, at most this many to re-admit what attribution reverted
    replan=True,            # after the gate, run the stages after the earliest one with reverts again on the
                            # gated board, behind a second gate (its input DRC is the first gate's last)
    margin=None,            # mm: new copper this close to another net's removed copper depends on its removal
                            # (None: the project's largest net-class clearance, journal.clearance_margin)
    tails_opts=None,        # pad_reroute.run keyword overrides (rails, target, operating)
    taut_opts=None,         # taut.DEFAULTS overrides
    power_opts=None,        # power_copper.DEFAULTS overrides
    operating=None,         # operating facts JSON for all passes (pad and net currents); default: KAE_OPERATING
)

# Seconds per part from the board's size, fitted on the 12 boards of the taut and power-copper
# smoke sets (planning only, gates excluded): taut 2-124 s for 36-1,245 pads, rule D 4-10 s,
# power copper's planning 2-15 s. A board without tracks (a task input) counts pads.
COEF = dict(tails=(5.0, 0.02), taut=(5.0, 0.12), power=(5.0, 0.03), trim=(3.0, 0.005))
DRC_COEF = (3.0, 0.02)       # one KiCad DRC: about 8 s at 300 pads, 30 s at 1,300 (zones refilled)


SAFETY_S = (15.0, 0.05)      # s: the margin finish keeps below its --time: fixed, and per second of budget


def safety_margin(time_s):
    """Seconds finish keeps free below its budget `time_s` (at most a quarter of it)."""
    return round(min(0.25 * time_s, SAFETY_S[0] + SAFETY_S[1] * time_s), 1)


def size_of(board_path):
    text = Path(board_path).read_text(encoding="utf-8", errors="replace")
    return dict(pads=text.count("(pad "), segments=text.count("(segment"), arcs=text.count("(arc"))


def estimate(board_path, drc_s=None, parts=PARTS):
    """{part: seconds} for each part, 'drc' (one KiCad DRC: `drc_s` when the caller measured one)
    and 'gate' (the output's DRC and one more, a noise run or a revert round), and 'total'."""
    n = size_of(board_path)["pads"]
    est = {p: COEF[p][0] + COEF[p][1] * n for p in parts}
    est["drc"] = float(drc_s) if drc_s else DRC_COEF[0] + DRC_COEF[1] * n
    est["gate"] = 2 * est["drc"]
    est["total"] = sum(est[p] for p in parts) + est["gate"] + 5.0
    return {k: round(v, 1) for k, v in est.items()}


def _pass(part, src, dst, o, wd, timeout, log):
    """Run one part with its gate off. Returns its report (with "_entries")."""
    if part == "tails":
        from . import pad_reroute
        kw = dict(o.get("tails_opts") or {})
        kw.setdefault("operating", o.get("operating"))
        return pad_reroute.run(src, dst, workdir=wd, timeout=timeout, log=log, gate=False, **kw)
    if part == "taut":
        from . import taut
        to = dict(o.get("taut_opts") or {})
        to.setdefault("operating", o.get("operating"))
        return taut.run(src, dst, opts=to, workdir=wd, timeout=timeout, log=log, gate=False)
    if part == "power":
        from . import power_copper
        po = dict(o.get("power_opts") or {})
        po.setdefault("zone_above_a", o.get("zone_above_a"))
        if o.get("operating"):
            po.setdefault("operating", o["operating"])
        return power_copper.run(src, dst, opts=po, workdir=wd, timeout=timeout, log=log, gate=False)
    if part == "trim":
        from . import pad_trim
        return pad_trim.run(src, dst, workdir=wd, timeout=timeout, log=log, gate=False)
    raise ValueError(f"unknown finish part {part!r} (known: {', '.join(PARTS + ('trim',))})")


def _summary(part, rep):
    keep = ("planned", "kept", "outcome", "necks", "len_delta_mm", "nets_changed", "overhang_fixed", "kinds",
            "plan_s", "total_s", "stats_in", "stats_out")
    out = {k: rep[k] for k in keep if k in rep}
    if "nets_changed" in out:
        out["nets_changed"] = len(out["nets_changed"])
    if part == "taut" and "stats" in rep:
        out["passes"] = rep["stats"].get("passes")
        if rep["stats"].get("stopped"):
            out["stopped"] = rep["stats"]["stopped"]
    if part == "power" and "nets" in rep:
        out["zone_nets"] = rep["nets"].get("zones")
    return out


def run(input_path, output_path, project=None, opts=None, workdir=None, time_s=None, base_report=None,
        drc_s=None, log=print):
    """Finish the routed board `input_path` into `output_path` (with `project`'s .kicad_pro and
    .kicad_dru: the task's rules; default the board's own). `base_report`: a KiCad DRC report of
    the input (dict or JSON path) the caller already has, e.g. the restart wrapper's judgement of the
    kept board. `time_s`: the seconds this may take (None: no limit); `drc_s`: one DRC's measured
    seconds, for the estimates. Returns a report: parts ran and skipped, entries kept and reverted
    per stage, DRC in and out, DRC runs, seconds per stage, hazards."""
    from . import stepcache
    o = {**DEFAULTS, **(opts or {})}
    o["parts"] = tuple(o["parts"])
    inp = Path(input_path).resolve()
    project = Path(project).resolve() if project else inp
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    key_opts = {k: v for k, v in o.items()}
    if o.get("operating") and Path(o["operating"]).exists():
        key_opts["operating"] = stepcache.file_sha(o["operating"])      # its content, not its path
    key = None
    if stepcache.enabled():
        from . import drc
        try:
            tool = stepcache.kicad_version(drc.kicad_cli())
        except Exception:      # noqa: BLE001 - no KiCad: the gate cannot run either; no cache
            tool = None
        if tool:
            key = stepcache.board_key("finish", inp, project, key_opts, tool=tool)
    if key is None:
        return _run(inp, out, project, o, workdir, time_s, base_report, drc_s, log)[0]
    rep = stepcache.cached_board_step("finish", key, {"board": out},
                                      lambda: _run(inp, out, project, o, workdir, time_s, base_report, drc_s, log),
                                      timeout=time_s)
    J.write(out.read_text(encoding="utf-8"), out, project)        # a hit restores the board alone
    return rep


def _run(inp, out, project, o, workdir, time_s, base_report, drc_s, log):
    from kae import hazards as H
    from . import drc
    t0 = clock_now()
    # the parts and the gate plan against `deadline`; the margin below it covers what may still run
    # after them: a gate DRC started just before the deadline (journal: timeout >= 10 s), writing the
    # board, and the caller's exit (kae.route.cli finish's recheck is skipped with under 20 s left)
    margin = None if time_s is None else safety_margin(float(time_s))
    deadline = None if time_s is None else t0 + float(time_s) - margin
    own = workdir is None
    wd = Path(workdir).resolve() if workdir else Path(tempfile.mkdtemp(prefix="kae-finish-", dir=out.parent))
    wd.mkdir(parents=True, exist_ok=True)

    def left():
        return float("inf") if deadline is None else deadline - clock_now()

    rep = dict(input=str(inp), project=str(project), parts=dict(ran=[], skipped={}, failed={}), stages={},
               seconds={}, hazards=[], budget_s=time_s, margin_s=margin)
    cacheable = True
    try:
        staged = drc.stage_board(inp, project, wd / "in")
        if isinstance(base_report, (str, Path)):
            try:
                base_report = json.loads(Path(base_report).read_text())
            except (OSError, ValueError):
                base_report = None
        if base_report is not None and len(base_report.get("unconnected_items") or []) >= drc.DRC_UNCONNECTED_CAP \
                and base_report.get("unconnected_count") is None:
            base_report = None          # a capped count: the gate runs its own (uncapped) DRC of the input
        est = estimate(staged, drc_s, o["parts"])
        rep["estimate_s"] = est
        jr = J.Journal(staged.read_text(encoding="utf-8"),
                       margin=o["margin"] if o["margin"] is not None else J.clearance_margin(project))
        cur = staged
        for part in o["parts"]:
            need = est.get(part, 10.0) + est["gate"]
            if left() < need:
                rep["parts"]["skipped"][part] = f"time: {left():.0f} s left, {need:.0f} s estimated"
                cacheable = False
                log(f"[finish] {part}: skipped ({rep['parts']['skipped'][part]})")
                continue
            t1 = clock_now()
            dst = drc.stage_board(cur, project, wd / part / "out")
            try:
                r = _pass(part, cur, dst, o, wd / part / "work",
                          timeout=max(1, int(left() - est["gate"])) if deadline else 3600, log=log)
            except Exception as e:      # noqa: BLE001 - one part never costs the board
                import traceback
                traceback.print_exc()
                rep["parts"]["failed"][part] = f"{type(e).__name__}: {e}"[:300]
                rep["seconds"][part] = round(clock_now() - t1, 1)
                continue
            entries = r.pop("_entries", [])
            n0 = len(jr.entries)
            jr.add(entries)
            entries = jr.entries[n0:]           # after merging conflicting ones
            rep["hazards"] += [h for h in r.get("hazards") or [] if isinstance(h, dict)]
            rep["stages"][part] = dict(_summary(part, r), entries=len(entries))
            rep["parts"]["ran"].append(part)
            rep["seconds"][part] = round(clock_now() - t1, 1)
            cur = dst
            log(f"[finish] {part}: {len(entries)} entries in {rep['seconds'][part]:.1f} s")
        t1 = clock_now()
        g = J.gate(staged, project, jr, wd / "gate", base_report=base_report, budget=int(o["drc_budget"]),
                   deadline=deadline, log=log, recover=int(o["recover"]))
        rep["seconds"]["gate"] = round(clock_now() - t1, 1)
        J.write(g["text"], out, project)
        kept = g["kept"]
        for part in rep["stages"]:
            st = [e for e in jr.entries if e.stage == part]
            rep["stages"][part].update(kept_entries=sum(1 for e in st if e.id in kept),
                                       reverted_entries=sum(1 for e in st if e.id not in kept))
        rep.update(drc_in=g["drc_in"], drc_out=g["drc_out"], drc_in_reused=g["drc_in_reused"], drc_runs=g["drc_runs"],
                   noise=g["noise"], capped=g.get("capped"), recovery=g.get("recovery"), worse_full=g.get("worse_full"), gate_rounds=g["rounds"],
                   entries=len(jr.entries), kept=len(kept), gate_time_limited=bool(g.get("time_limited")))
        if (deadline is not None and left() < 0) or g.get("time_limited"):
            cacheable = False
        rep["journal"] = [dict(id=e.id, stage=e.stage, net=e.net, deps=sorted(e.deps), kept=e.id in kept,
                               n_before=len(e.before), n_after=len(e.after), round=1, **e.meta) for e in jr.entries]
        # re-plan: entries reverted with a change they built on lose their copper, where the chained passes
        # would have planned the later stage around the gated earlier one. The stages after the earliest one
        # with reverts run again on the gated board, behind a second gate whose input DRC is the first's last
        g2 = None
        ran = rep["parts"]["ran"]
        rev_st = [p for p in ran if any(e.stage == p and e.id not in kept for e in jr.entries)]
        later = ran[ran.index(rev_st[0]) + 1:] if rev_st else []
        if o.get("replan", True) and later and g.get("report") is not None \
                and left() > sum(est.get(p, 10.0) for p in later) + est["gate"]:
            t1 = clock_now()
            cur2 = J.write(g["text"], wd / "r2" / "in" / "board.kicad_pcb", project)
            jr2 = J.Journal(g["text"], margin=jr.margin)
            r2 = dict(parts=[], entries={})
            for part in later:
                dst = drc.stage_board(cur2, project, wd / "r2" / part / "out")
                try:
                    rr = _pass(part, cur2, dst, o, wd / "r2" / part / "work",
                               timeout=max(1, int(left() - est["gate"])) if deadline else 3600, log=log)
                except Exception as e:      # noqa: BLE001
                    r2.setdefault("failed", {})[part] = f"{type(e).__name__}: {e}"[:300]
                    continue
                n0 = len(jr2.entries)
                jr2.add([x for x in rr.pop("_entries", [])])
                r2["entries"][part] = len(jr2.entries) - n0
                r2["parts"].append(part)
                cur2 = dst
            if jr2.entries:
                g2 = J.gate(cur2, project, jr2, wd / "gate2", base_report=g["report"],
                            budget=max(10, int(o["drc_budget"]) - int(g.get("probes") or 0)),
                            deadline=deadline, log=log, recover=int(o["recover"]), known_noise=g["noise"])
                kept2 = g2["kept"]
                J.write(g2["text"], out, project)
                for part in r2["parts"]:
                    st = [e for e in jr2.entries if e.stage == part]
                    rep["stages"][part].update(replan_entries=len(st),
                                               replan_kept=sum(1 for e in st if e.id in kept2))
                r2.update(kept=len(kept2), drc_runs=g2["drc_runs"], gate_rounds=g2["rounds"])
                rep.update(drc_out=g2["drc_out"], drc_runs=rep["drc_runs"] + g2["drc_runs"],
                           kept=rep["kept"] + len(kept2), entries=rep["entries"] + len(jr2.entries))
                rep["journal"] += [dict(id=e.id, stage=e.stage, net=e.net, deps=sorted(e.deps), kept=e.id in kept2,
                                        n_before=len(e.before), n_after=len(e.after), round=2, **e.meta)
                                   for e in jr2.entries]
                if g2.get("time_limited"):
                    cacheable = False
            rep["replan"] = r2
            rep["seconds"]["replan"] = round(clock_now() - t1, 1)
        # (e) hazards
        for part, why in rep["parts"]["skipped"].items():
            rep["hazards"].append(H.make(
                "finish_part_skipped", "warn" if part == "power" else "info", "data",
                f"Finish part '{part}' did not run: {why}" + (
                    "; rails and grounds keep their routed widths and no ground vias or stitching were added."
                    if part == "power" else "."),
                objects=[part], evidence=dict(part=part, reason=why, estimate_s=est.get(part)),
                fix=f"Give the finish stage more time (python -m kae.route.finish ... --time) or run '{part}' alone."))
        for part, why in rep["parts"]["failed"].items():
            rep["hazards"].append(H.make("finish_part_failed", "warn", "data", f"Finish part '{part}' failed: {why}",
                                         objects=[part], evidence=dict(error=why),
                                         fix="Report the board; the other parts and the gate ran without it."))
        for gg in (g, g2):
            if gg is None:
                continue
            if gg.get("gate_error"):
                rep["gate_error"] = gg["gate_error"]
                rep["hazards"].append(H.make(
                    "finish_failed", "warn", "data",
                    f"The finish gate could not finish ({gg['gate_error']}); the board has only the changes KiCad's "
                    f"DRC had already verified ({len(gg['kept'])} entries).",
                    objects=["finish"], evidence=dict(error=gg["gate_error"], kept=len(gg["kept"]), drc_runs=gg["drc_runs"]),
                    fix="Give the finish stage more time; unverified changes were dropped, the routed copper is intact."))
        if g["noise"]:
            rep["hazards"].append(H.make(
                "drc_noisy_checks", "info", "data",
                f"KiCad's DRC reported a different set of {', '.join(g['noise'])} violations on two runs of the "
                f"same board; finish judged those checks by count against the larger run.",
                objects=list(g["noise"]), evidence=dict(types=list(g["noise"])),
                fix="None needed; re-run kicad-cli pcb drc to see the spread."))
        rev = [e for e in jr.entries if e.id not in kept]
        if rev:
            by = {}
            for e in rev:
                by[e.stage] = by.get(e.stage, 0) + 1
            rep["hazards"].append(H.make(
                "finish_reverted", "info", "data",
                f"KiCad's DRC gate reverted {len(rev)} of {len(jr.entries)} finish changes "
                f"({', '.join(f'{k} {v}' for k, v in by.items())}); their copper stays as routed.",
                objects=sorted({e.net for e in rev})[:12], evidence=dict(by_stage=by, worse=g.get("worse_full")),
                fix="None needed; the reverted copper is the router's."))
    finally:
        rep["seconds"]["total"] = round(clock_now() - t0, 1)
        if own:
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
    if not out.exists():
        J.write(Path(inp).read_text(encoding="utf-8"), out, project)
    return rep, cacheable


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.route.finish", description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help="the routed board")
    ap.add_argument("output")
    ap.add_argument("--project", help="the task board whose .kicad_pro/.kicad_dru are the rules (default: INPUT's)")
    ap.add_argument("--time", type=float, help="seconds at most (parts that do not fit are skipped)")
    ap.add_argument("--parts", default=",".join(PARTS), help="comma list of tails, taut, power, trim (in order)")
    ap.add_argument("--input-drc", help="a KiCad DRC JSON report of INPUT with the task's rules (reused by the gate)")
    ap.add_argument("--drc-s", type=float, help="seconds one KiCad DRC of this board takes (for the estimates)")
    ap.add_argument("--drc-budget", type=int, default=DEFAULTS["drc_budget"])
    ap.add_argument("--zone-above", type=float, default=DEFAULTS["zone_above_a"],
                    help="A: rails above this get pours instead of wider tracks (negative: never)")
    ap.add_argument("--operating", help="operating facts JSON (default: KAE_OPERATING of the project)")
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    if getattr(a, "time", None):
        _start_run(float(a.time))
    rep = run(a.input, a.output, project=a.project, time_s=a.time, base_report=a.input_drc or None,
              drc_s=a.drc_s, workdir=a.workdir,
              opts=dict(parts=tuple(p for p in a.parts.split(",") if p), drc_budget=a.drc_budget,
                        zone_above_a=None if a.zone_above < 0 else a.zone_above, operating=a.operating))
    txt = json.dumps(rep, default=str)
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=1, default=str))
    print(txt, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
