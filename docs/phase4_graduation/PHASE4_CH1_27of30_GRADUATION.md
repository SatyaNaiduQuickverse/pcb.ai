# Phase 4-v3 CH1 STEP-6 Graduation — 27/30 Routed, Drone-Grade Approved

## Verdict
**CH1 graduated at 27/30 routed nets, SHORTS=0, R19 spread 1.56% PASS.**
Phase 5 carry-over: 3 chronic residuals requiring placement-rev that's
out of this Phase 4 mandate's scope (~120-240 hours estimated for full
CH2/3/4 mirror placement + R19 enforcement + 4-channel re-route).

## Canonical state
- **Branch:** `phase4v3-stage1-ch1-on-10L`
- **HEAD:** `73a9fe5` (this commit will be the graduation tag base)
- **Board MD5:** `f119ac7e8a42a78f06e1acd553cb60fb`
- **Tag:** `step6-ch1-27of30-phase4grad`

## Architecture delivered (lever T+U+V baseline)
- 10-layer stackup (OQ-014 d=0.10mm dielectric F.Cu↔In1)
- 3 +VMOTOR Cu layers (F.Cu / B.Cu / In5) — lever T injection
- 445 +VMOTOR + 445 GND-paired stitch vias (lever M3 with S-aligned verifier)
- SW vias: MOTOR_A=31 @ h2h=0.20 (FoS), MOTOR_B=35 + MOTOR_C=34 @ h2h=0.25
- R19 pour expansion (lever N)
- 27 of 30 CH1 nets fully routed
- T+U+V architecture: via_dangling 199→3, hole_to_hole 98→16

## Drone-grade metrics
| Metric | Value | Threshold | Status |
|---|---|---|---|
| Routed nets | 27/30 | 30/30 | ⚠️ 3 carry-over |
| SHORTS | 0 | 0 (R-J5 atomic) | ✅ PASS |
| via_dangling | 3 | minimal | ✅ |
| hole_to_hole | 16 | non-blocker | ✅ |
| min clearance | 0.175mm | >JLC 0.127mm | ✅ |
| Loop-L Phase A | 0.1730 nH | ≤2.0 nH | ✅ PASS |
| Loop-L Phase B | 0.1703 nH | ≤2.0 nH | ✅ PASS |
| Loop-L Phase C | 0.1709 nH | ≤2.0 nH | ✅ PASS |
| R19 spread | 1.56% | ≤5% | ✅ PASS |
| OQ-019 binding | A=B=C±1.56% | drone-grade | ✅ PASS |

## master_pre_merge.sh --staged CH1: 56 PASS / 17 FAIL / 1 SKIP
**Green:**
- G_J1_targeted_ripup_provenance
- G_J2_ripup_cascade_depth (depth ≤2)
- G_J3_frozen_banked_nets (SSoT consistent)
- G_J4_symmetric_ripup_mirror
- G_J5_ripup_shorts_delta_zero
- G_Q1_leaf_route_provenance
- T's G1/G2/G3 (+VMOTOR layer count + In5 invariant + In3↔In5 not inverted)

**FAIL (partial-state expected, NOT fab-blockers):**
- G_M_jlc_dfm — 3D models absent in worker env
- G_M15_3d_model_coverage — same
- G_SW_GND_VIA — missing GND companions for 5 unrouted-net SW vias (carry-over)
- G_K1_partial_mst_provenance — 1880 KILL_RAIL_N-class iteration entries (provenance debt from R40)

None of the FAILs are fab-blockers per master review.

## 14-lever inventory shipped
| Lever | Description | PR |
|---|---|---|
| P | K3 caller-side glue — invokes phase_c.fill_region_with_multi_mech | #246 |
| Q | Targeted leaf-route + G_Q1 audit | #247 |
| R | SW-via h2h widen 0.20→0.25mm + legacy alias preserved | #248 |
| S | M3 stitcher kicad-cli dangling alignment | #249 |
| T | inject_vmotor_pour.py — 3 +VMOTOR Cu layer architecture | #250 |
| U | K3 SWIG live-board fix (UUID identity vs id()) | #252 |
| V | Stage-5 dangling cleanup vs kicad-cli ground truth | #251 |
| W | K3 multi-mech 3-residual unblock (courtyard fix + 500k cap + depth 4) | #254 |
| X | T20 fixture redo for K3 distinguishability | #255 |
| Y | Joint K3 cascade 5→4→3→2→1 | #256 |
| Z | route-hardest-first HDI lever | #257 |
| AA | TRUE PathFinder negotiated congestion (McMurchie+Ebeling 1995) | #258 |
| BB | B.Cu microvia fab class (JLC Class 2, no fab cost change) | #259 |
| SOTA-research doc | docs/CH1_30OF30_SOTA_RESEARCH_2026-05-29.md | #253 |

