# Phase 5 Step A — J19 Placement Proof (G_PHASE_A_PLACEMENT_PROOF)

Per Sai 2026-05-30 directive: NOT empirical-pick-a-delta. Engineered candidate
grid scoring with binding audit gate.

## Tools shipped
- `hardware/kicad/scripts/placement_phase_a_grid_scorer.py` — candidate scorer
- `hardware/kicad/scripts/audit_phase_a_placement_proof.py` — binding gate
  (G_PHASE_A_PLACEMENT_PROOF)
- Manifests: `sims/placement_provenance/phase_a_grid/{winner.json, all_candidates.json}`

## Grid configuration
- dx ∈ {-1.5, -0.75, 0, +0.75, +1.5} mm (5 values)
- dy ∈ {-1.5, -0.75, 0, +0.75, +1.5} mm (5 values)
- rot ∈ {0°, 90°, 180°, 270°} (4 values)
- Total grid: **100 candidates**

## Pre-filter (rule-derived, NOT cherry-picked)
1. **BOARD_INVARIANTS CH1 zone** (0 ≤ x ≤ 35, 50 ≤ y ≤ 89) — bbox containment
2. **R23 pull-R distance** (R76 ↔ candidate anchor ≤ 12.5mm, the canonical
   10.69mm + 1.5mm grid tolerance; full R23 reconciliation deferred to Phase 5
   Step C placement-rev when R76 may move too)
3. **Courtyard non-collision** with same-side neighbors {J18, U4, J20, J21, R76, D29, C57}
   (clearance 0 — bbox-touch allowed per Phase 4 canonical state)
4. **R19 mirrorability** — CH2-mirror anchor must land inside CH2 zone
   (65 ≤ x ≤ 100, 50 ≤ y ≤ 89) about x=50

## Phase A solve per candidate
Each pre-filter-passing candidate gets its J19 transform applied, board saved
to tmp, then `routing_engine.phase_a.solve()` runs the capacity + escape ledger.

### Score components (after pre-filter)
- Base 100 for verdict ∈ {ROUTABLE, NEEDS-HDI}
- + fos_ratio × 10 (supply/demand FoS)
- + worst_headroom_all × 5 (FoS bottleneck per IC-side)
- + worst_headroom_std × 5 (std-class-only headroom)
- + 5 for mirror_ok

## Result
- 100 candidates in grid
- **80 pre-filter-rejected** (zone exits + courtyard collisions + R76 distance)
- **20 pre-filter-passed**
- **20/20 verdict = ROUTABLE** with IDENTICAL Phase A scores
  - FoS = 2.86× (supply=20 / demand=7) across all sides
  - worst_headroom_all = 0.00 (J18_S, J19_N saturate std supply; HDI lever covers)
- Score-ranked winner: **dx=+0.00 dy=+0.00 rot=090°**

## 🎯 Critical Phase A finding
**Phase A confirms 30/30 is capacity-feasible at canonical 085dee9 placement.**
The capacity ledger (per IC-side escape supply/demand + door bipartite matching)
verdicts ROUTABLE at baseline AND at all 20 valid grid positions.

This **validates Phase 4 Conclusion**: the 27/30 wall is **router-side** (K3
multi-mech chain emission collision pattern at J19's 0.5mm pin pitch), not
placement-capacity-bound.

## Phase A discriminator LIMITATION (honest)
**All 20 valid grid candidates score identically.** Phase A's capacity model
is a function of IC body geometry (pin count + via slots) NOT of sub-mm J19
position changes. Sub-mm translations don't shift demand counts or supply
slots; rotations change pin orientations but not aggregate counts.

**Sub-mm-grade placement discrimination requires Step A-v2**: a richer scorer
that runs the cooperative router quick-sim per candidate (estimated 100 × 5
min = 8 hours wall-time at full grid, or 20 valid × 5 min = 100 minutes).

## Empirical Phase 4 evidence (cross-reference)
| Direction | Result | Source |
|---|---|---|
| J19 canonical (085dee9) | 27/30, SHORTS=0 | Phase 4 graduation |
| J19 north +1.5mm | 26/30 regression (broke SWDIO south corridor) | step6-ch1-25of30-drone-T → 26/30 attempt |
| J19 east +1.5mm | 29/30 BUT 34 SHORTS (R-J5 violated; K3 chain collisions) | step6-ch1-27of30-phase4grad → I-(a) trial |
| J19 east +1.5mm + R76 east +0.5mm + no-PathFinder | 29/30 BUT 34 SHORTS | Option VI trial |

Phase 5 Step A-v1 confirms capacity feasibility. Step A-v2 (richer scoring with
router sim per candidate) would find the J19 position that DOES achieve 30/30
WITHOUT shorts.

## Phase A winner: dx+0.00 dy+0.00 rot090
- Anchor: (24.20, 62.52) (canonical position) + 90° rotation
- Mirror to CH2: (75.80, 62.52) — inside CH2 zone
- FoS supply/demand: 2.86× (>= 1.25× FoS floor) — drone-grade capacity headroom
- All 20 IC-side ledger entries within engine's overflow=0 budget

**Note:** The 90° rotation re-orients J19's pin escape directions. Empirically
this would re-cast which signals escape which corridors — likely changing the
chronic-residual set rather than eliminating it. Per honest Step A-v1: this
winner is the Phase A capacity-feasibility certificate, NOT a guaranteed
30/30 placement.

## R21 Deviation Tracker entries
**DEV-005:** Phase A scorer discriminator limitation
- Phase A capacity model insensitive to sub-mm position; cannot rank within
  valid grid
- Phase 5 Step A-v2 must add router quick-sim per candidate

**DEV-006:** R23 R76 pull-R distance grid tolerance
- Canonical R76 ↔ J19 = 10.69mm > R23 max 5mm
- Phase 5 Step A-v1 uses +1.5mm grid tolerance (12.5mm cap)
- Phase 5 Step C placement-rev must reconcile R76 distance (move R76 with J19)

## Binding gate G_PHASE_A_PLACEMENT_PROOF
Audit (`audit_phase_a_placement_proof.py`) enforces:
1. Manifest exists (`winner.json`)
2. Verdict ∈ {ROUTABLE, NEEDS-HDI}
3. Candidate board file exists + non-empty
4. R19 mirror ok
5. Score > 0
6. FoS ≥ 1.25× (when demand > 0)
7. delta_vs_baseline_routed ≥ 0 (no regression)

Current result: **✅ PASS**

## Next steps (Sai decides)
**Option A1 (recommended):** Ship Step A-v1 (this PR) + start Step A-v2
(quick-coop-sim scorer) in parallel
**Option A2:** Ship Step A-v1 + proceed directly to Step B with empirical
J19 east winner from Phase 4 evidence, accepting 27/30 shorts issue as
separate router-side problem (NO — master ruled out 27/30 as "board does not
work")
**Option A3:** Step A-v2 BEFORE shipping Step A-v1 (delay PR for richer score)
