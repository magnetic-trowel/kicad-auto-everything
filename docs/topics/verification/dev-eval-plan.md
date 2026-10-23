# Development and evaluation plan for placers and routers on sk-tibia

**TL;DR**
- **Fix the harness first (weeks 1–2).** Code review found defects that would mislead every comparison:
  - Place tasks move locked parts, so 24–40 of the 112 qualified boards can't be won.
  - The placement-legality list misnames copper-to-edge clearance.
  - A Freerouting timeout throws away the partial board.
  - Best-of-k attempts are nested runs of one seed.
  - KiCad 10 DRC caps how many items it reports, which skews completion.
  - Integrity checks miss layers, outline, zones and pad geometry.
- **Routing:** cheap wins first (budgets with partial output, DSN fidelity, seeded diversity), then second engines, repair and a gated portfolio ([routing/strategy-candidates](../routing/strategy-candidates.md)).
- **Placement:** geometry kit, CP-SAT-legalized seed, SA, then router-probe-in-the-loop repair, the strategy most likely to matter [I] ([placement/strategy-candidates](../placement/strategy-candidates.md)).
- **LLM work starts at week 8,** after measured, LLM-free headroom. Every LLM arm runs against zero-token controls: heuristic, random, shuffled, compute-matched best-of-N and an oracle. The LLM only emits configurations and intents, never coordinates.
- **Shared host:** at most 50 cores and about 96 GB, enforced with a cgroup and not only with `-j`. Workdir on local NVMe. The local corpus (`~/kae-boards`, 13,749 boards) has 2,412 drc-clean boards across 1,663 repos, enough to resolve 2–3 pp effects. Cores, not boards, now bound how often the full set can run.

Status 2026-10-21. Synthesized from three research passes over the docs, the harness code and recent sources. Tags: [P] primary, [V] vendor or self-report, [I] inference, [M] measured in this repo. Every gain estimate below is a hypothesis to test.

## Key facts

### Where we start

| Item | State |
|---|---|
| Host | sk-tibia: 128 threads, 251 GB, 2 NUMA nodes, **shared**. Budget: ≤ 50 cores, ≤ 96 GB. `$HOME` is NFS, local NVMe has 356 GB free |
| Toolchain | `kaebench doctor` passes: KiCad 10.0.7 (Apptainer image), Freerouting 2.5.0 |
| Corpus | `~/kae-boards` (local only, never committed): 13,749 KiCad-10-loadable boards, 10,902 fully routed, 2,412 drc-clean (2-layer 2,028, 4-layer 332, 6+ 52; median 27 footprints, p90 111; 1,663 repos; 193 noncommercial, private evaluation only). The committed benchmark manifest has 297, of which 112 qualified ([harness](harness.md)) |
| Routing baseline | Freerouting 2.5.0, k = 1, 600 s: A 0.62, B 0.35 with adapter fixes. C 0.04 with the **stock** adapter only; the fixed adapter has never run on C [M] |
| Placement baseline | None run. The place track has defects (below) |

### Harness defects found (verified in code unless marked)

