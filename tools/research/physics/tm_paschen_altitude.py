# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paschen's law, altitude and PCB clearance.

  1  ISA standard-atmosphere pressure vs altitude, and the ratio
     p(2000 m)/p(h). Compared with the IEC 60664-1 clearance altitude
     multiplication factors (values as commonly reproduced; 5000 m = 1.48 is
     confirmed in TI SLUP419). If the factors equal the pressure ratio, the
     altitude correction is pure Paschen similarity (V_b = f(p*d)) on the
     right-hand branch, not a safety margin.
  2  Townsend/Paschen uniform-field breakdown for air
     V_b = B*p*d / (ln(A*p*d) - ln(ln(1 + 1/gamma))), A = 15 /(cm Torr),
     B = 365 V/(cm Torr), gamma = 0.01, and the Paschen minimum. Below the
     minimum no gas discharge can occur at any pressure or gap.
  3  Breakdown of 0.2-5 mm gaps from sea level to 35 km (where p*d approaches
     the minimum and bigger gaps stop helping).
  4  Implied field-utilisation factor of the IEC case-A (inhomogeneous)
     clearance values: uniform-field V_b at that gap / rated impulse.

Run (numpy):

    python tools/research/physics/tm_paschen_altitude.py
"""
import math

A_T = 15.0      # 1/(cm Torr)
B_T = 365.0     # V/(cm Torr)
GAMMA = 0.01
TORR_PER_PA = 1 / 133.322


def isa_pressure(h):
    """ISA pressure (Pa) for 0-32 km geopotential altitude h (m)."""
    if h <= 11000:
        T = 288.15 - 0.0065 * h
        return 101325 * (T / 288.15) ** 5.25588
    p11 = 22632.06
    if h <= 20000:
        return p11 * math.exp(-9.80665 * 0.0289644 * (h - 11000) / (8.31446 * 216.65))
    p20 = 5474.89
    T = 216.65 + 0.001 * (h - 20000)
    return p20 * (T / 216.65) ** (-9.80665 * 0.0289644 / (8.31446 * 0.001))


def paschen(p_pa, d_m):
    pd = p_pa * TORR_PER_PA * d_m * 100   # Torr*cm
    den = math.log(A_T * pd) - math.log(math.log(1 + 1 / GAMMA))
    return B_T * pd / den if den > 0 else float("inf")


def schumann_kv(d_mm, delta):
    d = d_mm / 10 * delta
    return 24.22 * d + 6.08 * math.sqrt(d)


if __name__ == "__main__":
    print("1  altitude factor: IEC 60664-1 vs pressure ratio p(2000 m)/p(h)")
    iec = {2000: 1.00, 3000: 1.14, 4000: 1.29, 5000: 1.48, 6000: 1.70, 7000: 1.95,
           8000: 2.25, 9000: 2.62, 10000: 3.02, 15000: 6.67, 20000: 14.50}
    p2 = isa_pressure(2000)
    for h, f in iec.items():
        p = isa_pressure(h)
        print(f"    {h:6d} m  p = {p/1000:6.2f} kPa  ratio {p2/p:6.2f}   IEC factor {f:6.2f}")
    k = math.log(1 + 1 / GAMMA)
    pd_min = math.e * k / A_T
    v_min = math.e * B_T / A_T * k
    print(f"2  Paschen minimum (A={A_T}, B={B_T}, gamma={GAMMA}): {v_min:.0f} V at p*d = {pd_min:.2f} Torr*cm"
          " (measured air: ~327 V near 0.75 Torr*cm)")
    print("3  uniform-field breakdown (V) vs altitude and gap (Townsend form; Schumann form in brackets)")
    for h in (0, 2000, 5000, 10000, 15000, 20000, 25000, 30000, 35000):
        p = isa_pressure(h) if h <= 32000 else isa_pressure(32000) * math.exp(-(h - 32000) / 7000)
        delta = p / 101325 * 288.15 / (288.15 - 0.0065 * min(h, 11000) if h <= 11000 else 216.65)
        cells = []
        for d_mm in (0.2, 0.5, 1.0, 2.0, 5.0):
            vb = paschen(p, d_mm * 1e-3)
            cells.append(f"{d_mm}mm:{vb:6.0f}[{schumann_kv(d_mm, delta)*1000:6.0f}]")
        print(f"    {h:5d} m p={p/1000:6.2f} kPa  " + "  ".join(cells))
    print("4  IEC case-A clearance (PD2 column as reproduced in TI SLUP419) vs uniform-field breakdown at 1 atm")
    for kv, d_mm in ((0.5, 0.2), (1.5, 0.5), (2.5, 1.5), (4.0, 3.0), (6.0, 5.5)):
        vb = schumann_kv(d_mm, 1.0)
        print(f"    impulse {kv:3.1f} kV at {d_mm:4.2f} mm: uniform-field V_b {vb:5.2f} kV -> implied factor {vb/kv:4.2f}")
