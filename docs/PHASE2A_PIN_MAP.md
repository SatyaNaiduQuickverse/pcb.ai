# Phase 2a — Pin map for PL1 FPV 4-in-1 ESC (AT32F421K8T7 / LQFP-32)

Per Rigor §10 (grep-then-state): every claim below cites either the Artery
datasheet `DS_AT32F421_V2.02_EN.pdf` (downloaded fresh 2026-05-22 from
`https://www.arterychip.com/download/DS/DS_AT32F421_V2.02_EN.pdf`) or the
AM32 source at `am32-firmware/AM32` (HEAD as of Phase 1 baseline). No pin
claim is from memory.

References used throughout:
- **DS** = AT32F421 Series Datasheet v2.02, 2023-10-17 — LQFP-32 pinout
  (Figure 3, p.20), Table 5 pin definitions / alt-functions (pp.22-24),
  Table 3 bootloader pins (p.14).
- **PCB-AT-B** = `Inc/targets.h:4516-4549` (`HARDWARE_GROUP_AT_B`) — fixes
  the TMR1 PWM and DShot input pin assignments.
- **PCB-AT-045** = `Inc/targets.h:4728-4732` (`HARDWARE_GROUP_AT_045`) —
  fixes the BEMF comparator multiplexed inputs.
- **AM32-PERIPH** = `Mcu/f421/Src/peripherals.c` — TMR1 init, comparator
  pin analog config.
- **AM32-TELE** = `Mcu/f421/Src/serial_telemetry.c` — UART telemetry pin
  config.
- **AM32-ADC** = `Mcu/f421/Src/ADC.c` — ADC pin analog config.

Architecture reminder (per `docs/REQUIREMENTS.md` §fpv-4in1 → MCU): AM32 is
single-motor-per-MCU. The board hosts 4 × AT32F421K8T7; each instance of
this pin map applies to ONE of the four MCUs. Each MCU drives one motor's
three-phase half-bridge.

## Pin-map summary by subsystem

| Subsystem | Pins (LQFP-32 numbering) | Source |
|---|---|---|
| Power / ground | 1 (VDD), 5 (VDDA/VREF+), 16 (VSS), 17 (VDD), 32 (VSS) | DS Fig 3 p.20 |
| Reset / boot / debug | 4 (NRST), 31 (BOOT0), 23 (PA13/SWDIO), 24 (PA14/SWCLK) | DS Fig 3 p.20, DS Table 5 footnote (5) |
| HEXT (high-speed external osc) | 2 (PF0/HEXT_IN), 3 (PF1/HEXT_OUT) — **unused, HICK 48 MHz used** | DS p.20; AM32-PERIPH:55-58 (`CRM_CLOCK_SOURCE_HICK`) |
| 3-phase PWM (TMR1) — high side | 18 (PA8), 19 (PA9), 20 (PA10) | PCB-AT-B 4545/4538/4531 |
| 3-phase PWM (TMR1) — low side (complementary, dead-time inserted) | 13 (PA7), 14 (PB0), 15 (PB1) | PCB-AT-B 4542/4535/4528 |
| BEMF zero-crossing (CMP1 multiplexed) | 6 (PA0), 10 (PA4), 11 (PA5) + 7 (PA1) reference | PCB-AT-045 4729-4731; AM32-PERIPH:77-78 |
| DShot input (TMR3_CH1) | 27 (PB4) | PCB-AT-B 4520-4522 |
| Serial telemetry (USART1_TX, half-duplex single-line) | 29 (PB6) | AM32-TELE:31-34, 59 |
| ADC — current sense | 8 (PA2) → ADC1_IN2 | Master directive 2026-05-22; DS Table 5 row PA2 |
| ADC — bus voltage sense | 12 (PA6) → ADC1_IN6 | Master directive 2026-05-22; DS Table 5 row PA6 |
| ADC — external NTC | 9 (PA3) → ADC1_IN3 | Master directive 2026-05-22; DS Table 5 row PA3 |
| ADC — internal temperature | (no pin) → ADC1_IN16 | DS §2.15.1 p.19; AM32-ADC:95, 103 |
| Free / unassigned | 21 (PA11), 22 (PA12), 25 (PA15), 26 (PB3), 28 (PB5), 30 (PB7) | DS Table 5 + AM32 source (no references) |

