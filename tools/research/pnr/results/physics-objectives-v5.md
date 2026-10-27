| run | legal / clean / completion, physics boards | clean / completion, all boards | place scored | phys total x human (gmean) | worse / better | capped-u x human | worse / better | legal only: n, capped-u x human, worse | routed scored | routed x human | worse / better | open hops (method / human) | no open hop: n, routed x human, worse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 4.05 | 7 / 2 | 1.45 | 8 / 1 | 7, 1.31, 5 | 10 | 1.39 | 7 / 3 | 1.5 / 0.1 | 3, 1.45, 2 |
| pnr-seq_phys-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 1.52 | 5 / 4 | 1.20 | 5 / 4 | 7, 1.02, 2 | 10 | 1.26 | 7 / 3 | 1.1 / 0.1 | 3, 1.32, 2 |
| pnr-anneal-v5 | 9 / 4 of 10, 0.89 | 4 of 10, 0.89 | 10 | 4.28 | 7 / 2 | 1.57 | 7 / 2 | 9, 1.37, 6 | 10 | 1.54 | 6 / 4 | 1.5 / 0.1 | 5, 2.08, 4 |
| pnr-anneal_phys-v5 | 8 / 4 of 10, 0.89 | 4 of 10, 0.89 | 10 | 1.68 | 8 / 1 | 1.29 | 7 / 2 | 8, 1.11, 5 | 10 | 1.33 | 7 / 3 | 1.2 / 0.1 | 5, 1.20, 3 |
| pnr-combo_lv-v5 | 8 / 4 of 10, 0.96 | 4 of 10, 0.96 | 10 | 2.59 | 7 / 2 | 1.34 | 7 / 2 | 8, 1.49, 6 | 10 | 1.26 | 6 / 4 | 0.6 / 0.1 | 6, 1.75, 4 |
| pnr-combo-v5 | 9 / 5 of 10, 0.96 | 5 of 10, 0.96 | 10 | 1.03 | 4 / 5 | 0.97 | 4 / 5 | 9, 0.98, 4 | 10 | 1.13 | 5 / 5 | 0.5 / 0.1 | 6, 1.22, 4 |
| pnr-tension-v5 | 7 / 3 of 10, 0.88 | 3 of 10, 0.88 | 10 | 4.23 | 7 / 2 | 1.52 | 8 / 1 | 7, 1.36, 5 | 10 | 1.41 | 7 / 3 | 1.6 / 0.1 | 4, 1.27, 2 |
| pnr-bloat-v5 | 5 / 3 of 10, 0.55 | 3 of 10, 0.55 | 6 | 12.05 | 5 / 0 | 1.88 | 5 / 0 | 5, 1.51, 4 | 6 | 1.54 | 4 / 2 | 1.0 / 0.2 | 3, 1.49, 2 |
| pnr-seq_margin-v5 | 6 / 4 of 10, 0.85 | 4 of 10, 0.85 | 10 | 4.30 | 8 / 1 | 1.64 | 8 / 1 | 6, 1.56, 5 | 10 | 1.54 | 8 / 2 | 1.9 / 0.1 | 3, 2.22, 3 |
| pnr-route-v5 | 10 / 4 of 10, 0.96 | 4 of 10, 0.96 | 10 | 1.00 | 0 / 0 | 1.00 | 0 / 0 | 10, 1.00, 0 | 10 | 1.09 | 3 / 7 | 1.0 / 0.1 | 5, 0.90, 0 |

Per kind (capped u, method x human gmean; boards worse; share of the run's capped-u excess):

| run | commutation | coupling | decap | esd | thermal | world_cm |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 1.25 (2/2, 3%) | 3.50 (2/2, 25%) | 1.33 (7/10, 64%) | 0.56 (0/1, 0%) | 1.39 (2/2, 3%) | 4.48 (1/2, 5%) |
| pnr-seq_phys-v5 | 1.30 (2/2, 7%) | 1.22 (1/2, 6%) | 1.15 (5/10, 76%) | 0.38 (0/1, 0%) | 0.94 (1/2, 0%) | 4.71 (1/2, 12%) |
| pnr-anneal-v5 | 1.36 (2/2, 4%) | 3.53 (2/2, 24%) | 1.42 (6/10, 69%) | 1.10 (1/1, 1%) | 1.29 (2/2, 2%) | 2.02 (1/2, 1%) |
| pnr-anneal_phys-v5 | 1.42 (2/2, 7%) | 1.15 (1/2, 7%) | 1.23 (6/10, 71%) | 0.42 (0/1, 0%) | 1.10 (2/2, 1%) | 5.66 (1/2, 15%) |
| pnr-combo_lv-v5 | 1.12 (1/2, 2%) | 2.11 (1/2, 18%) | 1.24 (6/10, 55%) | 1.90 (1/1, 11%) | 1.07 (2/2, 0%) | 5.49 (1/2, 14%) |
| pnr-combo-v5 | 1.22 (2/2, 9%) | 1.58 (1/2, 44%) | 0.92 (4/10, 29%) | 0.44 (0/1, 0%) | 1.38 (2/2, 9%) | 7.06 (2/2, 10%) |
| pnr-tension-v5 | 1.35 (2/2, 4%) | 3.51 (2/2, 24%) | 1.39 (7/10, 69%) | 0.56 (0/1, 0%) | 1.31 (2/2, 1%) | 2.82 (1/2, 2%) |
| pnr-bloat-v5 | 1.27 (2/2, 4%) | 4.46 (2/2, 37%) | 1.54 (4/6, 50%) | 0.56 (0/1, 0%) | 1.39 (2/2, 3%) | 4.28 (1/2, 6%) |
| pnr-seq_margin-v5 | 1.16 (2/2, 2%) | 0.98 (1/2, 13%) | 1.53 (7/10, 64%) | 1.39 (1/1, 4%) | 1.99 (2/2, 8%) | 5.80 (1/2, 10%) |
| pnr-route-v5 | 1.00 (0/2, 0%) | 1.00 (0/2, 0%) | 1.00 (0/10, 0%) | 1.00 (0/1, 0%) | 1.00 (0/2, 0%) | 1.00 (0/2, 0%) |

Coverage: 10 boards; human reference: {"place ok": 10, "with physics structures": 10, "routed ok": 10}.
- pnr-seq-v5: {}
- pnr-seq_phys-v5: {}
- pnr-anneal-v5: {}
- pnr-anneal_phys-v5: {}
- pnr-combo_lv-v5: {}
- pnr-combo-v5: {}
- pnr-tension-v5: {}
- pnr-bloat-v5: {"no output board (status no_output)": 4}; pcbcorpus-badjeff-paw3395-pcb-paw3395: no output board (status no_output); pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pcb: no output board (status no_output); pcbcorpus-siderakb-pmw3360-pcb-pmw3360-pcb-jst: no output board (status no_output); pcbcorpus-siderakb-pmw3610-pcb-pmw3610-pcb: no output board (status no_output)
- pnr-seq_margin-v5: {}
- pnr-route-v5: {}
