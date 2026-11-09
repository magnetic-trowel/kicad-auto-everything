# Development and evaluation plan for placers and routers on a shared benchmark host

Scope: status (2026-10-21), harness defects H1–H12 and their fixes, phased plan 0–4 (harness trust, baselines, routing and placement strategies, LLM in the loop, physics/corpus/sealed test). Not here: evaluation protocol (metrics, statistics, resolving power) and host compute rules -> [dev-eval-protocol.md](dev-eval-protocol.md); harness -> [harness.md](harness.md); strategy details -> [../routing/strategy-candidates.md](../routing/strategy-candidates.md), [../placement/strategy-candidates.md](../placement/strategy-candidates.md).
Keys: dev-eval plan, harness defects, H1, H5, H6, H12, score v2, SCORE_VERSION, task_spec 2, red-team, suites v1, smoke, dev, dev-200, val, sealed test, A/A flip rate, split C diagnosis, PCBWorld reproduction, KRT adapter, R1–R9, P0–P7, LLM arms, B0–B4, oracle, intent-replay, contamination, routed-not-clean track
Tags: [P] primary, [V] vendor or self-report, [I] inference, [M] measured in this repo. Synthesized from three research passes over the docs, harness code and recent sources. Every gain estimate is a hypothesis to test.

## Plan summary
1. Fix the harness first (weeks 1–2): defects H1–H12 below would mislead every comparison (locked parts moved → 24–40 of 112 qualified boards unwinnable; misnamed copper-to-edge type; timeouts discard the partial board; best-of-k = nested runs of one seed; KiCad 10 DRC item caps skew completion; integrity missed layers, outline, zones, pad geometry).
2. Routing: cheap wins first (budgets with partial output, DSN fidelity, seeded diversity), then second engines, repair and a gated portfolio ([routing/strategy-candidates](../routing/strategy-candidates.md)).
3. Placement: geometry kit, CP-SAT-legalized seed, SA, then router-probe-in-the-loop repair, the strategy most likely to matter [I] ([placement/strategy-candidates](../placement/strategy-candidates.md)).
4. LLM work starts at week 8, after measured LLM-free headroom; every LLM arm runs against zero-token controls (heuristic, random, shuffled, compute-matched best-of-N, oracle). The LLM emits only configurations and intents, never coordinates.
5. Shared host (status 2026-10-21): ≤50 cores, ~96 GB, enforced by a cgroup, not only `-j`; workdir on local NVMe. Local corpus (2026-10-21 snapshot; current counts → [local-board-corpus](../data/local-board-corpus.md)) 13,749 boards, 2,412 drc-clean across 1,663 repos: enough for 2–3 pp effects; cores, not boards, bound how often the full set can run ([dev-eval-protocol.md](dev-eval-protocol.md)).
6. Week 1 order: (1) 0.10 resource control and local workdir; (2) 0.1 + 0.2 + 0.4 as scoring v2 (separate commits); (3) 0.5 partial output; (4) 0.3 integrity and sandbox; (5) 0.9 red team; (6) baseline re-run. Week 2: stats/compare, suites v1, noise floor. Ask before launching any run longer than the smoke suite on the shared host. Commit only code, suites and summarized results; never boards.

## Where we start

| Item | State |
|---|---|
| Host | Shared benchmark host: 128 threads, 251 GB, 2 NUMA nodes, **shared**. Budget: ≤ 50 cores, ≤ 96 GB. `$HOME` is NFS, local NVMe has 356 GB free |
| Toolchain | `kaebench doctor` passes: KiCad 10.0.7 (Apptainer image), Freerouting 2.5.0 |
| Corpus | local board corpus `kae-boards` (never committed): 13,749 KiCad-10-loadable boards, 10,902 fully routed, 2,412 drc-clean (2-layer 2,028, 4-layer 332, 6+ 52; median 27 footprints, p90 111; 1,663 repos; 193 noncommercial, private evaluation only). The committed benchmark manifest has 297, of which 112 qualified ([harness](harness.md)) |
| Routing baseline | Freerouting 2.5.0, k = 1, 600 s: A 0.62, B 0.35 with adapter fixes. C 0.04 with the **stock** adapter only; the fixed adapter has never run on C [M] |
| Placement baseline | None run. The place track has defects (below) |

## Harness defects found
Verified in code unless marked.