## Full 32-pin table

Pin direction: **I** = input, **O** = output, **A** = analog, **S** = supply, **B** = boot.

| Pin | Name | Dir | Our use | Net | Alt-func conflict check | Source |
|---|---|---|---|---|---|---|
| 1 | VDD | S | MCU digital power (3.3 V) | 3V3 | n/a | DS Fig 3 p.20 |
| 2 | PF0 / HEXT_IN | I/O | NC (HEXT not used, HICK 48 MHz used) | NC | I2C1_SDA alt available if needed later | DS Fig 3 p.20, DS Table 5 row PF0/HEXT_IN p.22; AM32-PERIPH:55-58 |
| 3 | PF1 / HEXT_OUT | I/O | NC | NC | I2C1_SCL alt available | DS p.20, Table 5 row PF1/HEXT_OUT |
| 4 | NRST | I/O | Reset input | nRST | n/a (dedicated reset, weak pull-up internal — DS Table 5 footnote on R) | DS Fig 3 p.20 |
| 5 | VDDA / VREF+ | S | ADC + CMP analog supply (= 3.3 V) | 3V3_A | DS §2.4 p.12: VDDA must equal VDD. LQFP-32 has no separate VSSA pin (bonded to VSS internally per Fig 3) | DS Fig 3 p.20, DS §2.4 |
| 6 | PA0 | A | BEMF Phase A (CMP1_INM6 multiplexed) | BEMF_A | TMR1_EXT/USART2_CTS/I2C2_SCL/CMP1_OUT/ADC1_IN0/CMP1_INP2/WKUP1 — none used | PCB-AT-045:4729 `PHASE_A_COMP=0x400000E5` decoded to PA0; DS Table 5 row PA0 |
| 7 | PA1 | A | CMP1 reference / +input (CMP1_INP1) | CMP_REF | TMR15_CH1C/USART2_RTS/I2C2_SDA/EVENTOUT/ADC1_IN1 — none used | AM32-PERIPH:77 `gpio_mode_QUICK(GPIOA, ..., GPIO_PINS_1)` set as ANALOG; DS Table 5 row PA1 |
| 8 | PA2 | A | **CURRENT_ADC (ADC1_IN2)** | ISENSE | TMR15_CH1/USART2_TX/CMP1_INM7 — none used (AM32 uses USART1 not USART2; TMR15 unused) | Master directive 2026-05-22; AM32-ADC:49 via CURRENT_ADC_PIN; DS Table 5 row PA2 |
| 9 | PA3 | A | **NTC_ADC (ADC1_IN3)** — external NTC thermistor | NTC | TMR15_CH2/USART2_RX/I2S2_MCK — none used | Master directive 2026-05-22; AM32-ADC:53 via NTC_ADC_PIN (under `USE_NTC`); DS Table 5 row PA3 |
| 10 | PA4 | A | BEMF Phase B (CMP1_INM4 multiplexed) | BEMF_B | TMR14_CH1/USART2_CK/SPI1_CS/I2S1_WS/ADC1_IN4 — none used | PCB-AT-045:4730 `PHASE_B_COMP=0x400000C5` decoded to PA4; DS Table 5 row PA4 |
| 11 | PA5 | A | BEMF Phase C (CMP1_INM5/INP0 multiplexed) | BEMF_C | SPI1_SCK/I2S1_CK/ADC1_IN5 — none used | PCB-AT-045:4731 `PHASE_C_COMP=0x400000D5` decoded to PA5; AM32-PERIPH:78 set ANALOG; DS Table 5 row PA5 |
| 12 | PA6 | A | **VOLTAGE_ADC (ADC1_IN6)** — bus voltage divider | VBAT_SENSE | TMR1_BRK/TMR3_CH1/TMR16_CH1/SPI1_MISO/I2S1_MCK/I2S2_MCK/CMP1_OUT/EVENTOUT — TMR1_BRK unused (no `tmr_brk_*` calls in AM32-PERIPH); TMR3_CH1 used on PB4 not PA6; no SPI/I2S/TMR16 output configured | Master directive 2026-05-22; AM32-ADC:51 `VOLTAGE_ADC_PIN`; DS Table 5 row PA6 |
| 13 | PA7 | I/O (mux) | PHASE_C low side (TMR1_CH1C, complementary) | PWM_C_LOW | TMR3_CH2/TMR14_CH1/TMR17_CH1/SPI1_MOSI/I2S1_SD/EVENTOUT/ADC1_IN7 — none used | PCB-AT-B:4542-4544 `PHASE_C_GPIO_LOW=GPIO_PINS_7, PORT_LOW=GPIOA`; AM32-PERIPH:129-130 `gpio_pin_mux_config(..., GPIO_MUX_2)`; DS Table 5 row PA7 lists TMR1_CH1C |
| 14 | PB0 | I/O (mux) | PHASE_B low side (TMR1_CH2C, complementary) | PWM_B_LOW | TMR3_CH3/USART2_RX/I2S1_MCK/EVENTOUT/ADC1_IN8 — none used | PCB-AT-B:4535-4537 `PHASE_B_GPIO_LOW=GPIO_PINS_0, PORT_LOW=GPIOB`; AM32-PERIPH MUX_2; DS Table 5 row PB0 lists TMR1_CH2C |
| 15 | PB1 | I/O (mux) | PHASE_A low side (TMR1_CH3C, complementary) | PWM_A_LOW | TMR3_CH4/TMR14_CH1/SPI2_SCK/I2S2_CK/ADC1_IN9 — none used | PCB-AT-B:4528-4530 `PHASE_A_GPIO_LOW=GPIO_PINS_1, PORT_LOW=GPIOB`; MUX_2; DS Table 5 row PB1 lists TMR1_CH3C |
| 16 | VSS | S | Digital ground | GND | n/a | DS Fig 3 p.20 |
| 17 | VDD | S | MCU digital power (3.3 V) — second VDD pin | 3V3 | n/a | DS Fig 3 p.20 |
| 18 | PA8 | I/O (mux) | PHASE_C high side (TMR1_CH1) | PWM_C_HIGH | USART1_CK/USART2_TX/I2C2_SCL/CLKOUT/EVENTOUT — none used | PCB-AT-B:4545-4547 `PHASE_C_GPIO_HIGH=GPIO_PINS_8, PORT_HIGH=GPIOA`; MUX_2; DS Table 5 row PA8 lists TMR1_CH1 |
| 19 | PA9 | I/O (mux) | PHASE_B high side (TMR1_CH2) | PWM_B_HIGH | TMR15_BRK/USART1_TX/I2C1_SCL/I2C2_SMBA/CLKOUT — USART1_TX is the bootloader pin (DS Table 3 p.14) but AM32 uses PB6 for runtime telemetry so PA9 stays clean for TMR1_CH2 in normal operation; bootloader entry is via the BOOT0 pin so this is benign | PCB-AT-B:4538-4540 `PHASE_B_GPIO_HIGH=GPIO_PINS_9, PORT_HIGH=GPIOA`; MUX_2; DS Table 5 row PA9 lists TMR1_CH2 |
| 20 | PA10 | I/O (mux) | PHASE_A high side (TMR1_CH3) | PWM_A_HIGH | TMR17_BRK/USART1_RX/I2C1_SDA — USART1_RX is the bootloader pin but runtime telemetry RX is on PB6 half-duplex; benign | PCB-AT-B:4531-4533 `PHASE_A_GPIO_HIGH=GPIO_PINS_10, PORT_HIGH=GPIOA`; MUX_2; DS Table 5 row PA10 lists TMR1_CH3 |
| 21 | PA11 | I/O | NC (free) | NC | TMR1_CH4/USART1_CTS/I2C1_SMBA/I2C2_SCL/CMP1_OUT/EVENTOUT all available if needed | DS Table 5 row PA11; no AM32 reference |
| 22 | PA12 | I/O | NC (free) | NC | TMR1_EXT/USART1_RTS/I2C2_SDA/EVENTOUT available | DS Table 5 row PA12; no AM32 reference |
| 23 | PA13 (SWDIO) | I/O | SWD data | SWDIO | After reset configured as SWDIO with internal pull-up | DS Table 5 footnote (5) p.24 |
| 24 | PA14 (SWCLK) | I/O | SWD clock | SWCLK | After reset configured as SWCLK with internal pull-down | DS Table 5 footnote (5) p.24 |
| 25 | PA15 | I/O | NC (free) | NC | USART2_RX/SPI1_CS/I2S1_WS/SPI2_CS/I2S2_WS/EVENTOUT available | DS Table 5 row PA15 |
| 26 | PB3 | I/O | NC (free) | NC | SPI1_SCK/I2S1_CK/SPI2_SCK/I2S2_CK/EVENTOUT available | DS Table 5 row PB3 |
| 27 | PB4 | I/O (mux) | DShot input (TMR3_CH1) | DSHOT_IN | TMR17_BRK/SPI1_MISO/SPI2_MISO/I2C2_SDA/EVENTOUT — none used | PCB-AT-B:4520-4523 `INPUT_PIN=GPIO_PINS_4, PORT=GPIOB, IC_TIMER_REGISTER=TMR3`; AM32-PERIPH:212-213 `gpio_pin_mux_config(..., GPIO_MUX_1)`; DS Table 5 row PB4 lists TMR3_CH1 |
| 28 | PB5 | I/O | NC (free) | NC | TMR3_CH2/TMR16_BRK/SPI/I2C1_SMBA/WKUP6 available | DS Table 5 row PB5 |
| 29 | PB6 | I/O (mux) | USART1_TX (half-duplex single-line telemetry) | TELEM | TMR16_CH1C/I2S1_MCK/I2C1_SCL available; runtime selection is USART1_TX (MUX_0) | AM32-TELE:31-34 `gpio_pins=GPIO_PINS_6, GPIOB, MUX_0`; AM32-TELE:59 `usart_single_line_halfduplex_select(USART1, TRUE)`; DS Table 5 row PB6 |
| 30 | PB7 | I/O | NC (free) | NC | TMR17_CH1C/USART1_RX/I2C1_SDA available | DS Table 5 row PB7 |
| 31 | BOOT0 | B | Boot mode selection | BOOT0 | Tied to GND via 10 kΩ pull-down for "boot from user Flash" (DS §2.5); leave a test point so BLHeli-passthrough flashing can pull high if needed | DS Fig 3 p.20; DS §2.5 boot modes |
| 32 | VSS | S | Digital ground | GND | n/a | DS Fig 3 p.20 |

