# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent scoring: re-open the saved board with the reference rules and run DRC.

A routing result is valid only if the router left placement, pad nets and board setup
untouched. A placement result is valid only if pad nets, locked footprints and board
setup are untouched. Clean pass = valid, fully connected, and no error-level DRC
violations (board's own severities; library-environment checks excluded).
"""
import shutil
from pathlib import Path

from . import tools
from .boardfiles import block_hash, board_path, install_rules
from .prepare import pose

PLACEMENT_ERROR_TYPES = ("courtyards_overlap", "edge_clearance", "clearance", "hole_clearance",
                         "holes_co_located", "malformed_courtyard", "npth_inside_courtyard",
                         "pth_inside_courtyard", "shorting_items")


def _stage(output_board, rules_dir, scoring_dir):
    scoring_dir = Path(scoring_dir)
    if scoring_dir.exists():
        shutil.rmtree(scoring_dir)
    scoring_dir.mkdir(parents=True)
    shutil.copy2(output_board, board_path(scoring_dir))
    install_rules(rules_dir, scoring_dir)
    return board_path(scoring_dir)


def measure(board, rules_dir, scoring_dir):
    """Stage `board` with the given rules, then stats + DRC in fresh processes."""
    staged = _stage(board, rules_dir, scoring_dir)
    st = tools.run_ops("stats", staged)
    drc = tools.summarize_drc(tools.run_drc(staged, Path(scoring_dir) / "drc.json"))
    return staged, st, drc


def score_routing(output_board, input_board, input_stats, start_unconnected, ref_stats,
                  rules_dir, scoring_dir):
    """Score a routed board against its unrouted input and the human reference."""
    staged, st, drc = measure(output_board, rules_dir, scoring_dir)
    integrity = dict(
        placement=st["placement_hash"] == input_stats["placement_hash"],
        pad_nets=st["padnet_hash"] == input_stats["padnet_hash"],
        setup=block_hash(staged, "setup") == block_hash(input_board, "setup"),
    )
    valid = all(integrity.values())
    completion = max(0.0, min(1.0, 1.0 - drc["unconnected"] / max(1, start_unconnected)))
    ref_wl = ref_stats.get("track_length_mm") or 0
    return dict(
        valid=valid, integrity=integrity,
        clean=valid and drc["unconnected"] == 0 and drc["errors"] == 0,
        completion=round(completion, 4) if valid else 0.0,
        start_unconnected=start_unconnected,
        unconnected=drc["unconnected"], errors=drc["errors"], warnings=drc["warnings"],
        errors_by_type=drc["errors_by_type"],
        track_length_mm=st["track_length_mm"], vias=st["vias"],
        wl_ratio=round(st["track_length_mm"] / ref_wl, 4) if ref_wl else None,
        via_delta=st["vias"] - ref_stats.get("vias", 0),
    )


def score_route_task(task_dir, output_board, scoring_dir, record):
    task_dir = Path(task_dir)
    t = record["tasks"]["route"]
    return score_routing(output_board, board_path(task_dir / "route" / "input"), t["input_stats"],
                         t["input_drc"]["unconnected"], record["reference"]["stats"],
                         task_dir / "reference", scoring_dir)


def score_place_task(task_dir, placed_board, scoring_dir, record):
    """Score placement legality and quality (before routing). Also returns the stats and
    unconnected count of the placed board, which a routing probe starts from."""
    task_dir = Path(task_dir)
    staged, st, drc = measure(placed_board, task_dir / "reference", scoring_dir)
    tin = record["tasks"]["place"]["input_stats"]
    locked_in = {r["uuid"]: r for r in tin.get("locked_placement", [])}
    out_rows = {r["uuid"]: pose(r) for r in st["placement"]}
    integrity = dict(
        pad_nets=st["padnet_hash"] == tin["padnet_hash"],
        locked=all(out_rows.get(u) == r for u, r in locked_in.items()),
        setup=block_hash(staged, "setup") == block_hash(board_path(task_dir / "place" / "input"), "setup"),
    )
    valid = all(integrity.values())
    outside = sum(1 for r in st["placement"] if r.get("inside") is False)
    place_errors = {k: v for k, v in drc["errors_by_type"].items() if k in PLACEMENT_ERROR_TYPES}
    ref = record["reference"]["stats"]
    score = dict(
        valid=valid, integrity=integrity, legal=valid and outside == 0 and not place_errors,
        outside=outside, placement_errors=place_errors, hpwl_mm=st["hpwl_mm"],
        hpwl_ratio=round(st["hpwl_mm"] / ref["hpwl_mm"], 4) if ref["hpwl_mm"] else None,
        unconnected=drc["unconnected"],
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
