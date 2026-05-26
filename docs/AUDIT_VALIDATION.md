# Audit Validation — ground-truth verification of audit scripts

**Per Sai 2026-05-26 R32 catch**: audits previously claimed "sureshot" without
external validation. This doc + the test fixtures under `hardware/kicad/tests/`
close that gap. Every audit in `master_pre_merge.sh` must be validated against
ground truth here before being trusted as a gate.

## Reputed sources (oracle hierarchy)

Per Sai's "make sure the source is good and reputed to validate":

| Tier | Oracle | Reputation |
|---|---|---|
| 1 | KiCad 9 built-in tools (pcbnew Python API: `GetPosition`, `GetBoundingBox(False, False)`, `IsFlipped`, `GetTracks`) | Open-source standard, IPC-compliant geometry, peer-reviewed code |
| 2 | Textbook formulas with cited page numbers — Bogatin SI/PI Ch. 5, Erickson Ch. 23, Ott Ch. 11, IPC-2152 | Peer-reviewed engineering literature |
| 3 | Mathematical proof (shoelace, Pythagorean) for constructed cases | Provable math, reproducible |

NOT trusted as oracle: hand-built test boards as primary truth source (same
blind spots as the audit), unknown github clones (provenance unclear).

## Methodology

1. **Construct synthetic board** via `tests/build_validation_board_v2.py` — every
   coordinate is computed inline from first principles. The truth lives in the
   construction code, so any audit-vs-truth mismatch indicates an audit bug
   (not a test bug).
2. **Run each audit** against the synthetic board.
3. **Compare** audit output to ground truth in `truth_v2.json`.
4. **Any divergence → root-fix the audit** (R-redo-not-mitigate). Never patch
   the test to make a bad audit pass.

## Results — 2026-05-26 baseline

### G1 — `audit_anchor_positions.py` (Tier 1 lockfile diff)

| Case | Lockfile | Actual | Expected | Result |
|---|---|---|---|---|
| `H_TOP` | (10,10) F.Cu rot=0 | (10,10) F.Cu rot=0 | PASS | ✅ PASS |
| `H_BOT` | (20,10) B.Cu rot=90 | (20,10) B.Cu rot=90 (flipped) | PASS | ✅ PASS |
| `H_DRIFT` | (30,10) F.Cu | (30.5,10) F.Cu | FAIL (x delta 0.5mm > 0.01mm tolerance) | ✅ FAIL detected |

**Bug found + fixed 2026-05-26**: `GetLayerName()` returns DISPLAY name like
`"F.Cu 3oz — heat layer"` when board has custom layer names (we do). Lockfile
uses canonical `"F.Cu"` / `"B.Cu"`. Compare via `IsFlipped()` instead.

### G3 — `audit_loop_area.py` (switching loop area)

| Channel | Polygon | Truth (shoelace) | Audit reports | Status | Result |
|---|---|---|---|---|---|
| CH1 | 5×5mm square | 25.0 mm² | 25.0 mm² | PASS (≤30 optimal) | ✅ |
| CH2 | 7×7mm square | 49.0 mm² | 49.0 mm² | WARN (30 < 49 < 50) | ✅ |
| CH3 | 8×8mm square | 64.0 mm² | 64.0 mm² | FAIL (>50) | ✅ |

Shoelace verified by hand: vertices (0,0)→(5,0)→(5,5)→(0,5) →
|(0·0 − 5·0) + (5·5 − 5·0) + (5·5 − 0·5) + (0·0 − 0·5)| / 2 = 50/2 = 25 mm² ✓

### G4 — `audit_decoupling.py` (R25 same-layer ≤3mm)

| IC | Cap position | Truth distance | Expected | Result |
|---|---|---|---|---|
| `U_OK` | C at 1.5mm same-layer | 1.5 mm | PASS | ✅ PASS |
| `U_FAR` | C at 4.5mm same-layer | 4.5 mm | FAIL (>3mm) | ✅ FAIL |
| `U_OPPLAYER` | C at 2mm opposite layer | 2.0 mm | WARN | ✅ WARN |

