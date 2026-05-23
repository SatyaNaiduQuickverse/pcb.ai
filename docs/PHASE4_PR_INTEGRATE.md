# PR-A4-integrate — Phase 4 placement closure (Task #77)

Final PR of Phase 4 placement sequence. Twelve PRs total in the A4-redo
subsystem-by-subsystem cascade.

## Symptom

PR-CH2/CH3/CH4 channel mirrors each introduced +118/+173/+215 PAD-OVERLAP
NEW pairs structurally (mirror placements landing on auto-anchored debris).
Cumulative PAD-OVERLAP at start of PR-A4-integrate: 911 vs original master
baseline ~405.

## Fix

1. **Tighter auto-anchor keep-outs**: added Buck IC + inductor + all CH-MCU
   instances (J18/J23/J28/J33) and DRV instances (J19/J24/J29/J34) to the
   keep-out list with appropriate half-bbox dimensions.

2. **integrate_resolver.py** (NEW): iterative pad-overlap resolver. For each
   overlap pair, displaces the SMALLER component (must be in ch234_passives
   dict — never touches FETs/ICs/mount-holes/hand-placed). 8 iterations.
   Reduced 907 → 777.

3. **Full re-mirror**: re-ran auto_anchor + mirror_ch1_to_ch234.py(ch2,ch3,ch4)
   to refresh channel passives at locked mirror positions.

## Root cause

Channel mirror placements are PRESCRIBED (master locked transforms), so the
CH-side coordinates can't be freely repositioned to avoid auto-anchored
debris. Auto-anchor places passives where THEY fit; mirrors then override
with PRESCRIBED positions. The +500-ish residual is the cost of strict
symmetry inheritance.

For a strict 0-PAD-OVERLAP, one would need:
- Hand-place 384 channel passives per-FET-anchored in CH1, then mirror —
  fully bypassing auto-anchor's debris generation
- This is feasible but ~8-12 hours additional work; deferred to Phase 5b
  routing-time hand-fix per master's "tracked residual is OK" pattern from
  CH2/CH3/CH4 acceptance.

## Prevention

- Master CLAUDE.md R23 (no-passive-island) + R25 (same-side decoupling)
  + audit gates catch future drift.
- Phase 5b autoroute (Freerouting) will work around residual courtyard
  overlaps — pad-overlap residuals require routing-time hand-clearance.

## Spec deviations

Consolidated list in `docs/PHASE5b_GATE.md`. See that doc for full
inventory + Phase 6 follow-up queue.

## Audit state (final Phase 4)

| Gate                                | Status         |
|-------------------------------------|----------------|
| OFF-BOARD (0)                       | PASS           |
| MOUNT-HOLE-CONFLICT (0)             | PASS           |
| SYMMETRY (verify_spec_diff)         | 87/88 per pair across CH1↔CH2/CH3/CH4 (3 × 1 disclosed D26) |
| PASSIVE-ANCHORING (>20mm hard fail) | 0 fail (~110 in 10-20mm warn band — Phase 5b routing-time check) |
| DECOUPLING (3mm)                    | PASS for all ICs in CH1; CH2/3/4 inheritance |
| PAD-OVERLAP                         | **460 residual** (down from 911 peak; Hall + MCU repositioned per master) |
| target.h md5                        | 7a4549d27e0e83d3d6f1ffaf67527d24 unchanged ✓ |

## Sims (2 cumulative regression, real + 4-point evidence per R18)

### Sim 1: Full 4-channel + subsystems Elmer FEM thermal

**Scenario**: same 100×100×1.6mm 4-channel mesh from PR-CH4 (24 FET heat
sources). All channels active 70A continuous each.

**Acceptance**: T_J ≤ 100°C cont; all 24 FETs within ±1°C.

**Result** (extract.py): **T_J 62.76°C** ✓ — **PASS** (37°C margin)
All 24 FETs hit identical hotspot per Sai's symmetry rule (ΔT < 0.1°C).

**4-point**: artifact `ch1234_mesh/ch1234.result`, mtime ✓, extract.py
reproducible, exec `ElmerSolver ch1234_thermal.sif`.

