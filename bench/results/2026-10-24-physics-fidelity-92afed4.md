# Physics fidelity A/B on splits A+B at 92afed4

Run on sk-tibia, 2026-10-24, KiCad 10.0.7. The critical-net router (`kae.route.critical_cli`) with
`--physics-fidelity fast` against `multi --physics-k 4` (fast ranks candidates, PEEC re-scores the
best four), route tasks of splits A+B, 33 boards, k = 2, 1800 s, scored by kaebench.

| arm | cp1 | cpk | completion | errors / board | clean attempts |
|---|---|---|---|---|---|
| fast | 0.667 | 0.697 | 0.968 | 0.03 | 44/66 |
| multi | 0.667 | 0.697 | 0.965 | 0.03 | 44/66 |

- `multi` re-scored 50 module-stage decisions by PEEC (226 exact calls, 1.1 s of PEEC in total) and
  confirmed the fast choice every time: 0 decisions changed. The same 12 boards are unclean in
  both arms.
- Routed physics against the human boards (`crit_compare`, median ratio, better/worse): decap
  0.957 (14/8) fast vs 0.961 (13/8) multi; cells 0.874 both; rail resistance 0.964 both. The
  decap difference is routing variance between runs.
- On these boards the fast estimates are accurate enough to choose by; exact physics is worth
  using where the reported number matters (finished-board physics), at negligible cost. Split C
  boards, with larger cells, are where `multi` could still change decisions.