## Subsystem cross-checks (Playbook §Known traps T6)

**T6 — alt-function conflict check:** every pin marked **A** (analog ADC), **I/O (mux)** (alt-function), or assigned-net was checked against DS Table 5's full alt-function list for that pin. The "Alt-func conflict check" column above enumerates the alts and explicitly flags whether AM32 uses any of them.

Two pins (PA9, PA10) carry both their AM32 runtime alt-function (TMR1_CH2/CH3) and the bootloader's USART1_TX/RX assignment (DS Table 3 p.14). This is **benign** because:
- The bootloader is entered only when BOOT0 is high at reset (DS §2.5).
- During normal operation BOOT0 is tied to GND, the boot ROM is not executed, and PA9/PA10 are reassigned to TMR1_CH2/CH3 by AM32's `peripherals.c`.
- BLHeli-passthrough firmware update happens over the runtime USART1 (PB6 half-duplex), not the bootloader.

The board should still expose BOOT0 as a test point per `REQUIREMENTS.md` §Protection (factory recovery path), but no co-use conflict exists at runtime.

## TMR1 channel ↔ phase mapping (non-obvious)

AM32's f421 build maps phases to TMR1 channels in **inverted order** relative to the conventional A→CH1, B→CH2, C→CH3 expectation:

| Logical phase | TMR1 main channel | High-side pin (CHx) | Low-side pin (CHxC, complementary) |
|---|---|---|---|
| Phase A | TMR1_CH3 | PA10 | PB1 |
| Phase B | TMR1_CH2 | PA9 | PB0 |
| Phase C | TMR1_CH1 | PA8 | PA7 |

