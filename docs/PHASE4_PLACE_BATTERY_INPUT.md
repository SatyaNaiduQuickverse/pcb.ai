# Phase 4-place-battery-input — Subsystem S1 placement

**Sub-phase 1 of `docs/PHASE4_SUBSYSTEMS.md` §S1**.
**Branch**: `phase4-place-battery-input/subsystem-s1`.
**Master directive**: Task #49 dispatch 2026-05-22.

## What's placed (8 components, S1 only)

| Ref | Value | Footprint | Layer | Position (x, y) mm | Notes |
|---|---|---|---|---|---|
| J1 | BATT_PAD | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | F.Cu (PTH all-layer) | (50, 4) | XT30 connector, bottom-center |
| D26 | SMBJ33A | `Diode_SMD:D_SMB` | B.Cu | (32, 5) | Battery section TVS, transient suppression on +BATT |
| R1 | MF72_5D25 | `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P5.08mm_Vertical` | F.Cu (PTH) | (28, 10) | NTC inrush limiter #1 (parallel with R2) |
| R2 | MF72_5D25 | `Resistor_THT:R_Axial_DIN0207_...` | F.Cu (PTH) | (72, 10) | NTC inrush limiter #2 |
| Q1 | BSC014N06NS | TDSON-8 (5×6 mm) | B.Cu | (40, 10) | Rev-pol FET #1 (top-left of 2×2 cluster) |
| Q2 | BSC014N06NS | TDSON-8 | B.Cu | (60, 10) | Rev-pol FET #2 (top-right) |
| Q3 | BSC014N06NS | TDSON-8 | B.Cu | (40, 17) | Rev-pol FET #3 (bot-left) |
| Q4 | BSC014N06NS | TDSON-8 | B.Cu | (60, 17) | Rev-pol FET #4 (bot-right) |

## Zone occupied

Spec §S1: X=20–80, Y=0–13 (bottom-edge band).

**Actual occupied X×Y**: ~24 ≤ x ≤ 78, 2 ≤ y ≤ 20.

**Spec deviation**: Q3/Q4 RP FET bottom-row spills to y=20 (4mm past Y=13). Reason: SuperSO8 (TDSON-8) body is 5×6 mm; a 2×2 cluster requires ≥12 mm vertical span; the spec'd 13 mm zone height with 2 rows of bodies + 1 mm minimum gap forces y_max ≥ 17–18. Master spec §S1 places cluster center at (50, 11) — actual cluster centers at (50, 13.5) for 1+ mm clearance to the bottom-row (J1, D26). The (40-60, 13-20) area is **reserved by S1**; subsequent S2 bulk-cap placement must avoid it.

## I/O contract (per spec §S1)

- **Inputs**: +BATT_RAW, BATGND (from XT30 J1 pins)
- **Outputs**: +BATT_FUSED, GND (post-NTC, post-rev-pol FETs)
- **Boundary to S2**: +BATT_FUSED rail exits the S1 zone at approximately y=18 (north of Q3/Q4 drain pads), feeding the bulk cap bank directly above in spec'd S2 zone (Y=13-42).

## Verification

- ✓ `verify_placement.py` bbox audit: **0 same-layer body overlaps** within S1 zone (J1 ↔ D26 prior-overlap eliminated by moving D26 left to x=32 and Q1/Q2 outward to x=40/60)
- ✓ **0 overlaps between S1 components and other placed parts** (mount holes at corners; rest of board at kinet2pcb-default positions away from S1 zone)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ J1 XT30 PTH pads accessible from board edge for wire soldering (pad-to-edge ≥ 2 mm)
- ✓ NTCs (R1, R2) inrush-limiter pair in parallel (combined 16 A capability per netlist description)
- ✓ Rev-pol FETs Q1-Q4 in 2×2 cluster, drain side faces +BATT_FUSED output (north)
- ✓ TVS D26 oriented for transient suppression on +BATT_RAW

## 3D render attachments

- [`docs/renders/phase4_place_battery_input/top.png`](renders/phase4_place_battery_input/top.png) (F.Cu view — J1 XT30, R1/R2 NTCs visible)
- [`docs/renders/phase4_place_battery_input/bottom.png`](renders/phase4_place_battery_input/bottom.png) (B.Cu view — Q1-Q4 rev-pol FETs, D26 TVS visible)

Renders regenerable via:
```
kicad-cli pcb render --output docs/renders/phase4_place_battery_input/top.png \
  --side top --background opaque --quality high --width 1600 --height 1200 \
  hardware/kicad/pcbai_fpv4in1.kicad_pcb
```
(same for `--side bottom` → `bottom.png`)

## What's NOT placed (deferred per spec §5 sub-phase ordering)

| Sub-phase | Subsystem | Components |
|---|---|---|
| S2 (next PR) | Bulk cap bank | C1-C4 EEHZS1V471P + ceramic decoupling |
| S3 | Supervisor + Hall | TPS3700, ACS770ECB-200B, voltage dividers |
| S4 ×4 | Channel template | 4× (MCU + 6 MOSFETs + driver + protection + bypass + TVS + BEMF + PWM passives) |
| S5 | BEC | 5 bucks + LDO + LC filters + protection |
| S6 | Connectors | FC connector, BM06B-SRSS-TB AUX, status LEDs, DShot TVS |

All 577 unplaced components remain at kinet2pcb-default positions in this PR (typically a flat grid). They get placed in subsequent sub-phase PRs.

## Acceptance gates (per spec §6)

| Gate | Status |
|---|---|
| 0 same-layer bbox overlaps within S1 | ✓ |
| 3D render PNG attached (top + bottom) | ✓ |
| Per-cluster D/S < 0.85 for S1 zone | ✓ (only 8 components in S1 zone; D ~ 50 mm² / S ~ 530 mm² ≈ 0.09; trivially passes) |
| target.h md5 unchanged | ✓ |
| Updates only S1 components | ✓ (no S2-S7 placements) |
