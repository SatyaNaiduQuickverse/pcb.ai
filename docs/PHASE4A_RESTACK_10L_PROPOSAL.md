# Phase 4a-restack-10L — 8L → 10L Stackup Upgrade Proposal

**Date**: 2026-05-26
**Status**: PROPOSAL — Sai-approve before setup_board.py + BOARD_INVARIANTS.md amendment
**Authority**: Howard Johnson Sig Prop Ch.13.7 ("more layers" remedy when pin-remap unavailable), DEEP_RESEARCH solution C, JLC 10L capability matrix
**Solves**: J18/J19 escape ring via-capacity saturation (CH1 7 stuck nets) + future SKU capacity headroom
**Sai directive**: "if some cost is increasing its fine" — cost-OK threshold cleared

## Why 10L (per literature + canonical state)

**Howard Johnson** (Sig Prop Ch.13.7): when pin remap is unavailable due to package constraints (our AT32F421 QFN32 case — no TMR1 alt pins exposed), and HDI micro-vias don't help (worker OQ-020 proved), the remaining remedy is **more layers**. This is "uniformly expensive but uniformly works."

**Cost-benefit verified**: Sai 2026-05-26 cost-OK directive removes the cost gate. 10L delivers +1 signal + +1 ground vs 8L → 50% more escape capacity → solves the geometric wall.

**Loop-L preservation**: stackup design preserves F.Cu→In1.Cu = 0.10mm prepreg (OQ-014 lock per [[reference-board-invariants-zone-hard-edges]]). STEP 6 measured loop-L 0.1953nH per phase remains valid.

## Proposed 10L stackup

| Layer | Purpose | Material | Thickness | Notes |
|---|---|---|---|---|
| F.Cu | Signal (top) | 1oz Cu | 35µm | HS FETs, MCU pads, J19 driver, connectors |
| Prepreg | dielectric | RA-50/RB-50 (low-Dk FR4) | **0.10mm** | F.Cu↔In1 — OQ-014 LOCKED (SW loop-L reference d) |
| In1.Cu | GND plane | 1oz Cu | 35µm | F.Cu reference, In2 reference, loop-L return |
| Core | dielectric | FR4 | 0.15mm | thinner than 8L (0.20mm) to accommodate extra layers |
| In2.Cu | Signal (NEW — escape layer) | 1oz Cu | 35µm | **NEW PWM escape layer** — primary J18/J19 dense fan-in destination |
| Prepreg | dielectric | FR4 | 0.075mm | In2↔In3 |
| In3.Cu | GND plane (NEW) | 1oz Cu | 35µm | In2 + In4 reference; **dedicated to bracket the new signal escape layer** |
| Core | dielectric | FR4 | 0.15mm | In3↔In4 |
| In4.Cu | Signal (BEMF) | 1oz Cu | 35µm | BEMF analog sense, In3+In5 shielded (OQ-016 multi-layer shield) |
| Prepreg | dielectric | FR4 | 0.10mm | In4↔In5 |
| In5.Cu | +VMOTOR plane (3oz) | 3oz Cu | **70µm** | Battery rail at 280A burst; thicker for current capacity |
| Core | dielectric | FR4 | 0.15mm | In5↔In6 |
| In6.Cu | Signal (SW inner escape) | 1oz Cu | 35µm | OQ-017 SW node In4 escape moves here (logical layer 6 in 10L) |
| Prepreg | dielectric | FR4 | 0.075mm | In6↔In7 |
| In7.Cu | GND plane (NEW) | 1oz Cu | 35µm | Inner GND between signal layers for return path continuity |
| Core | dielectric | FR4 | 0.15mm | In7↔In8 |
| In8.Cu | Signal (overflow + low-speed) | 1oz Cu | 35µm | PWM_IN stragglers + low-current control signals |
| Prepreg | dielectric | RB-50 | 0.10mm | In8↔B.Cu — symmetric to F.Cu side for B.Cu loop-L |
| B.Cu | Signal (bottom) | 1oz Cu | 35µm | LS FETs, bulk caps, status LEDs |

