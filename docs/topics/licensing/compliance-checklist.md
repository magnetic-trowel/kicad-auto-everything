# License compliance checklist (GPL-3.0-or-later code; permissive docs, rules, data, weights)

**TL;DR**
- **REUSE layout:** `LICENSES/` holds GPL-3.0-or-later, CC-BY-4.0, CC0-1.0, CDLA-Permissive-2.0 and Apache-2.0 (when weights land). Every file gets SPDX headers or a `REUSE.toml` annotation. Run `reuse lint` in CI [P/I].
- **Dependency gates** (`cargo-deny`, `pip-licenses`/`licensecheck`, ScanCode) **deny** GPL-2.0-only, AGPL, non-commercial, unlicensed and proprietary code, and **allow** GPL-3.0, GPL-2.0-or-later, LGPL, MPL-2.0 and permissive licenses [I].
- **Generate `THIRD_PARTY_NOTICES.md` at each release.** Bundles that ship KiCad, Freerouting or GEOS binaries must include license texts plus source or a written offer [P/I].
- **Contributions:** DCO plus inbound=outbound ([CONTRIBUTING.md](../../../CONTRIBUTING.md)). An AI-assistance rule bars AGPL, unlicensed, non-commercial and proprietary source from prompts and diffs [I].
- **Re-verify third-party licenses at each release**, because they drift [P].

## Key facts
- **REUSE 3.3:**
  - "Each License File MUST be placed in the LICENSES/ directory … named [by] the SPDX License Identifier".
  - "A Project MUST NOT include License Files for licenses under which none of the files in the Project are licensed".
  - "Each Covered File MUST have Licensing Information".
  - The `reuse` tool is at 6.2.0. Topola is a working REUSE example in this domain [P] ([spec](https://reuse.software/spec-3.3/)).
- **Header for new source files** ([LICENSING.md](../../../LICENSING.md)):
  ```
  # SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
  # SPDX-License-Identifier: GPL-3.0-or-later
  ```
- **Tools:**
  - `pip-licenses` 5.5.5 supports `--fail-on`, `--allow-only` and `--from=mixed`.
  - `licensecheck` checks "if these are compatible with the project license".
  - `cargo-deny` 0.20.2 verifies every crate's license against an allow-list.
  - ScanCode 32.5.0 scans vendored directories [P].
- **Notices:** PCBWorld ships a third-party `Notice.md`, a pattern worth copying [P]. Apache-2.0 code needs its NOTICE and marking of changed files; MPL-2.0 files stay MPL with source available; LGPL binaries need notices and source, plus relinkable objects if statically linked [P].
- **DCO 1.1:** a contributor certifies "I have the right to submit it under the open source license indicated in the file". The GitHub ToS makes contributions "inbound=outbound" unless a CLA supersedes it. FSF prefers assignment for enforcement (not adopted) [P].
- **Relicensing:** rights already granted under a license are irrevocable for snapshots people already have; once other contributors exist, relicensing needs every copyright holder. kicad-python's GPL→MIT move happened while the KiCad devs held all copyright [P].
- **Analytics:** Freerouting collects anonymous analytics unless `-da` is passed [P].

## Recommendations for our system
1. **Annotate `REUSE.toml`:** `docs/**`, `reports/**`, `research_notes/**` → CC-BY-4.0; `rules/**` and constraint/intent schemas → CC0-1.0; `datasets/manifests/**` → CDLA-Permissive-2.0; future weights → Apache-2.0. Quotations remain their authors' [I].
2. **Rust:** `cargo deny check licenses` allowing GPL-3.0(-or-later), GPL-2.0-or-later, LGPL-*, MPL-2.0, Apache-2.0, MIT, BSD-2/3-Clause, ISC, Zlib, BSL-1.0, Unicode-3.0. Deny AGPL (unless deliberately accepted), GPL-2.0-only, unlicensed and proprietary crates [I].
3. **Python:** `pip-licenses --from=mixed --fail-on` with the same deny list, or `licensecheck`. Keep Gurobi and other proprietary solvers as optional user-installed extras that are never bundled [I].
4. **Releases:** generate `THIRD_PARTY_NOTICES.md` (pip-licenses or cargo-about output). For Docker images bundling KiCad, Freerouting (GPL-3.0-only, so that image is GPL-3.0) or GEOS, include license texts and corresponding source or a written offer [I].
5. **Contributions:**
   - DCO sign-off (`git commit -s`) checked in CI.
   - Disclose AI use. No AGPL, unlicensed, non-commercial or proprietary source in prompts or diffs.
   - Ported GPL code (KiCad, Freerouting, POA) keeps its original copyright headers [I].
6. **Freerouting:** always pass `-da`, pin versions by hash, and keep cloud services (Freerouting public API, DeepPCB, Quilter) optional and off by default for privacy and IP reasons [I].
7. **Datasets, rule packs and weights:** follow [data-rulepacks-weights.md](data-rulepacks-weights.md).
8. **Patents:** keep [../landscape/patents-watchlist.md](../landscape/patents-watchlist.md) current and get counsel before shipping RL place/via/route policies or learned routability predictors [I].
9. **Re-verify licenses each release** and re-run the audit when lockfiles change [I].

## Conflicts and open questions
- No transitive dependency audit has been run yet; it needs lockfiles.
- DCO GitHub App versus CI action was not compared.

## Sources
- research notes:
  - [licensing.md § 5, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
  - [existing_tools_and_apis.md § 7 (license hygiene)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [REUSE spec 3.3](https://reuse.software/spec-3.3/), [cargo-deny licenses](https://embarkstudios.github.io/cargo-deny/checks/licenses/index.html), [developercertificate.org](https://developercertificate.org/)

See also: [reuse-matrix.md](reuse-matrix.md), [kicad-and-gpl-ecosystem-notes.md](kicad-and-gpl-ecosystem-notes.md), [../../../LICENSING.md](../../../LICENSING.md)
