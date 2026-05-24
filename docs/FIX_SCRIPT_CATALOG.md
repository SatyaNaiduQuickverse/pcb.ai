# Fix Script Catalog — Phase 4-v2 placement-class violations

**Per**: master 2026-05-24 R26 idle prep. Maps audit violation classes to existing/proposed fix scripts so if Sai chooses option (c) hybrid or (d) revisit on /tmp/sai-queue.md, worker can act fast.

## Comprehensive disclosure from master audit

100 audit_layout FAILs across 11 classes + 2 master_audit_invariants FAILs:
- 130 PAD-OVERLAP-DIFFNET
- 32 COMPONENT-INSIDE-BODY (regressed from PR #11)
- 29 SILK-ON-PAD
- 14 PASSIVE-ANCHORING
- 7 MOTOR-PAD-CLEAR
- 35 SUBSYSTEM_ZONE_COMPLIANCE OOZ (master_audit_invariants)
- 154 HIGHWAY_RESERVATION pad-in-corridor (master_audit_invariants)
- ...+ residual smaller classes

## Class → fix-script mapping

| Audit class | Existing fix script | Status | Proposed extension |
|---|---|---|---|
| **PAD-OVERLAP-DIFFNET** | `place_subsystem_ch{1-4}_*.py` + `place_subsystem_s{1,3,5,6}_*.py` | Per-PR ran clean for in-scope; cross-subsystem partial-board | Add `fix_cross_subsystem_overlap.py` — finds CH-vs-non-CH overlaps + nudges non-CH fps by 1-3mm |
| **COMPONENT-INSIDE-BODY** | placement scripts use silk-bbox check via `fp_silk_relative` | Works within subsystem | `fix_cross_subsystem_inside_body.py` — same nudge pattern for cross-zone |
| **SILK-ON-PAD** | inline silk-fix loops in CH1/CH2/CH3/CH4 PRs (rotate refdes / hide) | Per-subsystem only — non-subsystem silk untouched | Extract into `fix_silk_on_pad.py` — global pass on all fps |
| **PASSIVE-ANCHORING** | role-based spiral in `place_subsystem_ch1_v3.py` | CH1 only; CH2/CH3/CH4 mirror placement may have anchor-distance drift | `fix_anchor_distance.py` — re-spiral passives >max-distance from parent IC |
| **MOTOR-PAD-CLEAR** | TP-keepout in `place_subsystem_ch1_v3.position_valid` | CH1 only | `fix_motor_pad_clear.py` — apply TP keepout globally on non-sense-net fps |
| **SUBSYSTEM_ZONE_COMPLIANCE OOZ** | none — every PR added components without checking zone | n/a | `fix_oo_zone.py` — relocate fps whose net suggests one subsystem but current XY is outside that zone |
| **HIGHWAY_RESERVATION** | none enforced at placement | n/a | `fix_highway_clear.py` — relocate fps whose pads are inside reserved highway corridors per BOARD_INVARIANTS |

## Inline-fix scripts written but not extracted to repo

Several fix-passes were written inline (ad-hoc Python in bash heredocs) during PR iterations:
- `silk_fix.py` pattern (PR #91 v7): post-pass radius-12-angle search for ref-text relocation
- `r36_shift.py` (PR #94 v2): single fp position fix
- `c168_l6_shift.py` (PR #96 v2): single fp position fix
- `r141_spiral.py` (PR #98): single fp position fix

These should be consolidated into `scripts/fix_audit_violations.py` with class-dispatcher CLI.

## Proposed `fix_audit_violations.py` interface

```python
# scripts/fix_audit_violations.py <class> [--apply | --report]
#
# Classes:
#   silk-on-pad         — rotate/hide refdes
#   inside-body         — nudge invader fps 1-3mm
#   diffnet             — same as inside-body for invader-side
#   anchor-distance     — re-spiral passive from parent IC
#   motor-pad-clear     — TP-keepout enforcement
#   oo-zone             — relocate by net-suffix → expected zone
#   highway-clear       — relocate from highway corridors
#   all                 — run all passes sequentially
```

## Recommended execution order (if Sai picks option c)

1. Strip ALL existing tracks/vias (clean placement state)
2. `fix_audit_violations.py oo-zone` — get components into correct zones first
3. `fix_audit_violations.py highway-clear` — clear corridors
4. `fix_audit_violations.py inside-body diffnet` — resolve geometric collisions
5. `fix_audit_violations.py anchor-distance` — re-spiral stray passives
6. `fix_audit_violations.py silk-on-pad` — final DFM cleanup
7. Re-run full audit suite to verify
8. Re-run route_subsystem.py CH1 (PR-B will re-iterate cleanly)

Estimated time: 2-3h for script consolidation + 1-2h iteration to 0 fails per class.

## Status

Catalog drafted. If Sai picks (c) hybrid:
- Document existing fails as "Phase 4-v2 inheritance" in PR-A documentation amend
- Implement `fix_audit_violations.py` as a follow-up PR before any new placement work

If Sai picks (d) revisit:
- Use catalog to triage which PRs need re-do
- Order by impact: power/HV-related zones first (S1/S2/S3), then channels

If Sai picks (a) invariant change:
- Catalog still useful — relaxes which checks are "blocking" but doesn't remove the underlying physical drift.

## Worker availability

Standing by on PR #100 PR-B (audit_routing 6/6 PASS, ready for merge once upstream cleared). Doing R26 idle prep per master direction. No new placement work until Sai adjudication.

target.h md5: 7a4549d27e0e83d3d6f1ffaf67527d24 (locked throughout — 9 placement PRs + routing iteration, never touched).
