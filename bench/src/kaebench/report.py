# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate attempt results into leaderboard tables (@1 and best-of-k)."""
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .score import place_potential, potential


def load_rows(run_dir):
    """Read every attempt.json under a run (works for interrupted runs too)."""
    return [json.loads(p.read_text()) for p in sorted(Path(run_dir).glob("*/*/*/attempt-*/attempt.json"))]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


def _strict_mean(scores, key):
    """Share of `key` (clean_strict, legal_strict) over the scores; None when any scored result
    predates it (score v10), so a column never mixes the two definitions. A missing score
    (no output) counts as not clean."""
    if any(sc and key not in sc and sc.get("valid") is not False for sc in scores):
        return None
    return _mean([1.0 if sc.get(key) else 0.0 for sc in scores])


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def _route_best(attempts):
    return max(attempts, key=lambda r: potential(r.get("score")))


def _place_best(attempts):
    return max(attempts, key=lambda r: place_potential(r.get("score"), (r.get("probe") or {}).get("score")))


def summarize(rows):
    """Return {(adapter, kind, split): metrics} including an 'all' split."""
    by_board = defaultdict(list)
    for r in rows:
        by_board[(r["adapter"], r["kind"], r["id"], r["split"])].append(r)
    groups = defaultdict(list)
    for (adapter, kind, bid, split), atts in by_board.items():
        atts.sort(key=lambda r: r["attempt"])
        for sp in (split, "all"):
            groups[(adapter, kind, sp)].append(atts)
    out, best_by = {}, {}
    for key, boards in sorted(groups.items()):
        adapter, kind, split = key
        # cp1 is attempt 0's: a board whose attempt 0 is missing (an interrupted run) counts as not clean
        # and is reported (missing_a0), not silently replaced by a later attempt
        first = [b[0] if b[0]["attempt"] == 0 else {} for b in boards]
        k = max(len(b) for b in boards)
        every = [r for b in boards for r in b]
        m = dict(boards=len(boards), k=k,
                 failures=sum(1 for r in every if r["status"] != "ok"),
                 missing_a0=sum(1 for r in first if not r),
                 timeouts=sum(1 for r in every if (r.get("adapter_meta") or {}).get("timed_out")),
                 capped=sum(1 for r in every if (r.get("score") or {}).get("drc_capped")),
                 partial=sum(1 for r in every if (r.get("adapter_meta") or {}).get("partial")),
                 time_s=_mean([r.get("runtime_s") for r in every]),
                 cpu_s=_mean([(r.get("method_usage") or {}).get("cpu_s") for r in every]),
                 rss_mb_max=max([(r.get("method_usage") or {}).get("max_rss_mb") or 0 for r in every] or [0]) or None,
                 score_cpu_s=_mean([(r.get("scoring_usage") or {}).get("cpu_s") for r in every]),
                 suspect=sum(1 for r in every if (r.get("score") or {}).get("suspect_copy")),
                 unsandboxed=sum(1 for r in every if (r.get("adapter_meta") or {}).get("sandboxed") is False))
        if kind in ("route", "joint", "joint-fixed"):
            best = [_route_best(b) for b in boards]
            sc1 = [r.get("score") or {} for r in first]
            sck = [r.get("score") or {} for r in best]
            m.update(cp1=_mean([1.0 if s.get("clean") else 0.0 for s in sc1]),
                     cpk=_mean([1.0 if s.get("clean") else 0.0 for s in sck]),
                     # fixed-severity profile (score v10); None for results scored before it
                     cp1_strict=_strict_mean(sc1, "clean_strict"), cpk_strict=_strict_mean(sck, "clean_strict"),
                     completion=_mean([s.get("completion", 0.0) for s in sck]),
                     errors=_mean([s.get("errors") for s in sck]),
                     scored=sum(1 for s in sck if s.get("errors") is not None),
                     invalid=sum(1 for s in sck if s and not s.get("valid")),
                     wl_ratio=_median([s.get("wl_ratio") for s in sck]),
                     via_delta=_mean([s.get("via_delta") for s in sck]))
            if kind != "route":
                m.update(legal=_mean([1.0 if s.get("legal") else 0.0 for s in sck]),
                         legal_strict=_strict_mean(sck, "legal_strict"),
                         hpwl_ratio=_median([s.get("hpwl_ratio") for s in sck]))
        else:
            best = [_place_best(b) for b in boards]
            sck = [r.get("score") or {} for r in best]
            prb = [((r.get("probe") or {}).get("score")) or {} for r in best]
            m.update(legal=_mean([1.0 if s.get("legal") else 0.0 for s in sck]),
                     legal_strict=_strict_mean(sck, "legal_strict"),
                     invalid=sum(1 for s in sck if s and not s.get("valid")),
                     hpwl_ratio=_median([s.get("hpwl_ratio") for s in sck]),
                     outside=_mean([s.get("outside") for s in sck]),
                     scored=sum(1 for s in sck if s.get("hpwl_mm") is not None),
                     probe_cp=_mean([1.0 if p.get("clean") else 0.0 for p in prb]) if any(prb) else None,
                     probe_completion=_mean([p.get("completion", 0.0) for p in prb]) if any(prb) else None)
        out[key] = m
        best_by[key] = {b[0]["id"]: r.get("score") or {} for b, r in zip(boards, best)}
    _common_means(out, best_by)
    return out


