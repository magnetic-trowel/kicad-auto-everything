# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent scoring: rebuild the board from the task input, then run DRC under the
reference rules.

The scorer never judges the file a method wrote. It transplants only what the task lets
a method change into a fresh copy of the task input: tracks, arcs and vias for routing;
footprint poses (position, rotation, side) for placement. Edits to anything else (rules,
outline, keepouts, zones, pads, layers, nets) therefore cannot change a score. They are
still detected, and make the result invalid:

  route  placement, pad nets, every other board object untouched; routing only on the
         board's copper layers and nets
  place  pad nets and every non-pose property untouched; locked footprints unmoved; no
         footprints added or removed; no copper added

Clean pass = valid, fully connected, and no error-level DRC violations (board's own
severities; library-environment checks excluded). Each score also reports how much of the
output matches the human layout exactly (`copy`), a check for leaked reference answers.
"""
import shutil
from pathlib import Path

from . import tools
from .boardfiles import board_path, install_rules

SCORE_VERSION = 2

# KiCad 10 DRC type keys that make a placement illegal (as named in its JSON report).
PLACEMENT_ERROR_TYPES = ("courtyards_overlap", "copper_edge_clearance", "clearance", "hole_clearance",
                         "hole_to_hole", "holes_co_located", "items_not_allowed", "malformed_courtyard",
                         "npth_inside_courtyard", "pth_inside_courtyard", "shorting_items")


def _fresh_dir(d):
    d = Path(d)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def _rebuild(op, output_board, input_board, rules_dir, scoring_dir, reference_board=None):
    """Transplant the allowed changes of output_board into input_board (pcbnew op), install
    the reference rules beside the result. Returns (staged board path, transplant report)."""
    scoring_dir = _fresh_dir(scoring_dir)
    staged = board_path(scoring_dir)
    extra = [reference_board] if reference_board else []
    tr = tools.run_ops(op, output_board, input_board, staged, *extra)
    if tr.get("loadable"):
        install_rules(rules_dir, scoring_dir)
    return staged, tr


def _measure(staged, scoring_dir):
    st = tools.run_ops("stats", staged)
    drc = tools.summarize_drc(tools.run_drc(staged, Path(scoring_dir) / "drc.json"))
    return st, drc


def _unloadable(tr, **extra):
    return dict(valid=False, integrity=dict(loadable=False), error=tr.get("error"),
                score_version=SCORE_VERSION, **extra)


def _copy_fields(tr, allow_copy):
    copy = tr.get("copy")
    return dict(copy=copy, suspect_copy=bool(copy and copy.get("suspect")) and not allow_copy)


def score_routing(output_board, input_board, input_stats, start_unconnected, ref_stats,
                  rules_dir, scoring_dir, reference_board=None, allow_copy=False):
    """Score a routed board against its unrouted input and the human reference."""
    staged, tr = _rebuild("transplant-routing", output_board, input_board, rules_dir, scoring_dir,
                          reference_board)
    if not tr.get("loadable"):
        return _unloadable(tr, clean=False, completion=0.0)
    st, drc = _measure(staged, scoring_dir)
    out, foreign = tr["output"], tr["foreign"]
    integrity = dict(
        placement=out["placement_hash"] == input_stats["placement_hash"],
        pad_nets=out["padnet_hash"] == input_stats["padnet_hash"],
        layers=tr["bad_layer"] == 0,
        nets=tr["unknown_net"] == 0,
        untouched=foreign["count"] == 0,
    )
    valid = all(integrity.values())
    completion = max(0.0, min(1.0, 1.0 - drc["unconnected"] / max(1, start_unconnected)))
    ref_wl = ref_stats.get("track_length_mm") or 0
    return dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        clean=valid and drc["unconnected"] == 0 and drc["errors"] == 0,
        completion=round(completion, 4) if valid else 0.0,
        start_unconnected=start_unconnected,
        unconnected=drc["unconnected"], errors=drc["errors"], warnings=drc["warnings"],
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
                         reference_board=board_path(task_dir / "reference"), allow_copy=allow_copy)


def score_place_task(task_dir, placed_board, scoring_dir, record, allow_copy=False):
    """Score placement legality and quality (before routing). Also returns the stats of the
    rebuilt board (None if the output could not be loaded), which a routing probe starts from;
    the rebuilt board itself is board.kicad_pcb in scoring_dir."""
    task_dir = Path(task_dir)
    staged, tr = _rebuild("transplant-placement", placed_board, board_path(task_dir / "place" / "input"),
                          task_dir / "reference", scoring_dir, board_path(task_dir / "reference"))
    if not tr.get("loadable"):
        return _unloadable(tr, legal=False), None
    st, drc = _measure(staged, scoring_dir)
    tin = record["tasks"]["place"]["input_stats"]
    foreign = tr["foreign"]
    integrity = dict(
        pad_nets=tr["output"]["padnet_hash"] == tin["padnet_hash"],
        locked=tr["n_locked_moved"] == 0,
        footprints=tr["n_missing"] == 0 and tr["n_extra"] == 0,
        no_copper=tr["routing_added"] == 0,
        untouched=foreign["count"] == 0,
    )
    valid = all(integrity.values())
    outside = sum(1 for r in st["placement"] if r.get("inside") is False)
    place_errors = {k: v for k, v in drc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    ref = record["reference"]["stats"]
    score = dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        locked_moved=tr["locked_moved"], legal=valid and outside == 0 and not place_errors,
        outside=outside, placement_errors=place_errors, hpwl_mm=st["hpwl_mm"],
        hpwl_ratio=round(st["hpwl_mm"] / ref["hpwl_mm"], 4) if ref["hpwl_mm"] else None,
        unconnected=drc["unconnected"], score_version=SCORE_VERSION,
    )
    return score, st


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
