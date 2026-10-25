<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Experiment A (T1): min-plus best-response maps in jc (round 3, fixed engine)

Round 3 on pnr commit 4c4330a: joint tasks, ab33, budget 120 CPU-s, 3 seeds, against
`xf3-base-jc-ab33` (physics) and `xf3-base-jc_lv_nopol-ab33` (length + vias). The stopped
`xf2A-*` runs (old engine) are not used.

## Built

- **`minplus.py`**
  - Per-net Dijkstra fields on jc's β-priced grid: a cell costs (1+hist)(1+β·foreign), and vias are priced as the router prices them. Costs are min-pooled to 0.4 mm.
  - A part's map is the sum over its nets of the min over its pads of the shifted fields.
  - `MPCollapse` subclasses jc's `Collapse` and blends the map with jc's HPWL + tension term by `minplus_w`.
  - The wrapper loads a private copy of the current `collapse_joint/jc.py`, the code the baselines run.
  - Plug-ins:
    - `xf` / `xf_h`: phys_w 2, polish, as `jc`; `minplus_w` 1 / 0.5;
    - `xf_lv` / `xf_lv_h`: phys_w 0, no polish, as `jc_lv_nopol`;
    - `xf0`: control.
- **Tools:** `validate.py` + `gate_report.py` (gate), `test_minplus.py` (Dijkstra tests), `summarize.py` (paired length and vias, `--exclude`).

## Unit tests and gate (fixed engine)

**Unit tests:** Dijkstra is exact against Bellman-Ford on 33 grids, and no cost or field is negative on three boards at β 14. The median 2-pin field / routed priced cost is 0.98, 0.89 and 0.45; the 0.45 is paw3395, where the map is optimistic on a congested board.

**Gate on dev6** (2268 re-routed moves, β 0.05/1/5/20). Mean within-part Spearman ρ against
routed cost (mm + 2/via), the ranking a best response uses:

| | HPWL | jc term | min-plus |
|---|---|---|---|
| dev6, all moves | 0.79 | 0.78 | **0.82** |
| local / global moves | 0.68 / 0.78 | 0.66 / 0.78 | **0.71 / 0.84** |
| paw3395 | 0.62 | 0.59 | **0.72** |

- **Paired over 191 parts:**
  - min-plus − HPWL: +0.030 (95% CI +0.002 to +0.059);
  - min-plus − jc term: +0.035 (CI +0.004 to +0.065).
- **On priced cost:** +0.072 (CI +0.041 to +0.103).
- **Argmin regret:** min-plus 0.74 mm, HPWL 0.88, jc term 1.08.
- **Pooled ρ is lower for min-plus** (0.72 vs 0.97): a per-part offset that does not change a best response.

**Gate passed.** On engine v6.1 the results were nearly the same: 0.81 vs 0.79, regret 0.79 vs 1.48.
Tables: `kae-work2/xf_minplus/gate-report*.md`.

## Results (ab33, joint, budget 120, 3 seeds; all 396 attempts ok)

Table columns, from `score.sh` / `table.py`:
- legal, clean and completion: mean ± sd over seeds;
- length and vias: seed means over the boards that every run of that objective completed in every seed (26 boards for jc, 25 for lv);
- physics: method/human gmean on phys10, lower is better.

| run | legal | clean | best-of-3 | completion | length mm | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|---|
| xf3-base-jc-ab33 | 1.000 ± 0.000 | 0.687 ± 0.017 | 0.758 | 0.935 ± 0.002 | 3945 | 90 | 0.96 ± 0.08 | 1.18 ± 0.08 |
| xf3A-mp1-jc-ab33 | 0.980 ± 0.017 | 0.687 ± 0.035 | 0.727 | 0.939 ± 0.005 | 3779 (−4.2%) | 75 (−17%) | 0.85 ± 0.17 | 1.19 ± 0.11 |
| xf3A-mp05-jc-ab33 | 1.000 ± 0.000 | 0.687 ± 0.046 | 0.727 | 0.938 ± 0.002 | 3711 (−5.9%) | 72 (−20%) | 0.89 ± 0.03 | 1.18 ± 0.11 |
| xf3-base-jc_lv_nopol-ab33 | 0.990 ± 0.017 | 0.677 ± 0.035 | 0.727 | 0.942 ± 0.003 | 3465 | 61 | 1.92 ± 0.50 | 1.26 ± 0.05 |
| xf3A-mp1-lv-ab33 | 0.980 ± 0.017 | 0.707 ± 0.017 | 0.727 | 0.942 ± 0.005 | 3457 (−0.2%) | 51 (−16%) | 2.63 ± 0.10 | 1.43 ± 0.14 |
| xf3A-mp05-lv-ab33 | 0.990 ± 0.017 | 0.667 ± 0.030 | 0.697 | 0.940 ± 0.007 | 3402 (−1.8%) | 54 (−11%) | 2.35 ± 0.31 | 1.20 ± 0.06 |

