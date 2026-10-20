# Licensing

This project uses split licensing so that it stays open while remaining easy
to build on. The rationale and the survey behind it are in
[`research_notes/.../licensing.md`](research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md).
None of this is legal advice.

## What applies to what

| Material | License | SPDX |
|---|---|---|
| Source code (Python, Rust, MCP servers, KiCad IPC-API plugins, scripts) | Mozilla Public License 2.0 | `MPL-2.0` |
| Documentation, research notes, reports (`*.md`, `research_notes/`, `reports/`) | Creative Commons Attribution 4.0 | `CC-BY-4.0` |
| Machine-readable layout rule packs and constraint/intent schemas | CC0 1.0 (public domain dedication) | `CC0-1.0` |
| Datasets, benchmark manifests, and labels we create | Community Data License Agreement – Permissive 2.0 | `CDLA-Permissive-2.0` |
| Trained model weights we release | Apache License 2.0 | `Apache-2.0` |
| Code that must link KiCad or other GPL code in-process | GPL-3.0-or-later, as a separately distributed package | `GPL-3.0-or-later` |

The root [`LICENSE`](LICENSE) is MPL-2.0 because it is the default for code.
Per-file licensing is declared in [`REUSE.toml`](REUSE.toml) and in SPDX
headers, following the [REUSE](https://reuse.software) convention; full texts
are in [`LICENSES/`](LICENSES). When the first file of a category that is not
yet present lands (rule packs, datasets, weights, GPL bridge), add its license
text to `LICENSES/` and an annotation to `REUSE.toml`.

New source files should start with:

```
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: MPL-2.0
```

## Why this split

- **MPL-2.0 for code**: file-level copyleft. Changes to our files must stay
  open, but the code can be combined with anything, including proprietary
  tools and GPL projects such as KiCad (MPL-2.0 is GPL-compatible). It carries
  an express patent grant.
- **Permissive for specs, rule packs, and data**: formats and knowledge only
  become shared standards if every tool, open or commercial, can adopt them.
- **GPL kept at a process boundary**: KiCad's IPC API, `kicad-cli`, and
  external routers such as Freerouting are used as separate processes, so the
  core does not need to be GPL. Anything that must link GPL code lives in its
  own GPL-3.0-or-later package.

## Rules for dependencies and reused material

- **Fine to depend on or vendor** (with notices): MIT, BSD, ISC, Zlib,
  Apache-2.0, MPL-2.0, PSF, LGPL (as unmodified dynamic dependencies).
- **Separate process only, never imported by the MPL core**: GPL code such as
  Freerouting, KiCad's SWIG `pcbnew` bindings, openEMS/CGAL Python bindings,
  PCBWorld-Engine, `kiutils`.
- **Reference only, do not copy code**: AGPL projects (e.g. Konnect),
  non-commercial or unlicensed projects.
- **Never bundle**: Shewchuk's Triangle, Gurobi, or other non-redistributable
  components.
- **Vendor documents** (datasheets, app notes): record facts and numeric
  guidelines in our own words with citations; do not copy figures, tables, or
  PDFs into the repo.
- **Third-party boards**: benchmark datasets ship as manifests (repo, commit,
  upstream license) and fetch boards at run time rather than redistributing
  them. Extracted KiCad library footprints are CC-BY-SA-4.0.
- **Model weights**: fine-tune only from base models whose licenses permit
  Apache-2.0 redistribution, and check AI-provider terms before training on
  generated outputs.
- **Quotations** in the research notes remain the property of their authors
  and are included for commentary and citation; CC-BY-4.0 covers our original
  text.

Contributions are accepted under the license of the files they touch
(inbound = outbound); see [`CONTRIBUTING.md`](CONTRIBUTING.md).
