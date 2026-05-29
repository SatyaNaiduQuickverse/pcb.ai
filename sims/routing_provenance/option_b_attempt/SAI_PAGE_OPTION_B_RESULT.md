# Sai Page — Option B R76-move result + J19 micro-relief escalation

## TL;DR
**Option B R76-only move FAILED to improve routing.** Result still 27/30 with EXACTLY the same chronic residuals (PWM_INLA, GLB, KILL_RAIL_N). R76 was NOT the actual blocker. Per master path: ≤27 → J19 micro-relief decision.

## What was tried (Option B execution)
1. `move_obstacle.py` (new — codifies G_OBSTACLE_MOVE_PROVENANCE per Sai directive)
2. Applied R76 NORTH +2mm: (34.75, 60.80) → (34.75, 58.80) B.Cu
3. R23 anchor check: R76 is +3V3 pull-up to KILL_RAIL_N_CH1 (10K); pad2 (+3V3) within 2mm of decoupling caps — OK
4. R19 mirror disclosure: **NO_MIRROR** — R176 has value=1K + parked at (260,15) off-board (different schematic role); no R276/R376 placed on board
5. Refilled zones + relaunched coop with `--pathfinder --multi-mech-fallback --via-in-pad-allowed --enable-targeted-ripup --enable-leaf-route --route-hdi-first`

## Result: STILL 27/30
```
[pf] PathFinder loop DONE. committed=0/5 unrouted=5 best_ever=0/5 iterations=30 total_ripups=0
[pf] JOINT K3 result: 0/5 rescued
[pf] SEQUENTIAL K3: PWM_INHB ✓ SWDIO ✓; PWM_INLA ✗ GLB ✗ KILL_RAIL_N ✗
Result: full=2/5 partial=0 unrouted=3, 30 iterations, 30 ripups
```

Even with R76 closer to D38.2 (4.43mm→3.29mm), KILL_RAIL_N still gets ROUTED-but-SPLIT verify rejection every PathFinder iter (30 times). The leaf attaches but MST verify says R76.1 is its own island.

**Diagnosis correction:** R76 was NOT the actual blocker. The chronic split is on the J19.8 escape side, not the R76 terminus side. K3 multi-mech reported `chain=[]` for KILL_RAIL_N's 2 attempted pad-pairs — meaning planner couldn't generate ANY HDI chain for J19.8 escape.

## Per-net blocker analysis (per Sai directive 2)
### PWM_INLA_CH1 (J18.15→J19.1, 7.07mm)
**Single major blocker:** **J21 (INA186A3IDCKR op-amp SOIC)** at (24.50, 67.00) sits ON the straight-line corridor between J18.15 (33.00, 68.44) and J19.1 (22.26, 61.27).
- J21 is the current-sense amp for MOTOR_B_CH1
- Moving J21 cascades to: BEMF_B, CSA_B_OUT, MOTOR_B sense circuit
- **R19 mirror cascade:** J22/J23/J24 (INA186 for MOTOR_C/A/?) — must mirror per per-phase symmetry
- **Estimated cost:** 4-6 hours (place all 4 INA186, re-route 4 channels, re-sim loop-L ×4, R19 spread verify)

### GLB_CH1 (J19.10→R50.1, 21.0mm — long west)
**Multiple blockers** — 19 footprints in corridor. Major obstacles:
- **TP20** (15.00, 66.00) MOTOR_B test point
- **Q7, Q8** (8.40, 66-71) motor low-side FETs
- **D27, D28** (15.15, 69.90 / 15.00, 73.00) BZT52C5V6 protection Zeners
- **J21** (24.50, 67.00) INA186 — also on this corridor
- **D35, R51, R62** at (15, 71-75) — motor B gate drive area
**No single-passive move fixes GLB.** Needs J19.10 escape-side reroute via blind/stacked microvia OR J19 pin re-place.

