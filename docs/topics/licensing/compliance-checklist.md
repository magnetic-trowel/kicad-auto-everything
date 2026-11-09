# License compliance checklist (GPL-3.0-or-later code; permissive docs, rules, data, weights)

Scope: the mechanics of staying compliant: REUSE layout, SPDX headers, dependency gates, notices, contributions, release checks. Not here: per-component verdicts -> [reuse-matrix](reuse-matrix.md); KiCad/GPL facts -> [kicad-and-gpl-ecosystem-notes](kicad-and-gpl-ecosystem-notes.md); data, rule-pack and weight licences -> [data-rulepacks-weights](data-rulepacks-weights.md); project licence table -> [LICENSING.md](../../../LICENSING.md).
Keys: REUSE 3.3, reuse lint, REUSE.toml, LICENSES/, SPDX header, cargo-deny, pip-licenses, licensecheck, ScanCode, THIRD_PARTY_NOTICES.md, NOTICE, DCO, inbound=outbound, AI-assistance rule, relicensing, Freerouting -da analytics

## REUSE layout and headers

- REUSE 3.3 rules [P] ([spec](https://reuse.software/spec-3.3/)): "Each License File MUST be placed in the LICENSES/ directory … named [by] the SPDX License Identifier"; "A Project MUST NOT include License Files for licenses under which none of the files in the Project are licensed"; "Each Covered File MUST have Licensing Information". `reuse` tool at 6.2.0. Topola = working REUSE example in this domain.
- `LICENSES/` now: GPL-3.0-or-later, CC-BY-4.0, CDLA-Permissive-2.0, BSD-3-Clause (PCBWorld-derived suites). Add CC0-1.0 with the first rule pack and Apache-2.0 with the first weights (REUSE forbids unused licence files) [P/I].
- Every file gets SPDX headers or a `REUSE.toml` annotation; run `reuse lint` in CI [I].
- Header for new source files: [LICENSING.md](../../../LICENSING.md#what-applies-to-what).
- `REUSE.toml` (current state; the last matching table wins) [I]:

  | Paths | Licence |
  |---|---|
  | `**/*.md`, `docs/**`, `reports/**`, `research_notes/**` | CC-BY-4.0 |
  | `bench/manifests/*.jsonl`, `bench/suites/**`, `tools/research/**/results/*.jsonl` | CDLA-Permissive-2.0 |
  | the three PCBWorld D3 suites | BSD-3-Clause, with LG AI Research's copyright line |
  | everything else | GPL-3.0-or-later |
  | to add: rule packs and constraint/intent schemas (top-level path that cannot match `docs/topics/rules/**`) | CC0-1.0 |
  | to add: weights | Apache-2.0 |

## Dependency gates

Tools [P]: `pip-licenses` 5.5.5 (`--fail-on`, `--allow-only`, `--from=mixed`); `licensecheck` checks "if these are compatible with the project license"; `cargo-deny` 0.20.2 verifies every crate's licence against an allow-list; ScanCode 32.5.0 scans vendored directories.

| Ecosystem | Gate [I] |
|---|---|
| Rust | `cargo deny check licenses`; allow GPL-3.0(-or-later), GPL-2.0-or-later, LGPL-*, MPL-2.0, Apache-2.0, MIT, BSD-2/3-Clause, ISC, Zlib, BSL-1.0, Unicode-3.0; deny AGPL (unless deliberately accepted), GPL-2.0-only, unlicensed, proprietary |
| Python | `pip-licenses --from=mixed --fail-on` with the same deny list, or `licensecheck`. Gurobi and other proprietary solvers: optional user-installed extras, never bundled |
| Vendored dirs | ScanCode |

Deny list: [LICENSING.md](../../../LICENSING.md#rules-for-dependencies-and-reused-material).

## Notices and releases

- Generate `THIRD_PARTY_NOTICES.md` at each release (pip-licenses or cargo-about output) [I]. PCBWorld ships a third-party `Notice.md`, a pattern worth copying [P].
- Per-licence duties [P]: Apache-2.0 code needs its NOTICE and marking of changed files; MPL-2.0 files stay MPL with source available; LGPL binaries need notices and source, plus relinkable objects if statically linked.
- Docker images bundling KiCad, Freerouting (GPL-3.0-only, so that image is GPL-3.0; [reuse-matrix](reuse-matrix.md#routers-placers-agents-mcp-servers)) or GEOS: include licence texts and corresponding source or a written offer [I].
- Re-verify third-party licences at each release and when lockfiles change; they drift (examples in [reuse-matrix](reuse-matrix.md#reuse-rules)) [P].

## Contributions

- DCO 1.1: contributor certifies "I have the right to submit it under the open source license indicated in the file". GitHub ToS makes contributions "inbound=outbound" unless a CLA supersedes it. FSF prefers assignment for enforcement (not adopted) [P].
- Rules [I]: DCO sign-off and AI-assistance rule -> [CONTRIBUTING.md](../../../CONTRIBUTING.md#developer-certificate-of-origin). Added here: check sign-off in CI; disclose AI use; no AGPL, unlicensed, non-commercial or proprietary source in prompts or diffs; ported GPL code (KiCad, Freerouting, POA) keeps its original copyright headers.
- Relicensing: rights already granted are irrevocable for snapshots people have; once other contributors exist, relicensing needs every copyright holder. kicad-python's GPL→MIT move happened while the KiCad devs held all copyright [P].

## Services and patents

- Freerouting collects anonymous analytics unless `-da` is passed [P]: always pass `-da`, pin versions by hash; keep cloud services (Freerouting public API, DeepPCB, Quilter) optional and off by default for privacy and IP reasons [I].
- Patents: keep [../landscape/patents-watchlist.md](../landscape/patents-watchlist.md) current; get counsel before shipping RL place/via/route policies or learned routability predictors [I].

## Open questions

- No transitive dependency audit yet; needs lockfiles.
- DCO GitHub App vs CI action not compared.

## Sources

- research notes: [licensing.md § 5, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md); [existing_tools_and_apis.md § 7 (license hygiene)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [REUSE spec 3.3](https://reuse.software/spec-3.3/), [cargo-deny licenses](https://embarkstudios.github.io/cargo-deny/checks/licenses/index.html), [developercertificate.org](https://developercertificate.org/)
