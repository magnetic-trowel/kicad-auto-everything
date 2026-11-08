# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent scoring: rebuild the board from the task input, then run DRC under the
reference rules.

The scorer never judges the file a method wrote. It transplants only what the task lets
a method change into a fresh copy of the task input: tracks, arcs and vias for routing,
plus, in route and joint tasks, the copper zones a method adds and pads' own zone connection;
footprint poses (position, rotation, side) for placement. Edits to anything else (rules,
outline, keepouts, the task's zones, other pad properties, layers, nets) therefore cannot
change a score. They are still detected, and make the result invalid:

  route  placement, pad nets, every other board object untouched; routing only on the
         board's copper layers (copper on a new net is kept and counted: it cannot
         connect anything); added zones legal (below)
  joint  as place (added zones and pads' zone connection excepted: never in the placement that
         is judged), then as route, added zones included (joint and joint-fixed tasks)
  place  pad nets and every non-pose property untouched; locked footprints unmoved; no
         footprints added or removed; no copper added

Added zones (route, joint and joint-fixed tasks, score v10; pcbnew_ops._added_zones). In joint
tasks the placement half ignores them (and pads' zone connection) and judges legality on the
placement alone; the routing half transplants and checks them onto that placement exactly as
in a route task. A route method may add copper
pours. A zone the task input does not have (by uuid; teardrops are routing and stay ignored)
is transplanted with everything it carries (outline, layers, net, priority, clearance, pad
connection and thermal settings, minimum width, island removal) but not its fill: DRC refills
every zone of the rebuilt board (--refill-zones), and the uncapped unconnected count fills
them too, at the start and the end alike, so a pour that joins pads counts as connecting them.
Integrity (`zones`; any violation makes the result invalid and is listed in zone_problems):
  - a copper zone, not a rule area or keepout (those switch DRC checks off locally);
  - only on the board's enabled copper layers;
  - on a net the task has, by name: no new nets and no net-less zones (floating copper connects
    nothing and is not routing);
  - inside the board's outer outline (grown by 10 um for arc rounding; cut-outs inside it may be
    covered, the fill clears them);
  - outside every rule area that forbids copper pours on a shared layer (the method cuts its
    outline around them). This checks the outline; DRC (items_not_allowed) still checks the
    refilled copper against every keepout, and copper clearance, edge clearance and width;
  - where it overlaps another zone on a shared layer, a strictly different priority, so the fill
    never depends on uuid order (KiCad 10.0.7's filler deadlocks on overlapping zones of
    different nets that tie on priority and uuid);
  - a uuid no other zone has.
The task's own zones must stay exactly as given (outline, net, layers, settings; not deleted):
an edit is a foreign change (`untouched`). A pad's own zone connection (zone_connect, e.g. solid
on a heat pad) may change; it is transplanted, and every other pad property stays as given.
No cap on count or area: area is bounded by the outline, and an output whose refill makes DRC
exceed KAE_DRC_TIMEOUT fails to score like any other. `copy` also lists added zones whose
outline matches a human zone on the same net and a shared layer (IoU >= 0.8); one such zone
makes the output a suspect copy.

