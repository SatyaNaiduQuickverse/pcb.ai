# pcb.ai AM32 hardware-target

Files:
- `PCBAI_FPV4IN1_F421.target.h` — the AM32 hardware-target block for PL1 (FPV 4-in-1 ESC, AT32F421K8T7). Single-motor build, flashed to each of the 4 MCUs on the 4-in-1 board. Applied to `Inc/targets.h` in an AM32 clone.
- `PCBAI_FPV4IN1_F421.ntc_table.h` — the NTC lookup-table snippet (PLACEHOLDER values inherited from SEQURE_4IN1_F421). Applied to `Inc/ntc_tables.h` in an AM32 clone. Required because `USE_NTC` is enabled in our target.

## Why this lives here

AM32 (GPLv3, per `docs/OPEN_QUESTIONS.md` CL-002) sources are in
`github.com/am32-firmware/AM32`. Our hardware-target file is OUR contribution
under the copyleft; until Phase 2 locks the pin map and we open the upstream
PR, the canonical source is this directory in `pcb.ai`. Applied to a local
AM32 clone for the verified Phase 1 build.

## How to build (Phase 1 baseline, with PLACEHOLDER fields)

1. Clone AM32 alongside the pcb.ai working tree:
   ```
   gh repo clone am32-firmware/AM32 /home/novatics64/escworker/AM32
   ```
2. Insert the target block from `PCBAI_FPV4IN1_F421.target.h` into
   `<AM32-clone>/Inc/targets.h`, between the `BOTDRIVE_F421` `#endif` and the
   `/***** AT32F415 targets *****/` divider (around line 1850).
3. Insert the NTC table from `PCBAI_FPV4IN1_F421.ntc_table.h` into
   `<AM32-clone>/Inc/ntc_tables.h` after the `SEQURE_4IN1_F421` block (the
   table is required because `USE_NTC` is set).
4. Build with the system aarch64 ARM toolchain (AM32's bundled xpack is
   x86_64-only — see `docs/PHASE0_TOOLCHAIN.md` row #11):
   ```
   make -C /home/novatics64/escworker/AM32 \
        ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- \
        obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf \
        obj/AM32_PCBAI_FPV4IN1_F421_2.20.bin \
        obj/AM32_PCBAI_FPV4IN1_F421_2.20.hex
   ```
5. Artifacts land in `<AM32-clone>/obj/` — see `docs/PHASE2A_PIN_MAP.md` for
   the latest verified sizes (Phase 2a).

## Phase 2 to-do list (grep targets)

Phase 2a closed the four ADC PLACEHOLDERs (CURRENT/VOLTAGE/NTC pins +
channels). Remaining placeholders to close:

- `DEAD_TIME` — closes at **2c**. Depends on the TI DRV83xx pick
  (REQUIREMENTS.md §fpv-4in1 → Gate drivers).
- `MILLIVOLT_PER_AMP` — closes at **2b/2c**. = shunt R[mΩ] × opamp gain.
- NTC table values (`PCBAI_FPV4IN1_F421.ntc_table.h`) — closes at **2b/2c**
  once the thermistor + divider are picked. Currently SEQURE_4IN1_F421's
  table inherited as PLACEHOLDER.

Also at Phase 2: confirm the AT32F421 linker script (AM32 ships
`AT32F421x6_FLASH.ld` for the 32 KB-Flash variant; our K8 part has 64 KB —
either keep the conservative `.ld` or add a K8-specific `.ld`).
