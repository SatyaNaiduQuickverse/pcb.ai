# Phase 4-place-connectors — Subsystem S6 placement + DShot SI + BAT_V + S1/S2/S3 pair-wise

**Sub-phase 4 of `docs/PHASE4_SUBSYSTEMS.md` §S6.**
**Branch**: `phase4-place-connectors/subsystem-s6`.
**Master directive**: Task #55 dispatch 2026-05-22 (S6 reordered before S5 — tier-2 low-EMC anchor before introducing BEC tier-3 switching noise).

## What's placed (8 components; S1+S2+S3 preserved)

| Ref | Value | Footprint | Layer | Position (x, y) mm | Notes |
|---|---|---|---|---|---|
| J12 | BM06B-SRSS-TB | `Connector_JST:JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal` | F.Cu | (15, 80) | AUX 6-pin (Hall V_OUT + NTC + AUX_GPIO ×2 + V3V3 + GND) |
| J14 | SM08B-SRSS-TB | `Connector_JST:JST_SH_SM08B-SRSS-TB_1x08-1MP_P1.00mm_Horizontal` | F.Cu | (50, 80) | FC 8-pin (DShot×4 + TLM + VBAT_SENSE + CURR + GND) |
| J15 | USBLC6-2SC6 | `SOT-23-6` | F.Cu | (40, 75) | ESD array — DShot ch1 + ch2 |
| J16 | USBLC6-2SC6 | `SOT-23-6` | F.Cu | (60, 75) | ESD array — DShot ch3 + ch4 |
| J17 | USBLC6-2SC6 | `SOT-23-6` | F.Cu | (75, 75) | ESD array — TLM + spare |
| R36 | 100K | R_0402_1005Metric | F.Cu | (47, 76) | VBAT_SENSE divider top |
| R37 | 14K | R_0402_1005Metric | F.Cu | (47, 74) | VBAT_SENSE divider bottom (8.143:1 ratio) |
| C49 | 100nF | C_0402_1005Metric | F.Cu | (45, 74) | VBAT_SENSE filter cap (130 Hz cutoff) |

**Honest spec deviation flag**: master's contract estimated "10-15 components (... 4× protection-status LEDs)". The netlist (Phase 3a SKiDL) does NOT contain 4 per-channel kill LEDs — those are part of S4 channel template (1 LED per channel inside each MCU + protection cluster). S6 has only 8 components.

**S1+S2+S3 components** preserved at PR #32 + PR #34 + PR #35 (stage-3 amended) positions.

## I/O contract (per spec §S6)

| Direction | Net | Source / Sink |
|---|---|---|
| Input | DShot_CH1-4 | J14 pin 5-8 → J15/J16 ESD shunt → MCU GPIO in each S4 channel |
| Input | TLM | J14 pin 4 → J17 ESD shunt → MCU UART TX (telemetry shared bus) |
| Input | EXT_TEMP_NTC | J12 pin 4 → S5 NTC input |
| Input | BUS_CURR_HALL_OUT | S3 Hall divider (R31/R32/C44) → J12 pin 3 (AUX) |
| Output | VBAT_SENSE_OUT | BATT net → R36/R37/C49 divider → J14 pin 2 |
| Power | +V3V3 → J12 pin 2 | (V3V3 from S5 BEC — TBD) |
| Power | GND → J14 pin 1, J12 pin 1 | |

## Verification

- ✓ `verify_placement.py` bbox audit:
  - S1-internal: 0
  - S2-internal: 0
  - S3-internal: 0
  - S6-internal: 0
  - S1↔S2: 0, S1↔S3: 0, S1↔S6: 0
  - S2↔S3: 0, S2↔S6: 0
  - S3↔S6: 0
- ✓ Mount holes H3/H4 cleared (S6 components confined to x=10..90; H3 at (5,80) and H4 at (95,80) have ≥3mm clearance)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ Only S6 components placed (8); S1+S2+S3 preserved
- ✓ 551 footprints remain at kinet2pcb-default (placed in subsequent S4/S5 sub-phase PRs)

## 3D renders

- [`docs/renders/phase4_place_connectors/top.png`](renders/phase4_place_connectors/top.png) (F.Cu — top edge connectors + ESD chips + VBAT divider visible at Y=72-80)
- [`docs/renders/phase4_place_connectors/bottom.png`](renders/phase4_place_connectors/bottom.png) (B.Cu — no S6 components on bottom)

## Sim verdicts (5 sims per master spec, datasheet-anchored)

### Sim 1 — DShot 600 signal integrity (ngspice + LC ladder)

