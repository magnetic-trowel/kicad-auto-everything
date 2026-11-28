<!-- SPDX-FileCopyrightText: 2026 HaslamPCB contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# width_human on stored runs (subset `power`)

Boards with >= 1 power net with human track: 290. Errors: {('bridge', 'no output'): 292, ('staged', 'no output'): 80}.

## 1. Corpus mean, paired against the human floor (option set d, mean of seeds 0 and 1 per board)

| method | definition | boards | mean | median | human floor | method - floor [95 % CI] |
|---|---|---|---|---|---|---|
| bridge | share | 145 | 0.477 | 0.542 | 0.098 | 0.379 [0.333, 0.422] |
| bridge | share_x | 145 | 0.442 | 0.487 | 0.056 | 0.386 [0.339, 0.434] |
| bridge | deficit | 145 | 0.249 | 0.248 | 0.044 | 0.204 [0.178, 0.230] |
| bridge | share_i | 123 | 0.415 | 0.364 | 0.042 | 0.372 [0.307, 0.438] |
| bridge | share_neck | 145 | 0.092 | 0.000 | 0.017 | 0.076 [0.052, 0.100] |
| staged | share | 249 | 0.672 | 0.828 | 0.102 | 0.570 [0.530, 0.610] |
| staged | share_x | 248 | 0.637 | 0.760 | 0.063 | 0.574 [0.533, 0.616] |
| staged | deficit | 249 | 0.379 | 0.399 | 0.047 | 0.331 [0.303, 0.360] |
| staged | share_i | 206 | 0.690 | 0.963 | 0.041 | 0.649 [0.592, 0.702] |
| staged | share_neck | 248 | 0.130 | 0.006 | 0.016 | 0.114 [0.091, 0.137] |

## 2. Stability: seed 0 vs seed 1 (Spearman across boards) and option-set sensitivity

| method | definition | boards (both seeds) | Spearman s0-s1 | mean abs s0-s1 | mean d | tol15 - d | reach05 - d | nopour - d |
|---|---|---|---|---|---|---|---|---|
| bridge | share | 145 | 0.96 | 0.045 | 0.477 | -0.002 | 0.000 | 0.000 |
| bridge | share_x | 145 | 0.93 | 0.065 | 0.442 | -0.002 | 0.001 | 0.034 |
| bridge | deficit | 145 | 0.97 | 0.023 | 0.249 | 0.000 | 0.000 | 0.000 |
| bridge | share_i | 125 | 0.92 | 0.067 | 0.418 | -0.001 | 0.015 | 0.010 |
| bridge | share_neck | 145 | 0.92 | 0.037 | 0.092 | -0.000 | -0.002 | 0.014 |
| staged | share | 249 | 0.98 | 0.051 | 0.672 | -0.001 | 0.000 | 0.000 |
| staged | share_x | 248 | 0.92 | 0.077 | 0.637 | -0.001 | -0.006 | 0.045 |
| staged | deficit | 249 | 0.98 | 0.033 | 0.379 | 0.000 | 0.000 | 0.000 |
| staged | share_i | 209 | 0.87 | 0.084 | 0.692 | -0.000 | -0.003 | 0.018 |
| staged | share_neck | 248 | 0.82 | 0.073 | 0.130 | -0.001 | -0.003 | 0.019 |

## 3. Subsets (bridge, option set d, share_x, mean of seeds)

| subset | boards | bridge | human floor | staged |
|---|---|---|---|---|
| power | 145 | 0.442 | 0.056 | 0.637 |
| power_no_gnd | 144 | 0.473 | 0.058 | 0.673 |
| by_role | 145 | 0.400 | 0.059 | 0.624 |
| by_width | 122 | 0.582 | 0.075 | 0.790 |
| all | 145 | 0.439 | 0.055 | 0.635 |

## 4. By suite (option set d, mean of seeds; bridge - floor with 95 % CI)

| suite | definition | boards | bridge | floor | bridge - floor [CI] | staged |
|---|---|---|---|---|---|---|
| sprint-frontier | share_x | 60 | 0.478 | 0.053 | 0.425 [0.350, 0.496] | 0.630 |
| sprint-frontier | share_neck | 60 | 0.113 | 0.018 | 0.095 [0.054, 0.138] | 0.175 |
| sprint-frontier | deficit | 60 | 0.250 | 0.044 | 0.206 [0.171, 0.242] | 0.350 |
| sprint-frontier | share_i | 50 | 0.494 | 0.051 | 0.443 [0.331, 0.551] | 0.718 |
| sprint-quality | share_x | 78 | 0.423 | 0.059 | 0.364 [0.299, 0.429] | 0.616 |
| sprint-quality | share_neck | 78 | 0.078 | 0.017 | 0.061 [0.034, 0.092] | 0.151 |
| sprint-quality | deficit | 78 | 0.250 | 0.045 | 0.206 [0.168, 0.244] | 0.362 |
| sprint-quality | share_i | 66 | 0.358 | 0.037 | 0.321 [0.236, 0.406] | 0.658 |
| power-distribution | share_x | 21 | 0.435 | 0.081 | 0.353 [0.248, 0.457] | 0.641 |
| power-distribution | share_neck | 21 | 0.085 | 0.029 | 0.057 [-0.002, 0.128] | 0.079 |
| power-distribution | deficit | 21 | 0.283 | 0.052 | 0.231 [0.169, 0.292] | 0.427 |
| power-distribution | share_i | 19 | 0.456 | 0.063 | 0.393 [0.245, 0.547] | 0.680 |
| buck | share_x | 30 | 0.495 | 0.080 | 0.415 [0.334, 0.497] | 0.700 |
| buck | share_neck | 30 | 0.107 | 0.022 | 0.085 [0.036, 0.140] | 0.159 |
| buck | deficit | 30 | 0.296 | 0.055 | 0.241 [0.197, 0.284] | 0.423 |
| buck | share_i | 25 | 0.449 | 0.041 | 0.408 [0.260, 0.553] | 0.764 |
| boost | share_x | 10 | 0.322 | 0.046 | 0.277 [0.153, 0.404] | 0.702 |
| boost | share_neck | 10 | 0.104 | 0.015 | 0.089 [0.011, 0.180] | 0.118 |
| boost | deficit | 10 | 0.153 | 0.024 | 0.130 [0.072, 0.191] | 0.390 |
| boost | share_i | 9 | 0.290 | 0.058 | 0.232 [0.063, 0.410] | 0.741 |
| battery-charging | share_x | 7 | 0.326 | 0.040 | 0.286 [0.140, 0.441] | 0.612 |
| battery-charging | share_neck | 7 | 0.147 | 0.026 | 0.121 [0.024, 0.230] | 0.117 |
| battery-charging | deficit | 7 | 0.168 | 0.036 | 0.131 [0.066, 0.213] | 0.362 |
| battery-charging | share_i | 6 | 0.137 | 0.021 | 0.116 [0.031, 0.225] | 0.635 |
