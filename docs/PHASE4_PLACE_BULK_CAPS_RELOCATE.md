# Phase 4-place-bulk-caps-relocate — S2 amendment (PR-A1)

**Per master adjudication 2026-05-22 Option A**: S2 C3/C4 caps relocated outward 5mm to clear NW/NE channel zone intrusion. First of 3 PRs (PR-A1 → PR-A2 → PR-A3) unblocking Phase 4-place-channel-template.

## Change

| Ref | Position before | Position after | Reason |
|---|---|---|---|
| C3 | (30, 40) | **(25, 40)** | C3 bbox y_max=45.5 was intruding 3.5 mm into S4 NW channel zone (Y=42-58 strip). Move 5mm west; new bbox x=(18.1, 31.7), well outside NW channel inner edge x=39. |
| C4 | (70, 40) | **(75, 40)** | C4 bbox mirror — intruded NE channel zone. Move 5mm east; new bbox x=(68.1, 81.9), well outside NE channel inner edge x=61. |

C1/C2 at y=24 unchanged (already clear of channel zones starting y=42).

## Bbox-clean verification

After 5mm outward shift of C3/C4:
- S1-/S2-/S3-/S5-/S6-internal: 0/0/0/0/0
- All 10 pair-wise combinations: 0
- Total subsystem placements: 86 (preserved from PR #37)

## Regression sims (SPICE topology unchanged)

All circuit-level sims regenerate identically — placement doesn't affect capacitance/ESR/inductance values, only routing parasitics (which will be re-characterized at Phase 5b autoroute):

| Sim | Result | Status |
|---|---|---|
| S2 ripple (PR #34) | 65 mV pk-pk @ 30 kHz | Unchanged |
| S2↔S3 supervisor (PR #35) | 4.06 mV V_BATT_DIV / 12.3× hysteresis margin | Unchanged |
| S2↔S6 BAT_V (PR #36) | 0.21 µV at FC ADC | Unchanged |
| S5↔S2 combined RSS (PR #37) | 65.09 mV | Unchanged |

## Verification

- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ 0 same-layer bbox overlaps (all 15 subsystem checks)
- ✓ Only C3/C4 positions changed; all other subsystems preserved
- ✓ 3D renders attached
- ✓ NW/NE channel inner edge x=39/61 now clear of S2 cap bbox

## 3D renders

- [`docs/renders/phase4_place_bulk_caps_relocate/top.png`](renders/phase4_place_bulk_caps_relocate/top.png)
- [`docs/renders/phase4_place_bulk_caps_relocate/bottom.png`](renders/phase4_place_bulk_caps_relocate/bottom.png)

## Sequence (per master adjudication)

1. **PR-A1 (this PR)**: S2 C3/C4 relocate — unblocks NW/NE channel zone Y-boundary intrusion
2. **PR-A2 (next)**: Phase 4-place-bec-relocate — Bucks 1+2+3+4 from NW/NE strips → central spine pocket
3. **PR-A3 (final)**: Phase 4-place-channel-template — full CH1 placement in cleared NW quadrant with 10 sims

## Acceptance gates

| Gate | Status |
|---|---|
| Only C3, C4 positions changed (5mm outward shift) | ✓ |
| Bbox-clean across all 15 checks | ✓ |
| Regression sims identical (SPICE topology unchanged) | ✓ |
| target.h md5 unchanged | ✓ |
| 3D render attached | ✓ |
| One small PR | ✓ |
