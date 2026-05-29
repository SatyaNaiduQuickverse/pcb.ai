# Sai Page — BB result + B+ J19 micro-relief escalation

## TL;DR
**BB applied — STILL 27/30 — same 3 chronics.** B.Cu microvia fab class enabled correctly (log confirms LEVER BB activation for refs J19, R50, R76, D37, D38 on the 3 chronic nets) but K3 sequential pass generated NO new B.Cu microvia chain candidates. Same `chain=[]` for PWM_INLA + GLB, same `partial 0/2` for KILL_RAIL_N. Per master rules ≤27 → page Sai with B+ J19 micro-relief option costed.

## BB activation confirmed
```
[main] LEVER BB: B.Cu microvia destination-side HDI escape enabled
    nets=['PWM_INLA_CH1', 'GLB_CH1', 'KILL_RAIL_N_CH1']
    refs=['J19', 'R50', 'R76', 'D37', 'D38']
```

## Result: 27/30 (unchanged)
```
[pf] PathFinder loop DONE. committed=0/5 unrouted=5 best_ever=0/5 iterations=30 total_ripups=0
[pf] JOINT K3 result: 0/5 rescued
[pf] SEQUENTIAL K3: PWM_INHB ✓ SWDIO ✓; PWM_INLA ✗ GLB ✗ KILL_RAIL_N ✗
[targeted-ripup] phase done: 0/3 attempts committed.
Result: full=2/5 partial=0 unrouted=3
```

K3 chain detail for chronics shows no new B.Cu chains attempted:
- PWM_INLA_CH1: `aggregate status=partial (0/1 pairs routed)` — no chain printed
- GLB_CH1: `aggregate status=partial (0/1 pairs routed)` — no chain printed
- KILL_RAIL_N_CH1: `aggregate status=partial (0/2 pairs routed)` — no chain printed

BB unit tests pass 18/18 + 20/20 self-check, but the live K3 planner integration doesn't surface B.Cu microvia paths for these specific chronic geometries. The B.Cu-side congestion (the F→In8 stacked attempt I tested earlier hit TP21 4×4mm pad on In8 from F-side, and from B.Cu the same In8 obstacle persists) may be the underlying issue.

## All router-side levers now empirically exhausted
| Lever | Result |
|---|---|
| Cooperative + targeted-ripup + leaf-route | 25/30 |
| K3 multi-mech (W expanded budget) | +2 → 27/30 |
| Y joint K3 cascade 5→4→3→2→1 | 27/30 (chronics fail every k) |
| Z route-hardest-first | 27/30 (chronics fail solo at k=1 on CLEAN) |
| Strip+restart | REGRESSION to 13/33 |
| R76 single-move | 27/30 (R76 not blocker — proven) |
| AA TRUE PathFinder negotiated congestion | 27/30 (0 commits in 30 iters) |
| Hand-route programmatic | dry-run shows In2/In8 saturated, TP21 blocks GLB In8 |
| **BB B.Cu microvia fab class** | **27/30** (BB activated, K3 generates no new chains) |

## Decision per master path (≤27 → B+ J19 micro-relief)

### Option B+ scope (J19 micro-relief)
- **J19 footprint inspection:** see provenance file `j19_inspect.txt`
- J19 is at (24.20, 62.52), rotation 0° — likely 24-pin 0.5mm pitch FFC/header
- Approx 30+ connected nets in CH1 alone
- **Mirror connectors:** J19 (CH1), what about CH2/3/4?
  - J20 might exist but with different purpose
  - The 4-in-1 FPV ESC may use a SINGLE J19 for all 4 channels (DShot to FC) — in which case no mirror
  - OR J19 mirrors to J20/J21/J22 — full R19 cascade

### Cost estimates per scenario

**Scenario A (no J19 mirror — single FC connector per topology):**
- J19 ±1.5mm move: 5 min
- CH1 re-route + DRC + audit: 30 min
- Loop-L re-sim: 10 min
- master_pre_merge: 30 min
- **Total: ~1.5 hours**

**Scenario B (J19 has CH2/3/4 mirrors per R19):**
- 4 connector moves: 15 min
- 4-channel re-route + DRC: 1.5 hours
- 4× loop-L sim: 40 min
- 4× master_pre_merge: 1.5 hours
- R19 spread verify ≤5%: 15 min
- Sai-eye final review: 30 min
- **Total: 5-6 hours**

### Mirror determination needed
Per locked rule §19 (R19 symmetry preserves work): worker MUST verify CH2/3/4 mirrors before B+ execution. The provenance `j19_inspect.txt` shows candidate refs at known locations.

## Decision for Sai
**Option B+ (J19 micro-relief)** is the master-stated path per ≤27 rule. Cost ranges 1.5hr (no mirror) to 5-6hr (full R19 cascade). Worker requires Sai approval for:
1. **Direction of J19 move:** options are (a) east +2mm to widen escape corridors, (b) south +1.5mm to shift below J21/D29 cluster, (c) rotation 180° to re-orient pin escapes
2. **Mirror policy:** if J19 has mirrors, must they be moved identically? (R19 strict mirror invariant per §19)
3. **Acceptance threshold:** if B+ achieves 29-30/30, ship; if still ≤27, what's the Phase 4 graduation policy?

## Worker recommendation (Claude, honest)
**Sai picks direction + mirror policy → worker executes B+ deterministically.** Cannot proceed without these decisions because the move axis affects R19 compliance + cascades to CH2/3/4 sim re-run scope.

If Sai prefers to defer placement-rev to Phase 5: **ship 27/30 with documented Phase 4 carry-over** (3 chronic nets requiring hand-route or placement-rev). Drone-grade compromise: KILL_RAIL_N (e-stop) + GLB + PWM_INLA unrouted = 10% incomplete.

## Bundle
- `sims/routing_provenance/27of30_post_BB/` (post_route_bb + coop_bb.log + bb_trace.txt + this page)
- `sims/routing_provenance/27of30_post_BB/j19_inspect.txt` (J19 footprint + mirror candidates)

Canonical preserved at `085dee9` throughout all attempts. T+U+V architecture intact. Loop-L A/B/C = 0.173/0.170/0.171 nH, R19 spread 1.56% PASS.

— Worker (Claude) standing by per 10h mandate. Sai picks B+ direction + mirror policy + acceptance threshold.
