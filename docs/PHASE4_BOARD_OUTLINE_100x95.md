# Phase 4 board outline grow 100×85 → 100×95 (PR-A4-a)

**Per Sai 2026-05-23 approved Option A board grow + master PR-A4 5-sub-PR split.**

## Symptom / Fix / Root cause / Prevention

**Symptom**: 4-channel template instantiation at 100×85 board failed bbox-clean (45 pad-overlap defects). Root cause analysis identified AOTL66912 TO-263 pad-only bbox = 10.8mm tall; minimum P=12 pitch needed for clean 3-row layout; CH3/CH4 SW/SE quadrants at 29mm tall couldn't fit 33mm-tall P=12 layout.

**Fix**: Board height grown 85 → 95 mm (+12% area). Gives CH3/CH4 zones 32mm tall (Y=15-47) which accommodates P=12 layout with 1mm margin.

**Root cause**: Phase 4b-REDO3 board height 85mm was sized for signal density (Freerouting pass) but didn't account for symmetric R6 motor-pad-anchored architecture × 4 channels with TO-263 pad geometry. Original sizing only considered NW quadrant solo (single channel).

**Prevention**: REQUIREMENTS.md updated with explicit board-grow rationale; future board-size decisions must validate against:
1. All subsystem zones with explicit pad-bbox math (not just nominal package sizes)
2. Symmetric architectural patterns (×N channel instantiation) at the candidate size
3. Sai's locked rules + commercial-product-class criteria

## Change

| Item | Before | After |
|---|---|---|
| Board outline | 100×85 mm | 100×95 mm |
| Mount holes | (5,5)/(95,5)/(5,80)/(95,80) | (5,5)/(95,5)/(5,90)/(95,90) |
| Layer stackup | 8L unchanged | 8L unchanged |
| `BOARD_H` constant | 85.0 | 95.0 |

## What's preserved

- 100×85 placements (S1+S2+S3+S5+S6 + S4 CH1 = 166 components) all stay at original (x, y) positions
- No subsystem zones re-zoned in this PR (that's A4-b)
- No channel re-placement (that's A4-c)
- No CH2/3/4 instantiation (that's A4-d/e)

## Verification

- ✓ setup_board.py regenerated `pcbai_fpv4in1.kicad_pcb` with new outline
- ✓ Mount holes at new corners (5,5)/(95,5)/(5,90)/(95,90)
- ✓ PAD-OVERLAP defects: **0** (existing components don't conflict with new outline)
- ✓ Silkscreen-courtyard touches: 19 (unchanged, Phase 5c polish)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ Total board area: 9500 mm² (was 8500 mm², +12%)

## 3D renders

- [`docs/renders/phase4_board_outline_100x95/top.png`](renders/phase4_board_outline_100x95/top.png)
- [`docs/renders/phase4_board_outline_100x95/bottom.png`](renders/phase4_board_outline_100x95/bottom.png)

Renders show 100×95 outline with mount holes at corners; all existing subsystem placements (S1-S6 + CH1 NW) preserved.

## Next PRs in sequence

- **A4-b**: re-zone subsystem ALLOWED zones (S2 +4mm, S5/S6 +10mm shift) — spec/doc only
- **A4-c**: CH1 P=12 re-placement + S2-S6 batch shift + Elmer FEM v3
- **A4-d**: CH2/3/4 mirror instantiate via collision-detection
- **A4-e**: 168 channel passives + cross-channel EMC sims

## Acceptance gates

| Gate | Status |
|---|---|
| Board outline 100×95 | ✓ |
| Mount holes shifted | ✓ |
| 0 PAD-OVERLAP defects | ✓ |
| 3D render PNG attached | ✓ |
| target.h md5 unchanged | ✓ |
| 4-section S/F/R/P doc | ✓ |
| One small PR | ✓ |
