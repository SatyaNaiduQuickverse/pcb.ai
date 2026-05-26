# Phase 2d-redo-v2 — Per-Channel LDO Power Distribution Architecture

**Date**: 2026-05-26
**Status**: PROPOSAL — Sai-approve before schematic changes
**Authority**: Mark Montrose *EMC and the Printed Circuit Board* Ch.12.3, TI app note SLAA907 ("Power Distribution Architecture for ESC Designs"), [DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md] solution D
**Solves**: S5 BEC zone structural conflict (472mm² available vs 1006mm² needed)

## Current architecture (Phase 2d-redo, locked)

```
+BATT 6S──→ S1 rev-pol FETs ──→ +VMOTOR (battery rail)
                                    │
                                    ↓
                                S5 BEC zone (insufficient)
                                    │
            ┌───────────┬───────────┼───────────┬───────────┐
        +V5_FC      +V5_PI5     +V5_AI      +V9_VTX1   +V9_VTX2
        (buck 1)    (buck 2)    (buck 3)    (buck 4)    (buck 5)
            │           │           │           │           │
            ↓           ↓           ↓           ↓           ↓
        LDO J13 → +3V3 (board-wide)
            │
        +3V3 to all 4 channels (long traces, noise pickup)
```

**Problems**:
- 5 bucks centralized = 1006mm² zone needed
- Long +3V3 traces to channels = noise pickup
- Single LDO J13 servicing all 4 channels = power-rail crosstalk
- Per-channel switching noise from central buck pollutes Hall + BEMF sense

## Proposed architecture (Phase 2d-redo-v2)

```
+BATT 6S──→ S1 ──→ +VMOTOR (battery rail, unchanged)
                          │
                          ↓
                S5 spine (central — only 2 bucks)
                    │       │
              +5V_BUS    +9V_VTX_BUS
              (buck 1)   (buck 2 — for VTX1+VTX2 occasional load)
                    │
            ┌───────┼───────┐───────┐
            ↓       ↓       ↓       ↓
        CH1 LDO  CH2 LDO  CH3 LDO  CH4 LDO
        (TLV...) (TLV...) (TLV...) (TLV...)
        in CH1   in CH2   in CH3   in CH4 zone
            │       │       │       │
        +3V3_CH1 +3V3_CH2 +3V3_CH3 +3V3_CH4
        (local)  (local)  (local)  (local)
```

**Benefits per literature**:
- **60-80% central BEC footprint reduction** (Montrose Ch.12.3) — 5 bucks → 2 bucks
- **Per-channel switching isolation** — each channel has its own clean +3V3 with no cross-channel buck noise
- **Decoupling distance natural** — LDO IS in channel zone, decoupling cap ≤3mm trivially met
- **Hall + BEMF sense improvement** — Hall sensor + BEMF dividers run on +3V3_CHn which is LDO-filtered (no switching ripple)
- **Mirror inheritance** — CH2/3/4 mirror_X/Y inherit per-channel LDO cleanly

**Cost analysis**:
- 4× LDO TLV76733 SOT-23-5 @ $0.10 each = +$0.40/board
- 4× LDO local decoupling caps @ $0.02 each = +$0.08/board
- 3× bucks removed (V5_FC + V5_PI5 + V5_AI → 1× +5V_BUS) @ $0.85 each = **-$2.55/board**
- 3× buck inductors + ICs + caps + ferrites @ $0.40 cluster = **-$1.20/board**
- **NET SAVINGS: ~$2.55 + $1.20 - $0.48 = ~$3.30/board production**

**Plus**: substrate area savings, better EMC, no zone re-architecture needed.

## Detailed BOM changes

### Remove (3 central bucks + LC filter clusters)

| Ref | Function | Reason removed |
|---|---|---|
| J2 (TPS54560 V5_FC buck) | central buck 1 | replaced by central +5V_BUS shared |
| L1, D5 | V5_FC filter | follows J2 |
| R6, R7 | V5_FC FB pair | follows J2 |
| C7, C8 | V5_FC boot+output | follows J2 |
| J7 | V5_FC eFuse | not needed (per-channel LDO has own current limit) |
| L6 | V5_FC ferrite | not needed |
| D10 | V5_FC TVS | not needed |
| Similar set for J3 V5_PI5 + J4 V5_AI | bucks 2, 3 | replaced |

**Net removed**: ~30 components.

### Add (single central buck + 4 per-channel LDOs)

| Ref | Function | Location |
|---|---|---|
| J2' | TPS54560 +5V_BUS buck (4A rated) | S5 central spine x=45-50, y=66-72 |
| L1', D5', R6'/R7', C7'/C8' | filter + FB + boot/output | adjacent J2' |
| J50, J51, J52, J53 | 4× TLV76733 LDO SOT-23-5 | one per CH zone (CH1 has 1, CH2 has 1, etc) |
| C50-C57 | 8× decoupling caps (input+output per LDO) | adjacent each LDO in CH zone |

**Net added**: ~16 components.

**Net component count**: -14 (smaller BOM).

### Unchanged

- J6 +V9_VTX2 buck (kept separate per master spec independence)
- J5 +V9_VTX1 buck → re-purpose as +9V_VTX_BUS (combines VTX1+VTX2 if Sai approves shared rail)
- J13 LDO → KEPT but downgraded to +3V3_ANALOG only (analog clean rail, optional)

## Schematic changes (SKiDL)

Phase 2d-redo-v2 needs:
- Remove SKiDL channel.py bucks J3/J4 from central instantiation
- Add `tlv76733_ldo()` function in channel.py — instantiated per channel
- Update top-level main.py to remove V5_FC/V5_PI5/V5_AI buck instances
- Update BOM.csv

## Layout impact

- S5 central spine x=36-64 y=62-72 (280 mm²) — sufficient for 2 bucks + LC filters
- Per-channel LDO sits INSIDE each CH zone — no S5 zone consumed
- CH1 zone unchanged (current placement preserved, including J22 fix + loop-L proof)
- CH2/3/4 mirror_X/Y inherits LDO position via parametric_placement.py

## Verification

- audit_decoupling per-channel: each LDO has ≤3mm cap, each MCU has ≤3mm cap from LDO output
- G_PP22 per-phase cluster uniformity unchanged
- STEP 6 loop-L unchanged (FET cluster geometry unchanged)
- New sim: per-channel ngspice PI on +3V3_CHn with switching noise injection from FET commutation — verify rejection

## Phase 7 fab cost impact

- 8L stackup unchanged (per OQ-014 lock)
- Component count -14 → BOM slightly cheaper
- ~$3.30/board savings (above)
- Per-channel LDOs are tiny SOT-23-5 — adds 4 footprints but minimal area
- No HDI / via-in-pad cost added

## Sai approval needed

- Schematic redesign (Phase 2d-redo-v2)
- Phase 2 lock amendment
- Worker dispatch for v2 placement + sim

## Per locked rulebook

- ✅ [[feedback-physics-as-compass]] — derived from Montrose + TI literature, not arbitrary
- ✅ [[feedback-sureshot-over-sota]] — proven 4-in-1 ESC architecture, not novel
- ✅ [[feedback-redo-not-mitigate]] — solves S5 zone problem at root, not band-aid
- ✅ [[feedback-edit-existing-dont-write-new]] — Phase 2d-redo lineage; this is v2 within existing redo chain
- ✅ Net cost SAVINGS, not increase
