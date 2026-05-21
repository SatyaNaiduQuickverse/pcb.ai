/* pcb.ai FPV 4-in-1 ESC (PL1) — AM32 hardware-target block.
 *
 * Per CL-002 (`docs/OPEN_QUESTIONS.md`): AM32 GPLv3 firmware, copyleft honored
 * by contributing this hardware-target file back to am32-firmware/AM32 once
 * the schematic locks every Phase-2 placeholder. For now this snippet lives
 * in pcb.ai as the canonical source; applied to a local AM32 clone for the
 * verified build.
 *
 * APPLY: insert this block into am32-firmware/AM32:Inc/targets.h, between the
 * `BOTDRIVE_F421` target and the `/*** AT32F415 targets ***\/` divider. The
 * f421makefile.mk `$(call get_targets,F421)` will auto-discover it.
 *
 * BUILD:
 *   make -C <AM32-clone> ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- \
 *        obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf
 *
 * ARCHITECTURE: AM32 is single-motor-per-MCU firmware. The 4-in-1 board hosts
 * 4 × AT32F421K8T7 (one MCU per motor); the same `.elf` is flashed to each.
 * Per-board comms (DShot, telemetry, configurator) daisy-chain through the FC
 * passthrough — standard AM32 4-in-1 pattern (matches SEQURE_4IN1_F421,
 * TBS_6S_4IN1_F421, etc.).
 *
 * HARDWARE_GROUP_AT_B — 4-in-1 topology convention (per existing AM32 4-in-1
 * F421 targets). HARDWARE_GROUP_AT_045 — AT32F421 chip-family marker (sets
 * the BEMF comparator mux to PA0 / PA4 / PA5 for phases A / B / C).
 *
 * PIN MAP — Phase 2a locked. See `docs/PHASE2A_PIN_MAP.md` for the full
 * 32-pin table with datasheet + AM32 source citations.
 * CURRENT_ADC: PA2 (ADC1_IN2) — alt-funcs TMR15_CH1/USART2_TX unused in AM32.
 * VOLTAGE_ADC: PA6 (ADC1_IN6) — alt-funcs TMR1_BRK/TMR3_CH1/SPI1_MISO unused.
 * NTC_ADC:     PA3 (ADC1_IN3) — alt-funcs TMR15_CH2/USART2_RX unused.
 *
 * Phase 2c closures (this PR):
 *   DEAD_TIME = 60 (= 500 ns at 120 MHz TMR1 clock, DTG[7:0] standard encoding)
 *   MILLIVOLT_PER_AMP = 20 (= 0.2 mΩ shunt × INA186A3 100 V/V gain)
 *   Gate driver: DRV8300DRGER (TI 100 V 3-phase, JLC C3655801) primary;
 *                FD6288Q (Fortior, JLC C328453) pin-compat footprint alternate.
 *   Shunt + CSA: see docs/PHASE2C_GATEDRIVER_CURRENTSENSE.md.
 *
 * No remaining placeholders. Full pin map + part stack locked.
 */
#ifdef PCBAI_FPV4IN1_F421
#define FIRMWARE_NAME "pcb.ai 4in1"
#define FILE_NAME "PCBAI_FPV4IN1_F421"
/* DEAD_TIME is a raw DTG register value for TMR1->brk.dtc (see peripherals.c:115).
 * At 120 MHz APB2 clock with default CKD=00, T_DTS = 1/120e6 = 8.33 ns. For raw
 * value N < 128 (standard 0xx encoding), dead time = N × T_DTS ns.
 * Phase 2c lock: N=60 → 60 × 8.33 = 500 ns dead time. This covers:
 *   AON6260 turn-off worst-case (t_d_off + t_f ≈ 92 ns max)
 *   + DRV8300DRGER t_PD asymmetry (max 180 ns − min 70 ns = 110 ns spread)
 *   + driver matching skew (±30 ns max)
 *   + 1.5× safety margin
 *   = ~280 ns minimum required; 500 ns gives ~80% headroom.
 * Also satisfies FD6288Q's asymmetric t_on=300 typ / t_off=100 typ (which the
 * driver's internal cross-conduction prevention enforces anyway).
 * NOTE: contract guess that "DEAD_TIME=80 ≈ 80 ns" is wrong — actual is 667 ns.
 */
#define DEAD_TIME 60
#define HARDWARE_GROUP_AT_B
#define HARDWARE_GROUP_AT_045
#define USE_SERIAL_TELEMETRY
#define CURRENT_ADC_PIN GPIO_PINS_2             /* PA2 — ADC1_IN2; Phase 2a lock */
#define CURRENT_ADC_CHANNEL ADC_CHANNEL_2       /* PA2 — Phase 2a lock */
#define VOLTAGE_ADC_PIN GPIO_PINS_6             /* PA6 — ADC1_IN6; Phase 2a lock */
#define VOLTAGE_ADC_CHANNEL ADC_CHANNEL_6       /* PA6 — Phase 2a lock */
#define USE_NTC
#define NTC_ADC_PIN GPIO_PINS_3                 /* PA3 — ADC1_IN3; Phase 2a lock */
#define NTC_ADC_CHANNEL ADC_CHANNEL_3           /* PA3 — Phase 2a lock */
/* MILLIVOLT_PER_AMP = shunt R[mΩ] × CSA_gain × 1000 — wait the units here:
 *   shunt_drop_mV = I[A] × shunt[mΩ]
 *   CSA_output_mV = shunt_drop_mV × CSA_gain
 *   ⇒ CSA_output_mV / I = shunt[mΩ] × CSA_gain  = MILLIVOLT_PER_AMP
 * Phase 2c lock: 0.2 mΩ × 100 V/V gain (INA186A3IDCKR) = 20 mV/A.
 * Sanity check: 70 A peak × 20 mV/A = 1.4 V at ADC, 42 % of AT32F421 3.3 V
 * ADC range — comfortable headroom + noise floor.
 */
#define MILLIVOLT_PER_AMP 20
#endif