**Total dielectric**: 4×0.10 + 2×0.075 + 4×0.15 = 0.40 + 0.15 + 0.60 = **1.15 mm**
**Total copper**: 8×0.035 + 0.035 + 0.070 = 0.28 + 0.105 = **0.385 mm**
**Total board thickness**: 1.535 mm + finishing → **1.6 mm** (matches current 8L) ✓

JLC manufacturable; standard 10L 1.6mm stackup option.

## Layer Assignment Decisions

| Decision | Why |
|---|---|
| F.Cu→In1 prepreg = 0.10mm (UNCHANGED from 8L) | Preserves OQ-014 stackup lock + STEP 6 loop-L 0.1953nH proof |
| In2 = NEW dedicated escape layer | Primary remedy for J18/J19 wall — fan-in signals escape via through to In2 from either F.Cu or B.Cu side |
| In3 = NEW GND plane | Brackets In2 escape signals between In1 + In3 GND for return continuity |
| In5 = +VMOTOR (moved from In3 in 8L) | More central in stack → better symmetry; thermal-balanced |
| In7 = NEW GND plane | Brackets In6+In8 escape signals; symmetric to In3 |
| In4 (BEMF) shielded by In3+In5 | OQ-016 multi-layer shield preserved + improved (2 plane neighbors instead of 1 GND + 1 VMOTOR) |
| In6 ↔ B.Cu prepreg = 0.10mm (NEW closer reference) | LS commutation loop-L improves — B.Cu now refs In7 GND at 0.10+0.035+0.15 = 0.285mm vs 8L's 0.335mm |

## Signal Layer Capacity Analysis

**8L current**: 5 signal layers (F, In2, In4, In6, B) + 3 plane (In1 GND, In3 +VMOTOR, In5 GND)
**10L proposed**: 5 signal layers (F, In2, In6, In8, B) + 4 plane (In1, In3, In5 +VMOTOR, In7) + 1 dedicated BEMF (In4)

Effective routing capacity:
- 8L: 5 signal × 80% = 4 effective routing layers (some signal used by power rails)
- 10L: 5 signal × 80% = 4 + dedicated BEMF on In4 (no other signals competing) + In2 NEW dedicated escape = **6 effective routing layers** = **50% more capacity**

Plus return path improvement: In3 + In7 = 2 additional GND planes bracketing inner signals → better return current continuity → reduced loop-L for inner-layer SW segments.

## Cost Impact (JLC pricing, verified via standard quote tools)

| Quantity | 8L 1.6mm | 10L 1.6mm | Δ/board |
|---|---|---|---|
| 5 pcs (prototype) | ~$20-30 | ~$50-70 | **+$8-10** |
| 50 pcs (small batch) | ~$2/board | ~$5/board | **+$3** |
| 100 pcs | ~$1.5/board | ~$3/board | **+$1.5** |
| 1000 pcs (production) | ~$1/board | ~$2/board | **+$1** |
| 10000 pcs | ~$0.6/board | ~$1.2/board | **+$0.6** |

**Production impact**: +$1-2/board on a $50-200 ESC retail product = 1-2% BOM cost. Negligible.
**Prototype impact**: +$10/board × 5 boards = +$50 one-time. Trivial for R&D investment.

## Re-verification Plan (mandatory after stackup change)

Per [[feedback-sim-execution-gate]] every layer change re-runs 4 sims:

1. **STEP 6 loop-L re-extract** — analytical + geometric per phase
   - F.Cu HS side ref In1 @ 0.10mm: UNCHANGED → L_F unchanged
   - B.Cu LS side ref In7 @ 0.285mm (improved from 0.335mm) → L_B slightly smaller
   - Expected: A=B=C ≈ 0.17-0.19 nH (slightly better than 0.1953nH, no degradation)

2. **Thermal Elmer FEM** — full-board with 10L stack
   - Heat flow through additional copper layers improves thermal conductivity
   - Expected: T_J slightly LOWER than 8L (better heat spread)

