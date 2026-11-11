#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline replay of three window-choice designs (docs/research/joint/window-choice-proposal-2611.md) on stored
loop reports: upper bounds on what each could add, to compare with what restarts achieve at equal allowance.
    python3 replay_choice.py EXPERIMENT ARM [ARM...]"""
import collections
import sys
from pathlib import Path

import analyze as A


def board_stats(rep):
    its = rep.get("iterations") or []
    cur = (its[0].get("unconnected") or 0) if its else 0
    seen = collections.Counter()
    out = collections.Counter()
    for r in its[1:]:
        if "window" not in r:
            continue
        key = tuple(r["window"].get("parts") or []) or ("reroute",)
        rep_ = seen[key] > 0
        seen[key] += 1
        outcome = (r.get("repair") or {}).get("outcome") or "routed"
        sec = r.get("seconds") or 0.0
        kept = bool(r.get("accepted"))
        gain = 0
        if kept and r.get("unconnected") is not None:
            gain = max(0, cur - r["unconnected"])
            cur = r["unconnected"]
        tag = "repeat" if rep_ else "new"
        out[f"{tag}_n"] += 1
        out[f"{tag}_s"] += sec
        out[f"{tag}_kept"] += kept
        out[f"{tag}_gain"] += gain
        if outcome.startswith("illegal"):
            out["illegal_n"] += 1
            out["illegal_s"] += sec
        elif outcome == "routed":
            out["routed_n"] += 1
            out["routed_kept"] += kept
            out["routed_gain"] += gain
    bl = (rep.get("final") or {}).get("blocked") or {}
    out["final_congestion"] += len(bl.get("congestion") or [])
    out["final_blocked"] += len(bl.get("blocked") or [])
    out["final_undiagnosed"] += int(bl.get("undiagnosed") or 0)
    return out


def main():
    exp, arms = sys.argv[1], sys.argv[2:]
    data = A.load(exp, Path.home() / "kae-baselines")
    for arm in arms:
        T = collections.Counter()
        for d in data.values():
            if arm in d:
                T += board_stats(d[arm]["report"])
        n = T["new_n"] + T["repeat_n"]
        print(f"{exp} / {arm}: windows {n}; new {T['new_n']} (kept {T['new_kept']}, opens removed {T['new_gain']}, "
              f"{T['new_s'] / 3600:.1f} h); repeats {T['repeat_n']} (kept {T['repeat_kept']}, opens removed {T['repeat_gain']}, "
              f"{T['repeat_s'] / 3600:.1f} h); illegal {T['illegal_n']} ({T['illegal_s'] / 3600:.1f} h); routed {T['routed_n']} "
              f"(kept {T['routed_kept']}, opens removed {T['routed_gain']})")
        y_new = T["new_gain"] / max(1, T["new_s"])          # opens removed per window-second, new windows
        y_routed = T["routed_gain"] / max(1, T["routed_n"])  # opens removed per routed window
        print(f"  tabu bound: repeats' time {T['repeat_s'] / 3600:.1f} h spent at the new windows' yield "
              f"({3600 * y_new:.1f} opens/h) = +{T['repeat_s'] * y_new:.0f} opens, minus the {T['repeat_gain']} repeats removed")
        print(f"  sizing bound: {T['illegal_n']} illegal windows made legal at the routed yield ({y_routed:.2f} opens each) "
              f"= +{T['illegal_n'] * y_routed:.0f} opens")
        print(f"  final opens by diagnosis: congestion {T['final_congestion']}, blocked (rule / fixed copper) "
              f"{T['final_blocked']}, undiagnosed {T['final_undiagnosed']}")


if __name__ == "__main__":
    main()
