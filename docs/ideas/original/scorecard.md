# Scorecard: every idea from the joint place-and-route and layer-collapse work

Each idea, whether it was tested, and whether it had merit. Measured on the 33 qualified
A/B boards: KiCad DRC, kae.physics fast (place terms) and routed physics, 120 CPU-s per
board. Details: [joint-pnr-experiments](../../topics/placement/joint-pnr-experiments.md),
[joint-pnr ideas](joint-pnr.md), [layer-collapse](layer-collapse.md).

**Verdicts:**
- **Merit:** beat its control on DRC or physics.
- **Partial:** helps in some setting or as a component.
- **No merit:** did not beat a simple control.
- **Not tested:** idea only.

Baseline for "vs seq": place by HPWL, then route.

## Methods (place + route)

| # | Idea | Source domain | Tested as | Verdict | Key number |
|---|---|---|---|---|---|
| — | Own grid router (halo clearance, negotiated congestion) | FPGA PathFinder | route-only control | **Merit** (substrate) | Human placements: clean 0.85 (A) / 0.50 (B) in 2–8 s; tuned Freerouting 0.62 / 0.35 in ≤600 s |
| 43 | Physics place terms in the objective | kae.physics | `seq_phys`, `anneal_phys`, `combo` vs length+vias twins | **Merit** | Fast physics 4.05× → 1.52× human (seq), 0.97× (combo); routed physics improves too; completion, length and vias unchanged |
| — | Full routed physics at stage gates | kae routed recheck | `combo_full`, `jc_full` | **Partial** (promising) | jc_full routed physics 0.80× human, better than human on 8/10 physics boards (10 boards; open hops flatter it); combo_full still running |
| L | **Joint layer collapse by continuation**: everything lifted, one coupling β, parts and nets respond together | homotopy, deterministic annealing | `jc` | **Merit (best)** | Legal 0.879, clean 0.667, completion 0.897, fast physics 0.82×; 1 seed so far, +70% vias vs combo |
| L | Same, parts frozen after the lift | ablation | `jc_frozen` | Control | Joint uses 0.52× the copper on 24/24 boards and 59% fewer vias, so placement and routing are not separable |
| 7 | Beam search over place-one-route-it | search | `beam` (agent) | **Merit** | Completion 0.891 vs 0.868 greedy, −8% wire, physics 0.98× |
| — | combo = beam → blocker repair → physics annealing | combination | `combo` (3 seeds) | **Merit** | Legal 0.859, completion 0.896 vs seq 0.788 / 0.856 on every seed; clean +0.04 (within noise) |
| 11 | Annealing whose cost is re-routed copper | VPR, Nag–Rutenbar | `anneal`, `anneal_phys` | **Merit** | Legal 0.848, clean 0.576, −8% copper vs seq |
| 12, 13 | Blocker-directed window repair (LNS + guided local search) | vehicle-routing LNS, GLS | `repair` | **Merit** (as a stage) | dev6: legal 0.833, completion 0.921 vs 0.667 / 0.904; beat CP-SAT windows on identical windows |
| 1 | Unified negotiated congestion (parts and wires in one market) | PathFinder generalized | `negotiate` | **Partial** | Completion 0.897 (best single), but +11% copper; wire prices must decay |
| 6 | Place one part, route it, next | hand layout | `grow` | No merit alone | Same as seq; useful inside beam |
| 2, 3, 26 | Envelope-theorem pin tension + Lagrange price gradient + pin-facing rotation | envelope theorem, Lagrangian relaxation | `tension` | No merit | Completion 0.871, physics 4.2× |
| — | SimPLR-style bloating of congested parts | VLSI routability placement | `bloat` | No merit | Completion 0.748 |
| — | A-priori spacing margins (control) | — | `seq_margin` | No merit | Legal 0.727, +29% copper on v3 |
| 8 | MCTS with routing rollouts | AlphaGo | `mcts` (agent) | No merit at this budget | Too few rollouts per part; trails beam |
| 22, 23, 17 | Differentiable routing: soft-min shortest paths, gradient descent | Mensch–Blondel, Berthet | `grad` (agent) | No merit as a driver | Soft-route gradient improves routed cost 33% of the time vs HPWL 36%; +7% copper |
| 22 + 43 | Gradient global start + physics descent | combination | `grad_phys post=phys` | **Partial** | Routed physics 1.00× human, completion 0.837 |
| 20 | Physarum multi-commodity flow networks | slime-mould biology | `slime` (agent) | No merit | Neutral as a router prior; force moves barely act |
| 36 | Exact CP-SAT window place-and-route | SP&R, Numberlink SAT | `cpsat` (agent) | No merit | 0/112 wins over heuristic repair; no window proved optimal |
| 30 | LLM/VLM proposes moves, optimizer verifies | LLM agents | `llm` (agent as the LLM) | No merit (routing inconclusive) | Matched annealing on routing; about 110× worse than anneal_phys on physics; use only for diagnosis |
| T1 | Min-plus best-response maps (priced per-net Dijkstra fields, summed per part) in jc's part move | distance transforms, min-plus convolution | `xf_minplus` (minplus_w 1, 0.5) vs xf3 jc / jc_lv_nopol, joint, 3 seeds | **Inconclusive** (leans merit on vias) | Gate passed (within-part ρ 0.82 vs HPWL 0.79); vias −16 to −21% on every seed in all 4 arms at equal clean and completion, spread over ~10 boards; length ≥5% only with one board (noisecard); routed physics equal (jc) or worse (lv, w=1); round 1 (old engine, place tasks) read −27% vias, −6.5% length |
| T2 | Exact physics maps (DCT thermal, kae kernels compiled over the grid) replacing `coarse_map` in jc | Green's functions, spectral Poisson | `xf_physmap` (`jc_x`, `jc_full_x`, lift-only `jc_full_xlp`) vs xf3 jc / jc_full, joint, 3 seeds + phys10 replicate | **No merit** | Gate passed (p95 thermal 0.3%, coupling 0.3%); jc fast physics −11% on ab33 reversed by a replicate (6 attempts: −1% fast, −2% routed; identical-code noise ±0.08); jc_full routed 0.98→1.08× (worse on every seed), lift-only 1.05×; maps use a median 14–19% of CPU |
| T4 | Pour-damage maps (layer-coupled sensitivity of pour R_eff) in jc best responses and router costs | variational principles, topological derivative | `xf_pour` (`pjc2` coupled, `pjc` per-layer) vs xf3 jc / jc_lv_nopol, joint, 3 seeds | **Merit** (physics objective, coupled maps; needs confirming) | Gate ρ ≥ 0.96 per board vs exact re-solves; pjc2: pour R 0.84× jc, routed physics 1.05 ± 0.05 vs 1.18 ± 0.08, completion held (≈1.6 sd, 10 boards); no merit for length+vias (0.99×) or per-layer maps (0.94×, 1.12×) |
| 19 | Harmonic-field routing: nets as potential flow; streamlines as routes, field pressure on parts | electrostatics, potential flow | `harmonic` (`hjc_press`, `hjc_press_lv`), v7, engine v6.3, 3 seeds | No merit as a router; **partial** as part pressure (ties jc) | Streamlines: 49.5% of connections clearance-legal, 1.45× A* length. `hjc_press` vs combo on 28 boards: legal 0.988 vs 0.917, clean 0.714 vs 0.667, routed physics ~1.11× vs 1.27× human; vs jc (24 boards) within seed spread. Field density predicts copper better than RUDY on 23/33 boards. Provisional: jc baselines unfinished |
| 32 | Learned value of partial boards to prune jc restarts | AlphaZero value nets | `learn_value` (`jc_value`, `jc_value_lv`), v7, 3 seeds | No merit (provisional) | Nothing after the lift predicts a restart's end (ρ 0.12); from iteration 5 the current routed cost predicts as well (0.45 vs 0.36). Oracle pruning would buy only 3–4%; harness run ties jc |
| 16 | Quality-diversity (MAP-Elites) archive over short jc continuations | evolutionary computation | `qd`, `qd_lv`, `qdh`, v7, 3 seeds | Partial results only | See [qd_archive/RESULTS.md](../../../tools/research/qd_archive/RESULTS.md) |
| L′ | jc hardened (`jc2`): guarded PathFinder retry, legal-first restart ranking, stall stop, completion pass, via cost rising with β, via clean-up, min-plus for length+vias | ablations of jc | `jc2_fix`, `jc2_fixmp_lv`, v7, 61–62 of 99 attempts | **Merit likely** (unconfirmed) | vs jc: vias −17%, open connections 138 vs 154, clean 0.62 vs 0.56. `_lv` vs jc_lv: vias −30%, length −3.5%, open 120 vs 151. Clean gaps within seed spread |