| Item | Value |
|---|---|
| Method | DShot 600 pulse (625 ns @ 3.3V) drives 50mm PCB microstrip modelled as 5-section LC ladder (L=3.2 nH + C=0.8 pF per section). Receiver = USBLC6 ESD shunt 25 pF + MCU GPIO C_in 5 pF. |
| Source | `sims/phase4_place_connectors/dshot_signal_integrity.cir` + `dshot_analyze.py` |
| **Rise time (10-90%)** | **7.8 ns** |
| **Fall time** | < 10 ns |
| **Overshoot** | 0 mV |
| **Ringing (200 ns post-edge)** | **247 mV pk-pk (7.5 %)** |
| Spec (Betaflight DShot 600) | t_rise/fall ≤ 100 ns acceptable; ringing ≤ 10 % |
| **Verdict** | **PASS ✓** (rise 12.8× under spec; ringing margin 2.5 percentage points) |

### Sim 2 — BAT_V divider accuracy

| Item | Value |
|---|---|
| Method | R36 (100K ±1%) / R37 (14K ±1%) = 8.143:1 ratio. Sweep ±1% corners, compute V_SENSE error vs nominal at V_BATT = 18 / 25.2 / 30 V. |
| Source | `sims/phase4_place_connectors/batv_divider.py` |
| Nominal V_SENSE @ V_BATT=25.2 V | 3.0947 V (fits 3.3V ADC ref with 6.5% headroom) |
| **Worst-case corner error** | **±1.77 %** (R_top hi + R_bot lo or reverse) |
| Spec | ±5% (FC firmware tolerance) |
| **Verdict** | **PASS ✓** (margin 3.23 percentage points; FC per-board cal eliminates most systematic error) |
| Filter cutoff | C49 100nF × R_par 12.28 kΩ → f_3dB = 130 Hz (PWM ripple 30 kHz attenuated 231×) |

**ADC saturation honest flag**: At V_BATT = 30 V (above OVP trip 27 V), V_SENSE = 3.68 V which exceeds 3.3 V ADC ref. By design — FC sees "max" reading above OVP, which triggers warning. Normal 6S operating range (18-25.2 V) fits within ADC envelope.

### Sim 3 (pair-wise S1↔S6) — S1 inrush → BAT_V FC reading

| Item | Value |
|---|---|
| Method | V_BATT model: nominal 25.2 V dipping to 24.5 V at t=0, recovering with τ=9.4 ms (S1 inrush settle). Divider + C49 filter (τ=1.22 ms) applied. |
| Source | `sims/phase4_place_connectors/pairwise_s1_s6.py` |
| **Max FC-reading error vs true V_BATT** | **0.27 %** |
| Spec | ±5 % |
| **Verdict** | **PASS ✓** (130 Hz filter heavily attenuates 9.4 ms-scale dip; FC sees gradual settle) |
| Figure | `sims/phase4_place_connectors/pairwise_s1_s6.png` |

### Sim 4 (pair-wise S2↔S6) — S2 ripple → BAT_V

| Item | Value |
|---|---|
| Method | S2 V_VMOTOR ripple 65 mV pk-pk @ 30 kHz isolated from BATT by R_NTC (5 Ω vs 30 mΩ batt R_int → 0.006 attenuation). Then divider × 0.1228 × filter 30k/130Hz attenuation. |
| Source | `sims/phase4_place_connectors/pairwise_s2_s6.py` |
| Ripple at BATT terminal | 0.39 mV pk-pk (after NTC isolation) |
| Ripple at V_SENSE pre-filter | 47.6 µV pk-pk |
| Ripple at FC ADC post-C49 filter | **0.21 µV pk-pk** |
| Spec | ≤ 10 mV pk-pk at FC ADC |
| **Verdict** | **PASS ✓** (margin 48 472× — two-stage isolation effectively zeroes ripple) |

### Sim 5 (pair-wise S3↔S6) — Hall V_OUT routing to AUX header

| Item | Value |
|---|---|
| Method | Hall post-divider (R31/R32/C44 cluster at (45, 48)) → AUX J12 (15, 80) over ~44 mm F.Cu trace. Capacitive coupling to S2 30 kHz ripple via F.Cu→In1 GND plane. Source impedance R31‖R32 = 6.67 kΩ. |
| Source | `sims/phase4_place_connectors/pairwise_s3_s6.py` |
| Routing pickup from S2 ripple | **0.18 mV pk-pk** |
| Intrinsic ACS770 noise (Allegro datasheet) | 8.0 mV pk-pk |
| **Total end-to-end noise (RSS)** | **8.002 mV pk-pk** |
| **Acceptance criterion (master-adjudicated 2026-05-22)** | **≤ 10 mV pk-pk end-to-end** |
| **Verdict** | **PASS ✓** (margin **1.998 mV**) |