Clean pass = valid, fully connected, and no error-level DRC violations (board's own
severities; library-environment checks excluded). `clean_strict` / `legal_strict` also need
no violation of STRICT_CHECKS whatever the board's project says (a second DRC with those
checks promoted to error, run only when the project downgrades one of them; otherwise they
equal clean / legal). Each score also reports how much of the
output matches the human layout exactly (`copy`), a check for leaked reference answers.
"""
import json
import os
import shutil
import threading
from pathlib import Path

from . import tools
from .boardfiles import board_path, install_rules, unconnected_ignored

# 8: unconnected counted by pcbnew where the project ignores the check (_uncapped)
# 9: route placement integrity with the place side's pose tolerance (transplant-routing)
# 10: route and joint tasks may add copper zones and set pads' zone connection (see the docstring)
# 11: clean_strict / legal_strict / errors_strict (fixed-severity profile, STRICT_CHECKS)
# 12: the integrated scorer: 10 and 11 together, and duplicate uuids matched by content on both sides
#     (11 had meant different things on the decide and route-finish lines)
SCORE_VERSION = 12
# KiCad 10's DRC report stops listing unconnected items at 499 and other violations at 199
# per type (drc_engine ERROR_LIMIT / EXTENDED_ERROR_LIMIT).
DRC_UNCONNECTED_CAP = 499
DRC_TYPE_CAPS = (199, 499)

# KiCad 10 DRC type keys that make a placement illegal (as named in its JSON report).
PLACEMENT_ERROR_TYPES = ("courtyards_overlap", "copper_edge_clearance", "clearance", "hole_clearance",
                         "hole_to_hole", "holes_co_located", "items_not_allowed", "malformed_courtyard",
                         "npth_inside_courtyard", "pth_inside_courtyard", "shorting_items")


# Checks scored as errors whatever the board's project says (clean_strict, legal_strict): a
# short, a clearance or hole-clearance breach, copper too close to the edge, overlapping
# courtyards and parts in a rule area make a board that does not work or cannot be built as
# drawn. Of 2,454 qualified boards with project files, 184 downgrade courtyards_overlap, 96
# copper_edge_clearance, 69 hole_clearance, 49 clearance and 7 shorting_items, so `clean` means
# different things on different boards (dev-eval-plan H12). Unconnected items are counted by
# pcbnew where the project ignores them (_uncapped), so both columns count them. Custom
# .kicad_dru rules keep their own severities (a designer's per-object waiver).
STRICT_CHECKS = ("shorting_items", "clearance", "hole_clearance", "copper_edge_clearance", "courtyards_overlap",
                 "items_not_allowed")


def _strict_drc(staged, scoring_dir, drc):
    """DRC summary under the fixed-severity profile: `drc` itself when the staged board's project
    downgrades none of STRICT_CHECKS, else a second DRC of a copy whose project has them all at
    error (the board is not re-saved; only the copy's .kicad_pro changes)."""
    pro = Path(staged).with_suffix(".kicad_pro")
    try:
        d = json.loads(pro.read_text(encoding="utf-8", errors="replace")) if pro.exists() else {}
    except ValueError:
        d = {}
    rs = ((d.get("board") or {}).get("design_settings") or {}).get("rule_severities") or {}
    down = [c for c in STRICT_CHECKS if rs.get(c, "error") != "error"]
    if not down:
        return drc, []
    sdir = _fresh_dir(Path(scoring_dir) / "strict")
    sb = board_path(sdir)
    shutil.copy2(staged, sb)
    install_rules(Path(staged).parent, sdir)
    for c in down:
        rs[c] = "error"
    sb.with_suffix(".kicad_pro").write_text(json.dumps(d, indent=2))
    return tools.summarize_drc(tools.run_drc(sb, sdir / "drc.json")), down


def _strict_fields(staged, scoring_dir, drc):
    sdrc, down = _strict_drc(staged, scoring_dir, drc)
    return sdrc, dict(errors_strict=sdrc["errors"], errors_by_type_strict=sdrc["errors_by_type"],
                      strict_promoted=down)


def _fresh_dir(d):
    d = Path(d)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def _rebuild(op, output_board, input_board, rules_dir, scoring_dir, reference_board=None, flags=()):
    """Transplant the allowed changes of output_board into input_board (pcbnew op), install
    the reference rules beside the result. Returns (staged board path, transplant report).

    The output is opened next to the input's project files, never its own: KiCad takes
    board properties (text variables) and other settings from the project, so a board
    opened without them re-saves differently and every output would look changed.
    """
    scoring_dir = _fresh_dir(scoring_dir)
    staged = board_path(scoring_dir)
    method_dir = scoring_dir / "method"
    method_dir.mkdir()
    shutil.copy2(output_board, board_path(method_dir))
    install_rules(Path(input_board).parent, method_dir)
    extra = [reference_board] if reference_board else []
    tr = tools.run_ops(op, board_path(method_dir), input_board, staged, *extra, *flags)
    (scoring_dir / "rebuild.json").write_text(json.dumps(tr, indent=1))  # what was transplanted, what else changed
    if tr.get("loadable"):
        install_rules(rules_dir, scoring_dir)
    return staged, tr


def _uncapped(board, drc_unconnected, cache=None):
    """Unconnected count without DRC's cap: DRC's own count below the cap, else pcbnew's
    connectivity count after a zone fill (identical to DRC's where both are below the cap).
    Also pcbnew's count when the board's project ignores unconnected items, which DRC then does
    not report (3 qualified boards, e.g. gamaphy-freedom-rp2040, read 0 unconnected for every
    output, an empty one included). The start and the output of a task share the reference
    project, so both are counted the same way. Returns (count, was_capped)."""
    capped = drc_unconnected >= DRC_UNCONNECTED_CAP
    if not capped and not unconnected_ignored(board):
        return drc_unconnected, False
    if cache is not None and Path(cache).exists():
        return json.loads(Path(cache).read_text())["unconnected"], capped
    n = tools.run_ops("unconnected", board)["unconnected"]
    if cache is not None:
        tmp = Path(f"{cache}.{os.getpid()}.{threading.get_ident()}")
        tmp.write_text(json.dumps(dict(unconnected=n)))
        os.replace(tmp, cache)  # atomic: arms scoring the same board at once
    return n, capped


def _capped_types(drc):
    """Error types whose count sits exactly at a DRC report cap: their count is a lower bound."""
    return sorted(t for t, n in drc["errors_by_type"].items() if n in DRC_TYPE_CAPS)


def _measure(staged, scoring_dir):
    st = tools.run_ops("stats", staged)
    drc = tools.summarize_drc(tools.run_drc(staged, Path(scoring_dir) / "drc.json"))
    (Path(scoring_dir) / "stats.json").write_text(json.dumps(st, indent=1))  # full KiCad statistics
    return st, drc


def _unloadable(tr, **extra):
    return dict(valid=False, integrity=dict(loadable=False), error=tr.get("error"),
                score_version=SCORE_VERSION, **extra)


def _copy_fields(tr, allow_copy):
    copy = tr.get("copy")
    return dict(copy=copy, suspect_copy=bool(copy and copy.get("suspect")) and not allow_copy)


def score_routing(output_board, input_board, input_stats, start_unconnected, ref_stats,
                  rules_dir, scoring_dir, reference_board=None, allow_copy=False, allow_zones=False):
    """Score a routed board against its unrouted input and the human reference. allow_zones:
    the method may add copper zones and set pads' zone connection (route tasks)."""
    staged, tr = _rebuild("transplant-routing", output_board, input_board, rules_dir, scoring_dir,
                          reference_board, flags=("--zones",) if allow_zones else ())
    if not tr.get("loadable"):
        return _unloadable(tr, clean=False, completion=0.0)
    st, drc = _measure(staged, scoring_dir)
    unconnected, out_capped = _uncapped(staged, drc["unconnected"])
    start, start_capped = _uncapped(input_board, start_unconnected,
                                    cache=Path(input_board).parent / "unconnected.json")
    out, foreign = tr["output"], tr["foreign"]
    integrity = dict(
        placement=tr["n_placement_moved"] == 0,
        pad_nets=out["padnet_hash"] == input_stats["padnet_hash"],
        layers=tr["bad_layer"] == 0,
        untouched=foreign["count"] == 0,
    )
    zones = {}
    if allow_zones:
        integrity["zones"] = tr["n_zone_problems"] == 0
        zones = dict(zones_added=tr["zones_added"], zone_problems=tr["zone_problems"],
                     pad_zone_connections=tr["pad_zone_connections"])
    valid = all(integrity.values())
    completion = max(0.0, min(1.0, 1.0 - unconnected / max(1, start)))
    ref_wl = ref_stats.get("track_length_mm") or 0
    sdrc, strict = _strict_fields(staged, scoring_dir, drc)
    return dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        new_net_items=tr["new_net_items"], **zones,
        clean=valid and unconnected == 0 and drc["errors"] == 0,
        clean_strict=valid and unconnected == 0 and drc["errors"] == 0 and sdrc["errors"] == 0, **strict,
        completion=round(completion, 4) if valid else 0.0,
        start_unconnected=start, unconnected=unconnected,
        drc_unconnected=drc["unconnected"], start_unconnected_drc=start_unconnected,
        unconnected_capped=out_capped or start_capped, drc_capped=_capped_types(drc),
        errors=drc["errors"], warnings=drc["warnings"],
        errors_by_type=drc["errors_by_type"],
        track_length_mm=st["track_length_mm"], vias=st["vias"],
        wl_ratio=round(st["track_length_mm"] / ref_wl, 4) if ref_wl else None,
        via_delta=st["vias"] - ref_stats.get("vias", 0),
        score_version=SCORE_VERSION,
    )


