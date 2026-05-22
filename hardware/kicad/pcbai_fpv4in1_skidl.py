"""pcb.ai FPV 4-in-1 ESC — Phase 3a main schematic, SKiDL netlist spec.

Canonical netlist source for the main sheet. Visual KiCad schematic is the
human-readable view; THIS Python file is the design source of truth at
Phase 3a. Phase 4 GUI work renders this into the visual .kicad_sch.

Scope of main sheet (Phase 3a contract):
  POWER INPUT: +BATT pad, SMBJ33A TVS, 4× AON6260 reverse-pol N-FETs in
  parallel (low-side topology), 2× 470 µF bulk caps → +VMOTOR rail.
  BEC: LMR51420YDDCR buck (+VMOTOR → +5V) + TLV76733DRVR LDO (+5V → +3V3)
  + VDDA ferrite filter.
  FC CONNECTOR: JST SM08B-SRSS-TB 8-pin (Betaflight standard pinout).
  ESD: 3× USBLC6-2SC6 covering 4× DShot + 1× TLM + 1× spare.
  STATUS LED: 1× green power-good LED + 1 kΩ R on +3V3.
  HIERARCHICAL: 4× channel boundary nets declared (sheets instantiated 3c).

Channel-scope parts are NOT here — deferred to Phase 3b channel.kicad_sch:
  4× MCU + 4× gate driver + 24× phase MOSFET + 12× shunt + 12× CSA + all
  per-channel decoupling.
"""

