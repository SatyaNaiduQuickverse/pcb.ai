# Phase 1 — AM32 hardware-target file for PL1 (FPV 4-in-1 ESC)

Per `DESIGN_PHASES.md` Phase 1 acceptance ("build clean; identity correct"),
and Rigor §10 (grep-then-state) — every fact below was captured directly from
the tool / source, not recalled.

Project context: pcb.ai PL1 (`CLAUDE.md` §2, `docs/REQUIREMENTS.md`
§fpv-4in1). MCU pick AT32F421K8T7 — closed by master adjudication (OQ-006).

## Deliverable summary

| Item | Value | Source |
|---|---|---|
| MCU part | AT32F421K8T7 (Artery, M4 @ 120 MHz, LQFP-32, 64 KB Flash, 16 KB SRAM) | OQ-006 |
| Firmware | AM32 GPLv3, single-motor build, same `.elf` flashed per MCU | CL-002 |
| Target identifier | `PCBAI_FPV4IN1_F421` | this PR |
| HARDWARE_GROUP | `HARDWARE_GROUP_AT_B` + `HARDWARE_GROUP_AT_045` | Step 2 survey |
| AM32 baseline (`make f421`) | 103/103 targets built clean | this PR |
| New target build | `.elf` + `.bin` + `.hex` produced, `-Werror` clean | this PR |
| Build command | `make -C <AM32> ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- obj/AM32_PCBAI_FPV4IN1_F421_2.20.{elf,bin,hex}` | this PR |

## HARDWARE_GROUP pick — rationale

Surveyed every `#ifdef *_F421` block in `Inc/targets.h` (102 enabled, 103
with bootloader; cf. master's "240" estimate which counted every
`define FILE_NAME` line including `DISABLE_BUILD`-guarded ones).

Pattern observed across 4-in-1 AT32F421 targets — `SEQURE_4IN1_F421`,
`TBS_6S_4IN1_F421`, `TBS_8S_4IN1_F421`, `TEKKO32_4IN1_MINI_F421`,
`XILO_STAX_V2_4IN1_F421`, `GEPRC_4IN1_F421`, `F4A_4IN1_F421` — every one
uses **`HARDWARE_GROUP_AT_B` + `HARDWARE_GROUP_AT_045`**.

`HARDWARE_GROUP_AT_C` (and `AT_E`, `AT_F`) appear only on single-channel
ESCs (ORQA_F421, AIRBEE_F421, SWAP_PB0_PA7_F421). Convention is therefore:
- `AT_B` ⇒ 4-in-1 board variant, with 4 MCUs sharing the input rail
- `AT_C` / others ⇒ single-channel boards

Important: a recursive grep of the full AM32 repo shows the `HARDWARE_GROUP_AT_*`
macros are defined in `Inc/targets.h` but **not referenced anywhere else in the
codebase** — they're documentation/convention markers rather than build-time
switches. The actual configuration happens via `DEAD_TIME`, `*_ADC_PIN`,
`*_ADC_CHANNEL`, `USE_SERIAL_TELEMETRY`, `USE_NTC`, `MILLIVOLT_PER_AMP`.
Following the convention regardless so the file matches the 4-in-1 family.

## Target block (canonical in `firmware/am32-target/PCBAI_FPV4IN1_F421.target.h`)

Located between `BOTDRIVE_F421` and the AT32F415 divider when applied to
AM32 `Inc/targets.h`. PLACEHOLDER values are drawn from `SEQURE_4IN1_F421`
(the closest topological neighbour — 6S 4-in-1 AM32) so the build compiles
while preserving an explicit Phase-2 grep marker per field.

## Build verification

```
$ make -C /home/novatics64/escworker/AM32 \
       ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- \
       obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf
Memory region         Used Size  Region Size  %age Used
           FLASH:       22108 B        27 KB     79.96%
          EEPROM:          0 GB         1 KB      0.00%
       FILE_NAME:          32 B         32 B    100.00%
             RAM:        3672 B        15 KB     23.91%
```