**Bug found + fixed 2026-05-26**: `is_ic()` / `is_decoupling_cap()` used
`FOOTPRINT.GetBoundingBox()` which INCLUDES reference text. On long refs
(`"C_DECOUP_OK"` = 11 chars rendered at default font), bbox is 30-40× larger
than the body, breaking the IC-vs-passive heuristic. Fix: use
`GetBoundingBox(False, False)` (no text). On the synthetic board this changed
text-included bbox of 38-43 mm² down to body-only 1.28-64 mm² as expected.

### G5 — `audit_layout_compliance.py` `--parked-exempt` mode

| Mode | Parked components | Audit behavior |
|---|---|---|
| (no flag) | 3 parked at x=200,205,210 | Flags 3 OFF-BOARD-CENTER (correct for non-staged) |
| `--parked-exempt` | 3 parked | Skips 3, audits remaining 21 on-board |

**Mode added 2026-05-26**: per worker on real staged board — Phase 4-v3
park-then-bring-in (R27) intentionally parks 560 components off-board at
parking_grid origin (200, -50). Without `--parked-exempt`, G5 false-flags all
parked components. Threshold `x ≥ 130mm` (board is ≤100mm wide, 30mm buffer).

### G6 — `master_audit_invariants.py` `--parked-exempt` mode

Same treatment as G5 — added 2026-05-26. `_onboard_footprints(board)` helper
replaces direct `board.GetFootprints()` iteration in all 5 check functions.

## Run the validation suite

```bash
cd /path/to/pcb.ai
python3 hardware/kicad/tests/build_validation_board_v2.py
# → /tmp/audit_validation_board_v2.kicad_pcb + truth.json + lockfile.yaml

# G1
python3 hardware/kicad/scripts/audit_anchor_positions.py \
    /tmp/audit_validation_board_v2.kicad_pcb \
    /tmp/audit_validation_lockfile_v2.yaml

# G3
python3 hardware/kicad/scripts/audit_loop_area.py \
    /tmp/audit_validation_board_v2.kicad_pcb

# G4
python3 hardware/kicad/scripts/audit_decoupling.py \
    /tmp/audit_validation_board_v2.kicad_pcb

# G5 (with + without exempt)
python3 hardware/kicad/scripts/audit_layout_compliance.py \
    /tmp/audit_validation_board_v2.kicad_pcb --parked-exempt
```

## Results — 2026-05-26 G10-G15 additions

### G10 — `verify_spec_diff.py` (R20 mirror geometry)

Wired into `master_pre_merge.sh` (was standalone). Accepts board arg. SKIP in
`--staged` mode (mirror partners not all brought yet).

### G12 — `audit_diff_pair_match.py` (Tier 4)

| Case | Spread (mm) | Tolerance (mm) | Expected | Result |
|---|---|---|---|---|
| `dp_ok` (DP_OK_POS=30.0, DP_OK_NEG=30.3) | 0.30 | 0.5 | PASS | ✅ |
| `dp_fail` (DP_FAIL_POS=30.0, DP_FAIL_NEG=35.0) | 5.00 | 0.5 | FAIL | ✅ |

### G13 — `audit_kelvin_shunt_routing.py` (Tier 4)

| Sub-check | Result |
|---|---|
| Shunt pad has Kelvin tap | ✅ PASS |
| Sense tracks start at pad centroid (±0.2mm) | ✅ PASS |
| Pos/neg length match (|0-0|=0mm ≤ 0.5) | ✅ PASS |
| Max transverse separation (3.0mm ≤ 5.0) | ✅ PASS |

### G14 — `audit_via_stitching_density.py` (Tier 1 PDN)

| Net | Vias | Area | Density | Spec | Result |
|---|---|---|---|---|---|
| +VMOTOR_TEST_PASS | 16 | 100.2 cm² | 0.16/cm² | ≥ 0.1 | ✅ PASS |
| +VMOTOR_TEST_FAIL | 4 | 100.2 cm² | 0.04/cm² | ≥ 0.1 | ✅ FAIL |
| (board with 0 tracks) | — | — | — | — | ✅ SKIP (routing gate) |

