# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory leases: the pure planning behind them (grants, freezes, evictions, forecasts, adaptive set-aside)."""
from .consts import MEM_BINS, TICK


def mem_hist(samples, peak):
    """How a job spent its life: counts of RSS samples in MEM_BINS equal slices of its peak."""
    h = [0] * MEM_BINS
    for r in samples:
        h[min(MEM_BINS - 1, int(r / peak * MEM_BINS))] += 1
    return h


def pooled_headroom(jobs, z, rho, rho_of=None):
    """Memory to set aside for running jobs' growth when they rarely peak together.
    jobs: [(owner, expect_mb, rss_mb, profile or None)]: expect = the most it may reach (its peak x
    margin, or its declared --mem while it warms up); profile = share of lifetime its owner's jobs
    spend at each slice of their peak (MEM_BINS weights). A job without a profile counts its whole
    headroom (expect - rss). A profiled job's RSS at a random moment is expect x (slice upper edge),
    so its growth is max(0, that - rss): mean + z std over all of them, jobs of one owner correlated
    by rho (or rho_of[owner], measured), owners independent; never less than the largest single
    headroom, never more than the sum. Returns (set aside, sum of headrooms)."""
    full = worst = 0.0
    biggest = 0.0
    mu = 0.0
    var = 0.0
    by_owner = {}
    for owner, expect, rss, prof in jobs:
        room = max(0.0, expect - rss)
        worst += room
        if prof is None:
            full += room
            continue
        biggest = max(biggest, room)
        g = [max(0.0, expect * (k + 1) / MEM_BINS - rss) for k in range(MEM_BINS)]  # growth if at slice k
        m = sum(w * x for w, x in zip(prof, g))
        m2 = sum(w * x * x for w, x in zip(prof, g))
        sd = max(0.0, m2 - m * m) ** 0.5
        mu += m
        o = by_owner.setdefault(owner, [0.0, 0.0])
        o[0] += sd
        o[1] += sd * sd
    for owner, (lin, sq) in by_owner.items():
        r = (rho_of or {}).get(owner, rho)
        var += (1 - r) * sq + r * lin * lin
    pooled = max(biggest, mu + z * var ** 0.5)
    return min(worst, full + pooled), worst


def max_rise(series, window):
    """Largest G[j] - G[i] with i <= j and t_j - t_i <= window, over [(t, G)] sorted by t (a sliding minimum)."""
    from collections import deque
    best, q = 0.0, deque()  # indexes of increasing G within the window
    for j, (t, g) in enumerate(series):
        while q and series[q[0]][0] < t - window:
            q.popleft()
        while q and series[q[-1]][1] >= g:
            q.pop()
        q.append(j)
        best = max(best, g - series[q[0]][1])
    return best


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


def owner_correlation(series, prior, window=90, min_samples=30):
    """Correlation between one owner's concurrently running jobs, measured: the mean Pearson r over
    pairs of their last `window` RSS samples (taken on the same ticks), negative r counted as 0 and
    pairs where either job is flat (coefficient of variation < 5%) skipped, shrunk towards `prior`
    as 2 pseudo-pairs. series: [RSS samples] per job. Returns (rho, pairs used)."""
    ok = []
    for s in series:
        if len(s) >= min_samples:
            t = s[-window:]
            m = sum(t) / len(t)
            if m > 0 and (sum((x - m) ** 2 for x in t) / len(t)) ** 0.5 / m >= 0.05:
                ok.append(t)
    rs = []
    for i in range(len(ok)):
        for k in range(i + 1, len(ok)):
            n = min(len(ok[i]), len(ok[k]))
            r = pearson(ok[i][-n:], ok[k][-n:])
            if r is not None:
                rs.append(max(0.0, r))
    return (sum(rs) + 2 * prior) / (len(rs) + 2), len(rs)


def warm_headroom(jobs, z):
    """What jobs still warming up may yet grow by. jobs: [(rss, full_headroom, mem_mb, ratios or None)]:
    ratios = the owner's finished jobs' peak/--mem; without them a job counts its full headroom. With
    them, a job's peak is --mem x a random draw from those ratios (job sizes vary independently from
    one board to the next): mean + z std of the growth, at least the largest single headroom,
    capped at its full headroom per job and at the sum overall."""
    full = worst = biggest = mu = var = 0.0
    for rss, room, mem, rs in jobs:
        worst += room
        if not rs:
            full += room
            continue
        g = [min(room, max(0.0, mem * r - rss)) for r in rs]
        m = sum(g) / len(g)
        mu += m
        var += sum((x - m) ** 2 for x in g) / len(g)
        biggest = max(biggest, room)
    return min(worst, full + max(biggest, mu + z * var ** 0.5))