| # | Defect | Where | Effect |
|---|---|---|---|
| H1 | Place tasks move locked footprints unless `--keep-locked` is passed (which also keeps locked copper on route tasks) | `prepare.py:44`, `pcbnew_ops.py:188` | 24–40 of 112 boards unwinnable; the human reference should score invalid. **Fixed in score v2 (task spec 2)** |
| H2 | `PLACEMENT_ERROR_TYPES` lists `edge_clearance`, but KiCad's key is `copper_edge_clearance`. `hole_to_hole` and `items_not_allowed` are missing | `score.py:17` | Edge and keep-out violations never make a placement illegal. **Fixed in score v2** |
| H3 | Timeout returns no board | `adapters.py:120` | Partial routes score as completion 0. Freerouting's `--router.job_timeout` writes output on stop [P] |
| H4 | Best-of-k varies only `-mp` (10, 20, 30, …), and Freerouting seeds `Random(0)` | `adapters.py:72,112` | The k attempts are nested prefixes of one run, not independent samples |
| H5 | KiCad 10 DRC stops counting at 499 clearance/unconnected items and 199 for other types [P, unverified here] | `tools.summarize_drc`, `prepare.py` | `completion` is wrong on big C boards |
| H6 | Integrity covers only placement, pad nets and `(setup)` | `score.py`, `pcbnew_ops stats` | Layers, Edge.Cuts, zones, rule areas, pad geometry and local clearances can be changed without detection. Adapters can also read `tasks/<id>/reference/`. **Fixed in score v2:** rebuild-then-score, foreign-change detection, bwrap sandbox, red-team tests |
| H7 | The placement probe inherits the attempt index and the placer's timeout | `runner._probe` | Placement variance is mixed with router effort |
| H8 | Report bias | `report.py` | `_mean` skips boards with no output, so methods that time out look cleaner. `wl_ratio` and `via_delta` include incomplete boards. Place reports have no @1. **Paired report fixes it for A/Bs:** failures count, guardrails only on boards both arms routed clean, vias per connection |
| H9 | Scoring DRC timeouts and OOMs count as method failures and are cached | `runner.py` | Shared-host load turns into method noise. **Paired report** sets `score_error` boards aside and lists them for `kaebench rescore`; no `--retry-infra` yet |
| H10 | Provenance gaps: git dirty state, Freerouting version, image digest, task-set hash, filters, `-j`, cgroup | `runner.py` | Runs can't be checked for comparability |
| H11 | `hpwl_ratio` sums GND and power nets over pad centres | `pcbnew_ops stats` | Rewards over-packing. autolayout cut HPWL 21% and got about 2× the unconnected items [P] |
| H12 | Severities come from each board's `.kicad_pro`; `courtyards_overlap` is downgraded on 12 boards, `missing_courtyard` ignored on 90 | `score.py` | "Legal" means different things on different boards. **Score v11:** `clean_strict`/`legal_strict` beside `clean`/`legal` ([harness](harness.md)); the body-overlap check is still open |

Doc correction: Freerouting's "92.4% of 979 boards" (2.6.0-RC4) covers tiers A+B only. RC3 reached 69.5% on tier C with 360-minute budgets [P]. Applied in [freerouting](../routing/freerouting.md).

## Phase 0: trust the harness (weeks 1–2)

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
| 0.8 | Stats: `cp1_mean`, unbiased cp@k, per-type error diff, flipped-board list, exact McNemar, paired sign-flip and repo-clustered bootstrap (stdlib); new `kaebench compare`. **Built** in `stats.py` and as the paired section of `kaebench report` / `kaeres exp report` (on the boards both arms ran; `score_error` rows set aside; guardrails on boards both arms routed clean). Not yet: the A/A run (0.12), so the minimum claimable effect is unknown | new `stats.py`, `report.py` | M |
| 0.9 | **Done (22 cases).** V2 red-team suite: move part, delete keepout, grow outline, edit setup, shrink pad, zero pad clearance, swap net, add layer, bogus net, move locked part, delete footprint, shrink courtyard, add copper, own rules, read/write reference, network. Each is invalid, blocked or ineffective. Add a case per new cheat | `bench/tests/test_redteam.py` | M |
| 0.10 | Resource control (see Compute) | `adapters.py`, `tools.py`, `runner.py`, `CLAUDE.local.md` | M |
| 0.11 | Suites v1 from the 2,412 drc-clean boards: group by repo; seeded split stratified by split×layers×tier into `smoke` (12), `dev` (≈ 600, with a stratified `dev-200` for fast iteration), `val` (≈ 600) and `test` (≈ 1,200, sealed, reads logged in `bench/results/test-ledger.jsonl`). Commit ids only | `bench/scripts/make_splits.py`, `bench/suites/` | S |
| 0.12 | Noise floor: re-score 50 outputs 3× (must be identical); re-prepare 20 boards (hashes match); repeat Freerouting `-mt 1` runs under low and high load; A/A run of one baseline under two names | runs only | 1 day of compute |

**Exit gate:**
- Reference is clean and legal on every qualified board; `noop` scores 0.
- 12/12 cheats are caught.
- Scorer repeats are identical.
- A/A flip rate ≤ 3% of boards.

**Kill:** A/A above 5% after fixes means no comparisons until budgets are deterministic: pass counts, iterations and tokens rather than wall clock.

*Divergence, kept:* every method is budgeted in wall seconds (`--timeout`, `--time`), because that is how an LLM commanding kae spends time, and kae's routers, Freerouting and restart portfolios have no common deterministic unit. In exchange each attempt records its CPU-seconds (`method_usage.cpu_s`; kaeres also records the job step's cgroup CPU), so a parallel arm is read against its CPU: the restart portfolio at P = 4 used 6,199 CPU s in a 1,186 s run on gamaphy-freedom-rp2040, about 5× a single-process arm. A CPU-matched control is a best-of-N of the baseline at the same CPU total. Until the launcher became a subreaper, rusage lost every sandboxed (`--command`) method's CPU, because bwrap exits without reaping its pid 1; those older rows read ~0.

