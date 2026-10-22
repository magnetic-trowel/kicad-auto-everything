# Baseline: qualified suite, KiCad 10.0.7, sk-tibia, 2026-10-22

Summarized results only; boards and run directories stay on the host (third-party licences).

## Provenance

| Item | Value |
|---|---|
| Harness | branch `claude/vigilant-mayer-i91rrr` at 4e0ab77 (harness-integrity merged at 00a386d; later commits touch only `tools/research/physics`) |
| Scoring | SCORE_VERSION 5, TASK_SPEC 4 |
| Tools | KiCad 10.0.7 (Apptainer image), Freerouting 2.5.0 |
| Suite | `bench/suites/qualified-kicad-10.0.7.txt`, manifest `bench/manifests/candidates.jsonl`; 112 qualified (A 13, B 20, C 79), 0 prepare failures |
| Host | sk-tibia, `-j 32`, one cgroup scope (AllowedCPUs 0–49, MemoryMax 96 G), KiCad under `ulimit -v 40000000`; host load 65–98 from other jobs, so wall times are inflated |
| Runs | `human`: reference, kinds route + place, probe Freerouting, k = 3, 900 s. `noop`: route, k = 1. `fr-k3`: Freerouting, route, k = 3, 900 s, `--keep-work` |
| Caveat | `~/.config/freerouting/freerouting.json` was last written by Freerouting 2.5.1; 2.5.0 warns it may ignore some settings |

## Route

| Run | Split | n | cp1 | cpk | completion | errors/board | partial | wl_ratio |
|---|---|---|---|---|---|---|---|---|
| human | all | 112 | 1.000 | 1.000 | 1.000 | 0 | 0 | 1.000 |
| noop | all | 112 | 0 | 0 | 0 | 0.46 | 0 | — |
| fr-k3 | A | 13 | 0.615 | 0.615 | 0.913 | 1.69 | 0 | 0.929 |
| fr-k3 | B | 20 | 0.350 | 0.350 | 0.886 | 3.20 | 0 | 0.852 |
| fr-k3 | C | 79 | 0.051 | 0.051 | 0.746 | 31.4 | 66 | 0.788 |
| fr-k3 | all | 112 | 0.170 | 0.170 | 0.790 | 22.9 | 66 | 0.831 |

- cp1 = cpk on every split: only 24 of 112 boards gave different results across the three attempts (the attempts differ only in pass count).
- Freerouting finished 270 attempts and timed out on 66, all in split C (internal deadline 776 s); timed-out attempts are scored on their partial routing.
- Invalid and suspect: 0 in every run. Infrastructure failures: 0 of 1,120 attempts.

## Place (human placement, Freerouting probe)

| Split | legal | hpwl_ratio | probe cp | probe completion |
|---|---|---|---|---|
| A | 1.0 | 1.0 | 0.615 | 0.913 |
| B | 1.0 | 1.0 | 0.350 | 0.886 |
| C | 1.0 | 1.0 | 0.051 | 0.743 |
| all | 1.0 | 1.0 | 0.170 | 0.788 |

This is the bar for the one-month placer on the joint task ([month-plan](../../docs/topics/architecture/month-plan.md)): routed clean rate at least 0.615 on split A and 0.350 on split B.

## Freerouting errors by type (fr-k3, 336 attempts; count, boards)

| Split | Top types |
|---|---|
| A | track_width 33 (2); copper_edge_clearance 21 (1); shorting_items 6 (1); clearance 6 (1) |
| B | track_width 99 (4); clearance 57 (1); copper_edge_clearance 21 (4); starved_thermal 15 (2) |
| C | track_width 5,679 (39); clearance 726 (13); starved_thermal 271 (19); solder_mask_bridge 245 (7); copper_edge_clearance 174 (7); shorting_items 114 (10); hole_clearance 114 (3); hole_to_hole 98 (2); via_diameter 42 (1) |

Track width is about 70% of all errors, including 199 on one board whose DSN widths needed no clamping, so the cause is a rule that the DSN does not carry, not the board minimum.

## Resources per attempt (fr-k3)

| Measure | median | p90 | max |
|---|---|---|---|
| Method CPU (s) | 133 | 914 | 2,590 |
| Method peak RSS (MB) | 1,184 | 3,628 | 13,046 |
| Wall (s) | 45 | 806 | 870 |
| Scoring CPU (s) | 6.0 | 18.6 | 119 |
| Scoring RSS (MB) | 256 | 400 | 1,082 |

## Worst boards by completion (fr-k3, best of 3)

| Board | Split | Completion | Unconnected now/start | Errors |
|---|---|---|---|---|
| berkeleylab-obsidian-obsidian | C | 0.00 | 499/499 | 239 |
| kicad-demos-video-video | C | 0.00 | 499/499 | 199 |
| azonenberg-latentred-linecard | C | 0.00 | 499/499 | 2 |
| chipsalliance-rocket-pcb-fmc-usb-gpio-spi-jtag | C | 0.006 | 322/324 | 2 |
| pcbcorpus-justbuchanan-oasis-ledboard | A | 0.18 | 9/11 | 0 (Freerouting reported completion) |
| pcbcorpus-sufst-pcb-16ch-sensor-hub | C | 0.23 | 223/289 | 80 |

## Known limits of these numbers

- **The unconnected count saturates at 499** on several large boards, consistent with a KiCad DRC report cap ([dev-eval-plan](../../docs/topics/verification/dev-eval-plan.md) H5), so completion on large split-C boards is not exact.
- **TASK_SPEC 4 place tasks** stage unlocked footprints that carry Edge.Cuts (11 of 112 boards); TASK_SPEC 5 anchors them. The human place probe is unaffected because scoring rebuilds those footprints at the human pose; any other place method needs spec-5 tasks.