def lease_plan(jobs, real_mb, cfg, now, buffer=0.0, timed_held=None, credit=0.0, free_now=None):
    """One pass of the memory leases. jobs: [{id, prio, started, grant, use, slack_since, stall_since, grew}] (MB, s;
    grew: MB the job grew since the last tick). real_mb: memory really free beyond the reserve (MemAvailable). A grant
    is a limit, not a reservation: what is free for grants and new jobs is real_mb minus `buffer` (room for the
    fleet's growth between two ticks), minus the unused grants of jobs younger than lease_warm_s (they are still
    growing into them), minus lease_hold_frac of every other job's unused grant. Should real_mb fall below the
    buffer anyway (jobs grew into room they were granted but nobody set aside), the jobs that grew this tick are
    frozen at what they use, lowest priority and newest first; while real_mb stays above half the buffer, the
    oldest of highest priority keeps running, so peaks take turns. Grants far above use
    for a while (and past the job's first warmup_s) are trimmed (that memory is free again); jobs near their grant get one more step each, by
    priority then age, while memory is free; of the rest, those at their grant (within lease_freeze_mb, or two
    ticks of their growth "rate", MB/s) are stalled and wait frozen, the others run on in the room they have. A job
    stalled lease_stall_s with nothing freeing names a victim among jobs of no higher priority: the one furthest
    past mem_overrun x its declared --mem ("declared", MB; a runaway), else the newest other job (a job within its declaration that only
    waits for other users' memory keeps waiting).
    Jobs with timed=True (class "timed") are never stalled: their unused grant counts as taken (timed_hold_frac),
    they get memory before batch jobs, and one that needs more than is free names the newest batch job (a frozen
    one first) as `timed_victim`, to be requeued. Only batch jobs are frozen or chosen as victims.
    Returns {grants: {id: MB}, slack_since, stall_since, stalled: [ids], free, held, victim, timed_victim}."""
    grants = {j["id"]: j["grant"] for j in jobs}
    slack = {j["id"]: j.get("slack_since") or 0.0 for j in jobs}
    stall = {j["id"]: j.get("stall_since") or 0.0 for j in jobs}
    rel = cfg["lease_release_gb"] * 1024
    for j in jobs:
        g, u = grants[j["id"]], j["use"]
        young = now - (j["started"] or now) < cfg.get("warmup_s", 300)   # still growing into its declared --mem
        if g - u > max(rel, cfg.get("lease_release_frac", 0.25) * u) and not young:
            slack[j["id"]] = slack[j["id"]] or now
            if now - slack[j["id"]] >= cfg["lease_release_after_s"]:
                ng = max(u * 1.25, u + 1024)
                if ng < g:
                    grants[j["id"]] = ng      # what it no longer holds is free again (held, below)
                slack[j["id"]] = 0.0
        else:
            slack[j["id"]] = 0.0
    warm = cfg.get("lease_warm_s", 120)
    hold = cfg.get("lease_hold_frac", 1.0)
    thold = cfg.get("timed_hold_frac", 1.0)
    young = lambda j: now - (j["started"] or now) < warm
    # kept running: timed, or expensive batch, or batch in its run window after a thaw (but below half the buffer
    # the window gives way: a just-thawed job may be frozen again)
    keep = lambda j: j.get("timed") or j.get("dear") or (j.get("keep") and real_mb >= buffer / 2)
    if timed_held is None:
        held = sum(max(0.0, grants[j["id"]] - j["use"])
                   * (1.0 if young(j) or j.get("protected") else thold if j.get("timed") else hold) for j in jobs
                   if young(j) or j.get("timed") or j.get("reserve_mb") is None)
    else:   # timed jobs past warm-up: their forecast growth (timed_held), computed by the daemon
        held = timed_held + sum(max(0.0, grants[j["id"]] - j["use"]) * (1.0 if young(j) else hold)
                                for j in jobs if young(j) or not j.get("timed") and j.get("reserve_mb") is None)
    # expensive batch jobs: the growth they are forecast to need is set aside in full, so new jobs do not take it
    held += sum(j["reserve_mb"] for j in jobs if j.get("reserve_mb") is not None and not young(j) and not j.get("timed"))
    held += sum(j.get("swapped", 0.0) for j in jobs if not j.get("compressed"))   # thawed: still coming back
    # (a squeezed running job's cold pages are passed as swapped=0: they stay out unless it touches them)
    free_mb = real_mb - buffer - held + credit     # credit: squeezable memory of timed jobs (squeeze_credit)
    # what the guard, the evictions and kept jobs' room-making go by: memory really free beyond the reserve (real_mb
    # also leaves out what jobs started this tick declared, before their scope shows: right for admission, but
    # not a shortage to requeue or freeze for)
    real_mb = real_mb if free_now is None else free_now
    stalled = []
    if real_mb < buffer:     # the fleet grew into the buffer: freeze who grew, the least valuable first
        grew = sorted((j for j in jobs if j.get("grew", 0.0) > 0 and not keep(j)),
                      key=lambda j: (j["prio"], -(j["started"] or 0)))
        if grew and real_mb > buffer / 2:
            grew.pop()                   # the oldest of highest priority grows on while there is half a buffer
        for j in grew:
            grants[j["id"]] = min(grants[j["id"]], j["use"])
            stalled.append(j["id"])
            stall[j["id"]] = stall[j["id"]] or now
    # below half the buffer, freezing growers is not enough (a frozen job keeps its memory, and a timed job is
    # never frozen): requeue the job whose restart loses the least work per MB it frees (it starts again from
    # scratch, so its results are unaffected); a job requeued evict_protect_after times is spared
    evict = None
    if real_mb < buffer / 2:
        cand = [j for j in jobs if not j.get("protected") and j["use"] > 256]
        if cand:                         # (jobs kept running for being expensive go last)
            evict = min(cand, key=lambda j: (bool(j.get("keep")), j.get("invest", 0.0) / j["use"]))["id"]
    short = []                           # kept jobs that need memory nobody can give
    by_id = {j["id"]: j for j in jobs}
    # memory goes first to a compressed frozen job (it waits to come back), then kept jobs, then by priority, age
    for j in sorted(jobs, key=lambda j: (not j.get("compressed"), not keep(j), -j["prio"], j["started"] or 0)):
        if j["id"] in stalled:
            continue
        g, u = grants[j["id"]], j["use"] + (j.get("swapped", 0.0) if j.get("compressed") else 0.0)  # it holds that
        if j.get("mpress", 0.0) > cfg.get("lease_press_pct", 10.0):
            u = max(u, g)                # thrashing at its limit: it needs more whatever its use says
        margin = max(cfg["lease_margin_mb"], cfg.get("lease_margin_frac", 0.0) * g)
        if u < g - margin:
            stall[j["id"]] = 0.0
            continue
        step = max(cfg["lease_step_gb"] * 1024, cfg["lease_step_frac"] * g, u + margin - g)
        if free_mb > 4 * step:           # plenty free: grow well ahead of a fast-growing job
            step = max(step, 0.5 * g)
        back = 0.0   # (a compressed job's u includes what it has in swap: its step makes room for all of it)
        # a batch job gets a whole step or waits frozen: fed in crumbs it would sit throttled at memory.high, which
        # stalls it and builds the pressure systemd-oomd kills for (a timed job is never throttled: crumbs are fine)
        if free_mb - back >= (min(step, 256.0) if keep(j) else step):
            take = min(step, free_mb - back)
            grants[j["id"]] = g + take
            free_mb -= take + back
            stall[j["id"]] = 0.0
        elif keep(j):
            stall[j["id"]] = 0.0         # never frozen: it runs on (unthrottled), and a batch job makes room
            if u >= g - max(cfg.get("lease_freeze_mb", 256), 2 * TICK * j.get("rate", 0.0)):
                short.append(j["id"])
        elif j.get("frozen") or u >= g - max(cfg.get("lease_freeze_mb", 256), 2 * TICK * j.get("rate", 0.0)):
            stalled.append(j["id"])      # at its grant with nothing to give: it waits, frozen (a frozen job stays
                                         # frozen until it gets more: frozen, it shows no growth to judge by)
            stall[j["id"]] = stall[j["id"]] or now
        else:
            stall[j["id"]] = 0.0         # wants more but still has room of its own: it runs on
    victim = None
    # how long a job has waited: its current stall, or all its time frozen since the last victim made room for
    # it (a job thawed for a moment and frozen again, over and over, waits as long as one never thawed)
    waited = {j["id"]: max(now - stall[j["id"]] if stall[j["id"]] else 0.0, j.get("waited_frozen", 0.0)) for j in jobs}
    long_ = [i for i in stalled if waited[i] >= cfg["lease_stall_s"]]
    waiter = None
    if long_:
        by = {j["id"]: j for j in jobs}
        s = waiter = max(long_, key=lambda i: waited[i])
        peers = [j for j in jobs if j["prio"] <= by[s]["prio"] and not keep(j)]
        over = [j for j in peers if j["use"] > j.get("declared", float("inf")) * cfg.get("mem_overrun", 1.5)]
        if over:                    # the job furthest past what it declared (a runaway), whichever it is
            victim = max(over, key=lambda j: j["use"] - j["declared"])["id"]
        else:                       # everyone within their declaration: the newest other job
            others = [j for j in peers if j["id"] != s]
            victim = max(others, key=lambda j: j["started"] or 0)["id"] if others else None
        if victim is not None:
            stall[s] = now          # the next victim only after another lease_stall_s
    # a kept job needs memory and it is really short: make room by freezing the newest batch job not kept (its
    # memory is compressed: about a third comes free); only for a timed job, once all such jobs are frozen, is
    # the newest frozen one requeued (requeueing for expensive batch jobs lost far more work than it saved in
    # trace replays)
    timed_victim = None
    batch = [j for j in jobs if not keep(j) and j["id"] not in (victim, evict)]
    if short and batch and real_mb <= buffer:
        running = [j for j in batch if not j.get("frozen") and j["id"] not in stalled]
        if running:
            j = max(running, key=lambda j: (-j["prio"], j["started"] or 0))
            grants[j["id"]] = min(grants[j["id"]], j["use"])
            stalled.append(j["id"])
            stall[j["id"]] = stall[j["id"]] or now
        elif any(by_id[i].get("timed") for i in short):
            timed_victim = max(batch, key=lambda j: (-j["prio"], j["started"] or 0))["id"]
    return dict(grants=grants, slack_since=slack, stall_since=stall, stalled=stalled, free=free_mb, held=held,
                victim=victim, waiter=waiter if victim is not None else None, timed_victim=timed_victim, short=short,
                evict=evict if evict != victim else None)


