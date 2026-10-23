# kicad-auto-everything

Tools for LLM-driven KiCad placement and routing. Code is GPL-3.0-or-later; docs
CC-BY-4.0 (see `LICENSING.md`). New source files carry SPDX headers.

## Docs: load little, follow links

- Start at `docs/INDEX.md`, then read one digest (`docs/digests/`) and the one topic
  doc you need (`docs/topics/<area>/`). Don't bulk-read `research_notes/`; it is raw
  evidence cited by the topic docs.
- When writing docs, follow `docs/CONVENTIONS.md`: digests <= 800 words, topic docs
  <= 3,000 words, link instead of repeating.

## Benchmark harness (`bench/`, package `kaebench`)

Setup on an Ubuntu host (no sudo needed: installs Apptainer rootless and runs KiCad from its official image): `bench/scripts/setup.sh`, then `source bench/.venv/bin/activate`
and `kaebench doctor`. Tests: `pytest bench/tests` (KiCad tests skip without KiCad).

Closed loop:

```bash
M=bench/manifests/candidates.jsonl
kaebench fetch -m $M -j 16
kaebench prepare -m $M -j 16                       # KAE_DRC_TIMEOUT=3600 for big boards
kaebench tasks --write-suite kae-work/qualified.txt
kaebench run --adapter <name> [--command "..."] --kinds route -k 3 --timeout 900 -j 16 \
  --only @kae-work/qualified.txt --name <run>
kaebench report kae-work/results/<run> kae-work/results/<baseline-run>
```

- Fast iteration: `--splits A` (≤ 31 pads) or `--only id1,id2`; full runs take hours.
- Run long jobs detached and poll them instead of holding a foreground command:
  `tmux new -d -s bench 'kaebench run ... > kae-work/<run>.log 2>&1'`, then `tail` the log.
- Host-specific paths (KiCad, Freerouting, data dirs) go in a git-ignored `CLAUDE.local.md`.
- Re-using `--name` resumes a run; use a new name after changing a method.
- Per-attempt artifacts: `kae-work/results/<run>/<adapter>/<kind>/<id>/attempt-N/`
  (`attempt.json`, `adapter.log`, `score/drc.json`).
- New methods plug in with `--command` (reads `{input}`, writes `{output}`) or a class in
  `bench/src/kaebench/adapters.py`.

## Rules for closed-loop work

- Never change scoring to improve a score. Scoring and integrity checks
  (`score.py`, `tools.summarize_drc`, `prepare.py`) define the benchmark. If one is
  wrong, fix it in a separate commit that says why, and re-run the baselines.
- Compare against a baseline run made with the same KiCad version, manifest and suite.
  Report both `cp1` and `cpk`, plus completion and error counts. Read the per-type
  errors in `drc.json` before concluding anything.
- A router's own log is not a score; only `kicad-cli` on the re-opened board counts.
- `kae-work/` is git-ignored. Commit code, manifests, suites and summarized results,
  never boards (third-party licences).

## Design synthesis (`synth/`, package `kaesynth`; designs in `designs/<slug>/`)

Turns an LLM-written `designs/<slug>/design.py` (typed circuit IR) into a checked KiCad 10
schematic, `.kicad_dru` and `intent.yaml` placement relations. Guide: `synth/README.md`.

```bash
cd synth && uv venv .venv && . .venv/bin/activate && uv pip install -e '.[test]'   # needs KiCad 10 + kicad-symbols/kicad-footprints
kaesynth build ../designs/<slug>/design.py -v    # writes designs/<slug>/out/; exit 1 while errors remain
pytest tests
```

- Never relax a check, rating or derating to make a design pass. Fix the design, or
  `d.waive(check, regex, reason, by)` with a reason a reviewer can audit. Change a check in
  `synth/src/kaesynth/checks.py` only in a separate commit that says why.
- Part facts (pins, pin maps, ratings, isolation) come from datasheets with `source=` provenance,
  never from memory. Spacing numbers for barriers cite the standard's table.
- `designs/<slug>/out/` is generated and committed; rebuild instead of editing it.