**Acceptance criterion rationale (master adjudication 2026-05-22)**: anchor on sensor-intrinsic noise per Allegro ACS770 datasheet (8 mV pk-pk @ 80 kHz BW) PLUS industry-standard 25% system-routing margin = **10 mV end-to-end** (sensor + ≤50 mm PCB routing). The 8 mV datasheet number is the silicon + internal filter performance — real end-to-end signals always include routing pickup. RSS overshoot of 0.002 mV vs strict 8 mV anchor is numerical-rounding noise (0.18² added to 64² is negligible). Same engineering-anchoring pattern as Phase 4-place-bulk-caps Sim 4 stage-2 adjudication (V_VMOTOR ≥ 12 V replaced sag ≤ 5 V).

### Regression check (S1 + S2 + S3 sims re-run with S6 placed)

- S1 inrush peak 9.86 A unchanged
- S2 ripple 65 mV unchanged
- S3 Sims 1-4 outputs unchanged (S6 placement doesn't affect S3 internal sims)
- No regression.

## Sim methodology notes + limitations

- **DShot SI lumped LC model**: 5-section ladder approximates real microstrip but doesn't capture true distributed line behavior; accuracy ~80% for trace lengths < 50 mm at 600 kbaud. For Phase 5b autoroute, full S-parameter sim (scikit-rf) recommended on actual routed trace.
- **BAT_V worst-case corners**: assumes ±1% E96 resistors at nominal temp; full operating range (-40 to +85 °C) adds ~±200 ppm/°C × 125°C ≈ ±2.5% drift → still within ±5% spec.
- **Routing pickup coupling estimate**: 0.05 pF/mm assumed for F.Cu over In1 GND through 0.2 mm prepreg. Actual value depends on dielectric + plane orientation; Phase 5b can refine via 3D EM solver if needed.
- **S2↔S6 NTC isolation**: assumes 5 Ω cold NTC (MF72 5D25 spec) + 30 mΩ battery R_int. Hot NTC drops to ~50 mΩ (warmer = lower R for MF72 series); ripple isolation degrades but still > 100× margin remains.

## What's NOT placed (deferred)

| Sub-phase | Subsystem |
|---|---|
| S4 ×4 (next PR) | Channel template (4× MCU + 6 MOSFET + driver + protection + bypass + TVS + per-channel kill LED) |
| S5 | BEC (5 bucks + LDO + safety stack) |

551 footprints remain at kinet2pcb-default. Placed in subsequent sub-phase PRs.

## Open items (track to Phase 4-place-channels-x4 + Phase 4-place-bec)

- **DShot trace length placeholder**: Sim assumed 50 mm trace FC→MCU. Actual length determined by S4 channel placement (MCU position per quadrant). If any DShot trace exceeds 70 mm, re-sim with extended LC ladder + verify ringing margin.
- **VBAT divider ADC saturation above OVP**: V_BATT > 27 V → V_SENSE > 3.3 V → ADC clamps. By design; FC firmware sees "max reading" as OVP warning. Not a fix needed but flagging for FC firmware engineers.
- **Hall analog routing length**: 44 mm in current placement. If S6 AUX moved further from S3 in any future re-layout, re-sim routing pickup. > 70 mm length warrants shielded trace or differential routing.

## Acceptance gates (per spec §6 + locked rules)

| Gate | Status |
|---|---|
| S1 + S2 + S3 placement preserved | ✓ |
| ONLY S6 components placed (8 — honest deviation flag: master estimated 10-15) | ✓ |
| 0 same-layer bbox overlaps (all subsystem-internal + pair-wise + vs other) | ✓ |
| Mount-hole clearance (H3/H4 each ≥3 mm from S6 bbox) | ✓ |
| 3D render PNG (top + bottom) attached | ✓ |
| Sim 1 (DShot SI ngspice) — datasheet-anchored | ✓ PASS (rise 7.8 ns / ringing 7.5%) |
| Sim 2 (BAT_V divider accuracy) | ✓ PASS (worst-case 1.77% < 5%) |
| Sim 3 (S1↔S6 inrush → FC reading) | ✓ PASS (0.27% error) |
| Sim 4 (S2↔S6 ripple → FC) | ✓ PASS (48 472× margin) |
| Sim 5 (S3↔S6 Hall routing noise) — master-adjudicated ≤10 mV end-to-end (datasheet 8 mV + 25% system margin) | ✓ PASS (8.002 mV vs 10 mV; 1.998 mV headroom) |
| Regression: S1 + S2 + S3 sims unchanged | ✓ PASS |
| target.h md5 unchanged | ✓ `7a4549d27e0e83d3d6f1ffaf67527d24` |
| One PR | ✓ |