| # | Defect | Where | Effect |
|---|---|---|---|
| H1 | Place tasks move locked footprints unless `--keep-locked` is passed (which also keeps locked copper on route tasks) | `prepare.py:44`, `pcbnew_ops.py:188` | 24–40 of 112 boards unwinnable; the human reference should score invalid. **Fixed in score v2 (task spec 2)** |
| H2 | `PLACEMENT_ERROR_TYPES` lists `edge_clearance`, but KiCad's key is `copper_edge_clearance`. `hole_to_hole` and `items_not_allowed` are missing | `score.py:17` | Edge and keep-out violations never make a placement illegal. **Fixed in score v2** |
| H3 | Timeout returns no board | `adapters.py:120` | Partial routes score as completion 0. Freerouting's `--router.job_timeout` writes output on stop [P] |
| H4 | Best-of-k varies only `-mp` (10, 20, 30, …), and Freerouting seeds `Random(0)` | `adapters.py:72,112` | The k attempts are nested prefixes of one run, not independent samples |
| H5 | KiCad 10 DRC stops counting at 499 clearance/unconnected items and 199 for other types [P, unverified here] | `tools.summarize_drc`, `prepare.py` | `completion` is wrong on big C boards |
| H6 | Integrity covers only placement, pad nets and `(setup)` | `score.py`, `pcbnew_ops stats` | Layers, Edge.Cuts, zones, rule areas, pad geometry and local clearances can be changed without detection. Adapters can also read `tasks/<id>/reference/`. **Fixed in score v2:** rebuild-then-score, foreign-change detection, bwrap sandbox, red-team tests |
| H7 | The placement probe inherits the attempt index and the placer's timeout | `runner._probe` | Placement variance is mixed with router effort |
| H8 | Report bias | `report.py` | `_mean` skips boards with no output, so methods that time out look cleaner. `wl_ratio` and `via_delta` include incomplete boards. Place reports have no @1 |
| H9 | Scoring DRC timeouts and OOMs count as method failures and are cached | `runner.py` | Shared-host load turns into method noise |
| H10 | Provenance gaps: git dirty state, Freerouting version, image digest, task-set hash, filters, `-j`, cgroup | `runner.py` | Runs can't be checked for comparability |
| H11 | `hpwl_ratio` sums GND and power nets over pad centres | `pcbnew_ops stats` | Rewards over-packing. autolayout cut HPWL 21% and got about 2× the unconnected items [P] |
| H12 | Severities come from each board's `.kicad_pro`; `courtyards_overlap` is downgraded on 12 boards, `missing_courtyard` ignored on 90 | `score.py` | "Legal" means different things on different boards |

Doc correction: Freerouting's "92.4% of 979 boards" (2.6.0-RC4) covers tiers A+B only. RC3 reached 69.5% on tier C with 360-minute budgets [P]. Applied in [freerouting](../routing/freerouting.md).

## Plan

### Phase 0: trust the harness (weeks 1–2)

**Rule.** Scoring and integrity changes (`score.py`, `prepare.py`, `tools.summarize_drc`) go in separate commits that say why. They bump a `SCORE_VERSION` recorded per attempt, per CLAUDE.md. Batch them into one scoring-v2 release so the baselines are re-run once.

| # | Work item | Files | Effort |
|---|---|---|---|
| 0.1 | **Done.** H1: always keep locked footprints in place tasks; `task_spec` 2. Still to do: state what the task gives away (outline, sides, zones) | `prepare.py`, `pcbnew_ops.py` | S |
| 0.2 | H2 + H12: fix the type names, and add a fixed-severity placement DRC profile plus a body-overlap check for parts without courtyards | `score.py` | S |
| 0.3 | **Done.** H6: score a board rebuilt from the task input plus the allowed changes; detect every other change (tolerance-aware diff of KiCad re-saves); bwrap sandbox (no network, references hidden); copy check (report-only until calibrated) | `pcbnew_ops.py`, `score.py`, `adapters.py` | M |
| 0.4 | H5: uncapped unconnected count from pcbnew connectivity; flag capped DRC values | `pcbnew_ops.py`, `score.py` | S–M |
| 0.5 | H3: use `--router.job_timeout` with a margin, keep the last SES, add `--router.result_json` | `adapters.py` | S |
| 0.6 | H7: `--probe-passes` and `--probe-timeout`, always also probing the human placement | `runner.py`, `cli.py` | S |
| 0.7 | H8–H10: infra vs method status, `--retry-infra`, CPU-seconds and peak RSS per attempt, full provenance in `run.json`; `report` refuses to mix incomparable runs | `runner.py`, `report.py`, `tools.py` | M |
| 0.8 | Stats: `cp1_mean`, unbiased cp@k, per-type error diff, flipped-board list, exact McNemar, paired sign-flip and repo-clustered bootstrap (stdlib); new `kaebench compare` | new `stats.py`, `report.py` | M |
| 0.9 | **Done (22 cases).** V2 red-team suite: move part, delete keepout, grow outline, edit setup, shrink pad, zero pad clearance, swap net, add layer, bogus net, move locked part, delete footprint, shrink courtyard, add copper, own rules, read/write reference, network. Each is invalid, blocked or ineffective. Add a case per new cheat | `bench/tests/test_redteam.py` | M |
| 0.10 | Resource control (see Compute) | `adapters.py`, `tools.py`, `runner.py`, `CLAUDE.local.md` | M |
| 0.11 | Suites v1 from the 2,412 drc-clean boards: group by repo; seeded split stratified by split×layers×tier into `smoke` (12), `dev` (≈ 600, with a stratified `dev-200` for fast iteration), `val` (≈ 600) and `test` (≈ 1,200, sealed, reads logged in `bench/results/test-ledger.jsonl`). Commit ids only | `bench/scripts/make_splits.py`, `bench/suites/` | S |
| 0.12 | Noise floor: re-score 50 outputs 3× (must be identical); re-prepare 20 boards (hashes match); repeat Freerouting `-mt 1` runs under low and high load; A/A run of one baseline under two names | runs only | 1 day of compute |

