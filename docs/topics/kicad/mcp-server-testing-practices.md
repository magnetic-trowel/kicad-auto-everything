# Testing and evaluation practices from the KiCad MCP servers

**TL;DR**
- **The strongest strategy is POA's:** "Every test has a judge that is not the code under test", meaning KiCad's own Python, `kicad-cli` output, ports of KiCad routines, or exact integer geometry. KMS mostly tests against `MagicMock` pcbnew stubs, the weak pattern [P].
- **Konnect requires a negative control** (neutralize the guard, show its test fails) and keeps a live-DRC regression recipe [P].
- **PRO contributes:** a 14-project golden corpus with labelled defect classes, tool-selection evals (expected and forbidden tools, safety tiers, call budgets), and an attempt-accounting contract that keeps failures in the denominator [P].
- **No server publishes placement or routing quality results** on a board corpus [P].
- **Under GPL-3.0-or-later**, POA's `pcbnew_judge` and `tests/kicad_ref` ports are directly reusable [I].

## Key facts
| Practice | Detail | Source |
|---|---|---|
| POA test ladder | ~1,950 test functions. Rungs: 1 bytes and tokens, 2 numbers and geometry, 3 single-element edits, 4 whole-file reads, 5 one tool call, 6 composite tools, 7 end to end. An autouse fixture runs `kicad-cli` on every KiCad file a test leaves behind. The only allowed xfail is a strict xfail naming a numbered bug and the fixing step. Hypothesis: 200 examples in CI, 5,000 nightly. CI: full suite on Linux with KiCad 9 and 10; macOS and Windows with KiCad 10 | [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md) [P] |
| POA judges | `tests/pcbnew_judge.py` runs scripts under KiCad's own Python ("what it computes … is KiCad's answer by definition") and asks pcbnew for its version. `tests/kicad_ref/` ports KiCad's `trigo`, `transform`, footprint `SetPosition`/`SetOrientation`/`Rotate`/`Flip`, pad and layer pairs, the DSN lexer and unit parsing. `tests/kicad_corpus.py` sweeps the installed demos and libraries | [pcbnew_judge.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/pcbnew_judge.py), [kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref) [P] |
| POA routing harness | `tools/routing_harness/` compares `kicad-cli` netlist node sets before and after each call. Measured: "16 of 36 generated layouts built the way the repo's skills prescribe came out shorted"; the wrong pin was wired in 4 of 12 orientations | [adr-routing-safety.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-routing-safety.md) [P] |
| Konnect | ~2,445 tests, an NNG mock server, and `--ignored` live tests needing a disposable board open in KiCad (`KONNECT_LIVE_KICAD_BOARD`). Weekly Windows E2E installs KiCad 10.0.5 with choco. Governance requires a negative control. 20 `.kicad_pcb` fixtures, including KiCad demos (`pic_programmer`, `ecc83`) and Antmicro's Kria K26 (Apache-2.0) for transform ground truth | [e2e-kicad.yml](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/.github/workflows/e2e-kicad.yml), [RELIABILITY_CONTRACT.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/RELIABILITY_CONTRACT.md) [P] |
| Konnect live-DRC recipe | (1) create and save a via; (2) delete it without saving; (3) file-only DRC still reports the via's UUID; (4) synchronized DRC drops it after refill and save | [DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md) [P] |
| PRO golden corpus | ~5,250 tests. 14 small projects under `tests/fixtures/benchmark_projects/` with per-gate expected outcomes. Pass: `pass_minimal_mcu_board`, `pass_sensor_node`. Fail: `fail_bad_decoupling_placement`, `fail_footprint_overlap_board`, `fail_dfm_edge_clearance`, `fail_dirty_transfer_wrong_pad_nets`, `fail_sensor_cluster_spread`, `fail_label_only_schematic`. KiCad 10 features: custom DRC, design blocks, time domain, variants | [golden_corpus.yaml](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/evals/golden_corpus.yaml) [P] |
| PRO tool-selection evals | Each case declares `expected_tools`, `forbidden_tools`, a safety tier (read_only, write, export, publish, human_only, no_tool) and `max_calls`. A scorer measures recall, safety violations, unnecessary calls and nondeterminism across repeats | [evals/README.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/evals/README.md) [P] |
| PRO attempt accounting (#730) | Each attempt directory holds `specification.md`, `original-prompt.md`, `benchmark.json` (`pcb-task-outcome.v1`) and `attempt-manifest.json` with SHA-256 digests. Failures stay in the denominator. An "infrastructure_invalid" exclusion is refused if the agent log shows any tool call. A `manual_repair=true` success is "not publishable as autonomous success". PRO's own native-live evidence "intentionally reports `insufficient_evidence`" | [reference-board-corpus.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/development/reference-board-corpus.md) [P] |
| PRO transaction evidence (10.0.5) | One real Ctrl+Z reverted a committed track and via group to the exact pre-operation digest; a 20-iteration stage-and-drop soak had zero failures | [cc91138e](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae) [P] |
| KMS | ~2,309 test functions. `conftest.py` stubs `pcbnew` with `MagicMock` (`GetBuildVersion` → "9.0.0-stub"). Real-pcbnew smoke tests run only with `KICAD_USE_REAL_PCBNEW=1`. CI installs KiCad from the PPA. A test freezes the count of unindexed tools so it can only shrink | [conftest.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/tests/conftest.py) [P] |
| Mocks hide API shapes | kipy `Track.length` is a method, but mocks made it an int: "the mock could only fail in the way its author expected" | [PRO 30d02c76](https://github.com/oaslananka/kicad-mcp-pro/commit/30d02c76b74b95ab83d588d43cbbf33630014e7f) [P] |

- Test counts are grep counts, including parametrized bases; the suites were not run.

## Recommendations for our system
- **Adopt the full set:**
  - an independent judge for every test;
  - a negative control for every guard;
  - a `kicad-cli` load check on every produced file;
  - drill and Gerber coordinate oracles for every transform;
  - netlist node-set diffs around every mutating call;
  - a KiCad 9 and 10 CI matrix [I].
- **Reuse:** POA's `pcbnew_judge` and `kicad_ref` (GPL-3.0-or-later, compatible with our code), PRO's golden corpus and eval scorer (MIT), and the Konnect live-DRC recipe as a pattern (AGPL; reimplement) [I].
- **Fixtures:** read KiCad's shipped demos (ecc83, pic_programmer, multichannel_mixer, vme-wren; CC BY-SA 4.0) from the user's install, as POA does, rather than re-hosting them. Use Antmicro's Apache-2.0 boards for routed ground truth [I]. See [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md).
- **Benchmark contract:** PRO-style attempt accounting plus tool-selection evals. The evaluation stack itself belongs to the `verification/` area [I].

## Conflicts and open questions
- None of the four publishes a placement or routing quality benchmark on a corpus. PRO's reference-board corpus is infrastructure only: it "does **not** by itself satisfy the requirement to publish at least three serious reference boards".

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 4, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [licensing.md § 1A (KiCad demos CC BY-SA)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)

See also: [mcp-server-lessons.md](mcp-server-lessons.md), [transform-math-pitfalls.md](transform-math-pitfalls.md), [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md)