# Means of the best attempts' scores that skip boards without a value (no output, unloadable): over
# each adapter's own boards they favour a method that fails on hard boards, so they are also taken
# over the boards every adapter of the same kind and split scored (`common` of them).
COMMON = {"route": dict(errors=_mean, wl_ratio=_median, via_delta=_mean),
          "place": dict(hpwl_ratio=_median, outside=_mean)}
COMMON["joint"] = COMMON["joint-fixed"] = dict(COMMON["route"], hpwl_ratio=_median)
COMMON["place-fixed"] = COMMON["place"]


def _common_means(out, best_by):
    by_group = defaultdict(list)
    for key in out:
        by_group[(key[1], key[2])].append(key)
    for (kind, _), keys in by_group.items():
        need = "hpwl_mm" if kind in ("place", "place-fixed") else "errors"
        common = set.intersection(*({b for b, s in best_by[k].items() if s.get(need) is not None} for k in keys))
        for k in keys:
            out[k]["common"] = len(common)
            for metric, agg in COMMON[kind].items():
                out[k][f"{metric}_common"] = agg([best_by[k][b].get(metric) for b in common])


ROUTE_COLS = ("adapter", "split", "boards", "k", "cp1", "cpk", "cp1_strict", "cpk_strict", "completion", "errors", "scored", "errors_common",
              "common", "invalid",
              "suspect", "wl_ratio", "via_delta", "time_s", "cpu_s", "rss_mb_max", "score_cpu_s", "partial",
              "timeouts", "capped", "failures", "missing_a0")
JOINT_COLS = ("adapter", "split", "boards", "k", "cp1", "cpk", "cp1_strict", "cpk_strict", "legal", "legal_strict",
              "completion", "errors", "scored",
              "errors_common", "common", "invalid",
              "suspect", "hpwl_ratio", "wl_ratio", "via_delta", "time_s", "cpu_s", "rss_mb_max", "timeouts",
              "failures", "missing_a0")
PLACE_COLS = ("adapter", "split", "boards", "k", "legal", "legal_strict", "invalid", "suspect", "hpwl_ratio", "outside", "scored",
              "hpwl_ratio_common", "outside_common", "common",
              "probe_cp", "probe_completion", "time_s", "cpu_s", "rss_mb_max", "score_cpu_s", "failures")


def to_markdown(summary):
    lines = []
    for kind, cols in (("route", ROUTE_COLS), ("place", PLACE_COLS), ("joint", JOINT_COLS),
                       ("place-fixed", PLACE_COLS), ("joint-fixed", JOINT_COLS)):
        rows = [(key, m) for key, m in summary.items() if key[1] == kind]
        if not rows:
            continue
        lines.append(f"### {kind}\n")
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for (adapter, _, split), m in rows:
            vals = dict(m, adapter=adapter, split=split)
            lines.append("| " + " | ".join("" if vals.get(c) is None else str(vals.get(c)) for c in cols) + " |")
        lines.append("")
    unsandboxed = sorted({key[0] for key, m in summary.items() if m.get("unsandboxed")})
    if unsandboxed:
        lines.append(f"**Unsandboxed attempts** ({', '.join(unsandboxed)}): these methods could read "
                     "the reference layouts; do not treat their scores as results.\n")
    lines.append("cp1/cpk: clean pass on attempt 0 / best of k (fully connected, no error-level DRC, "
                 "nothing but routing changed). completion: share of start-of-task unconnected items "
                 "routed; missing_a0: boards without attempt 0, counted not clean in cp1. errors (and wl_ratio, via_delta, hpwl_ratio, outside): over the `scored` boards whose best "
                 "attempt has a value, which differ by adapter (no output drops a board); *_common: the same over "
                 "the `common` boards every adapter in the table scored, the comparable number. invalid: best attempts that changed more than the task allows. suspect: "
                 "attempts that reproduce the human layout. wl_ratio: track length / human. cpu_s / "
                 "rss_mb_max: the method's CPU seconds (mean) and peak memory (max) over all processes it "
                 "ran; score_cpu_s: the scorer's. capped: attempts with an error type at KiCad's DRC report cap "
                 "(199 per type), whose error count is a lower bound; unconnected counts are exact. Scored by "
                 "kicad-cli on boards rebuilt from the task input plus the method's allowed changes.")
    return "\n".join(lines)