## Layer collapse pieces

| Piece | Analog | Tested as | Verdict | Key number |
|---|---|---|---|---|
| Topological layer bounds (graph thickness) | Euler, thickness | literature + `obst` | No merit | With vias, topology never forces more than 2 layers; bound = 1 on real netlists |
| Cut-capacity bound | Cole–Siegel, Okamura–Seymour | `obst`, 112 boards | No merit as a predictor | Never forces more than 2 layers; layer counts are planes plus BGA escape |
| BGA escape formula | escape routing | `obst` | **Merit** (narrow) | Within ±1 of signal layers on all 7 fine-pitch BGAs |
| Bus via-free layers by pin order (longest decreasing subsequence, RSK) | Greene / RSK | `obst`, `cplace` | **Partial** | Best rotations would cut forced 2-layer jumpers 209 → 78 over 240 buses; helps place-then-route (bus vias 22 → 12), not the joint loop |
| Ratsnest crossings / cut overflow as placement terms | via proxies | `cplace` | No merit in the joint loop | Proxies drop, routed vias do not (118 vs 117), physics worse |
| Collapse as a router: lift, exact layer assignment, realize | via minimization, planar max-cut | `assign` (CP-SAT exact on 33/33) | No merit | Clean 0.606 vs 0.636 engine vs 0.667 random assignment |
| Lifted cost as a placement measure | lifted relaxation | `assign` placement study | **Partial** (promising) | Ranks placements by routed cost at ρ 0.85 vs HPWL 0.51; does not predict unrouted connections |
| Minimal-partition (soap-film) pours | Plateau, double bubble, MBO | `pour` | No merit | Geometry matches theory (0.45° junction error); real pours 1.01–1.05× human resistance; interleaved rails fail |
| Octilinear Wulff pours | crystalline variational problems | `pour` | No merit | Octagon reproduced; never better than isotropic |
| Pour score as a placement term | Laplace conductance | `pour` placement study | **Partial** | Full pour resistance tracks routed physics (ρ 0.65); the cheap score does not (0.11). Physics-aware placements give better pours than human (0.90×) |
| Over/under at crossings as knot diagrams; origami layer ordering | knot theory, flat folding | literature | No merit | Nothing transfers |

