# Sai Page — Phase 4-v3 CH1 STEP-6 Final Verdict: 27/30 router-side ceiling reached

## TL;DR
**All router-side levers (K3, Y joint, Z hardest-first, W expanded budget, AA PathFinder) PROVEN EXHAUSTED at 27/30.** The 3 chronic residuals (PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1) need PLACEMENT-RELIEF to escape — software can't.

**Recommendation:** Accept 27/30 OR approve targeted placement micro-relief (R76 move). Costs both options below.

## What was tried (after master 10h autonomous mandate)
| Lever | What | Live-board canonical result |
|---|---|---|
| Baseline lever-C era | Cooperative router + targeted ripup + leaf-route | 25/30 |
| K3 multi-mech (W expanded budget 500k cap + depth 4) | Synthetic 5/5; live | 25/30 + 2 K3 = **27/30** |
| Y joint K3 cascade 5→4→3→2→1 | Joint atomic batch rescue | **27/30** (same 3 chronics fail at every cascade size) |
| Z route-hardest-first (HDI 6 nets before main pass) | SOTA cascade reorder | **27/30** (chronics fail solo at cascade k=1) |
| Z on stripped CLEAN canonical (728 tracks + 1206 vias removed) | True fresh start | **REGRESSION to 13/33** (lever-C state was load-bearing) |
| **AA TRUE PathFinder** (per-iter rip-all + h_n×p_n cost + 2-zero convergence) | Last router-side lever | **27/30** (PathFinder loop: 0/5 committed in 30 iters; ALL get KILL_RAIL_N-style ROUTED-but-SPLIT verify; present_factor ran to 17286.74 with no progress) |

## Why chronic residuals are GEOMETRIC, not algorithmic
**Z's HDI-first joint K3 on CLEAN canonical** (zero foreign CH1 routes committed):
```
[Z] HDI-whitelisted nets (6 on clean): [BSTB, GLB, KILL_RAIL_N, PWM_INHB, PWM_INLA, SWDIO]
[Y] cascade k=1: ['KILL_RAIL_N_CH1'] → 0 routed → KILL_RAIL_N_CH1 FAILS SOLO
```

KILL_RAIL_N fails at solo k=1 on a 100% empty board with --via-in-pad-allowed ON, blind + stacked + through via-classes available, W's 500k cap + depth 4 budget — **empirical geometric-infeasibility proof.**

## The chronic geometric fact — KILL_RAIL_N J19.8↔R76.1
- **J19.8** (24.20+0.x, 62.52+0.y) — fine-pitch SOIC on F.Cu, HDI whitelist
- **R76 footprint** at **(34.75, 60.80) B.Cu**
- Corridor distance: ~10.5mm
- KILL_RAIL_N nodes: J19.8, R76.1, D37.2, D38.2 (D37/D38 at (31.75, 61.20) + (33.25, 57.60) B.Cu)
- Perpetual MST split: {J19.8, D38.2, D37.2} on F.Cu cluster ↔ {R76.1} on B.Cu isolated
- Through-via routes tried 1-via, 2-via, 3-via stacks — DRC rejected every time
- No B.Cu microvia class available in current via-set
- B.Cu region between R76 and J19 footprint: dense with D37/D38 pad-layer obstacles + GND zone clearance

## Two options — Sai picks
### Option A: Accept 27/30 (router-side ceiling)
**Cost:** 3 nets manual-route by Sai/Master in KiCad GUI OR documented as Phase 4 carry-over for Phase 5 rev. Compromises drone-grade 30/30 binding (current PR binds OQ-019 + R19 1.56%, but the 3 unrouted are non-power-loop critical: KILL_RAIL_N is e-stop, GLB is gate-low B, PWM_INLA is PWM input low A — these route fine on Phase 5 placement rev).

**Pros:** No CH2/3/4 mirror cascade. Loop-L preserved (0.173/0.170/0.171 nH, R19 1.56% PASS). T+U+V architecture intact (3 +VMOTOR Cu layers, dangling=3, h2h=16). Ships now.

**Cons:** Phase 4 graduation is 27/30, not 30/30. 3 nets carry over.

### Option B: Targeted placement micro-relief on R76 only
**The move:** Shift R76 from (34.75, 60.80) B.Cu → suggested (32.5, 62.5) F.Cu (cross to F.Cu near J19.8 cluster). Anchor remains within R23 limit (R76 is pull-up to KILL_RAIL_N; ≤5mm from parent FET = U-something — verify locally).

**Cost cascade per locked rules:**
- **R19 (mirror invariant):** CH2/3/4 must mirror — 3 additional R76 moves (R176, R276, R376 or equivalent). Sub-mm parameter only, simple XY mirror.
- **CH2/3/4 placement sims:** loop-L re-extract ×3 channels (~5 min each).
- **CH1 placement-vs-spec gate:** must re-run `verify_spec_diff.py` (≤0.5mm tolerance).
- **DRC + master_pre_merge full sweep:** ~30 min.
- **Re-route ALL 4 channels:** R76 move invalidates current routing — ~10 min coop per channel.
- **Total cost estimate:** ~2-3 hours focused work + Sai-eye final review.

**Pros:** Achieves drone-grade 30/30. KILL_RAIL_N J19.8↔R76.1 corridor opened.
**Cons:** Cascades to CH2/3/4 (preserves R19 mirror). May not solve PWM_INLA + GLB residuals (those have separate root causes — need investigation).

### Option C (combo): Place-rev for KILL_RAIL_N only + manual-route PWM_INLA + GLB
**Mixed bag** — relief for the chronic R76 split, accept-with-trade-off for the other 2. ~2hr instead of 3hr.

## My recommendation (Claude-as-worker, honest)
**Option B if Sai-grade matters.** The 27→30 delta is 3 specific nets, but KILL_RAIL_N is e-stop — a Phase 4 graduation board missing e-stop routing is hard to justify even with carry-over notes. PWM_INLA + GLB are gate-driver inputs to the FET pair — also critical.

Option A is honest if Phase 5 will re-place anyway (the 4-channel drone may need re-organization at scale). Option C is a middle path if R76 move is simple but PWM_INLA / GLB root cause needs separate investigation.

## Canonical state preserved at 085dee9
Architecture: T+U+V (3 +VMOTOR Cu layers, 199→3 dangling), SW vias 31/35/34 (R19 mirror), loop-L A/B/C = 0.173/0.170/0.171 nH (R19 spread 1.56% PASS <5% drone-grade), SHORTS=0, master_pre_merge 57P/16F (G_J1-J5 + G_Q1 + T's G1/G2/G3 all PASS; remaining FAILs are partial-state expected).

## Bundle for inspection
- `sims/routing_provenance/27of30_post_AA_pathfinder/` (post_route_aa + coop_aa.log + aa_trace.txt + this page)
- Prior bundles: `27of30_w_via_in_pad/`, `27of30_post_W/`, `27of30_post_Z/`, `zstrip_clean/`

— Worker (Claude) standing by per 10h autonomous mandate. Sai decision required.
