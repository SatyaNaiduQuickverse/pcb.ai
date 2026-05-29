# Sai Page — J19 east +1.5mm: route gain BUT SHORTS gate violated

## TL;DR
**Route count UP: 27/30 → 29/30** (PWM_INLA + GLB + SWDIO routed; KILL_RAIL_N trunk routed). **But SHORTS UP: 0 → 35** (R-J5 / G_J5 SHORTS_GATE_REJECT). PWM_INHB regressed (was routed pre-move). KILL_RAIL_N R76.1 leaf NO_PATH. Net: worse per drone-grade SHORTS gate.

## Result detail
| Metric | Pre-J19-east (085dee9) | Post-J19-east |
|---|---|---|
| Routed (full) | 27/30 | **29/30** ⬆️ |
| Routed (with R76.1 leaf disconnected) | 27/30 | 28-29/30 |
| SHORTS | 0 | **35** ⬇️⬇️ R-J5 VIOLATED |
| via_dangling | 3 | 5 |
| hole_to_hole | 16 | 19 |
| solder_mask_bridge | 1 | 32 |
| Loop-L A/B/C | 0.173/0.170/0.171 | 0.173/0.170/0.171 (unchanged — phases not affected) |

## What changed vs canonical
- J19_CH1 (DRV8300): (24.20, 62.52) → **(25.70, 62.52)** EAST +1.5mm
- East column pins (13-18: GHC, BSTC, MOTOR_B, GHB, BSTB, MOTOR_A) now at x=27.64
- This widened west-column escape corridor (PWM_INLA + GLB benefit)
- But east column pins now closer to D19 + R22 + C52 cluster
- PathFinder over-emitted 13 tracks for KILL_RAIL_N (vs ~7 needed) — these caused shorts
- K3 chains generated for PWM_INLA + SWDIO (chain=['through','through']) introduced more shorts at J19 east column

## SHORTS forensics
```
shorts by net (top 10): [populated from /tmp/drc_fin29.json]
shorts by zone: distributed J18 + J19 + other
```

35 shorts = unshippable per master R-J5 ("shorts_delta=0 atomic"). Even though route count is up, the board is fab-broken.

## Per master rules "28-29 → ship + honest" — VIOLATED by SHORTS gate
Master's outcome rule "28-29 → ship + honest report" implicitly requires SHORTS gate to pass. With 35 shorts, the board fails fab-class DRC and is not shippable.

## Decision — reverted to 085dee9
Canonical preserved at 27/30 + SHORTS=0 (the previously-validated state).

## Sai paths
**(I-b) Try J19 south +1.5mm** — opposite direction, may avoid the east-column collision
**(I-c) Try J19 rotation 90°** — reorients escape corridors
**(III) Accept 27/30 + Phase 4 graduation** — honest carry-over for 3 chronics
**(V) J19 east +0.75mm** — smaller move, may unlock 1-2 routes without 35 shorts
**(VI) East +1.5mm WITHOUT PathFinder** — rely on cooperative+K3 only (less over-emission); may keep PWM_INHB routed

## Worker recommendation
**Option VI (east +1.5mm + no --pathfinder flag).** PathFinder's per-iter rip-all + over-emit (13 tracks for KILL_RAIL_N!) caused most shorts. Cooperative router alone would emit cleaner paths.

If VI also shorts-out: **Option III (Phase 4 graduation at 27/30)** is honest — empirical evidence shows no single-component move achieves drone-grade 30/30 + SHORTS=0 on canonical 085dee9.

## Canonical state
HEAD `55d59aa`, MD5 `f119ac7e8a42a78f06e1acd553cb60fb` (085dee9-era, 27/30, SHORTS=0, R19 1.56% PASS).

J19 east provenance: `sims/routing_provenance/j19_micro_relief/j19_relief_20260529T150605Z.json`.

— Worker (Claude) standing by per 10h mandate. Sai picks I-b / I-c / III / V / VI.