**Exit gate:**
- Reference is clean and legal on every qualified board; `noop` scores 0.
- Every red-team case passes (22 at present, item 0.9).
- Scorer repeats are identical.
- A/A flip rate ≤ 3% of boards.

**Kill:** A/A above 5% after fixes means no comparisons until budgets are deterministic: pass counts, iterations and tokens rather than wall clock.

### Phase 1: baselines and diagnosis (weeks 3–4)

Re-run on scoring v2 with the same KiCad, manifest and suite. Register the results in `bench/results/BASELINES.md`:
- `reference`, `noop`, `freerouting`, `freerouting-stock` on route;
- `reference` with probe on place.

**Split C diagnosis** (k = 1, `job_timeout` ≈ 3,500 s, about 2–3.5 h wall at `-j 24`). Classify every failure from the attempt directories:

| Class | Signature | Leads to |
|---|---|---|
| Budget | log says "completed with timeout"; note the stage | R1, R4 |
| Translation loss, connections | Freerouting reports 0 unrouted, KiCad finds unconnected items (split pad–zone, zone–zone, pad–pad) | R2 |
| Translation loss, errors | Freerouting `-drc` reports 0, KiCad finds errors; split by type and shortfall (≤ 5 µm suggests rounding) | R2 |
| Congestion | Unrouted without a timeout, but routes alone on an empty board | R3, R5, then R9 |
| Blocked | Fails even alone: rules, neck-down, geometry | R2, or fix the task |
| Unattainable | Zone islands need stitching vias; unsupported rule classes | Fix the task or harness |

**Ablations** on a 20-board C subset (about 20 core-hours each):
- neck-down off vs on with a floor;
- zones as planes vs stripped vs obstacles;
- fanout on vs off;
- budget 600, 3,600 or 10,800 s.

Commit the cause table as summarized results.

**Reproduction:**
- Build PCBWorld D3 with PCBWorld's chain on local disk, then `prepare-dir` it.
- The reference must reach CP 1.00.
- Add a `pcbworld` scoring profile that promotes dangling items.
- Check score parity on 50 outputs.
- Reproduce Freerouting 2.1.0 `-mp 10`, target within ±0.08 of 0.80 on D3-A [P]. PCBWorld's @1 was 0.75, inside that band, so match @1 and @5 separately; with a fixed `-mp` our attempts may be identical (H4). D3-B (10 boards, about ±0.26 CI) is for reporting only.
- **Kill:** an unexplained gap > 0.15 after one extra week stops strategy work.

**Second engine:** a KRT adapter (MIT; reads `.kicad_pcb` directly, so no DSN loss). PCBWorld measured 0.74 on D3-A and 0.20 on D3-B [P]. Weak single baselines mislead.

