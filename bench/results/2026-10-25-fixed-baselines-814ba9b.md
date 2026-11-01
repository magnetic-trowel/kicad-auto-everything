# Baselines for the fixed-interface tasks, classifier rules 4 (harness 814ba9b)

Run by the harness session, 2026-10-25: 112 qualified boards, KiCad 10.0.7, task spec 8, k = 1,
900 s timeout, all arms at one harness commit (run names `*-v4`). No invalid or suspect results.

Fixed under rules 4: 637 connectors (102 boards), 342 mounting parts (72), 407 user-facing parts
(61). Movable footprints per board: median 49.5 on `place`, 42 on `place-fixed`; 13 boards have
≤ 5 movable and 3 have none (held out by `--min-movable 1`).

| arm | kind | legal | probe / route cp1 | completion | errors / board |
|---|---|---|---|---|---|
| noop | place | 0.009 | – | – | – |
| noop | place-fixed | 0.027 (the 3 boards with 0 movable) | – | – | – |
| human placement + Freerouting probe | place | 1.0 | 0.17 (A 0.615, B 0.35, C 0.051) | 0.809 | – |
| human placement + Freerouting probe | place-fixed | 1.0 | 0.17 (same per split) | 0.809 | – |
| reference (human board as routed) | joint-fixed | 1.0 | 1.0 (cpk 1.0) | 1.0 | 0 |
| human placement + Freerouting | joint-fixed | 1.0 | 0.17 (cpk 0.17) | 0.809 | 23.1 |

Reading: the human placement's probe score is the same on both place kinds, so the fixed kind
changes only what the placer may move. Our headline runs (`fixed-place-d0bdb9d`,
`joint-*-fixed-d0bdb9d`, queued on the shared benchmark host) compare against these rows; stock Freerouting on the
human placement (0.17) is the routing baseline, the human-routed board (1.0) the ceiling.