Source: cross-referencing PCB-AT-B (`PHASE_*_GPIO_HIGH/LOW` definitions, lines 4528-4547) against DS Table 5's TMR1 alt-function column. The naming is internal to AM32 and consistent throughout the commutation tables (`Mcu/f421/Src/phaseouts.c`); it does not affect the board design — Phase A/B/C nets just connect to PA10+PB1, PA9+PB0, PA8+PA7 respectively.

Note: a code comment in `peripherals.c:119` reads "configure PA8/PA9/PA10(TIMER0/CH0/CH1/CH2) as alternate function" but that comment is **stale** — the surrounding code actually configures `PHASE_*_GPIO_LOW` which are PB1/PB0/PA7. The HARDWARE_GROUP_AT_B definitions in `targets.h` are the authoritative source.

## Power scheme (board-level requirements derived from DS Figure 8)

Per DS Figure 8 (Power supply scheme, p.26), the AT32F421 needs these decoupling components per MCU:

| Net | Pin(s) | Capacitor stack |
|---|---|---|
| VDD | 1, 17 | 2 × 100 nF (one per pin), placed within ~3 mm |
| VDDA | 5 | 100 nF + 1 µF, ferrite-bead-filtered from VDD (analog isolation) |
| Power-on reset | NRST (pin 4) | 100 nF to GND for debounce; internal weak pull-up exists, but external 10 kΩ pull-up recommended for noise immunity |

