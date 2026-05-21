/* pcb.ai FPV 4-in-1 ESC — AM32 NTC lookup table snippet (Inc/ntc_tables.h).
 *
 * APPLY: insert into am32-firmware/AM32:Inc/ntc_tables.h, anywhere inside the
 * outer `#ifdef USE_NTC` block (place it after the SEQURE_4IN1_F421 block
 * for the cleanest diff).
 *
 * This table is consumed by Mcu/f421/Src/ADC.c:getNTCDegrees() — a 65-entry
 * lookup keyed off the upper 6 bits of the 12-bit ADC reading on NTC_ADC_PIN
 * (PA3 / ADC1_IN3 per the Phase 2a pin map).
 *
 * The values below are inherited from SEQURE_4IN1_F421 as a PLACEHOLDER. The
 * SEQURE topology is a 10 kΩ NTC (B-constant ~3950) with a half-divider to
 * VDD (3.3 V), which is a defensible default for the same FPV-4in1 segment.
 * Phase 2b/2c either confirms the same part choice (table stays) or replaces
 * it (re-characterize and regenerate). The B-constant + divider ratio define
 * the table; changing either invalidates it. Grep for "PLACEHOLDER — FILL AT
 * PHASE 2b/2c" before flashing real hardware.
 */
#ifdef PCBAI_FPV4IN1_F421
int NTC_table[65] = {
  400, 332, 264, 230, 208, 192, 180, 170, 161,
  154, 147, 141, 136, 131, 127, 122, 119, 115,
  111, 108, 105, 102, 99, 96, 94, 91, 88, 86,
  84, 81, 79, 77, 74, 72, 70, 68, 66, 63, 61,
  59, 57, 55, 53, 50, 48, 46, 44, 41, 39, 37,
  34, 32, 29, 26, 23, 20, 16, 13, 9, 4, -1,
  -8, -16, -29, -42
};
#endif
