"""pcb.ai FPV 4-in-1 ESC — Phase 3b channel sub-sheet, SKiDL netlist spec.

Single ESC channel as a parameterized function: make_channel(ch_num, rails).
Phase 3c instantiates 4× (one per motor channel).
"""

import os
os.environ.setdefault("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
os.environ.setdefault("KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols")

import skidl
from skidl import Part, Net, generate_netlist

skidl.set_default_tool(skidl.KICAD)


def make_channel(ch_num, vmotor, v5, v3v3, v3v3a, gnd, dshot_in, tlm, swdio, swclk,
                 vref_2v5, global_ovuv_n=None, kill_bus=None):
    """Instantiate one ESC channel.

    PR-centralize-vref (Phase 2 of channel-template-redo, 2026-05-23):
        TL431 + bias R + bypass C moved OUT of make_channel to main script —
        VREF_2V5 is now a board-global shared reference. Per-channel cluster now
        adds only a 10nF local bypass cap at the divider entry tap (HF decoupling
        at the hysteresis-feedback injection node). TLM pull-up also removed
        (was 4× parallel 10K = 2.5kΩ effective, accidental; now 1× central 10K
        in main script).

    Phase 3-redo additions: gate clamps, hardware current-limit,
    NTC + OTP comparator, local bypass cap stack, motor-phase TVS,
    per-channel kill rail.

    Args:
        vref_2v5: board-global 2.5V reference (from central TL431 in main script).
        global_ovuv_n: global TPS3700 fault output (active-low). When LOW,
            disables all channels. Wire-OR'd into kill_bus (open-drain).
        kill_bus: per-board channel kill signal node. Forms wire-OR (active-low)
            from each channel's I_TRIP, OTP_TRIP, plus global OVUV_N.
            Drives DRV8300 nSLEEP/EN per channel.

    Returns (motor_a, motor_b, motor_c, kill_rail_ch) nets.
    """
    cn = ch_num

    motor_a = Net(f"MOTOR_A_CH{cn}")
    motor_b = Net(f"MOTOR_B_CH{cn}")
    motor_c = Net(f"MOTOR_C_CH{cn}")
    shunt_a_top = Net(f"SHUNT_A_TOP_CH{cn}")
    shunt_b_top = Net(f"SHUNT_B_TOP_CH{cn}")
    shunt_c_top = Net(f"SHUNT_C_TOP_CH{cn}")
    csa_a_out = Net(f"CSA_A_OUT_CH{cn}")
    csa_b_out = Net(f"CSA_B_OUT_CH{cn}")
    csa_c_out = Net(f"CSA_C_OUT_CH{cn}")
    bemf_a = Net(f"BEMF_A_CH{cn}")
    bemf_b = Net(f"BEMF_B_CH{cn}")
    bemf_c = Net(f"BEMF_C_CH{cn}")
    gha = Net(f"GHA_CH{cn}"); gla = Net(f"GLA_CH{cn}")
    ghb = Net(f"GHB_CH{cn}"); glb = Net(f"GLB_CH{cn}")
    ghc = Net(f"GHC_CH{cn}"); glc = Net(f"GLC_CH{cn}")
    bsta = Net(f"BSTA_CH{cn}"); bstb = Net(f"BSTB_CH{cn}"); bstc = Net(f"BSTC_CH{cn}")
    pwm_inha = Net(f"PWM_INHA_CH{cn}")
    pwm_inhb = Net(f"PWM_INHB_CH{cn}")
    pwm_inhc = Net(f"PWM_INHC_CH{cn}")
    pwm_inla = Net(f"PWM_INLA_CH{cn}")
    pwm_inlb = Net(f"PWM_INLB_CH{cn}")
    pwm_inlc = Net(f"PWM_INLC_CH{cn}")
    led_gpio = Net(f"LED_GPIO_CH{cn}")

    # MCU (functional stand-in: Conn_01x32 32-pin placeholder; Phase 4 swaps to AT32F421 custom symbol from components.kicad_sym)
    # PR-A4-integrate amendment 5 BOM B-1b: LQFP-32 7x7mm → QFN-32 5x5mm
    # (AT32F421K8T7 → AT32F421K8U7 — same die, same firmware, JLC C176942)
    mcu = Part("Connector_Generic", "Conn_01x32", value="AT32F421K8U7",
               footprint="Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm_ThermalVias")
    mcu[1] += v3v3
    mcu[17] += v3v3
    mcu[5] += v3v3a
    mcu[16] += gnd
    mcu[32] += gnd
    mcu[4] += Net(f"NRST_CH{cn}")
    # BOOT0 (pin 31) — Phase 3b-detail: replace direct GND tie with 10kΩ pull-down
    # + 2-pin solder jumper for emergency DFU access (bridge to +3V3 to boot from
    # system bootloader). Per AT32F421 DS §2.5 boot-mode selection.
    boot0_node = Net(f"BOOT0_CH{cn}")
    mcu[31] += boot0_node
    r_boot0_pd = Part("Device", "R", value="10K",
                      footprint="Resistor_SMD:R_0402_1005Metric",
                      description=f"BOOT0 pull-down CH{cn} — default boot from flash")
    r_boot0_pd[1] += boot0_node
    r_boot0_pd[2] += gnd
    # 2-pin solder jumper pad: short to pull BOOT0 → +3V3 for DFU
    boot_jumper = Part("Connector", "TestPoint", value=f"BOOT_JUMPER_CH{cn}",
                       footprint="TestPoint:TestPoint_Pad_D1.5mm",
                       description=f"BOOT0 emergency DFU jumper pad CH{cn} — bridge to +3V3 solder pad")
    boot_jumper[1] += boot0_node
    boot_jumper_3v = Part("Connector", "TestPoint", value=f"BOOT_3V_CH{cn}",
                          footprint="TestPoint:TestPoint_Pad_D1.5mm",
                          description=f"+3V3 reference pad for BOOT0 jumper CH{cn}")
    boot_jumper_3v[1] += v3v3
    mcu[6] += bemf_a
    mcu[10] += bemf_b
    mcu[11] += bemf_c
    mcu[7] += gnd
    mcu[8] += csa_a_out
    mcu[9] += Net(f"NTC_CH{cn}")
    mcu[12] += Net(f"VBAT_SENSE_CH{cn}")
    mcu[13] += pwm_inlc
    mcu[14] += pwm_inlb
    mcu[15] += pwm_inla
    mcu[18] += pwm_inhc
    mcu[19] += pwm_inhb
    mcu[20] += pwm_inha
    mcu[23] += swdio
    mcu[24] += swclk
    mcu[27] += dshot_in
    mcu[29] += tlm
    # PR-centralize-vref Phase 2 (2026-05-23): per-channel TLM pull-up REMOVED.
    # Phase 1 audit found that 4× per-channel 10K pull-ups in parallel = 2.5kΩ
    # effective, which was unintentional (TLM is shared half-duplex single-line
    # bus across all 4 MCUs + FC). Single 10K to V3V3 lives in main script now.
    mcu[21] += Net(f"PA11_NC_CH{cn}")
    mcu[22] += Net(f"PA12_NC_CH{cn}")
    mcu[25] += led_gpio
    mcu[26] += Net(f"PB3_NC_CH{cn}")
    mcu[28] += Net(f"PB5_NC_CH{cn}")
    mcu[30] += Net(f"PB7_NC_CH{cn}")
    mcu[2] += Net(f"PF0_NC_CH{cn}")
    mcu[3] += Net(f"PF1_NC_CH{cn}")

    # MCU decoupling (per AT32F421 Fig 8)
    for _ in range(2):
        c = Part("Device", "C", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
        c[1] += v3v3; c[2] += gnd
    c_vdd_bulk = Part("Device", "C", value="10uF", footprint="Capacitor_SMD:C_0805_2012Metric")
    c_vdd_bulk[1] += v3v3; c_vdd_bulk[2] += gnd
    c_vdda1 = Part("Device", "C", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_vdda1[1] += v3v3a; c_vdda1[2] += gnd
    c_vdda2 = Part("Device", "C", value="1uF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_vdda2[1] += v3v3a; c_vdda2[2] += gnd

    # NRST cap + pull-up; BOOT0 pull-down
    c_nrst = Part("Device", "C", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_nrst[1] += mcu[4]; c_nrst[2] += gnd
    r_nrst = Part("Device", "R", value="10K", footprint="Resistor_SMD:R_0402_1005Metric")
    r_nrst[1] += mcu[4]; r_nrst[2] += v3v3
    r_boot = Part("Device", "R", value="10K", footprint="Resistor_SMD:R_0402_1005Metric")
    r_boot[1] += mcu[31]; r_boot[2] += gnd

    # Gate driver — DRV8300DRGER (functional stand-in: Conn_01x24 for pin-by-pin in Phase 4)
    drv = Part("Connector_Generic", "Conn_01x24", value="DRV8300DRGER",
               footprint="Package_DFN_QFN:HVQFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm")
    drv[1] += pwm_inla; drv[2] += pwm_inlb; drv[3] += pwm_inlc
    drv[4] += v5
    drv[5] += gnd
    drv[6] += gnd
    drv[9] += glc; drv[10] += glb; drv[11] += gla
    drv[12] += motor_c; drv[13] += ghc; drv[14] += bstc
    drv[15] += motor_b; drv[16] += ghb; drv[17] += bstb
    drv[18] += motor_a; drv[19] += gha; drv[20] += bsta
    r_dt = Part("Device", "R", value="40K", footprint="Resistor_SMD:R_0402_1005Metric")
    drv[21] += r_dt[1]; r_dt[2] += gnd
    drv[22] += pwm_inha; drv[23] += pwm_inhb; drv[24] += pwm_inhc

    # Driver decoupling
    c_drv_1u = Part("Device", "C", value="1uF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_drv_1u[1] += v5; c_drv_1u[2] += gnd
    c_drv_100n = Part("Device", "C", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_drv_100n[1] += v5; c_drv_100n[2] += gnd

    # Bootstrap caps 1µF X7R (per DRV8300 datasheet C_BOOT recommended)
    c_bsta = Part("Device", "C", value="1uF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_bsta[1] += bsta; c_bsta[2] += motor_a
    c_bstb = Part("Device", "C", value="1uF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_bstb[1] += bstb; c_bstb[2] += motor_b
    c_bstc = Part("Device", "C", value="1uF", footprint="Capacitor_SMD:C_0402_1005Metric")
    c_bstc[1] += bstc; c_bstc[2] += motor_c

    # Half-bridges with gate-drive damping + Phase 3-redo gate clamps + bypass stack + phase TVS
    def half_bridge(gh_net, gl_net, motor_net, shunt_top_net, phase_label):
        r_gh = Part("Device", "R", value="15R", footprint="Resistor_SMD:R_0402_1005Metric")
        r_gl = Part("Device", "R", value="15R", footprint="Resistor_SMD:R_0402_1005Metric")
        # PR-A4-integrate amendment 5 BOM B-1a: AOTL66912 TO-263 → BSC014N06NS PDFN-8
        # Same Infineon part as Q1-Q4 protection FETs (JLC C113391).
        # 60V V_DS, 1.45mΩ R_DS(on) (3× lower than AOTL66912 4.5mΩ — better thermals),
        # 170A @T_C=100°C. 4× parallel handles 4ch × 100A peak with margin.
        # Pin map: G→4, S→1,2,3, D→5,6,7,8 (handled by fix_fet_netlist_drop.py).
        qh = Part("Device", "Q_NMOS", value="BSC014N06NS",
                  footprint="Package_DFN_QFN:W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm")
        ql = Part("Device", "Q_NMOS", value="BSC014N06NS",
                  footprint="Package_DFN_QFN:W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm")
        qh["D"] += vmotor
        qh["S"] += motor_net
        r_gh[1] += gh_net; r_gh[2] += qh["G"]
        ql["D"] += motor_net
        ql["S"] += shunt_top_net
        r_gl[1] += gl_net; r_gl[2] += ql["G"]

        # Phase 3-redo: gate clamps per FET (2 components each = 12/half-bridge × 3 = 36/ch)
        # 5.6V Zener cathode→gate + 10kΩ gate→source pull-down
        # Protects against gate-source overvoltage (Vgs_max=20V for AOTL66912; 5.6V clamp
        # gives wide margin) and ensures FET is OFF during gate-driver Hi-Z (power-up,
        # driver fault, kill-rail-active).
        for fet, gnd_ref, lbl in ((qh, motor_net, "HI"), (ql, shunt_top_net, "LO")):
            zd = Part("Device", "D_Zener", value="BZT52C5V6",
                      footprint="Diode_SMD:D_SOD-123",
                      description=f"Gate clamp 5.6V Zener {lbl} CH{cn}-{phase_label} (Vgs limit)")
            zd["K"] += fet["G"]; zd["A"] += gnd_ref
            r_pd = Part("Device", "R", value="10K",
                        footprint="Resistor_SMD:R_0402_1005Metric",
                        description=f"Gate pull-down 10K {lbl} CH{cn}-{phase_label}")
            r_pd[1] += fet["G"]; r_pd[2] += gnd_ref

        # Phase 3-redo: local bypass cap stack per FET pair (3 caps × 1 pair = 3 caps/half-bridge × 3 = 9/ch)
        # 100nF + 10nF + 1nF X7R 0402 from VMOTOR (drain) to GND, ≤5mm trace placement requirement.
        for cval in ("100nF", "10nF", "1nF"):
            cbp = Part("Device", "C", value=cval,
                       footprint="Capacitor_SMD:C_0402_1005Metric",
                       description=f"Local bypass {cval} VMOTOR CH{cn}-{phase_label}")
            cbp[1] += vmotor; cbp[2] += gnd

        # Phase 3-redo: phase TVS on motor output (1/phase × 3 = 3/ch)
        # SMBJ33A unidirectional 33V TVS at motor pad — clamps BLDC back-EMF spikes
        # during commutation. Vbr_min=36.7V > VMOTOR_max=25.2V; Vclamp_max=53.3V <
        # Vds_max=60V of FET. ≤3mm trace placement requirement. Use Device:D
        # (K/A pins) since KiCad's D_TVS is bidirectional (A1/A2) and SMBJ33A is uni.
        tvs_phase = Part("Device", "D", value="SMBJ33A",
                         footprint="Diode_SMD:D_SMA",
                         description=f"Phase TVS 33V uni CH{cn}-{phase_label}")
        tvs_phase["K"] += motor_net; tvs_phase["A"] += gnd

    half_bridge(gha, gla, motor_a, shunt_a_top, "A")
    half_bridge(ghb, glb, motor_b, shunt_b_top, "B")
    half_bridge(ghc, glc, motor_c, shunt_c_top, "C")

    # Current sense — 3× shunt + 3× INA186
    def current_sense(shunt_top_net, csa_out_net):
        rsh = Part("Device", "R", value="0.2mR",
                   footprint="Resistor_SMD:R_2512_6332Metric")
        rsh[1] += shunt_top_net; rsh[2] += gnd
        csa = Part("Connector_Generic", "Conn_01x06", value="INA186A3IDCKR",
                   footprint="Package_TO_SOT_SMD:SOT-363_SC-70-6")
        csa[1] += shunt_top_net
        csa[6] += gnd
        csa[2] += gnd
        csa[3] += gnd
        csa[4] += v3v3
        csa[5] += csa_out_net
        c_csa = Part("Device", "C", value="100nF",
                     footprint="Capacitor_SMD:C_0402_1005Metric")
        c_csa[1] += csa_out_net; c_csa[2] += gnd

    current_sense(shunt_a_top, csa_a_out)
    current_sense(shunt_b_top, csa_b_out)
    current_sense(shunt_c_top, csa_c_out)

    # BEMF dividers (22 kΩ / 3.3 kΩ, ratio 7.67)
    def bemf_divider(motor_net, bemf_node):
        r_top = Part("Device", "R", value="22K",
                     footprint="Resistor_SMD:R_0402_1005Metric")
        r_bot = Part("Device", "R", value="3.3K",
                     footprint="Resistor_SMD:R_0402_1005Metric")
        r_top[1] += motor_net; r_top[2] += bemf_node
        r_bot[1] += bemf_node; r_bot[2] += gnd
        c_bemf = Part("Device", "C", value="1nF",
                      footprint="Capacitor_SMD:C_0402_1005Metric")
        c_bemf[1] += bemf_node; c_bemf[2] += gnd

    bemf_divider(motor_a, bemf_a)
    bemf_divider(motor_b, bemf_b)
    bemf_divider(motor_c, bemf_c)

    # Channel-local bus cap 22µF
    c_local = Part("Device", "C", value="22uF",
                   footprint="Capacitor_SMD:C_0603_1608Metric")
    c_local[1] += v5; c_local[2] += gnd

    # Status LED — red 0603, GPIO-driven on PA15 (active-low: GPIO sinks)
    led_status = Part("Device", "LED", value="RED",
                      footprint="LED_SMD:LED_0603_1608Metric")
    r_led = Part("Device", "R", value="1K",
                 footprint="Resistor_SMD:R_0402_1005Metric")
    r_led[1] += v3v3
    r_led[2] += led_status["A"]
    led_status["K"] += led_gpio

    # ─────────────────────────────────────────────────────────────────────
    # Phase 3-redo: per-channel hardware protection subsystem
    # ─────────────────────────────────────────────────────────────────────
    # Three protection trip sources combine into a per-channel active-low
    # kill rail (KILL_RAIL_CH<n>_N). Trip sources:
    #   (a) Current-limit: CSA_MAX > 2.4V (= 120A at 20 mV/A) via LM393 comp A
    #   (b) OTP: NTC voltage < 0.3V (= 100°C with 10k NTC + 10k pull-up) via LM393 comp B
    #   (c) Global OV/UV: TPS3700 fault from main sheet (wire-OR into kill_bus)
    # Outputs are open-drain → wire-OR via single 10kΩ pull-up. Discrete 74LVC1G32
    # OR gate kept per master Phase 3-redo spec (combines I_TRIP + OTP_TRIP into
    # KILL_LOCAL before global wire-OR, to give us a single deterministic local
    # trip signal usable for the protection-status LED).
    # ─────────────────────────────────────────────────────────────────────

    # NTC sensor for both firmware (PA3 ADC) AND hardware OTP comparator
    # 10kΩ NTC (NCP18WF104J03RB, B25/100=4250K) + 10kΩ pull-up to 3V3.
    # At 100°C: NTC ≈ 1kΩ → V_PA3 = 3.3 × 1k/(10k+1k) = 0.30V.
    # At 25°C nominal: NTC = 10kΩ → V_PA3 = 1.65V.
    # ntc_node net name matches the anonymous Net created at mcu[9] earlier;
    # SKiDL auto-merges nets with the same name. Below we add the NTC sensor +
    # pull-up + comparator tap; mcu[9] connection is unchanged.
    ntc_node = Net(f"NTC_CH{cn}")
    r_ntc_pu = Part("Device", "R", value="10K",
                    footprint="Resistor_SMD:R_0402_1005Metric",
                    description=f"NTC pull-up 10K → +3V3 CH{cn}")
    r_ntc_pu[1] += v3v3; r_ntc_pu[2] += ntc_node
    rt_ntc = Part("Device", "Thermistor_NTC", value="10K_B4250",
                  footprint="Resistor_SMD:R_0402_1005Metric",
                  description=f"NTC 10kΩ B25/100=4250K (Murata NCP18WF104) CH{cn}")
    rt_ntc[1] += ntc_node; rt_ntc[2] += gnd

    # PR-centralize-vref Phase 2 (2026-05-23): TL431 + bias R + bulk bypass C
    # MOVED to main script (single central instance for all 4 channels). Phase 1
    # audit verified: 200µA/channel load, 4-ch shared = 800µA; hysteresis
    # (r_fb_i) injects at VREF_I_TRIP divider tap, NOT at VREF_2V5 → no
    # inter-channel coupling on the shared rail. See docs/PHASE4_ARCHITECTURE_REVIEW.md.
    # Per-channel: add 10nF local bypass at the divider/hysteresis injection
    # node for HF decoupling (impedance-to-ground at the comparator-input bypass).
    c_vref_local = Part("Device", "C", value="10nF",
                        footprint="Capacitor_SMD:C_0402_1005Metric",
                        description=f"VREF_2V5 local bypass CH{cn} (HF decoupling at divider tap)")
    c_vref_local[1] += vref_2v5; c_vref_local[2] += gnd

    # Derived reference for I_TRIP @ 2.4V (= 120A @ 20 mV/A from INA186)
    # Divider: 2.4 = 2.5 × (24k/(1k+24k)) → R_high=1k, R_low=24k from VREF_2V5 to GND.
    vref_i_trip = Net(f"VREF_I_TRIP_CH{cn}")  # 2.4V trip threshold
    r_vd_i_top = Part("Device", "R", value="1K",
                      footprint="Resistor_SMD:R_0402_1005Metric")
    r_vd_i_top[1] += vref_2v5; r_vd_i_top[2] += vref_i_trip
    r_vd_i_bot = Part("Device", "R", value="24K",
                      footprint="Resistor_SMD:R_0402_1005Metric")
    r_vd_i_bot[1] += vref_i_trip; r_vd_i_bot[2] += gnd

    # Derived reference for OTP @ 0.3V (= 100°C with 10k NTC + 10k pull-up)
    # Divider: 0.3 = 2.5 × (270/(2k+270)) → R_high=2k, R_low=270 from VREF_2V5 to GND.
    vref_otp = Net(f"VREF_OTP_CH{cn}")  # 0.3V trip threshold
    r_vd_otp_top = Part("Device", "R", value="22K",
                        footprint="Resistor_SMD:R_0402_1005Metric")
    r_vd_otp_top[1] += vref_2v5; r_vd_otp_top[2] += vref_otp
    r_vd_otp_bot = Part("Device", "R", value="3K",
                        footprint="Resistor_SMD:R_0402_1005Metric")
    r_vd_otp_bot[1] += vref_otp; r_vd_otp_bot[2] += gnd

    # CSA_MAX = diode-OR of the 3 CSA outputs (only 1 phase low-side conducts at a time
    # in BLDC trapezoidal commutation; max of 3 CSAs = active-phase current sense).
    # 3× BAT54 Schottky (Vf ≈ 0.3V at 1mA) + 100kΩ pull-down to GND.
    csa_max = Net(f"CSA_MAX_CH{cn}")
    for csa_signal in (csa_a_out, csa_b_out, csa_c_out):
        d_or = Part("Device", "D", value="BAT54",
                    footprint="Diode_SMD:D_SOD-323",
                    description=f"CSA diode-OR CH{cn}")
        d_or["A"] += csa_signal; d_or["K"] += csa_max
    r_csa_max_pd = Part("Device", "R", value="100K",
                        footprint="Resistor_SMD:R_0402_1005Metric",
                        description=f"CSA_MAX pull-down CH{cn}")
    r_csa_max_pd[1] += csa_max; r_csa_max_pd[2] += gnd

    # Dual comparator — LM393 (open-drain output, supply 3V3, ±0V to V_CC inputs).
    # Source: JLC C7955 (LM393DR, SOIC-8, Basic tier).
    # Comp A: I_TRIP — IN+ = vref_i_trip(2.4V), IN- = csa_max → OUT_A low when csa > 2.4V
    # Comp B: OTP   — IN+ = ntc_node, IN- = vref_otp(0.3V)   → OUT_B low when ntc < 0.3V
    # Both outputs open-drain, pulled up to 3V3 via 10kΩ; wire-OR combines them.
    i_trip_n = Net(f"I_TRIP_N_CH{cn}")     # active-low current trip
    otp_trip_n = Net(f"OTP_TRIP_N_CH{cn}") # active-low OTP trip
    u_cmp = Part("Comparator", "LM393", value="LM393",
                 footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    u_cmp[8] += v3v3  # V+
    u_cmp[4] += gnd   # V-
    # Comp A (pins 1=OUT, 2=IN-, 3=IN+)
    u_cmp[1] += i_trip_n
    u_cmp[2] += csa_max
    u_cmp[3] += vref_i_trip
    # Comp B (pins 7=OUT, 6=IN-, 5=IN+)
    u_cmp[7] += otp_trip_n
    u_cmp[6] += vref_otp
    u_cmp[5] += ntc_node
    c_cmp_bp = Part("Device", "C", value="100nF",
                    footprint="Capacitor_SMD:C_0402_1005Metric",
                    description=f"LM393 bypass CH{cn}")
    c_cmp_bp[1] += v3v3; c_cmp_bp[2] += gnd
    # Pull-ups for open-drain outputs (10kΩ each to 3V3)
    r_pu_i = Part("Device", "R", value="10K",
                  footprint="Resistor_SMD:R_0402_1005Metric")
    r_pu_i[1] += i_trip_n; r_pu_i[2] += v3v3
    r_pu_otp = Part("Device", "R", value="10K",
                    footprint="Resistor_SMD:R_0402_1005Metric")
    r_pu_otp[1] += otp_trip_n; r_pu_otp[2] += v3v3

    # Positive-feedback hysteresis on Comp A (current limit), R_fb = 1MΩ
    # When OUT_A = HI (3V3, untripped): vref_i_trip nudged up by I_fb · R_ext
    # When OUT_A = LO (0V, tripped):    vref_i_trip nudged down
    # Hysteresis on vref_i_trip ≈ 3.3V × (24k || 1k) / (24k || 1k + 1M)
    # = 3.3 × 0.96k / 1001k ≈ 3.2 mV at vref → reflected as ~3.2 mV at csa_max
    # That's ~0.16A hysteresis at 20 mV/A. To get ~10A (200 mV), R_fb must be lower.
    # Compromise: R_fb = 20k → 3.3 × 0.96 / 21k ≈ 150 mV ≈ 7.5A hysteresis. Acceptable.
    r_fb_i = Part("Device", "R", value="20K",
                  footprint="Resistor_SMD:R_0402_1005Metric",
                  description=f"I_TRIP hysteresis feedback CH{cn} (~7-10A hyst)")
    r_fb_i[1] += i_trip_n; r_fb_i[2] += vref_i_trip

    # 74LVC1G32 single OR gate — combines I_TRIP_N + OTP_TRIP_N into KILL_LOCAL_CH_N
    # Output is active-low channel trip. Source: JLC C432449 (Basic tier).
    # 74LVC1G32 OR: OUT = A | B. With active-low inputs, OUT = LOW only when both
    # I_TRIP_N AND OTP_TRIP_N are LOW (i.e., both tripped). That's wrong for OR-of-trips.
    # Use 74LVC1G08 AND instead: OUT = A & B. Active-low inputs → AND output is LOW
    # when ANY input is LOW. That's the OR-of-trips behavior we want.
    # Lock: 74LVC1G08 (single 2-input AND gate, SOT-353). JLC C432552 (Basic tier).
    kill_local_n = Net(f"KILL_LOCAL_N_CH{cn}")
    u_and = Part("74xGxx", "74LVC1G08", value="74LVC1G08",
                 footprint="Package_TO_SOT_SMD:SOT-353_SC-70-5")
    u_and[1] += i_trip_n      # A
    u_and[2] += otp_trip_n    # B
    u_and[3] += gnd           # GND
    u_and[4] += kill_local_n  # Y
    u_and[5] += v3v3          # VCC
    c_and_bp = Part("Device", "C", value="100nF",
                    footprint="Capacitor_SMD:C_0402_1005Metric",
                    description=f"74LVC1G08 bypass CH{cn}")
    c_and_bp[1] += v3v3; c_and_bp[2] += gnd

    # NOTE: hardware-driven protection-status LED is on the main sheet,
    # not per-channel (master Phase 3a spec). kill_local_n is exported so
    # the main sheet can drive its 4× hardware fault LEDs.

    # Global wire-OR: per-channel kill bus = wire-AND-active-low of:
    #   kill_local_n (this channel's local trip)
    #   global_ovuv_n (TPS3700 fault from main sheet)
    # → KILL_RAIL_CH<n>_N. Pull-up + bus is on the main sheet (one pull-up shared
    # by all 4 channels' kill_local_n + global_ovuv_n inputs).
    kill_rail_ch_n = Net(f"KILL_RAIL_N_CH{cn}")
    if kill_bus is not None:
        # kill_bus is the board-wide active-low protection bus. Wire-OR via
        # open-drain diodes is overkill since the LM393 outputs and 74LVC1G08
        # OAndd are already wired to kill_local_n (already open-drain / driven).
        # Per-channel kill_rail uses the 74LVC1G08 output directly + an additional
        # diode wire-OR with global_ovuv_n at this node.
        d_kill_global = Part("Device", "D", value="BAT54",
                             footprint="Diode_SMD:D_SOD-323",
                             description=f"Kill bus wire-OR diode (global→CH{cn})")
        if global_ovuv_n is not None:
            d_kill_global["K"] += global_ovuv_n
            d_kill_global["A"] += kill_rail_ch_n
        else:
            d_kill_global["K"] += kill_rail_ch_n
            d_kill_global["A"] += kill_rail_ch_n
        d_kill_local = Part("Device", "D", value="BAT54",
                            footprint="Diode_SMD:D_SOD-323",
                            description=f"Kill bus wire-OR diode (local→CH{cn})")
        d_kill_local["K"] += kill_local_n
        d_kill_local["A"] += kill_rail_ch_n
        r_kill_pu = Part("Device", "R", value="10K",
                         footprint="Resistor_SMD:R_0402_1005Metric",
                         description=f"Kill rail pull-up CH{cn}")
        r_kill_pu[1] += kill_rail_ch_n; r_kill_pu[2] += v3v3

    # Drive DRV8300 nSLEEP/EN (active-low) with kill_rail. When kill = LOW (any
    # trip active), DRV8300 enters sleep, all 6 FETs are gated OFF via internal
    # pull-down + external 10kΩ pull-down clamps installed earlier.
    # Phase 4 will swap Conn_01x24 stand-in for real DRV8300DRGER symbol; for now
    # use pin 8 of the connector as the nSLEEP/EN placeholder (currently unused).
    drv[8] += kill_rail_ch_n

    return (motor_a, motor_b, motor_c, kill_local_n, kill_rail_ch_n)


if __name__ == "__main__":
    vmotor = Net("+VMOTOR_TEST")
    v5 = Net("+5V_TEST")
    v3v3 = Net("+3V3_TEST")
    v3v3a = Net("+3V3A_TEST")
    gnd = Net("GND_TEST")
    dshot = Net("DSHOT1_TEST")
    tlm = Net("TLM_TEST")
    swdio = Net("SWDIO_CH1_TEST")
    swclk = Net("SWCLK_CH1_TEST")
    vref_2v5 = Net("VREF_2V5_TEST")
    ma, mb, mc, kln, krn = make_channel(1, vmotor, v5, v3v3, v3v3a, gnd, dshot, tlm,
                                         swdio, swclk, vref_2v5)
    print(f"Channel 1 motor nets: A={ma.name} B={mb.name} C={mc.name}")
    out = "/home/novatics64/escworker/pcb.ai/hardware/kicad/channel_skidl_test.net"
    generate_netlist(file_=out)
    print(f"Channel-1 standalone netlist: {out}")
    with open(out) as f:
        txt = f.read()
    print(f"  refs: {txt.count(chr(40) + 'ref ')}")
    print(f"  nets: {txt.count('(net (code ')}")
