# Phase 4-v3 Stage 1 — Tier-1 mechanical anchors

**Branch**: `phase4v3-stage1-anchors`. Builds on Stage 0 (S6). Places the remaining
Tier-1 anchors so Tier-2 channel clusters (Stage 2+) can anchor to the motor pads.

## What this PR does

`place_subsystem.py TIER1` (`bring_anchors`) places every parked lockfile anchor at
its lockfile coordinate. Foundation (mounts/fiducials/J1/J12/J14) was already placed
by park; this brings the 24 channel-owned anchors:

- 12 motor phase pads (TP19-42, `ESCMotorPad_4x4mm_5via`)
- 8 SWD pads (TP22/23/29/30/36/37/43/44) + 4 BOOT pads (TP17/24/31/38)

On-board count 34 → 58. It also re-snaps the fiducials to the #109-corrected coords
(FID1/FID4 → (8,50), FID2/FID5 → (92,50)).

## Contract change (audit_zone_contract)

Lockfile anchors are now exempt from the brought-subsystem zone/ghost logic — their
position is `audit_anchor_positions` (G1)'s responsibility. Without this, a
channel-roster motor pad placed in Stage 1 false-flagged as GHOST because its channel
isn't brought yet. (A non-anchor channel component on-board pre-channel still flags
GHOST — the exempt is anchors-only.)

## Gate status (master_pre_merge.sh --staged S6) — ALL GREEN

```
G1✅ G2✅ G3✅ G4✅ G5✅ G6✅ G8✅ G9✅ G11✅ G12✅ G13✅ G14✅ G15✅
G7⏭ (no tracks)   G10⏭ (staged — partner channels not all brought)
```

## Spec deviations (R21)

None new in this PR. (The FID coord shifts + J1/J14 fixes landed in #109 / #107.)

## Dependency note

This branch merges `origin/master` to pick up #109's fiducial-coordinate fix
(FID1/FID4/FID2/FID5 shifted off the 4×4mm motor-pad columns). target.h md5
`7a4549d27e0e83d3d6f1ffaf67527d24` unchanged. Netlist unchanged.

## Next

Stage 2 = CH1 (hardest channel first): fill `routing_topology.yaml` CH1 component
roles + real role-based cluster placement anchored to the Tier-1 motor pads; R34
scoped-Freerouter available for the dense MCU pin breakout (scope declared per R34).
