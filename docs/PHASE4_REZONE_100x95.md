# Phase 4 re-zone spec amendments for 100×95 board (PR-A4-b)

**Per master PR-A4 5-sub-PR plan, A4-b (docs-only).** After A4-a merged board outline 100×85 → 100×95 (PR #41), subsystem ALLOWED zones must be re-spec'd to use the new vertical area.

## Symptom / Fix / Root cause / Prevention

**Symptom**: Old ALLOWED zones referenced Y=0-85 board height. With 100×95 board, zones at Y=72-85 (S6) and Y=58-72 (S5 spine pocket) no longer align with new board geometry; subsystems would either compress unnecessarily or violate the new available area boundaries.

**Fix**: Shift relevant subsystem ALLOWED zones by +10mm to use the new top 10mm of board:
- S2 +4mm (Y=20-42 → Y=24-46)
- S5 spine pocket +10mm (Y=58-72 → Y=68-82)
- S5 top strip +10mm (Y=70-77 → Y=80-87)
- S6 +10mm (Y=72-85 → Y=82-95)
- CH1/CH2 NW/NE zones shifted +5mm (Y=42-72 → Y=47-80, +1mm extra room)
- CH3/CH4 SW/SE zones shifted +2mm (Y=13-42 → Y=15-47, +3mm extra room)
- S1 narrows to Y=0-13 (was Y=0-20 with 2×2 RP cluster — now single-row Q1-Q4 fits Y=0-13)
- S3 spine unchanged (Hall+supervisor at Y=20-58)

**Root cause**: Original 100×85 zones sized for that board height. Board grow at A4-a is mechanical; subsystem spec must follow to authorize component placements at the new coordinates.

**Prevention**: PHASE4_SUBSYSTEMS.md zone amendments are scripted-friendly (single Y-shift constant per zone). Future board-size changes apply same pattern: amend zone Y bounds, then re-place components per shifted zones.

## Zone amendment table

| Subsystem | Before (100×85) | After (100×95) | Δ | Notes |
|---|---|---|---|---|
| S1 Battery | Y=0-20 | Y=0-13 | -7 | Single-row RP cluster (already restored PR-A4 stage-2) |
| S2 Bulk caps | Y=20-42 | Y=24-46 | +4 | Allow S1 single-row to settle; C3/C4 still at x=25/75 |
| S3 Hall+supervisor | Y=20-58 | Y=20-58 | 0 | Central spine unchanged |
| S4 CH1 NW | Y=42-72 | Y=47-80 | +5 | 33mm tall, fits P=12 FET pitch |
| S4 CH2 NE | Y=42-72 | Y=47-80 | +5 | Same as CH1 |
| S4 CH3 SW | Y=13-42 | Y=15-47 | +2 | 32mm tall, fits P=12 |
| S4 CH4 SE | Y=13-42 | Y=15-47 | +2 | Same as CH3 |
| S5 spine pocket | Y=58-72 | Y=68-82 | +10 | Top edge of pocket aligns with S5 top strip |
| S5 top strip | Y=70-77 | Y=80-87 | +10 | Output-side passives |
| S5 bottom strip | Y=12-19 | Y=14-19 | +2 (start), 0 (end) | Slight compression to clear S1 single-row |
| S5 SW corner (Buck 5) | Y=22-38 | Y=22-38 | 0 | Buck 5 cluster unchanged |
| S6 connectors | Y=72-85 | Y=82-95 | +10 | Top edge — new corner mount-hole zone |

## What's NOT in this PR (subsequent A4-* PRs)

- **A4-c**: actual component re-placement at shifted Y coordinates + CH1 P=12 + Elmer FEM v3 re-sim
- **A4-d**: CH2/3/4 mirror instantiate via collision-detection
- **A4-e**: 168 channel passives + cross-channel EMC sims

## Verification

- ✓ docs/PHASE4_SUBSYSTEMS.md §S1-§S6 ALLOWED + FORBIDDEN zones updated
- ✓ Zone map preamble (§2) updated for 100×95 board geometry
- ✓ No `place_board.py` changes (spec-only PR)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ All existing 166 placements still in PCB file (not changed by this PR)

## Acceptance gates

| Gate | Status |
|---|---|
| §S1-§S6 zones updated for 100×95 board | ✓ |
| Zone map preamble updated | ✓ |
| 4-section S/F/R/P doc | ✓ |
| ALLOWED + FORBIDDEN enumeration preserved per locked rule | ✓ |
| One docs-only PR | ✓ |
| target.h md5 unchanged | ✓ |
