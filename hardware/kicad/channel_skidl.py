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


def make_channel(ch_num, vmotor, v5, v3v3, v3v3a, gnd, dshot_in, tlm, swdio, swclk):
    """Instantiate one ESC channel. Returns (motor_a, motor_b, motor_c) nets."""
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
    mcu = Part("Connector_Generic", "Conn_01x32", value="AT32F421K8T7",
               footprint="Package_QFP:LQFP-32_7x7mm_P0.8mm")
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
    # Phase 3b-detail: 10kΩ pull-up on TLM (PB6) to +3V3.
    # AM32 source verification (serial_telemetry.c L27-34): PB6 is configured
    # PUSH-PULL + internal pull-up + half-duplex single-line. External pull-up
    # is NOT strictly required, but FPV reference designs add it for noise
    # immunity on the shared TX/RX line with FC UART. Pending master URGENT
    # adjudication 2026-05-22 on push-pull vs skip — worker recommended (a).
    r_tlm_pu = Part("Device", "R", value="10K",
                    footprint="Resistor_SMD:R_0402_1005Metric",
                    description=f"TLM pull-up to +3V3 CH{cn} (noise immunity for half-duplex)")
    r_tlm_pu[1] += tlm
    r_tlm_pu[2] += v3v3
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

    # Half-bridges with gate-drive damping
    def half_bridge(gh_net, gl_net, motor_net, shunt_top_net):
        r_gh = Part("Device", "R", value="15R", footprint="Resistor_SMD:R_0402_1005Metric")
        r_gl = Part("Device", "R", value="15R", footprint="Resistor_SMD:R_0402_1005Metric")
        qh = Part("Device", "Q_NMOS", value="AOTL66912",
                  footprint="Package_TO_SOT_SMD:TO-263-3_TabPin2")
        ql = Part("Device", "Q_NMOS", value="AOTL66912",
                  footprint="Package_TO_SOT_SMD:TO-263-3_TabPin2")
        qh["D"] += vmotor
        qh["S"] += motor_net
        r_gh[1] += gh_net; r_gh[2] += qh["G"]
        ql["D"] += motor_net
        ql["S"] += shunt_top_net
        r_gl[1] += gl_net; r_gl[2] += ql["G"]

    half_bridge(gha, gla, motor_a, shunt_a_top)
    half_bridge(ghb, glb, motor_b, shunt_b_top)
    half_bridge(ghc, glc, motor_c, shunt_c_top)

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

    return (motor_a, motor_b, motor_c)


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
    ma, mb, mc = make_channel(1, vmotor, v5, v3v3, v3v3a, gnd, dshot, tlm, swdio, swclk)
    print(f"Channel 1 motor nets: A={ma.name} B={mb.name} C={mc.name}")
    out = "/home/novatics64/escworker/pcb.ai/hardware/kicad/channel_skidl_test.net"
    generate_netlist(file_=out)
    print(f"Channel-1 standalone netlist: {out}")
    with open(out) as f:
        txt = f.read()
    print(f"  refs: {txt.count(chr(40) + 'ref ')}")
    print(f"  nets: {txt.count('(net (code ')}")