def report(run_dirs):
    """Summarize one or more runs. An adapter name used by more than one run is labelled
    `adapter@run`, so a method and its baseline are never pooled into one row."""
    runs = [(Path(d), load_rows(d)) for d in run_dirs]
    names = [p.name for p, _ in runs]
    labels = [n if names.count(n) == 1 else str(p) for (p, _), n in zip(runs, names)]
    adapter_runs = defaultdict(set)
    for label, (_, rs) in zip(labels, runs):
        for r in rs:
            adapter_runs[r["adapter"]].add(label)
    rows = []
    for label, (_, rs) in zip(labels, runs):
        for r in rs:
            shared = len(adapter_runs[r["adapter"]]) > 1
            rows.append(dict(r, run=label, adapter=f"{r['adapter']}@{label}" if shared else r["adapter"]))
    return summarize(rows), rows


def score_versions(rows):
    """Distinct score versions among attempts; more than one means the runs aren't comparable."""
    return sorted({r.get("score_version") for r in rows}, key=str)


# ------------------------------------------------------------------ paired A/B comparison
INFRA_STATUS = ("score_error",)  # the scorer failed (DRC timeout, stall, OOM): not the method's fault


def _per_board(rows):
    """{board: [attempt rows sorted by attempt]} of one adapter's rows."""
    by = defaultdict(list)
    for r in rows:
        by[r["id"]].append(r)
    for v in by.values():
        v.sort(key=lambda r: r["attempt"])
    return by


def _board_metrics(atts, k):
    """Per-board metrics of one arm: cp1 (attempt 0 clean), cp1_mean (clean share over k attempts,
    a missing attempt counted not clean), cpk (any attempt clean), completion of the best."""
    cl = {r["attempt"]: bool((r.get("score") or {}).get("clean")) for r in atts}
    best = (_route_best(atts).get("score") or {}) if atts else {}
    return dict(cp1=1.0 if cl.get(0) else 0.0, cp1_mean=sum(cl.values()) / max(1, k),
                cpk=1.0 if any(cl.values()) else 0.0, completion=best.get("completion", 0.0) or 0.0,
                best=best)


def compare(rows, a, b, seed=0):
    """Paired comparison of adapters `a` (baseline) and `b` over the boards both were run on.

    A failed attempt (no output, adapter error) has a row and counts as not clean, so a method that
    fails on hard boards is charged for them. A board one arm has no row for at all was not run by
    it (an interrupted or unfinished run): it is left out and listed (only_a, only_b). Boards where
    either arm has an infrastructure failure (INFRA_STATUS: the scorer, not the method, failed)
    are left out of every test and listed: rescore them (`kaebench rescore`) and compare again.
    Guardrails are on the boards both arms routed clean (dev-eval-plan, Evaluation protocol):
    the median ratio of B's to A's track length, and the mean via change per connection."""
    from . import stats
    ra = [r for r in rows if r["adapter"] == a]
    rb = [r for r in rows if r["adapter"] == b]
    pa, pb = _per_board(ra), _per_board(rb)
    k = max([r["attempt"] + 1 for r in ra + rb] or [1])
    infra = sorted({r["id"] for r in ra + rb if r.get("status") in INFRA_STATUS})
    boards = sorted((set(pa) & set(pb)) - set(infra))
    clusters = {r["id"]: r.get("repo") or r["id"] for r in ra + rb}
    ma = {bd: _board_metrics(pa.get(bd, []), k) for bd in boards}
    mb = {bd: _board_metrics(pb.get(bd, []), k) for bd in boards}
    res = dict(a=a, b=b, k=k, boards=len(boards), infra=infra,
               only_a=sorted(set(pa) - set(pb) - set(infra)), only_b=sorted(set(pb) - set(pa) - set(infra)))
    tests = {}
    for metric, binary in (("cp1", True), ("cpk", True), ("cp1_mean", False), ("completion", False)):
        tests[metric] = stats.paired({bd: ma[bd][metric] for bd in boards}, {bd: mb[bd][metric] for bd in boards},
                                     boards=boards, clusters=clusters, binary=binary, seed=seed)
    # secondaries (all but the primary cp1_mean) Holm-corrected among themselves
    sec = [m for m in tests if m != "cp1_mean"]
    for m, p in zip(sec, stats.holm([tests[m]["p"] for m in sec])):
        tests[m]["p_holm"] = round(p, 4)
    tests["cp1_mean"]["p_holm"] = tests["cp1_mean"]["p"]
    for t in tests.values():
        t["verdict"] = stats.verdict(t)
    res["tests"] = tests
    both = [bd for bd in boards if ma[bd]["best"].get("clean") and mb[bd]["best"].get("clean")]
    wl = [mb[bd]["best"]["track_length_mm"] / ma[bd]["best"]["track_length_mm"] for bd in both
          if ma[bd]["best"].get("track_length_mm") and mb[bd]["best"].get("track_length_mm") is not None]
    vpc = [(mb[bd]["best"].get("vias", 0) - ma[bd]["best"].get("vias", 0)) / max(1, ma[bd]["best"].get("start_unconnected") or 1)
           for bd in both if ma[bd]["best"].get("vias") is not None and mb[bd]["best"].get("vias") is not None]
    res["guardrails"] = dict(both_clean=len(both), wl_ratio_b_over_a=_median(wl),
                             vias_per_connection_delta=_mean(vpc),
                             vias_per_connection_a=_mean([(ma[bd]["best"].get("vias") or 0) / max(1, ma[bd]["best"].get("start_unconnected") or 1) for bd in both]),
                             wl_limit=1.05, vpc_note="limit: B's vias per connection at most +10 % of A's")
    # the flipped boards (cp1) with their error types, as the protocol asks
    flips = []
    for sign, key in ((+1, "gained"), (-1, "lost")):
        for bd in tests["cp1"][key]:
            s = (pb if sign > 0 else pa).get(bd, [{}])[0].get("score") or {}
            o = (pa if sign > 0 else pb).get(bd, [{}])[0].get("score") or {}
            flips.append(dict(board=bd, to=b if sign > 0 else a, loser_unconnected=o.get("unconnected"),
                              loser_errors_by_type=o.get("errors_by_type") or {}, winner_errors=s.get("errors")))
    res["cp1_flips"] = flips
    return res


