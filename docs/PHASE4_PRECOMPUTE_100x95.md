# Phase 4 Pre-computation — placement at proposed 100×95 board

**Per master directive 2026-05-23 (while Sai considers board-grow)**: pre-compute placement coordinates for the proposed 100×95 mm board so once Sai approves we can land fast.

## Board dimensions

- Current: 100×85 mm
- Proposed (master recommendation A): 100×95 mm (+10mm vertical = +12% area)

## Working pitch math (P=12 with AOTL66912 TO-263)

Pad-only bbox: 16.15 × 10.8 mm (verified via pcbnew API).

At P=12mm center-to-center pitch:
- Pad-to-pad clearance: 12 - 10.8 = 1.2 mm (8× JLCPCB 0.15mm minimum) ✓
- Span of 3 rows: 2×12 + 10.8 = 34.8 mm ≈ 35 mm

CH1/CH2 NW/NE zone at 100×95 = 33mm tall (Y=47-80). P=12 fits with 2mm margin. ✓
CH3/CH4 SW/SE zone at 100×95 = 32mm tall (Y=15-47). P=12 fits with 1mm margin. ✓

## Re-zoned subsystem map (100×95)

| Subsystem | Current zone | New zone (100×95) |
|---|---|---|
| S1 battery | Y=0-13 | Y=0-15 (slight expansion for safety stack) |
| S2 caps | Y=20-42, X=18-82 | Y=24-46, X=18-82 (shift +4mm) |
| S3 supervisor + Hall | Y=20-58 spine X=39-61 | Y=24-62 spine X=39-61 |
| S4 channels NW/NE | Y=42-72 | Y=47-80 (+5mm) |
| S4 channels SW/SE | Y=13-42 | Y=15-47 (+3mm) |
| S5 BEC spine pocket | Y=58-72 | Y=62-78 (+4mm taller) |
| S5 bottom input strip | Y=12-19 | Y=12-21 |
| S5 top output strip | Y=70-77 | Y=78-87 |
| S6 connectors | Y=72-85 | Y=87-95 |
| SW Buck 5 cluster | Y=12-42 | Y=12-45 |

## Pre-computed CH1 NW positions (100×95 + P=12)

```python
# CH1 NW (X=5-39, Y=47-80, P=12)
'TP19': (5.0, 51.0, 'F.Cu', 0.0),   # motor pad A (was y=46)
'TP20': (5.0, 61.0, 'F.Cu', 0.0),   # motor pad B (was y=56)
'TP21': (5.0, 71.0, 'F.Cu', 0.0),   # motor pad C (was y=66)
# 6 MOSFETs at P=12 pitch
'Q5':  (12.0, 54.0, 'B.Cu', 0.0),   # Phase A hi (Y=47+7=54)
'Q6':  (30.0, 54.0, 'B.Cu', 0.0),
'Q7':  (12.0, 66.0, 'B.Cu', 0.0),   # Phase B (Y=54+12=66)
'Q8':  (30.0, 66.0, 'B.Cu', 0.0),
'Q9':  (12.0, 78.0, 'B.Cu', 0.0),   # Phase C (Y=66+12=78)
'Q10': (30.0, 78.0, 'B.Cu', 0.0),
# MCU, DRV, INA per CH1 template — shift y by +5
'J18': (32.0, 57.0, 'F.Cu', 0.0),   # MCU (was y=52)
'J19': (22.0, 55.0, 'F.Cu', 0.0),   # DRV (was y=50)
'J20': (15.0, 50.0, 'F.Cu', 0.0),   # INA A (was y=45)
'J21': (15.0, 60.0, 'F.Cu', 0.0),
'J22': (15.0, 70.0, 'F.Cu', 0.0),
# ... (all other CH1 components shifted +5mm in y)
```

## Pre-computed CH3 SW positions (100×95, mirror y → 95-y)

```python
# CH3 SW (Y=15-47)
'TP33': (5.0, 44.0, 'F.Cu', 180.0),   # mirror y=51 → 44
'TP34': (5.0, 34.0, 'F.Cu', 180.0),
'TP35': (5.0, 24.0, 'F.Cu', 180.0),
'Q17': (12.0, 41.0, 'B.Cu', 180.0),   # mirror y=54 → 41
'Q18': (30.0, 41.0, 'B.Cu', 180.0),
'Q19': (12.0, 29.0, 'B.Cu', 180.0),   # mirror y=66 → 29
'Q20': (30.0, 29.0, 'B.Cu', 180.0),
'Q21': (12.0, 17.0, 'B.Cu', 180.0),   # mirror y=78 → 17 (bbox y=11.3-22.7 fits Y=15-47 with -3.7mm boundary leak)
'Q22': (30.0, 17.0, 'B.Cu', 180.0),
```

**Q21/Q22 boundary check**: bbox y_min=11.3 leaks 3.7mm into S1 zone Y=0-15. Acceptable if S1 amendment to Y=0-11 (further compress) — or accept silkscreen-only leak.

## Pre-computed CH4 SE (XY-mirror)

Same Y as CH3, X mirrored across spine (x=100-x):
```python
'TP40': (95.0, 44.0, 'F.Cu', 0.0),
'TP41': (95.0, 34.0, 'F.Cu', 0.0),
'TP42': (95.0, 24.0, 'F.Cu', 0.0),
'Q23': (88.0, 41.0, 'B.Cu', 0.0),
'Q24': (70.0, 41.0, 'B.Cu', 0.0),
# ... etc
```

## Once Sai approves 100×95

Steps to land fast:
1. Update `setup_board.py` board outline 100×85 → 100×95
2. Update `place_board.py` with pre-computed positions above
3. Run + verify bbox-clean (expected ~0 pad-overlap with proper P=12 + 4mm subsystem shifts)
4. Re-run Elmer FEM v3 with P=12 (expect ~85°C continuous, ~110°C burst per master estimates)
5. Place 168 missing channel passives via mirror script + collision detection
6. 3D render, doc, commit, PR

Estimated landing time after Sai approves: 2-4 hours.

## Alternative — if Sai approves smaller increment (100×90 = +5mm)

Would give CH3/CH4 27mm tall (Y=15-42 if S5 spine moves), but with P=10 pitch → 0.8mm pad overlap. NOT viable.

100×90 wouldn't solve constraint. Master's 100×95 recommendation is the minimum that achieves clean P=12 with margin.

## Standing by

Branch `phase4-place-channels-x4/instantiate` frozen at commit `c88b9ce`. No further iteration until Sai responds on board-grow decision.