def score_route_task(task_dir, output_board, scoring_dir, record, allow_copy=False):
    task_dir = Path(task_dir)
    t = record["tasks"]["route"]
    return score_routing(output_board, board_path(task_dir / "route" / "input"), t["input_stats"],
                         t["input_drc"]["unconnected"], record["reference"]["stats"],
                         task_dir / "reference", scoring_dir,
                         reference_board=board_path(task_dir / "reference"), allow_copy=allow_copy,
                         allow_zones=True)


def score_place_task(task_dir, placed_board, scoring_dir, record, allow_copy=False, kind="place"):
    """Score placement legality and quality (before routing). Also returns the stats of the
    rebuilt board (None if the output could not be loaded), which a routing probe starts from;
    the rebuilt board itself is board.kicad_pcb in scoring_dir. kind: the place task
    (place or place-fixed) whose input and record the output is judged against."""
    task_dir = Path(task_dir)
    staged, tr = _rebuild("transplant-placement", placed_board, board_path(task_dir / kind / "input"),
                          task_dir / "reference", scoring_dir, board_path(task_dir / "reference"))
    if not tr.get("loadable"):
        return _unloadable(tr, legal=False), None
    st, drc = _measure(staged, scoring_dir)
    tin = record["tasks"][kind]["input_stats"]
    foreign = tr["foreign"]
    integrity = dict(
        pad_nets=tr["output"]["padnet_hash"] == tin["padnet_hash"],
        locked=tr["n_locked_moved"] == 0,
        footprints=tr["n_missing"] == 0 and tr["n_extra"] == 0,
        no_copper=tr["routing_added"] == 0,
        untouched=foreign["count"] == 0,
    )
    valid = all(integrity.values())
    outside = outside_count(st["placement"], record["reference"].get("pads_outside", {}))
    place_errors = {k: v for k, v in drc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    sdrc, strict = _strict_fields(staged, scoring_dir, drc)
    place_errors_strict = {k: v for k, v in sdrc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    ref = record["reference"]["stats"]
    score = dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        locked_moved=tr["locked_moved"], legal=valid and outside == 0 and not place_errors,
        legal_strict=valid and outside == 0 and not place_errors and not place_errors_strict,
        placement_errors_strict=place_errors_strict, strict_promoted=strict["strict_promoted"],
        outside=outside, placement_errors=place_errors, hpwl_mm=st["hpwl_mm"],
        hpwl_ratio=round(st["hpwl_mm"] / ref["hpwl_mm"], 4) if ref["hpwl_mm"] else None,
        unconnected=_uncapped(staged, drc["unconnected"])[0], drc_unconnected=drc["unconnected"],
        drc_capped=_capped_types(drc), score_version=SCORE_VERSION,
    )
    return score, st


def score_joint_task(task_dir, output_board, scoring_dir, record, allow_copy=False, input_kind="place"):
    """Place and route together, from the input of the place task input_kind (place for joint,
    place-fixed for joint-fixed). The output's footprint poses
    are transplanted into the place input (placement integrity and legality, judged on the
    placement alone), then its tracks and vias into that placement (route integrity and
    route metrics). Valid only if both are; clean = valid, legal, fully routed, no errors."""
    task_dir, scoring_dir = Path(task_dir), Path(scoring_dir)
    ref_board = board_path(task_dir / "reference")
    placed_dir = scoring_dir / "placement"
    staged_p, tp = _rebuild("transplant-placement", output_board, board_path(task_dir / input_kind / "input"),
                            task_dir / "reference", placed_dir, ref_board, flags=("--zones",))
    if not tp.get("loadable"):
        return _unloadable(tp, clean=False, legal=False, completion=0.0)
    pst, pdrc = _measure(staged_p, placed_dir)
    start, _ = _uncapped(staged_p, pdrc["unconnected"], cache=placed_dir / "unconnected.json")
    tin = record["tasks"][input_kind]["input_stats"]
    place_integrity = dict(
        pad_nets=tp["output"]["padnet_hash"] == tin["padnet_hash"],
        locked=tp["n_locked_moved"] == 0,
        footprints=tp["n_missing"] == 0 and tp["n_extra"] == 0,
        untouched=tp["foreign"]["count"] == 0,
    )
    s = score_routing(output_board, staged_p, pst, start, record["reference"]["stats"], task_dir / "reference",
                      scoring_dir / "routing", reference_board=ref_board, allow_copy=allow_copy, allow_zones=True)
    if not s.get("valid") and s.get("integrity", {}).get("loadable") is False:
        return s
    outside = outside_count(pst["placement"], record["reference"].get("pads_outside", {}))
    place_errors = {k: v for k, v in pdrc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    psdrc, _ = _strict_drc(staged_p, placed_dir, pdrc)
    place_errors_strict = {k: v for k, v in psdrc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    valid = all(place_integrity.values()) and s["valid"]
    legal = valid and outside == 0 and not place_errors
    legal_strict = legal and not place_errors_strict
    ref = record["reference"]["stats"]
    s.update(
        integrity={**{f"place_{k}": v for k, v in place_integrity.items()},
                   **{f"route_{k}": v for k, v in s["integrity"].items()}},
        place_foreign=tp["foreign"], place_copy=tp.get("copy"),
        suspect_copy=s["suspect_copy"] or (bool((tp.get("copy") or {}).get("suspect")) and not allow_copy),
        locked_moved=tp["locked_moved"], valid=valid, legal=legal, outside=outside,
        placement_errors=place_errors, hpwl_mm=pst["hpwl_mm"],
        hpwl_ratio=round(pst["hpwl_mm"] / ref["hpwl_mm"], 4) if ref["hpwl_mm"] else None,
        clean=legal and s["unconnected"] == 0 and s["errors"] == 0,
        legal_strict=legal_strict, placement_errors_strict=place_errors_strict,
        clean_strict=legal_strict and s.get("clean_strict", False),
        completion=s["completion"] if valid else 0.0,
    )
    return s


def outside_count(placement, allowed):
    """Footprints with more pad centres outside the board outline than the same footprint
    has in the human placement (edge connectors may overhang as far as the designer's do)."""
    return sum(1 for r in placement if (r.get("pads_outside") or 0) > allowed.get(r["uuid"], 0))


def potential(s):
    """Ranking key for best-of-k (higher is better): clean, then completion, errors, length."""
    if not s or not s.get("valid"):
        return (-1, 0, 0, 0)
    return (1 if s.get("clean") else 0, s.get("completion", 0), -s.get("errors", 0),
            -(s.get("track_length_mm") or 0))


def place_potential(s, probe):
    """Best-of-k for placement: legal, then probe routing potential, then shorter HPWL."""
    if not s or not s.get("valid"):
        return (-1,)
    return (1 if s.get("legal") else 0, *potential(probe), -(s.get("hpwl_mm") or 0))