### Phase 2a: routing strategies (weeks 3–8)

R1 budgets with partial output → split C diagnosis → R2 DSN fidelity pack → R3 seeded diversity → R4 fastroute → R5 DRC-driven repair → R6 portfolio selector, built only if the oracle portfolio from logs shows ≥ 0.05. R7 (PNS residual completion, blocked on KiCad 9) and R9 (own PathFinder router, only if congestion causes ≥ 40% of C failures) are gated. Mechanisms, reuse, effort, expected gains and kill criteria: [routing/strategy-candidates](../routing/strategy-candidates.md).

### Phase 2b: placement strategies (weeks 3–10)

Baselines B0–B5 first (noop, reference + probe, random + legalizer, pyplacer, kicad-tools, Cypress). Then P0 geometry kit → P1 constructive seed + CP-SAT legalizer → P2 slot/orientation clean-up → P3 multi-seed SA → P4 router-probe-in-the-loop repair. P5 Cypress is time-boxed to 3 days for a CPU build; P6 analytical placer and P7 weight tuning are gated. Prerequisites: mechanical anchors, signal-only HPWL, and KRT as a second probe. Details and kill criteria: [placement/strategy-candidates](../placement/strategy-candidates.md).

### Phase 3: LLM in the loop (weeks 8–13, only after headroom is shown)

**Headroom first (CPU only):**
- **Hindsight oracle:** per-board best config from the R3 grid, minus the best single global config. This tests "setup is the bottleneck" ([deeppcb](../landscape/deeppcb.md) [V]).
- **Human-hint ceiling:** layer preferences and via budgets derived from human copper, fed into the DSN.

Levers under +5 pp of oracle headroom are dropped. Under +10 pp, they are not worth an LLM.

**LLM adapter contract:**
- It writes `{output}`, `intent.json` (committed decisions in a versioned schema) and `trace.jsonl`.
- Every model call goes through a logging gateway: pinned model ID, token and $ caps, response cache. The runner keeps these files in the attempt dir.
- Token ceiling: 50k per board-attempt.
- It runs in the Phase 0 sandbox, so it can't read the reference.

**Arms run on every experiment, paired.** An `intent-replay` adapter makes the controls free.

| Arm | Purpose |
|---|---|
| B0 engine alone | Baseline |
| B1 heuristic intents (regex net roles, rule-based config) | Is the gain from the structure or from the LLM? |
| B2 random intents from the same menu | Does semantic content matter? |
| B3 another board's LLM intents | Do hints of this shape help on their own? |
| B4 compute-matched best-of-N | Is it just extra engine calls? |
| O oracle intents from human copper | Ceiling; run first |
| L, L-small, L-1shot | Model and feedback effects |

**Experiments, cheapest first:**
1. LLM as router configurator and priority-setter (bandit arms) ([agent-loop-patterns](../llm/agent-loop-patterns.md)).
2. Net-role accuracy vs regex against designer netclasses ([net-role-classification](../llm/net-role-classification.md)).
3. Bounded repair menus on near-miss outputs, a DRC-Aid analog.
4. Placement intent layer: groups, anchors, regions as weak anchors (weight set by sweep against a random-region control), net weights feeding P1–P3 ([llm-guided-placement](../placement/llm-guided-placement.md)).
5. Relations vs coordinates on real A/B boards, using the legalizer ([interfaces-relations-vs-coordinates](../llm/interfaces-relations-vs-coordinates.md)).

**Success:** L beats the strongest of B1–B4 on val by ≥ 5 pp, with a CI that excludes 0, and within the guardrails. Two iterations that don't beat B1/B2 kill that lever.

**Contamination:**
- Memorization probes: ask the model to name the project from its netlist; mirror and perturb boards.
- Add `commit_date` to the manifest for a time-split suite.
- Keep `test` ids out of anything the model sees.

### Phase 4: physics, corpus, sealed test (weeks 10–16)

