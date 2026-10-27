# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Value, net-name and package parsers of kae.circuit.values."""
import pytest

from kae.circuit import values as V


@pytest.mark.parametrize('text,farads', [
    ('100nF', 100e-9), ('0.1uF/16V', 0.1e-6), ('4u7', 4.7e-6), ('22p', 22e-12), ('1µF', 1e-6), ('0.1', 0.1e-6),
    ('10uF 25V X5R', 10e-6), ('CC0402_100NF_50V_10%_X7R', 100e-9), ('470µF', 470e-6), ('', None), ('100', None),
])
def test_capacitance(text, farads):
    got = V.capacitance(text)
    assert (got is None and farads is None) or got == pytest.approx(farads)


@pytest.mark.parametrize('text,ohms', [
    ('10k', 10e3), ('4K7', 4.7e3), ('0R05', 0.05), ('R050', 0.05), ('50m', 0.05), ('2.2 kOhm', 2.2e3), ('0', 0.0),
    ('1M', 1e6), ('120R', 120.0), ('10k/R0402', 10e3), ('R0402', None), ('5.1K 1%', 5.1e3),
])
def test_resistance_ignores_package_codes(text, ohms):
    """'R0402' is a package code, not 0.0402 ohm (suite run failure mode)."""
    got = V.resistance(text)
    assert (got is None and ohms is None) or got == pytest.approx(ohms)


@pytest.mark.parametrize('text,henries', [
    ('10uH', 10e-6), ('4.7 uH', 4.7e-6), ('2u2', 2.2e-6), ('33n', 33e-9), ('IND_2.2UH_20%_BOURNS', 2.2e-6), ('10uH 3A', 10e-6),
])
def test_inductance(text, henries):
    assert V.inductance(text) == pytest.approx(henries)


@pytest.mark.parametrize('text,hz', [('8MHz', 8e6), ('32.768kHz', 32768.0), ('32768Hz', 32768.0), ('32k768', 32768.0), ('12M', 12e6)])
def test_frequency(text, hz):
    assert V.frequency(text) == pytest.approx(hz)


@pytest.mark.parametrize('name,volts', [
    ('+3V3', 3.3), ('3.3V', 3.3), ('/Power/+1V8', 1.8), ('VCC_12V', 12.0), ('12V0', 12.0), ('P3V3', 3.3), ('-12V', -12.0),
    ('+5VA', 5.0), ('VDD3V3', 3.3), ('12P0V', 12.0), ('VCC', None), ('VBUS', None), ('GPIO2V', None), ('SDA', None),
])
def test_net_voltage(name, volts):
    got = V.net_voltage(name)
    assert (got is None and volts is None) or got[0] == pytest.approx(volts)


def test_clean_net_names():
    n = V.clean_net('/Sheet A/~{RESET}')
    assert n.short == 'RESET' and n.active_low
    assert V.clean_net('Net-(U1-Pad2)').auto
    assert V.clean_net('unconnected-(U3-NC-Pad4)').unconnected
    assert V.clean_net('/SDC0_D1{slash}JTAG_TMS').short == 'SDC0_D1/JTAG_TMS'


def test_package():
    assert V.package('Capacitor_SMD:C_0402_1005Metric').size == '0402'
    assert V.package('Capacitors SMD:CAPC1608X90N').size == '0603'
    assert V.package('Capacitor_THT:CP_Radial_D5.0mm_P2.00mm').polarized
    assert V.package('Capacitor_SMD:CP_Elec_6.3x5.4').polarized
    assert not V.package('Capacitor_SMD:C_0805_2012Metric').polarized