def adapt_z(z, hist, cfg, now):
    """The next timed_z (std deviations of forecast growth set aside for timed jobs), from the work lost to
    requeues like adapt_hold: +0.5 above overcommit_loss_target, -0.25 below half of it, within [0, 6]."""
    new, loss = adapt_hold(z / 6.0, hist, cfg, now)
    if loss is None:
        return z, None
    if loss > cfg["overcommit_loss_target"]:
        return min(6.0, z + 0.5), loss
    if loss < cfg["overcommit_loss_target"] / 2:
        return max(0.0, z - 0.25), loss
    return z, loss


def adapt_hold(hold, hist, cfg, now):
    """The next timed_hold_frac: work lost to requeues over overcommit_window_s, as a share of the timed work done,
    against overcommit_loss_target. hist: [(t, cumulative core-s done, cumulative core-s lost)]."""
    old = [h for h in hist if h[0] >= now - cfg["overcommit_window_s"]]
    if len(old) < 2 or old[-1][1] - old[0][1] < 3600:      # under a core-hour of work: no evidence yet
        return hold, None
    loss = (old[-1][2] - old[0][2]) / (old[-1][1] - old[0][1])
    if loss > cfg["overcommit_loss_target"]:
        return min(1.0, hold + 0.1), loss
    if loss < cfg["overcommit_loss_target"] / 2:
        return max(0.0, hold - 0.05), loss
    return hold, loss


