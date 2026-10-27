# Place and route pipeline on splits A+B at c9c49d6

Run on the shared benchmark host, 2026-10-24, KiCad 10.0.7. `kae place` (physics on, silk where the project makes it
an error, numbered-row labels, closed-loop legality with KiCad DRC) followed by kae's bridge with
last mile (now the default) as the kaebench probe, against the human placement routed by the same
probe. 33 boards, k = 2, 1800 s, Freerouting fork heap 2 GB, place tasks at task spec 6.

| placement → router | legal | probe cp1 | probe cpk | completion | probe DRC errors |
|---|---|---|---|---|---|
| kae place → kae bridge | 65/66 | **0.909** | **0.939** | 0.997 | copper_edge_clearance 1 (paw3222 #0) |
| human → kae bridge | 66/66 | 0.909 | 0.939 | 0.998 | none |

By split: A 1.0 for both, B 0.90 for both. HPWL relative to human 0.713. No silkscreen error on any
attempt (49 on ecc83 in the probe run three hours earlier).

- Ours worse: paw3395 (2 and 1 unconnected vs clean), badjeff-pmw3610 (3, 2 vs 1, 1), paw3222
  attempt 0 (illegal placement, 7 unconnected).
- Ours better: dumptruck emmc-interposer (clean, clean vs clean, 3), olimex dcdc-50-5-12 (clean,
  clean vs 1, 1), siderakb-pmw3610 (clean, clean vs 3, clean: the board no router arm had closed on
  the human placement).

For comparison, Freerouting 2.5.0 on the human placement scored cp1 0.615 on split A and 0.35 on
split B at k = 10 ([baseline](2026-10-22-qualified-k10-baseline.md)), about 0.46 on A+B; the
month plan's routing target on A+B was "at least human placement + Freerouting".
