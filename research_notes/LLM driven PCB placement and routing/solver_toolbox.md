# Optimization Solver & Computational Geometry Toolbox for a Python PCB Placement + Routing Engine (LLM-callable, 20–1000 parts, 2–8 layers)

> Research notes compiled 2026-10-20. Versions and licenses for Python packages come from PyPI metadata (`https://pypi.org/pypi/<pkg>/json`) queried that day. Method caveat: arxiv.org, readthedocs, gnu.org, docs.kicad.org and most vendor doc sites could not be reached from this environment (DNS/proxy denial), and the shared web-search budget ran out partway through. Primary sources were therefore mostly GitHub READMEs and source files, the KiCad GitLab source, PyPI metadata, and search-result snippets for papers. Where a claim rests only on a search snippet, the notes say so.

---

## 1. Exact/declarative solvers (CP-SAT, MILP, SMT, MaxSAT) for placement, floorplanning, escape routing

### Takeaway
OR-Tools CP-SAT (Apache-2.0) is the best fit for exact discrete placement and legalization. It has native `add_no_overlap_2d` over optional interval variables, keep-out handling through fixed boxes, region splitting, LNS workers built for packing, and solution hints. It finds feasible packings quickly but rarely proves infeasibility. It works on integer coordinates only, and no published benchmark shows it handling a whole 1000-part PCB in one model. Use it on clusters, for legalization, and inside LNS. MILP (HiGHS/SCIP) suits network-flow problems such as escape routing and assignment. SMT (Z3) has floorplanning and analog-placement precedents but lacks CP-SAT's global packing propagators.

### Cited Findings
**CP-SAT core facts**
- `ortools` 9.15.6755 (released 2026-01-14) is Apache 2.0 licensed — [PyPI ortools](https://pypi.org/pypi/ortools/json)
- CP-SAT has three interval constraints: `add_no_overlap`, `add_no_overlap_2d` and `add_cumulative`. `add_no_overlap_2d` "takes two lists of (optional) interval[s] and ensures that for every i and j either x_intervals[i] and x_intervals[j] or y_intervals[i] and y_intervals[j] do not overlap… If either x_intervals[i] or y_intervals[i] are optional, the whole object is optional." — [cpsat-primer, advanced_modelling.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md)
- Rotation in the primer's packing example: a bool `rotated_i`, plus width and height IntVars over `Domain.from_values([w,h])` tied together with `add_allowed_assignments([w,h,rot], [(w,h,0),(h,w,1)])`. Optional intervals take `is_present=packed_i`, giving a knapsack variant — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md)
- Scale and behaviour: "CP-SAT is good at finding a feasible packing, but incapable of proving infeasibility in most cases. When using the knapsack variant, it can still pack most of the rectangles even for the larger instances." Benchmark used a 90 s limit; "Rotations make things slightly more difficult. None of the used instances were proved infeasible." One dense packing "was found by CP-SAT in less than 0.3s… more efficient than a naive Gurobi implementation." — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md)
- Coordinate resolution matters, and the effect has varied by version. Runtime vs resolution scaling for CP-SAT 9.3 / 9.8: 1x 0.02s/0.03s; 10x 0.7s/0.02s; 100x 7.6s/1.1s; 1000x 75s/40.3s; 10,000x >15min/0.4s. The author calls this "not stabilized" — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md)
- NoOverlap2D tuning parameters in `sat_parameters.proto` (stable branch):
  - `use_timetabling_in_no_overlap_2d` projects to cumulative constraints. `use_energetic_reasoning_in_no_overlap_2d` and `use_area_energetic_reasoning_in_no_overlap_2d` add energetic reasoning. These three default to false.
  - `max_pairs_pairwise_reasoning_in_no_overlap_2d` defaults to 1250.
  - `no_overlap_2d_boolean_relations_limit` (default 10) creates left/right/above/below Booleans for small problems.
  - `maximum_regions_to_split_in_disconnected_no_overlap_2d`: "Detects when the space where items… can [be] placed is disjoint (ie., fixed boxes split the domain)… replace the original no_overlap_2d constraint by one… for each component". Default 0, which disables it.
  - `use_linear3_for_no_overlap_2d_precedences` (default true) uses linear constraints of the form `start1 - end2 + c*w <= ub` and is "particularly useful for problems where the distance between two boxes is part of the model."
  - Source: [OR-Tools sat_parameters.proto](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto)