def keep_flags(rec, cfg, now, no_freeze_until=0.0, swapped=None):
    """Mark a batch job's lease record (lease_plan's input) as the daemon does: "dear" if it is expected to reach
    keep_gb or has keep_core_h of work in it (kept running: never frozen for a grant), "keep" if dear or still in
    its run window after a thaw, and the share of its forecast growth set aside (keep_reserve_frac; swapped: what
    it has in swap, if not rec's). Timed jobs are kept by lease_plan itself. Returns whether the job is dear."""
    if rec.get("timed"):
        return False
    dear = rec["expect"] >= cfg["keep_gb"] * 1024 or rec["invest"] >= cfg["keep_core_h"] * 3600
    rec["keep"], rec["dear"] = dear or no_freeze_until > now, dear      # (a frozen expensive job is thawed and kept)
    if dear and cfg["keep_reserve_frac"] > 0:
        sw = rec.get("swapped", 0.0) if swapped is None else swapped
        rec["reserve_mb"] = cfg["keep_reserve_frac"] * max(0.0, rec["expect"] - rec["use"] - sw)
    return dear


def expected_size(declared, ratios, max_use, age, cfg):
    """How big a running job is expected to get (MB), from evidence before declarations: with forecast_min_jobs
    of its owner's finished jobs, its --mem x their median peak/--mem (x mem_learn_margin); else, once it has run
    forecast_trust_s, forecast_trust_margin x the most it has used; else its declared --mem. Never below what it
    has used. (Declared --mem alone, counted as growth to come for every job of a new owner, held tens of GB for
    jobs using a tenth of it.)"""
    if ratios and len(ratios) >= cfg["forecast_min_jobs"]:
        e = declared * sorted(ratios)[len(ratios) // 2] * cfg["mem_learn_margin"]
    elif age >= cfg["forecast_trust_s"]:
        e = max_use * cfg["forecast_trust_margin"]
    else:
        e = declared
    return max(e, max_use)
