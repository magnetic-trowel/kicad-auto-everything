# Licensing

Code is GPL-3.0-or-later so it can integrate tightly with KiCad and the GPL
routing/placement ecosystem around it. Non-code material (docs, rule packs,
data, model weights) uses permissive licenses so formats and knowledge can be
adopted by any tool. The survey behind this is in
[`research_notes/.../licensing.md`](research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
(written before the switch from MPL-2.0 to GPL; its inventory still applies).
None of this is legal advice.

## What applies to what

| Material | License | SPDX |
|---|---|---|
| Source code (Python, Rust, MCP servers, KiCad plugins, scripts) | GNU GPL v3 or later | `GPL-3.0-or-later` |
| Documentation, research notes, reports (`*.md`, `docs/`, `research_notes/`, `reports/`) | Creative Commons Attribution 4.0 | `CC-BY-4.0` |
| Machine-readable layout rule packs and constraint/intent schemas | CC0 1.0 (public domain dedication) | `CC0-1.0` |
| Datasets, benchmark manifests, board-id suites (`bench/suites/`), and labels we create | Community Data License Agreement – Permissive 2.0 | `CDLA-Permissive-2.0` |
| PCBWorld D3 suites (`bench/suites/pcbworld-d3*-test.txt`), derived from LGAI-Research/PCBWorld `configs/datasets/d3.json` @ 1989a93 | BSD 3-Clause, © 2026 LG Management Development Institute Co., Ltd. (LG AI Research) | `BSD-3-Clause` |
| Trained model weights we release | Apache License 2.0 | `Apache-2.0` |

The root [`LICENSE`](LICENSE) is the GPL v3 text. Per-file licensing is
declared in [`REUSE.toml`](REUSE.toml) and SPDX headers, following
[REUSE](https://reuse.software); full texts are in [`LICENSES/`](LICENSES).
When the first rule pack or weights file lands, add its license text to
`LICENSES/` and an annotation to `REUSE.toml` (as done for the benchmark
results in `tools/research/`). Data derived from a third-party file keeps that
file's license and copyright line, as for the PCBWorld suites.

New source files should start with:

```
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
```

## Why GPL for code

- KiCad (GPL-3.0-or-later), Freerouting (GPL-3.0), KiCad's push-and-shove
  router (including LG's PCBWorld-Engine bindings), Horizon EDA, `kiutils`,
  openEMS, and CGAL's bindings are all GPL. GPL lets us import, vendor, fork,
  port, and link them in-process instead of hiding them behind process
  boundaries, and makes upstreaming into KiCad straightforward.
- "Or later" matches KiCad and keeps us compatible with GPL-3.0-only code.

## Why permissive for everything else

- Rule packs, constraint schemas, and benchmark data only become shared
  standards if every tool, open or commercial, can adopt them. They do not link
  with GPL code, so they do not need to be GPL.
- Model weights released as Apache-2.0 stay usable by anyone; fine-tune only
  from base models whose licenses allow that.

## Rules for dependencies and reused material

- **Fine to depend on, vendor, or port** (keep notices): GPL-3.0 and
  GPL-3.0-or-later, GPL-2.0-or-later, LGPL, MPL-2.0, Apache-2.0, MIT, BSD, ISC,
  Zlib, PSF.
- **Incompatible, do not combine**: GPL-2.0-only code, non-commercial or
  unlicensed code, Shewchuk's Triangle, Gurobi or other non-redistributable
  components.
- **AGPL-3.0** (e.g. Konnect): GPLv3 §13 allows combining, but the AGPL network
  clause then applies to the whole combination. Use as reference only unless
  we deliberately accept that.
- **Vendor documents** (datasheets, app notes): record facts and numeric
  guidelines in our own words with citations; do not copy figures, tables, or
  PDFs into the repo.
- **Third-party boards**: benchmark datasets ship as manifests (repo, commit,
  upstream license) and fetch boards at run time. Extracted KiCad library
  footprints are CC-BY-SA-4.0.
- **Model weights**: check base-model licenses and AI-provider terms before
  training on generated outputs.
- **Quotations** in docs and research notes remain the property of their
  authors and are included for commentary and citation; CC-BY-4.0 covers our
  original text.

Contributions are accepted under the license of the files they touch
(inbound = outbound); see [`CONTRIBUTING.md`](CONTRIBUTING.md).
