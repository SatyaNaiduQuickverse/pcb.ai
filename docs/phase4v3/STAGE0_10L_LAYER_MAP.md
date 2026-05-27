# STAGE-0 10L — Layer-Index Map (router/script reference)

Phase 4a-restack-10L migration (PR #180, Sai-approved autonomous 2026-05-27).
Companion to `docs/BOARD_INVARIANTS.md` (semantic stackup + dielectric, load-bearing).
This file gives the **pcbnew integer layer-ID ↔ name ↔ role** map that routing/audit
scripts must use, and the **8L→10L remap** that breaks 8L-hardcoded assumptions.

## Authoritative pcbnew layer IDs (from migrated canonical, GetEnabledLayers().CuStack())

| pcbnew id | name   | type (phys) | 10L role                                              |
|-----------|--------|-------------|-------------------------------------------------------|
| 0         | F.Cu   | signal 1oz  | HS FETs, MCU pads, drivers (J19), connectors          |
| 4         | In1.Cu | GND 1oz     | GND plane #1 — F.Cu ref @ 0.10mm prepreg (OQ-014 LOCK) |
| 6         | In2.Cu | signal 1oz  | **NEW** dedicated J18/J19 fan-in escape layer         |
| 8         | In3.Cu | GND 1oz     | **NEW** GND plane #2 — brackets In2 escape            |
| 10        | In4.Cu | signal 1oz  | BEMF analog (shielded by In3 GND + In5 VMOTOR, OQ-016)|
| 12        | In5.Cu | +VMOTOR 3oz | +VMOTOR ≥280A bus — **MOVED from In3 (8L)**           |
| 14        | In6.Cu | signal 1oz  | SW inner escape (OQ-017) — **was In4 in 8L**          |
| 16        | In7.Cu | GND 1oz     | **NEW** GND plane #3 — brackets In6 + In8             |
| 18        | In8.Cu | signal 1oz  | **NEW** PWM_IN stragglers + low-current overflow + per-channel VMOTOR_CHn local pours in FET regions (CH1-4) |
| 2         | B.Cu   | signal 1oz  | LS FETs, bulk caps, status LEDs                       |

Note: all copper layers are **signal-typed** in the .kicad_pcb (DSN-export compat per
Phase 5b finding T8); In1/In3/In5/In7 carry "(Phase 5c re-classifies to power)" descriptors.
Plane-ness is by convention/descriptor, not the KiCad layer type, until Phase 5c.

## 8L → 10L remap (what 8L-hardcoded scripts get WRONG)

| Role            | 8L layer (id)   | 10L layer (id)   | Impact on 8L-hardcoded code            |
|-----------------|-----------------|------------------|----------------------------------------|
| GND ref (F-side)| In1 (4)         | In1 (4)          | unchanged — loop-L plane ref intact    |
| **+VMOTOR**     | **In3 (8)**     | **In5 (12)**     | id 8 was VMOTOR, now GND — MUST remap   |
| GND #2          | In5 (12)        | In3 (8) + In7(16)| id 12 was GND, now VMOTOR — MUST remap  |
| BEMF analog     | In4 (10)        | In4 (10)         | id unchanged; shield neighbors changed  |
| **SW escape**   | **In4 (10)**    | **In6 (14)**     | SW escape layer moved 10→14             |
| escape / fan-in | (none / In2 ad-hoc) | In2 (6) dedicated | NEW dedicated escape layer          |
| overflow signal | (none)          | In8 (18)         | NEW — PWM_IN straggler capacity         |
| VMOTOR_CHn rail | (none)          | In8 (18) local   | NEW — per-channel local pour in FET region (x≈4-35 CH1, mirror per ch); VMOTOR_CH≠+VMOTOR until R34 (S3). Master-approved 2026-05-27 |

Net routing capacity: 8L signal layers {F(0),In2(6),In4(10),In6(14),B(2)} = 4 inner+2 outer
effective 4 → 10L signal {F(0),In2(6),In4(10 BEMF),In6(14),In8(18),B(2)} + In4 dedicated BEMF
= **6 effective routing layers (+50%)**. This is the J18/J19 escape remedy
(see memory reference-j18-escape-rootcause: pin-remap unavailable on QFN32 → more layers).

## Script-impact list (must update before STEP 0.7 re-route)

- **Routers** (`route_ch1_coop.py`, `route_ch1_*`): 8L plan was F/In4/In6/B with In2=BEMF-reserved.
  10L plan: escape on **In2(6)**, SW on **In6(14)**, BEMF on **In4(10)**, overflow on **In8(18)**;
  +VMOTOR plane now **In5(12)** not In3(8). Full layer-plan rewrite required.
- **Loop-L extract** (`loop_extract.py`): GND ref = In1(4) UNCHANGED → 0.1953nH expectation holds
  (re-verify in STEP 0.5).
- **vocc/occ grids / DRC substitute** (`check_ch1_clearance.py`): layer set enumeration must include
  In7(16)+In8(18); +VMOTOR collision layer is now id 12 not 8.
- **Audits keying on layer id** (via-stitching, plane checks): +VMOTOR=12, GND={4,8,16}.

## Dielectric / loop-L (see BOARD_INVARIANTS.md §10L)

F.Cu→In1 = 0.10mm UNCHANGED (OQ-014 LOAD-BEARING; STEP-6 0.1953nH/phase preserved).
B.Cu→In7 = 0.285mm (improved from 8L 0.335mm → LS-side loop-L slightly better).
Total 1.6mm 10L (JLC standard).
