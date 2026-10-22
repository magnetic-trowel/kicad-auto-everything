# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part and net roles (kae.circuit.roles), including the failure modes found by the suite physics run
(docs/topics/physics/suite-physics-results.md)."""
from circuit_fixtures import C, D, IC, Q, R, board, buck_board, fp, mcu_parts

from kae.circuit.netlist import Netlist
from kae.circuit.roles import classify_part, infer_roles, regulator_vout


def roles_of(parts, **kw):
    nl = Netlist.from_board(board(parts, **kw))
    return nl, infer_roles(nl)


# ------------------------------------------------------------------------------- part kinds
def kind(*args, **kw):
    nl = Netlist.from_board(board([fp(*args, **kw)]))
    k, sub, p, _ = classify_part(next(iter(nl.parts.values())))
    return k, sub, p


def test_part_kinds_from_names_values_footprints():
    assert kind('C1', '100nF', 'Capacitor_SMD:C_0402_1005Metric', [('1', 'A', '', ''), ('2', 'B', '', '')])[0] == 'capacitor'
    assert kind('R1', '10k', 'Resistor_SMD:R_0402_1005Metric', [('1', 'A', '', ''), ('2', 'B', '', '')])[0] == 'resistor'
    assert kind('L1', '10uH', 'Inductor_SMD:L_1210_3225Metric', [('1', 'A', '', ''), ('2', 'B', '', '')])[0] == 'inductor'
    # a bead on a resistor footprint, named by its impedance
    assert kind('FB1', '600R@100MHz', 'Resistor_SMD:R_0603_1608Metric', [('1', 'A', '', ''), ('2', 'B', '', '')])[0] == 'ferrite'
    assert kind('L2', '600OHM/2A', 'Inductor_SMD:L_0805_2012Metric', [('1', 'A', '', ''), ('2', 'B', '', '')])[0] == 'ferrite'
    k, sub, _ = kind('D1', 'SMBJ15A', 'Diode_SMD:D_SMB', [('1', 'A', 'K', ''), ('2', 'B', 'A', '')])
    assert (k, sub) == ('diode', 'tvs')
    k, sub, _ = kind('U5', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6',
                     [('1', 'D1', 'I/O1', 'passive'), ('2', 'GND', 'GND', 'passive'), ('3', 'D2', 'I/O2', 'passive'),
                      ('4', 'D2b', 'I/O2', 'passive'), ('5', 'VBUS', 'VBUS', 'passive'), ('6', 'D1b', 'I/O1', 'passive')])
    assert (k, sub) == ('diode', 'esd_array')          # an ESD array with a U prefix is not an IC
    assert kind('D2', 'BAT54', 'Package_TO_SOT_SMD:SOT-23', [('1', 'A', 'A', ''), ('3', 'B', 'K', '')])[1] == 'schottky'
    assert kind('Q1', 'AO3400A', 'Package_TO_SOT_SMD:SOT-23', [('1', 'G', 'G', ''), ('2', 'S', 'S', ''), ('3', 'D', 'D', '')])[:2] == ('transistor', 'nmos')
    assert kind('Y1', '8MHz', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', [('1', 'A', '1', ''), ('3', 'B', '3', '')])[0] == 'crystal'
    assert kind('X1', 'ASE-24MHz', 'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
                [('1', 'EN', 'EN', 'input'), ('2', 'GND', 'GND', 'power_in'), ('3', 'CLK', 'OUT', 'output'), ('4', 'V', 'VDD', 'power_in')])[0] == 'oscillator'
    assert kind('J1', 'USB_C_Receptacle', 'Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P', [('A4', 'VBUS', 'VBUS', 'passive')])[0] == 'connector'
    assert kind('TP1', 'TestPoint', 'TestPoint:TestPoint_Pad_D1.0mm', [('1', 'X', '1', 'passive')])[0] == 'test_point'
    assert kind('H1', 'MountingHole', 'MountingHole:MountingHole_3.2mm_M3', [])[0] == 'mounting_hole'
    assert kind('FID1', 'Fiducial', 'Fiducial:Fiducial_1mm_Mask2mm', [('1', '', '', '')])[0] == 'fiducial'
    assert kind('G1', 'LOGO', 'Symbol:OSHW-Logo_7.5x8mm_SilkScreen', [])[0] == 'graphic'
    # case-insensitive substrings must not misfire ('ExtraFootprints' contains 'traFo')
    assert kind('SW1', 'EG2305', 'ExtraFootprints:EG2305', [('1', 'A', 'NC_1', ''), ('2', 'B', 'NO_1', ''), ('3', 'C', 'COM_1', '')])[0] == 'switch'


def test_regulator_part_number_voltage():
    assert regulator_vout('AMS1117-3.3')[0] == 3.3
    assert regulator_vout('MCP1700-3302E/TT')[0] == 3.3
    assert regulator_vout('XC6206P332MR')[0] == 3.3
    assert regulator_vout('L7805CV')[0] == 5.0
    assert regulator_vout('NCP177AMX330TCG')[0] == 3.3
    assert regulator_vout('TLV74318PDBVR')[0] == 1.8
    assert regulator_vout('LM317') is None
    assert regulator_vout('SPX1117-ADJ') is None


# ------------------------------------------------------------------------------- grounds and rails
def test_split_grounds_stay_distinct():
    parts = [IC('U1', 'ADS1115', 'Package_SO:MSOP-10_3x3mm_P0.5mm',
                [('1', 'GND', 'GND', 'power_in'), ('2', 'AGND', 'AGND', 'power_in'), ('3', 'VDD', '+3V3', 'power_in'),
                 ('4', 'AIN0', 'AIN0', 'input')]),
             C('C1', '100nF', '+3V3', 'GND'), C('C2', '100nF', '+3V3', 'AGND'), C('C3', '1nF', 'AIN0', 'AGND'),
             IC('U2', 'ISO7741', 'Package_SO:SOIC-16W', [('1', 'GND_ISO', 'GND1', 'power_in'), ('2', 'VCC1', 'V_ISO', 'power_in')]),
             C('C4', '100nF', 'V_ISO', 'GND_ISO'), C('C5', '100nF', 'V_ISO', 'GND_ISO'),
             fp('J1', 'Conn_01x02', 'Connector_PinHeader_2.54mm:PinHeader_1x02', [('1', 'PGND', '', ''), ('2', '+12V', '', '')]),
             C('C6', '10uF', '+12V', 'PGND'), C('C7', '10uF', '+12V', 'PGND'),
             fp('J2', 'USB_B', 'Connector_USB:USB_B_OST', [('5', 'EARTH', 'Shield', 'passive')]),
             C('C8', '4.7nF', 'EARTH', 'GND'), R('R1', '1M', 'EARTH', 'GND')]
    nl, r = roles_of(parts)
    sub = {n: r.nets[n].subrole for n in r.grounds}
    assert sub['GND'] == 'ground' and r.gnd == 'GND'
    assert sub['AGND'] == 'analog_ground'
    assert sub['PGND'] == 'power_ground'
    assert sub['GND_ISO'] == 'isolated_ground'
    assert sub['EARTH'] == 'chassis'


def test_rails_with_voltage_sources():
    nl, r = roles_of(buck_board() + mcu_parts())
    assert r.nets['+12V'].role == 'rail' and r.nets['+12V'].attrs['volts']['value'] == 12.0
    assert r.nets['+3V3'].attrs['volts']['value'] == 3.3
    assert r.nets['+3V3'].attrs['source']['kind'] == 'converter'
    assert r.nets['+3V3A'].role == 'rail'                       # filtered branch through FB1
    assert r.nets['+3V3A'].attrs['source']['kind'] == 'derived'
    assert r.nets['SW'].role == 'switch_node'
    assert r.nets['FB'].role == 'analog' and r.nets['FB'].subrole == 'feedback'


def test_power_out_pin_on_a_connector_is_not_a_source():
    """Library pins typed power_out on connectors, fuses and resistors were read as regulator outputs."""
    parts = [fp('J1', 'Conn_01x02', 'Connector_PinHeader_2.54mm:PinHeader_1x02',
                [('1', 'SIG_OUT', 'VOUT', 'power_out'), ('2', 'GND', 'GND', 'power_out')]),
             R('R1', '10k', 'SIG_OUT', 'MCU_IN'), C('C1', '100nF', 'SIG_OUT', 'GND'),
             IC('U1', 'ATTINY85-20SU', 'Package_SO:SOIC-8', [('1', 'PB0', 'MCU_IN', 'bidirectional'), ('4', 'GND', 'GND', 'power_in'),
                                                             ('8', 'VCC', '+5V', 'power_in')]),
             C('C2', '100nF', '+5V', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets.get('SIG_OUT') is None or r.nets['SIG_OUT'].role != 'rail'
    assert r.parts['J1'].kind == 'connector'


def test_kelvin_sense_line_named_after_a_rail_is_not_a_rail():
    parts = [IC('U1', 'INA219AID', 'Package_SO:SOIC-8', [('1', 'IN+', 'VBAT_SENSE', 'input'), ('2', 'IN-', '+5V_KELVIN', 'input'),
                                                        ('3', 'VS', '+3V3', 'power_in'), ('4', 'GND', 'GND', 'power_in')]),
             R('R1', '0R05', 'VBAT_SENSE', '+5V_KELVIN', lib='Resistor_SMD:R_2512_6332Metric'),
             C('C1', '100nF', '+3V3', 'GND'), C('C2', '1uF', 'VBAT_SENSE', 'GND')]
    nl, r = roles_of(parts)
    for n in ('VBAT_SENSE', '+5V_KELVIN'):
        assert r.nets[n].role != 'rail', n
    assert r.parts['R1'].role == 'shunt'


def test_two_pin_supply_net_is_a_rail():
    """A rail with one load and one cap is still a rail (suite run: rejected for having two pads)."""
    parts = [IC('U1', 'BME280', 'Package_LGA:Bosch_LGA-8', [('1', 'GND', 'GND', 'power_in'), ('8', 'VDD', 'Net-(U1-VDD)', 'power_in')]),
             C('C1', '100nF', 'Net-(U1-VDD)', 'GND'), C('C2', '100nF', '+3V3', 'GND'), C('C3', '1uF', '+3V3', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets['Net-(U1-VDD)'].role == 'rail'


def test_internal_supply_without_a_source_is_still_a_rail():
    """IC-internal supplies (core LDO output on a decoupling-only net): source 'internal', not an error."""
    parts = [IC('U1', 'STM32F405RGT6', 'Package_QFP:LQFP-64', [('1', 'VCAP_1', 'VCAP1', 'power_out'), ('2', 'VSS', 'GND', 'power_in'),
                                                               ('3', 'VDD', '+3V3', 'power_in')]),
             C('C1', '2.2uF', 'VCAP1', 'GND'), C('C2', '100nF', '+3V3', 'GND'), C('C3', '100nF', '+3V3', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets['VCAP1'].role == 'rail'
    assert r.nets['VCAP1'].attrs['source']['kind'] == 'internal'
    assert r.nets['+3V3'].attrs['source']['kind'] == 'unknown'


# ------------------------------------------------------------------------------- switch nodes, pairs, signals
def test_logic_pair_is_not_a_half_bridge():
    """Two small FETs sharing a node (a level shifter, a logic inverter) must not become a power stage."""
    parts = [Q('Q1', 'BSS84', 'G1', '+3V3', 'X'), Q('Q2', 'BSS138', 'G1', 'X', 'GND'),
             C('C1', '100nF', '+3V3', 'GND'), C('C2', '100nF', '+3V3', 'GND'),
             IC('U1', 'ATTINY85-20SU', 'Package_SO:SOIC-8', [('1', 'PB0', 'G1', 'bidirectional'), ('4', 'GND', 'GND', 'power_in'),
                                                             ('8', 'VCC', '+3V3', 'power_in')])]
    nl, r = roles_of(parts)
    assert 'X' not in r.switch_nodes


def test_power_half_bridge_with_driver_and_shunt():
    drv = IC('U1', 'IR2104', 'Package_SO:SOIC-8', [('1', 'VCC', '+12V', 'power_in'), ('2', 'IN', 'PWM', 'input'),
                                                   ('7', 'HO', 'GH', 'output'), ('5', 'LO', 'GL', 'output'), ('6', 'VS', 'PHASE', 'passive'),
                                                   ('4', 'COM', 'GND', 'power_in')])
    parts = [drv, Q('Q1', 'IRF540N', 'GH', '+48V', 'PHASE', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             Q('Q2', 'IRF540N', 'GL', 'PHASE', 'SRC', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             R('R1', '0R01', 'SRC', 'GND', lib='Resistor_SMD:R_2512_6332Metric'),
             C('C1', '100uF', '+48V', 'GND', lib='Capacitor_THT:CP_Radial_D10.0mm_P5.00mm'), C('C2', '1uF', '+48V', 'GND'),
             C('C3', '100nF', '+12V', 'GND'),
             fp('J1', 'Conn_01x02', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', 'PHASE', '', ''), ('2', 'GND', '', '')])]
    nl, r = roles_of(parts)
    assert r.switch_nodes['PHASE']['kind'] == 'half_bridge'
    assert r.parts['R1'].role == 'shunt'


def test_usb_pair_and_signal_roles():
    nl, r = roles_of(mcu_parts() + [fp('J1', 'USB_C_Receptacle', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
                                       [('A6', 'USB_DP', 'D+', 'bidirectional'), ('A7', 'USB_DM', 'D-', 'bidirectional'),
                                        ('A4', 'VBUS', 'VBUS', 'passive'), ('A1', 'GND', 'GND', 'passive')]),
                                    C('C20', '10uF', 'VBUS', 'GND')])
    pairs = {(p.p, p.n): p for p in r.pairs}
    assert ('USB_DP', 'USB_DM') in pairs and pairs[('USB_DP', 'USB_DM')].interface == 'usb2'
    assert r.nets['USB_DP'].role == 'high_speed'
    assert r.nets['XIN'].role == 'clock' and r.nets['XIN'].subrole == 'xtal'
    assert r.nets['NRST'].role == 'reset'
    assert r.nets['ADC_IN0'].role == 'analog'
    assert r.nets['VBUS'].subrole == 'usb_vbus' and r.nets['VBUS'].attrs['volts']['value'] == 5.0
    assert r.parts['J1'].subtype == 'usb'


def test_can_pair_and_termination():
    parts = [IC('U1', 'TCAN1042', 'Package_SO:SOIC-8', [('6', 'CANL', 'CAN_L', 'bidirectional'), ('7', 'CANH', 'CAN_H', 'bidirectional'),
                                                        ('3', 'VCC', '+5V', 'power_in'), ('2', 'GND', 'GND', 'power_in')]),
             R('R1', '120', 'CAN_H', 'CAN_L'), C('C1', '100nF', '+5V', 'GND'),
             fp('J1', 'Conn_01x03', 'Connector_JST:JST_PH_B3B-PH-K', [('1', 'CAN_H', '', ''), ('2', 'CAN_L', '', ''), ('3', 'GND', '', '')])]
    nl, r = roles_of(parts)
    assert any(p.interface == 'can' and {p.p, p.n} == {'CAN_H', 'CAN_L'} for p in r.pairs)
    assert r.parts['R1'].role == 'termination'


# ------------------------------------------------------------------------------- audit fixes (docs/topics/physics/comprehension.md)
def test_supply_pins_typed_input_still_make_a_rail():
    """Libraries type VIN/VBAT/VDD as input or bidirectional (TPS63802 VIN, MCP73031 VBAT, CP2102 VDD)."""
    parts = [IC('U1', 'TPS63802', 'Package_SON:Texas_DLA0010A', [('10', 'VIN', '+BATT', 'input'), ('1', 'EN', '+BATT', 'input'),
                                                                   ('8', 'GND', 'GND', 'power_in')]),
             IC('U2', 'MCP73031', 'Package_TO_SOT_SMD:SOT-23-5', [('3', 'VBAT', '+BATT', 'input'), ('2', 'VSS', 'GND', 'input'),
                                                                   ('4', 'VDD', 'VBUS', 'input')]),
             C('C1', '4.7uF', '+BATT', 'GND'), C('C2', '10uF', '+BATT', 'GND'),
             IC('U3', 'CP2102-GMR', 'Package_DFN_QFN:QFN-28', [('6', 'VDD', 'Net-(U3-VDD)', 'bidirectional'), ('3', 'GND', 'GND', 'bidirectional')]),
             C('C3', '4.7uF', 'Net-(U3-VDD)', 'GND'), C('C4', '100nF', 'Net-(U3-VDD)', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets['+BATT'].role == 'rail' and r.nets['+BATT'].subrole == 'battery'
    assert r.nets['+BATT'].attrs['source'] == {'kind': 'regulator', 'ref': 'U2', 'pin': '3'}     # the charger's battery pin
    assert r.nets['Net-(U3-VDD)'].role == 'rail' and r.nets['Net-(U3-VDD)'].attrs['source']['kind'] == 'internal'


def test_rail_named_control_lines_are_not_rails():
    """'12V0_OUT_EN' is an enable line; INA VIN+/VIN- typed power_in on '12V0_LC1_P' are Kelvin taps."""
    parts = [fp('J1', 'MGMT', 'Connector_Molex:Molex_PicoBlade', [('1', '12V0_OUT_EN', '12V0_OUT_EN', 'input'), ('2', 'GND', 'GND', 'passive')]),
             fp('J2', 'MGMT', 'Connector_Molex:Molex_PicoBlade', [('1', '12V0_OUT_EN', '12V0_OUT_EN', 'output'), ('2', 'GND', 'GND', 'passive')]),
             IC('U1', 'INA230', 'Package_DFN_QFN:QFN-16', [('13', 'VIN+', '12V0_LC1_P', 'power_in'), ('12', 'VIN-', '12V0_LC1_N', 'power_in'),
                                                          ('11', 'VBUS', '12V0_LC1', 'power_in'), ('9', 'VS', '3V3', 'power_in'),
                                                          ('10', 'GND', 'GND', 'power_in')]),
             fp('R1', 'LVK25R005FER', 'Resistor_SMD:R_Shunt_Ohmite_LVK25', [('1', '12V0_LC1_N', 'ILO', 'power_out'), ('2', '12V0_LC1', 'VO', 'power_out'),
                                                                         ('3', '12V0_LC1_P', 'IHI', 'power_out'), ('4', 'SW_OUT', 'VI', 'power_out')]),
             IC('U2', 'NCP45560', 'Package_DFN_QFN:DFN-12', [('1', 'VIN', '12V0', 'power_in'), ('8', 'VOUT', 'SW_OUT', 'power_out'),
                                                            ('4', 'GND', 'GND', 'power_in'), ('3', 'VCC', '3V3', 'power_in')]),
             fp('J3', 'MiniFit', 'Connector_Molex:Molex_Mini-Fit_Jr', [('1', '12V0_LC1', '', 'passive'), ('2', 'GND', '', 'passive')]),
             fp('J4', 'MiniFit', 'Connector_Molex:Molex_Mini-Fit_Jr', [('1', '12V0', '', 'passive'), ('2', 'GND', '', 'passive')]),
             C('C1', '470nF', '3V3', 'GND'), C('C2', '10uF', '12V0', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets['12V0_OUT_EN'].role != 'rail'
    for n in ('12V0_LC1_P', '12V0_LC1_N'):
        assert r.nets[n].role == 'analog' and r.nets[n].subrole == 'sense', n
    assert r.parts['R1'].subtype == 'shunt'
    assert r.nets['SW_OUT'].attrs['volts']['value'] == 12.0                        # a load switch passes its input through
    assert r.nets['12V0_LC1'].attrs['source'] == {'kind': 'derived', 'ref': 'R1', 'upstream': 'SW_OUT', 'via': 'shunt'}


def test_i2c_clock_and_gpio_named_oscillator_pins():
    parts = [IC('U1', 'STM32F030C8T6', 'Package_QFP:LQFP-48', [('3', 'PC14', 'PC14', 'bidirectional'), ('4', 'PC15', 'BUTTON', 'bidirectional'),
                                                             ('42', 'PB6', 'I2C1_SCLK', 'bidirectional'), ('1', 'VDD', '+3V3', 'power_in'),
                                                             ('8', 'VSS', 'GND', 'power_in')]),
             IC('U2', 'AT24C128C', 'Package_SO:SOIC-8', [('6', 'SCL', 'I2C1_SCLK', 'input'), ('8', 'VCC', '+3V3', 'power_in'), ('4', 'GND', 'GND', 'power_in')]),
             R('R1', '2k2', 'I2C1_SCLK', '+3V3'), C('C1', '100nF', '+3V3', 'GND')]
    nl, r = roles_of(parts)
    assert r.nets['I2C1_SCLK'].role == 'signal' and r.nets['I2C1_SCLK'].subrole == 'i2c'
    assert r.nets['PC14'].role != 'clock' and r.nets['BUTTON'].role != 'clock'


def test_negative_rail_series_diode_direction():
    parts = [fp('J1', 'EuroPower', 'Connector_IDC:IDC-Header_2x05', [('1', '-12V_IN', '-12V', 'passive'), ('3', 'GND', 'GND', 'passive'),
                                                                    ('9', '+12V_IN', '+12V', 'passive')]),
             D('D1', '1N4001', '+12V', '+12V_IN'), D('D2', '1N4001', '-12V_IN', '-12V'),
             C('C1', '22uF', '+12V', 'GND', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm'),
             C('C2', '22uF', 'GND', '-12V', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm')]
    nl, r = roles_of(parts)
    assert r.nets['+12V'].attrs['source']['upstream'] == '+12V_IN'
    assert r.nets['-12V'].attrs['source']['kind'] == 'derived' and r.nets['-12V'].attrs['source']['upstream'] == '-12V_IN'
    assert r.nets['-12V_IN'].attrs['source']['kind'] == 'connector'


def test_rail_sources_through_middle_nets_jacks_and_modules():
    parts = [fp('J1', 'USB_C', 'Connector_USB:USB_C_Receptacle_HRO', [('A4', 'VBUS', 'VBUS', 'passive'), ('A1', 'GND', 'GND', 'passive')]),
             fp('F1', 'MF-NSMF050', 'Fuse:Fuse_1206_3216Metric', [('1', 'VBUS', '', 'passive'), ('2', 'MID', '', 'passive')]),
             D('D1', 'RB160M-30', '5V0', 'MID'), C('C1', '10uF', '5V0', 'GND'), C('C2', '1uF', '5V0', 'GND'),
             fp('J2', 'TRRS', 'Connector_Audio:Jack_3.5mm_PJ320A', [('S', '5V0', '', 'passive'), ('T', 'GND', '', 'passive')]),
             fp('U1', 'RP2040_breakout', 'lib:RP2040_Breakout-PTH', [('1', '3V3', '+3V3', 'power_in'), ('2', 'GND', 'GND', 'power_in'),
                                                                     ('3', '5V0', 'VSYS', 'power_in')]),
             fp('J3', 'OLED', 'Connector_PinHeader_2.54mm:PinHeader_1x04', [('1', '3V3', 'VCC', 'passive'), ('2', 'GND', 'GND', 'passive')]),
             C('C3', '100nF', '3V3', 'GND'),
             fp('JP1', 'SolderJumper_2_Open', 'Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm', [('1', '5V0', 'A', 'passive'), ('2', '3V3', 'B', 'passive')])]
    nl, r = roles_of(parts)
    s = r.nets['5V0'].attrs['source']
    assert s['kind'] == 'derived' and s['upstream'] == 'VBUS' and s['path'] == ['D1', 'F1']
    assert r.nets['VBUS'].attrs['source']['kind'] == 'connector' and r.nets['VBUS'].attrs['source']['ref'] == 'J1'
    assert r.nets['3V3'].attrs['source']['kind'] == 'module'                       # not the open jumper, not the OLED header
    assert abs(r.nets['5V0'].attrs['volts']['value'] - 5.0) < 1e-6                 # named 5V0


def test_signal_role_fixes():
    """GPIO0 is a strap only on ESP parts; bridge-driver AIN1 is a logic input; a converter's BOOT net is a bootstrap."""
    parts = [IC('U1', 'RP2350B', 'Package_DFN_QFN:QFN-80', [('2', 'GPIO0', 'GPIO0/TRIG', 'bidirectional'), ('5', 'IOVDD', '+3V3', 'power_in'),
                                                          ('3', 'GPIO10', 'MOTOR_IN1', 'bidirectional'), ('81', 'GND', 'GND', 'power_in')]),
             IC('U2', 'DRV8411A', 'Package_DFN_QFN:QFN-16', [('13', 'AIN1', 'MOTOR_IN1', 'input'), ('10', 'VM', 'VM', 'power_in'),
                                                            ('1', 'PGND', 'GND', 'power_in')]),
             IC('U3', 'ESP32-S3-WROOM-1', 'RF_Module:ESP32-S3-WROOM-1', [('27', 'IO0', 'BOOT_BTN', 'bidirectional'), ('2', '3V3', '+3V3', 'power_in'),
                                                                        ('1', 'GND', 'GND', 'power_in')]),
             fp('SW1', 'BOOT', 'Button_Switch_SMD:SW_SPST_B3U', [('1', 'BOOT_BTN', '1', 'passive'), ('2', 'GND', '2', 'passive')]),
             C('C1', '100nF', '+3V3', 'GND'), C('C2', '10uF', 'VM', 'GND')] + buck_board()
    nl, r = roles_of(parts)
    assert r.nets['GPIO0/TRIG'].role != 'boot'
    assert r.nets['BOOT_BTN'].role == 'boot'
    assert r.nets['MOTOR_IN1'].role != 'analog'
    assert r.nets['BST'].role == 'signal' and r.nets['BST'].subrole == 'bootstrap'