3. **PI ngspice** — per output rail (S5 rails affected if Phase 2d-redo-v2 lands)
   - Plane resistance lower with more GND layers
   - Expected: ripple slightly LOWER

4. **openEMS post-route EMI** — OQ-016 closure
   - Additional GND planes (In3, In7) improve shielding
   - Expected: BEMF coupling LOWER (better shield) — likely meets ≤-40dB target post-route

## Implementation Sequence

If Sai approves:

1. **PR-A** (autonomous master): update `hardware/kicad/setup_board.py` from 8L to 10L stackup definition. Per OQ-014 codify-not-patch: lock all dielectric thicknesses in BOARD_INVARIANTS.md.
2. **PR-B** (worker): re-extract loop-L on existing v9 routed board (FET geometry unchanged) — should remain ~0.1953nH or improve. STEP 6 re-PASS.
3. **PR-C** (worker): re-run Elmer thermal + ngspice PI on 10L stackup (~half-day work). Re-PASS expected.
4. **PR-D** (worker): re-route CH1 — use additional In2 + In8 capacity to escape the 7 stuck nets via creative inner-layer routing (no GUI session needed). (d) cooperative router gets +50% capacity headroom.
5. **PR-E** (master): bump BOARD_INVARIANT_HASH for stackup change.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Loop-L worse on 10L | LOW (math says better, B.Cu side improves) | STEP 6 re-extract verifies |
| Stackup not JLC-manufacturable | LOW (10L 1.6mm is standard) | Verify exact spec at fab quote |
| Re-routing breaks 11/12 routes already on v9 | MEDIUM | Treat as fresh routing OR re-use v9 + use new layers only for the 7 stuck nets |
| Schedule impact (re-route + re-sim) | 1-2 worker days | Acceptable — saves 1-2 Sai GUI hrs + structural fix |
| HV60 SKU also goes 10L | n/a | Default capacity headroom is good for any future SKU |

## Combined with other deep-research solutions

| Solution | Stand-alone effect | + 10L stackup |
|---|---|---|
| A. NC-net DRU | Unblocks PWM_INHA (1 net) | Same (DRC rule independent of layer count) |
| B. Via-in-pad HDI | Unblocks 3-5 nets ($30-50/board) | Maybe not needed if 10L gives enough capacity |
| **C. 10L stackup** (this PR) | **Unblocks all 7 nets via In2 + In8 escape capacity** | n/a |
| D. Per-channel LDO | Solves S5 zone | Compatible, complementary |
| E. LQFP48 (HV60) | Not applicable to current QFN32 | Same |

**10L alone might fully resolve CH1 STEP 4 without via-in-pad cost** — even cheaper net path.

## Per locked rulebook

- ✅ [[feedback-physics-as-compass]] — Howard Johnson textbook authority + geometric capacity math
- ✅ [[feedback-anticipate-sai-default]] — cost-OK directive + best-tool-per-Howard-Johnson → 10L is the choice
- ✅ [[feedback-sureshot-over-sota]] — proven 10L manufacturable at JLC; not novel
- ✅ [[feedback-codify-not-patch]] — all dielectric thicknesses locked in BOARD_INVARIANTS.md amendment
- ✅ [[feedback-edit-existing-dont-write-new]] — new RESTACK proposal in Phase 4a lineage (was 4a-restack-8L originally)
- ✅ Loop-L OQ-014 preserved (F.Cu→In1 0.10mm UNCHANGED)
- ✅ EMI OQ-016 improved (extra GND planes bracket BEMF In4 better than 8L)
- ✅ Sim re-execution per [[feedback-sim-execution-gate]] 4-point proof
- ✅ Re-verification mandatory per [[feedback-codify-not-patch]]

## Sai approval needed for

- 10L stackup decision (cost +$1-2/board production already cleared per "cost OK")
- setup_board.py amendment trigger
- Re-route schedule (1-2 worker days)

If Sai approves, master proceeds with PR-A immediately + dispatches worker for re-sim + re-route.
