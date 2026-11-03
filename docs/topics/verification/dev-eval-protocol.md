# Development evaluation protocol and benchmark-host compute

Scope: metrics, statistics, resolving power and attempt policy for the development plan; compute caps, Freerouting/KiCad resource settings, concurrency and cost on the shared benchmark host (status 2026-10-21). Not here: the phased plan and harness defects -> [dev-eval-plan.md](dev-eval-plan.md); metric definitions -> [quality-metrics.md](quality-metrics.md).
Keys: evaluation protocol, valid, cp1_mean, cp1, cpk, cp@5, completion, guardrails, wl_ratio, via delta, legal, probe, McNemar, sign-flip permutation, clustered bootstrap, Holm, MDE, A/A flip rate, resolving power, systemd-run, AllowedCPUs, MemoryMax, JAVA_TOOL_OPTIONS, MaximumThreads, KICAD_CONFIG_HOME, APPTAINER_BIND, concurrency, core-hours
Tags: [P] primary, [I] inference, [M] measured in this repo.

## Evaluation protocol

**Metrics:**
- **Gate:** `valid` under whitelist integrity.
- **Primary:** `cp1_mean`, the clean rate averaged over all attempts. Always report `cp1` and `cpk` too.
- **Secondary:**
  - unbiased cp@5;
  - completion (uncapped);
  - per-net clean rate (sensitive on C);
  - errors by type;
  - timeouts and infra errors, reported separately.
- **Guardrails, fixed in advance:** median `wl_ratio` ≤ +5%, mean via delta per connection ≤ +10%, on clean boards only.
- **Placement:**
  - gate: `legal` (fixed-severity profile);
  - primary: probe `cp1_mean` with a fixed probe;
  - also probe completion relative to the human placement.

**Statistics:**
- The board is the unit, paired across methods.
- Exact McNemar for binary outcomes; sign-flip permutation for fractional ones.
- 95% CIs by bootstrap clustered by repo.
- One primary per experiment; secondaries Holm-corrected.
- Every comparison lists the flipped boards and their error types.
- Minimum claimable effect = max(MDE, 2 × the A/A flip rate).

**Resolving power** (α = 0.05, power 0.8, 10–25% discordant boards):

| Boards | Detectable effect |
|---|---|
| 2,412 drc-clean boards | 2–3 pp |
| ≈ 1,200-board test split | 3–4 pp |
| ≈ 200-board dev subset | 6–10 pp |
| 112 boards (old manifest) | 8–13 pp |
| Splits A or B alone | almost nothing |
| 5 pp effects | need 250–780 boards |

**Attempts:**
- Deterministic engines: k = 5 *configs*, a portfolio rather than seeds.
- LLM arms: k = 3 on dev, 5 on val/test.
- More boards beat more attempts.

## Compute on the benchmark host

- **Hard caps.** Wrap every session in `systemd-run --user --scope -p AllowedCPUs=<lease> -p MemoryMax=96G -p MemoryHigh=88G` (verified to work on this host). The lease is within cores 0–49, recorded in a lease file so our concurrent sessions don't overlap.
- **Freerouting:**
  - `JAVA_TOOL_OPTIONS="-Xmx3g -XX:ActiveProcessorCount=1 -XX:+UseSerialGC"`, with `-mt 1`;
  - verify the jpackage launcher honours it.
  - Peak heap is 0.4–1.2 GB per board [P].
- **KiCad DRC threads:** cap with the advanced-config `MaximumThreads` in a harness-private `KICAD_CONFIG_HOME`; verify the name in 10.0.7. Score in a separate pool of ≤ 6 × 4 threads.
- **Disk:** move the workdir and `KAE_HOME` to local NVMe (`/var/tmp/$USER/kae-work`, `APPTAINER_BIND=/var/tmp/$USER`). Record this in `CLAUDE.local.md`. Every attempt starts about 5 KiCad processes from the 2.5 GB image, which is slow over NFS.
- **Concurrency to start** (re-tune after measuring peak RSS on the 10 largest boards):

  | Workload | Concurrency |
  |---|---|
  | Freerouting on A/B | 40 |
  | Freerouting on C | 24–32 |
  | Placers with 4-worker CP-SAT | 12 |
  | LLM arms | 8–16, rate-limited |

- **Wall-clock is noisy here.** Budget in deterministic units (passes, iterations, tokens), with `prlimit --cpu`. Keep wall timeouts as a 3× safety net. Run baseline and candidate interleaved in the same window.
- **Cost scale:**

  | Run | Core-hours | Wall time |
  |---|---|---|
  | Smoke (8 boards, k = 1) | — | < 10 min |
  | dev A+B (k = 3) | — | 20–40 min |
  | `dev-200` route run (k = 3) | ≈ 60 | ≈ 1.5 h |
  | Prepare all 2,412 drc-clean boards | ≈ 40 | ≈ 1 h |
  | Full drc-clean route run (k = 3) [I] | ≈ 700 | ≈ 15 h, overnight; phase gates only |
  | C diagnosis | 40–80 | 2–3.5 h |

  With 2,412 boards, cores are the binding limit: iterate on `dev-200`, read `val` weekly and `test` once per gate.

## Sources
- Statistics: Miller, [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640); Chen et al. 2021 unbiased pass@k (arXiv 2107.03374); Agarwal et al. 2021 (arXiv 2108.13264)
- KiCad [advanced_config](https://docs.kicad.org/doxygen/advanced__config_8cpp.html); Freerouting [settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md)