- The primer recommends isolating the expensive packing propagators in a single custom subsolver: `subsolver_params.append(...)`, `extra_subsolvers.append(name)`, with area/energetic/timetabling on and `max_pairs_pairwise_reasoning_in_no_overlap_2d = 5_000`. That way only one worker slows down if the propagators don't help — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md)
- The CP-SAT portfolio includes packing-specific LNS workers `packing_precedences_lns`, `packing_rectangles_lns` and `packing_slice_lns`, alongside `graph_*_lns`, `rins/rens` and `violation_ls` — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md)
- Warm starts: `model.add_hint(var, val)`. "CP-SAT only benefits from complete hints (all variables hinted)." Infeasible hints can be debugged with `fix_variables_to_their_hinted_value = True`; `hint_conflict_limit` defaults to 10; `model.clear_hints()` exists. — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md); [sat_parameters.proto](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto)
- On LNS, the primer says CP-SAT "is great at solving small and medium-sized problems". For big ones, LNS "formulates a 'mini-problem' that modifies parts of the current solution… often outperforms all other approaches." — [cpsat-primer lns.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/lns.md)
- CP-SAT runs symmetry detection during presolve; the primer's example log shows "[Symmetry] … Found orbitope of size 6 x 2" — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md)
- A Dec-2025 study (seen via search snippet) benchmarks CP-SAT, MILP and a SAT encoding on slot-based facility layouts with adjacency and separation constraints. It credits CP-SAT with "natural expression of logical structure and disjunctions, and strong propagation through global constraints" and warns that "distance-based objectives generally require careful formulations to propagate effectively." — [arXiv 2512.18034 (search snippet)](https://arxiv.org/pdf/2512.18034v1)

**MILP**
- HiGHS: `highspy` 1.15.1 is MIT. "*-mit binary packages contain HiGHS and are MIT-licenced. The *-apache binary packages contain HiGHS with HiPO and are Apache-licenced" — [PyPI highspy](https://pypi.org/pypi/highspy/json); [HiGHS GitHub (search snippet)](https://github.com/ERGO-Code/HiGHS)
- SCIP 10.0, SoPlex 8.0, PaPILO 3.0 and GCG 4.0 are Apache 2.0, and SCIP has used Apache 2.0 since v8.0.3 — [SCIP Opt Suite 10.0 report (snippet)](https://arxiv.org/html/2511.18580v1); [scipopt.org (snippet)](https://scipopt.org). `pyscipopt` 6.3.0 is MIT — [PyPI](https://pypi.org/pypi/pyscipopt/json)
- `gurobipy` 13.0.3 has a proprietary license — [PyPI gurobipy](https://pypi.org/pypi/gurobipy/json)

**SMT / OMT / MaxSAT**
- `z3-solver` 5.3.1.0 is MIT and supports "bitvectors, booleans, arrays, floating point numbers, strings" — [PyPI z3-solver](https://pypi.org/pypi/z3-solver/json)
- VLSI floorplanning has been formulated as SMT and solved with Z3 on GSRC and MCNC benchmarks, targeting no-overlap with minimal area — [arXiv 1709.07241 (snippet)](https://arxiv.org/pdf/1709.07241)
- SMT analog placement (DATE 2016) treats devices as fixed-size black boxes and generates area-optimal placements at several aspect ratios. It reports "As the number of physical constraints increases, the SMT solver processing time decreases." — [DATE 2016 paper](https://past.date-conference.com/proceedings-archive/2016/pdf/0804.pdf). An IDT 2014 paper handles mirror symmetry and common-centroid constraints and notes doubly-exponential worst-case complexity — [IDT 2014 (snippet)](https://unpaywall.org/10.1109%2FIDT.2014.7038590)
- SMT-based SoC macro placement (ISCAS 2021) was released as open source — [JKU publication page](https://research.jku.at/en/publications/smt-based-placement-for-system-on-chip-design/)
- OptiMathSAT supports "incremental multi-objective optimization over linear arithmetic". Its license allows "research and evaluation purposes only. It can not be used in a commercial environment… without written permission." — [OptiMathSAT download page (snippet)](https://optimathsat.disi.unitn.it/pages/download-js.html); [OptiMathSAT home](https://optimathsat.disi.unitn.it/)
- PySAT (`python-sat`, MIT) gives a Python interface to state-of-the-art SAT solvers plus cardinality and pseudo-Boolean encodings. Its stated goal is that "it should be easy for you to implement a MaxSAT solver, an MUS/MCS extractor" — [PyPI python-sat](https://pypi.org/pypi/python-sat/json)

**Escape routing (BGA)**
- Unordered escape "can be solved optimally with network flow". Ordered escape approaches of the time could not guarantee a solution when one existed, so this ASP-DAC 2008 paper solves escape routing exactly with SAT — [ASP-DAC 2008 p244](https://www.cecs.uci.edu/~papers/aspdac08/pdf/p244_3A-4.pdf)
- Two network-flow ILPs solve simultaneous escape routing and area routing: one escapes pins to the array boundary, the other connects them — [PeerJ CS 499](https://peerj.com/articles/cs-499.pdf)
- Linear network-flow models can solve net ordering and net escape together — [Sattar & Ignjatovic, MJCS](https://jml.um.edu.my/index.php/MJCS/article/view/7006)

### Inferences
- **Scale guidance.** This is an inference; no PCB-specific CP-SAT benchmark was found. A single NoOverlap2D model with 4-way rotation, double-sided placement and an HPWL objective is realistic for one cluster of about 20–150 parts. A 1000-part board needs hierarchical decomposition: schematic sheet or net-cluster, then a cluster floorplan, then intra-cluster placement. Alternatively, run CP-SAT as a legalizer/LNS step on top of an analytical global placement.
- **Use integer coordinates on a coarse grid.** Examples are 0.05–0.1 mm for global placement and 0.01 mm only in final local legalization, given the resolution sensitivity above. Model clearance by inflating courtyards with half-clearance rather than adding pairwise distance constraints.
- **Keep-outs** become fixed intervals inside the same NoOverlap2D. Polygonal keep-outs and non-rectangular outlines can be rectangle-decomposed, for example with Shapely, into fixed boxes. Turn on `maximum_regions_to_split_in_disconnected_no_overlap_2d` when fixed boxes split the board into islands.
- **Symmetry breaking for interchangeable parts** (identical decaps or resistors in one group): add lexicographic `x_i <= x_{i+1}` (or `(x_i, y_i)` ordering). Also use CP-SAT's built-in symmetry detection.
- **SMT/OMT** adds little beyond CP-SAT here. OptiMathSAT's license rules out shipping it. Z3 is useful for small exact sub-checks (MIT) but has no NoOverlap2D propagator.
- **GPL-3.0 compatibility.** Inference from license names; see Gaps. Apache-2.0 (OR-Tools, SCIP), MIT (HiGHS, Z3, PySCIPOpt, PySAT) and BSD are generally GPLv3-compatible. Gurobi and OptiMathSAT cannot be bundled; offer them only as optional user-installed backends.

#### Example formulation A — CP-SAT placement with rotation, double-sided, keep-outs, decap proximity (pseudo-code)
```python
from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import Domain
S = 20                       # 1 unit = 0.05 mm (keep grid coarse; refine later)
m = cp_model.CpModel()

for c in comps:              # c.w, c.h = courtyard + clearance/2 on each side, in units
    rot = [m.new_bool_var(f"{c.id}_r{k}") for k in range(4)]   # 0,90,180,270
    m.add_exactly_one(rot)
    swapped = m.new_bool_var(f"{c.id}_sw"); m.add(swapped == rot[1] + rot[3])
    c.W = m.new_int_var_from_domain(Domain.from_values([c.w, c.h]), "")
    c.H = m.new_int_var_from_domain(Domain.from_values([c.w, c.h]), "")
    m.add_allowed_assignments([c.W, c.H, swapped], [(c.w, c.h, 0), (c.h, c.w, 1)])
    c.x = m.new_int_var(0, BW - min(c.w, c.h), ""); c.y = m.new_int_var(0, BH - min(c.w, c.h), "")
    c.top = m.new_bool_var(f"{c.id}_top")          # side; THT parts: present on both sides
    if c.fixed_side: m.add(c.top == c.fixed_side_is_top)
    ex, ey = m.new_int_var(0, BW, ""), m.new_int_var(0, BH, "")
    c.ix_t = m.new_optional_interval_var(c.x, c.W, ex, c.top if not c.tht else True, "")
    c.iy_t = m.new_optional_interval_var(c.y, c.H, ey, c.top if not c.tht else True, "")
    c.ix_b = m.new_optional_interval_var(c.x, c.W, ex, ~c.top if not c.tht else True, "")
    c.iy_b = m.new_optional_interval_var(c.y, c.H, ey, ~c.top if not c.tht else True, "")
    # pin positions are linear in the one-hot rotation literals:
    for p in c.pins:  # (dx_k, dy_k) = pin offset rotated by k*90 deg, precomputed
        p.X = c.x + sum(rot[k] * p.dx[k] for k in range(4))
        p.Y = c.y + sum(rot[k] * p.dy[k] for k in range(4))
        # (bottom side additionally mirrors dx; add a second one-hot over (side,rot) if needed)

# keep-outs / non-rectangular outline: fixed boxes from rectangle decomposition (Shapely)
ko_top = [(m.new_fixed_size_interval_var(kx, kw, ""), m.new_fixed_size_interval_var(ky, kh, ""))
          for (kx, ky, kw, kh) in keepout_rects_top]
m.add_no_overlap_2d([c.ix_t for c in comps] + [a for a, _ in ko_top],
                    [c.iy_t for c in comps] + [b for _, b in ko_top])
m.add_no_overlap_2d([c.ix_b for c in comps] + ..., [c.iy_b for c in comps] + ...)  # bottom

# decap proximity (hard L1 ball, linear) + soft distance term
obj = []
for (cap_pin, ic_pin, dmax) in decap_pairs:            # e.g. dmax = 2 mm -> 40 units
    dx = m.new_int_var(0, BW, ""); dy = m.new_int_var(0, BH, "")
    m.add_abs_equality(dx, cap_pin.X - ic_pin.X); m.add_abs_equality(dy, cap_pin.Y - ic_pin.Y)
    m.add(dx + dy <= dmax)                             # 'use_linear3_for_no_overlap_2d_precedences' helps here
    m.add(cap.top == ic.top).only_enforce_if(same_side_required)   # or allow under-BGA bottom
    obj.append(W_DECAP * (dx + dy))

# HPWL per net (exact, linear)
for n in nets:
    xs = [p.X for p in n.pins]; ys = [p.Y for p in n.pins]
    xmax, xmin, ymax, ymin = (m.new_int_var(0, BW, ""), m.new_int_var(0, BW, ""),
                              m.new_int_var(0, BH, ""), m.new_int_var(0, BH, ""))
    m.add_max_equality(xmax, xs); m.add_min_equality(xmin, xs)
    m.add_max_equality(ymax, ys); m.add_min_equality(ymin, ys)
    obj.append(n.weight * (xmax - xmin + ymax - ymin))

# symmetry breaking for interchangeable identical parts in one group
for a, b in zip(group[:-1], group[1:]): m.add(a.x <= b.x)

m.minimize(sum(obj))
for c in comps: m.add_hint(c.x, gp_x[c]); m.add_hint(c.y, gp_y[c])   # from analytical placer
solver = cp_model.CpSolver()
solver.parameters.num_workers = 8; solver.parameters.max_time_in_seconds = 30
# optional dedicated packing subsolver (cpsat-primer pattern)
# LNS outer loop: fix all comps outside a moving window, re-solve window, accept if better
```

### Gaps
- No published benchmark gives CP-SAT (or MILP/SMT) scale limits for PCB placement with real footprints, pin-level HPWL and rotation at 100–1000 parts. The primer's packing benchmark reports solved counts and a plot but no rectangle counts in the text.
- No open-source project was found that uses CP-SAT for PCB placement or BGA escape routing. Search budget ran out before more targeted queries (e.g. GitHub code search) could be tried.
- The full texts of arXiv 1709.07241 and 2512.18034 were unreachable (arxiv.org blocked), so their instance sizes and runtimes are not recorded.
- GPLv3 compatibility could not be re-verified against the FSF license list (gnu.org unreachable). CPLEX licensing was not checked.

---

## 2. Continuous / differentiable placement (ePlace/DREAMPlace-style, custom PyTorch/JAX losses, RUDY)

### Takeaway
The most proven scalable approach is analytical placement: a smooth wirelength model (WA or LSE) plus electrostatic density solved with a DCT-based Poisson equation, optimized with Nesterov. DREAMPlace (BSD-3) implements it in PyTorch with CPU and GPU ops, including RUDY. Cypress (Apache-2.0) adapted it for PCBs and won ISPD 2025 Best Paper. Domain terms (decap distance, keep-out SDF, thermal spreading, loop area) can be added as differentiable penalties in a custom PyTorch/JAX loss. Discrete parts (rotation, side, legality) still need relaxation plus a discrete legalizer afterwards.

### Cited Findings
- DREAMPlace is BSD-3-Clause. It reports "Over 30X speedup over the CPU implementation (RePlAce)… in global placement and legalization on ISPD 2005… with a Nvidia Tesla V100 GPU", and its ABCDPlace detailed placer gives "around 16X speedup on million-size benchmarks" — [DREAMPlace README](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/README.md); [GitHub](https://github.com/limbo018/DREAMPlace)
- DREAMPlace features by version: routability via NCTUgr (2.2), fence regions (3.0), timing-driven placement (4.0, momentum net weighting), GiFt init (4.2), and GPU timing with HeteroSTA (4.3). Tested with Python 3.5–3.9 and PyTorch 1.6–2.0; GCC 7.5 recommended; CUDA optional (compute capability ≥6.0). Inputs are Bookshelf and LEF/DEF — [DREAMPlace GitHub](https://github.com/limbo018/DREAMPlace)
- DREAMPlace ops include `weighted_average_wirelength`, `logsumexp_wirelength`, `electric_potential`, `density_map`, `rudy`, `pinrudy`, `adjust_node_area`, `abacus_legalize`, `greedy_legalize`, `macro_legalize`, `fence_region`, `hpwl` and `rmst_wl` — [DREAMPlace ops tree](https://github.com/limbo018/DREAMPlace/tree/master/dreamplace/ops)
- The WA wirelength op says "Compute weighted-average wirelength according to e-place" and takes `inv_gamma`: "1/gamma, the larger, the closer to HPWL" — [weighted_average_wirelength.py](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/ops/weighted_average_wirelength/weighted_average_wirelength.py)
- The electric potential op "according to e-place" cites the ePlace paper and computes potential with a DCT/IDCT spectral Poisson solve, with energy = Σ potential·density — [electric_potential.py](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/ops/electric_potential/electric_potential.py); [ePlace TODAES'14 paper](http://cseweb.ucsd.edu/~jlu/papers/eplace-todaes14/paper.pdf)
- DREAMPlace parameter defaults:
  - `gamma` = 4.0 ("base coefficient for log-sum-exp and weighted-average wirelength, a relative value to bin size")
  - `density_weight` = 8e-05 (initial)
  - `target_density` = 0.8
  - `stop_overflow` = 0.1
  - `routability_opt_flag` = 0; when enabled, `adjust_rudy_area_flag` = 1 ("use RUDY/RISA map to guide area adjustment"), `route_num_bins_x/y` = 512, `max_num_area_adjust` = 3
  - `global_place_stages[].optimizer` can be "nesterov, adam, s[gd]…"
  - Source: [DREAMPlace params.json](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/params.json)
- The RUDY op normalizes by `bin_area * unit_horizontal_capacity` — [rudy.py](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/ops/rudy/rudy.py)
- Cypress, "VLSI-Inspired PCB Placement with GPU Acceleration" (Zhang, Agnesina, Shbat, Leader, Zhang, Ren; ISPD 2025):
  - Apache-2.0
  - "builds upon and extends" DREAMPlace; its hyperparameter tuner is inspired by AutoDMP
  - runs via `python dreamplace/Placer.py config.json`; the tuner uses an `.aux` (Bookshelf) input
  - Sources: [Cypress README](https://raw.githubusercontent.com/NVlabs/Cypress/main/README.md); [NVlabs/Cypress](https://github.com/NVlabs/Cypress)
- Cypress reports "1–5.9× higher routability" and, on fully routed designs, "1–19.7× shorter routed track lengths". It also releases an open PCB benchmark suite built from real commercial designs, and won ISPD 2025 Best Paper — [Cypress paper (via search)](https://www.csl.cornell.edu/~zhiruz/pdfs/cypress-ispd2025.pdf); [Cornell news](https://zhang.ece.cornell.edu/news/cypress_ispd_bpa.html)
- Counter-evidence on routability: on photonic circuits, Apollo reports geometric-mean routability of 94.79%, against 50.85% for DREAMPlace (routability mode) and 51.38% for Cypress. This is a different domain — [Apollo arXiv 2504.18813 (snippet)](https://arxiv.org/pdf/2504.18813)
- RL alternative: RL_PCB (MIT, DATE 2024) learns per-component policies that minimize HPWL, Euclidean wirelength and overlap. It parses `.kicad_pcb` files and requires Python 3.8 — [RL_PCB README](https://raw.githubusercontent.com/LukeVassallo/RL_PCB/main/README.md)
- PyTorch 2.14.1 (Apache-2.0 and others) and JAX 0.12.0 (Apache-2.0) are current — [PyPI torch](https://pypi.org/pypi/torch/json); [PyPI jax](https://pypi.org/pypi/jax/json)

### Inferences
- **DREAMPlace as a library.** Its documented interface is the JSON-config CLI plus Bookshelf/DEF inputs, and it pins old Python/PyTorch/GCC. A PCB engine would need a KiCad→Bookshelf exporter (Cypress shows the route) or would reuse only individual ops. For 20–1000 parts, a lean custom JAX/PyTorch loss (no CUDA build) is likely simpler, faster to iterate on, and easier for an LLM agent to configure. GPU gives little at this size; CPU JAX with `jit` should suffice (inference, not benchmarked).
- **Rotation.** Options: (a) softmax or Gumbel-softmax over 4 orientations, with pin offsets taken as a probability-weighted mix, annealing temperature τ→0; (b) a continuous angle θ with a periodic penalty sin²(2θ) pulling toward multiples of 90°. Both are inferences; no source compared them for PCB. Snap orientation before legalization.
- **Overlap.** For tens to hundreds of parts, a pairwise soft-overlap term over STRtree/spatial-hash neighbors (softplus(overlap_x)·softplus(overlap_y)) is simpler than an FFT density grid and handles very different part sizes (a BGA next to 0201s). Electrostatic density pays off at thousands of parts.
- **Domain terms** (all differentiable penalties):
  - keep-outs and board outline: signed distance fields, rasterized once to a grid and bilinearly sampled (or analytic box SDFs)
  - decap: relu(‖pin_cap − pin_IC‖ − dmax)²
  - power-loop area: triangle area of (IC VDD pin, cap, IC GND pin)
  - thermal spreading: Σ PᵢPⱼ/(‖cᵢ−cⱼ‖²+ε)
  - connector edge attraction: SDF to the board edge
  - routability: differentiable RUDY over net bounding boxes (DREAMPlace has a `rudy` op)

#### Example formulation B — differentiable placement loss with domain terms (JAX-style pseudo-code)
```python
def wa(v, mask, gamma):          # weighted-average smooth max - smooth min (per net)
    ep = jnp.exp((v - v.max()) / gamma) * mask; en = jnp.exp((v.min() - v) / gamma) * mask
    return (v*ep).sum()/ep.sum() - (v*en).sum()/en.sum()

def loss(params, k):             # k = continuation step (anneal gamma, tau; ramp weights)
    xy, rot_logits = params["xy"], params["rot"]
    p_rot = jax.nn.softmax(rot_logits / tau(k))                   # [C,4] orientation probs
    off = jnp.einsum("pk,pkd->pd", p_rot[pin2comp], pin_off_rot)  # pin offsets mixed over 4 rots
    pin = xy[pin2comp] + off
    WL = sum(w[n] * (wa(pin[idx_n,0], m_n, g(k)) + wa(pin[idx_n,1], m_n, g(k))) for n...)  # vmap over padded nets
    # overlap on candidate pairs (rebuilt every N steps from an STRtree / grid hash)
    ox = relu(half_w[i] + half_w[j] - abs(xy[i,0]-xy[j,0])); oy = relu(half_h[i]+half_h[j]-abs(xy[i,1]-xy[j,1]))
    OVL = (softplus_beta(ox) * softplus_beta(oy)).sum()
    corners = comp_corners(xy, p_rot)                              # [C,4,2]
    KO  = (relu(clear - sdf_keepout(corners))**2).sum()            # sdf>0 outside keep-out
    OUT = (relu(sdf_outline(corners) + margin)**2).sum()           # sdf>0 outside board
    DEC = sum(relu(norm(pin[cp] - pin[ip]) - dmax)**2 for cp, ip, dmax in decaps)
    LOOP = sum(tri_area(pin[vdd], pin[cap_mid], pin[gnd]) for ...)  # hot-loop area proxy
    TH  = sum(P[i]*P[j] / (sqdist(xy[i], xy[j]) + eps) for hot pairs)
    CONG = (relu(rudy_map(pin, nets) - cap_map)**2).sum()           # differentiable RUDY
    return WL + lam_o(k)*OVL + lam_k*KO + lam_b*OUT + lam_d*DEC + lam_l*LOOP + lam_t*TH + lam_c*CONG
# optimizer: optax Nesterov/Adam; lam_o(k) ramps up ePlace-style until overlap < threshold;
# then snap rotations, legalize (CP-SAT with hints, or greedy/Abacus-like), then SA/LNS detailed placement.
```

### Gaps
- The Cypress paper PDF (cost function details, rotation and double-sided handling, benchmark sizes) could not be fetched. Its README does not describe those features.
- No source compared Gumbel-softmax with other rotation relaxations for PCB placement.
- No published differentiable formulation of PCB-specific terms (decap loop area, thermal) was found. The terms above are proposed designs.

---

## 3. Metaheuristics (SA, GA, CMA-ES, NSGA-II/III, MAP-Elites, tabu, LNS) and libraries

### Takeaway
Use metaheuristics as the outer search and for detailed placement, not as the main global placer for 1000 parts. Simulated annealing with incremental cost (swap, shift, rotate, flip moves) remains the practical detailed-placement workhorse. pymoo (Apache-2.0) gives NSGA-II/III, MOEA/D and others for Pareto trade-offs. pyribs (MIT) gives MAP-Elites/CMA-ME/CMA-MAE for producing diverse layout alternatives an LLM can choose between. pycma (BSD-3) and Nevergrad (MIT) handle continuous weight vectors. DEAP is LGPL.

### Cited Findings
- pymoo 0.6.2 is Apache-2.0. Its `pymoo/algorithms/moo` modules include nsga2, nsga3, unsga3, rnsga2, rnsga3, moead, age/age2, ctaea, rvea, sms, spea2, mocmaes, como_cmaes, gde3, nsde, mopso_cd, cmopso, dnsga2, pinsga2 and kgb — [PyPI pymoo](https://pypi.org/pypi/pymoo/json); [pymoo moo dir](https://github.com/anyoptimization/pymoo/tree/main/pymoo/algorithms/moo)
- pyribs (`ribs` 0.12.0, MIT) provides MAP-Elites-family quality-diversity algorithms including CMA-ME, CMA-MEGA, CMA-MAE "and scalable variants of CMA-MAE", built on archive/emitters/scheduler with an `ask()`/`tell()` loop — [PyPI ribs](https://pypi.org/pypi/ribs/json)
- DEAP 1.4.4 is LGPL. It offers GAs with arbitrary representations, GP, CMA-ES, and multi-objective "NSGA-II, NSGA-III, SPEA2, MO-CMA-ES", with multiprocessing/SCOOP parallelism — [PyPI deap](https://pypi.org/pypi/deap/json)
- Nevergrad 1.0.12 (MIT, last release 2025-04-23) offers gradient-free optimization with the `NGOpt` meta-optimizer — [PyPI nevergrad](https://pypi.org/pypi/nevergrad/json)
- `cma` (pycma) 4.5.0 is BSD-3-Clause — [PyPI cma](https://pypi.org/pypi/cma/json)
- `pygad` 3.9.2 exists, but its PyPI license field shows only a copyright line — [PyPI pygad](https://pypi.org/pypi/pygad/json)
- The cpsat-primer author argues that LNS with CP-SAT "often outperforms" hand-built metaheuristics, citing Sörensen's "Metaheuristics – The Metaphor Exposed" — [cpsat-primer lns.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/lns.md)
- RL_PCB reports that its learned policies outperform "stochastic methods" (it compares against SA-type baselines) — [RL_PCB README](https://raw.githubusercontent.com/LukeVassallo/RL_PCB/main/README.md)

### Inferences
- **Suggested split:**
  - SA or tabu with O(Δ) incremental HPWL and overlap updates for detailed placement, run in a Rust core
  - CP-SAT LNS windows for legal re-packing of crowded regions
  - NSGA-II/III (pymoo) or MOTPE/NSGA-II (Optuna) over placer weights, giving a Pareto front of wirelength, routability, thermal and EMI proxies
  - MAP-Elites (pyribs) with behaviour descriptors such as aspect ratio, side usage or connector edge to hand an LLM qualitatively different candidates
- DEAP's LGPL is GPLv3-compatible for this project, but pymoo and pyribs cover the same ground with permissive licenses and better maintenance signals (inference from release dates above).

### Gaps
- No quantitative comparison of SA, GA and CMA-ES specifically on PCB placement was found. RL_PCB's comparisons could not be checked in the DATE paper (IEEE blocked).
- No PCB-specific use of MAP-Elites was found.

---

## 4. Bayesian optimization / hyperparameter tuning of placer & router weights; LLM-guided tuning

### Takeaway
Tuning placer and router knobs with multi-objective BO is established practice in VLSI. AutoDMP runs MOBO over DREAMPlace parameters, and Cypress ships a tuner inspired by it. Optuna 5.x (MIT) is the pragmatic default (TPE/MOTPE, NSGA-II, CMA-ES, GP, AutoSampler, constraints, pruning). BoTorch/Ax (MIT) fit custom MOBO. SMAC3 (BSD-3) fits multi-fidelity, Hyperband-style tuning. Evidence for LLM-guided tuning could not be verified here.

### Cited Findings
- AutoDMP (ISPD 2023, NVIDIA) builds on DREAMPlace and ABCDPlace and adds "automatic parameter tuning based on multi-objective hyperparameter Bayesian optimization (MOBO)". Its example runs "20 iterations with 2 parallel workers", with the search space in `configspace.json` — [AutoDMP README](https://raw.githubusercontent.com/NVlabs/AutoDMP/main/README.md)
- Cypress includes `tuner/run_tuner.sh` with a PCB config space (`test/tune/pcb-configspace.json`) — [Cypress README](https://raw.githubusercontent.com/NVlabs/Cypress/main/README.md)
- Optuna 5.0.0 (2026-09-07) is MIT. An Oct-2025 post announced "AutoSampler: Full Support for Multi-Objective & Constrained Optimization" via OptunaHub. Rustuna, an experimental Rust reimplementation, "supports TPE, MOTPE, NSGA-II, and CMA-ES, and finishes the same study several times to several hundred times faster for cheap objective functions." — [PyPI optuna](https://pypi.org/pypi/optuna/json)
- BoTorch 0.18.1 (MIT) provides "Bayesian Optimization in PyTorch" with Monte-Carlo acquisition functions and underpins Ax — [PyPI botorch](https://pypi.org/pypi/botorch/json)
- SMAC 2.4.1 (BSD-3): "All facades/intensifiers support multi-objective, multi-fidelity". Since 2.4.0 its default surrogate is sklearn's random forest — [PyPI smac](https://pypi.org/pypi/smac/json)

### Inferences
- **For an LLM-driven engine:** expose a typed parameter space (wirelength vs density vs decap vs thermal weights, grid pitch, router via cost, history factor) to Optuna. Run multi-objective studies using cheap proxies (Section 8). Let the LLM (a) choose which weights and constraints to vary from the design intent and (b) read the Pareto front and pick one. Optuna's ask/tell API suits an agent driving trials step by step.
- Multi-fidelity BO (SMAC or Optuna pruning) maps naturally onto increasing fidelity: HPWL → RUDY → a quick maze route → full Freerouting + KiCad DRC.

### Gaps
- No primary source was retrieved for LLM-guided BO (e.g. LLAMBO) or for LLM-tuned EDA parameters; the guessed LLAMBO repo URLs returned 404 and search budget was exhausted. This needs follow-up.
- No PCB-specific study of BO-tuned placer weights was found beyond Cypress's tuner mention.

---

## 5. Routing engines (maze/A*, PathFinder negotiated congestion, Lee, any-angle, MAPF, Freerouting, tscircuit, KiCad PNS)

### Takeaway
For a GPL-3.0 Python engine, the most robust path combines two things. First, an in-house grid/graph router: A* on a 3D (x, y, layer) lattice with PathFinder negotiated congestion and rip-up/reroute, with the core in Rust or C++. Second, Freerouting (GPL-3.0, Java), headless via CLI or local REST API, as a strong baseline and fallback. KiCad 10's IPC API does not expose the push-and-shove (PNS) router or autorouting. KiCad master (11.0-dev) has just added Specctra DSN export to kicad-cli and SES import to the API. tscircuit's MIT autorouter is TypeScript and usable through a Node subprocess. Topola (Rust, MIT) is still work in progress.

### Cited Findings
**PathFinder**
- Patent wording of PathFinder cost: "Cost(R) = (BasicCost + Hist_Cong) × (1 + SharePenalty × Num_Contend)", with history "increased after each iteration in which there is a conflict" — [US patent 8312409 (snippet)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8312409)
- Course notes write node cost as Cn = (bn + hn) × pn (base, history, present-sharing) — [Lafayette PathFinder page (snippet)](https://sites.lafayette.edu/cadapps/main-page/pathfinder-fpga-routing-algorithm/)
- Lecture notes on the original 1995 McMurchie & Ebeling algorithm: [TU Darmstadt router-pathfinder.pdf](https://www.esa.informatik.tu-darmstadt.de/archive/twiki/pub/Lectures/AlgorithmenImChipEntwurfDe/router-pathfinder.pdf)

**OrthoRoute** (PathFinder on PCBs)
- MIT license, v1.0.0, KiCad 10+ IPC-API plugin. It models the PCB as a lattice graph (via sites as nodes, trace segments as edges) and runs negotiated congestion with rip-up of the worst offenders — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- GPU is used through a CUDA/CuPy parallel-Dijkstra (SSSP) kernel per net, or Metal on Apple; "Nets are still routed sequentially on a shared congestion map". VRAM depends on board size, layers and pitch, not net count. 500 vs 8,000 nets on a 200×200 mm, 20-layer board take the same VRAM but the larger case is about 16× slower — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- It is explicitly "not a general-purpose PCB autorouter" and is aimed at dense regular backplanes and BGA escape — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute); [Hackaday](https://hackaday.com/2026/07/01/gpu-accelerated-autorouter-handles-monstrous-pcb-designs/)

**PCBWorld benchmark** (arXiv 2607.05915, July 2026)
- Open KiCad-based routing environment with three dataset families, including 679 real open-source boards, and "eight engine-checked evaluation metrics". Tasks are routed-then-stripped KiCad boards — [PCBWorld (search snippet)](https://arxiv.org/abs/2607.05915); [HF papers](https://huggingface.co/papers/2607.05915)
- Per the OrthoRoute README, OrthoRoute scored 1% clean-pass / 30% routability on synthetic D2 and 2% / 51% on D3-A (99 real boards). The README says "Freerouting and KiCadRoutingTools performed dramatically better". That is a secondary account by the OrthoRoute author — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)

**Freerouting**
- GPL-3.0; Java JRE 25 recommended. Has GUI, CLI and API; Docker image `ghcr.io/freerouting/freerouting` (amd64/arm64/armv7); an MCP server (`@freerouting/freerouting-mcp-server`); and a beta hosted REST API at `api.freerouting.app/v1`. "a full run may take from a few minutes to several hours" — [Freerouting README](https://github.com/freerouting/freerouting)
- CLI flags:
  - input/output: `-de` (DSN in, optionally `+ses+rules`), `-do` (DSN/SES/SCR out), `-dr` rules, `-drc` (writes the DRC report in KiCad JSON format)
  - headless: `--gui.enabled=false`
  - search control: `-mp` max passes; `-mt` optimizer threads (0 disables optimization); `--router.optimizer.improvement_threshold` (default 2.5%); `-us greedy|global|hybrid`; `-is sequential|random|prioritized`; `-inc` ignore net classes; `-im` checkpoints
  - per-layer arrays such as `--router.layers.routable=false,true`
  - local REST server: `--api_server.enabled=true --api_server.endpoints=http://127.0.0.1:37864`; env vars `FREEROUTING__…`
  - Source: [Freerouting command_line_arguments.md](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md)
- `freerouting-client` 2.3.0 (MIT) is the official Python client — [PyPI](https://pypi.org/pypi/freerouting-client/json)
- KiCad integration goes through a Plugin-and-Content-Manager plugin (KiCad ≥6.0) and Specctra DSN/SES exchange — [Freerouting integrations.md](https://github.com/freerouting/freerouting/blob/master/docs/integrations.md)

**KiCad PNS / IPC API**
- `RunAction` "Runs a TOOL_ACTION… WARNING: The TOOL_ACTIONs are specifically *not* an API. Command names may change… provided for low-level prototyping purposes only." — [KiCad editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/common/commands/editor_commands.proto)
- The API offers `BeginCommit`/`EndCommit`, `CreateItems`/`UpdateItems`/`DeleteItems`, `GetBoundingBox` and selection — [same file](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/common/commands/editor_commands.proto)
- Board API: `GetNets`, `GetItemsByNet`, `GetConnectedItems`, `GetNetClassForNets`, design-rule get/set, `RefillZones`, `GetPadShapeAsPolygon`, `CheckPadstackPresenceOnLayers`, `InjectDrcError`, `FlipItems`. It also has `ImportSpecctraSession`, marked "Since: 11.0", which "repositions footprints, deletes unlocked existing tracks and vias, and adds the tracks and vias routed in the external router session". No routing or autoroute command exists — [KiCad board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto)
- KiCad master commits on 2026-10-14: "CLI: Add pcb export specctra_dsn" and "API: Support specctra import/export". The latest stable tag is 10.0.7 (2026-10-06), so both are 11.0-dev only — [GitLab commits API](https://gitlab.com/api/v4/projects/kicad%2Fcode%2Fkicad/repository/commits?path=kicad/cli/command_pcb_export_specctra.cpp&per_page=100); [tags](https://gitlab.com/api/v4/projects/kicad%2Fcode%2Fkicad/repository/tags?search=10.0&per_page=5)
- `kicad-python` 0.8.0 (MIT, 2026-08-30) is the official IPC API binding — [PyPI kicad-python](https://pypi.org/pypi/kicad-python/json)
- Router-related action names exist (e.g. `pcbnew.InteractiveRouter.DiffPair`), but 122 actions were added and 47 removed between 9.0 and 10.0 (third-party claim) — [Adom KiCad bridge (snippet)](https://wiki.adom.inc/adom/kicad-bridge/files/KICAD-PLUGIN-PROMPT.md)

**tscircuit autorouter**
- `@tscircuit/capacity-autorouter` is MIT and "composed of hundreds of algorithms organized in a Pipeline… uses successive approximation and Hypergraphs rather than sequential routing" — [README](https://raw.githubusercontent.com/tscircuit/tscircuit-autorouter/main/README.md); [blog: hypergraph autorouting](https://blog.autorouting.com/p/hypergraph-autorouting)
- Input is `SimpleRouteJson`: layerCount, minTraceWidth, rectangular obstacles (with rotation), connections, buses (`maxLengthSkew`), differential pairs (`lengthTolerance`, `traceGap`, `maxUncoupledLength`), `allowViaInPad`. Output is wire/via traces. Usage is a `solver.step()` loop — [README](https://raw.githubusercontent.com/tscircuit/tscircuit-autorouter/main/README.md)

**Topola**
- Rust topological (gridless, any-angle) interactive router/autorouter; MIT; WIP crate 0.1.0; NLnet NGI0 Entrust funded — [docs.rs topola](https://docs.rs/crate/topola/0.1.0); [NLnet](https://nlnet.nl/project/Topola/); [Codeberg](https://codeberg.org/mikolaj/topola)

**MAPF and grid-path libraries**
- libMultiRobotPlanning: MIT, header-only C++14. Provides A*, A*-epsilon (focal), SIPP, CBS, ECBS, CBS-TA, ECBS-TA, prioritized planning and flow-based assignment. No Python bindings were found — [README](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/README.md); [LICENSE](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/LICENSE)
- Original CBS paper: Sharon et al., AAAI 2012 — [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/8140)
- No paper applying CBS to PCB routing was found in search.
- `pathfinding` 1.0.22 (MIT): grid A*, Dijkstra, Best-First, bidirectional A*, BFS, IDA* and MST. No Theta* listed — [PyPI pathfinding](https://pypi.org/pypi/pathfinding/json)
- `pyvisgraph` 0.2.1 (visibility graphs) was last released in 2018 — [PyPI](https://pypi.org/pypi/pyvisgraph/json)
- Graph libraries: `networkx` 3.7 (BSD-3), `rustworkx` 0.18.1 (Apache-2.0) — [PyPI networkx](https://pypi.org/pypi/networkx/json); [PyPI rustworkx](https://pypi.org/pypi/rustworkx/json)

### Inferences
- **KiCad PNS cannot be scripted stably from Python today.** `RunAction` can fire interactive tools but is explicitly unstable and needs GUI interaction. Embedding PNS means compiling against KiCad's C++ sources (GPL-3.0+, so license-compatible with a GPL-3.0 project). That is a heavy, version-fragile dependency.
- **Practical round-trip with released KiCad 10:** export DSN through the GUI or legacy pcbnew Python (SWIG), run Freerouting headless, re-import the SES. Once 11.0 ships, use `kicad-cli pcb export specctra_dsn` plus IPC `ImportSpecctraSession`. Alternatively, write tracks and vias directly through IPC `CreateItems` inside a `BeginCommit`/`EndCommit`.
- **MAPF (CBS/ECBS)** fits short, local, multi-net problems such as fan-out and escape around a BGA, or bus routing with ordering, rather than whole-board routing. PathFinder's negotiation is the scalable whole-board analogue.
- **Any-angle routing** (Theta*, Topola-style) is attractive for final quality but harder to make DRC-robust. Route on a 45°-capable octilinear lattice, then smooth and shrink-wrap with Clipper/Shapely in a post-pass.

#### Example formulation C — negotiated-congestion (PathFinder) multi-layer grid router (pseudo-code)
```python
# Graph: nodes (ix, iy, layer) at pitch = trace_w + clearance (per netclass: use widest or multi-track occupancy)
# cap[n] = 1 for track nodes; pad/via-keepout nodes pre-blocked except for own net; via edges cost via_cost
hist = zeros(N); pres_fac = 0.5; HIST_FAC = 1.0; PRES_GROW = 1.6
def node_cost(n, net):
    if blocked[n] and owner[n] != net: return INF
    over = max(0, occ[n] + 1 - cap[n])
    return (base[n] + hist[n]) * (1 + pres_fac * over)      # PathFinder: (b + h) * p

order = sort(nets, key=lambda n: (-n.criticality, n.bbox_halfperimeter))   # diff pairs/buses first
for it in range(MAX_IT):
    for net in order:
        if it > 0 and not any(occ[v] > cap[v] for v in route[net]): continue   # only re-route offenders
        rip_up(net)                                    # occ[v] -= 1 for v in route[net]
        tree = {pins_of(net)[0]}
        for sink in prim_order(pins_of(net)):          # Steiner-ish: A* from current tree to next sink
            path = astar(sources=tree, goal=sink, cost=lambda v: node_cost(v, net),
                         h=lambda v: manhattan(v, sink) * min_base + layer_delta(v, sink) * via_cost,
                         bbox=expand(net.bbox, margin(it)))           # bounded search window, grows with it
            tree |= set(path)
        route[net] = tree; for v in tree: occ[v] += 1
    over_nodes = [v for v in V if occ[v] > cap[v]]
    if not over_nodes: break
    for v in over_nodes: hist[v] += HIST_FAC * (occ[v] - cap[v])
    pres_fac *= PRES_GROW
# post: path -> segments (merge collinear), 45-degree smoothing, neck-down at pads,
# write via KiCad IPC CreateItems in one commit; run kicad-cli pcb drc; repair or fall back to Freerouting
```

### Gaps
- PCBWorld's exact Freerouting and KiCadRoutingTools numbers and its eight metrics were not retrieved (arXiv/HF blocked). "KiCadRoutingTools" could not be identified.
- The current pcbnew SWIG `ExportSpecctraDSN`/`ImportSpecctraSES` signatures for KiCad 10 were not re-verified (GitLab file paths returned a non-raw page). The SWIG binding's deprecation timeline was not retrieved.
- Freerouting runtime as a function of board size was not quantified beyond "minutes to several hours".
- No Python-bound Theta* or any-angle router library was verified.

---

## 6. Computational geometry libraries (Shapely/GEOS, Clipper2, CGAL, R-trees, triangulation, SDF, Minkowski/NFP)

### Takeaway
Shapely 2.x (BSD-3, with bundled LGPL-2.1 GEOS) is the default for polygons, buffers and vectorized predicates. Its STRtree is fast but immutable, so rebuild it per batch or use `rtree` (MIT, supports insert/delete) for incremental updates. Clipper2 (Boost license) is the best engine for integer-robust clearance offsetting and booleans, via `pyclipr` (Boost) or `pyclipper` (Clipper1, MIT). For constrained Delaunay triangulation use PythonCDT (MPL-2.0/BSD/Apache) and avoid `triangle`: its upstream Shewchuk code restricts commercial distribution. CGAL's Python bindings are GPLv3+ and experimental.

### Cited Findings
- Shapely 2.2.0 (2026-10-07) is BSD-3-Clause — [PyPI shapely](https://pypi.org/pypi/shapely/json)
- Its STRtree "is created using the Sort-Tile-Recursive (STR) algorithm… constructed directly at initialization and nodes cannot be added or removed"; `node_capacity` defaults to 10. `query(geometry, predicate=..., distance=...)` supports 'intersects', 'within', 'contains', 'overlaps', 'crosses', 'touches', 'covers', 'covered_by', 'contains_properly' and 'dwithin' (distance required). It accepts arrays of geometries and returns index pairs — [shapely/strtree.py](https://raw.githubusercontent.com/shapely/shapely/main/src/shapely/strtree.py)
- GEOS is LGPL v2.1 — [GEOS COPYING](https://raw.githubusercontent.com/libgeos/geos/main/COPYING)
- `rtree` 1.4.1 (MIT) wraps libspatialindex and supports nearest-neighbour search, intersection, bulk loading, deletion and disk serialization — [PyPI rtree](https://pypi.org/pypi/rtree/json)
- Clipper2 does intersection, union, difference, XOR and "polygon offsetting" in C++17/C#/Delphi under the Boost Software License 1.0. Its README links a discussion "Why there haven't been any updates in the last 6 months" — [Clipper2 README](https://raw.githubusercontent.com/AngusJohnson/Clipper2/main/README.md)
- `pyclipr` 0.1.8 is a pybind11 Clipper2 binding (Boost license). Its README says pre-built packages cover "Windows, Mac but excludes Linux"; Linux needs a source build — [PyPI pyclipr](https://pypi.org/pypi/pyclipr/json)
- `pyclipper` 1.4.0 (MIT) is a Cython wrapper of Clipper1 — [PyPI pyclipper](https://pypi.org/pypi/pyclipper/json)
- `PythonCDT` 2.0.2 (license "MPL-2.0 AND BSD-3-Clause AND Apache-2.0 WITH LLVM-exception") binds artem-ogre's CDT C++ library, has wheels for Linux, macOS and Windows, and resolves intersecting constraint edges (`IntersectingConstraintEdges.TRY_RESOLVE`) — [PyPI PythonCDT](https://pypi.org/pypi/PythonCDT/json)
- The `triangle` Python wrapper (20250106) is LGPL-3.0 but wraps Shewchuk's Triangle — [PyPI triangle](https://pypi.org/pypi/triangle/json). Upstream terms: "Distribution of this code as part of a commercial system is permissible ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR" — [Triangle README (libigl mirror)](https://raw.githubusercontent.com/libigl/triangle/master/README); "may not be sold or included in commercial products without a license" — [wo80/Triangle README](https://raw.githubusercontent.com/wo80/Triangle/master/README.md)
- `mapbox-earcut` 2.1.0 is ISC (ear-clipping triangulation) — [PyPI](https://pypi.org/pypi/mapbox-earcut/json)
- `cgal` 6.0.1 (last release Oct 2024) is GPLv3+; "This project is still experimental" — [PyPI cgal](https://pypi.org/pypi/cgal/json)
- scikit-geometry is LGPL-3.0 and is not on PyPI (the PyPI lookup failed) — [scikit-geometry LICENSE](https://raw.githubusercontent.com/scikit-geometry/scikit-geometry/master/LICENSE)
- `skia-pathops` 0.9.2 (BSD-3) does path booleans; `manifold3d` 3.5.4 (Apache) and `trimesh` 5.1.1 (MIT) are 3D — [PyPI skia-pathops](https://pypi.org/pypi/skia-pathops/json); [PyPI manifold3d](https://pypi.org/pypi/manifold3d/json); [PyPI trimesh](https://pypi.org/pypi/trimesh/json)
- KiCad itself can return exact pad copper as polygons through the IPC `GetPadShapeAsPolygon` ("approximate curves as a series of segments") — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto)

### Inferences
- **Incremental DRC-like checks in an optimization loop.** Keep a three-tier check:
  1. axis-aligned courtyard boxes in NumPy, or a uniform grid hash in Rust (O(1) update per move)
  2. exact polygon tests only for pairs whose boxes are within clearance, using Shapely vectorized `dwithin`/`intersects` or Clipper2 offsets on integer nm coordinates
  3. full KiCad DRC (`kicad-cli pcb drc`) only for finalists
- STRtree's immutability makes it a poor fit for per-move updates. Rebuild it per SA temperature step or per optimizer epoch, or use `rtree` insert/delete.
- **Minkowski sums / no-fit polygons.** For courtyards that are near-rectangles, inflating by clearance (Clipper offset) is the practical Minkowski sum with a disk. True NFPs matter only for strongly concave outlines; no maintained, permissively licensed Python NFP library was verified (see Gaps).
- **SDFs** for keep-outs and outlines: rasterize Shapely polygons and compute a distance transform (e.g. SciPy `distance_transform_edt`) once per board, then sample bilinearly in JAX/PyTorch (inference; SciPy not verified here).
- **Triangulation.** Constrained Delaunay over obstacles and pads (PythonCDT) gives routing channels for topological or any-angle global routing (Topola-like). For license safety, avoid `triangle`.

### Gaps
- No published benchmark compares Shapely, Clipper2 and CGAL throughput for PCB-sized DRC loops. Performance claims above are inferences.
- No maintained Python no-fit-polygon library was verified (search budget exhausted).
- The FSF GPLv3-compatibility list could not be fetched to confirm the compatibility of MPL-2.0, Boost, ISC and LGPL with GPLv3.

---

## 7. Performance engineering (Rust/C++ cores via PyO3, incremental evaluation, GPU, parallel restarts)

### Takeaway
Keep the orchestration and LLM tool layer in Python. Put the hot loops (incremental cost, SA moves, A*/PathFinder, spatial hashing) in a Rust crate exposed through PyO3/maturin. Use CP-SAT's multi-worker portfolio and process-level parallel restarts. Reserve GPU (JAX/PyTorch/CuPy) for analytical placement at the high end of the size range or for very large routing lattices.

### Cited Findings
- `maturin` 1.15.0 ("MIT OR Apache-2.0") builds and publishes "crates with pyo3, cffi and uniffi bindings" — [PyPI maturin](https://pypi.org/pypi/maturin/json)
- Rustuna, Optuna's Rust reimplementation, is "several times to several hundred times faster for cheap objective functions" — [PyPI optuna](https://pypi.org/pypi/optuna/json)
- DREAMPlace's GPU speedups are >30× (global placement) and about 16× (detailed placement) on million-cell VLSI. It also runs multi-threaded on CPU — [DREAMPlace README](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/README.md)
- OrthoRoute's GPU parallelism sits inside the single-net shortest-path search (CUDA SSSP); nets stay sequential — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- CP-SAT uses `num_workers` for a parallel portfolio; `interleave_search` gives deterministic search independent of worker count — [sat_parameters.proto](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto); [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md)
- Freerouting's optimizer threads are set with `-mt` (default: logical processors − 1) — [Freerouting CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md)
- libMultiRobotPlanning is "highly templated for good performance" header-only C++14 — [README](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/README.md)

### Inferences
- **Incremental evaluation is the biggest lever for SA, LNS and detailed placement.** Keep per-net min/max pin coordinates with counts so a move updates HPWL in O(pins of moved part). Use a grid hash for overlap. Keep a per-bin RUDY array updated by subtracting and adding moved nets' boxes.
- **Use parallel restarts with diverse seeds** (multiprocessing or Ray) together with Optuna's parallel trials. For 20–1000 parts, CPU parallelism is likely more cost-effective than GPU. This is an inference: OrthoRoute's own guidance is that its GPU approach targets thousands-of-nets backplanes.

### Gaps
- No measured Python-vs-Rust speedups for PCB placement or routing kernels were found.

---

## 8. Multi-fidelity evaluation (fast proxies during search, accurate checks at the end)

### Takeaway
Build a fidelity ladder:

| Level | Check | Cost |
|---|---|---|
| L0 | HPWL/RSMT + overlap + constraint penalties | µs–ms |
| L1 | RUDY/pin-density congestion map | ms |
| L2 | quick global route / coarse PathFinder with a capped iteration count | 0.1–2 s |
| L3 | full detailed route with Freerouting headless (`-mp`, `-mt 0` for speed) or the in-house router | minutes |
| L4 | KiCad DRC JSON + rule checks (decap loop, impedance) | final |

This mirrors VLSI practice: DREAMPlace's RUDY-guided area adjustment, and AutoDMP/Cypress tuning on placement metrics.

### Cited Findings
- DREAMPlace uses RUDY/RISA maps for routability-driven area adjustment (`adjust_rudy_area_flag`, `max_num_area_adjust`=3) and can call NCTUgr for routability — [params.json](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/params.json); [DREAMPlace GitHub](https://github.com/limbo018/DREAMPlace)
- Freerouting exposes fidelity knobs: `-mp` (max passes), `-mt 0` (disable optimization), `--router.optimizer.improvement_threshold` (default 2.5%; higher is faster), and `-drc` for a KiCad-format JSON DRC report. Full runs take "a few minutes to several hours" — [Freerouting CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md); [Freerouting README](https://github.com/freerouting/freerouting)
- SMAC facades support multi-fidelity and multi-objective optimization — [PyPI smac](https://pypi.org/pypi/smac/json)
- PCBWorld scores routing with "eight engine-checked evaluation metrics" on KiCad boards. This is a candidate L3/L4 harness — [PCBWorld (snippet)](https://arxiv.org/abs/2607.05915)
- Cypress measures routability and routed track length after full routing (1–5.9× routability; 1–19.7× shorter tracks), so final fidelity requires a real router — [Cypress paper (via search)](https://www.csl.cornell.edu/~zhiruz/pdfs/cypress-ispd2025.pdf)
- Apollo's results suggest wirelength- and density-driven placers can still score low on routability (about 51% for DREAMPlace and Cypress on photonic benchmarks), so proxies need validation against routed outcomes — [Apollo (snippet)](https://arxiv.org/pdf/2504.18813)

### Inferences
- **Calibrate L1/L2 against L3 on a sample of boards.** For example, check the rank correlation between the RUDY-overflow proxy and Freerouting completion and via count. Re-weight the proxy accordingly; Optuna or SMAC multi-fidelity can automate this.
- **Give the LLM agent explicit control over fidelity**, via a tool such as "evaluate(candidate, level=…)", so it spends expensive evaluations only on Pareto finalists.

### Gaps
- No published correlation between RUDY-type proxies and actual PCB autorouter completion was found.

---

## 9. Recommended solver stack for an LLM-driven KiCad placer/router

### Takeaway
A hybrid pipeline, all GPL-3.0-compatible by license name:

1. KiCad IPC API (kicad-python) for I/O.
2. Python orchestration, with Rust (PyO3) hot loops.
3. Hierarchical clustering, then CP-SAT floorplanning of clusters and constrained sub-placement.
4. JAX/PyTorch analytical global placement with domain penalties (or Cypress/DREAMPlace when GPU is available).
5. CP-SAT legalization and LNS, then SA detailed placement.
6. Optuna multi-objective weight tuning and pyribs diversity.
7. In-house PathFinder/A* router, with Freerouting headless as baseline and fallback.
8. KiCad DRC as the final check.

Shapely, Clipper2 and rtree carry the geometry; PythonCDT supplies routing channels.

### Cited Findings
Key facts behind the mapping (details and citations in Sections 1–8):
- CP-SAT: NoOverlap2D, optional intervals, hints and packing LNS; Apache-2.0 — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md); [PyPI ortools](https://pypi.org/pypi/ortools/json)
- DREAMPlace (BSD-3) and Cypress (Apache-2.0, a PCB-adapted DREAMPlace) — [DREAMPlace](https://github.com/limbo018/DREAMPlace); [Cypress](https://github.com/NVlabs/Cypress)
- Freerouting (GPL-3.0): headless CLI and REST API — [Freerouting CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md)
- KiCad IPC API: commits, item CRUD, pad polygons, no router; Specctra CLI/API only in 11.0-dev — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto); [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/common/commands/editor_commands.proto)
- Library licenses on PyPI: Optuna MIT, pymoo Apache-2.0, pyribs MIT, BoTorch MIT, SMAC BSD-3, Shapely BSD-3, rtree MIT, pyclipr Boost, PythonCDT MPL/BSD/Apache, HiGHS MIT, PySCIPOpt MIT, Z3 MIT, rustworkx Apache-2.0, maturin MIT/Apache — [PyPI JSON API](https://pypi.org/)

### Inferences

**Subproblem → tool mapping**

| Subproblem | Primary tool | Alternatives / notes | License |
|---|---|---|---|
| Board/netlist I/O, writing placements and tracks | `kicad-python` (IPC API) in `BeginCommit`/`EndCommit`; `GetPadShapeAsPolygon` for exact copper | pcbnew SWIG for headless KiCad 10; `.kicad_pcb` S-expression parsing | MIT (KiCad GPL-3+) |
| Clustering and hierarchy (sheets, connectivity, power domains) | NetworkX/rustworkx community detection + schematic hierarchy | LLM proposes groupings and constraints | BSD-3 / Apache-2.0 |
| Cluster floorplan (≤~50 blocks) | CP-SAT NoOverlap2D (optional intervals, 4 rotations, side literal, fixed keep-out boxes, region split) | MILP (HiGHS) for slicing/sequence-pair variants | Apache-2.0 |
| Global placement (100–1000 parts) | Custom JAX/PyTorch loss: WA wirelength + soft overlap or electrostatic density + SDF keep-out/outline + decap/loop/thermal/RUDY penalties; Nesterov/Adam with continuation | Cypress/DREAMPlace (GPU, Bookshelf export); ePlace as reference | Apache-2.0 / BSD-3 |
| Small or critical sub-placements (decap rings, power stages, connectors on edges, symmetric analog) | CP-SAT with hard L1 decap balls, alignment, symmetry and lexicographic symmetry breaking; hints from global placement | Z3 for small exact checks | Apache-2.0 / MIT |
| Legalization | CP-SAT with hints from global placement, solved per region/window (LNS) | Greedy Tetris/Abacus-style in Rust | Apache-2.0 |
| Detailed placement | SA/tabu in Rust with incremental HPWL, overlap and RUDY; moves: shift, swap, rotate, flip side | CP-SAT LNS windows | own code |
| Multi-objective trade-offs and weight tuning | Optuna (MOTPE/NSGA-II/AutoSampler, constraints, pruning) driven by the LLM via ask/tell | BoTorch/Ax (custom MOBO), SMAC3 (multi-fidelity), pymoo NSGA-III | MIT / MIT / BSD-3 / Apache-2.0 |
| Diverse alternatives for the LLM to choose from | pyribs CMA-MAE/MAP-Elites over placer weights with layout descriptors | pymoo Pareto fronts | MIT |
| BGA/QFN escape and fan-out | Network-flow MILP (HiGHS/SCIP) or CP-SAT on a local escape graph | SAT exact (ASP-DAC'08 style); CBS/ECBS (libMultiRobotPlanning) for ordered local multi-net | MIT / Apache-2.0 / MIT |
| Global and detailed routing | In-house 3D-lattice A* + PathFinder negotiated congestion (Rust core, bounded windows, incremental rip-up) | Freerouting headless (`--gui.enabled=false -de/-do -mp -mt`) as baseline, fallback and judge; tscircuit autorouter via Node for SimpleRouteJson; Topola (WIP) for any-angle | own / GPL-3.0 / MIT / MIT |
| Interactive-quality cleanup (push and shove) | Not scriptable via a stable API; use Freerouting's optimizer pass or own smoothing | KiCad PNS only by linking KiCad C++ (GPL, fragile) | — |
| Clearance geometry and booleans | Clipper2 (`pyclipr`, or a Rust `clipper2` crate) on integer nm | Shapely `buffer` for prototyping | Boost / BSD-3 |
| Spatial queries | Rust grid hash (hot loop); Shapely STRtree for batch predicates (`dwithin`); `rtree` when insert/delete are needed | — | BSD-3 / MIT |
| Routing channels / topological routing | PythonCDT constrained Delaunay | avoid `triangle` (non-free upstream); CGAL (GPLv3+, experimental bindings) | MPL/BSD/Apache |
| Fidelity ladder / final verification | L0 HPWL → L1 RUDY → L2 coarse PathFinder → L3 Freerouting/own router → L4 `kicad-cli pcb drc` + custom rule checks; PCBWorld-style metrics | — | — |
| Performance | PyO3/maturin Rust core; CP-SAT `num_workers`; process-parallel restarts; JAX `jit` on CPU, GPU optional | CuPy for very large lattices (OrthoRoute pattern) | MIT/Apache |

**LLM integration pattern** (inference)
- Expose each stage as a deterministic, typed tool, e.g. `cluster()`, `floorplan(constraints)`, `global_place(weights)`, `legalize()`, `route(level)`, `evaluate(level)`, `drc()`.
- The LLM translates datasheet and schematic intent into constraints: decap→pin distances, keep-outs, edge connectors, thermal pairs, diff pairs.
- The LLM picks fidelity levels and Optuna search spaces, and reviews Pareto and MAP-Elites candidates. Solvers guarantee legality.

**GPL-3.0 notes** (inference from license names; see Gaps)
- Everything in the table is permissive or GPL-compatible.
- Exclude OptiMathSAT (research-only) and Shewchuk's Triangle (commercial-distribution restriction).
- Gurobi/CPLEX only as optional, user-supplied backends behind a solver abstraction (e.g. OR-Tools MathOpt or PySCIPOpt), not bundled.

### Gaps
- No end-to-end open-source reference implementation combining CP-SAT with analytical PCB placement and a negotiated-congestion router was found. The stack above is a synthesis, not a validated pipeline.
- Concrete scale tests for this stack on 1000-part, 8-layer boards (runtime, completion rate vs Freerouting) need to be run in-project. PCBWorld's 679-board dataset and Cypress's benchmark suite are the obvious evaluation sets.
- The FSF compatibility list and the status of KiCad's SWIG Specctra helpers in 10.0.x were not verified in this session.
