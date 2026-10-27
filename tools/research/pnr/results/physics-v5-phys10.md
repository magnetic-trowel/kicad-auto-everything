| run | legal / clean / completion, physics boards | clean / completion, all boards | place scored | phys total x human (gmean) | worse / better | capped-u x human | worse / better | legal only: n, capped-u x human, worse | routed scored | routed x human | worse / better | open hops (method / human) | no open hop: n, routed x human, worse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 4.05 | 7 / 2 | 1.45 | 8 / 1 | 7, 1.31, 5 | 10 | 1.39 | 7 / 3 | 1.5 / 0.1 | 3, 1.45, 2 |
| pnr-seq_phys-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 1.52 | 5 / 4 | 1.20 | 5 / 4 | 7, 1.02, 2 | 10 | 1.26 | 7 / 3 | 1.1 / 0.1 | 3, 1.32, 2 |
| pnr-anneal_phys-v5 | 8 / 4 of 10, 0.89 | 4 of 10, 0.89 | 10 | 1.68 | 8 / 1 | 1.29 | 7 / 2 | 8, 1.11, 5 | 10 | 1.33 | 7 / 3 | 1.2 / 0.1 | 5, 1.20, 3 |
| mcts-beam-ab33-p2-v5 | 8 / 4 of 10, 0.94 | 4 of 10, 0.94 | 10 | 0.98 | 4 / 5 | 1.01 | 5 / 4 | 8, 1.06, 4 | 10 | 1.14 | 5 / 5 | 0.8 / 0.1 | 6, 1.25, 3 |
| pnr-combo-v5 | 9 / 5 of 10, 0.96 | 5 of 10, 0.96 | 10 | 1.03 | 4 / 5 | 0.97 | 4 / 5 | 9, 0.98, 4 | 10 | 1.13 | 5 / 5 | 0.5 / 0.1 | 6, 1.22, 4 |
| pnr-route-v5 | 10 / 4 of 10, 0.96 | 4 of 10, 0.96 | 10 | 1.00 | 0 / 0 | 1.00 | 0 / 0 | 10, 1.00, 0 | 10 | 1.09 | 3 / 7 | 1.0 / 0.1 | 5, 0.90, 0 |

Per kind (capped u, method x human gmean; boards worse; share of the run's capped-u excess):

| run | commutation | coupling | decap | esd | thermal | world_cm |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 1.25 (2/2, 3%) | 3.50 (2/2, 25%) | 1.33 (7/10, 64%) | 0.56 (0/1, 0%) | 1.39 (2/2, 3%) | 4.48 (1/2, 5%) |
| pnr-seq_phys-v5 | 1.30 (2/2, 7%) | 1.22 (1/2, 6%) | 1.15 (5/10, 76%) | 0.38 (0/1, 0%) | 0.94 (1/2, 0%) | 4.71 (1/2, 12%) |
| pnr-anneal_phys-v5 | 1.42 (2/2, 7%) | 1.15 (1/2, 7%) | 1.23 (6/10, 71%) | 0.42 (0/1, 0%) | 1.10 (2/2, 1%) | 5.66 (1/2, 15%) |
| mcts-beam-ab33-p2-v5 | 0.98 (1/2, 2%) | 1.36 (1/2, 14%) | 0.97 (4/10, 54%) | 0.71 (0/1, 0%) | 1.78 (2/2, 25%) | 6.87 (2/2, 5%) |
| pnr-combo-v5 | 1.22 (2/2, 9%) | 1.58 (1/2, 44%) | 0.92 (4/10, 29%) | 0.44 (0/1, 0%) | 1.38 (2/2, 9%) | 7.06 (2/2, 10%) |
| pnr-route-v5 | 1.00 (0/2, 0%) | 1.00 (0/2, 0%) | 1.00 (0/10, 0%) | 1.00 (0/1, 0%) | 1.00 (0/2, 0%) | 1.00 (0/2, 0%) |

Coverage: 10 boards; human reference: {"place ok": 10, "with physics structures": 10, "routed ok": 10}.
- pnr-seq-v5: {}
- pnr-seq_phys-v5: {}
- pnr-anneal_phys-v5: {}
- mcts-beam-ab33-p2-v5: {}
- pnr-combo-v5: {}
- pnr-route-v5: {}
