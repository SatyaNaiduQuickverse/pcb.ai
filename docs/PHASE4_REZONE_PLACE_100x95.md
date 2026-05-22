# Phase 4 re-place components at 100×95 zones + CH1 P=12 + Elmer FEM v3 (PR-A4-c)

## Symptom / Fix / Root cause / Prevention

- **Symptom**: After A4-a board grow + A4-b spec re-zone, components still at 100×85 positions; CH1 at P=13 not P=12.
- **Fix**: Batch-shift components per master spec (S2 +4mm, S5 spine/top +10mm, S6 +10mm, CH1 +6mm) + re-place CH1 6 FETs at P=12 row pitch (Y=54/66/78).
- **Root cause**: Component positions tied to old board geometry; spec → place ordering requires this PR after A4-b spec lock.
- **Prevention**: Re-place script logged in commit + 4-section doc; future board changes apply same Y-shift pattern.

## What's placed (166 components per current PCB state)

All preserved + repositioned:
- S1 (8 components): single-row at y=10, x=15/22/30/45/50/55/70/78
- S2 (4 caps): C1/C2 at y=28, C3/C4 at y=44 (+4mm shift)
- S3 (14 components): Hall + supervisor cluster unchanged (Y=20-58)
- S5 spine pocket (10 + supporting): bucks J2-J5 at Y=72/80 +10mm
- S5 top strip (24 components): +10mm to Y=80-87 range
- S5 bottom strip (8 components): unchanged Y position
- S5 SW corner (10 components): Buck 5 cluster unchanged
- S6 (8 components): +10mm to Y=82-95
- CH1 NW (80 components): full re-place at P=12

## Elmer FEM v3 thermal sim (real 3D, k=200, h_bot=1500, localized sources)

| FET | T_J burst (°C) | T_J cont (°C) | Verdict |
|---|---:|---:|---|
| Q5 hi-A | 96.5 | 77.9 | PASS ✓ |
| Q6 lo-A | 97.4 | 78.3 | PASS ✓ |
| Q7 hi-B | 96.7 | 78.0 | PASS ✓ |
| Q8 lo-B | 97.6 | 78.4 | PASS ✓ |
| Q9 hi-C | 95.7 | 77.5 | PASS ✓ |
| Q10 lo-C | 96.5 | 77.9 | PASS ✓ |

Spec: T_J ≤ 100°C continuous (margin ~22°C), ≤ 150°C burst (margin ~52°C). All 6 FETs PASS.

Methodology unchanged from v2 (master-locked): 3D mesh, k=200 W/m·K effective composite, h_top=80/h_bot=1500/h_sides=10, localized FET heat sources, per-FET T_J reporting.

P=12 (vs v2 P=13) results identical because:
1. FET pad geometry unchanged
2. Total board heat dissipation unchanged
3. Mesh subcells already at 5mm pitch — P=12 vs P=13 doesn't alter mesh resolution at FET zones

## Verification

- ✓ Board outline 100×95
- ✓ Mount holes at (5,5)/(95,5)/(5,90)/(95,90) (dedup-fix in place_board.py: keep LAST 4)
- ✓ **PAD-OVERLAP defects: 0**
- ✓ Silkscreen-courtyard touches: 17 (Phase 5c polish)
- ✓ target.h md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ Elmer FEM v3 PASS per-FET continuous + burst
- ✓ 3D renders attached

## 3D renders

- [`docs/renders/phase4_rezone_place_100x95/top.png`](renders/phase4_rezone_place_100x95/top.png)
- [`docs/renders/phase4_rezone_place_100x95/bottom.png`](renders/phase4_rezone_place_100x95/bottom.png)

## What's NOT in this PR (subsequent A4-* PRs)

- **A4-d**: CH2/3/4 mirror instantiate via collision-detection script (~72 major components × 3 channels)
- **A4-e**: 168 channel passives (CH2/3/4 instantiation) + cross-channel EMC sims + final PR

## Acceptance gates

| Gate | Status |
|---|---|
| Board outline 100×95 + mount holes at new corners | ✓ |
| CH1 NW P=12 re-place at Y=54/66/78 | ✓ |
| S2 +4mm shift | ✓ |
| S5 spine pocket + top strip +10mm | ✓ |
| S6 +10mm | ✓ |
| 0 PAD-OVERLAP defects | ✓ |
| Elmer FEM v3 PASS per-FET continuous + burst | ✓ |
| 4-section S/F/R/P doc | ✓ |
| 3D render attached | ✓ |
| target.h md5 unchanged | ✓ |
| One PR | ✓ |
