# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structures (kae.circuit.structures): commutation cells, decoupling, crystals, chains, victims, antennas."""
from circuit_fixtures import C, D, IC, L, Q, R, board, buck_board, fp, mcu_parts

from kae.circuit.netlist import Netlist
from kae.circuit.roles import infer_roles
from kae.circuit.structures import find_structures


def structures(parts):
    nl = Netlist.from_board(board(parts))
    r = infer_roles(nl)
    return nl, r, find_structures(nl, r)


def one(lst, **match):
    hits = [s for s in lst if all(s.get(k) == v for k, v in match.items())]
    assert len(hits) == 1, (match, [s['id'] for s in lst])
    return hits[0]


# ------------------------------------------------------------------------------- commutation cells
def test_integrated_buck_cell_loop_order_and_members():
    nl, r, st = structures(buck_board())
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck' and c['rail'] == '+12V' and c['sw'] == 'SW' and c['gnd'] == 'GND'
    # Cin+ -> U.VIN -> U.PGND -> Cin-, closed on the HF (smallest) input capacitor
    assert c['loop'][0] == ['C2', '1'] and c['loop'][-1] == ['C2', '2']
    assert c['loop'][1] == ['U1', ['3']] and c['loop'][2] == ['U1', ['1']]
    assert c['inductor'] == 'L1' and set(c['caps']) == {'C1', 'C2'}
    assert c['bootstrap_cap'] == 'C3'
    assert set(c['output_caps']) == {'C4', 'C5'}
    ex = c['excite']
    assert ex['V'] == 12.0 and ex['I'] == 1.2 and ex['t_sw_ns'] > 0 and ex['f_sw_Hz'] == 500e3


def test_feedback_divider_victim_states_the_output_voltage():
    nl, r, st = structures(buck_board())
    v = one(st['victims'], **{'class': 'feedback'})
    d = v['divider']
    assert d['top'] == 'R1' and d['bottom'] == 'R2' and d['sense_net'] == '+3V3'
    assert abs(d['vout_implied_V'] - 0.596 * (1 + 45.3 / 10)) < 0.01      # TPS54202 Vref 0.596 V
    assert v['nets'] == ['FB']


