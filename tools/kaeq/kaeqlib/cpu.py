# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CPU admission: the run-queue quantile and its controller, and timed jobs' pooled bursts."""


def quantile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0.0


def adapt_runq_q(q, samples, pool, cfg):
    """The next runq_q from the last runq_adapt_s of (runnable threads, jobs waiting for a CPU start) samples:
    oversubscribed too often -> more cautious (+0.05), idle CPUs too often while jobs wait -> bolder (-0.05).
    Returns (q, oversubscribed share, idle-while-waiting share)."""
    if not samples:
        return q, 0.0, 0.0
    over = sum(1 for r, _ in samples if r > pool) / len(samples)
    idle = sum(1 for r, w in samples if w and r < pool - cfg["runq_idle_cpus"]) / len(samples)
    if over > cfg["runq_over_target"]:
        q = min(0.95, q + 0.05)
    elif idle > cfg["runq_idle_target"]:
        q = max(0.5, q - 0.05)
    return q, over, idle


def burst_fits(jobs, new, cap):
    """Whether timed jobs' CPU fits: jobs and new are (mean, peak) cores; their means add up, their bursts
    (peak - mean) are pooled as independent (root of the summed squares), as phases rarely coincide."""
    allj = list(jobs) + [new]
    return sum(m for m, _ in allj) + sum(max(0.0, p - m) ** 2 for m, p in allj) ** 0.5 <= cap