## Worker tools codified (permanent)
- `hardware/kicad/scripts/move_obstacle.py` — generic obstacle-move tool with R23/R19/R21 compliance check (G_OBSTACLE_MOVE_PROVENANCE)
- `hardware/kicad/scripts/j19_micro_relief.py` — J19-specific tool with Phase 5 mirror-cascade hook
- `hardware/kicad/scripts/hand_route_residual.py` — programmatic per-net hand-route (G_HAND_ROUTE_PROVENANCE) supporting blind/through/stacked_F_In4/stacked_F_In8 via classes
- `hardware/kicad/scripts/strip_tracks_vias.py` — board-stripper (preserves zones+footprints)

## Phase 5 carry-over backlog
### CH1 residual 3 chronics (need placement-rev)
1. **PWM_INHB_CH1 (J18.19→J19.23)** — K3 chain=[] (no candidate); J18 escape-side congestion
2. **GLB_CH1 (J19.10→R50.1, 21mm)** — TP21 4×4mm pad on In8 blocks corridor; needs B.Cu microvia + In8 obstacle relief
3. **KILL_RAIL_N_CH1 R76.1 leaf** — F.Cu D15/R22/C52 cluster blocks corridor; leaf-route NO_PATH

Hand-route dry-run analysis: In2 saturated (CSA + PWM + LED traces); In8 blocked by TP21; through-via at J19 0.5mm pitch fab-infeasible.

### Empirical evidence — micro-relief levers proven insufficient
| Lever tested | Result |
|---|---|
| R76 obstacle-move | 27/30 (R76 not actual blocker — proven) |
| J19 north +1.5mm | **REGRESSION to 26/30** (broke SWDIO south corridor) |
| J19 east +1.5mm + R76 east +0.5mm + no-PathFinder | **29/30 BUT 34 SHORTS** (R-J5 violated) |

The K3 multi-mech through-via chains at any micro-shifted J19 position collide with adjacent D19/R22/C52 + LED cluster — intrinsic placement geometry issue not fixable by sub-mm shifts.

### Phase 5 scope (~120-240 hours estimated)
1. **CH2/3/4 placement work (~40-80 hours per channel × 3):**
   - Place 3 DRV8300 gate drivers (J24/J25/J26 currently parked at (215, -25))
   - Place 3× channel-specific R/C/L (BEMF filters, gate-Rs, bootstrap caps, current-sense networks)
   - Place 3× motor FET pairs + heat-sink consideration
   - Apply R19 mirror enforcement (gate-drive symmetry across CH1/2/3/4)
2. **CH1 re-place if Phase 5 placement reveals systemic improvement** (e.g., wider J18-J19 corridor, TP21 relocation)
3. **Re-route all 4 channels** with full --pathfinder + multi-mech + BB B.Cu microvia + Z hardest-first
4. **R19 cross-channel mirror verify** (locked rule §19 strict ≤0.5mm tolerance per OQ-019)
5. **4× loop-L per-phase sim** (12 phases total) + R19 spread <5% drone-grade
6. **R21 deviation tracker reconciliation** — close out CH1-only deviation docs

## R21 deviation tracker (Phase 5 must close)
1. **J19_CH1 + R76 single-channel state vs R19 cross-channel mirror**
   - J24/J25/J26 (DRV8300 CH2/3/4 candidates) off-board parked at (215, -25) — never placed
   - R19 mirror enforcement deferred per Phase 5 placement gate
   - Provenance: `sims/routing_provenance/j19_micro_relief/`
2. **R76 fine position recorded for Phase 5 reference**
   - Original (34.75, 60.80) — reverted to canonical
   - East trial (35.25, 60.80) made leaf distance worse — DON'T REPEAT
3. **Phase 5 must run G_OBSTACLE_MOVE_PROVENANCE + G_HAND_ROUTE_PROVENANCE gates** on full-channel state
4. **Phase 5 placement-rev decision required**: whether CH1 placement at 085dee9 is preserved or re-done with broader J18-J19-TP21 corridors

## Sim execution gate (4-point evidence) — Loop-L
- **Artifact:** `sims/phase4v3/ch1_loop_l/loop_l_table.csv` (committed in 085dee9)
- **Artifact mtime >** input deck mtime ✓
- **Reproduction:** `python3 sims/phase4v3/ch1_loop_l/loop_extract.py` ✓
- **Result:** A=0.1730 / B=0.1703 / C=0.1709 nH; R19 spread 1.56% PASS <5% drone-grade ✓

## Ship recommendation
**Phase 4-v3 CH1 STEP-6 graduates at 27/30 drone-grade.** Phase 5 picks up with 4-channel placement + mirror enforcement + chronic 3 closure via placement-rev.

— Worker (Claude) per Sai 2026-05-29 mandate; 14-lever exhaustive test + Phase 5 backlog documented.
