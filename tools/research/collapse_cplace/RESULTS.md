# Layer-collapse quantities as placement terms (`cplace`)

Idea: [layer-collapse](../../../docs/ideas/original/layer-collapse.md). Closed forms from
[analogs.md](../../../research_notes/layer-collapse/analogs.md) (C2, C3) used as placement
cost for position and rotation. Engine: pnr v5, 120 CPU-s, 33 A/B place tasks, KiCad DRC.

## Terms ([terms.py](terms.py))

- **fv:** forced vias of buses (part pairs joined by ≥ 3 two-pin nets). Pins are
  projected across the gap; fv = n − (λ₁+…+λ_L) of the RSK shape. L = copper layers both
  pins share, so SMD-to-SMD gives L = 1. 0.1 ms per bus (agrees with
  `collapse_obst` `bus_lds` on 6 of 9 buses; that takes 25 ms).
- **x:** crossings of the ratsnest MST segments of different nets (catalog idea 25).
- **ovf:** cut-capacity overflow on Delaunay edges of at most 4 mm between pads of
  different parts and board-edge points: Σ max(0, N(γ) − Σ_l ⌊(ℓ_free+s)/(w+s)⌋). About 5 ms.
- Pour fragmentation was not built.

**Methods** ([methods_cplace.py](methods_cplace.py), [methods_cplace_lv.py](methods_cplace_lv.py)),
all wrappers, with no edits to `pnr/`:
- `combo_collapse` adds the terms in three places: the beam child score (each candidate
  is already routed), the beam candidate order (HPWL + fv), and repair/annealing
  acceptance (a `Phys` wrapper).
- `_lv` is the same with phys_w = 0.
- `seq_collapse` is `seq_phys` plus a descent on HPWL + physics + terms over the top-4
  candidates per rotation, then routing. With weights 0 it is the control.

Final weights: w_fv = 4 mm, w_x = 1 mm, w_ovf = 0. On dev11 (dev6 plus 5 bus boards,
seed 0), fv+ovf and x alone were both within noise of `combo`.

## Results (33 boards; length and vias on the 66 board-seed pairs every run completed)

| Method (3 seeds) | Legal | Clean (per seed) | Compl. | Length | Vias |
|---|---|---|---|---|---|
| `pnr-combo-v5` | 0.859 | 0.596 (.64/.61/.55) | 0.897 | 8923 | 85 |
| **`combo_collapse`** | 0.838 | 0.606 (.61/.61/.61) | 0.893 | 9028 | 94 |
| `pnr-seq-v5` | 0.788 | 0.556 | 0.855 | 10223 | 187 |
| `seq_collapse`, weights 0 | 0.788 | 0.556 | 0.856 | 10237 | 199 |
| `seq_collapse` | 0.788 | 0.505 | 0.858 | 10180 | 194 |
| `seq_collapse_lv`, weights 0 | 0.788 | 0.556 | 0.855 | 10166 | 189 |
| `seq_collapse_lv` | 0.788 | 0.525 | 0.856 | 10094 | 190 |
| *Length + vias, seed 0* (23 complete boards) | | | | | |
| `pnr-combo_lv-v5` | 0.818 | 0.545 | 0.900 | 2998 | 32 |
| `combo_collapse_lv` | 0.848 | 0.636 | 0.894 | 3004 | 37 |

Physics, ratio to human on the 10 boards with structures (attempt 0; `kae-work/score/cplace-*.md`):

| | combo | +coll. | combo_lv | +coll. | seq_phys | sc 0 | sc | seq | sc_lv 0 | sc_lv |
|---|---|---|---|---|---|---|---|---|---|---|
| fast | **1.03** | 1.23 | 2.59 | 2.49 | 1.52 | 1.45 | 1.45 | 4.05 | 4.05 | 3.93 |
| routed | **1.13** | 1.36 | 1.26 | 1.44 | 1.26 | 1.33 | 1.22 | 1.39 | 1.38 | 1.37 |

`seq_collapse`'s clean losses are all `starved_thermal`; `combo_collapse` has more
`silk_overlap` (133 vs 87). Neither type is in any objective.

## Diagnostics ([diag.py](diag.py))

- **The terms move their proxies, not the routed vias.** Mean per seed, `combo_collapse`
  vs `combo`: crossings 372 vs 421, fv 4 vs 6, overflow 8 vs 62, but output-board vias
  118 vs 117.
- With routing outside the loop the terms do act. In `seq`, seed 0, crossings fall from
  457 to 324 and vias from 146 to 129.
- **LDS-optimal orientation.** Only 7 of 33 boards have a bus (9 buses of 3–5 nets).
  - Human: optimal on 5 of 9 buses (`collapse_obst`: 60% of 240).
  - Ours, of 27 bus-seeds: `seq` 18, `combo` 15, `seq_collapse` 21, `combo_collapse` 18.
- **Forced vias predict routed vias weakly.** Per bus, Spearman between fv and vias on the
  bus nets is 0.23 (n = 144); buses with fv > 0 get 0.89 vias against 0.51 with fv = 0.
  Board level, as pooled / within-board Spearman: crossings 0.67 / 0.39, fv 0.29 / 0.20,
  overflow 0.18 / −0.05. Capacity does not bind here (as in `collapse_obst`).

## Verdict: no merit as objective terms on these boards

- fv works as stated: more orientations are LDS-optimal, and vias on bus nets fall from
  22 to 12 in `seq`.
- But the buses are few and small.
- In the joint loop the router already prices real vias. The proxies only move vias
  around: there are 11% more vias on complete boards.
- The proxies also compete with physics: fast physics 1.23 vs 1.03, routed 1.36 vs 1.13.
- The steady 0.606 clean rate is within `combo`'s seed spread.

**Next:**
- Use fv only as an ε-tie-breaker between rotations of near-equal routed cost.
- Test it on boards with real buses: `collapse_obst`'s 55 boards, where forced jumpers
  could go from 209 to 78.
- For cheap routing-aware ranking, use `collapse_assign`'s lifted cost (Spearman 0.85
  against routed cost).

Reproduce: `run_cplace.sh SPEC NAME 120 kae-work/ab33.txt 2 3 --opt w_fv=4 --opt w_x=1 --opt w_ovf=0`,
`summarize.py`, `kae-work/score_all.sh`. Runs: `cplace-cc-fvx[-lv]-ab33`,
`cplace-sc-{fvx,zero}[-lv]-ab33`, `cplace-cc-{fvovf,x}-dev11`.
