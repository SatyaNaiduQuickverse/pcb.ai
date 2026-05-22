"""pcb.ai 4-in-1 ESC + autonomous-drone power-hub — Phase 3a main schematic.

Canonical netlist source for the main sheet. Visual KiCad schematic is the
human-readable view; THIS Python file is the design source of truth at
Phase 3a. Phase 4 GUI work renders this into the visual .kicad_sch.

Scope of main sheet (Phase 2d-REDO expanded contract):
  POWER INPUT: +BATT pad, NTC inrush limiter, SMBJ33A TVS, 4× AON6260
  reverse-pol N-FETs in parallel (low-side topology), 2× 470 µF bulk caps
  → +VMOTOR rail. Indicator LEDs (power-on green + rev-pol red).
  BEC (6-rail, autonomous-drone power-hub class — NOT FPV-class):
    +V5_FC  : buck #1, +VMOTOR → 5V/5A,  FC + cam + RX + LEDs
    +V5_PI5 : buck #2, +VMOTOR → 5V/5A,  RPi 5 (enhanced filter)
    +V5_AI  : buck #3, +VMOTOR → 5V/3A,  AI HAT (enhanced filter, split per master adjudication)
    +V9_VTX1: buck #4, +VMOTOR → 9V/2A,  VTX #1
    +V9_VTX2: buck #5, +VMOTOR → 9V/2A,  VTX #2 (isolated from #1)
    +V3V3   : LDO,     +V5_FC  → 3.3V/1A (existing TLV76733DRVR — kept)
  PER-RAIL SAFETY: eFuse + TVS + LC filter on each rail.
  AUX OUT: 6× solder pad pairs (one per rail) + 4× GND distribution pads —
    per Phase 2e-REDO solder-first strategy. Optional JST SH / XT30 connector
    footprints OVERLAID at Phase 3b-detail (not in this netlist).
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

# ─────────── Power nets — global (Phase 2d-REDO expanded 4-rail BEC) ───────────
BATT = Net("+BATT")               # raw battery (+ terminal)
BATT_NTC = Net("+BATT_NTC")       # after NTC inrush limiter (post-warmup ≈ +BATT)
BATGND = Net("BATGND")            # battery (- terminal)
VMOTOR = Net("+VMOTOR")           # after rev-pol FETs — main rail to MOSFETs + bucks
V5_FC = Net("+V5_FC")             # buck #1 output (FC/cam/RX/LEDs, 5A)
V5_PI5 = Net("+V5_PI5")           # buck #2 output (RPi 5, 5A — split from old V5_RPI per master adjudication)
V5_AI = Net("+V5_AI")             # buck #3 output (AI HAT, 3A — split per master adjudication)
V9_VTX1 = Net("+V9_VTX1")         # buck #4 output (VTX #1, 2A)
V9_VTX2 = Net("+V9_VTX2")         # buck #5 output (VTX #2, 2A, independent of #1)
V3V3 = Net("+3V3")                # LDO output (from V5_FC)
V3V3A = Net("+3V3A")              # analog VDD (V3V3 via ferrite)
GND = Net("GND")
# Backward-compat alias for downstream code referencing V5 (e.g., ESD Vbus).
# All loads on V5 belong to the FC domain (USBLC6 ESD, LDO input) — alias to V5_FC.
V5 = V5_FC

# ─────────── Power input — battery solder pads ───────────
BATT_PAD = Part("Connector_Generic", "Conn_01x02", value="BATT_PAD",
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
BATT_PAD[1] += BATT
BATT_PAD[2] += BATGND

# ─────────── NTC Inrush Current Limiter — 2× MF72 5D25 in PARALLEL (Phase 2d-REDO) ───────────
# Per master adjudication 2026-05-22 (URGENT #2 closed): no single NTC ICL with
# I_max ≥15A exists in JLC parts library. Parallel 2× MF72 5D25 (8A each, JLC
# C116485) → combined I_max = 16A ≥ 15A ✓, R_cold = 2.5Ω ≥ 1.5Ω ✓, R_hot ~25mΩ ≤ 50mΩ ✓.
# All 3 spec criteria met.
U_NTC1 = Part("Device", "R", value="MF72_5D25",
              footprint="Resistor_THT:R_Disc_D11.0mm_W4.6mm_P5.00mm",
              description="NTC inrush limiter #1 (Nanjing Shiheng MF72 5D25, 5Ω/8A, JLC C116485)")
U_NTC2 = Part("Device", "R", value="MF72_5D25",
              footprint="Resistor_THT:R_Disc_D11.0mm_W4.6mm_P5.00mm",
              description="NTC inrush limiter #2 (parallel with #1 for 16A combined I_max)")
U_NTC1[1] += BATT;     U_NTC1[2] += BATT_NTC
U_NTC2[1] += BATT;     U_NTC2[2] += BATT_NTC

# ─────────── TVS — SMBJ33A across +BATT_NTC to GND ───────────
TVS1 = Part("Device", "D_TVS", value="SMBJ33A",
            footprint="Diode_SMD:D_SMB")
TVS1[1] += GND
TVS1[2] += BATT_NTC

# ─────────── Reverse-polarity ideal-diode (4× AON6260 N-FET, low-side) ───────────
R_GATE = Part("Device", "R", value="10K",
              footprint="Resistor_SMD:R_0603_1608Metric")
D_Z = Part("Device", "D_Zener", value="12V",
           footprint="Diode_SMD:D_SOD-323")

GATE_RP = Net("GATE_RP")
R_GATE[1] += BATT_NTC
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
VMOTOR += BATT_NTC

CBULK1 = Part("Device", "C_Polarized", value="470uF_63V",
              footprint="Capacitor_SMD:CP_Elec_10x14.3")
CBULK2 = Part("Device", "C_Polarized", value="470uF_63V",
              footprint="Capacitor_SMD:CP_Elec_10x14.3")
CBULK1[1] += VMOTOR
CBULK1[2] += GND
CBULK2[1] += VMOTOR
CBULK2[2] += GND

# ─────────── Indicator LEDs (Phase 2d-REDO) ───────────
# LED_PWR: GREEN — lit when battery is connected with CORRECT polarity (visible
# only when rev-pol FETs ON, i.e., GATE_RP is high and rev-pol FETs source the
# return path normally). Powered from +VMOTOR (post rev-pol) via 5.1 kΩ → GND.
LED_PWR = Part("Device", "LED", value="GREEN",
               footprint="LED_SMD:LED_0603_1608Metric",
               description="Battery present + polarity correct indicator")
R_LED_PWR = Part("Device", "R", value="5K1",
                 footprint="Resistor_SMD:R_0603_1608Metric")
LED_PWR_NODE = Net("LED_PWR_NODE")
R_LED_PWR[1] += VMOTOR
R_LED_PWR[2] += LED_PWR_NODE
LED_PWR["A"] += LED_PWR_NODE
LED_PWR["K"] += GND

# LED_RPOL: RED — lit when battery polarity is REVERSED. In normal operation,
# GATE_RP is held high by R_GATE (pulled up from +BATT_NTC); rev-pol FETs are ON;
# BATGND is at GND potential; this LED sees zero V across it → OFF.
# When reversed, BATT_NTC is at -25V vs GND, R_GATE doesn't bias GATE_RP; the
# only path for current is through the rev-pol FET body diodes (reversed) →
# small current flows backward; LED_RPOL between GATE_RP and BATGND sees ~V_BR
# of the body diodes and lights through R_LED_RPOL. Safety: at most ~1mA.
LED_RPOL = Part("Device", "LED", value="RED",
                footprint="LED_SMD:LED_0603_1608Metric",
                description="Reverse-polarity warning indicator")
R_LED_RPOL = Part("Device", "R", value="5K1",
                  footprint="Resistor_SMD:R_0603_1608Metric")
LED_RPOL_NODE = Net("LED_RPOL_NODE")
R_LED_RPOL[1] += BATT
R_LED_RPOL[2] += LED_RPOL_NODE
LED_RPOL["A"] += LED_RPOL_NODE
LED_RPOL["K"] += BATGND

# ─────────── BEC — 4 Buck rails (Phase 2d-REDO expansion) ───────────
# Each buck: VIN=VMOTOR (12-30V range), with C_IN, inductor L, output C_OUT,
# feedback divider FB_TOP/FB_BOT, bootstrap cap C_BST, optional soft-start.
# Output then goes to eFuse → TVS → LC filter → exposed rail.
# All buck-IC PNs locked in docs/PHASE2D_REDO_BEC_EXPANSION.md §6 (JLC verified).

def buck_stage(idx, vmotor, gnd, vout_volts, i_out_amps,
               l_value, c_out_value, fb_top_value, fb_bot_value, part_value):
    """Generate one non-synchronous SOIC-8-EP buck stage (TPS54560 or AOZ1284PI).

    All 5 BEC bucks are non-synchronous SOIC-8-EP per master adjudication
    2026-05-22 (no JLC-stocked synchronous 30V-VIN 5A+ part exists). External
    Schottky catch diode (SS54 60V/5A SMA) is added per stage.

    Returns the V_BUCK<idx>_OUT net (buck IC's switching-node output, pre-eFuse).
    """
    sw = Net(f"BUCK{idx}_SW")
    fb = Net(f"BUCK{idx}_FB")
    bst = Net(f"BUCK{idx}_BST")
    v_buck_out = Net(f"V_BUCK{idx}_OUT")

    u_buck = Part("Connector_Generic", "Conn_01x08",
                  value=part_value,
                  footprint="Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm_ThermalVias",
                  description=f"Buck #{idx} ({part_value}, {vout_volts}V/{i_out_amps}A); non-sync, ext Schottky required")

    # Input bulk cap (close to VIN)
    c_in = Part("Device", "C", value="10uF",
                footprint="Capacitor_SMD:C_0805_2012Metric")
    c_in[1] += vmotor; c_in[2] += gnd
    # Additional input cap for ≥5A rails
    if i_out_amps >= 5:
        c_in_b = Part("Device", "C", value="22uF",
                      footprint="Capacitor_SMD:C_1206_3216Metric")
        c_in_b[1] += vmotor; c_in_b[2] += gnd

    # Inductor (sized per buck IC datasheet — see PHASE2D_REDO_BEC_EXPANSION.md §3)
    l_buck = Part("Device", "L", value=l_value,
                  footprint="Inductor_SMD:L_Sunlord_MWSA0630-2R2MT" if i_out_amps >= 5
                            else "Inductor_SMD:L_Sunlord_MWSA0503S-1R5MT")
    l_buck[1] += sw; l_buck[2] += v_buck_out

    # External Schottky catch diode (TPS54560 + AOZ1284PI are non-synchronous)
    # SS54: 40V/5A Schottky in SMA — handles freewheel current during off-time.
    d_catch = Part("Device", "D_Schottky", value="SS54",
                   footprint="Diode_SMD:D_SMA",
                   description=f"Buck #{idx} freewheel Schottky (non-sync requirement)")
    d_catch[1] += gnd   # Anode → GND
    d_catch[2] += sw    # Cathode → SW node

    # Bootstrap cap (BST to SW)
    c_bst = Part("Device", "C", value="100nF",
                 footprint="Capacitor_SMD:C_0402_1005Metric")
    c_bst[1] += bst; c_bst[2] += sw

    # Output cap
    c_out = Part("Device", "C", value=c_out_value,
                 footprint="Capacitor_SMD:C_0805_2012Metric")
    c_out[1] += v_buck_out; c_out[2] += gnd

    # Feedback divider (V_OUT = V_FB × (1 + R_TOP/R_BOT); V_FB=0.8V on TPS54560 and AOZ1284)
    r_fb_top = Part("Device", "R", value=fb_top_value,
                    footprint="Resistor_SMD:R_0402_1005Metric")
    r_fb_bot = Part("Device", "R", value=fb_bot_value,
                    footprint="Resistor_SMD:R_0402_1005Metric")
    r_fb_top[1] += v_buck_out
    r_fb_top[2] += fb
    r_fb_bot[1] += fb
    r_fb_bot[2] += gnd

    # SOIC-8-EP placeholder pin map (Phase 4 GUI swaps to per-PN custom symbol).
    u_buck[1] += bst        # BOOT
    u_buck[2] += vmotor     # VIN
    u_buck[3] += vmotor     # EN (tied to VIN for always-on)
    u_buck[4] += fb         # FB / VSENSE
    u_buck[5] += gnd        # GND (AGND)
    u_buck[6] += sw         # SW
    u_buck[7] += sw         # SW (TPS54560 SS/TR or 2nd SW — placeholder)
    u_buck[8] += gnd        # GND (EP / PGND)

    return v_buck_out


def safety_stack(rail_name, idx, v_in_unfiltered, v_out_filtered, gnd,
                 efuse_pn, tvs_pn, tvs_vrwm,
                 enhanced=False, protection_type="efuse"):
    """Generate per-rail safety stack: protection (eFuse OR polyfuse) → TVS → LC filter.

    v_in_unfiltered: buck IC's output node (pre-protection).
    v_out_filtered: final exposed rail net.
    enhanced=True: dual-stage LC + polymer electrolytic (V5_PI5 / V5_AI for sensitive loads).
    protection_type: "efuse" (active IC, 5V rails) or "polyfuse" (passive PPTC, 9V rails).
        Per master adjudication 2026-05-22: tier-matched protection.
    """
    v_protect_out = Net(f"{rail_name}_PROTECT_OUT")

    if protection_type == "efuse":
        # Active eFuse — TPS259251DRCR VSON-10 (or similar SOT-23-5 TPS family).
        # Provides current-limit, soft-start, reverse-current block, fault flag.
        u_efuse = Part("Connector_Generic", "Conn_01x10", value=efuse_pn,
                       footprint="Package_DFN_QFN:QFN-10-1EP_3x3mm_P0.5mm_EP1.65x1.65mm",
                       description=f"eFuse {efuse_pn} on rail {rail_name}")
        # Generic VSON-10 placeholder pin map. Per TPS25925 datasheet:
        # 1=VIN, 2=VIN, 3=GND (EP), 4=EN, 5=ILIMIT, 6=FLT_n, 7=NC, 8=OUT, 9=OUT, 10=NC
        u_efuse[1] += v_in_unfiltered    # VIN
        u_efuse[2] += v_in_unfiltered    # VIN (parallel pin)
        u_efuse[3] += gnd                # GND / EP
        u_efuse[4] += v_in_unfiltered    # EN tied to VIN for always-on
        u_efuse[8] += v_protect_out      # OUT
        u_efuse[9] += v_protect_out      # OUT (parallel pin)
        # ILIMIT resistor (programs trip current per datasheet's ILIM equation)
        r_ilim = Part("Device", "R", value="10K",
                      footprint="Resistor_SMD:R_0402_1005Metric")
        r_ilim[1] += u_efuse[5]
        r_ilim[2] += gnd
    elif protection_type == "polyfuse":
        # Passive resettable polyfuse — Bourns MF-MSMF200 (2A hold, ~4A trip).
        # No current sensing or fault flag; trips on overcurrent and self-resets when cool.
        u_polyfuse = Part("Device", "Fuse", value=efuse_pn,
                          footprint="Fuse:Fuse_1206_3216Metric",
                          description=f"Polyfuse {efuse_pn} on rail {rail_name} (2A hold)")
        u_polyfuse[1] += v_in_unfiltered
        u_polyfuse[2] += v_protect_out
    else:
        raise ValueError(f"Unknown protection_type: {protection_type}")

    # Rename for the rest of the function (was v_efuse_out before refactor)
    v_efuse_out = v_protect_out

    # TVS on eFuse output (transient suppression)
    tvs = Part("Device", "D_TVS", value=tvs_pn,
               footprint="Diode_SMD:D_SMA")
    tvs[1] += gnd
    tvs[2] += v_efuse_out

    # Ferrite bead (LC filter inductor — high-freq blocker)
    fb_filt = Part("Device", "L", value="600ohm@100MHz",
                   footprint="Inductor_SMD:L_0805_2012Metric")
    fb_filt[1] += v_efuse_out
    fb_filt[2] += v_out_filtered

    # Output filter caps (multi-stage ceramic)
    c1 = Part("Device", "C", value="22uF",
              footprint="Capacitor_SMD:C_0805_2012Metric")
    c2 = Part("Device", "C", value="10uF",
              footprint="Capacitor_SMD:C_0603_1608Metric")
    c3 = Part("Device", "C", value="100nF",
              footprint="Capacitor_SMD:C_0402_1005Metric")
    for c in (c1, c2, c3):
        c[1] += v_out_filtered
        c[2] += gnd

    if enhanced:
        # V5_PI5 extras: low-ESR polymer electrolytic + extra ceramic + supervisor
        c_pol = Part("Device", "C_Polarized", value="100uF_6V3_polymer",
                     footprint="Capacitor_SMD:CP_Elec_6.3x7.7")
        c_pol[1] += v_out_filtered; c_pol[2] += gnd
        c_extra = Part("Device", "C", value="22uF",
                       footprint="Capacitor_SMD:C_0805_2012Metric")
        c_extra[1] += v_out_filtered; c_extra[2] += gnd


# 5 buck rails (per master adjudication 2026-05-22 — V5_RPI 8A SPLIT into V5_PI5 5A + V5_AI 3A).
#
# FB divider math (V_FB = 0.8V on TPS54560 and AOZ1284):
#   5.0V: R_TOP/R_BOT = (5.0-0.8)/0.8 = 5.25 → 52.3K / 10K
#   9.0V: R_TOP/R_BOT = (9.0-0.8)/0.8 = 10.25 → 102K / 10K
#
# Inductor sizing per buck (assumed f_sw ≈ 600 kHz for TPS54560, ≈ 500 kHz for AOZ1284):
#   L ≥ V_IN × D × (1-D) / (f_sw × ΔI_L), ΔI_L ≈ 30% I_OUT
#   5V/5A @ V_IN=25V, D=0.2, f_sw=600k, ΔI_L=1.5A: L ≥ 4.4 µH → 4.7 µH E12
#   5V/3A @ same conds, ΔI_L=0.9A:                 L ≥ 7.4 µH → 8.2 µH E12
#   9V/2A @ V_IN=25V, D=0.36, f_sw=500k, ΔI_L=0.6A: L ≥ 7.7 µH → 10 µH E12

# Buck #1 — +V5_FC (FC + cam + RX + LEDs, 5A)
V_BUCK1_OUT = buck_stage(idx=1, vmotor=VMOTOR, gnd=GND,
                         vout_volts=5.0, i_out_amps=5.0,
                         l_value="4.7uH", c_out_value="22uF",
                         fb_top_value="52K3", fb_bot_value="10K",
                         part_value="TPS54560DDAR")     # JLC C31966

# Buck #2 — +V5_PI5 (RPi 5, 5A — dedicated rail per master adjudication)
V_BUCK2_OUT = buck_stage(idx=2, vmotor=VMOTOR, gnd=GND,
                         vout_volts=5.0, i_out_amps=5.0,
                         l_value="4.7uH", c_out_value="22uF",
                         fb_top_value="52K3", fb_bot_value="10K",
                         part_value="TPS54560DDAR")     # JLC C31966

# Buck #3 — +V5_AI (AI HAT, 3A — dedicated rail per master adjudication)
V_BUCK3_OUT = buck_stage(idx=3, vmotor=VMOTOR, gnd=GND,
                         vout_volts=5.0, i_out_amps=3.0,
                         l_value="8.2uH", c_out_value="22uF",
                         fb_top_value="52K3", fb_bot_value="10K",
                         part_value="TPS54560DDAR")     # JLC C31966

# Buck #4 — +V9_VTX1 (2A)
V_BUCK4_OUT = buck_stage(idx=4, vmotor=VMOTOR, gnd=GND,
                         vout_volts=9.0, i_out_amps=2.0,
                         l_value="10uH", c_out_value="22uF",
                         fb_top_value="102K", fb_bot_value="10K",
                         part_value="AOZ1284PI")        # JLC C48060

# Buck #5 — +V9_VTX2 (2A, independent of #4 per Sai's isolation requirement)
V_BUCK5_OUT = buck_stage(idx=5, vmotor=VMOTOR, gnd=GND,
                         vout_volts=9.0, i_out_amps=2.0,
                         l_value="10uH", c_out_value="22uF",
                         fb_top_value="102K", fb_bot_value="10K",
                         part_value="AOZ1284PI")        # JLC C48060

# ─────────── Per-rail safety stacks ───────────
# Tier-matched protection per master adjudication 2026-05-22:
#   5V rails (sensitive loads): TPS259251DRCR eFuse C527680
#   9V rails (VTX, less sensitive): Bourns MF-MSMF200 polyfuse (2A hold, ~4A trip)
#   3V3 LDO: internal current-limit (no extra IC)
safety_stack("V5_FC",  1, V_BUCK1_OUT, V5_FC,  GND,
             efuse_pn="TPS259251DRCR", tvs_pn="SMAJ5.0A", tvs_vrwm=5.0,
             protection_type="efuse")
safety_stack("V5_PI5", 2, V_BUCK2_OUT, V5_PI5, GND,
             efuse_pn="TPS259251DRCR", tvs_pn="SMAJ5.0A", tvs_vrwm=5.0,
             enhanced=True,                            # RPi5 enhanced filtering
             protection_type="efuse")
safety_stack("V5_AI",  3, V_BUCK3_OUT, V5_AI,  GND,
             efuse_pn="TPS259251DRCR", tvs_pn="SMAJ5.0A", tvs_vrwm=5.0,
             enhanced=True,                            # AI HAT also sensitive
             protection_type="efuse")
safety_stack("V9_VTX1",4, V_BUCK4_OUT, V9_VTX1,GND,
             efuse_pn="MF-MSMF200",    tvs_pn="SMAJ9.0A", tvs_vrwm=9.0,
             protection_type="polyfuse")
safety_stack("V9_VTX2",5, V_BUCK5_OUT, V9_VTX2,GND,
             efuse_pn="MF-MSMF200",    tvs_pn="SMAJ9.0A", tvs_vrwm=9.0,
             protection_type="polyfuse")

# ─────────── V5_PI5 voltage supervisor IC (Phase 2d-REDO enhanced filter requirement) ───────────
# Monitors V5_PI5; asserts PG_RPI when stable (4.65V threshold = 93% of 5.0V).
# Used for orderly RPi 5 power-up sequencing (Sai's sensitive-electronics requirement).
PG_RPI = Net("PG_RPI")
U_SUPERVISOR = Part("Connector_Generic", "Conn_01x03", value="VSUP_5V_TBD",
                    footprint="Package_TO_SOT_SMD:SOT-23",
                    description="V5_PI5 voltage supervisor (reset-IC class, 4.65V threshold)")
U_SUPERVISOR[1] += V5_PI5   # VCC
U_SUPERVISOR[2] += GND
U_SUPERVISOR[3] += PG_RPI   # RESET / PG output

# ─────────── BEC OUT — Solder pad pairs per rail (Phase 2e-REDO) ───────────
# Per Sai's 2026-05-22 user-POV direction: SOLDER PADS FIRST, optional connector
# footprints OVERLAID at Phase 3b-detail. Per-rail pad-pair sized per current:
#   5V rails (5A/5A/3A): D4.0mm (TestPoint_Pad_D4.0mm) — generous solder area
#   9V rails (2A each):  D3.0mm — medium
#   3V3 rail (1A):       D2.5mm — low
# Additional standalone GND pads (×4) distribute return current.
# Silkscreen requirements for Phase 3b-detail forward-listed in PHASE2E_REDO_CONNECTORS.md §3.

def bec_pad_pair(rail_name, rail_net, gnd_net, pad_diameter_mm):
    """Emit a +V and GND solder pad pair for one BEC rail.

    pad_diameter_mm: 4.0 for ≥3A rails, 3.0 for 2A, 2.5 for 1A.
    Value strings get silkscreen labels applied at Phase 3b-detail (see doc §3).
    """
    fp = f"TestPoint:TestPoint_Pad_D{pad_diameter_mm:.1f}mm"
    pad_v = Part("Connector", "TestPoint", value=f"PAD_{rail_name}_PLUS",
                 footprint=fp,
                 description=f"Solder pad for +{rail_name} (Phase 2e-REDO; optional JST SH / XT30 connector overlay per spec)")
    pad_v[1] += rail_net
    pad_g = Part("Connector", "TestPoint", value=f"PAD_{rail_name}_GND",
                 footprint=fp,
                 description=f"GND pad paired with +{rail_name}")
    pad_g[1] += gnd_net


# 6 BEC rails — solder pads per rail
bec_pad_pair("V5_FC",   V5_FC,   GND, 4.0)   # 5A — large
bec_pad_pair("V5_PI5",  V5_PI5,  GND, 4.0)   # 5A — large (RPi 5)
bec_pad_pair("V5_AI",   V5_AI,   GND, 4.0)   # 3A — large (AI HAT, also sensitive)
bec_pad_pair("V9_VTX1", V9_VTX1, GND, 3.0)   # 2A — medium
bec_pad_pair("V9_VTX2", V9_VTX2, GND, 3.0)   # 2A — medium
bec_pad_pair("V3V3",    V3V3,    GND, 2.5)   # 1A — small (no connector option per contract)

# Additional GND distribution pads (×4) for return-current spreading. Per
# master spec: "additional GND pads spread across the pad sets for return-current
# distribution".
for i in range(1, 5):
    pad_gnd_dist = Part("Connector", "TestPoint", value=f"PAD_GND_DIST_{i}",
                        footprint="TestPoint:TestPoint_Pad_D3.0mm",
                        description=f"GND return-current distribution pad #{i}")
    pad_gnd_dist[1] += GND

# ─────────── BEC — LDO stage (TLV76733DRVR) ───────────
# Now derived from +V5_FC (filtered rail) — same load domain as FC/MCU.
U_LDO = Part("Connector_Generic", "Conn_01x06", value="TLV76733DRVR",
             footprint="Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
             description="TLV76733DRVR LDO (+V5_FC → +V3V3, 1A); Phase 4 GUI swaps to custom symbol")

C_LDO_IN = Part("Device", "C", value="1uF",
                footprint="Capacitor_SMD:C_0402_1005Metric")
C_LDO_IN[1] += V5_FC
C_LDO_IN[2] += GND

C_LDO_OUT = Part("Device", "C", value="1uF",
                 footprint="Capacitor_SMD:C_0402_1005Metric")
C_LDO_OUT[1] += V3V3
C_LDO_OUT[2] += GND

U_LDO[1] += V5_FC
U_LDO[2] += GND
U_LDO[3] += V5_FC
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
