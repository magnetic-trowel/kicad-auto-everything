# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Event simulation of the heartbeat watchdog (U1 74LVC1G123 -> Q7) and one relay (review N1).

Model (DESIGN.md C-4):
  - U1 is retriggered by every rising edge on B (A = GND, CLR = VCC; SCES586E Table 4-1); Q stays high
    until tw after the last rising edge. Q7 follows Q within ns.
  - Relay (G5RL, CH held high): the contact closes after `t_op` of continuous coil current and opens once
    the coil has been off for longer than `t_rel` (coil re-energized sooner: contact stays closed).
  - `t_rel_fast` (2 ms, [I]) is used when asking "does a gap drop the load" (pessimistic for nuisance trips);
    `t_rel_slow` (15 ms with the flyback diode, [I]) when asking "how late can it turn off" (pessimistic for
    safety). t_op 15 ms is the G5RL maximum operate time [P].
Run `python wdsim.py` for the table quoted in DESIGN.md; design.py imports the same functions for its calcs.
"""

T_OP = 0.015
T_REL_FAST = 0.002
T_REL_SLOW = 0.015


def tw_bounds(r_ohm, c_farad):
    """tw range: K 1.0-1.1 (SCES586E 5.8/5.9), R +/-1 %, C +/-10 %, X7R +/-15 % over temperature, and +/-10 %
    for the +/-0.25 uA Rext/Cext leakage at 1 Mohm (0.25 V of 3.3 V, [I])."""
    base = r_ohm * c_farad
    return 1.0 * base * 0.99 * 0.90 * 0.85 * 0.90, 1.1 * base * 1.01 * 1.10 * 1.15 * 1.10


def simulate(edges, tw, t_end, t_rel, dt=0.0005):
    """Return (q_intervals, contact_events). edges: rising-edge times of HB."""
    edges = sorted(edges)
    t, i, q_until = 0.0, 0, -1.0
    coil_on_since, coil_off_since, closed = None, 0.0, False
    events = []
    while t <= t_end:
        while i < len(edges) and edges[i] <= t:
            q_until = edges[i] + tw
            i += 1
        coil = t < q_until
        if coil:
            coil_off_since = None
            if coil_on_since is None:
                coil_on_since = t
            if not closed and t - coil_on_since >= T_OP:
                closed = True
                events.append(("close", round(t, 4)))
        else:
            coil_on_since = None
            if coil_off_since is None:
                coil_off_since = t
            if closed and t - coil_off_since > t_rel:
                closed = False
                events.append(("open", round(t, 4)))
        t += dt
    return events


def disarm_after_stop(tw, period=0.01):
    """HB stops (either level) at t = 0.5 s: last rising edge <= 0.5 s. Returns time from the stop to open."""
    edges = [k * period for k in range(int(0.5 / period) + 1)]
    ev = simulate(edges, tw, 2.0, T_REL_SLOW)
    opens = [t for kind, t in ev if kind == "open"]
    return opens[-1] - edges[-1] if opens else None


def max_gap_ridden(tw, period=0.01):
    """Largest single gap between rising edges (1 ms steps) that does not open the contact."""
    best = 0.0
    for gap_ms in range(10, 1000):
        gap = gap_ms / 1000
        edges = [k * period for k in range(50)]
        last = edges[-1]
        edges += [last + gap + k * period for k in range(50)]
        ev = simulate(edges, tw, last + gap + 0.6, T_REL_FAST)
        if any(kind == "open" for kind, t in ev if t > last):
            break
        best = gap
    return best


def chatter_band(tw_min, tw_max):
    """HB frequencies that may arm and drop each period on some part: between 1/tw_max and 1/tw_min."""
    return 1 / tw_max, 1 / tw_min


if __name__ == "__main__":
    lo, hi = tw_bounds(1e6, 220e-9)
    print(f"tw {lo * 1e3:.0f}-{hi * 1e3:.0f} ms")
    for name, tw in (("tw_min", lo), ("tw_max", hi)):
        print(f"{name}: disarm after HB stops (high or low) {disarm_after_stop(tw) * 1e3:.0f} ms; "
              f"largest gap ridden through {max_gap_ridden(tw) * 1e3:.0f} ms")
    for f in (2, 4, 6, 10, 20):
        edges = [k / f for k in range(int(3 * f) + 1)]
        ev = simulate(edges, lo, 3.0, T_REL_FAST)
        print(f"HB {f} Hz on the tw_min part: {sum(1 for k, _ in ev if k == 'open')} openings in 3 s")
    a, b = chatter_band(lo, hi)
    print(f"chatter band {a:.1f}-{b:.1f} Hz")
