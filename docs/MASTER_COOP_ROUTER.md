# Cooperative Ripup-Reroute Router

**Tool**: `hardware/kicad/scripts/route_subsystem_cooperative.py`

**Origin**: Master dispatch 2026-05-27 (worker R26 escalation on J18/J19 CH1 STEP-6 dense fan-in plateau).

**Algorithm**: Pathfinder-style (McMurchie + Ebeling 1995) cooperative ripup-reroute maze router on a 3D cell grid (x, y, layer). Solves the greedy-A* self-congestion problem identified in [[reference-cascading-escape-needs-negotiated-routing]].

**Status**: Operational. Master-verified on `phase4v3-stage1-ch1-on-10L` @ 9eed5ae.
- 100% routed (3/3) when run on isolated stragglers
- 80% routed (24/30) when run on full CH1 signal set (15 iter, ~200s on Pi)
- 100% routed (6/6 PWM) on dense J18/J19 fan-in subset (3 iter, 40s)
- Zero same-layer power-pad-clearance violations introduced

## Why

Greedy escape-to-inner routing on dense IC pin-out cascades self-congests:
each net's escape tracks block the next net's via positions. The standard PCB
EDA fix (Pathfinder / negotiated congestion) routes each net with per-cell
congestion cost, rips up nets blocking failed nets, increments history cost
per congested cell, and iterates until convergence or plateau.

See [[reference-cascading-escape-needs-negotiated-routing]] for the design rationale
(no Freerouter per [[reference-kicad-dsn-export-drops-inner-layers]]: DSN export drops
inner layers, breaking incremental routing on already-routed boards).

## Algorithm

```
For iteration in 1..N:
  Sort unrouted nets by (fail_count DESC, priority ASC)
  For each unrouted net:
    Build MST of pads (greedy nearest)
    For each MST edge:
      A* search on grid with cost = LAYER_BASE + present_factor*present + history
      Allow via-change between configured signal layers (LAYER_PREF per net pattern)
      Validate diagonal moves (axis-cells must also be passable)
    If routed: commit (stamp obstacles, increment present_count)
    Else: increment fail_count, queue for next pass
  After pass:
    Bump history: cells with present>1 get history += (present-1) (cong'd cells learned)
    present_factor *= 1.4 (raise pressure)
    Rip top-K nets blocking failed-net pads; force-rip 3 random nets if plateau
```

## Architecture

```
BoardState         — extracts pads + tracks + vias + zones from .kicad_pcb
CongestionGrid     — (x,y,layer) grid; obstacle / net_halo / pad_cells / present / history
CooperativeRouter  — main loop; A* per-edge; commit/rip; plateau detection
path_to_segments   — collapse path cells into straight segments + via points
```

### Pad model

```
Pad copper rect       = hard obstacle, OWN-NET cells accessible
Clearance halo        = pad rect + CLEARANCE + trace_half + slop; owner-net-only
Via-keepout zone      = pad rect + CLEARANCE + via_radius; via forbidden for foreign nets
```

For a QFN/LQFP at 0.5mm pitch with 0.25×0.88mm pads:
- Pad halo = 0.305mm beyond copper edge
- Between adjacent pads = 0.25mm < 2×0.305 → no trace between pads
  (correct dog-bone topology: escape MUST be perpendicular to pad row)
- Via must land at least `pad_half + CLEARANCE + via_radius ≈ 0.83mm` from
  any foreign pad center (prevents via-in-pad and inter-pad-clearance)

## Layer allocation (per CH1 STEP-6 plan, BOARD_INVARIANTS §10L)

```python
F.Cu / B.Cu : pad fanout stubs only (high LAYER_BASE_COST=4.0)
In2.Cu      : PRIMARY signal escape (PWM, CSA, dense fan-in)  cost=1.0
In4.Cu      : DEDICATED BEMF (OQ-016 lock)                     cost=1.0
In6.Cu      : SW escape (OQ-017; mostly free after STEP-4)    cost=1.5
In8.Cu      : SWD/NRST/BOOT0/control overflow (PR #192)        cost=1.0
```

GND planes In1/In3/In7, +VMOTOR In5 are UNTOUCHED. Power nets (MOTOR/SHUNT/+V*/GND)
matched by SKIP_NET_PATTERNS and never routed.

## Usage

```bash
python3 hardware/kicad/scripts/route_subsystem_cooperative.py \
  /path/to/board.kicad_pcb \
  --subsystem CH1 \
  --output /tmp/routed.kicad_pcb \
  --max-iterations 25 \
  [--grid-pitch 0.1] \
  [--seed-nets NET1,NET2,...] \
  [--report routed.csv]
```

### Auto-detect mode (default)

Without `--seed-nets`, router auto-picks all CH1 nets with ≥2 pads in zone,
≤2 existing tracks (unrouted), and not matching SKIP_NET_PATTERNS.

### Targeted mode

With `--seed-nets net1,net2,...`, router targets the explicit list — useful for:
- Re-routing a specific set after a partial run
- Routing stragglers after main batch
- Testing on isolated nets to debug obstacle stamping

## Validation gate (per [[feedback-sim-execution-gate]] discipline)