LQFP-32 specifics:
- No separate VSSA pin — bonded to VSS internally (DS Fig 3 p.20).
- VDD pins are diagonal (1 and 17), VSS pins are diagonal (16 and 32) — short ground return loops for both VDD pairs.

Per-board: ×4 sets of these decoupling components (one per MCU). The shared input rail powers a single 3.3 V LDO (or a buck) which then fans out to all 4 MCUs' VDD/VDDA — the LDO/buck pick lands at Phase 2d (Bus caps + BEC).

## Build verification (after Phase 2a edits)

```
$ make -C /home/novatics64/escworker/AM32 \
       ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- \
       obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf
Memory region         Used Size  Region Size  %age Used
           FLASH:       22408 B        27 KB     81.05%
          EEPROM:          0 GB         1 KB      0.00%
       FILE_NAME:          32 B         32 B    100.00%
             RAM:        3936 B        15 KB     25.62%
```

`arm-none-eabi-size`: text=21200, data=1240, bss=2704, dec=25144 (0x6238).
`-Werror -Wall -Wextra` clean. Delta vs Phase 1 baseline (text=21164,
data=976, bss=2704): +36 B text (NTC code newly enabled by `USE_NTC`),
+264 B data (the `NTC_table[65]` itself — note that AM32 declares the table
as non-`const int`, so it lives in RAM/data rather than rodata; this is a
quirk of AM32, not a choice we made).

## Phase 2a deliverable checklist (against contract pass criteria)

- [x] Every AT32F421K8T7 pin in this table (32/32), source cited per row.
- [x] 4 ADC PLACEHOLDERs closed in `PCBAI_FPV4IN1_F421.target.h` (CURRENT_ADC_PIN/CHANNEL, VOLTAGE_ADC_PIN/CHANNEL, plus NTC_ADC_PIN/CHANNEL added per master's call).
- [x] `DEAD_TIME` + `MILLIVOLT_PER_AMP` still PLACEHOLDER (close at 2c and 2b/2c respectively).
- [x] No T6 pin-budget conflicts. PA9/PA10 bootloader-vs-runtime overlap is benign and documented.
- [x] Build clean. `-Werror -Wall -Wextra`; .elf + .bin + .hex produced.
- [x] One PR.

## Items to revisit at later sub-phases

| Item | Sub-phase | Why |
|---|---|---|
| TI DRV83xx pick → `DEAD_TIME` final value | 2c | DRV part defines `t_dead_min` |
| Shunt R + opamp gain → `MILLIVOLT_PER_AMP` final | 2b → 2c | 2b picks MOSFET, defining current rating; 2c picks gate driver / current-sense topology |
| NTC thermistor + divider → `NTC_table` regeneration | 2b/2c | If we change the thermistor part or divider ratio from SEQURE's |
| Boot0 test-pad / pull-down resistor | 2e | Connectors + protection sub-phase |
| AT32F421 K8 linker script (vs ships-`x6` 32 KB script) | optional, post-2 | Currently we fit in 27 KB; only needed if we exceed |
| Pin assignments for the 6 free pins (PA11, PA12, PA15, PB3, PB5, PB7) | as needed | Reserved for debug-LED / config jumper / I²C bus / etc. — claim only as a real need surfaces (R4) |