### G15 — `audit_length_match.py` (Tier 5 highways)

| Group | Lengths (mm) | Spread (mm) | Tolerance (mm) | Result |
|---|---|---|---|---|
| `hw_ok` | 50, 51, 49 | 2.00 | 2.5 | ✅ PASS |
| `hw_fail` | 50, 60, 49 | 11.00 | 2.5 | ✅ FAIL |

## Phase 2 — real-world cross-check on VESC BLDC_4 (Benjamin Vedder, BSD)

Board: `/tmp/audit_xchecks/vesc_bldc/design/BLDC_4.kicad_pcb` — 127 footprints, 1858 tracks, 187 vias, 38.6×65.2 mm. Reputed: Benjamin Vedder VESC reference, widely deployed across the FOC motor-control industry.

**Cross-checks ran (audits that universalize):**

| Audit | VESC behavior | Interpretation |
|---|---|---|
| G3 audit_loop_area | SKIP all 4 channels (CH1-CH4 refs not in VESC convention) | Audit correctly skips when our channel naming absent — won't false-FAIL foreign boards |
| G4 audit_decoupling | Detects U1/U2/U3 VDD pins with caps 3-12mm away → FAIL R25 | R25 (≤3mm) is STRICTER than VESC's design choice; gate works correctly. VESC isn't wrong, it's just on a different spec |
| G7 audit_routing | 1252 SUBSYSTEM-ZONE crossings (VESC has no zone structure) | Expected — gate keyed to our zone yaml; correctly inert against foreign boards lacking our metadata |
| G14 audit_via_stitching | Audits any net with via_stitching_density_per_cm2 spec; VESC has none → no false FAIL | Correct opt-in gate |

**Bug caught + fixed during cross-check:**
- `is_ic()` was flagging C11 (cap, body >4mm²) as IC needing decoupling. Refined prefix exclusion (now: J/P/TP/H/FID/FB/CP/C/R/Q/Y/BT/SW/SP/K/M + digit-suffix D/L/F). VESC re-run: only true U* refs flagged.

## Pending

