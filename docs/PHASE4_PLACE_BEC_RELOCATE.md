# Phase 4-place-bec-relocate — S5 spine pocket relocation (PR-A2)

**Per master Option A adjudication 2026-05-22 + root-cause prevention rule 2026-05-23.**
**PR-A2 of 3 (PR-A1 merged; PR-A3 next).**

## Symptom

PR #37 placed S5 BEC Bucks 1-4 in NW/NE channel-zone strips (X=5-39, X=61-95 at Y=58-72). Phase 4-place-channel-template attempt (PR-A3 draft) failed bbox-clean (13 overlaps) because channel quadrants were occupied by S5 components. Fix attempt deadlocked.

## Fix

Move Bucks 1-4 + inductors L1-L4 + LDO J13 from NW/NE strips → **central spine pocket** X=39-61 Y=58-72. Move R34 S3 jumper from (50, 65) → (50, 47) B.Cu to free spine pocket center. Move J10 V5_PI5 supervisor to SW corner (no room in spine pocket). Buck 5 V9_VTX2 cluster retains SW exception (already isolated).

## Root cause

`docs/PHASE4_SUBSYSTEMS.md` §S5 said:
> "Zone: central spine middle, Y=42-58 sharing with S3, or distributed side bands"

The wording **"distributed side bands"** was ambiguous:
- Interpretation (a): outside channel zones (in safe lateral strips)
- Interpretation (b): IN the channel-zone side strips at Y=58-72

PR #37 went with interpretation (b), placing bucks in channel-zone strips. This created the structural conflict for S4.

## Prevention (locked rule 2026-05-23)

**Every subsystem in `docs/PHASE4_SUBSYSTEMS.md` now has ALLOWED zone + explicit FORBIDDEN zones**:

- §S1 battery: ALLOWED Y=0-20 X=20-80; FORBIDDEN channel zones + spine pocket + S6 top edge
- §S2 bulk caps: ALLOWED X=18-82 Y=20-42; FORBIDDEN channel zones + spine pocket + Hall body + S1/S6 zones
- §S3 supervisor: ALLOWED X=39-61 Y=20-58; FORBIDDEN channel zones + spine pocket Y=58-72 + S6/S1/S2 zones
- §S4 channels: ALLOWED quadrant per index; FORBIDDEN central spine + other channels + S1/S6 zones
- §S5 BEC: **ALLOWED spine pocket X=39-61 Y=58-72** + SW corner exception for Buck 5; FORBIDDEN all 4 channel zones + S1/S2/S3/S6 zones
- §S6 connectors: ALLOWED Y=72-85; FORBIDDEN all other subsystem zones

**Root-cause prevention rule**: every future PR doc must include 4 sections: Symptom, Fix, Root cause, Prevention. If any can't be filled, PR is incomplete. (See [[feedback-root-cause-not-symptom]].)

## What's placed in PR-A2 (S5)

| Ref | Position | Notes |
|---|---|---|
| J2 V5_FC | (43, 62) F.Cu | Spine pocket NW corner — relocated from (12, 60) |
| J3 V5_PI5 | (43, 70) F.Cu | Spine pocket SW corner — relocated from (12, 70) |
| J4 V5_AI | (57, 62) F.Cu | Spine pocket NE corner — relocated from (88, 60) |
| J5 V9_VTX1 | (57, 70) F.Cu | Spine pocket SE corner — relocated from (88, 70) |
| L1 4.7uH | (43, 62) B.Cu | Stacked under J2 (different layer) |
| L2 4.7uH | (43, 70) B.Cu | Stacked under J3 |
| L3 8.2uH | (57, 62) B.Cu | Stacked under J4 |
| L4 10uH | (57, 70) B.Cu | Stacked under J5 |
| J13 LDO | (50, 66) F.Cu | Center spine pocket (between 4 bucks) |
| J10 supervisor | (10, 10) F.Cu | EVICTED to SW corner (no room in spine pocket center) |

**Buck 5 V9_VTX2 cluster preserved at SW** (J6, L5, D9, F2, R14, R15, C20, L10, D14, C21) — already isolated.
**S3 R34 B.Cu jumper** relocated from (50, 65) → (50, 47) to clear spine pocket center.

## Honest spec deviation — safety stack deferred off-board (20 components)