import os
os.environ.setdefault("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
os.environ.setdefault("KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols")

import skidl
from skidl import Part, Net, generate_netlist

skidl.set_default_tool(skidl.KICAD)

# ─────────── Power nets — global ───────────
BATT = Net("+BATT")
BATGND = Net("BATGND")
VMOTOR = Net("+VMOTOR")
V5 = Net("+5V")
V3V3 = Net("+3V3")
V3V3A = Net("+3V3A")
GND = Net("GND")

# ─────────── Power input — battery solder pads ───────────
BATT_PAD = Part("Connector_Generic", "Conn_01x02", value="BATT_PAD",
                footprint="Connector:TerminalBlock_Phoenix_MPT-2.54mm_1x02_P2.54mm_Horizontal")
BATT_PAD[1] += BATT
BATT_PAD[2] += BATGND

# ─────────── TVS — SMBJ33A across +BATT to GND ───────────
TVS1 = Part("Device", "D_TVS", value="SMBJ33A",
            footprint="Diode_SMD:D_SMB")
TVS1[1] += GND
TVS1[2] += BATT

# ─────────── Reverse-polarity ideal-diode (4× AON6260 N-FET, low-side) ───────────
R_GATE = Part("Device", "R", value="10K",
              footprint="Resistor_SMD:R_0603_1608Metric")
D_Z = Part("Device", "D_Zener", value="12V",
           footprint="Diode_SMD:D_SOD-323")

GATE_RP = Net("GATE_RP")
R_GATE[1] += BATT
R_GATE[2] += GATE_RP
D_Z[1] += GATE_RP
D_Z[2] += GND

RP_FETS = []
for i in range(1, 5):
    Q = Part("Device", "Q_NMOS", value="AON6260",
             footprint="Package_DFN_QFN:W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm")
    Q["G"] += GATE_RP
    Q["S"] += BATGND
    Q["D"] += GND
    RP_FETS.append(Q)

# ─────────── Bulk capacitor bank — 2× 470µF 63V ───────────
VMOTOR += BATT

CBULK1 = Part("Device", "C_Polarized", value="470uF_63V",
              footprint="Capacitor_SMD:CP_Elec_10x14.3")
CBULK2 = Part("Device", "C_Polarized", value="470uF_63V",
              footprint="Capacitor_SMD:CP_Elec_10x14.3")
CBULK1[1] += VMOTOR
CBULK1[2] += GND
CBULK2[1] += VMOTOR
CBULK2[2] += GND

# ─────────── BEC — Buck stage ───────────
U_BUCK = Part("Connector_Generic", "Conn_01x06", value="LMR51420YDDCR",
              footprint="Package_TO_SOT_SMD:SOT-23-6",
              description="LMR51420YDDCR functional placeholder; Phase 4 GUI swaps to custom symbol from components.kicad_sym")

SW = Net("BUCK_SW")
FB = Net("BUCK_FB")
BST = Net("BUCK_BST")

C_BUCK_IN = Part("Device", "C", value="10uF",
                 footprint="Capacitor_SMD:C_0805_2012Metric")
C_BUCK_IN[1] += VMOTOR
C_BUCK_IN[2] += GND

C_BUCK_OUT = Part("Device", "C", value="22uF",
                  footprint="Capacitor_SMD:C_0603_1608Metric")
C_BUCK_OUT[1] += V5
C_BUCK_OUT[2] += GND

L_BUCK = Part("Device", "L", value="0.47uH",
              footprint="Inductor_SMD:L_1608_0603Metric")
L_BUCK[1] += SW
L_BUCK[2] += V5

C_BST = Part("Device", "C", value="100nF",
             footprint="Capacitor_SMD:C_0402_1005Metric")
C_BST[1] += BST
C_BST[2] += SW

# Feedback divider for V_OUT = 5.0V (V_FB ≈ 0.8V on LMR51420)
R_FB_TOP = Part("Device", "R", value="130K",
                footprint="Resistor_SMD:R_0402_1005Metric")
R_FB_BOT = Part("Device", "R", value="24.9K",
                footprint="Resistor_SMD:R_0402_1005Metric")
R_FB_TOP[1] += V5
R_FB_TOP[2] += FB
R_FB_BOT[1] += FB
R_FB_BOT[2] += GND

# TPS563200 pin assignment used as a functional stand-in for LMR51420YDDCR
# (both SOT-23-6 6-pin buck). Verify exact mapping at Phase 4 GUI.
U_BUCK[5] += VMOTOR
U_BUCK[2] += GND
U_BUCK[4] += VMOTOR
U_BUCK[1] += SW
U_BUCK[6] += BST
U_BUCK[3] += FB

# ─────────── BEC — LDO stage (TLV76733DRVR) ───────────
U_LDO = Part("Connector_Generic", "Conn_01x06", value="TLV76733DRVR",
             footprint="Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP0.9x1.6mm",
             description="TLV76733DRVR functional placeholder; Phase 4 GUI swaps to custom symbol")

C_LDO_IN = Part("Device", "C", value="1uF",
                footprint="Capacitor_SMD:C_0402_1005Metric")
C_LDO_IN[1] += V5
C_LDO_IN[2] += GND

C_LDO_OUT = Part("Device", "C", value="1uF",
                 footprint="Capacitor_SMD:C_0402_1005Metric")
C_LDO_OUT[1] += V3V3
C_LDO_OUT[2] += GND

U_LDO[1] += V5
U_LDO[2] += GND
U_LDO[3] += V5
U_LDO[5] += V3V3

# VDDA ferrite + bypass for analog reference
FB_VDDA = Part("Device", "L", value="120ohm@100MHz",
               footprint="Inductor_SMD:L_0201_0603Metric")
FB_VDDA[1] += V3V3
FB_VDDA[2] += V3V3A
C_VDDA_1u = Part("Device", "C", value="1uF",
                 footprint="Capacitor_SMD:C_0402_1005Metric")
C_VDDA_100n = Part("Device", "C", value="100nF",
                   footprint="Capacitor_SMD:C_0402_1005Metric")
C_VDDA_1u[1] += V3V3A
C_VDDA_1u[2] += GND
C_VDDA_100n[1] += V3V3A
C_VDDA_100n[2] += GND

# ─────────── FC connector — JST SM08B-SRSS-TB ───────────
M1_RAW = Net("M1_RAW")
M2_RAW = Net("M2_RAW")
M3_RAW = Net("M3_RAW")
M4_RAW = Net("M4_RAW")
TLM = Net("TLM")
VBAT_SENSE_OUT = Net("VBAT_SENSE_OUT")
CURR_OUT = Net("CURR_OUT")

J_FC = Part("Connector_Generic", "Conn_01x08", value="SM08B-SRSS-TB",
            footprint="Connector_JST:JST_SH_SM08B-SRSS-TB_1x08-1MP_P1.00mm_Horizontal")
J_FC[1] += GND
J_FC[2] += VBAT_SENSE_OUT
J_FC[3] += CURR_OUT
J_FC[4] += TLM
J_FC[5] += M4_RAW
J_FC[6] += M3_RAW
J_FC[7] += M2_RAW
J_FC[8] += M1_RAW

# ─────────── ESD — 3× USBLC6-2SC6 ───────────
# In Phase 3a netlist, each USBLC6 is a shunt-to-GND on the data lines;
# I/O ports of the device are bidirectional, the data net passes through.
# Conceptually: M*_RAW (from FC) → M*_CLEAN (to MCU input).
M1_CLEAN = Net("M1_CLEAN")
M2_CLEAN = Net("M2_CLEAN")
M3_CLEAN = Net("M3_CLEAN")
M4_CLEAN = Net("M4_CLEAN")
TLM_CLEAN = Net("TLM_CLEAN")
ESD_SPARE = Net("ESD_SPARE")

# Each USBLC6-2SC6: I/O1, GND, Vbus, I/O2, GND, Vbus (per ST datasheet SC-70-6 mapping)
U_ESD1 = Part("Connector_Generic", "Conn_01x06", value="USBLC6-2SC6",
              footprint="Package_TO_SOT_SMD:SOT-23-6",
              description="USBLC6-2SC6 ESD array placeholder")
U_ESD1[1] += M1_RAW
U_ESD1[2] += GND
U_ESD1[3] += V5
U_ESD1[4] += M2_RAW
U_ESD1[5] += GND
U_ESD1[6] += M1_CLEAN

U_ESD2 = Part("Connector_Generic", "Conn_01x06", value="USBLC6-2SC6",
              footprint="Package_TO_SOT_SMD:SOT-23-6")
U_ESD2[1] += M3_RAW
U_ESD2[2] += GND
U_ESD2[3] += V5
U_ESD2[4] += M4_RAW
U_ESD2[5] += GND
U_ESD2[6] += M3_CLEAN

U_ESD3 = Part("Connector_Generic", "Conn_01x06", value="USBLC6-2SC6",
              footprint="Package_TO_SOT_SMD:SOT-23-6")
U_ESD3[1] += TLM
U_ESD3[2] += GND
U_ESD3[3] += V5
U_ESD3[4] += ESD_SPARE
U_ESD3[5] += GND
U_ESD3[6] += TLM_CLEAN

# Logical equivalence of raw/clean nets (USBLC6 is shunt; net passes through)
M1_CLEAN += M1_RAW
M2_CLEAN += M2_RAW
M3_CLEAN += M3_RAW
M4_CLEAN += M4_RAW
TLM_CLEAN += TLM

# ─────────── Power-good LED (green on +3V3) ───────────
LED_PG = Part("Device", "LED", value="GREEN",
              footprint="LED_SMD:LED_0603_1608Metric")
R_LED_PG = Part("Device", "R", value="1K",
                footprint="Resistor_SMD:R_0402_1005Metric")
LED_PG_NODE = Net("LED_PG_NODE")
R_LED_PG[1] += V3V3
R_LED_PG[2] += LED_PG_NODE
LED_PG["A"] += LED_PG_NODE
LED_PG["K"] += GND

# ─────────── VBAT_SENSE divider (Phase 3c — closes 3a deferred item) ───────────
# Battery voltage divider for FC pack-voltage monitoring (FC connector pin 2).
# Ratio derivation (Rigor §10):
#   6S worst case +BATT = 25.2 V (4.2 V × 6, CL-006 lock)
#   FC analog input range = ~3.3 V max (Betaflight FC ADC)
#   Target: VBAT=25.2 V → V_SENSE = 3.10 V (leaves 6.5% headroom under 3.3 V)
#   Required ratio = 25.2 / 3.10 = 8.13
#   Pick: R_TOP = 100 kΩ, R_BOT = 14 kΩ → ratio (100+14)/14 = 8.143
#         → V_SENSE at +BATT=25.2 V: 25.2 × 14/114 = 3.094 V ✓
#         → V_SENSE at +BATT=18.0 V (LiPo LVC): 18.0 × 14/114 = 2.21 V
#   Standby current: 25.2 V / 114 kΩ = 221 µA (low; meets master's "low Iq" criterion)
R_VBAT_TOP = Part("Device", "R", value="100K",
                  footprint="Resistor_SMD:R_0402_1005Metric",
                  description="VBAT_SENSE divider top (Phase 3c)")
R_VBAT_BOT = Part("Device", "R", value="14K",
                  footprint="Resistor_SMD:R_0402_1005Metric",
                  description="VBAT_SENSE divider bottom")
C_VBAT_FILT = Part("Device", "C", value="100nF",
                   footprint="Capacitor_SMD:C_0402_1005Metric",
                   description="VBAT_SENSE filter cap (anti-noise into FC ADC)")
R_VBAT_TOP[1] += BATT
R_VBAT_TOP[2] += VBAT_SENSE_OUT
R_VBAT_BOT[1] += VBAT_SENSE_OUT
R_VBAT_BOT[2] += GND
C_VBAT_FILT[1] += VBAT_SENSE_OUT
C_VBAT_FILT[2] += GND

# ─────────── CURR_OUT decision (Phase 3c — closes 3a deferred item) ──────────
# Master directive verified vs Betaflight 4-in-1 8-pin standard:
#   The TLM (telemetry) single-wire UART (pin 4) carries per-channel current
#   data reported by AM32 firmware (USE_SERIAL_TELEMETRY=yes per target.h
#   Phase 2c lock). FC parses this via the "Esc_sensor" / "Telemetry" data
#   stream. Analog CURR_OUT is NOT part of Betaflight's 4-in-1 standard.
#
# Decision: NO analog CURR aggregation hardware. The FC connector pin 3
# (defined as CURR_OUT in Phase 3a) is left as a future-expansion pin (e.g.,
# could carry RPM signal or auxiliary analog). For now, tie CURR_OUT to GND
# through a 100 kΩ pull-down to provide a defined inactive level (so the
# FC's analog input doesn't float when this ESC is connected; a floating
# ADC pin can pick up noise on the FC side).
R_CURR_PD = Part("Device", "R", value="100K",
                 footprint="Resistor_SMD:R_0402_1005Metric",
                 description="CURR_OUT inactive-state pull-down (analog CURR_OUT not used per Betaflight std; AM32 reports current via TLM telemetry)")
R_CURR_PD[1] += CURR_OUT
R_CURR_PD[2] += GND

# ─────────── 4× channel instantiation (Phase 3c hierarchy) ────────────────────
from channel_skidl import make_channel

# Connect TLM_CLEAN to one shared TLM bus across all 4 channels (Betaflight
# 4-in-1 convention — single TLM line, half-duplex multiplexed by FC config).
TLM_BUS = TLM_CLEAN

for ch_num in range(1, 5):
    # Per-channel hierarchical-pin nets:
    #   DShot input — one of M<n>_CLEAN from main (already wired to FC + ESD)
    dshot_in = [M1_CLEAN, M2_CLEAN, M3_CLEAN, M4_CLEAN][ch_num - 1]
    # SWD pads — one set per MCU (4 SWD test-point sets on board edge)
    swdio = Net(f"SWDIO_CH{ch_num}")
    swclk = Net(f"SWCLK_CH{ch_num}")
    # Motor outputs returned by make_channel
    motor_a, motor_b, motor_c = make_channel(
        ch_num,
        vmotor=VMOTOR,
        v5=V5,
        v3v3=V3V3,
        v3v3a=V3V3A,
        gnd=GND,
        dshot_in=dshot_in,
        tlm=TLM_BUS,
        swdio=swdio,
        swclk=swclk,
    )

    # Motor solder pads — 3× per channel (12 total). 3.0 mm dia exposed pads
    # on board edge per Phase 2.5 placement.
    for phase, motor_net in [('A', motor_a), ('B', motor_b), ('C', motor_c)]:
        pad = Part("Connector", "TestPoint", value=f"MOTOR_{phase}_CH{ch_num}",
                   footprint="TestPoint:TestPoint_Pad_D3.0mm")
        pad[1] += motor_net

    # SWD pads (per-MCU pattern) — 2 pads per channel (4 sets × 2 = 8 pads total).
    swd_dio_pad = Part("Connector", "TestPoint", value=f"SWDIO_CH{ch_num}",
                      footprint="TestPoint:TestPoint_Pad_D1.0mm")
    swd_clk_pad = Part("Connector", "TestPoint", value=f"SWCLK_CH{ch_num}",
                      footprint="TestPoint:TestPoint_Pad_D1.0mm")
    swd_dio_pad[1] += swdio
    swd_clk_pad[1] += swclk

if __name__ == "__main__":
    out = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.net"
    generate_netlist(file_=out)
    print(f"\n=== Phase 3c netlist export ===")
    print(f"output: {out}")
    with open(out) as f:
        txt = f.read()
    nrefs = txt.count(chr(40) + 'comp')
    nnets = txt.count('(net (code')
    print(f"  components (comp blocks): {nrefs}")
    print(f"  nets (net blocks):        {nnets}")
    print(f"  file size:                {len(txt):,} bytes")