def test_async_buck_loop_runs_through_the_catch_diode():
    parts = [IC('U1', 'LM2596S-ADJ', 'Package_TO_SOT_SMD:TO-263-5', [('1', 'VIN', '+24V', 'power_in'), ('2', 'OUT', 'SW', 'output'),
                                                                    ('3', 'GND', 'GND', 'power_in'), ('4', 'FB', 'FB', 'input'),
                                                                    ('5', 'ON/OFF', 'GND', 'input')]),
             C('C1', '100uF', '+24V', 'GND', lib='Capacitor_SMD:CP_Elec_8x10'), C('C2', '1uF', '+24V', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
             D('D1', 'SS34', 'SW', 'GND', lib='Diode_SMD:D_SMA'), L('L1', '33uH', 'SW', '+5V'),
             C('C3', '220uF', '+5V', 'GND', lib='Capacitor_SMD:CP_Elec_8x10'), R('R1', '3k', '+5V', 'FB'), R('R2', '1k', 'FB', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck'
    refs = [t[0] for t in c['loop']]
    assert refs[0] == refs[-1] == 'C2'               # the ceramic, not the electrolytic, closes the hot loop
    assert 'D1' in refs and refs.index('U1') < refs.index('D1')


def test_boost_cell_closes_on_the_output_capacitor():
    parts = [IC('U1', 'MT3608', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'SW', 'SW', 'power_out'), ('2', 'GND', 'GND', 'power_in'),
                                                               ('3', 'FB', 'FB', 'input'), ('4', 'EN', '+3V3', 'input'),
                                                               ('5', 'IN', '+3V3', 'power_in'), ('6', 'NC', '', 'no_connect')]),
             C('C1', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'), L('L1', '4.7uH', '+3V3', 'SW'),
             D('D1', 'SS14', '+12V', 'SW', lib='Diode_SMD:D_SMA'), C('C2', '22uF', '+12V', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             R('R1', '191k', '+12V', 'FB'), R('R2', '10k', 'FB', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'boost' and c['rail'] == '+12V'
    assert c['loop'][0][0] == c['loop'][-1][0] == 'C2'
    assert [t[0] for t in c['loop'][1:3]] == ['D1', 'D1']


def test_discrete_half_bridge_cell_with_shunt():
    drv = IC('U1', 'IR2104', 'Package_SO:SOIC-8', [('1', 'VCC', '+12V', 'power_in'), ('2', 'IN', 'PWM', 'input'), ('7', 'HO', 'GH', 'output'),
                                                   ('5', 'LO', 'GL', 'output'), ('6', 'VS', 'PHASE', 'passive'), ('4', 'COM', 'GND', 'power_in')])
    parts = [drv, Q('Q1', 'IRF540N', 'GH', '+48V', 'PHASE', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             Q('Q2', 'IRF540N', 'GL', 'PHASE', 'SRC', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             R('R1', '0R01', 'SRC', 'GND', lib='Resistor_SMD:R_2512_6332Metric'),
             C('C1', '100uF', '+48V', 'GND', lib='Capacitor_THT:CP_Radial_D10.0mm_P5.00mm'), C('C2', '1uF', '+48V', 'GND'),
             C('C3', '100nF', '+12V', 'GND'),
             fp('J1', 'Conn_01x02', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', 'PHASE', '', ''), ('2', 'GND', '', '')])]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], **{'class': 'half_bridge'})
    refs = [t[0] for t in c['loop']]
    assert refs == ['C2', 'Q1', 'Q1', 'Q2', 'Q2', 'R1', 'R1', 'C2']
    assert c['controller'] == 'U1' and c['shunt'] == 'R1' and c['excite']['V'] == 48.0


# ------------------------------------------------------------------------------- decoupling
def test_decap_groups_and_ownership_by_sheet():
    parts = mcu_parts(sheet='/MCU/') + [
        IC('U3', 'W25Q128JVS', 'Package_SO:SOIC-8_5.23x5.23mm', [('8', 'VCC', '+3V3', 'power_in'), ('4', 'GND', 'GND', 'power_in'),
                                                                 ('1', 'CS', 'CS', 'input')], sheet='/Flash/'),
        C('C30', '100nF', '+3V3', 'GND', sheet='/Flash/')]
    nl, r, st = structures(parts)
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    flash = one(st['decaps'], ic='U3', rail='+3V3')
    assert mcu['power_pins'] == ['1', '2', '3', '4'] and mcu['ground_pins'] == ['6', '7']
    assert set(mcu['caps']) == {'C10', 'C11', 'C12', 'C13', 'C14'}
    assert flash['caps'] == ['C30']
    assert mcu['bulk_caps'] == ['C14'] and 'C14' not in mcu['hf_caps']   # >= 4.7 uF is bulk
    vdda = one(st['decaps'], ic='U2', rail='+3V3A')
    assert vdda['caps'] == ['C15']
    # four VDD pins on one net: no netlist evidence for which cap sits at which pin -> the placer pairs by distance
    assert mcu['pin_caps'] == {} and mcu['pairing'] == 'nearest_pin'
    assert flash['pin_caps'] == {'8': ['C30']} and flash['pairing'] == 'pin'


def test_ldo_input_and_output_caps():
    parts = [IC('U1', 'AMS1117-3.3', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2', [('1', 'GND', 'GND', 'power_in'), ('2', 'VO', '+3V3', 'power_out'),
                                                                             ('3', 'VI', '+5V', 'power_in')]),
             C('C1', '10uF', '+5V', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             C('C2', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
             IC('U2', 'ATTINY85-20SU', 'Package_SO:SOIC-8', [('4', 'GND', 'GND', 'power_in'), ('8', 'VCC', '+3V3', 'power_in')]),
             C('C3', '100nF', '+3V3', 'GND')]
    nl, r, st = structures(parts)
    out = one(st['decaps'], ic='U1', function='regulator_output')
    assert out['caps'] == ['C2']
    assert one(st['decaps'], ic='U2')['caps'] == ['C3']
    heat = one(st['heat_sources'], part='U1')
    assert 0.1 < heat['P_W'] < 2.0


# ------------------------------------------------------------------------------- crystal, chains, sense, antenna
def test_crystal_circuit():
    nl, r, st = structures(mcu_parts())
    x = one(st['crystals'], crystal='Y1')
    assert x['ic'] == 'U2' and x['xin'] == '8' and x['xout'] == '9'
    assert set(x['load_caps']) == {'C16', 'C17'} and x['f_Hz'] == 8e6
    one(st['victims'], **{'class': 'crystal'})


def test_usb_connector_chain_with_esd_and_series_resistors():
    parts = mcu_parts() + [
        fp('J1', 'USB_C_Receptacle', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
           [('A6', 'D_P', 'D+', 'bidirectional'), ('A7', 'D_N', 'D-', 'bidirectional'), ('A4', 'VBUS', 'VBUS', 'passive'),
            ('A1', 'GND', 'GND', 'passive'), ('S1', 'SHIELD', 'SHIELD', 'passive')]),
        IC('U4', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'I/O1', 'D_P', 'passive'), ('2', 'GND', 'GND', 'passive'),
                                                               ('3', 'I/O2', 'D_N', 'passive'), ('5', 'VBUS', 'VBUS', 'passive')]),
        R('R20', '22', 'D_P', 'USB_DP'), R('R21', '22', 'D_N', 'USB_DM'), C('C20', '10uF', 'VBUS', 'GND'),
        C('C21', '4.7nF', 'SHIELD', 'GND'), R('R22', '1M', 'SHIELD', 'GND')]
    nl, r, st = structures(parts)
    ch = one(st['chains'], connector='J1', pin='A6')
    assert ch['chain'] == [['J1', 'A6'], ['U4', '1'], ['R20', '1'], ['R20', '2'], ['U2', '12']]
    assert ch['protection'] == ['U4'] and ch['external'] == 'cable'
    sh = one(st['chains'], connector='J1', pin='S1')
    assert sh['shield_bond'] == 'rc_to_ground' and set(sh['bond']) == {'C21', 'R22'}


def test_sense_resistor_kelvin_loop():
    parts = [IC('U1', 'INA180A1', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'OUT', 'ISENSE', 'output'), ('2', 'GND', 'GND', 'power_in'),
                                                                 ('3', 'IN+', 'BUS', 'input'), ('4', 'IN-', 'LOAD', 'input'),
                                                                 ('5', 'VS', '+3V3', 'power_in')]),
             R('R1', '0R02', 'BUS', 'LOAD', lib='Resistor_SMD:R_2512_6332Metric'), C('C1', '100nF', '+3V3', 'GND'),
             C('C2', '10uF', 'BUS', 'GND'), R('R2', '10k', 'LOAD', 'GND')]
    nl, r, st = structures(parts)
    v = one(st['victims'], **{'class': 'sense'})
    assert v['shunt'] == 'R1' and v['amp'] == 'U1' and v['kelvin'] == 'pad_inner_edge'
    assert v['loop'] == [['R1', '1'], ['U1', '3'], ['U1', '4'], ['R1', '2']]


def test_antenna_feed_through_a_matching_network():
    parts = [fp('AE1', '2450AT18A100', 'RF_Antenna:Johanson_2450AT18x100', [('1', 'ANT', 'FEED', 'passive'), ('2', 'NC', '', 'no_connect')]),
             C('C1', '1.5pF', 'ANT', 'GND'), L('L1', '2.7nH', 'ANT', 'RF_M', lib='Inductor_SMD:L_0402_1005Metric'),
             C('C2', '1.2pF', 'RF_M', 'GND'),
             IC('U1', 'nRF52832', 'Package_DFN_QFN:QFN-48', [('30', 'ANT', 'RF_M', 'bidirectional'), ('31', 'VSS', 'GND', 'power_in'),
                                                             ('32', 'VDD', '+3V3', 'power_in')]),
             C('C3', '100nF', '+3V3', 'GND')]
    nl, r, st = structures(parts)
    a = one(st['antennas'], part='AE1')
    assert a['feed'][0] == ['AE1', '1'] and a['feed'][-1] == ['U1', '30']
    assert {'C1', 'L1', 'C2'} <= set(a['match']) and a['f_Hz'] == 2.45e9


# ------------------------------------------------------------------------------- audit fixes
def _opamp(ref, sheet=''):
    return IC(ref, 'NE5532', 'Package_DIP:DIP-8_W7.62mm', [('8', 'V+', '+12V', 'power_in'), ('4', 'V-', '-12V', 'power_in'),
                                                          ('3', '+', f'IN_{ref}', 'input'), ('1', '', f'OUT_{ref}', 'output')], sheet=sheet)


def test_split_supply_decoupling_and_entry_bulk():
    """Op-amps decoupled V+ to V- (one cap across each), and the electrolytics stay at the power entry."""
    parts = [fp('J1', 'EuroPower', 'Connector_IDC:IDC-Header_2x05', [('1', '-12V_IN', '-12V', 'passive'), ('3', 'GND', 'GND', 'passive'),
                                                                    ('9', '+12V_IN', '+12V', 'passive')]),
             D('D1', '1N4001', '+12V', '+12V_IN'), D('D2', '1N4001', '-12V_IN', '-12V'),
             C('C1', '22uF', '+12V', 'GND', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm'),
             C('C2', '22uF', 'GND', '-12V', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm'),
             _opamp('U1'), _opamp('U2'), _opamp('U3'),
             C('C3', '100nF', '+12V', '-12V'), C('C4', '100nF', '+12V', '-12V'), C('C5', '100nF', '+12V', '-12V')]
    nl, r, st = structures(parts)
    split = {d['ic']: d for d in st['decaps'] if d['function'] == 'split_supply'}
    assert {k: v['caps'] for k, v in split.items()} == {'U1': ['C3'], 'U2': ['C4'], 'U3': ['C5']}
    assert split['U1']['rail'] == '+12V' and split['U1']['ground'] == '-12V' and split['U1']['ground_pins'] == ['4']
    entry = {d['rail']: d for d in st['decaps'] if d['function'] == 'entry'}
    assert entry['+12V']['ic'] == 'D1' and entry['+12V']['caps'] == ['C1']
    assert entry['-12V']['ic'] == 'D2' and entry['-12V']['caps'] == ['C2']
    assert not any(u['ic'] in ('U1', 'U2', 'U3') for u in st['uncovered'])


def test_converter_output_caps_sit_at_the_inductor():
    nl, r, st = structures(buck_board() + mcu_parts())
    d = one(st['decaps'], function='converter_output')
    assert d['ic'] == 'L1' and d['rail'] == '+3V3' and set(d['caps']) == {'C4', 'C5'}
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    assert set(mcu['caps']) >= {'C10', 'C11', 'C12', 'C13'}       # the 100 nF caps stay with the MCU's VDD pins


def test_boost_cell_leaves_the_mcu_its_small_caps():
    """A boost converter's output loop closes on the large ceramic when the loads' pins need every 100 nF."""
    u = IC('U1', 'TPS61023', 'Package_TO_SOT_SMD:SOT-563', [('1', 'VIN', '+BATT', 'power_in'), ('2', 'SW', 'SW', 'power_out'),
                                                           ('3', 'GND', 'GND', 'power_in'), ('4', 'VOUT', '+3V3', 'power_out'),
                                                           ('5', 'FB', 'FB', 'input'), ('6', 'EN', '+BATT', 'input')])
    parts = [u, L('L1', '1uH', '+BATT', 'SW'), C('C1', '10uF', '+BATT', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'),
             C('C2', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'), R('R1', '732k', '+3V3', 'FB'), R('R2', '100k', 'FB', 'GND'),
             fp('BT1', 'LiPo', 'Battery:BatteryHolder_Keystone_1042_1x18650', [('1', '+BATT', '+', 'passive'), ('2', 'GND', '-', 'passive')])]
    parts += [x for x in mcu_parts() if x.ref not in ('C14',)]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1', **{'class': 'boost'})
    assert c['caps'][0] == 'C2' and c['loop'][0][0] == 'C2'
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    assert set(mcu['caps']) == {'C10', 'C11', 'C12', 'C13'}
    assert c['loop'][1] == ['U1', ['4']]                       # VOUT only, not the EN pin tied to the rail


def test_mcu_internal_smps_keeps_its_io_supply_pins_as_loads():
    mcu = IC('U1', 'RP2350A', 'Package_DFN_QFN:QFN-60', [('44', 'VREG_VIN', '+3V3', 'power_in'), ('45', 'VREG_LX', 'LX', 'power_out'),
                                                        ('46', 'VREG_PGND', 'GND', 'power_in'), ('47', 'VREG_FB', '+1V1', 'input'),
                                                        ('1', 'IOVDD', '+3V3', 'power_in'), ('10', 'IOVDD', '+3V3', 'power_in'),
                                                        ('22', 'IOVDD', '+3V3', 'power_in'), ('23', 'DVDD', '+1V1', 'power_in'),
                                                        ('61', 'GND', 'GND', 'power_in')])
    parts = [mcu, L('L1', '3.3uH', 'LX', '+1V1'), C('C1', '4.7uF', '+3V3', 'GND'), C('C2', '100nF', '+3V3', 'GND'),
             C('C3', '100nF', '+3V3', 'GND'), C('C4', '100nF', '+3V3', 'GND'), C('C5', '4.7uF', '+1V1', 'GND')]
    nl, r, st = structures(parts)
    one(st['commutation_cells'], controller='U1')
    io = one(st['decaps'], ic='U1', rail='+3V3')
    assert io['power_pins'] == ['1', '10', '22'] and len(io['caps']) >= 2


def test_chains_skip_cell_parts_and_led_zeners():
    parts = buck_board() + [fp('J2', 'Out', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', '+3V3', '', ''), ('2', 'GND', '', '')]),
                            D('D5', 'BZV55C6V2', '+3V3', 'LEDZ', lib='Diode_SMD:D_MiniMELF'), R('R5', '1k', 'LEDZ', 'LEDA'),
                            D('D6', 'LED', 'GND', 'LEDA', lib='LED_SMD:LED_0603_1608Metric')]
    nl, r, st = structures(parts)
    for ch in st['chains']:
        if ch['connector'] == 'J2':
            assert 'D5' not in ch['protection'] and 'L1' not in ch['series']


def test_feedback_found_from_the_net_name_when_pins_are_unnamed():
    u = IC('U1', 'TX4138', 'Package_SO:SOIC-8', [('1', '', 'SW', 'passive'), ('3', '', 'VIN', 'passive'), ('4', '', 'GND', 'passive'),
                                                 ('5', '', 'Vfb', 'passive')])
    parts = [u, L('L1', '33uH', 'SW', 'VOUT'), D('D1', 'SS510', 'SW', 'GND', lib='Diode_SMD:D_SMC'),
             C('C1', '100nF', 'VIN', 'GND'), C('C2', '470uF', 'VOUT', 'GND', lib='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'),
             R('R1', '56.2k', 'VOUT', 'Vfb'), R('R2', '10k', 'Vfb', 'GND')]
    nl, r, st = structures(parts)
    v = one(st['victims'], **{'class': 'feedback'})
    assert v['divider']['top'] == 'R1' and v['divider']['bottom'] == 'R2'


def test_pmic_buck_input_is_not_its_own_output():
    """nPM1300: the bucks run from VSYS (pin V_DD); +1V8 is buck 1's output through a 0 ohm link, not its input."""
    pm = IC('U1', 'nPM1300-QEXX', 'Package_DFN_QFN:QFN-32', [('1', 'VOUT1', 'VOUT1', 'power_out'), ('2', 'PVSS1', 'GND', 'input'),
                                                            ('3', 'SW1', 'SW1', 'input'), ('4', 'V_{DD}', 'VSYS', 'power_in'),
                                                            ('12', 'V_{IO}', '+1V8', 'power_in'), ('20', 'V_{SYS}', 'VSYS', 'power_out'),
                                                            ('33', 'GND', 'GND', 'passive')])
    parts = [pm, L('L1', '2u2', 'VOUT1', 'SW1'), C('C1', '10uF', 'VOUT1', 'GND'), R('R1', '0R', 'VOUT1', '+1V8'),
             C('C2', '100n', '+1V8', 'GND'), C('C3', '100n', '+1V8', 'GND'), C('C4', '10uF', 'VSYS', 'GND'), C('C5', '10uF', 'VSYS', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck' and c['rail'] == 'VSYS' and c['loop'][1] == ['U1', ['4']]


def test_logic_strap_divider_is_no_victim_but_an_adc_divider_is():
    parts = [IC('U1', 'STM32F030C8T6', 'Package_QFP:LQFP-48', [('10', 'PA0', 'TOUCH_EN', 'bidirectional'), ('11', 'PA1', 'ADC_VBAT', 'bidirectional'),
                                                             ('1', 'VDD', '+3V3', 'power_in'), ('8', 'VSS', 'GND', 'power_in')]),
             IC('U2', 'AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'VIN', 'VBAT', 'power_in'), ('5', 'VOUT', '+3V3', 'power_out'),
                                                                     ('2', 'GND', 'GND', 'power_in')]),
             C('C1', '1uF', '+3V3', 'GND'), C('C2', '1uF', 'VBAT', 'GND'),
             R('R1', '100k', '+3V3', 'TOUCH_EN'), R('R2', '100k', 'TOUCH_EN', 'GND'),
             R('R3', '1M', 'VBAT', 'ADC_VBAT'), R('R4', '1M', 'ADC_VBAT', 'GND'),
             fp('BT1', 'LiPo', 'Battery:BatteryHolder_Keystone_1042_1x18650', [('1', 'VBAT', '+', 'passive'), ('2', 'GND', '-', 'passive')])]
    nl, r, st = structures(parts)
    ids = {v['id'] for v in st['victims']}
    assert 'victim:divider:ADC_VBAT' in ids and 'victim:divider:TOUCH_EN' not in ids


# ------------------------------------------------------------------------------- second-step cell members
def test_cell_members_input_shunt_bootstrap_resistor_and_snubber():
    """TX4138-style buck: input shunts in the switch path, a bootstrap cap through 4.7 ohm, an RC snubber on SW."""
    u = IC('U1', 'TX4138', 'Package_SO:SOIC-8', [('1', '', 'SW', 'passive'), ('2', '', 'ILIM', 'passive'), ('9', '', 'ILIM', 'passive'),
                                                 ('3', '', 'VIN', 'passive'), ('4', '', 'GND', 'passive'), ('5', '', 'Vfb', 'passive'),
                                                 ('8', '', 'BSR', 'passive')])
    parts = [u, R('R1', '0.03', 'ILIM', 'VIN', lib='Resistor_SMD:R_1206_3216Metric'), R('R2', '0.03', 'ILIM', 'VIN', lib='Resistor_SMD:R_1206_3216Metric'),
             C('C1', '100uF', 'VIN', 'GND', lib='Capacitor_THT:CP_Radial_D10.0mm_P5.00mm'), C('C2', '100nF', 'VIN', 'GND'),
             D('D1', 'SS510', 'SW', 'GND', lib='Diode_SMD:D_SMC'), L('L1', '33uH', 'SW', 'VOUT'),
             C('C6', '470uF', 'VOUT', 'GND', lib='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'),
             R('R3', '4.7', 'BSR', 'BSC'), C('C4', '100nF', 'SW', 'BSC'),
             R('R4', '22', 'SNB', 'SW'), C('C3', '220pF', 'SNB', 'GND'),
             R('R7', '56.2k', 'VOUT', 'Vfb'), R('R5', '10k', 'Vfb', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['series_shunt'] == ['R1', 'R2']
    assert [t[0] for t in c['loop']] == ['C2', 'R1', 'R1', 'U1', 'U1', 'D1', 'D1', 'C2']
    assert c['loop'][3] == ['U1', ['2', '9']]                 # the switch current enters at ILIM/EP, not the VIN pin
    assert (c['bootstrap_cap'], c['bootstrap_r']) == ('C4', 'R3')
    assert c['snubbers'] == [['R4', 'C3']]


def test_bridge_charge_pump_caps_are_cell_members():
    drv = IC('U3', 'TMC6300-LA', 'Package_DFN_QFN:QFN-20', [('18', 'VS', 'VIN', 'power_in'), ('2', 'VCP', 'VCP', 'passive'),
                                                           ('1', 'W', 'PH_W', 'output'), ('19', 'U', 'PH_U', 'output'),
                                                           ('20', 'V', 'PH_V', 'output'), ('8', 'GND', 'GND', 'power_in')])
    parts = [drv, C('C10', '100nF', 'VIN', 'GND'), C('C9', '10uF', 'VIN', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             C('C2', '100nF', 'VCP', 'VIN'),
             fp('J2', 'Motor', 'Connector_JST:JST_PH_B3B-PH-K', [('1', 'PH_U', '', ''), ('2', 'PH_V', '', ''), ('3', 'PH_W', '', '')]),
             fp('J3', 'Power', 'Connector_JST:JST_PH_B2B-PH-K', [('1', 'VIN', '', ''), ('2', 'GND', '', '')])]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U3')
    assert c['charge_pump_caps'] == ['C2']


# ------------------------------------------------------------------------------- decap pairing cases (critical-router reports)
def test_multi_pin_group_pairs_by_distance_not_by_reference_order():
    """canhw-processor U4: six VDD pins on one net; a reference-order pin pairing put caps 11-22 mm from 'their' pins."""
    pins = [(n, 'VDD', '+3V3', 'power_in') for n in ('6', '11', '27', '50', '75', '100')] + [('10', 'VSS', 'GND', 'power_in')]
    parts = [IC('U4', 'STM32F407VGT6', 'Package_QFP:LQFP-100_14x14mm_P0.5mm', pins)] + \
        [C(f'C{i}', '0.1uF', '+3V3', 'GND') for i in (5, 6, 7, 8, 11, 12)]
    nl, r, st = structures(parts)
    d = one(st['decaps'], ic='U4', rail='+3V3')
    assert d['pairing'] == 'nearest_pin' and d['pin_caps'] == {} and len(d['caps']) == 6


def _bms_3v3(module_pin_type='power_in'):
    buck = IC('U3', 'LMR38010', 'Package_SO:SOIC-8', [('3', 'VIN', 'VIN', 'power_in'), ('8', 'SW', 'SW', 'power_out'),
                                                      ('1', 'GND', 'GND', 'power_in'), ('5', 'FB', 'FB', 'input')])
    return [buck, C('C40', '10uF', 'VIN', 'GND'), L('L2', '22uH', 'SW', '+3V3'), D('D9', 'SS14', 'SW', 'GND'),
            C('C17', '47uF', '+3V3', 'GND', lib='Capacitor_SMD:C_1210_3225Metric'), C('C18', '47uF', '+3V3', 'GND', lib='Capacitor_SMD:C_1210_3225Metric'),
            R('R28', '82k', '+3V3', 'FB'), R('R31', '35.7k', 'FB', 'GND'),
            IC('U1', 'SN65HVD230', 'Package_SO:SOIC-8', [('3', 'VCC', '+3V3', 'power_in'), ('2', 'GND', 'GND', 'power_in')], sheet='/MCU/'),
            IC('U2', 'SN65HVD75', 'Package_SO:SOIC-8', [('8', 'VCC', '+3V3', 'power_in'), ('5', 'GND', 'GND', 'power_in')], sheet='/MCU/'),
            fp('U5', 'ESP32-C3-MINI-1', 'RF_Module:ESP32-C3-MINI-1', [('3', '+3V3', '3V3', module_pin_type), ('1', 'GND', 'GND', 'power_in')],
               sheet='/MCU/'),
            C('C19', '100nF', '+3V3', 'GND', sheet='/MCU/'), C('C21', '100nF', '+3V3', 'GND', sheet='/MCU/'),
            C('C36', '100nF', '+3V3', 'GND', sheet='/MCU/'), C('C46', '10uF', '+3V3', 'GND', sheet='/MCU/')]


def test_module_3v3_pin_is_a_load_and_exclusive_owners_take_only_eligible_caps():
    """bms-c1: the ESP32 module's '3V3' pin read as a regulator output (a 'bypass' group), and the buck's output
    filter took a 100 nF cap because its quota had room."""
    nl, r, st = structures(_bms_3v3())
    mod = one(st['decaps'], ic='U5', rail='+3V3')
    assert mod['function'] == 'load'
    conv = one(st['decaps'], function='converter_output')
    assert set(conv['caps']) <= {'C17', 'C18', 'C46'} and 'C36' not in conv['caps']
    owners = {c: d['ic'] for d in st['decaps'] for c in d['caps']}
    assert all(owners.get(c) in ('U1', 'U2', 'U5') for c in ('C19', 'C21', 'C36'))
    for d in st['decaps']:                         # nothing below p = 0.5 is ever pinned
        assert all(d['caps_p'][c] >= 0.5 for cl in d['pin_caps'].values() for c in cl)


def test_leftover_caps_spread_by_caps_per_pin():
    """noisecard: caps left over after the quotas all went to the first consumer (the microphone)."""
    parts = [fp('MK1', 'ICS-43434', 'Sensor_Audio:InvenSense_ICS-43434', [('5', '+1V8', 'VDD', 'power_in'), ('3', 'GND', 'GND', 'power_in')]),
             IC('U1', 'STM32L011', 'Package_SO:TSSOP-20', [('4', 'VDD', '+1V8', 'power_in'), ('15', 'VSS', 'GND', 'power_in')]),
             C('C6', '0.1U', '+1V8', 'GND'), C('C7', '0.1U', '+1V8', 'GND'), C('C8', '2U2', '+1V8', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             C('C9', '0.1U', '+1V8', 'GND'),
             fp('J1', 'Power', 'Connector_PinHeader_2.54mm:PinHeader_1x02', [('1', '+1V8', 'VCC', 'power_in'), ('2', 'GND', 'GND', 'passive')])]
    nl, r, st = structures(parts)
    mic = one(st['decaps'], ic='MK1')
    mcu = one(st['decaps'], ic='U1')
    assert len(mic['caps']) == 2 and len(mcu['caps']) == 2


# ------------------------------------------------------------------------------- power paths (no switching)
def _usb_c(net='VUSB'):
    return fp('J1', 'USB_C', 'Connector_USB:USB_C_Receptacle_GCT_USB4105', [('A4', net, 'VBUS', 'passive'), ('A1', 'GND', 'GND', 'passive')])


def _battery(net='VBAT'):
    return fp('BT1', 'Battery', 'Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal', [('1', net, '+', 'passive'), ('2', 'GND', '-', 'passive')])


def test_load_switch_path_loop_current_and_heat():
    ls = IC('U1', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'VIN', '+5V', 'power_in'), ('6', 'VOUT', '+5V_SW', 'power_out'),
                                                                   ('3', 'ON', 'LOAD_EN', 'input'), ('2', 'GND', 'GND', 'power_in'),
                                                                   ('5', 'CT', 'Net-(U1-CT)', 'passive'), ('4', 'QOD', '+5V_SW', 'passive')])
    parts = [ls, C('C1', '1uF', '+5V', 'GND'), C('C2', '10uF', '+5V_SW', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             C('C3', '1nF', 'Net-(U1-CT)', 'GND'), _usb_c('+5V'),
             IC('U2', 'ATtiny85-20S', 'Package_SO:SOIC-8', [('8', 'VCC', '+5V', 'power_in'), ('4', 'GND', 'GND', 'power_in'),
                                                           ('5', 'PB0', 'LOAD_EN', 'bidirectional')]),
             C('C4', '100nF', '+5V', 'GND')]
    nl, r, st = structures(parts)
    p = one(st['power_paths'], controller='U1')
    assert p['id'] == 'path:U1' and p['class'] == 'load_switch' and (p['rail_in'], p['rail_out'], p['gnd']) == ('+5V', '+5V_SW', 'GND')
    assert p['caps_in'] == ['C1'] and p['caps_out'] == ['C2']       # the MCU keeps its own C4
    # Cin+ -> VIN -> VOUT (not the QOD pin tied to VOUT) -> Cout+ -> Cout- -> Cin-
    assert p['loop'] == [['C1', '1'], ['U1', '1'], ['U1', '6'], ['C2', '1'], ['C2', '2'], ['C1', '2']]
    assert p['excite']['I'] == 2.0 and p['R_on_ohm']['value'] == 0.052 and p['P_W'] == round(2.0 ** 2 * 0.052, 4)
    assert p['excite']['I_belief']['exactness'] == 'E5' and p['excite']['I_belief']['interval'] == [round(2.0 / 3, 3), 2.0]
    assert p['R_on_ohm']['exactness'] == 'E5' and p['R_on_ohm']['interval'][0] < 0.052 < p['R_on_ohm']['interval'][1]
    assert p['group'] is None
    h = one(st['heat_sources'], part='U1')
    assert h['P_W'] == p['P_W'] and st['P_W']['U1'][0] >= p['P_W']


def test_power_mux_one_path_per_input_sharing_the_output_caps():
    mux = IC('U1', 'TPS2115A', 'Package_SO:TSSOP-8', [('8', 'IN1', 'VUSB', 'power_in'), ('6', 'IN2', 'VBAT', 'power_in'),
                                                     ('7', 'OUT', 'VSYS', 'power_out'), ('5', 'GND', 'GND', 'power_in'),
                                                     ('1', 'D0', 'VUSB', 'input'), ('2', 'D1', 'GND', 'input'),
                                                     ('4', 'ILIM', 'Net-(U1-ILIM)', 'passive'), ('3', 'STAT', 'STAT', 'output')])
    parts = [mux, R('R1', '1k', 'Net-(U1-ILIM)', 'GND'), C('C1', '1uF', 'VUSB', 'GND'), C('C2', '1uF', 'VBAT', 'GND'),
             C('C3', '10uF', 'VSYS', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'), _usb_c(), _battery()]
    nl, r, st = structures(parts)
    ps = sorted(st['power_paths'], key=lambda p: p['id'])
    assert [p['id'] for p in ps] == ['path:U1:VBAT', 'path:U1:VUSB']
    assert all(p['class'] == 'power_mux' and p['group'] == 'U1' and p['rail_out'] == 'VSYS' and p['caps_out'] == ['C3'] for p in ps)
    assert [p['caps_in'] for p in ps] == [['C2'], ['C1']]
    assert ps[1]['loop'][1] == ['U1', '8']                        # IN1, not the D0 control pin tied to VUSB
    assert len([h for h in st['heat_sources'] if h['part'] == 'U1']) == 1


def _ideal_diode(q, qp, src, out, g):
    """A PMOS ideal diode with a matched PNP pair driving its gate."""
    return [Q(q, 'DMG2305UX', g, src, out),
            fp(qp, 'BC857BS', 'Package_TO_SOT_SMD:SOT-363_SC-70-6', [('1', g, 'C1', 'passive'), ('2', f'B_{q}', 'B1', 'passive'),
                                                                     ('3', out, 'E1', 'passive'), ('4', f'B_{q}', 'C2', 'passive'),
                                                                     ('5', f'B_{q}', 'B2', 'passive'), ('6', src, 'E2', 'passive')]),
            R(f'R{q}', '10k', g, 'GND'), R(f'RB{q}', '47k', f'B_{q}', 'GND')]


def test_ideal_diode_or_group_shares_the_output():
    parts = _ideal_diode('Q1', 'Q3', 'VUSB', 'VSYS', 'G1') + _ideal_diode('Q2', 'Q4', 'VBAT', 'VSYS', 'G2') + [
        C('C1', '10uF', 'VSYS', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'), C('C2', '1uF', 'VUSB', 'GND'), _usb_c(), _battery(),
        IC('U1', 'AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'VIN', 'VSYS', 'power_in'), ('5', 'VOUT', '+3V3', 'power_out'),
                                                                 ('2', 'GND', 'GND', 'power_in'), ('3', 'EN', 'VSYS', 'input')]),
        C('C3', '1uF', '+3V3', 'GND')]
    nl, r, st = structures(parts)
    p1, p2 = one(st['power_paths'], switches=['Q1']), one(st['power_paths'], switches=['Q2'])
    for p, src in ((p1, 'VUSB'), (p2, 'VBAT')):
        assert p['class'] == 'ideal_diode' and (p['rail_in'], p['rail_out']) == (src, 'VSYS') and p['group'] == 'or:VSYS'
        assert p['caps_out'] == ['C1']
    assert p1['caps_in'] == ['C2'] and p1['loop'][0] == ['C2', '1'] and p1['loop'][-1] == ['C2', '2']
    assert p2['caps_in'] == [] and any(e.weight < 0 for e in p2['evidence'])     # the battery side closes off the board
    assert 'or:VSYS' not in {p['id'] for p in st['power_paths']}


def test_reverse_polarity_pmos_behind_a_fuse():
    parts = [fp('J1', 'Screw_Terminal', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', 'VIN_RAW', '', 'passive'), ('2', 'GND', '', 'passive')]),
             fp('F1', '2A', 'Fuse:Fuse_1206_3216Metric', [('1', 'VIN_RAW', '', 'passive'), ('2', 'VIN_F', '', 'passive')]),
             Q('Q1', 'DMP3013SFV', 'Net-(Q1-G)', 'VIN_F', 'VIN', lib='Package_SO:PowerDI3333-8'),
             R('R1', '100k', 'Net-(Q1-G)', 'GND'), D('D1', 'BZT52C12', 'VIN', 'Net-(Q1-G)'),
             C('C1', '100uF', 'VIN', 'GND', lib='Capacitor_SMD:CP_Elec_6.3x7.7'), C('C2', '100nF', 'VIN', 'GND'),
             IC('U1', 'LM1117-3.3', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2', [('3', 'VI', 'VIN', 'power_in'), ('2', 'VO', '+3V3', 'power_out'),
                                                                              ('1', 'GND', 'GND', 'power_in')]),
             C('C3', '10uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0805_2012Metric')]
    nl, r, st = structures(parts)
    p = one(st['power_paths'], switches=['Q1'])
    assert p['class'] == 'reverse_polarity' and (p['rail_in'], p['rail_out']) == ('VIN_F', 'VIN')   # D in, S out: body diode forward
    assert p['series'] == ['F1'] and p['controller'] is None
    assert p['excite']['I'] == 2.0 and 'fuse F1' in p['excite']['basis'][0]
    assert p['P_W'] == round(4.0 * 13e-3, 4)


def test_small_fet_current_is_capped_by_what_its_package_dissipates():
    """sufst Q2: a 5 ohm SOT-23 PMOS behind a 2 A fuse would have dissipated 20 W."""
    parts = [fp('J1', 'Conn', 'Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical', [('1', 'VRAW', '', 'passive'), ('2', 'GND', '', 'passive')]),
             fp('F1', '500mA', 'Fuse:Fuse_0603_1608Metric', [('1', 'VRAW', '', 'passive'), ('2', '+12V', '', 'passive')]),
             Q('Q1', 'DMP510DL-7', 'GND', '+12V', '+12V_PROT'), C('C1', '10uF', '+12V_PROT', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             IC('U1', 'LM7805', 'Package_TO_SOT_SMD:TO-252-2', [('1', 'VI', '+12V_PROT', 'power_in'), ('3', 'VO', '+5V', 'power_out'),
                                                               ('2', 'GND', 'GND', 'power_in')]),
             C('C2', '10uF', '+5V', 'GND', lib='Capacitor_SMD:C_0805_2012Metric')]
    nl, r, st = structures(parts)
    p = one(st['power_paths'], switches=['Q1'])
    assert p['class'] == 'reverse_polarity' and p['controller'] is None          # a grounded gate names no controller
    assert "fuse F1 rated 0.5 A ('500mA')" in p['excite']['basis'][0] and 'capped' in p['excite']['basis'][0]
    assert abs(p['excite']['I'] - (0.35 / 5.0) ** 0.5) < 0.01


def _bms_bank():
    hsof = 'Package_TO_SOT_SMD:Infineon_PG-HSOF-8-1'
    return [Q('Q1', 'IPT012N08N5', 'G_DSG', 'MID', 'BAT+', lib=hsof), Q('Q2', 'IPT012N08N5', 'G_DSG', 'MID', 'BAT+', lib=hsof),
            Q('Q3', 'IPT012N08N5', 'G_CHG', 'MID', 'PACK+', lib=hsof), Q('Q4', 'IPT012N08N5', 'G_CHG', 'MID', 'PACK+', lib=hsof),
            Q('Q5', 'ZXMP10A17GTA', 'G_PCHG', 'PCHG', 'MID', lib='Package_TO_SOT_SMD:SOT-223-3_TabPin2'),       # pre-charge
            R('R9', '100', 'PCHG', 'PACK+', lib='Resistor_SMD:R_2512_6332Metric'),
            IC('U1', 'BQ76952', 'Package_QFP:TQFP-48_7x7mm_P0.5mm', [('41', 'DSG', 'G_DSG', 'output'), ('42', 'CHG', 'G_CHG', 'output'),
                                                                     ('43', 'PCHG', 'G_PCHG', 'output'), ('17', 'VSS', 'GND', 'power_in'),
                                                                     ('1', 'BAT', 'BAT+', 'power_in')]),
            fp('NT1', 'NetTie', 'NetTie:NetTie-2_SMD_Pad0.5mm', [('1', 'BAT-', '1', 'passive'), ('2', 'GND', '2', 'passive')]),
            C('C1', '47uF', 'BAT+', 'BAT-', lib='Capacitor_SMD:C_1210_3225Metric'),
            fp('P1', 'BAT+', 'Connector:Wuerth_PowerOne', [('1', 'BAT+', '', 'passive')]),
            fp('P2', 'BAT-', 'Connector:Wuerth_PowerOne', [('1', 'BAT-', '', 'passive')]),
            fp('P3', 'PACK+', 'Connector:Wuerth_PowerOne', [('1', 'PACK+', '', 'passive')])]


def test_bms_back_to_back_banks_chain_past_the_precharge_fet():
    """bms-c1: a pre-charge FET on the common-drain node had split the bank into two 'paths' into that node."""
    nl, r, st = structures(_bms_bank())
    p = one(st['power_paths'], **{'class': 'fet_bank'})
    assert p['id'] == 'path:Q1+Q3' and p['stages'] == [['Q1', 'Q2'], ['Q3', 'Q4']] and p['controller'] == 'U1'
    assert (p['rail_in'], p['rail_out'], p['gnd']) == ('BAT+', 'PACK+', 'BAT-') and p['caps_in'] == ['C1']
    assert abs(p['R_on_ohm']['value'] - 2 * 1.2e-3 / 2) < 1e-9
    assert len(st['power_paths']) == 1 and not any('Q5' in q['switches'] for q in st['power_paths'])
    assert {h['part'] for h in st['heat_sources']} >= {'Q1', 'Q2', 'Q3', 'Q4'}


def test_low_side_heater_switch_closes_through_its_terminals():
    """ikajdan: a TO-263 low-side heater switch on a connector-fed return was dropped as a crowbar; its flyback
    diode made the 24 V supply look derived from the switched node."""
    pad = 'Local:Pad_D5mm'
    parts = [fp('J8', 'Conn_01x01', pad, [('1', '+24V', 'PIN', 'passive')]), fp('J9', 'Conn_01x01', pad, [('1', 'HEAT-', 'PIN', 'passive')]),
             fp('F1', '3A', 'Fuse:Fuse_1206_3216Metric', [('1', '+24V', '', 'passive'), ('2', 'VIN', '', 'passive')]),
             Q('Q1', 'IRF1018ESPBF', 'Net-(Q1-G)', 'HEAT-', 'GND', lib='Package_TO_SOT_SMD:TO-263-2'),
             D('D1', 'SS54', '+24V', 'HEAT-', lib='Diode_SMD:D_SMC'), R('R1', '100', 'Net-(Q1-G)', 'HEAT_PWM'), R('R2', '10k', 'Net-(Q1-G)', 'GND'),
             IC('U1', 'ATmega328P-AU', 'Package_QFP:TQFP-32_7x7mm_P0.8mm', [('4', 'VCC', '+5V', 'power_in'), ('5', 'GND', 'GND', 'power_in'),
                                                                           ('13', 'PD6', 'HEAT_PWM', 'bidirectional')]),
             IC('U2', 'LM2596S-5', 'Package_TO_SOT_SMD:TO-263-5_TabPin3', [('1', 'VIN', 'VIN', 'power_in'), ('2', 'OUT', 'SW', 'output'),
                                                                           ('3', 'GND', 'GND', 'power_in'), ('4', 'FB', '+5V', 'input')]),
             C('C9', '100uF', 'VIN', 'GND', lib='Capacitor_SMD:CP_Elec_8x10'), C('C10', '1uF', 'VIN', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
             D('D2', 'SS34', 'SW', 'GND', lib='Diode_SMD:D_SMA'), L('L1', '33uH', 'SW', '+5V'),
             C('C1', '100nF', '+5V', 'GND'), C('C2', '220uF', '+5V', 'GND', lib='Capacitor_SMD:CP_Elec_8x10')]
    nl, r, st = structures(parts)
    assert r.nets['+24V'].attrs['source']['kind'] == 'connector'                 # not 'derived' through the flyback diode
    assert r.nets['VIN'].attrs['source'] == {'kind': 'derived', 'ref': 'F1', 'upstream': '+24V', 'via': 'fuse'}
    p = one(st['power_paths'], switches=['Q1'])
    assert p['class'] == 'fet_switch' and (p['rail_in'], p['rail_out']) == ('HEAT-', 'GND') and p['controller'] == 'U1'
    terms = [t[0] for t in p['loop']]
    assert terms[1:5] == ['J8', 'J9', 'Q1', 'Q1'] and terms[0] == terms[-1] and terms[0] in ('C9', 'C10')
    assert p['excite']['V'] == 24.0 and p['P_W'] > 1.0


def test_logic_gates_and_crowbars_are_no_power_paths():
    parts = [Q('Q1', 'DMG2305UX', 'IN', 'OUT', '+3V3'), Q('Q2', 'AO3400A', 'IN', 'OUT', 'GND'),                  # a CMOS inverter
             Q('Q3', 'AO3400A', 'CROW', '+3V3', 'GND'), R('R1', '10k', 'CROW', 'GND'),                         # a crowbar
             IC('U1', 'AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'VIN', '+5V', 'power_in'), ('5', 'VOUT', '+3V3', 'power_out'),
                                                                      ('2', 'GND', 'GND', 'power_in')]),
             C('C1', '1uF', '+3V3', 'GND'), C('C2', '1uF', '+5V', 'GND')]
    nl, r, st = structures(parts)
    assert st['power_paths'] == []


# ------------------------------------------------------------------------------- rail groups (many identical loads)
def _led_string(n, caps, lib2=None):
    parts = []
    for i in range(1, n + 1):
        lib = lib2 if lib2 and i % 2 == 0 else 'LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm'
        parts.append(fp(f'D{i}', 'WS2812B', lib, [('1', '+5V', 'VDD', 'power_in'), ('2', f'DO{i}', 'DOUT', 'output'),
                                                  ('3', 'GND', 'VSS', 'power_in'), ('4', f'DO{i - 1}', 'DIN', 'input')]))
    parts += [C(f'C{i}', '100nF', '+5V', 'GND') for i in range(1, caps + 1)]
    return parts


def test_identical_loads_make_a_rail_group_with_nearest_load_pairing():
    """yuiop29re: 29 WS2812C on one rail with 5 capacitors; reference order decides nothing there."""
    mcu = IC('U1', 'ATmega32U4-AU', 'Package_QFP:TQFP-44_10x10mm_P0.8mm', [('14', 'VCC', '+5V', 'power_in'), ('15', 'GND', 'GND', 'power_in'),
                                                                           ('34', 'VCC', '+5V', 'power_in'), ('35', 'GND', 'GND', 'power_in'),
                                                                           ('1', 'PE6', 'DO0', 'bidirectional')])
    parts = _led_string(8, 8) + [mcu, C('C20', '100nF', '+5V', 'GND', sheet='/MCU/'), C('C21', '100nF', '+5V', 'GND', sheet='/MCU/')]
    parts[-3].sheet = '/MCU/'
    nl, r, st = structures(parts)
    g = one(st['rail_groups'], rail='+5V')
    assert g['id'] == 'rg:+5V' and g['kind'] == 'rail_group' and g['pairing'] == 'nearest_load' and g['ground'] == 'GND'
    assert g['loads'] == [f'D{i}' for i in range(1, 9)] and 'U1' not in g['loads']
    assert set(g['caps']) <= {f'C{i}' for i in range(1, 9)} | {'C20', 'C21'} and g['caps']
    for d in st['decaps']:
        if d['ic'] in g['loads']:
            assert d['rail_group'] == 'rg:+5V' and d['pairing'] == 'nearest_load' and d['pin_caps'] == {}
        else:
            assert 'rail_group' not in d


def test_rail_group_thresholds_and_footprint_variants():
    nl, r, st = structures(_led_string(4, 2))                 # 4 loads, fewer caps than loads
    assert [g['id'] for g in st['rail_groups']] == ['rg:+5V']
    nl, r, st = structures(_led_string(4, 4))                 # 4 loads with a cap each: ownership stands
    assert st['rail_groups'] == []
    nl, r, st = structures(_led_string(6, 6, lib2='LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm_Rotated'))
    g = one(st['rail_groups'], rail='+5V')                    # rotated footprint variants are the same load
    assert len(g['loads']) == 6


def test_two_converters_on_one_rail_each_close_on_their_own_capacitor():
    """trellis-core: two TLV62569 bucks on VBUS with two 10 uF caps; the first took both, the second borrowed."""
    def buck(u, sw, out, fb):
        return [IC(u, 'TLV62569PDDCR', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'EN', 'VBUS', 'input'), ('2', 'GND', 'GND', 'power_in'),
                                                                        ('3', 'SW', sw, 'power_out'), ('4', 'VIN', 'VBUS', 'power_in'),
                                                                        ('6', 'FB', fb, 'input')]),
                L(f'L{u}', '2u2', sw, out, lib='Inductor_SMD:L_Wuerth_MAPI-2510'), R(f'RT{u}', '100k', out, fb), R(f'RB{u}', '100k', fb, 'GND'),
                C(f'CO{u}', '22u', out, 'GND', lib='Capacitor_SMD:C_0805_2012Metric')]
    parts = buck('U1', 'SW1', '+3V3', 'FB1') + buck('U2', 'SW2', '+0V9', 'FB2') + [
        C('C1', '10u', 'VBUS', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'), C('C7', '10u', 'VBUS', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'),
        fp('J1', 'USB_C', 'Connector_USB:USB_C_Receptacle_GCT_USB4105', [('A4', 'VBUS', 'VBUS', 'passive'), ('A1', 'GND', 'GND', 'passive')])]
    nl, r, st = structures(parts)
    c1, c2 = one(st['commutation_cells'], controller='U1'), one(st['commutation_cells'], controller='U2')
    assert c1['caps'] == ['C1'] and c2['caps'] == ['C7'] and not c2.get('cap_shared')
