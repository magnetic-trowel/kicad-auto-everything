<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# decide-ab analysis

Scripts that read the decide-ab experiments (plan and pass criteria: `../PLAN.md`).

| Script | What it reports |
|---|---|
| `ab_analyze.py EXP` | Place-kind experiments, paired per board: legal, legal_strict, clean, clean_strict, completion, hpwl_ratio, errors by type and hazards |
| `edge_measure.py` | Distance of connectors from the edge, and which way they face (P4) |
| `copper_dry.sh` / `copper_dry_sum.py` | Critical stage only, per copper-ab arm: copper and via hazard counts (C2, RC3) |
| `edge_boards.py` | Picks boards with an unlocked connector of a kind kae pins |
| `costmodel.py` | Cost estimate for the plan |

Use `kaeres exp report` for copper-ab, edge-ab2 and aa-joint.

Environment:
- `KAE_AB_WORK`: local working directory for the copper dry runs.
- `KAE_AB_SCRATCH`: where cost inputs are written.
- `KAE_LOCAL`: local NVMe root (it is also bound into the KiCad container).
