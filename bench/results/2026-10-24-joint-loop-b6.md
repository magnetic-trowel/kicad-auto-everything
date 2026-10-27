# Joint place-route loop, 6 split-B boards (WIP snapshots up to d8c09e6)

Local, 2026-10-24, KiCad 10.0.7, kaebench `joint` kind, 6 split-B boards, seeds 0 and 1, 900 s,
Freerouting heap 3 GB (an attempt hit by an out-of-memory kill was re-run). Values are seed 0 / 1.

| arm | clean | unconnected | DRC errors | module value vs human | worst rail mΩ |
|---|---|---|---|---|---|
| human + Freerouting | 2 / 2 | 23 / 23 | 7 / 7 | 0.99 | 101 |
| staged (place, then route) | 3 / 4 | 3 / 3 | 0 / 0 | 1.18 / 1.39 | 108 / 87 |
| joint loop | 3 / 3 | 11 / 8 | 0 / 0 | 0.81 / 0.96 | 43 / 58 |
| joint loop, `--physics-fidelity multi` | 3 / 3 | 14 / 10 | 0 / 0 | 0.96 / 0.84 | 54 / 72 |

- The loop keeps the module physics below human (0.81–0.96) with about half the rail resistance,
  but leaves more connections open than staged, almost all on siderakb-pmw3610 (8 / 5 vs 1 / 2).
  Its finishing bridge reached 5 open on seed 0 at +120% module physics, which the accept rule
  (clean boards always kept; other completion gains may cost ≤ 10% physics per item) rejected.
- Stopping: at 9,000 s on pmw3610 the loop ran 108 windows over 3 cycles (10 → 8 unconnected,
  Σu 0.73 → 0.53) and stopped on "no improvement (cycle 2)" after 2,101 s.
- Harness issue found: a footprint rotated to 45° round-trips its text positions 1 nm off in
  `pcbnew_ops.transplant_placement`, and `_foreign` then marks the attempt invalid (both olimex
  attempts). Reported to the harness owner; the 10x joint sweep waits for the fix.
