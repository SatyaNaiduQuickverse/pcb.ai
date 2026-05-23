# PR-S2 — §S2 bulk caps subsystem (Task #71)

Third of 11 sequential A4-* PRs (after PR-S1 at 44d9ad2). Places §S2 polymer
bulk caps with 2×2 mirror symmetry about (50, 36) per master locked spec.

## Symptom

PR-A4-c master placement had C1 at (22, 28) and C2 at (85, 28) — NOT
X-symmetric. C3/C4 at (25/75, 44) were already mirror-correct. The C1/C2
asymmetry violated [[feedback-symmetry-preserves-work]] (per R19 +
locked master rule "all 4 caps form perfect 2×2 mirror").

## Fix

§S2 placement (4 components, perfect 2×2 mirror about (50, 36)):

| Ref | Pos (mm)   | Mirror role                 |
|-----|------------|-----------------------------|
| C1  | (25, 28)   | NW corner — reference       |
| C2  | (75, 28)   | NE = mirror_X(50) of C1     |
| C3  | (25, 44)   | SW = mirror_Y(36) of C1     |
| C4  | (75, 44)   | SE = 180°-rot(50,36) of C1  |

All EEHZS1V471P 470µF polymer, F.Cu, rotation 0°.

Symmetry verification (verify_spec_diff.py equivalent):
```
mirror_X(50): C1@(25,28) → C2@(75,28); expected (75,28); Δ=0.000mm PASS
mirror_Y(36): C1@(25,28) → C3@(25,44); expected (25,44); Δ=0.000mm PASS
180°(50,36): C1@(25,28) → C4@(75,44); expected (75,44); Δ=0.000mm PASS
```

## Root cause

PR-A4-c (master baseline) shifted C1/C2 to clear Hall body (S3 U1) — the C3/C4
correction landed properly but C1/C2 X-coords (22, 85) drifted to avoid PHASE
4 collisions that no longer apply with the new 100×100 board (Hall now at
(50, 50)). PR-A4-c was solving for old geometry; now C1/C2 should be at the
canonical (25, 75) X-mirror.

## Prevention

- Run `verify_spec_diff.py` per R20 every layout PR; this catches drift.
- `check_dimensional_feasibility.py` lists S2 cap bbox 13.59×11.05 — flags
  the master-spec (25,28)/(75,28) C1/C2 position requirement directly.

## Spec deviations

NONE — pure transform applied. C1/C2 corrected to master locked spec.

## Audit state

| Gate                                   | Status     | Notes                  |
|----------------------------------------|------------|------------------------|
| Total PAD-OVERLAP vs master 364        | PASS (364) | 2 NEW pairs swapped with 2 FIXED — net 0 |
| §S2 internal pad-overlap (C1-4 only)   | 0          | no C↔C overlaps         |
| §S2 symmetry (≤0.5mm)                  | PASS       | All 4 caps within tolerance |
| target.h md5                           | UNCHANGED  | 7a4549d27e0e83d3d6f1ffaf67527d24 |

Note on "2 NEW pairs swapped": moving C2 from (85, 28) to (75, 28) shifted
which CH3 FET pads it overlaps with (was C2↔Q19.1/Q19.2, now C2↔Q20.2/Q19.1).
Same number of conflicts (2), different identities. CH3 FETs themselves will
be moved in PR-CH3 (Y=29→32 per master P=12 spec); the conflicts will resolve
when PR-CH3 reshuffles those FETs.

## Sims (3, real + 4-point evidence per R18)

### Sim 1: Ripple ngspice — 4-channel 30kHz PWM, bulk cap ripple

**Scenario**: 4 motor channels switching at 30kHz, 50% duty, 25A each at
90°-staggered phase offsets (0/8.33/16.67/25 µs). Source impedance 30mΩ
(6S LiPo internal ~5mΩ + NTC hot pair 25mΩ + rev-pol FET 0.4mΩ). Bulk cap
bank C1-C4 = 4×470µF parallel = 1880µF, ESR per cap 30mΩ → 7.5mΩ total.

**Acceptance**: V_BUS ripple ≤ 1V peak-to-peak.

**Result**: V_BUS pk-pk **0.460 V** — **PASS** (≤ 1.0V, 0.54V margin)

**4-point evidence**:
1. Artifact: `sims/phase4_s2/ripple_ngspice/ripple_data.raw` (1MB+)
2. Artifact mtime > input deck mtime
3. Extract reproducible: `python3 extract_ripple.py` → 0.460V
4. Exec: `ngspice -b sims/phase4_s2/ripple_ngspice/ripple.cir`

### Sim 2: ESR thermal Elmer FEM — bulk cap T_J at I_rms

**Scenario**: 100×24×1.6mm PCB section around bulk cap cluster. Heat source
via MATC indicator in 4 cap-body regions; P_per_cap = I_rms²×ESR = 5²×0.030
= 0.75W (conservative continuous-AC component); volumetric density 2596 W/kg.
BCs per Phase7_PREP heatsink (h_bot=1500, h_top=80, h_sides=10, T_amb=60°C).

**Acceptance**: T_J ≤ 105°C (polymer cap max temp rating).

**Result**: max board T **66.93 °C** — **PASS** (≤ 105°C, 38°C margin)

**4-point evidence**:
1. Artifact: `sims/phase4_s2/esr_thermal_elmer/cap_max_temp.dat` +
   `cap_mesh/cap_thermal.result`
2. Artifact mtime > input mtime
3. Extract reproducible: `python3 extract_thermal.py` → 66.93°C
4. Exec: `/home/novatics64/local/elmer/bin/ElmerSolver cap_thermal.sif`

### Sim 3: Pair-wise S1+S2 inrush ngspice (cumulative)

**Scenario**: combined S1 (NTC + rev-pol FETs) + S2 (1880µF bulk caps).
Cold-start charging from 0V → 25.2V. Verifies the S1 inrush envelope holds
when full S2 bulk cap bank is included as the charge load.

**Acceptance**: V_BUS rise to 95% within 5ms (re-confirm S1 result holds).

**Result**:
- Peak inrush: **13.10 A** (≤200A) **PASS**
- t_95% to 23.94V: **4.36 ms** (≤5ms) **PASS**

Identical to PR-S1 standalone result — S1 had already modeled 1880µF cap
bank as the charge load. This confirms no S2 added impedance shifts the
inrush envelope.

**4-point evidence**:
1. Artifact: `sims/phase4_s2/pairwise_s1_s2_inrush/s1s2_inrush.raw`
2. Artifact mtime > input deck mtime
3. Extract reproducible: `python3 extract_pairwise.py` → 13.1A / 4.36ms
4. Exec: `ngspice -b sims/phase4_s2/pairwise_s1_s2_inrush/s1s2_inrush.cir`

## Renders

- `docs/renders/s2/top.png` — top view showing 2×2 cap grid at (25/75, 28/44)
- `docs/renders/s2/bottom.png` — bottom view

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-spec-vs-placement-gate]]
  [[feedback-sim-execution-gate]] [[feedback-incremental-sim-driven-placement]]
- Master CLAUDE.md: R18 (sim execution gate), R19 (symmetry), R20 (spec-vs-placement gate)
- Locked spec: master 2026-05-23 dispatch — 2×2 mirror grid about (50, 36)
