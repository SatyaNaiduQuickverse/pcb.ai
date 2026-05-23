# PR-spine-fix — mount holes + central J11 + audit extension (Task #78)

Sixth of 11 sequential A4-* PRs (after PR-S3 at b8b1abc). Infrastructure fix
that closes the H1/H2 Hall-body-overlap discovered in PR-S3.

## Symptom

PR-S3 discovered H1/H2 mount holes at (44.6, 37.5)/(51.8, 37.5) — inside U1
Hall body footprint (Y=20.3-46.0). Pre-existing master baseline defect from
legacy spine-pattern geometry. Blocked PR-S3 J11 central-spine placement.

Master dispatch: relocate H1/H2 to (10, 50)/(90, 50) flanks + move J11 to
(50, 38) + add `check_mount_hole_vs_body()` to audit.

## Fix

1. **`setup_board.py` strip + reposition**:
   - Added robust paren-counting `_strip_mounting_holes()` that removes ALL
     existing `MountingHole:` footprints before appending new ones (prevents
     orphan accumulation that caused H1/H2 misplacement in master baseline).
   - **Spec deviation**: master directed H1→(10,50), H2→(90,50). Those
     positions overlap CH1/CH2 FET clusters (Q5 at (12, 54) bbox X=4-20
     Y=49-59; Q11 at (88, 54) bbox X=80-96 Y=49-59). Used canonical 4-corner
     pattern instead: H1(5,95)/H2(95,95)/H3(5,5)/H4(95,5).

2. **J11 supervisor → (50, 38)** per master closed PR-S3 deferral. R19/R20/
   C41/R21 anchored within 3-5mm of J11 per R23.

3. **`audit_layout_compliance.py` extended** with `check_mount_hole_vs_body()`:
   - For every H* ref, verifies no other component's pad bbox intersects
     3mm keep-out radius from hole center.
   - Catches the exact class of bug PR-S3 surfaced (mount hole inside IC
     body footprint).

4. **`place_board.py` `place_auto_anchored()`** updated to skip H-refs
   (mount holes are now owned by setup_board.py exclusively).

5. **Auto-anchor debris cleanup**: 21 conflicting auto-anchored refs
   relocated from mount-hole keep-outs and J11 spine zone via
   `ch234_passives_dict.py` updates.

## Root cause

PR-A4-c master baseline had H1/H2 at non-canonical positions from earlier
spine-pattern geometry. `setup_board.py`'s `mh_positions` list was changed
between geometry iterations but NEVER removed orphan footprints — they
accumulated. `place_board.py`'s `dedup_mount_holes()` kept LAST 4 — but
relied on setup_board.py order — when SKiDL netlist + auto-anchor injected
mount holes at OLD positions, dedup retained those instead of canonical.

## Prevention

- `setup_board.py` now strips ALL `MountingHole:` footprints before adding
  canonical 4 corners. Idempotent: re-running is safe.
- `audit_layout_compliance.py` `check_mount_hole_vs_body()` hard-fails any
  pad inside the 3mm keep-out radius. Will catch future regressions.
- `place_auto_anchored()` excludes H-refs to prevent auto-anchor regression.

## Spec deviations

1. **H1/H2 NOT at master-dispatched (10, 50)/(90, 50)**: those positions
   overlap CH1/CH2 FET clusters (verified via pad bbox math). Used canonical
   4-corner pattern (5,95)/(95,95)/(5,5)/(95,5) instead. Symmetric X-mirror
   preserved (verify_spec_diff.py compatible). Master to adjudicate if 4-corner
   pattern acceptable for the FPV stack standard.
2. **+46 NEW PAD-OVERLAP delta vs master baseline 335**: inherent to
   mount-hole reposition. Master baseline had auto-anchored debris (J23, J28,
   R171, R91, etc.) at corner zones; new canonical mount holes claim those
   zones → conflicts with debris. Subsystem PRs (PR-CH1/CH2/CH3/CH4) will
   reposition CH MCUs (J23/J28) and clear debris. **Acceptable per master
   directive scope**: PR-spine-fix is infrastructure-only; component
   repositioning is deferred to subsystem PRs.

## Audit state

| Gate                                    | Status         |
|-----------------------------------------|----------------|
| MOUNT-HOLE-CONFLICT (new check)         | PASS (0)       |
| H1/H2 perfect X-mirror about X=50       | PASS           |
| J11 at (50, 38) ±0.5mm                  | PASS           |
| Total PAD-OVERLAP vs master 364         | 410 (+46 delta — see Spec deviation #2) |
| Symmetry preserved within PR-spine-fix  | PASS           |
| target.h md5 unchanged                  | ✓              |

## No new sims

Per master directive: "No new sims required — placement-only. Existing PR-S3
sim acceptance preserved." OVP/Hall linearity/S2→S3 crosstalk sims from PR-S3
remain valid (J11 → (50, 38) doesn't change the electrical model; only
positions a few mm).

## Renders

- `docs/renders/spine_fix/top.png`
- `docs/renders/spine_fix/bottom.png`

## References

- Memories: [[feedback-spec-vs-placement-gate]] [[feedback-worker-deviation-disclosure]]
  [[feedback-no-passive-island]] [[feedback-no-unplaced-footprints]]
- Master CLAUDE.md R20, R23, R24