def test_mechanical_and_relay_part_kinds():
    panel = fp('REF1', 'PanelHole_Potentiometer_RV09', 'Panel:PanelHole_Potentiometer_RV09', [('', '', '', '')])
    panel.pads[0].kind = 'np_thru_hole'                 # one unplated hole: a front-panel cut-out drawing
    nl = Netlist.from_board(board([panel]))
    assert classify_part(next(iter(nl.parts.values())))[0] not in ('potentiometer', 'connector', 'switch')
    assert kind('BOOT0', 'BOOT0_SW', 'Project:K3-1270L-F1', [('1', 'A', '', 'passive'), ('2', 'B', '', 'passive'), ('3', 'C', '', 'passive')])[0] == 'switch'
    assert kind('U3', 'GAQY252G3S', 'Package_SO:SOP-4_4.4x2.6mm_P1.27mm',
                [('1', 'A', '1', 'input'), ('2', 'K', '2', 'input'), ('3', 'X', '3', 'passive'), ('4', 'Y', '4', 'passive')])[0] == 'optocoupler'
    k, sub, _ = kind('U1', 'FUSB302BMPX', 'Package_DFN_QFN:WQFN-14', [('1', 'CC2', 'CC2', 'bidirectional'), ('2', 'VBUS', 'VBUS', 'power_in'),
                                                                       ('3', 'VDD', 'VDD', 'power_in'), ('8', 'GND', 'GND', 'power_in')])
    assert (k, sub) == ('ic', 'usb_pd')