- Synthetic test for `audit_zone_contract.py` (worker's G2) — currently validated only via real-board E2E by worker.

## Rule

**Per R32 (sureshot > SOTA)**: any audit added to `master_pre_merge.sh` must
have a ground-truth test case in `tests/build_validation_board*.py` + a row in
the results table above. Audits without validation entries are blockers for
Phase 4-v3 Stage dispatches.

## Batch-3 audits (no synthetic test fixture yet — covered by real-board smoke-test only)

The following audits were added 2026-05-26 with smoke-test on Stage 1 real
master board (not synthetic ground truth — pending). Marked as VALIDATION-
TODO; build synthetic test before relying on them as hard gates:

- audit_doc_sync.py (G_D1/G_D2/G_D3) — sync between code, doc, memory
- audit_rotation_alignment.py (G_PP4) — same-class footprint rotation uniformity
- audit_test_point_access.py (G_PP5) — TP probe-clip clearance
- audit_cable_swing.py (G_PP7) — cable bend-radius vs same-side tall component
- audit_pickplace_reach.py (G_PP2) — small SMD vs tall same-side neighbour
- audit_fos_pin_current.py (G_FoS5) — connector pin-current FoS
- audit_lockfile_completeness.py (G_L1) — netlist↔lockfile↔board consistency
- audit_connector_symmetry.py (G16) — connector mirror-symmetry per lockfile
- audit_edge_keepout.py (G17) — JLC edge clearance + Sai-#5 connector-near-edge
- audit_fos_thermal.py (G_FoS1) — T_J ≤ 75°C / 90°C thermal FoS
- audit_silk_size.py (G_PP3) — JLC silk text height
- audit_polarity_marker.py (G_PP1) — D/CP/U polarity silk presence
- audit_hv_creepage.py (G_PP6) — IPC-2221 B-grade HV clearance
- audit_jlc_dfm.py (G_M1/M2/M3) — JLC trace/via/annular floors
- audit_fos_current.py (G_FoS2) — trace ampacity FoS
- audit_via_current_capacity.py (G_R5) — via array vs net current
- audit_sim_execution.py (R-sim-execution) — 4-point sim proof per Sai 2026-05-23 lock; input + result + mtime > input + extract script + literal exec command. PRs #153, #154, #162 broader globs. Real-board smoke-test: 8/8 sim files PASS on master HEAD post-PR-#162.
- audit_subsystem_flow.py (G_FLOW1/2/3) — 7-step subsystem flow enforcement (PLACEMENT_GLOBAL_PLAN §8); G_FLOW1 STEP markers in subsystem doc, G_FLOW2 adjacent integration sim per pairing table, G_FLOW3 I/O port allocation. Pre-flow-lock stages (S6/TIER1) grandfathered as WARN.
- audit_sim_artifact_provenance.py (R-sim-provenance) — sim inputs/results/RESULTS.md must cite git-tracked paths only; /tmp/ citations FAIL. Added 2026-05-26 after worker caught CH1 placement living only in /tmp/ch1_152.kicad_pcb (STEP-3 sims would be unreproducible if /tmp wiped).
- audit_per_phase_cluster_uniformity.py (G_PP22) — transformable per-phase cluster pitch must be uniform within 0.5mm; FAIL not WARN. Added 2026-05-26 after worker caught J22 class lesson: sign typo in parametric_placement.py (motor['TP21'][1] - 1 instead of + 1) placed J22 at 2mm off uniform Δ13mm, passed all 56 existing gates as WARN-tolerance, surfaced only when STEP-4 R19 pure-transform attempted. Validates against pre-fix (FAIL spread=2.000mm) + post-fix (PASS spread=0.000mm) boards in escworker/local/. Per-phase clusters covered: HS_FETs, LS_FETs, Boot_caps, Gate_R_HS, Gate_R_LS, Shunts, INAs, Dividers — 8 clusters × 3 instances each.

## Pre-existing audits (Phase 4-v2 era, no synthetic test):

- audit_3d_model_coverage.py — verifies 3D model attached to every fp (assembly visualization)
- audit_meta.py — RULES_MANIFEST.md ↔ scripts consistency
- audit_routing_system.py — methodology hash drift detection


## Batch-4/5/6 audits + parser-fix iteration (no synthetic test fixture yet)

The following audits were added in PRs #112-#130 with smoke-test on Stage 1 + worker CH1 boards (not synthetic ground-truth comparison — pending Phase 2):

- audit_anchor_pitch.py (G_PP8) — per-column same-role uniform pitch
- audit_polarity_direction.py (G_PP9) — same-class polarized fp rotation axis
- audit_zone_tile_continuity.py (G_Z1) — primary subsystem zone overlap detection
- audit_assembly_drawing.py (G_M5) — fp Value + rotation + attribute presence
- audit_sim_mesh_validity.py (G_S2) — Elmer mesh node/element count
- audit_sim_result_sanity.py (G_S3) — T/I/V/P range plausibility
- audit_stub_length.py (G_R2) — Howard Johnson HSDD §6 stub limits
- audit_crosstalk_spacing.py (G_R4) — aggressor-victim spacing per Bogatin §10
- audit_fos_cap_voltage.py (G_FoS3) — type-keyed cap voltage derating
- audit_panel_fit.py (G_M6) — JLC single-board envelope
- audit_diff_pair_z0.py (G_R1) — trace width vs Z0 spec
- audit_return_path.py (G_R3) — signal layer ↔ ref plane pour
- audit_antenna_structure.py (G_R6) — aggressor cumulative length λ/4
- audit_fos_cap_ripple.py (G_FoS4) — cap ripple-rating vs RMS × FoS
- audit_bom_lcsc.py (G_M4) — LCSC stock + part-number presence


## G_M7-M14 mount-hole + pad-edge audits (added 2026-05-26)

| Gate | Script | Purpose |
|---|---|---|
| G_M7 | audit_mount_hole_keepout.py | Every TP/connector/fiducial/motor pad ≥ KO radius from every mount hole |
| G_M8 | audit_mount_hole_keepout.py | Highway corridor clear of every mount-hole keep-out circle |
| G_M9 | audit_mount_hole_keepout.py | Every mount hole inside a defined subsystem zone (corner-edge OK) |
| G_M10 | audit_mount_hole_keepout.py | Mount-hole pattern matches a documented frame standard (90/75/30.5/20/36mm); >4 holes requires explicit [invariant-change] PR |
| G_M11 | audit_mount_hole_keepout.py | Mount holes come in mirror_X(50) pairs per R20 |
| G_M12 | audit_mount_hole_keepout.py | No two mount holes < 10mm c-to-c (stress concentration) |
| G_M13 | audit_mount_hole_keepout.py | Every mount hole ≥ 3mm from board edge |
| G_M14 | audit_pad_edge_clearance.py | Every fixed pad bbox ≥ 0.5mm from board outline (covers TPs/connectors/fiducials/motor pads/mount holes) |

**Class-of-mistake context**: G_M7-M13 added after PR #122 H5-H8 cinematic-mount fiasco (added 4 mounts without checking surrounding TPs/highways/keepouts). G_M14 added after my PR #137 OWN mistake — moved TP2 to (2,89) which put its 4mm pad bbox flush against x=0 board edge.

Both audit batches enforce [[feedback-sai-catches-are-samples]] + [[feedback-codify-not-patch]]: any class-of-mistake gets a CODIFIED audit gate so it can never recur silently.


## G_PP11/G_PP16/G_PP19/G_PP20/G_PP21/G_META1 audits (PR #137-149)

| Gate | Script | Purpose |
|---|---|---|
| G_PP11 | audit_body_bbox_overlap.py | Same-layer component-body bbox overlap (the big miss caught 2026-05-26 by Sai-eye after 55 gates passed 57 overlaps) |
| G_PP16 | audit_channel_bom_match.py | Per-channel (role,value) BOM consistency — R20 symmetry deep-check (staged-mode aware: FET-presence per channel) |
| G_PP19 | audit_routing_channels.py | 8 reserved routing channels (4 per-channel FET/east + 4 inter-sub-zone MOTOR/LOGIC) clear of components (mechanical anchors TP/FID/H exempt) |
| G_PP20 | audit_zone_density.py | Per-zone density budget (≤55% comp, ≥20% routing, ≥25% headroom); staged-mode aware for CH zones (advisory only when <4 channels have FETs) |
| G_PP21 | audit_parametric_compliance.py | parametric_placement.py engine ↔ lockfile YAML + BOARD_INVARIANTS.md sync (19 relationships verified) |
| G_META1 | audit_meta_coverage.py | META: scans audit_*.py + verify_*.py + FAILS if any not wired into master_pre_merge.sh as BLOCKING (or explicitly deferred in docs/AUDIT_DEFERRED.txt). Catches future migration-drift orphan audits. |

Context: G_PP11 closed the audit-suite gap that allowed verify_placement.py's bbox-overlap detection to be orphaned during Phase 4-v1→v2→v3 migrations. G_META1 prevents future orphans. G_PP19-21 implement the parametric placement framework (Sai 2026-05-26 directive). G_PP16 implements per-channel BOM consistency for R20 symmetry verification.

Also Sai-adjudicated 2026-05-26 batch 2.5: G6 highway_reservation now SAME-NET EXEMPT — a same-net component pad inside its highway is the intended electrical tap (e.g., VMOTOR bypass cap in VMOTOR feed corridor), not a routing violation.
- audit_routing.py check_unrouted_nets (added 2026-05-26) — 7th check on audit_routing.py: every multi-pad non-plane-served net MUST have ≥1 track segment. Class lesson: worker's GetEdges() ratsnest API silently returned 0-open on v2b board with 6 genuinely-unrouted nets (GLB/GLC gate, OTP_TRIP_N, PWM_INHA/INHC/INLB). API claimed success without doing the work (sibling of [[reference-sim-claimed-not-executed]]). Track-count cross-check catches it regardless of API behavior. Optional `--subsystem CHn` arg scopes check to subsystem PRs per §8. Validated against worker's pre-J22-fix v2b board: catches 28 unrouted CH1 nets including all 6 of worker's R22 catch.