## Engine and harness findings (needed for any of the above)

| Finding | Effect |
|---|---|
| `--command` adapters got relative paths | Every external tool failed; fixed |
| Locked footprints were staged off-board | 7/33 place tasks were unsolvable even for the human placement; fixed |
| Legality stricter than KiCad (through-hole parts on both sides, no courtyard overhang, back-side courtyards unread) | 22/33 human placements counted as illegal; now 12 (by 0.1 mm rounding); legal rate 0.39 → 0.79 |
| Pad-local clearances, NPTH hole keep-outs, footprint Edge.Cuts, duplicate UUIDs, courtyards smaller than pads | Each caused DRC errors; fixed |
| Thermal starvation comes from placement crowding, not routing | Spoke room reserved in placement keep-outs (3 → 1 on olimex) |
| Fast physics vs full routed physics | Within-board Spearman 0.55 (0.13–0.95): fast physics alone can mislead |

## Not tested (idea only)

Congestion game (4); auction for board area (5); space-colonization growth (9);
dungeon-generator layout (10); tabu search (14); CMA-ES (15); copper as electrostatic
charge (18); homotopy on clearance (21); Tutte embedding seed (24); crossing-number
objective (25: tested only as a proxy in `cplace`); planar sub-netlist layering (27);
multigrid V-cycle (28); channel reservation (29); LLM-evolved coupling policy (31);
diffusion on joint state (33); imitation of human routing order (34); factory-game,
piping, cable-harness, urban, biochip and protein-packing transplants (35, 37–42).
