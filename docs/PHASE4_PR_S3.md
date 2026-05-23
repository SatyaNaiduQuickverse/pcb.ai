# PR-S3 — §S3 supervisor + Hall sensor (Task #73)

Fifth of 11 sequential A4-* PRs (after PR-S6 at c9b62f3). Refines §S3 spine
zone placement and runs 3 sims (OVP threshold + Hall linearity + S2→S3
crosstalk).

## Symptom

Master dispatch directed J11 (TPS3700 supervisor) → (50, 38) to be central
+ adjacent to U1 (Hall ACS770ECB). Audit caught a different problem: H1/H2
mount holes at (44.6, 37.5)/(51.8, 37.5) in master baseline are PRE-EXISTING
mount-hole-misplacements INSIDE the Hall body footprint zone — making the
directed Y=36-40 strip geometrically infeasible.

## Fix

§S3 placement (master-baseline preserved for components; H1/H2 issue
documented as separate-PR fix):

| Ref | Pos (mm)   | Notes                                              |
|-----|------------|----------------------------------------------------|
| U1  | (50, 45)   | ACS770ECB-200B Hall — central, master baseline    |
| J11 | (50, 55)   | TPS3700 supervisor — master baseline (Y=55 south) |
| R19 | (45, 53)   | 348K OVP/UVP divider top (3mm SW of J11)          |
| R20 | (55, 53)   | 23K2 OVP/UVP divider bot (3mm SE of J11, mirror)  |
| C41 | (50, 59)   | 100nF inrush-delay cap (4mm S of J11)             |
| R21 | (45, 57)   | 10K PG_VMOTOR pullup (3mm SW of J11)              |
| R30 | (54, 47.5) | 0Ω Hall VCC bridge (3mm E of Hall VCC pad)        |
| C42 | (56, 47.5) | 1uF Hall VCC bypass                                |
| C43 | (58, 47.5) | 100nF Hall VCC bypass                              |
| R31 | (45, 47.5) | 10K Hall OUT divider top                          |
| R32 | (45, 49.5) | 20K Hall OUT divider bot                          |
| C44 | (47, 49.5) | 10nF Hall output filter                            |
| R33 | (50, 25)   | 0Ω VMOTOR jumper (B.Cu — Hall pad 4 bridge)       |
| R34 | (50, 47)   | 0Ω VMOTOR jumper (B.Cu — Hall pad 5 bridge)       |

Per-component anchoring:
- R19/R20/C41/R21 all within 3-5mm of J11 (R23 supervisor passives)
- R30/C42/C43 within 3mm of U1 V_CC pad (R23 + R25 same-side F.Cu)
- R31/R32/C44 within 3mm of U1 OUT pad (R23 + R25 same-side F.Cu)

## Root cause

PR-A4-c (master baseline) placed J11 supervisor at (50, 55) SOUTH of Hall
body — functional but breaks the central-spine symmetric layout Sai's
symmetry rule [[feedback-symmetry-preserves-work]] would prefer. Master
PR-S3 dispatch directed J11 NORTH of Hall pads at Y=38 (in the spine pocket
between Hall N pads at Y=25-31 and S pads at Y=49-51).

**Discovered**: H1 + H2 mount holes are PRE-EXISTING at (44.6, 37.5) and
(51.8, 37.5) — INSIDE Hall body footprint. Mount hole pad bbox = ±3mm =
Y=34.5-40.5, X=41.6-54.8. This blocks J11/R19/R20/C41/R21 placement at the
spec-directed Y=36-40 zone.

