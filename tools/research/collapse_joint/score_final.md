<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
<!-- kae-work/score_all.sh jcollapse-final ... (copied from kae-work/score/jcollapse-final.md) -->
## DRC (all 33 boards)
boards in common: 33

| run | legal | clean | completion | len (all-complete boards) | vias | mean t (s) | top DRC errors |
|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.788 | 0.545 | 0.863 | 3386 (22 boards) | 60 | 58 | {'silk_overlap': 28, 'solder_mask_bridge': 9, 'shorting_items': 6} |
| pnr-seq_phys-v5 | 0.788 | 0.545 | 0.863 | 3422 (22 boards) | 64 | 108 | {'silk_overlap': 28, 'solder_mask_bridge': 9, 'shorting_items': 6} |
| pnr-negotiate-v5 | 0.818 | 0.545 | 0.897 | 3749 (22 boards) | 58 | 118 | {'solder_mask_bridge': 7, 'starved_thermal': 6, 'shorting_items': 5} |
| pnr-combo-v5 | 0.848 | 0.636 | 0.897 | 2943 (22 boards) | 25 | 116 | {'items_not_allowed': 10, 'copper_edge_clearance': 4, 'clearance': 3} |
| pnr-combo_lv-v5 | 0.818 | 0.545 | 0.900 | 2948 (22 boards) | 28 | 436 | {'starved_thermal': 6, 'solder_mask_bridge': 4, 'items_not_allowed': 4} |
| jcollapse-jc-ab33-v3 | 0.879 | 0.667 | 0.897 | 2977 (22 boards) | 42 | 410 | {'solder_mask_bridge': 12, 'shorting_items': 5, 'silk_overlap': 2} |
| jcollapse-jc_nopol-ab33-v3 | 0.879 | 0.606 | 0.893 | 2928 (22 boards) | 48 | 204 | {'solder_mask_bridge': 9, 'shorting_items': 5, 'silk_overlap': 4} |
| jcollapse-jc_lv_nopol-ab33-v3 | 0.879 | 0.667 | 0.897 | 3045 (22 boards) | 48 | 208 | {'solder_mask_bridge': 12, 'shorting_items': 6, 'items_not_allowed': 6} |
| jcollapse-jc_frozen-ab33-v3 | 0.879 | 0.485 | 0.892 | 4684 (22 boards) | 117 | 369 | {'items_not_allowed': 17, 'solder_mask_bridge': 14, 'starved_thermal': 8} |

## Physics (boards with physics structures; fast = place terms, routed = full recheck on copper)
| run | legal / clean / completion, physics boards | clean / completion, all boards | place scored | phys total x human (gmean) | worse / better | capped-u x human | worse / better | legal only: n, capped-u x human, worse | routed scored | routed x human | worse / better | open hops (method / human) | no open hop: n, routed x human, worse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 4.05 | 7 / 2 | 1.45 | 8 / 1 | 7, 1.31, 5 | 10 | 1.39 | 7 / 3 | 1.5 / 0.1 | 3, 1.45, 2 |
| pnr-seq_phys-v5 | 7 / 3 of 10, 0.86 | 3 of 10, 0.86 | 10 | 1.52 | 5 / 4 | 1.20 | 5 / 4 | 7, 1.02, 2 | 10 | 1.26 | 7 / 3 | 1.1 / 0.1 | 3, 1.32, 2 |
| pnr-negotiate-v5 | 7 / 3 of 10, 0.94 | 3 of 10, 0.94 | 10 | 1.89 | 7 / 2 | 1.30 | 7 / 2 | 7, 1.36, 5 | 10 | 1.40 | 7 / 3 | 1.0 / 0.1 | 5, 1.51, 3 |
| pnr-combo-v5 | 9 / 5 of 10, 0.96 | 5 of 10, 0.96 | 10 | 1.03 | 4 / 5 | 0.97 | 4 / 5 | 9, 0.98, 4 | 10 | 1.13 | 5 / 5 | 0.5 / 0.1 | 6, 1.22, 4 |
| pnr-combo_lv-v5 | 8 / 4 of 10, 0.96 | 4 of 10, 0.96 | 10 | 2.59 | 7 / 2 | 1.34 | 7 / 2 | 8, 1.49, 6 | 10 | 1.26 | 6 / 4 | 0.6 / 0.1 | 6, 1.75, 4 |
| jcollapse-jc-ab33-v3 | 9 / 6 of 10, 0.95 | 6 of 10, 0.95 | 10 | 0.82 | 4 / 5 | 0.90 | 4 / 5 | 9, 0.89, 4 | 10 | 1.05 | 5 / 5 | 1.3 / 0.1 | 4, 1.27, 3 |
| jcollapse-jc_nopol-ab33-v3 | 9 / 4 of 10, 0.95 | 4 of 10, 0.95 | 10 | 0.86 | 3 / 6 | 0.92 | 3 / 6 | 9, 0.92, 3 | 10 | 1.00 | 4 / 6 | 1.0 / 0.1 | 4, 1.23, 2 |
| jcollapse-jc_lv_nopol-ab33-v3 | 9 / 4 of 10, 0.96 | 4 of 10, 0.96 | 10 | 2.05 | 8 / 1 | 1.31 | 8 / 1 | 9, 1.31, 7 | 10 | 1.29 | 8 / 2 | 1.3 / 0.1 | 6, 1.47, 5 |
| jcollapse-jc_frozen-ab33-v3 | 10 / 4 of 10, 0.95 | 4 of 10, 0.95 | 10 | 1.08 | 5 / 4 | 1.00 | 5 / 4 | 10, 1.00, 5 | 10 | 1.04 | 5 / 5 | 0.3 / 0.1 | 7, 1.11, 4 |

