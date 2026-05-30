# Phase 5 Step B — CH1 Re-place with engineered J19 (task #215)

Per Sai 2026-05-30 directive (post Phase 5 router-side wall empirically
proven 10/10 levers fail = placement-bound chronic confirmed):
re-place CH1 with engineered J19 anchor from CC Step A grid (#260).

## Candidate selection from #260 grid

20 candidates passed pre-filter; all tied at Phase A FoS=2.86× supply/demand
(Phase A's known sub-mm-discrimination limitation per #260 honest finding).

Step B per-physics ranking:
- **Prefer east-shift** (positive dx) — Phase 4 lever I-(a) empirical evidence:
  east +1.5mm unlocked PWM_INLA + GLB + KILL_RAIL_N trunk (29 routes pre-EE,
  but with K3 through-via shorts at fine-pitch)
- **Prefer dy=0** (no Y shift) — Phase 4 J19 north -1.5mm regressed SWDIO
  south corridor
- **Prefer rot=0** (preserve pin layout) — rotation cascades whole-net re-route

Selected: **dx=+1.50, dy=+0.00, rot=000** → new J19 anchor (25.70, 62.52)

WHY pick: east-shift widens J19→J18 escape corridor (PWM_INLA J18.15→J19.1
unblock); dy=0 keeps SWDIO south corridor; rot=0 keeps pin layout (no
re-route cascade); +1.50mm is the max usable east-shift (larger exits CH1
zone east edge).

## Execution

1. `j19_micro_relief.py --dx 1.5 --dy 0.0`
2. `carve_zone_keepout.py --rect 28,60,36,62 --layer B.Cu` (Option A keepout)
3. Refill +VMOTOR / GND zones
4. Run audits:
   - G_ZONE_KEEPOUT_PROVENANCE: ✅ PASS
   - G_HDI_SYMMETRIC_WHITELIST: ⚠️ 1 stranded BSTB endpoint (C60.1 not whitelisted)
   - G_K3_CHAIN_DEPTH_COMPLIANCE: ✅ PASS
   - G_MST_ROOT_PROVENANCE: ✅ PASS
5. Cooperative router with ALL Phase 5 levers stacked:
   `--pathfinder --multi-mech-fallback --via-in-pad-allowed`
   `--bcu-microvia-allowed --route-hdi-first --enable-targeted-ripup`
   `--enable-leaf-route`

## Empirical Step B result

| Metric | Canonical (Phase 4 grad) | Step B |
|---|---|---|
| Routed | 27/30 | **26/30** (25 base + 1 K3 rescue) |
| GLB_CH1 chronic | ✗ unrouted | **✓ K3 routed** (chain=['through','through']) |
| PWM_INHB_CH1 | ✓ K3 (pre-EE) | ✗ regressed (EE refuses) |
| SWDIO_CH1 | ✓ K3 (pre-EE) | ✗ regressed (EE refuses) |
| PWM_INLA_CH1 | ✗ | ✗ |
| KILL_RAIL_N R76.1 leaf | ✗ NO_PATH | ✗ NO_PATH (verify-split still) |
| SHORTS | **0** | **9** (R-J5 violated) |
| via_dangling | 3 | 5 |

## Honest verdict

**Step B's J19 east +1.5mm with EE/CC/DD/Z/keepout stack:**
- ✅ Mechanically unlocks GLB (chain through+through emitted) — proves
  the corridor opens at the new position
- ❌ Introduces 9 K3-chain shorts at J19's east column (EE alone doesn't
  catch all collisions when chain emits through-vias near moved pin pads)
- ❌ Regresses PWM_INHB + SWDIO that K3 pre-EE routed (EE per-pad-exclude
  now refuses those chains)
- ❌ R76.1 chronic NO_PATH persists (placement-bound deeper than J19 alone)

**Net delta vs canonical: -1 net routed (26 vs 27) + 9 new shorts.** Step B
is a NET REGRESSION at this single-direction J19 move.

## What would actually close 30/30 (next dispatch)

Per the empirical evidence accumulated:
1. **Full CH1 re-placement with broader corridors** — move not just J19
   but also D15/R22/C52 (R76 corridor blockers) + TP21 (GLB In8 blocker).
   Requires `place_subsystem_ch1_v3.py` extension + new anchor map.
   ~40-80 hours scope per Phase 4 graduation notes.
2. **Schematic-level intervention** — UU.1 damping resistors with TP fanout
   at chronic endpoints adds physical relay points that decouple the
   chronic chains from J19/J18 directly.
3. **Phase 4 graduation hold + Phase 5 placement-rev scope** — accept
   27/30 SoT, queue full CH1 + CH2/3/4 placement work to a dedicated
   Phase 5 placement subagent dispatch.

## R21 deviation tracker
- DEV-014 (new): Step B J19 east trial — partial corridor unlock for GLB
  but introduces shorts + regresses other K3 routes. Mechanism confirmed
  + path forward = full CH1 placement-rev, not single-IC micro-relief.

## Status
Canonical REVERTED to Phase 4 graduation state (f119ac7e...). Step B's
9-short state preserved under sims/routing_provenance/step_B_attempt/
for evidence.

Step B SHIPS as DOCUMENTED HONEST PARTIAL — surfaces the empirical
finding that single-IC J19 move is insufficient even with all 10 Phase 5
levers stacked. Phase 5 placement-rev needs broader scope.

Per Sai "no corners cut + drone-grade" — pushing honest finding rather
than a 9-short state.