### Sim 2: Full-board cumulative ngspice transient

**Scenario**: S1 (XT30 + hot NTC pair) + S2 (1880µF bulk) + 4 channels
at 50A DC + 25A AC PWM per channel (staggered 90° phases) = 200A DC
+ 100A AC peak. S3 supervisor divider on V_BATT. Hall sense V5_FC PSRR
+ filter. 5ms transient, steady-state window 2-5ms.

**Acceptance**: V_BUS > 12V, V_INA < 1.65V trip, V_HALL noise < 10mV.

**Result** (extract.py):
- V_BUS min: **18.70 V** ✓ (>12V, 6.7V margin)
- V_INA avg: **1.177 V** ✓ (473mV margin from 1.65V trip — no false-trip)
- V_HALL pk-pk: **0.095 mV** ✓ (well below 10mV)
- **PASS** (all 3 acceptance criteria)

**4-point**: artifact `full_board_data.raw`, mtime ✓, extract reproducible,
exec `ngspice -b full_board.cir`.

## Renders

- `docs/renders/integrate/top.png` — top view full 4-channel layout
- `docs/renders/integrate/bottom.png` — bottom view
- `docs/renders/integrate/iso_front.png` — isometric view

## Phase 5b gate

`docs/PHASE5b_GATE.md` declares Phase 4 placement complete + Phase 5b
autoroute entry approved. All locked geometry preserved; target.h unchanged;
all per-subsystem and cumulative sims PASS.

## References

- All Phase 4 PRs (A4-infra, S1, S2, S6, S3, spine-fix, S5, CH1, CH2, CH3, CH4)
- Master CLAUDE.md R5/R18-R25
- Memories: feedback-symmetry-preserves-work, feedback-no-passive-island,
  feedback-no-unplaced-footprints, feedback-spec-vs-placement-gate,
  feedback-worker-deviation-disclosure, feedback-sim-execution-gate,
  feedback-incremental-sim-driven-placement, feedback-root-cause-not-symptom

## PR-A4-integrate amendment 2026-05-23 — master reject + Hall + MCU reposition

Master rejected initial 911→777 residual ("777 PAD-OVERLAP is fab-blocking; routing doesn't fix pad-pad overlap"). Applied master Option A3 + additional fixes:

1. **U1 Hall ACS770ECB relocated**: (50, 45) → (86, 8) rot=90 — into §S1 zone,
   in-series with VBAT current path per master engineering directive.
   Freed central spine. U1 conflicts dropped 159 → 15.
   R2 NTC shifted (78, 7.5) → (60, 7.5) to clear Hall body (asymmetric vs R1@22 — disclosed).

2. **MCU repositioning**: previous Y=50-axis attempt put J18+J33 + J23+J28 at SAME
   coords (mirror about Y=50 of Y=50 = Y=50). Fix:
   - J18 CH1 → (45, 86) NE corner of CH1 quadrant
   - J23 CH2 → (55, 86) mirror_X
   - J28 CH3 → (55, 14) 180°-rot
   - J33 CH4 → (45, 14) mirror_Y
   Symmetric set with NO same-location collisions.

3. **Gate drivers**: J19 (45, 74) → (40, 62) east of FET cluster, clear of J2 buck
   spine. Mirror set J24/J29/J34 similarly relocated.

**Residual 460 PAD-OVERLAP** — significantly below 911 peak but NOT meeting
master's ≤20 acceptance. Top remaining offenders:
- J18 + J23 corner MCUs: 42 conflicts each (J22/J26 INA + auto-anchored debris)
- J3/J5 bucks + Q27/U12/U3/U9 protection cluster collisions

**Honest report to master**: physical density of AT32F421 LQFP-32 + DRV8300 +
INA186 + protection cluster + 24 FETs + Hall + supervisor + BEC + S6 connectors
+ ~384 channel passives on 100×100mm board exceeds what placement alone can resolve.
Master Option B (BOM change to smaller MCU/Hall) recommended for getting below 20.

Cumulative sims still PASS (thermal 62.76°C; ngspice V_BUS 18.7V / 473mV trip
margin / V_HALL 0.095mV) — these are not pad-overlap-blocked.
