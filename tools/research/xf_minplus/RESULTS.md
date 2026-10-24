<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Experiment A (T1): min-plus best-response maps in jc

## Built

- **`minplus.py`**
  - Per-net Dijkstra fields on jc's β-priced grid: cells cost (1+hist)(1+β·foreign) and vias are priced as the router prices them, min-pooled to 0.4 mm.
  - A part's map is the sum over its nets of the minimum over its pads of the shifted fields.
  - `MPCollapse` subclasses jc's `Collapse` (jc.py is not edited) and blends the map with jc's HPWL + tension term by `minplus_w`.
  - Plug-ins: `xf`, `xf_h`, `xf_lv`, `xf_lv_h`, `xf0`.
- **`validate.py` and `gate_report.py`:** the gate.
- **`test_minplus.py`:** Dijkstra tests.
- **`summarize.py`:** paired length and vias.

**Suspected −1e6 bug: not reproduced.**
- The Dijkstra matches Bellman-Ford exactly on 33 hand-made and random grids.
- On three boards, at β up to 92, no field and no cost is negative.
- For 2-pin nets, the field at the other pin is 0.74–0.98 × the routed priced cost at β≈5. That is a lower bound, as min-pooling should give.
- At β=92 on paw3395 the ratio is 0.15: min-pooling is optimistic on congested boards.

## Gate (dev6, 2243 re-routed moves, β = 0.05, 1, 5, 20)

Each move re-routes the part's nets with the engine router at the current price. The table gives within-part Spearman ρ against routed cost (mm + 2/via), which is the ranking a best response uses.

| board | HPWL | jc term | min-plus |
|---|---|---|---|
| biscuit-crowbar | 0.81 | 0.81 | 0.78 |
| gas-sensor | 0.74 | 0.70 | 0.78 |
| paw3395 | 0.57 | 0.56 | 0.60 |
| os-3d-blender | 0.87 | 0.80 | 0.91 |
| rgbpi-sync-mixer | 0.83 | 0.83 | 0.81 |
| xor-2in | 0.92 | 0.92 | 0.92 |
| **all** (local / global moves) | 0.78 (0.66 / 0.75) | 0.76 (0.61 / 0.73) | **0.79** (0.68 / 0.80) |

- **Paired over 187 parts, min-plus minus HPWL:** +0.007 (95% CI −0.02 to +0.04) on routed cost; +0.06 (CI +0.03 to +0.09) on priced cost.
- **Argmin regret:** 0.88 mm for min-plus, 1.48 for HPWL.
- **Pooled ρ is worse for min-plus** (0.69 vs 0.97): the map leaves out the rest of each net, a per-part offset that does not affect a best response.
- **Tree sources gave the same 0.79.**

**Gate passed narrowly:** min-plus is at least as good as HPWL, and better on priced cost and regret. Tables: `kae-work/xf_minplus/gate-*.md`.

## Sweep (ab33, budget 120, 3 seeds)

- Legal, clean and completion are 3-seed means.
- Length and vias are 3-seed means over the 25 boards that every run of that objective fully routed.
- Physics is phys10, seed 0, as a method/human gmean.

| run | legal | clean mean±sd | best-of-3 | completion | length mm | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|---|
| xf-base-jc-ab33 | 0.899 | 0.657±0.035 | 0.727 | 0.897 | 3311 | 75.7 | 1.08 | 0.88 |
| xfA-mp1-jc-ab33 | 0.879 | 0.616±0.017 | 0.667 | 0.900 | 3187 (−3.7%) | 58.0 (−23%) | 0.86 | 1.18 |
| xfA-mp05-jc-ab33 | 0.899 | 0.677±0.017 | 0.727 | 0.900 | 3197 (−3.4%) | 61.0 (−19%) | 0.96 | 1.14 |
| xf-base-jc_lv_nopol-ab33 | 0.879 | 0.616±0.046 | 0.697 | 0.900 | 3406 | 86.3 | 2.31 | 1.16 |
| xfA-mp1-lv-ab33 | 0.899 | 0.677±0.035 | 0.697 | 0.899 | 3184 (−6.5%) | 63.3 (−27%) | 2.20 | 1.29 |
| xfA-mp05-lv-ab33 | 0.909 | 0.626±0.017 | 0.697 | 0.904 | 3238 (−4.9%) | 68.7 (−20%) | 2.35 | 1.33 |

- **Paired by seed:**
  - mp1-lv: length −4.2, −8.6 and −6.6%; vias −19, −33 and −28%. It is shorter on 20 of 25 boards.
  - mp1-jc: length −1, −5 and −5%; vias −37, −29 and −3%.
- **About half the via cut is on one board,** `tcsullivan-noisecard`. Without it:
  - mp1-lv still gives −2.5 to −4.9% length and −4 to −18% vias;
  - mp1-jc's gain is noise.
- **The added `silk_overlap` errors are all on `ecc83`,** which is never clean in any run.
- **Control:** `xfA-mp0-jc-dev6` (`minplus_w=0`) matches jc on dev6. Length is 613 vs 614 mm and best-of-3 clean is the same.
- **Map cost:** the map runs inside jc's budget, and attempt times are unchanged.

## Verdict

**Merit for the length + vias objective; inconclusive for the physics objective.**
- **Length + vias:** with `minplus_w=1`, length is −6.5% and vias −27% on every seed, which meets the criterion. Legal and completion are equal, and clean is +0.06. The via figure leans on one board; the length figure does not.
- **Physics:** vias are −23%, mostly from noisecard, and length −3.7%. Clean is −0.04. Routed physics worsens (0.88 → 1.18) while fast physics improves (1.08 → 0.86).
- **`minplus_w=0.5`** is the safer setting under jc.

Scorecard row:

| T1 | Min-plus best-response maps (priced per-net Dijkstra fields, summed per part) in jc's part move | distance transforms, min-plus convolution | `xf`, `xf_lv` (minplus_w 1, 0.5) | **Merit** (length+vias) / inconclusive (physics) | jc_lv: −6.5% length, −27% vias on every seed at equal legal/completion (half the via cut on one board); jc: −23% vias, −4% length, clean −0.04, routed physics 0.88→1.18 |
