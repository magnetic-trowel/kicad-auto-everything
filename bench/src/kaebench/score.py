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
         board's copper layers (copper on a new net is kept and counted: it cannot
         connect anything)
  place  pad nets and every non-pose property untouched; locked footprints unmoved; no
         footprints added or removed; no copper added

Clean pass = valid, fully connected, and no error-level DRC violations (board's own
severities; library-environment checks excluded). Each score also reports how much of the
output matches the human layout exactly (`copy`), a check for leaked reference answers.
"""
import json
import os
import shutil
import threading
from pathlib import Path

from . import tools
from .boardfiles import board_path, install_rules

SCORE_VERSION = 7
# KiCad 10's DRC report stops listing unconnected items at 499 and other violations at 199
# per type (drc_engine ERROR_LIMIT / EXTENDED_ERROR_LIMIT).
DRC_UNCONNECTED_CAP = 499
DRC_TYPE_CAPS = (199, 499)

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
    tr = tools.run_ops(op, board_path(method_dir), input_board, staged, *extra)
    (scoring_dir / "rebuild.json").write_text(json.dumps(tr, indent=1))  # what was transplanted, what else changed
    if tr.get("loadable"):
        install_rules(rules_dir, scoring_dir)
    return staged, tr


def _uncapped(board, drc_unconnected, cache=None):
    """Unconnected count without DRC's cap: DRC's own count below the cap, else pcbnew's
    connectivity count after a zone fill (identical to DRC's where both are below the cap).
    Returns (count, was_capped)."""
    if drc_unconnected < DRC_UNCONNECTED_CAP:
        return drc_unconnected, False
    if cache is not None and Path(cache).exists():
        return json.loads(Path(cache).read_text())["unconnected"], True
    n = tools.run_ops("unconnected", board)["unconnected"]
    if cache is not None:
        tmp = Path(f"{cache}.{os.getpid()}.{threading.get_ident()}")
        tmp.write_text(json.dumps(dict(unconnected=n)))
        os.replace(tmp, cache)  # atomic: arms scoring the same board at once
    return n, True


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
                  rules_dir, scoring_dir, reference_board=None, allow_copy=False):
    """Score a routed board against its unrouted input and the human reference."""
    staged, tr = _rebuild("transplant-routing", output_board, input_board, rules_dir, scoring_dir,
                          reference_board)
    if not tr.get("loadable"):
        return _unloadable(tr, clean=False, completion=0.0)
    st, drc = _measure(staged, scoring_dir)
    unconnected, out_capped = _uncapped(staged, drc["unconnected"])
    start, start_capped = _uncapped(input_board, start_unconnected,
                                    cache=Path(input_board).parent / "unconnected.json")
    out, foreign = tr["output"], tr["foreign"]
    integrity = dict(
        placement=out["placement_hash"] == input_stats["placement_hash"],
        pad_nets=out["padnet_hash"] == input_stats["padnet_hash"],
        layers=tr["bad_layer"] == 0,
        untouched=foreign["count"] == 0,
    )
    valid = all(integrity.values())
    completion = max(0.0, min(1.0, 1.0 - unconnected / max(1, start)))
    ref_wl = ref_stats.get("track_length_mm") or 0
    return dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        new_net_items=tr["new_net_items"],
        clean=valid and unconnected == 0 and drc["errors"] == 0,
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
    outside = outside_count(st["placement"], record["reference"].get("pads_outside", {}))
    place_errors = {k: v for k, v in drc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    ref = record["reference"]["stats"]
    score = dict(
        valid=valid, integrity=integrity, foreign=foreign, **_copy_fields(tr, allow_copy),
        locked_moved=tr["locked_moved"], legal=valid and outside == 0 and not place_errors,
        outside=outside, placement_errors=place_errors, hpwl_mm=st["hpwl_mm"],
        hpwl_ratio=round(st["hpwl_mm"] / ref["hpwl_mm"], 4) if ref["hpwl_mm"] else None,
        unconnected=_uncapped(staged, drc["unconnected"])[0], drc_unconnected=drc["unconnected"],
        drc_capped=_capped_types(drc), score_version=SCORE_VERSION,
    )
    return score, st


def score_joint_task(task_dir, output_board, scoring_dir, record, allow_copy=False):
    """Place and route together, from the place task's input. The output's footprint poses
    are transplanted into the place input (placement integrity and legality, judged on the
    placement alone), then its tracks and vias into that placement (route integrity and
    route metrics). Valid only if both are; clean = valid, legal, fully routed, no errors."""
    task_dir, scoring_dir = Path(task_dir), Path(scoring_dir)
    ref_board = board_path(task_dir / "reference")
    placed_dir = scoring_dir / "placement"
    staged_p, tp = _rebuild("transplant-placement", output_board, board_path(task_dir / "place" / "input"),
                            task_dir / "reference", placed_dir, ref_board)
    if not tp.get("loadable"):
        return _unloadable(tp, clean=False, legal=False, completion=0.0)
    pst, pdrc = _measure(staged_p, placed_dir)
    start, _ = _uncapped(staged_p, pdrc["unconnected"])
    tin = record["tasks"]["place"]["input_stats"]
    place_integrity = dict(
        pad_nets=tp["output"]["padnet_hash"] == tin["padnet_hash"],
        locked=tp["n_locked_moved"] == 0,
        footprints=tp["n_missing"] == 0 and tp["n_extra"] == 0,
        untouched=tp["foreign"]["count"] == 0,
    )
    s = score_routing(output_board, staged_p, pst, start, record["reference"]["stats"], task_dir / "reference",
                      scoring_dir / "routing", reference_board=ref_board, allow_copy=allow_copy)
    if not s.get("valid") and s.get("integrity", {}).get("loadable") is False:
        return s
    outside = outside_count(pst["placement"], record["reference"].get("pads_outside", {}))
    place_errors = {k: v for k, v in pdrc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    valid = all(place_integrity.values()) and s["valid"]
    legal = valid and outside == 0 and not place_errors
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
