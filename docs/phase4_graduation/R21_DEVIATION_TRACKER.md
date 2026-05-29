# R21 Deviation Tracker — Phase 4-v3 CH1 STEP-6 → Phase 5 reconciliation queue

Per CLAUDE.md §3 Rule 21 (Worker Deviation Disclosure), this document tracks
ALL placement/routing deviations from R19 mirror invariant + R23 anchor rules
that were accepted at Phase 4 close-out and must be reconciled in Phase 5.

## DEV-001: J19_CH1 placement single-channel state
- **Description:** J19 (DRV8300 gate driver) placed at (24.20, 62.52) for CH1
  ONLY. CH2/3/4 equivalents (J24/J25/J26) parked off-board at (215, -25)+.
- **R19 invariant violated?** Yes — cross-channel gate-driver mirror cannot be
  enforced because mirror targets not placed.
- **Phase 5 reconciliation:**
  1. Place J24/J25/J26 in CH2/3/4 subsystem zones with subsystem-zone-mirror
     transform from J19 position
  2. Re-run loop-L per-phase × 4 channels; verify R19 spread ≤5%
  3. Re-route all 4 channels with full --pathfinder + multi-mech + BB
- **Provenance:** sims/routing_provenance/j19_micro_relief/*.json

## DEV-002: J19 micro-relief trials (north + east) — empirical no-go
- **Description:** Phase 4 attempted J19 north +1.5mm (regressed 26/30) and
  J19 east +1.5mm + R76 east +0.5mm (29 routes BUT 34 shorts). Both reverted.
- **Phase 5 implication:** When mirror placement is done, J19 will go to the
  PRE-MOVE canonical position (24.20, 62.52). Phase 5 placement-rev may
  redefine J19 + J18 + TP21 corridors with broader spacing to allow chronic
  3 closure without micro-relief.
- **Phase 5 must NOT REPEAT:** R76 east move (made R76.1 leaf distance worse)
- **Provenance:** sims/routing_provenance/26of30_post_J19_north/,
  sims/routing_provenance/29of30_post_J19_east_SHORTS/,
  sims/routing_provenance/option_VI_shorts/

## DEV-003: Chronic 3 residual nets — Phase 4 carry-over
- **Description:** PWM_INHB_CH1, GLB_CH1, KILL_RAIL_N_CH1 R76.1 leaf NOT
  routed at Phase 4 graduation. Empirical evidence after 14-lever exhaustive
  test shows micro-relief insufficient; structural placement-rev needed.
- **Phase 5 reconciliation:**
  1. After CH2/3/4 placed, retry full --pathfinder + BB on canonical
  2. If still residual: placement-rev option (broader J18-J19 corridor,
     TP21 relocation, or J21 INA186 shift)
  3. If still residual after placement-rev: hand-route via hand_route_residual.py
     (Phase 5 may extend the via-class set with B.Cu microvia integration)
- **Provenance:** all sims/routing_provenance/27of30_* and 26of30_*

## DEV-004: PathFinder + K3 chain through-via emission at J19 area
- **Description:** Empirical finding: K3 multi-mech chain=['through','through']
  emission near J19's signal-pin column creates 10+ shorts intrinsically. Not
  a router bug — fundamental fab-class collision between through-via clearance
  + 0.5mm J19 pitch.
- **Phase 5 implication:** BB B.Cu microvia path needed for chronic-residual
  rescue; through-via via-in-pad at 0.5mm pitch is fab-infeasible.
- **Provenance:** sims/routing_provenance/27of30_post_BB/

## Reconciliation gate (Phase 5 entry)
Before Phase 5 closure: each DEV entry must be either CLOSED (reconciled) or
RE-ACCEPTED with new R21 disclosure pointing to evidence of why the deviation
persists. NEVER silently drop.
