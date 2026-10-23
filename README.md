# kicad-auto-everything
helper systems for LLMing KiCad

## Research

- [`docs/INDEX.md`](docs/INDEX.md): start here. Short digests link to small
  focused topic docs on placement and routing algorithms, LLMs for EDA, KiCad
  integration, layout rules, verification, benchmarks, and licensing.
- [`research_notes/LLM driven PCB placement and routing/`](research_notes/LLM%20driven%20PCB%20placement%20and%20routing/):
  the raw survey notes the docs cite as evidence.

## Design synthesis

- [`synth/`](synth/README.md) (`kaesynth`): an LLM writes a typed circuit description
  (`designs/<slug>/design.py`); `kaesynth build` checks it (ratings vs worst-case net voltage,
  isolation domains, protection, provenance), writes a KiCad 10 schematic and project, proves the
  schematic's netlist matches, and emits placement intent for the placer/router.
- [`designs/`](designs/): worked examples from plain-language briefs.

## License

Code is [GPL-3.0-or-later](LICENSE); documentation and research notes are
CC-BY-4.0, rule packs CC0-1.0, datasets CDLA-Permissive-2.0, and model weights
Apache-2.0. See [`LICENSING.md`](LICENSING.md) for details and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for how to contribute (DCO sign-off).