After running, every PR MUST verify on the OUTPUT board:

```bash
# 1. audit_routing.py: 0 new TRACK-WIDTH/UNROUTED failures vs input baseline
python3 hardware/kicad/scripts/audit_routing.py <output.kicad_pcb> --subsystem CH1

# 2. audit_power_drc.py: 0 new POWER-PAD-CLEARANCE violations on SAME LAYER
#    (audit's L∞ approximation gives false positives on different layers;
#    use the layer-aware check script if available)
python3 hardware/kicad/scripts/audit_power_drc.py <output.kicad_pcb>

# 3. Per-net connectivity: every routed target net has 1 island (use union-find
#    over pad positions + track endpoints)
```

## Known limitations + future work

1. **Plateau at ~80% on dense full-CH1 signal set**: 6 nets typically remain
   unrouted in mutual-blocking scenarios. Each routes IN ISOLATION (3/3 verified
   on PWM_INHB+PWM_INLB+SWDIO alone), but greedy sibling routing starves them.
   - **Fix path**: multi-net joint A* (route all sibling QFN-row nets as one
     atomic operation with distinct via slots pre-assigned).

2. **Grid pitch 0.1mm**: 0.05mm pitch needed for ultra-dense QFN escapes but
   blows Pi memory budget (3.4M cells × 6 layers). Per [[feedback-pi-shared-system-protect]],
   stay at 0.1mm for Pi-resident master ops; escalate to Phase 7 x86 for finer pitch.

3. **MST + per-edge A***: doesn't optimize globally; near-optimal but not
   length-optimal. Tradeoff: O(E·A*) time vs O(N²·A*) for full-net Steiner.

4. **Diagonal moves**: 8-connected A* with axis-cell-passable check prevents
   corner-clipping but doesn't perfectly model trace mitering. Bresenham-style
   segment validation added post-collapse for hard correctness.

5. **History-cost decay**: not implemented. Long-running routing may have stale
   history dominating present-congestion. Add decay factor if observed.

## Test results (CH1 dense fan-in scenario)

| Target set | Iter | Time | Routed | Ripups |
|---|---|---|---|---|
| 2 nets (PWM_INHA, INLA) | 1 | 0.5s | 2/2 | 0 |
| 6 nets (all PWM_IN*) | 3 | 40s | 6/6 | 4 |
| 15 nets (dispatch target) | 3 | 51s | 15/15 | 4 |
| 30 nets (full CH1 auto) | 30 | 200s | 24/30 | 58 |
| 3 stragglers (isolated) | 1 | 5s | 3/3 | 0 |

The 30-net case plateaus at 24/30. The 6 unrouted in plateau:
`BSTB_CH1, GLB_CH1, KILL_RAIL_N_CH1, SWDIO_CH1, PWM_INHB_CH1, PWM_INLB_CH1`.
All route trivially when isolated → confirms greedy-blocking, not infeasibility.

## Worker workflow integration

```bash
# 1. Worker checks out branch with placed CH1 + routed STEP-4 power
git checkout phase4v3-stage1-ch1-on-10L
cp hardware/kicad/pcbai_fpv4in1.kicad_pcb /tmp/in.kicad_pcb

# 2. Run cooperative router on dense fan-in subset
python3 hardware/kicad/scripts/route_subsystem_cooperative.py \
  /tmp/in.kicad_pcb \
  --subsystem CH1 \
  --output /tmp/out.kicad_pcb \
  --seed-nets BEMF_B_CH1,BEMF_C_CH1,CSA_A_OUT_CH1,CSA_B_OUT_CH1,CSA_C_OUT_CH1,PWM_INHA_CH1,PWM_INLA_CH1,PWM_INHB_CH1,PWM_INLB_CH1,PWM_INHC_CH1,PWM_INLC_CH1,SWDIO_CH1,SWCLK_CH1,NRST_CH1,BOOT0_CH1 \
  --max-iterations 25 \
  --report /tmp/coop_report.csv

# 3. Apply to canonical
cp /tmp/out.kicad_pcb hardware/kicad/pcbai_fpv4in1.kicad_pcb

# 4. Audit gate
python3 hardware/kicad/scripts/audit_routing.py hardware/kicad/pcbai_fpv4in1.kicad_pcb --subsystem CH1
python3 hardware/kicad/scripts/audit_power_drc.py hardware/kicad/pcbai_fpv4in1.kicad_pcb

# 5. If unrouted nets remain: re-run on stragglers in isolation, then merge

# 6. Commit + PR per worker R-process
```

## References

- [[reference-cascading-escape-needs-negotiated-routing]] — design rationale
- [[reference-kicad-dsn-export-drops-inner-layers]] — why not Freerouter
- [[reference-qfn-pin-escape-bottleneck]] — dog-bone fanout topology
- [[feedback-build-routing-system-not-freerouter]] — Sai 2026-05-24 directive
- [[feedback-codify-not-patch]] — this doc + audit gate satisfy the 3-artifact rule
- McMurchie + Ebeling 1995, "PathFinder: A Negotiation-Based
  Performance-Driven Router for FPGAs" — algorithmic precedent