def compare_markdown(res):
    t = res["tests"]
    L = [f"### Paired comparison: {res['b']} (B) vs {res['a']} (A)", "",
         f"{res['boards']} boards run by both arms (a failed attempt counts as not clean), k = {res['k']}. "
         f"Infrastructure failures left out: {len(res['infra'])}"
         + (f" ({', '.join(res['infra'][:10])}{' ...' if len(res['infra']) > 10 else ''}; rescore and compare again)" if res["infra"] else "")
         + f". Not run by the other arm, left out: {len(res['only_a'])} only in A, {len(res['only_b'])} only in B"
         + (" (finish both runs before concluding)" if res["only_a"] or res["only_b"] else "") + ".", "",
         "| metric | A | B | B − A | 95 % CI (repo bootstrap) | test | p | p (Holm) | verdict |",
         "|---|---|---|---|---|---|---|---|---|"]
    for m in ("cp1_mean", "cp1", "cpk", "completion"):
        r = t[m]
        extra = f" (+{len(r['gained'])} / −{len(r['lost'])} boards)" if "gained" in r else ""
        L.append(f"| {m}{' (primary)' if m == 'cp1_mean' else ''} | {r['mean_a']} | {r['mean_b']} | {r['diff']}{extra} | "
                 f"{r['ci'][0]} … {r['ci'][1]} | {r['test']} | {r['p']} | {r['p_holm']} | {r['verdict']} |")
    g = res["guardrails"]
    L += ["", f"Guardrails on the {g['both_clean']} boards both arms routed clean: median track length B / A = "
          f"{g['wl_ratio_b_over_a']} (limit 1.05); mean via change per connection B − A = {g['vias_per_connection_delta']} "
          f"(A's mean {g['vias_per_connection_a']} per connection; limit +10 % of it).", ""]
    if res["cp1_flips"]:
        L += ["cp1 flips (the board, who won it, and what the loser's attempt 0 still had):", "",
              "| board | clean only in | loser unconnected | loser errors by type |", "|---|---|---|---|"]
        for f in res["cp1_flips"][:40]:
            L.append(f"| {f['board']} | {f['to']} | {f['loser_unconnected']} | "
                     f"{', '.join(f'{k} {v}' for k, v in sorted(f['loser_errors_by_type'].items())) or '—'} |")
        L.append("")
    L.append("p: exact McNemar for clean/not clean, paired sign-flip permutation for fractions; Holm over the "
             "secondaries (cp1, cpk, completion); cp1_mean is the primary. A difference is significant at p < 0.05; "
             "the protocol's minimum claimable effect is also at least twice the A/A flip rate, which is unmeasured.")
    return "\n".join(L)