Spine pocket (X=39-61 Y=58-72 = 308 mm²) is physically too small for full S5 spec (4 bucks ~168mm² + 4 inductors ~200mm² + 4 Schottky ~100mm² + 4 TVS ~100mm² + 4 ferrites ~40mm² + 3 eFuses ~54mm² + 1 polyfuse ~11mm² + 4 C_OUT ~32mm² + 8 FB + 4 boot caps + LDO + supervisor = ~830 mm²).

Even with F.Cu + B.Cu stacking (616 mm² total), the spine pocket can't fit the full safety stack alongside the bucks.

**Deferred to follow-up PR (off-board placement coords y=95/100/105/110 mm; outside board y=0-85 mm)**:
- 4× Schottky D5/D6/D7/D8 (SS54)
- 4× TVS D10/D11/D12/D13 (SMAJ5.0A V5; SMAJ9.0A V9)
- 3× eFuses J7/J8/J9 (TPS259251)
- 1× polyfuse F1 (MF-MSMF200)
- 4× ferrites L6/L7/L8/L9 (600Ω@100MHz)
- 4× C_OUT C8/C12/C15/C18 (22µF)
- 8× FB resistors R6-R13
- 4× boot caps C7/C11/C14/C17

These will be placed in a **PR-A2-followup** (Phase 4-place-bec-safety) after PR-A3 (channel template). Channel placement may free additional area to accommodate safety stack near each rail's output, OR master may adjudicate to place them in SW corner with Buck 5 cluster + SE corner extension.

## Verification

- ✓ 0 same-layer bbox overlaps across all 15 subsystem checks
- ✓ target.h md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ S1 + S2 + S6 preserved from PR-A1
- ✓ S3 R34 jumper relocated (small S3 amendment per spec update)
- ✓ NW/NE channel zones now FULLY CLEAR of S5 buck ICs + inductors + LDO
- ⚠ 20 S5 safety stack components placed OFF-BOARD pending follow-up adjudication

## 3D renders

- [`docs/renders/phase4_place_bec_relocate/top.png`](renders/phase4_place_bec_relocate/top.png) — 4 bucks visible in spine pocket; J10 supervisor in SW with Buck 5
- [`docs/renders/phase4_place_bec_relocate/bottom.png`](renders/phase4_place_bec_relocate/bottom.png) — 4 inductors B.Cu in spine pocket; R34 jumper moved

## Regression sims

All circuit-level sims regenerate identically (SPICE topology unchanged — placement doesn't change L/C/ESR values; routing parasitics will be re-characterized at Phase 5b autoroute):

- S2 ripple 65 mV unchanged
- S2↔S3 supervisor 12.3× hysteresis margin unchanged
- S2↔S6 BAT_V <1 µV at FC unchanged
- S3 OVP/UVP trip 27.008V/18.000V unchanged
- S3↔S6 Hall noise 8.002 mV unchanged
- All S5 internal + S5↔S1/S2/S3/S6 sims unchanged
- S6 DShot SI 7.8 ns rise unchanged

## Sequence

- **PR-A1 (merged #38)**: S2 C3/C4 +5mm outward
- **PR-A2 (this PR)**: S5 Bucks 1-4 + inductors + LDO → spine pocket; safety stack deferred
- **PR-A3 (next)**: Phase 4-place-channel-template — NW quadrant now fully free for S4 CH1
- **PR-A2-followup**: place deferred 20 S5 safety-stack components after PR-A3 establishes channel footprint

## Acceptance gates

| Gate | Status |
|---|---|
| Bucks 1-4 evicted from NW/NE channel zones | ✓ |
| 4 buck ICs in spine pocket F.Cu | ✓ |
| 4 inductors in spine pocket B.Cu | ✓ |
| LDO in spine pocket | ✓ |
| Supervisor relocated (SW corner with Buck 5) | ✓ |
| Buck 5 V9_VTX2 cluster preserved in SW | ✓ |
| S3 R34 jumper moved out of spine pocket | ✓ |
| `docs/PHASE4_SUBSYSTEMS.md` zone allowed/forbidden updated for all subsystems | ✓ |
| Symptom/Fix/Root cause/Prevention sections present | ✓ |
| Bbox-clean across all 15 subsystem checks | ✓ |
| Regression sims SPICE-identical | ✓ |
| 3D renders attached | ✓ |
| target.h md5 unchanged | ✓ `7a4549d27e0e83d3d6f1ffaf67527d24` |
| ⚠ 20 safety-stack components off-board (honest deviation flagged) | DEFERRED to PR-A2-followup |
