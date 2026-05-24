# Audit Gap Report — master_audit_invariants on merged subsystems

**Per**: master 2026-05-24 — Sai-queued discipline-miss documentation for R26 idle prep.

## Issue surfaced

PR #100 v5 (CH1 routing) is CLEAN on audit_routing (6/6 PASS), BUT master_audit_invariants surfaces 2 inherited-placement FAILs that were NOT caught when individual placement PRs landed:

- **SUBSYSTEM_ZONE_COMPLIANCE**: 35 components Out-Of-Zone (OOZ)
- **HIGHWAY_RESERVATION**: 154 pads inside reserved highway corridors

These FAILs trace to placements merged across PR #91-99 — master was running `audit_layout_compliance` per PR but missed running `master_audit_invariants` to catch zone-compliance + highway-reservation violations.

## Discipline-miss root cause

Master gate review on placement PRs ran:
- ✓ `audit_layout_compliance` (16 gates: DIFFNET, INSIDE-BODY, DECOUPLING, MOTOR-PAD-CLEAR, SYMMETRY internal, SILK-ON-PAD, ANCHORING, etc.)
- ✗ `master_audit_invariants` (5 gates: BOARD_INVARIANTS_HASH, SUBSYSTEM_ZONE_COMPLIANCE, IO_PORT_COMPLIANCE, HIGHWAY_RESERVATION, SYMMETRY_PARTNER_DIFF)

Hash + symmetry-partner passed every PR. SUBSYSTEM_ZONE + HIGHWAY were treated as documented partial-board FAILs per scope policy — but each merged PR added new components to non-original zones, accumulating zone-noncompliance.

## Pre-existing state per audit

```
master HEAD (post-PR #99) master_audit_invariants:
  [PASS] BOARD_INVARIANTS_HASH
  [FAIL] SUBSYSTEM_ZONE_COMPLIANCE: 35 components OOZ
  [WARN] IO_PORT_COMPLIANCE: 15 mismatches (documented per partial-subsystem)
  [FAIL] HIGHWAY_RESERVATION: 154 pads in reserved highways
  [PASS] SYMMETRY_PARTNER_DIFF
```

## 3 resolution options (Sai-queued)

### (a) Invariant change

Relax SUBSYSTEM_ZONE_COMPLIANCE + HIGHWAY_RESERVATION rules in `master_audit_invariants.py` to ACCEPT partial-board states (current per-PR policy was implicit; codify as gate-behavior).

Risk: invariant relaxation removes a safety check that catches genuine placement drift.

### (b) Placement REDO

Re-open each merged placement PR, fix zone-compliance + highway-reservation, re-merge. ~9 PRs × ~30-60min per fix = 4-9 hours.

Risk: cascading rework; some "fixes" may regress audit_layout_compliance gates.

### (c) Hybrid

- Run `master_audit_invariants` as part of audit_meta orchestrator going forward (catch new violations at insert)
- Document existing 35 OOZ + 154 highway-pad as "Phase 4-v2 Step 2 known-inheritance" — accepted for fab-prep iteration
- Address selectively if specific OOZ/highway components matter for routing or thermal

## Recommendation

(c) hybrid — gate going forward, document inheritance. The audit_routing 6/6 PASS on PR-B v5 shows the routing layer is CLEAN; placement-inherited issues are upstream and don't block routing iteration. Full placement redo would lose 9 PRs of validated progress.

Codify rule: every placement PR going forward MUST run BOTH `audit_layout_compliance` AND `master_audit_invariants` before master merge. Add to audit_meta.

## Implementation gap codified for next iteration

```python
# Master discipline rule (per feedback-anticipate-sai-default + Phase 4-v2):
# placement PR gate = audit_layout_compliance ∪ master_audit_invariants ∪ audit_routing_system
# (NOT just audit_layout — that misses zone-compliance + highway-reservation)
```
