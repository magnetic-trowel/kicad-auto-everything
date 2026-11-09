# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paired statistics (kaebench.stats) and the paired A/B report (report.compare)."""
import pytest

from kaebench import report, stats


def test_mcnemar_exact_matches_the_binomial():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(0, 6) == pytest.approx(2 / 64)      # 6 discordant, all one way
    assert stats.mcnemar_exact(1, 9) == pytest.approx(2 * 11 / 1024)
    assert stats.mcnemar_exact(5, 5) == 1.0


def test_sign_flip_exact_and_monte_carlo():
    assert stats.sign_flip([0, 0, 0]) == 1.0
    assert stats.sign_flip([1] * 6) == pytest.approx(2 / 64)
    p = stats.sign_flip([0.1] * 30, seed=1)                        # Monte Carlo branch (m > 16)
    assert p < 0.001
    assert stats.sign_flip([0.1, -0.1] * 15, seed=1) > 0.5
    assert stats.sign_flip([0.1] * 30, seed=1) == p                  # seeded: repeatable


def test_bootstrap_ci_clusters_and_holm():
    lo, hi = stats.bootstrap_ci([1.0] * 10)
    assert lo == hi == 1.0
    d = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    lo1, hi1 = stats.bootstrap_ci(d, seed=0)
    lo2, hi2 = stats.bootstrap_ci(d, clusters=["r1", "r1", "r1", "r2", "r2", "r2"], seed=0)
    assert hi2 - lo2 > hi1 - lo1                                     # two clusters: wider
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_cp_at_k_is_the_unbiased_estimator():
    assert stats.cp_at_k(5, 0, 1) == 0.0 and stats.cp_at_k(5, 5, 3) == 1.0
    assert stats.cp_at_k(5, 1, 1) == pytest.approx(0.2)
    assert stats.cp_at_k(5, 1, 5) == 1.0 and stats.cp_at_k(3, 1, 5) is None


def _row(adapter, bid, attempt, clean, status="ok", comp=None, vias=10, wl=100.0, repo=None):
    return dict(adapter=adapter, kind="route", id=bid, split="A", attempt=attempt, status=status, repo=repo,
                score=None if status != "ok" else dict(valid=True, clean=clean, completion=comp if comp is not None else
                                                       (1.0 if clean else 0.5), errors=0 if clean else 2,
                                                       errors_by_type={} if clean else {"clearance": 2},
                                                       unconnected=0 if clean else 3, start_unconnected=20,
                                                       track_length_mm=wl, vias=vias))


def test_compare_pairs_boards_charges_failures_and_sets_infra_aside():
    rows = []
    for i in range(12):                                   # B wins 10 boards A loses, ties on 2
        rows += [_row("A", f"b{i}", 0, i >= 10), _row("B", f"b{i}", 0, True, vias=12, wl=103.0)]
    rows.append(_row("A", "only-a", 0, True))             # B never ran it: left out, listed
    rows.append(_row("A", "fail-b", 0, True))
    rows.append(_row("B", "fail-b", 0, False, status="no_output"))  # B failed it: a loss of B
    rows.append(_row("A", "infra", 0, True))
    rows.append(_row("B", "infra", 0, False, status="score_error"))
    res = report.compare(rows, "A", "B")
    assert res["boards"] == 13 and res["infra"] == ["infra"] and res["only_a"] == ["only-a"]
    t = res["tests"]
    assert len(t["cp1"]["gained"]) == 10 and t["cp1"]["lost"] == ["fail-b"]
    assert t["cp1"]["p"] == pytest.approx(stats.mcnemar_exact(1, 10), abs=1e-4)
    assert t["cp1"]["verdict"] == "B better"
    g = res["guardrails"]
    assert g["both_clean"] == 2 and g["wl_ratio_b_over_a"] == pytest.approx(1.03)
    assert g["vias_per_connection_delta"] == pytest.approx(0.1)
    md = report.compare_markdown(res)
    assert "cp1_mean (primary)" in md and "McNemar" in md and "fail-b" in md and "1 only in A" in md


def test_compare_cp1_mean_and_cpk_over_attempts():
    rows = [_row("A", "b", 0, False), _row("A", "b", 1, True), _row("B", "b", 0, True), _row("B", "b", 1, True)]
    res = report.compare(rows, "A", "B")
    t = res["tests"]
    assert res["k"] == 2
    assert (t["cp1"]["mean_a"], t["cp1"]["mean_b"]) == (0.0, 1.0)
    assert (t["cpk"]["mean_a"], t["cpk"]["mean_b"]) == (1.0, 1.0)
    assert (t["cp1_mean"]["mean_a"], t["cp1_mean"]["mean_b"]) == (0.5, 1.0)