- **Intent and physics MVP,** reference-relative. Each checker is validated by V1 mutants: decap pin distance, diff-pair skew, power-net minimum width, vias per pair ([critic-stack](critic-stack.md)).
- **Use the routed-but-not-clean boards** (8,490 of the 10,902 routed): a reference-relative track that scores "no DRC error instances beyond the human layout's". It is a new metric, so it goes in its own commit next to `clean`, never replacing it. Add commit dates for the time-split suite ([open-board-sources](../data/open-board-sources.md)).
- **Sealed test read, then write-up:**
  - CIs and per-type errors;
  - $ per extra clean board;
  - summarized results in `bench/results/`.

## Evaluation protocol

**Metrics:**
- **Gate:** `valid` under whitelist integrity.
- **Primary:** `cp1_mean`, the clean rate averaged over all attempts. Always report `cp1` and `cpk` too.
- **Secondary:**
  - unbiased cp@5 for sampled methods (it assumes n ≥ 5 exchangeable attempts; for a deterministic engine's config portfolio it is just best-of-5 configs);
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

## Compute on sk-tibia

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

## Recommendations for our system

- **Week 1 order:**
  1. 0.10 resource control and local workdir;
  2. 0.1 + 0.2 + 0.4 as scoring v2 (separate commits);
  3. 0.5 partial output;
  4. 0.3 integrity and sandbox;
  5. 0.9 red team;
  6. the baseline re-run.
- **Week 2:** stats/compare, suites v1, noise floor.
- **Ask before launching** any run longer than the smoke suite on the shared host.
- **Commit** only code, suites and summarized results; never boards.

## Conflicts and open questions

- **Locked-board count:** 24–39 vs 40 boards depending on the parser. Settle it with the Phase 0 reference run.
- **Unverified items:**
  - the DRC cap values;
  - whether `job_timeout` always yields an SES (pass 1 has run for 1,748 s on one board);
  - the `MaximumThreads` name;
  - whether Freerouting caps edge clearance at 250 µm;
  - fanout via sizes vs board rules.
- **Uncertain tools:** fastroute and autolayout results are self-reported on 1–20 boards. Cypress CPU feasibility is unknown, and sk-tibia has no GPU.
- **Corpus bias:** 84% of drc-clean boards are 2-layer (only 52 have 6+ layers), so report results per layer class; dense-board claims need the 6+ stratum or the routed-not-clean track.
- **Information leaks:** place tasks keep the human side assignment, zones and silkscreen, which leaks floorplan information. State this in results, or strip them in a harder task variant.
- **Contamination:** if this repo becomes public, suite files may enter pretraining; keep `test` ids private.

## Sources

- Harness code: [bench/src/kaebench/](../../../bench/src/kaebench/) (line references above, read 2026-10-21)
- Freerouting: [settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md), [nightly benchmarks](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md), [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)
- KiCad 10 DRC: [drc_engine.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp), [advanced_config](https://docs.kicad.org/doxygen/advanced__config_8cpp.html)
- fastroute: [repo](https://github.com/parisxmas/fastroute). KRT: [repo](https://github.com/drandyhaas/KiCadRoutingTools), [placement-optimization.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md). kicad-tools: [placement_score_calibration.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/placement_score_calibration.md). autolayout: [ROADMAP](https://github.com/bwattendorf/autolayout/blob/main/ROADMAP.md)
- Placers: [Cypress](https://github.com/NVlabs/Cypress), [pyplacer](https://github.com/ajokela/pyplacer), [VeoPlace](https://arxiv.org/pdf/2603.28733), [OmniLayout](https://arxiv.org/abs/2607.03261)
- Statistics: Miller, [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640); Chen et al. 2021 unbiased pass@k (arXiv 2107.03374); Agarwal et al. 2021 (arXiv 2108.13264)

See also: [benchmark-plan](benchmark-plan.md), [harness](harness.md), [evaluation-stack](evaluation-stack.md), [hybrid-architecture-options](../architecture/hybrid-architecture-options.md), [original ideas](../../ideas/original/README.md)