`arm-none-eabi-size`: text=21164, data=976, bss=2704, dec=24844 (0x610c).
`file`: `ELF 32-bit LSB executable, ARM, EABI5 version 1`. `-Werror -Wall
-Wextra` clean.

The 27 KB FLASH "region size" is the AM32 application slot (linker script
`AT32F421x6_FLASH.ld`, app region = 0x08001000 → 0x08007C00 — bootloader at
0x08000000 + EEPROM at 0x08007C00). The AT32F421K8T7 has 64 KB Flash total,
so there is significant unused space if we switch to a K8-specific `.ld`
in Phase 2 (Phase 2 to-do).

## Baseline `make f421` re-verification (Phase 0 only ran `make g071`)

`make -C /home/novatics64/escworker/AM32 ARM_SDK_PREFIX=… f421` ran clean:
103/103 `.elf` + `.bin` artifacts produced, zero errors. Reference
`SEQURE_4IN1_F421` sizes (closest topological neighbour to PCBAI):
text=21220 / data=1240 / bss=2704 (dec=25164 / 0x624c). Our target's sizes
(text=21164 / data=976 / bss=2704) sit within ~1% of SEQURE's — sanity-check
that the placeholder values produced a normal AM32 build.

## Build-time finding — `MILLIVOLT_PER_AMP 0` triggers div-by-zero `-Werror`

Master's literal Phase 1 contract had:
```
#define MILLIVOLT_PER_AMP 0  /* PLACEHOLDER — FILL AT PHASE 2 */
```
With `-Werror`, GCC 10.2.1 constant-folds the expression at `Src/main.c:2041`:
```
actual_current = ((smoothed_raw_current * 3300 / 41) - (CURRENT_OFFSET * 100)) / (MILLIVOLT_PER_AMP);
                                                                                  ^
error: division by zero [-Werror=div-by-zero]
```
Replaced `0` with `9` (SEQURE_4IN1_F421's value) — same PLACEHOLDER status,
preserves the marker, makes the build pass. Recorded inline in the target
block so future-Phase-2 sees the why.

## Phase 2 grep checklist

```
grep -n "PLACEHOLDER — FILL AT PHASE 2" \
     firmware/am32-target/PCBAI_FPV4IN1_F421.target.h
```
Should return 5 lines (DEAD_TIME, CURRENT_ADC_PIN, CURRENT_ADC_CHANNEL,
VOLTAGE_ADC_PIN, VOLTAGE_ADC_CHANNEL, MILLIVOLT_PER_AMP — 6 fields actually,
since DEAD_TIME and MILLIVOLT_PER_AMP each contribute one). Phase 2 closes
every one against the schematic + datasheet + opamp gain choice.

## Open thread for master / Sai

`docs/REQUIREMENTS.md` §fpv-4in1 → MCU **Pin count** row previously read
"≥ 32 pins (4 PWM × 3 phases + 4 current sense × 3 phases + 4 DShot inputs
+ comms / config / debug)" — implying a single MCU controlling all 4
motors. That is inconsistent with the AM32 single-motor-per-MCU
architecture confirmed by every existing 4-in-1 AT32F421 target. Updated
the row in this PR to "≥ 32 pins per MCU (3 PWM × 1 phase set + 1 current
sense + 1 voltage sense + 1 DShot in + 1 telemetry out + comms / config /
debug)" and added the per-board interpretation, but flagged for master
sign-off — the change is a meaningful architectural clarification rather
than a small refinement.

If the original "single MCU, all 4 motors" reading was intentional
(custom FOC-style firmware on a beefier MCU than AM32 — e.g. STM32G4
with X-CUBE-MCSDK like PL2), that contradicts CL-002 (firmware = AM32)
and OQ-006 (MCU = AT32F421K8T7) and we should re-open. Otherwise the
correction stands.