Paired by seed, against the matching baseline. Each seed is compared on the boards that
seed's runs all fully routed (`summarize.py`, `kae-work2/xf_minplus/summarize-xf3A.md`):

| arm | length / seed (mean) | vias / seed (mean) | vias without noisecard | length without noisecard |
|---|---|---|---|---|
| mp1-jc | −10.2, +1.3, −3.1% (−4.0%) | −21, −12, −15% (−16%) | −19, −18, −25% (−21%) | −2.4% |
| mp05-jc | −10.7, −3.4, −3.2% (−5.8%) | −28, −18, −10% (−18%) | −13, −21, −2% (−12%) | −2.7% |
| mp1-lv | −2.4, −0.2, −0.8% (−1.1%) | −17, −18, −23% (−19%) | −11, −18, −20% (−16%) | −0.2% |
| mp05-lv | −2.5, −2.4, −3.6% (−2.8%) | −15, −26, −9% (−17%) | −5, −26, −2% (−11%) | −1.8% |

- **Vias fall on every seed in every arm, and the cut is spread over many boards.**
  - Summed over seeds, 9–11 boards have fewer vias, 3–5 more, and 11–12 are equal.
  - noisecard is the largest single contributor for `minplus_w = 0.5` and for lv (−17 to −31 vias).
  - For mp1-jc, the cut is −21% with noisecard removed.
  - Baseline seed noise in vias is about ±9% (sd over seeds without noisecard), so the sign is beyond noise.
- **The ≥5% length gains depend on noisecard.** mp05-jc's −5.9% comes mostly from noisecard on seed 0. Without it, length is −0.2 to −2.7% for every arm.
- **Legal:** 5 of 396 attempts are illegal, all shorting_items on paw3395 or biscuit-crowbar (2 in mp1-jc, 2 in mp1-lv, 1 in mp05-lv). The lv baseline has 1. Legal is 0.98–0.99 against 1.00 / 0.99, within one sd.
- **Clean and completion are equal** within noise.
- **DRC errors:**
  - mp05-jc's 39 `solder_mask_bridge` errors are all on lambdakb-trackball. The baseline has 33 there.
  - mp1 removes most of them (3).
- **Physics:** in jc, fast improves (0.85–0.89 vs 0.96) and routed is unchanged. In lv, mp1 worsens routed (1.43 vs 1.26); mp05 does not (1.20).
- **Cost:** attempt time is unchanged (127 vs 125 s).

## Verdict

**Inconclusive, leaning merit for vias.**
- **Criterion:** ≥5% length or ≥20% vias at equal legal and completion.
- **Every arm:** a seed-consistent via cut of 16–21% at equal clean and completion, spread over about 10 boards. It sits at the 20% bar rather than clearly above it.
- **Where the bar is met:**
  - mp05-jc on the fixed board set (−5.9% length, −20% vias), but only with noisecard;
  - mp1-jc without noisecard (−21% vias), at legal 0.98 vs 1.00.
- **Length gains** without noisecard are 0–3%.

Against round 1, the length gain shrank and most of the via gain stayed. The best setting is `minplus_w = 0.5`
under the physics objective. It gets −18/−20% vias at legal 1.00 with fast and routed physics
no worse.

Scorecard row:

| T1 | Min-plus best-response maps (priced per-net Dijkstra fields, summed per part) in jc's part move | distance transforms, min-plus convolution | `xf`, `xf_h`, `xf_lv`, `xf_lv_h` (minplus_w 1, 0.5) | **Inconclusive** (leans merit on vias) | gate passed (within-part ρ 0.82 vs HPWL 0.79, regret 0.74 vs 0.88 mm); ab33 joint, fixed engine: vias −16 to −21% on every seed in all 4 arms at equal clean/completion (not one board); length −1 to −6%, only ≥5% with noisecard; routed physics equal (jc) or worse (lv mp1 1.43 vs 1.26) |

## Earlier rounds (not comparable)

Round 1 (old engine, place tasks with `--probe self`) gave lv −6.5% length and −27% vias, half the via cut from noisecard. Round 2 (engine v6.1) passed the gate; its sweep was stopped for the engine fix.
