# Layer assignment and via minimization

**TL;DR**
- Unconstrained topological via minimization is **NP-complete** (Marek-Sadowska 1984); constrained via minimization on two-layer PCBs has polynomial optimal cases (Chen–Kajitani–Chan 1983).
- Modern practice treats via count as a **cost term with a user knob** (Situs Via Miser / More-Less Vias slider; Freerouting via_costs 50; SURF K_v).
- The largest reported via reductions come from **topology-first** and **SAT** approaches (MonoSAT 4 → 3 layers; TopoR vendor 15–45% fewer vias; pin equivalence 67 → 17 vias).
- **Negotiation-based layer assignment** removes most order dependence.
- Humans use *more* vias than Freerouting on PCBWorld (D3-A 1.18 vs 0.74 at Freerouting routability 0.91; D3-B 6.70 vs 3.48 at 1.00) — via count alone is not quality.

## Key facts

| Work | Contribution |
|---|---|
| Hsu, TCAD'83 "Minimum-Via Topological Routing" | Circle graph selects a maximal via-free net set; layer assignment as **max-cut**, solved greedily; then geometric mapping (IC, 2-layer) [P-abs] |
| Chen, Kajitani, Chan, TCAS'83 | Polynomial via minimization "for certain types of two-layer PCBs"; junction degrees 2–8; minimum guaranteed for ≤3 segments per junction; supports pre-assigned segments [P-abs] |
| Marek-Sadowska, TCAD'84 | "The simplest problem of this type is NP-complete"; heuristic [P-abs] |
| Shi, GLSVLSI'92 | Signed-hypergraph model of general CVM; linear-time two-layer heuristic [P-abs] |
| Chang & Cong, DAC'97 | Multilayer layer assignment for via minimization (IC) [title] |
| **Liu & Li, ASP-DAC'11 (NVM)** | Negotiation-based layer assignment: ordering "only slightly influences the quality"; additional via cost −10.8% / −2.5% vs two prior methods; via overflow −11.5% with two stages (VLSI) [P-abs] |
| Dayan & Dai (SURF) | Steepest descent on K_v·ViaCost + WiringCost; user K_v trades vias vs length (MCM) [P] |
| Ozdal–Wong; Yan–Kong–Wong; Ma–Young–Wong; Bayless | Escape-specific layer minimization ([escape](escape-routing.md)) |
| Altium Situs | More/Less Vias slider; "Via Miser" default strategy; Completion pass makes vias cheaper; blind/buried per Layer Stack Manager [P-doc] |
| Freerouting | via_costs 50, plane_via_costs 5 defaults ([freerouting](freerouting.md)) |
| gEDA autoroute | ViaCost 3.5 in + 30× via diameter; NewLayerPenalty 10× ViaCost ([algorithm families](algorithm-families.md)) |
| ML for package substrates | Learned net ordering for layer assignment beats heuristic scores ([arXiv 2412.21035](https://arxiv.org/abs/2412.21035) [P-abs]) |

**Cost and SI context** (Luzin & Polubasov, vendor): via inductance ~1.1 nH (0.4 × 1.5 mm); ~$1 per extra 300 vias/dm² above 250; ~1000 hits per drill; 2.5–3 min extra drilling per 1000 holes per stack [P/V]. Practitioners: early autorouters "added too many vias" (Olney); poor grouping "will definitely lead to more vias than needed" (SparkFun) ([skepticism](autorouter-skepticism.md)).

**Evidence of via outcomes**: PCBWorld D3-A vias per board — reference 1.18, Freerouting 0.74 (routability 0.91, so some connections are missing), KRT 3.69, PPO 0.92, GRPO 9.39 ([PCBWorld](pcbworld.md)); DeepPCB vendor 0.50–0.59× reference [V]; ModuPlace placement cut vias 40.51% vs SA-PCB ([LLM-guided placement](../placement/llm-guided-placement.md)); DATE'23 MCTS router had worse via counts than FreeRouting/DeepPCB.

## Recommendations for our system
- Expose via cost, layer directions and a via-vs-length knob (K_v) per net class; LLM sets via technology and layer budget from stackup/fab constraints [I].
- Use negotiation-based layer assignment in the in-house router; topology-first planning for critical groups ([topological](topological-routing.md)) [I].
- Report via density per dm² (Luzin thresholds), vias per net and reference-plane changes without stitching vias, not just total vias ([skepticism](autorouter-skepticism.md)) [I].
- Relation API: `via_limit(net, n)`, `layer_pref(net, layer)` ([LLM routing evidence](llm-routing-evidence.md)) [I].

## Conflicts and open questions
- No modern PCB comparison of layer-assignment methods; most results are IC/MCM.

## Sources
- research notes: [routing_classics_supplement.md § Q6, Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [verification_papers.md § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [escape-routing](escape-routing.md) · [topological-routing](topological-routing.md) · [net-ordering](net-ordering.md)
