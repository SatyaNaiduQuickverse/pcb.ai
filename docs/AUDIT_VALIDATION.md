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

## TODO — pending validation

The following audits ship in PR #103 but are NOT YET validated against ground
truth. Each needs a test fixture + truth-comparison run before being trusted:

- `audit_via_stitching_density.py` — Tier 1 PDN gate
- `audit_length_match.py` — Tier 5 signal highway gate
- `audit_zone_contract.py` (worker's G2) — partial — passes real-board E2E but
  no synthetic ground-truth comparison yet

Phase 2 (post-PR):

- Fetch reputed external KiCad PCB (e.g. VESC 6.x by Benjamin Vedder) as
  real-world cross-check. Run all audits, compare against published spec.

## Rule

**Per R32 (sureshot > SOTA)**: any audit added to `master_pre_merge.sh` must
have a ground-truth test case in `tests/build_validation_board*.py` + a row in
the results table above. Audits without validation entries are blockers for
Phase 4-v3 Stage dispatches.
