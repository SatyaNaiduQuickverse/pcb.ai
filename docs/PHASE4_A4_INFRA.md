# PR-A4-infra — Phase 4 layout infrastructure (board grow + audit + placer skeleton)

PR-A4-infra is the foundation PR for the 11-PR sequential A4-* phase per Sai's
"subsystem-by-subsystem, no one-shot" directive (2026-05-23). It installs the
infrastructure that subsequent PRs (PR-S1 through PR-integrate) build on, with
NO new subsystem-specific placement work.

Subsequent PRs in this series (dispatch by master after merge):
- **PR-S1**: §S1 battery input refinement
- **PR-S2**: §S2 bulk caps refinement
- **PR-S6**: §S6 connectors refinement
- **PR-S3**: §S3 supervisor + Hall refinement
- **PR-S5**: §S5 BEC refinement
- **PR-CH1**: Channel 1 full placement (FETs + driver + passives)
- **PR-CH2/CH3/CH4**: pure-transform mirrors of CH1
- **PR-integrate**: full-board audit + cumulative regression sims + Phase 5b prep

---

## Symptom

A4-redo one-shot attempt hit the auto-anchor density wall (250–300 PAD-OVERLAP)
combined with N-channel cross-validation gaps in master geometry dispatches
(third dimensional dispatch error in 24 hours — CH-CH boundary not gated).
Sai directive: subsystem-by-subsystem, no corners cut, unlimited time.

## Fix (this PR)

Infrastructure-only changes that unlock the subsystem PRs:

1. **Board grow 100×95 → 100×100mm** (`setup_board.py` BOARD_H=100, mount holes
   shifted to (5,5)/(95,5)/(5,95)/(95,95)). Sai authorized; preserves locked
   A4-c thermal reference (P=12 row pitch is now dimensionally feasible).

2. **`scripts/check_dimensional_feasibility.py` (NEW)** — pre-placement geometry
   gate. Validates row pitch, board bounds, JLC clearance + the boundary checks
   that would have caught master's prior Y=17 and Y=51/Y=44 dispatch errors
   (S1↔CH3/4, CH1/2↔CH3/4, CH1/2↔S6, board-bound, mirror-axis sanity).

3. **`scripts/audit_layout_compliance.py` (FIX)** — symmetry check now reads the
   board outline dynamically (was hardcoded to 95×100). Fixes CH-pair symmetry
   evaluation on the new 100×100 board.

4. **`scripts/auto_anchor_passives.py` (NEW)** — per-parent-anchored passive
   placement utility, multi-pass + grid-strip fallback. Used by S8 placer to
   ensure no kinet2pcb-default off-board defects (R24). Each subsystem PR will
   SUPERSEDE its components' auto-anchor positions with intentional layouts.

5. **`scripts/verify_spec_diff.py` (NEW)** — coord-diff gate (actual vs locked
   transforms) per R20. Used by master gate.

6. **`place_board.py` 8-subsystem-placer skeleton**:
   - S1 `place_battery_input`
   - S2 `place_bulk_caps`
   - S3 `place_supervisor_hall`
   - S5 `place_bec`
   - S6 `place_connectors`
   - S4-CH1 `place_channel_ch1`
   - S4-CH234 `place_channels_234`
   - S8 `place_auto_anchored` (auto-anchor fallback for off-board=0)

   Each subsystem PR refines one placer's positions; S8 auto-anchor handles
   the rest until intentional placement lands.

7. **S1 Q1-Q4 + R1/R2 shifted to Y=7.5** (was Y=10) — pre-positions for
   PR-S1's S1↔CH3/4 clearance requirement (CH3/4 bottom row Y=20 needs ≥1mm
   clear of S1 top edge). Bbox top Y=11.0 << 14.6 = CH3/4 bot edge.
   This is the only intentional placement change in PR-A4-infra.

## Root cause

A4-redo one-shot violated [[feedback-subsystem-by-subsystem]]: it tried to land
192+ component placements + cross-channel symmetry + 8 ICs decoupling + sim
re-runs + renders + 3D verification in a single PR. The auto-anchor density
algorithm hit local minima; debugging cycles compounded across orthogonal
failure modes (geometry / collision / decoupling / island-anchoring). Sai called
out the same root cause that drove [[feedback-root-cause-not-symptom]] earlier:
mixing multiple problem classes in one PR makes each unfixable.

Master's geometry dispatch errors (CH-CH boundary missed) traced back to
[[feedback-spec-vs-placement-gate]] enforcement at WORKER's
`check_dimensional_feasibility.py` checking ONLY CH-S1/S6 boundaries, not
inter-channel boundaries. This PR adds that check.

## Prevention

- Subsystem PRs from now on. No one-shot multi-subsystem PR for A4 family.
- `check_dimensional_feasibility.py` runs BEFORE every subsystem PR's
  placement work. Master dispatch geometry validated against actual FET
  pad bboxes (not body bbox).
- `audit_layout_compliance.py` runs at the end of every PR scoped to that
  subsystem's zone + all-previously-placed zones; pass criteria advance as
  PRs land.
- `auto_anchor_passives.py` provides a safe baseline so off-board=0 is
  always achievable; PRs replace its placements with intentional ones.

## Spec deviations

NONE — pure infrastructure change. Q1-Q4/R1/R2 Y-shift is mechanically
required for CH3/4 clearance and is part of locked master dispatch geometry.

## Audit state at end of PR-A4-infra

| Gate              | Status | Notes                                       |
|-------------------|--------|---------------------------------------------|
| Off-board=0       | PASS   | All 585 components on-board (via S8 auto)   |
| PAD-OVERLAP=0     | FAIL   | 364 — deferred to subsystem PRs (expected)  |
| Symmetry          | FAIL   | CH3/4 P=11 (master-base state) — fix in PR-CH3/CH4 |
| Passive anchoring | WARN   | 162 in 10-20mm + 5 >20mm — refined per-PR   |
| Decoupling        | FAIL   | 10 ICs need 3mm-cap — fix in subsystem PRs  |

Per master 2026-05-23 directive: PR-A4-infra acceptance gate is **off-board=0
only**. Other failures are intentional defer-points consumed by subsequent
subsystem PRs.

## References

- Memory: [[feedback-symmetry-preserves-work]] [[feedback-spec-vs-placement-gate]]
  [[feedback-worker-deviation-disclosure]] [[feedback-no-passive-island]]
  [[feedback-no-unplaced-footprints]] [[feedback-sim-execution-gate]]
- Baseline audit: `docs/PHASE4_A4REDO_baseline_audit.txt`
- Master CLAUDE.md rules R18-R25 (audit gates, symmetry, anchoring, dispatch
  disclosure, decoupling same-side)

## Sim section

No sims in PR-A4-infra (no placement work to validate). Subsystem PRs will run
per-subsystem real sims with 4-point evidence per R18.