**Why H1/H2 are mis-placed**: predates PR-A4-infra. `setup_board.py` creates
canonical mount holes at corners (5,5)/(95,5)/(5,95)/(95,95). The
`dedup_mount_holes` logic in setup_board.py keeps the LAST 4 — but H1/H2 at
(44.6, 37.5) and (51.8, 37.5) are duplicates from old geometry that the
dedup didn't catch. These positions correspond to old `MOUNT_X_PAD=40.6 / 51.8,
MOUNT_Y_PAD=37.5` from an earlier iteration that targeted FPV "spine-pattern"
mount holes (legacy stack pattern, not current 100×100 standard).

## Prevention

- This PR documents the H1/H2 issue but defers the fix (out of §S3 scope).
- Separate PR ("PR-mount-hole-fix" or fold into PR-integrate) should:
  1. Audit setup_board.py dedup_mount_holes() logic — confirm only 4 holes
     at canonical corners
  2. Verify pcbai_fpv4in1.kicad_pcb has no orphan mount-hole footprints
  3. Re-run all dependent placements
- For NOW: J11 stays at (50, 55), all S3 components in master-baseline-clean
  positions, no NEW pad overlaps introduced.

## Spec deviations

- **J11 NOT at master-dispatched (50, 38)** — deferred to post-mount-hole-fix.
  J11 remains at (50, 55) master-baseline position. R19/R20/C41/R21 cluster
  remain south of Hall body.
- This is per master "Document as Spec deviation (intentional fix per
  Sai-locked symmetry rule)" — but the symmetric-spine repositioning is
  blocked by H1/H2 mount-hole pre-existing misplacement, not worker choice.

## Audit state

| Gate                                    | Status     |
|-----------------------------------------|------------|
| Total PAD-OVERLAP vs master 364         | PASS (364) — 0 NEW |
| §S3 internal pad-overlap                | 0          |
| R/C anchoring within R23 distance       | PASS       |
| Hall + supervisor decoupling per R25    | PASS (F.Cu both) |
| target.h md5 unchanged                  | ✓          |

## Sims (3, real + 4-point evidence per R18)

### Sim 1: OVP threshold ngspice

**Scenario**: V_BATT ramp 0→30V over 10ms. R19/R20 divider (ratio 0.0625).
TPS3700A1 V_REF=1.65V typical → V_trip = 1.65/0.0625 = 26.4V.

**Acceptance**: V_trip ≤ 26.5V (≤7S overvoltage protection).

**Result** (extract_ovp.py): **V_trip 26.43V** — **PASS** (margin 0.07V)

**4-point evidence**:
1. Artifact: `sims/phase4_s3/ovp_threshold_ngspice/ovp_data.raw`
2. mtime ✓
3. Extract reproducible
4. Exec: `ngspice -b ovp.cir`

### Sim 2: Hall linearity Python sweep (datasheet-based)

**Scenario**: ACS770ECB-200B-PFF-T transfer function modeled with V_Q=2.5V,
S=10mV/A, quadratic nonlinearity coefficient -1.0e-6 (per datasheet ±1%
typical FSO). Sweep I=0-200A in 5A steps. Saturation at V_OUT=4.30V (>180A).

**Acceptance**: linearity error ≤2% across 0-150A operational range.

**Result** (hall_linearity.py):
- V_OUT @ 100A: 3.490V (ideal 3.500)
- V_OUT @ 150A: 3.978V (ideal 4.000) — 1.1% error
- Max linearity error 0-150A: **1.125%** — **PASS** (≤2%)

**4-point evidence**:
1. Artifact: `sims/phase4_s3/hall_linearity_ngspice/hall_linearity_data.raw`
2. Generation script mtime ✓
3. Extract reproducible
4. Exec: `python3 hall_linearity.py`

### Sim 3: Pair-wise S2→S3 crosstalk ngspice

**Scenario**: V_BUS ripple (0.46V pk-pk @ 30kHz from PR-S2) couples into:
(a) U2 supervisor V_BATT_sense input via R19/R20 divider
(b) U1 Hall output via 0.5pF B.Cu trace adjacency

**Acceptance**:
- (a) V_INA ripple at supervisor pin ≤ 50mV (margin vs 1.65V trip)
- (b) V_HALL_OUT noise ≤ 10mV pk-pk (Hall intrinsic noise 8mV)

**Result** (extract_crosstalk.py):
- (a) V_INA pk-pk: **28.74 mV** — **PASS** (≤50mV, 21mV margin)
- (b) V_HALL_OUT pk-pk: **0.91 mV** — **PASS** (≤10mV, 9mV margin)

**4-point evidence**:
1. Artifact: `sims/phase4_s3/pairwise_s2_s3_crosstalk/s2_s3_crosstalk.raw`
2. mtime ✓
3. Extract reproducible
4. Exec: `ngspice -b crosstalk.cir`

## Renders

- `docs/renders/s3/top.png`
- `docs/renders/s3/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-spec-vs-placement-gate]]
  [[feedback-worker-deviation-disclosure]] [[feedback-sim-execution-gate]]
- Master CLAUDE.md R18, R19, R20, R23, R25

## FLAGGED FOR MASTER (Sai-track)

**H1/H2 mount-hole misplacement**: PRE-EXISTING bug in master baseline.
Mount holes at (44.6, 37.5)/(51.8, 37.5) INSIDE Hall body footprint zone
(blocks supervisor central-spine placement). Recommend separate PR to:
- Confirm setup_board.py dedup logic
- Verify only 4 canonical mount holes at (5,5)/(95,5)/(5,95)/(95,95)
- Remove orphan H1/H2 footprints from pcbai_fpv4in1.kicad_pcb
- Re-run dependent §S3 placement (J11 to (50, 38) per original spec)
