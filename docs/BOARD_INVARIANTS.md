# Board Invariants (SSOT) — Phase 4-v2 Step 1

**Status**: v2 — addresses master review (5 issues). Pending Sai-approval lock.
**Per**: Phase 4-v2 dispatch Step 1.

Any PR changing this hash WITHOUT explicit "invariant-change" PR title = REJECT.

## Board geometry

- Outline: 100×100 mm
- Mount holes: 4× M3 at corners (5,5), (95,5), (5,95), (95,95)
- target.h md5: `7a4549d27e0e83d3d6f1ffaf67527d24` (firmware contract — LOCKED)
- Stackup: 8-layer (F.Cu / In1=GND / In2=signal / In3=+VMOTOR / In4=signal / In5=GND / In6=signal / B.Cu)

## Subsystem zones (LOCKED on Sai-approval)

Per master v2 review #1: CH1-CH4 tightened to EXCLUDE the 35-65 central spine
(where S2/S3 sit).

| Subsystem | x_min | y_min | x_max | y_max | Function |
|---|---|---|---|---|---|
| S1 battery input | 0 | 82 | 100 | 100 | bottom edge — BAT_P/BAT_N solder pads + NTC + TVS (swapped 2026-05-26 with S6 per Sai mechanical revamp) |
| S6 connectors | 0 | 0 | 100 | 18 | top edge — J14 FC + J12 AUX + USBLC6 ESDs + LDO (swapped 2026-05-26 with S1) |
| CH1 (channel A) | 0 | 50 | 35 | 82 | NW — FET cluster + DRV + MCU + INA |
| CH2 (channel B) | 65 | 50 | 100 | 82 | NE — mirror_X(CH1) |
| CH3 (channel C) | 65 | 18 | 100 | 50 | SE — mirror_X(CH4) |
| CH4 (channel D) | 0 | 18 | 35 | 50 | SW — bottom-pair template |
| S2 bulk caps | 40 | 40 | 60 | 60 | central — 4× polymer caps low-ESR |
| S3 supervisor+Hall | 40 | 18 | 60 | 40 | central spine — TL431 + Hall |
| S5 BEC east strip | 35 | 50 | 40 | 82 | east of CH1 spine — 5mm BEC bus (CH1/CH2 feed) |
| S5 BEC west strip | 60 | 50 | 65 | 82 | west of CH2 spine — 5mm BEC bus (S5-2) |
| S5 BEC south strip | 35 | 18 | 40 | 50 | for CH3/CH4 (mirror) |

Channels NO LONGER overlap central 35-65 column. S5 explicit bbox per v2 #4.

## Symmetry pairs (LOCKED, 2-fold mirror about x=50)

- **CH1 ↔ CH2**: mirror_X(50)
- **CH3 ↔ CH4**: mirror_X(50)

No 4-fold symmetry — only 2-fold pair-mirror per master dispatch.

## Subsystem I/O ports (LOCKED at zone boundary, ±0.5mm tolerance)

Per master v2 review #3: S6→CHn now 4 explicit rows.

| From → To | Port pos | Width | Signals | Reason |
|---|---|---|---|---|
| S1 → S3 | (50, 18) | 4 mm | +BATT, BATGND | central spine to bulk |
| S3 → S2 | (50, 40) | 4 mm | +BATT, BATGND, BUS_CURR_HALL_OUT | bulk caps + sensor |
| S2 → CH1 | (40, 50) | 4 mm | +VMOTOR, GND | feed CH1 FETs |
| S2 → CH2 | (60, 50) | 4 mm | +VMOTOR, GND | feed CH2 FETs |
| S2 → CH3 | (60, 50) | 4 mm | +VMOTOR, GND | feed CH3 FETs (mirror_Y of CH1) |
| S2 → CH4 | (40, 50) | 4 mm | +VMOTOR, GND | feed CH4 FETs |
| S6 → CH1 | (17, 82) | 2 mm | DShot_CH1, TLM_CH1, KILL_CH1 | FC commands CH1 |
| S6 → CH2 | (83, 82) | 2 mm | DShot_CH2, TLM_CH2, KILL_CH2 | FC commands CH2 |
| S6 → CH3 | (83, 50) | 2 mm | DShot_CH3, TLM_CH3, KILL_CH3 | FC→CH3 (south, mirror) |
| S6 → CH4 | (17, 50) | 2 mm | DShot_CH4, TLM_CH4, KILL_CH4 | FC→CH4 |
| S5 → CH1 | (35, 65) | 2 mm | +V5, +V9, +3V3 | BEC east strip → CH1 |
| S5 → CH2 | (65, 65) | 2 mm | +V5, +V9, +3V3 | BEC west strip → CH2 |
| S5 → CH3 | (65, 35) | 2 mm | +V5, +V9, +3V3 | mirror_Y |
| S5 → CH4 | (35, 35) | 2 mm | +V5, +V9, +3V3 | mirror_Y |

## Highway reservations (NO subsystem may place into)

Per master v2 review #2: removed vague "radial" entry; replaced with explicit
coords.

| Highway | x_min | y_min | x_max | y_max | Reason |
|---|---|---|---|---|---|
| +BATT/GND spine | 48 | 0 | 52 | 50 | 280A continuous power path top→center |
| BEMF return centerline | 47 | 50 | 53 | 82 | 4× BEMF signals to central MCU |
| TLM/AUX bus strip | 0 | 80 | 100 | 82 | inter-subsystem digital |
| S2 to CH1 +VMOTOR feed | 30 | 47 | 36 | 53 | low-loop radial CH1 (6×6mm corner) |
| S2 to CH2 +VMOTOR feed | 64 | 47 | 70 | 53 | low-loop radial CH2 |
| S2 to CH3 +VMOTOR feed | 64 | 47 | 70 | 53 | low-loop radial CH3 (mirror) |
| S2 to CH4 +VMOTOR feed | 30 | 47 | 36 | 53 | low-loop radial CH4 |

## Invariant hash

Per master v2 review #5: compute + store hash.

Run `python3 hardware/kicad/scripts/compute_board_invariant_hash.py --write`
to compute and write.

```
BOARD_INVARIANT_HASH = b6766bd3223baef22f56dbc8f10003fb366d46162a044326bd61b2e6ec84c03e
```

## Audit gate

`check_board_invariants_hash()` to be added to audit_meta.py:
- Recomputes hash from this file's structured tables
- Compares to stored BOARD_INVARIANT_HASH
- REJECT on drift unless PR title contains "invariant-change"

## Approval flow

1. master review v2 (this commit)
2. Compute + write hash
3. master final-approve
4. Lock — audit_meta enforces