## Phase 1: baselines and diagnosis (weeks 3–4)

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
- Reproduce Freerouting 2.1.0 `-mp 10`, target within ±0.08 of 0.80 on D3-A [P]. D3-B (10 boards, about ±0.26 CI) is for reporting only.
- **Kill:** an unexplained gap > 0.15 after one extra week stops strategy work.

**Second engine:** a KRT adapter (MIT; reads `.kicad_pcb` directly, so no DSN loss). PCBWorld measured 0.74 on D3-A and 0.20 on D3-B [P]. Weak single baselines mislead.

## Phase 2a: routing strategies (weeks 3–8)

R1 budgets with partial output → split C diagnosis → R2 DSN fidelity pack → R3 seeded diversity → R4 fastroute → R5 DRC-driven repair → R6 portfolio selector, built only if the oracle portfolio from logs shows ≥ 0.05. R7 (PNS residual completion, blocked on KiCad 9) and R9 (own PathFinder router, only if congestion causes ≥ 40% of C failures) are gated. Mechanisms, reuse, effort, expected gains and kill criteria: [routing/strategy-candidates](../routing/strategy-candidates.md).

## Phase 2b: placement strategies (weeks 3–10)

Baselines B0–B5 first (noop, reference + probe, random + legalizer, pyplacer, kicad-tools, Cypress). Then P0 geometry kit → P1 constructive seed + CP-SAT legalizer → P2 slot/orientation clean-up → P3 multi-seed SA → P4 router-probe-in-the-loop repair. P5 Cypress is time-boxed to 3 days for a CPU build; P6 analytical placer and P7 weight tuning are gated. Prerequisites: mechanical anchors, signal-only HPWL, and KRT as a second probe. Details and kill criteria: [placement/strategy-candidates](../placement/strategy-candidates.md).

## Phase 3: LLM in the loop (weeks 8–13, only after headroom is shown)

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

## Phase 4: physics, corpus, sealed test (weeks 10–16)

- **Intent and physics MVP,** reference-relative. Each checker is validated by V1 mutants: decap pin distance, diff-pair skew, power-net minimum width, vias per pair ([critic-stack](critic-stack.md)).
- **Use the routed-but-not-clean boards** (8,490 of the 10,902 routed): a reference-relative track that scores "no DRC error instances beyond the human layout's". It is a new metric, so it goes in its own commit next to `clean`, never replacing it. Add commit dates for the time-split suite ([open-board-sources](../data/open-board-sources.md)).
- **Sealed test read, then write-up:**
  - CIs and per-type errors;
  - $ per extra clean board;
  - summarized results in `bench/results/`.

## Open questions

- **Locked-board count:** 24–39 vs 40 boards depending on the parser. Settle it with the Phase 0 reference run.
- **Unverified items:**
  - the DRC cap values;
  - whether `job_timeout` always yields an SES (pass 1 has run for 1,748 s on one board);
  - the `MaximumThreads` name;
  - whether Freerouting caps edge clearance at 250 µm;
  - fanout via sizes vs board rules.
- **Uncertain tools:** fastroute and autolayout results are self-reported on 1–20 boards. Cypress CPU feasibility is unknown, and the benchmark host has no GPU.
- **Corpus bias:** 84% of drc-clean boards are 2-layer (only 52 have 6+ layers), so report results per layer class; dense-board claims need the 6+ stratum or the routed-not-clean track.
- **Information leaks:** place tasks keep the human side assignment, zones and silkscreen, which leaks floorplan information. State this in results, or strip them in a harder task variant.
- **Contamination:** if this repo becomes public, suite files may enter pretraining; keep `test` ids private.

## Sources

- Harness code: [bench/src/kaebench/](../../../bench/src/kaebench/) (line references above, read 2026-10-21)
- Freerouting: [settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md), [nightly benchmarks](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md), [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)
- KiCad 10 DRC: [drc_engine.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp), [advanced_config](https://docs.kicad.org/doxygen/advanced__config_8cpp.html)
- fastroute: [repo](https://github.com/parisxmas/fastroute). KRT: [repo](https://github.com/drandyhaas/KiCadRoutingTools), [placement-optimization.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md). kicad-tools: [placement_score_calibration.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/placement_score_calibration.md). autolayout: [ROADMAP](https://github.com/bwattendorf/autolayout/blob/main/ROADMAP.md)
- Placers: [Cypress](https://github.com/NVlabs/Cypress), [pyplacer](https://github.com/ajokela/pyplacer), [VeoPlace](https://arxiv.org/pdf/2603.28733), [OmniLayout](https://arxiv.org/abs/2607.03261)
- See also [benchmark-plan](benchmark-plan.md), [evaluation-stack](evaluation-stack.md), [hybrid-architecture-options](../architecture/hybrid-architecture-options.md), [original ideas](../../ideas/original/README.md).
