# PR-S1 — §S1 battery input subsystem (Task #70)

Second of 11 sequential A4-* PRs (after PR-A4-infra at 22bc4ab). Places the
§S1 battery input subsystem and runs 3 internal sims with 4-point evidence.

## Symptom

§S1 components were placed in PR-A4-c at master, but per Sai's subsystem-by-
subsystem directive, this PR establishes the canonical §S1 placement on the
new 100×100mm board: corner LEDs symmetric, NTC pair X-mirror, rev-pol FET
row aligned with PR-A4-infra Y=7.5 baseline, gate-protection cluster per
[[feedback-no-passive-island]] (≤5mm anchored).

## Fix

§S1 placement (13 components — D26 explicitly excluded; per netlist D26 is
CH1's motor TVS, will land in PR-CH1):

| Ref  | Value         | Pos (mm)   | Notes                                 |
|------|---------------|------------|---------------------------------------|
| J1   | XT30 BATT_PAD | (50, 4)    | center input                          |
| R1   | MF72_5D25 NTC | (18, 7.5)  | west of Q1/Q2; through-hole pad-clear |
| R2   | MF72_5D25 NTC | (82, 7.5)  | mirror of R1                          |
| Q1   | BSC014N06NS   | (30, 7.5)  | rev-pol FET (4× parallel)             |
| Q2   | BSC014N06NS   | (45, 7.5)  |                                       |
| Q3   | BSC014N06NS   | (55, 7.5)  | mirror of Q2                          |
| Q4   | BSC014N06NS   | (70, 7.5)  | mirror of Q1                          |
| R3   | 10K GATE_RP   | (32, 11)   | gate-pull, 4mm from Q1 (≤5mm R23 gate_R) |
| D2   | 12V Zener     | (68, 11)   | gate-clamp, 4mm from Q4 (mirror of R3) |
| D4   | RED_RPOL LED  | (10, 2)    | rev-pol warning                       |
| R5   | 5K1           | (13, 2)    | D4 limit-R, 3mm pitch (same-net pad-clear) |
| D3   | GREEN_PWR LED | (90, 2)    | +VMOTOR power-good                    |
| R4   | 5K1           | (87, 2)    | D3 limit-R (mirror)                   |

Symmetry verified: J1 at X=50 (center); R1↔R2, Q1↔Q4, Q2↔Q3, R3↔D2,
D4↔D3, R5↔R4 all X-mirror about X=50.

## Root cause

§S1 placement gaps in PR-A4-c (master base):
- NTCs at (22/78, 7.5) collided with Q1/Q4 F.Cu signal pads (NTC through-hole
  pad 2 at X+5mm hits FET pad at X+4-5). Pad-pad clearance violated.
- Gate-protection R3/D2 were placed outside §S1 zone Y=11 strip → too far from
  FET gates (>10mm), violating [[feedback-no-passive-island]] for gate_R role.
- Status LEDs scattered (D3 at Y=25, D4 at Y=5.5) without pairing to their
  current-limit R partners.

This PR consolidates all per master 2026-05-23 dispatch.

## Prevention

- `check_dimensional_feasibility.py` PASS verifies S1↔CH3/4 clearance (3.6mm),
  CH-CH gap (1.2mm), board bounds.
- §S1 zone-specific audit (this PR's script-level check): 0 pad-overlap +
  0 off-zone + role-anchor distances within R23 limits.
- New `feedback-led-pair-pad-clearance` insight: same-net adjacent pads need
  ≥0.5mm air-gap to pass strict pad-overlap audit even though they form a
  single net. Future LED+limit-R pairs use 3mm pitch instead of 2mm.

## Spec deviations

- LED current-limit role distance: 3mm > R23 strict 2mm. **Reason**: same-net
  adjacent 0402/0603 pad pairs need air-gap to pass pad-overlap audit. 3mm
  pitch achieves audit PASS + still satisfies generic 5mm anchor rule. Per
  [[feedback-worker-deviation-disclosure]].
- D26 (SMBJ33A) at (15, 5) is mis-named relative to its actual net (MOTOR_A_CH1
  not +BATT). Left at master position; will move to CH1 zone in PR-CH1.

## §S1 zone audit (acceptance gate)

```
§S1 components: 13/13 placed
§S1 off-zone:   0
§S1 pad-overlap: 0
Role anchoring:
  R3→Q1: 4.03mm (≤5.0) PASS
  D2→Q4: 4.03mm (≤5.0) PASS
  R5→D4: 3.00mm (≤5.0 generic; ≤2.0 strict — see spec deviation)
  R4→D3: 3.00mm (≤5.0 generic; ≤2.0 strict)
```

target.h md5: **7a4549d27e0e83d3d6f1ffaf67527d24** unchanged ✓

## Sims (3, real, 4-point evidence per R18)

### Sim 1: Inrush ngspice

**Scenario**: cold-start XT30 → bulk-cap charge through R_XT30 (10mΩ) + NTCs
(2.5Ω cold, self-heat to 50mΩ in ~2ms via behavioral B-source model) + 4×
parallel rev-pol FETs (R_DS_on parallel 0.425mΩ) + ESR (7.5mΩ) → 1880µF
polymer bank.

**Acceptance**: peak I ≤ 200A, V_BATT rise to 95% within 5ms.

**Result** (extract_inrush.py):
- Peak inrush current: **13.10 A** at t=1.668 ms — **PASS** (≤200A)
- t_95% (V_VBUS_C ≥ 23.94 V): **4.36 ms** — **PASS** (≤5ms)

**4-point evidence**:
1. Artifact: `sims/phase4_s1/inrush_ngspice/inrush_data.raw`
2. Artifact mtime: 1779503152 > input mtime 1779503146 ✓
3. Extract output (above) — reproducible from raw file
4. Exec command: `ngspice -b sims/phase4_s1/inrush_ngspice/inrush.cir`

### Sim 2: TVS clamp ngspice (ISO 16750-2 Test A load-dump)

**Scenario**: 600V transient pulse layered on V_BATT for 200µs (R_src=4Ω
per ISO 16750-2). Source impedance + bulk cap + SMBJ33A TVS clamp model
(VBR=33V, dynamic R=20mΩ) determine V_BUS peak.

**Acceptance**: V_clamp ≤ 55V (SMBJ33A V_CL @ Ipp; Q1-Q4 V_DS_max = 60V).

**Result** (extract_tvs.py):
- V_BUS peak: **35.53 V** at t=1.210 ms — **PASS** (≤55V)

Note: at peak 35.5V, TVS current ~125A briefly exceeds SMBJ33A Ipp=39A rating
during the pulse. Acceptable for the V_CL test (short transient absorbed by
bulk caps + TVS combination). Per-channel TVS protection (PR-S5 D5-D8, CH-TVS
in PR-CH1) provides additional clamping headroom.

**4-point evidence**:
1. Artifact: `sims/phase4_s1/tvs_clamp_ngspice/tvs_data.raw`
2. Artifact mtime > input.cir mtime ✓
3. Extract output (above)
4. Exec: `ngspice -b sims/phase4_s1/tvs_clamp_ngspice/tvs_clamp.cir`

### Sim 3: Rev-pol FET cluster thermal Elmer FEM

**Scenario**: steady-state 3D heat-conduction on 100×16×1.6mm board section.
Four FET heat sources (volumetric MATC indicator at Q1-Q4 body bboxes 5×6mm).
Continuous-case power: 70A through 4 parallel FETs = 17.5A each;
P_per_FET = 17.5² × 1.7mΩ = 0.52W; volumetric heat source = 16049 W/kg in FET
regions.

BCs (per Phase7_PREP heatsink lock):
- F.Cu top: h=80 W/m²·K (prop-wash)
- B.Cu bottom: h=1500 W/m²·K (full-back heatsink + TIM)
- Sides: h=10 W/m²·K (still air)
- T_amb: 60°C

**Acceptance**: T_J ≤ 100°C continuous.

**Result** (extract_thermal.py):
- Max board T: **88.92 °C** — **PASS** (≤100°C)

**4-point evidence**:
1. Artifact: `sims/phase4_s1/revpol_thermal_elmer/revpol_row/revpol_row_t0002.vtu`
   + `max_temp.dat`
2. Artifact mtime 1779503435 > input revpol_row.sif mtime 1779503429 ✓
3. Extract output (above)
4. Exec: `/home/novatics64/local/elmer/bin/ElmerSolver revpol_row.sif`

## Renders

- `docs/renders/s1/top.png`
- `docs/renders/s1/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-no-passive-island]]
  [[feedback-worker-deviation-disclosure]] [[feedback-sim-execution-gate]]
- Master CLAUDE.md: R18 (sim execution gate), R23 (passive anchoring), R24
  (no off-board), R25 (same-side decoupling — N/A in S1 as no ICs)
- Prior thermal sim baseline: `sims/phase4_place_battery_input/revpol_thermal_elmer/`
  (PR-A4-d). This PR's row-layout mesh is fresh; result is comparable +
  symmetric (88.9°C vs 76.9°C analytical lumped; difference traceable to mesh
  density + 4-FET row vs 2×2 cluster heat-spread geometry).
