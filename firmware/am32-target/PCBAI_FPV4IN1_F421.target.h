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
 * Remaining placeholders (close at later sub-phases):
 *   DEAD_TIME         — closes at 2c (depends on gate-driver dt_min)
 *   MILLIVOLT_PER_AMP — closes at 2b/2c (= shunt R[mΩ] × opamp gain)
 */
#ifdef PCBAI_FPV4IN1_F421
#define FIRMWARE_NAME "pcb.ai 4in1"
#define FILE_NAME "PCBAI_FPV4IN1_F421"
#define DEAD_TIME 60                            /* PLACEHOLDER — FILL AT PHASE 2c (gate-driver shoot-through window, ns) */
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
#define MILLIVOLT_PER_AMP 9                     /* PLACEHOLDER — FILL AT PHASE 2b/2c (= shunt R[mΩ] * opamp gain). 9 mirrors SEQURE_4IN1_F421; 0 would trigger -Werror=div-by-zero at main.c:2041 */
#endif