### KILL_RAIL_N_CH1 (4-node MST: J19.8, D37.2, D38.2, R76.1)
**Chronic split** at J19.8 escape side, NOT R76 terminus. K3 reports chain=[] for both attempted pad-pairs.
- J19.8 at (23.45, 64.46) F.Cu — fine-pitch corridor escape FAILS regardless of where R76 is
- R76 move test PROVED R76 is irrelevant
- Same blocker class as PWM_INLA + GLB: J19 fine-pitch escape

## All 3 chronics share root cause
**J19 fine-pitch pin escape congestion.** Software exhausted (W's 500k cap + AA PathFinder + Y joint + Z hardest-first + targeted moves). R76 single-move was insufficient because it's not the blocker.

## Per master path: ≤27 → J19 micro-relief decision

### Option B-extended: J19 pin micro-relief
**The move:** Shift J19 connector body by 1.5-2mm to widen pin escape corridors on F.Cu around J19.1, J19.8, J19.10, J19.23.

**R19 mirror cascade (mandatory per locked rule §19):**
- J19 has CH2/3/4 equivalents on the 4-in-1 ESC topology — likely J20 (CH2), J21 NOT (that's INA), but per typical layouts: J19→CH1, plus equivalents per channel
- Must verify which connectors map to which channels first
- **All connector-using nets in all 4 channels need re-route**

**Estimated cost (worker honest estimate):**
- J19 + 3 mirror connector moves: 30 min
- Refill + re-route 4 channels with `--pathfinder` × 4: ~30 min wall (parallel) but serial in 1 worker: ~2 hr
- 4× loop-L sim: 1 hr
- master_pre_merge × 4 channels: 1 hr
- Sai-eye final review: 1 hr
- **Total: 5-6 hours focused work**

### Option C: Accept 27/30 with carry-over
**Trade-off:** 3 chronic nets documented as Phase 4 carry-over:
- KILL_RAIL_N: e-stop hardware kill — drone-grade compromise (safety net not connected at fab)
- GLB: gate-low B — Motor B can't be driven by hardware; manual-route required
- PWM_INLA: PWM input low A — Motor A can't receive PWM; manual-route required

3 out of 30 nets unrouted = 10% incomplete. ALL 3 are critical (e-stop + 2 motor drive inputs). NOT shippable without manual-route.

### Option D: Manual-route 3 chronics in KiCad GUI
- Sai manually drags traces with KiCad's interactive router (PCB editor F.Cu/B.Cu)
- Bypasses --pathfinder verify-rejection (the SPLIT-verify is router-internal; human can see split + connect)
- **Estimated cost:** 1-2 hours Sai-time
- Result: 30/30 routed, DRC may need spot-fixing for hand-route choices

## Worker recommendation (Claude, honest)
**Option D (manual-route by Sai) for fastest 30/30 path.** The 3 chronic nets are router-verification-internal issues that human routing can see through. R19 mirror cascade for J19 micro-relief is expensive (5-6 hours) and may not be needed if 1-2 hours of manual routing achieves the same outcome.

If full automation matters (no manual-route policy), **Option B-extended (J19 micro-relief)** is the master-domain escalation per the stated path.

## Canonical state
**Reverted to 085dee9-era** (R76 move discarded — provided no improvement). MD5 `f119ac7e8a42a78f06e1acd553cb60fb`. T+U+V architecture intact. R76 move provenance under `sims/routing_provenance/obstacle_moves/R76_20260529T123951Z.json`.

## Bundle
- `sims/routing_provenance/option_b_attempt/` (post_route_b1.kicad_pcb + coop_b1.log + b1_trace.txt + this page)
- `sims/routing_provenance/obstacle_moves/R76_20260529T123951Z.json` (move provenance)
- `hardware/kicad/scripts/move_obstacle.py` (G_OBSTACLE_MOVE_PROVENANCE tooling)

— Worker (Claude) standing by per 10h mandate. Master + Sai decide D vs B-extended.
