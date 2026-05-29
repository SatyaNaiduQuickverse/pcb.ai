# Sai Page — J19 north +1.5mm REGRESSED to 26/30, empirical structural-infeasibility proof

## TL;DR
**J19_CH1 NORTH +1.5mm move REGRESSED route count: 27/30 → 26/30.** SWDIO_CH1 (which was K3-routable pre-move) now fails because J19's south-row shift broke SWDIO's existing K3 chain clearance. KILL_RAIL_N reached `partial 1/2` (one pad-pair routed — closest ever) but still atomic-rollback. PWM_INLA + GLB unchanged.

**Per master directive ≤27 + J19-relief failed: empirical proof of deeper structural infeasibility.** Phase 5 placement-rev needed; CH1-only J19 micro-relief cannot achieve 30/30.

## Move applied
- `j19_micro_relief.py` (NEW permanent tool, codified per Sai)
- J19_CH1 (DRV8300, HVQFN-24-1EP_4x4mm_P0.5mm): (24.20, 62.52) → (24.20, 61.02) NORTH +1.5mm
- R21 deviation flags: 3 (CH2/3/4 mirrors J24/J25/J26 off-board parked at (215, -25)+; cascade DEFERRED to Phase 5)
- Provenance: `sims/routing_provenance/j19_micro_relief/j19_relief_20260529T142209Z.json`

## Result
| | Pre-move (085dee9) | Post-J19-north |
|---|---|---|
| Full routed | **27/30** | **26/30** ⬇️ |
| PWM_INHB | ✓ K3 routed | ✓ K3 routed |
| PWM_INLA | ✗ partial | ✗ partial |
| GLB | ✗ partial | ✗ partial |
| KILL_RAIL_N | ✗ partial 0/2 | ✗ partial **1/2** (closest yet) |
| SWDIO | ✓ K3 routed | ✗ partial 0/1 (NEW regression) |
| PathFinder loop | committed 0/5 (30 iter) | committed 0/5 best=1/5 (30 iter, 1166s) |

## What went wrong
J19 north +1.5mm shifted:
- Pins 1-6 (west column): same column position, just 1.5mm higher in Y
- Pins 7-12 (south row): from y=64.46 → y=62.96 — **moves SOUTH-row pins INTO J19's body area at original y=62.52**
- Pins 19-24 (north row): from y=60.58 → y=59.08 — **moves NORTH-row pins closer to D38/D19 at y=57.60** (collision risk)

The "north" move actually CRUSHED the south-row escape corridor (where SWDIO's J18.23→TP22.1 chain ran) by moving J19's body into the corridor.

KILL_RAIL_N got partial 1/2 — one pad-pair routed (likely J19.8→D37.2 or similar) — but the second pad-pair still failed verify. Move helped marginally but cost SWDIO.

## Per master path: "If still <30/30 even after J19 relief: page Sai immediately with empirical evidence — that would prove deeper structural infeasibility requiring more invasive placement redo"

**EMPIRICAL EVIDENCE COMPLETE.** All software + placement-micro-relief levers exhausted:
| Lever | Result |
|---|---|
| Cooperative + W expanded budget | 25/30 |
| K3 multi-mech | +2 = 27/30 |
| Y joint K3 cascade | 27/30 |
| Z hardest-first | 27/30 |
| Strip+restart | 13/33 regression |
| AA PathFinder | 27/30 (0 commits) |
| BB B.Cu microvia | 27/30 (no new chains) |
| R76 obstacle-move | 27/30 (R76 not blocker) |
| **J19 north +1.5mm** | **26/30 REGRESSION** |
| Hand-route programmatic | dry-run In2/In8 saturated |

## Sai decision required — Phase 5 placement-rev options

**(I) Try DIFFERENT J19 directions before giving up**
- (a) east +1.5mm (24.20→25.70) — shifts pin escapes east toward J18 (closer to J18.15 for PWM_INLA)
- (b) south +1.5mm (62.52→64.02) — opposite of north; may help PWM_INLA west column
- (c) rotation 90° — re-orients escape corridors
- Cost per direction try: ~25min coop run

**(II) Multi-component micro-relief**
- Move J21 INA186 (24.50, 67.00) further from J19 south row — could open KILL_RAIL_N + GLB escape
- Move TP21 (15.00, 79.00) test point that blocks GLB In8 destination
- Cost: ~1hr per try

**(III) Accept 27/30 → Phase 4 carry-over for 3 chronic nets**
- Cost: 0
- 3 chronics manually-route in Phase 5 with proper placement
- Honest: NOT drone-grade (e-stop + 2 gate-driver inputs unrouted)

**(IV) Phase 5 invasive placement redo**
- Place CH2/3/4 first (~40-80hr per channel × 3)
- Re-do CH1 placement with broader corridor design
- True 4-channel ESC capability with R19 enforcement
- Phase 4 graduation: ship-with-honest 27/30, queue Phase 5

## Worker recommendation (Claude, honest after this empirical proof)
**Option I-(a) east +1.5mm.** J19 north FAILED because it crushed the south corridor. East may widen PWM_INLA escape (J19.1→J18.15 northeast straight-line) without disrupting south/west corridors. 25min to test definitively.

If I-(a) also regresses or stays at 27, **Option III (Phase 4 graduation at 27/30 + Phase 5 queue)** is honest — the empirical evidence shows CH1 placement is locally optimal for 27 nets but the 3 chronics require structural changes beyond micro-relief.

## Canonical reverted
HEAD `fd76744`, board MD5 `f119ac7e8a42a78f06e1acd553cb60fb` (preserved 085dee9-era T+U+V state, 27/30 routable).

J19 move provenance preserved at `sims/routing_provenance/j19_micro_relief/j19_relief_20260529T142209Z.json` for audit.

## Bundle
- `sims/routing_provenance/26of30_post_J19_north/` (post_route_j19 + coop_j19.log + this page)
- `hardware/kicad/scripts/j19_micro_relief.py` (permanent tool — supports any direction)
- All prior bundles preserved

— Worker (Claude) standing by per 10h mandate. Sai picks I / II / III / IV.
