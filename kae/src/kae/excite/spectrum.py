# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-spectrum totals of a periodic aggressor through a reduced model of the board (kae.em.reduce).

A switching source is periodic, so its current is a sum of harmonics n f_sw and every time-averaged
quantity splits exactly over them (Parseval): no band is sampled and nothing is interpolated.

    i(t) = c_0 + sum_{n>=1} 2 Re(c_n e^{j n w t})       a symmetric trapezoid of height I, 50 %-width
    c_n  = I D sinc(n D) sinc(n t_r f_sw) e^{-j pi n D}   D/f_sw, edges t_r (sinc(x) = sin(pi x)/(pi x))

Per harmonic the model gives every port's response to the source's unit current; with the peak
phasor a_n = 2 c_n:

    power      P = sum_n 1/2 |a_n|^2 Re Z_ss(n w)          delivered, = copper + parts' losses
    energy     W = sum_n 1/4 |a_n|^2 I^H L I               magnetic, time average
    observer   v_k(t) = sum_n Re(a_n H_k(n w) e^{j n w t}), H_k the layout share Z_ks - Z_ks(ideal copper)
               its peak by one inverse FFT, its RMS by Parseval, each harmonic against a limit line

The harmonics run to f_max (the model's range, at most the quasi-static limit); the source's mean
square beyond it is reported as the share left out, never extrapolated.
"""
from __future__ import annotations

import numpy as np


ETA0 = 376.730313668
R_TEST = 10.0           # m, the CISPR 32 class B measuring distance


def radiated_E(m, f, r=R_TEST):
    """Peak far field (V/m) of a magnetic dipole m (A m^2, phasor vector) at distance r, with the factor 2
    of a ground-plane reflection at the test site: 2 eta0 k^2 |m| / (4 pi r)."""
    k = 2 * np.pi * f / 299792458.0
    return 2 * ETA0 * k * k * float(np.linalg.norm(m)) / (4 * np.pi * r)


def cispr_b(f):
    """CISPR 32 class B radiated limit at 10 m (V/m, quasi-peak): 30 dBuV/m to 230 MHz, 37 above."""
    return 10 ** (np.where(np.asarray(f) <= 230e6, 30.0, 37.0) / 20) * 1e-6


def trapezoid(I, D, t_r, f_sw, n):
    """Complex Fourier coefficients c_n (two-sided) of the trapezoid pulse train, for integer n."""
    n = np.asarray(n, float)
    return I * D * np.sinc(n * D) * np.sinc(n * t_r * f_sw) * np.exp(-1j * np.pi * n * D)


def share_beyond(I, D, t_r, f_sw, n_max, n_far=None):
    """The fraction of the trapezoid's AC mean square carried by harmonics above n_max."""
    n_far = n_far or max(64 * n_max, 4096)
    n = np.arange(1, n_far + 1)
    p = 2 * np.abs(trapezoid(I, D, t_r, f_sw, n)) ** 2
    tot = p.sum()
    return float(p[n_max:].sum() / tot) if tot > 0 else 0.0


def totals(model, s, obs, I, D, t_r, f_sw, f_max, ideal=None, n_time=None):
    """Whole-spectrum totals of source port s (index into the model's ports) driven by the trapezoid
    (I, D, t_r, f_sw), harmonics up to f_max.

    obs: observer port indices; ideal(f) -> their Z with ideal copper (subtracted: the layout's share).
    Returns dict(n, f, a (peak phasors), delivered, copper, parts (per lumped part), magnetic (W, J,
    totals), per_harmonic (copper, parts, delivered arrays), V (observer spectra, (n_obs, n_h)), peak,
    rms (per observer), left_out (share of the source's AC mean square above f_max), balance (worst
    relative mismatch of delivered against copper + parts over the harmonics))."""
    n_max = int(f_max // f_sw)
    n = np.arange(1, n_max + 1)
    a = 2 * trapezoid(I, D, t_r, f_sw, n)
    nl = len(model.net.lump)
    dl, cu, pa, mg = np.zeros(n_max), np.zeros(n_max), np.zeros((nl, n_max)), np.zeros(n_max)
    V = np.zeros((len(obs), n_max), complex)
    E = np.zeros(n_max)
    for q, (nn, an) in enumerate(zip(n, a)):
        f = nn * f_sw
        pw = model.powers(f, cols=[s])
        g = abs(an) ** 2
        dl[q], cu[q], mg[q] = g * pw["delivered"][0], g * pw["copper"][0], g * pw["magnetic"][0]
        pa[:, q] = g * pw["parts"][:, 0]
        H = pw["Z"][obs, 0]
        if ideal is not None:
            H = H - ideal(f)
        V[:, q] = an * H
        E[q] = abs(an) * radiated_E(model.moment(pw["Y"])[:, 0], f)
    # the waveform over one period: v(t) = Re sum_n V_n e^{j n w t}
    N = n_time or int(2 ** np.ceil(np.log2(8 * (n_max + 1))))
    spec = np.zeros((len(obs), N // 2 + 1), complex)
    spec[:, 1:n_max + 1] = V * (N / 2)
    wave = np.fft.irfft(spec, n=N, axis=1)
    lost = share_beyond(I, D, t_r, f_sw, n_max)
    los = cu + pa.sum(0)
    bal = float(np.max(np.abs(dl - los) / np.maximum(np.abs(dl), 1e-300))) if n_max else 0.0
    return dict(n=n, f=n * f_sw, a=a, delivered=float(dl.sum()), copper=float(cu.sum()),
                parts=dict(zip(model.part_names(), pa.sum(1))), magnetic=float(mg.sum()),
                per_harmonic=dict(delivered=dl, copper=cu, parts=pa), V=V, wave=wave,
                peak=np.abs(wave).max(axis=1), rms=np.sqrt(0.5 * np.sum(np.abs(V) ** 2, axis=1)), E=E,
                left_out=lost, balance=bal)
