# Strip+restart REGRESSED — KILL_RAIL_N geometric-infeasible from clean confirmed

## Pipeline executed
1. `strip_tracks_vias.py` removed 728 tracks + 1206 vias from canonical 085dee9
   - Preserved: 19 zones + 573 footprints (verified post-strip)
2. Ran coop with full flags + `--route-hdi-first` on stripped board

## Result: REGRESSION
- **Lever-C era canonical (085dee9):** 25/30 routed (hard-won via careful greedy+ripup sequence)
- **Strip + restart (this run):** 13/33 routed + 2 partial + 9 unrouted

`full=13/33 partial=2 unrouted=9, 30 iterations, 277 ripups, elapsed ~5min`

The cumulative greedy+ripup work that achieved 25/30 was destroyed.
Strip+restart starts fresh, hits W's expanded budget early, but on the
**physically-constrained CH1 region** the planner can't rediscover the
25-net solution — it converges to a worse local optimum.

## Critical Z HDI-first finding (on CLEAN canonical)
Z's joint K3 HDI-first phase ran with **zero foreign CH1 routes committed**:
```
[Z] HDI-whitelisted target nets (6): ['BSTB_CH1', 'GLB_CH1', 'KILL_RAIL_N_CH1', 'PWM_INHB_CH1', 'PWM_INLA_CH1', 'SWDIO_CH1']
[Y] cascade k=6: 3 routed (BSTB, PWM_INHB, PWM_INLA — different result from post-Z!)
[Y] cascade k=5: 3 routed
[Y] cascade k=4: 2 routed
[Y] cascade k=3: 1 routed (BSTB only)
[Y] cascade k=2: 1 routed (KILL_RAIL_N still fails)
[Y] cascade k=1: 0 routed (KILL_RAIL_N alone — STILL FAILS)
[Z] HDI-first phase: 0/6 rescued — proceeding to normal cooperative pass
```

**KILL_RAIL_N_CH1 fails at solo cascade k=1 on a 100% clean board.**

## Hypothesis-elimination, now complete
| Hypothesis | Disproven by |
|---|---|
| Occupancy of other routed nets | Z HDI-first SOLO k=1 on CLEAN: KILL_RAIL_N fails |
| Search budget | W's 500k+depth 4 didn't help |
| Joint vs sequential | Y cascade fails at every k |
| Greedy contention | Even hardest-first (Z) fails |
| Iteration count | 30 iter + 277 ripups from clean: worse than 25/30 baseline |

**Geometric-infeasible at current placement+via-class is now empirically confirmed for at least KILL_RAIL_N_CH1.**

## Pad-pair detail
KILL_RAIL_N nodes: J19.8, R76.1, D38.2, D37.2 (per K2 partial-MST):
- J19.8 is fine-pitch SOIC on F.Cu (HDI whitelist)
- R76.1 is the chronic disconnect — keeps becoming a 2nd MST island
- D37.2 + D38.2 cluster ~3mm from J19.8 but isolated from R76.1

The corridor J19.8↔R76.1 needs either:
- B.Cu microvia (current via-class set is through+blind+stacked F-In2)
- Placement micro-relief (move R76 closer to J19.8 or open corridor)
- Negotiated congestion (downgrade R76 net priority during routing)

## Strip+restart is NOT the path forward
- It loses the 25/30 hard-won state.
- The 3 originally-stuck nets (GLB, KILL_RAIL_N, PWM_INLA) reproduce.
- New nets join the residual set (BEMF_C, CSA_B/MAX, GHB/C, GLC, OTP_TRIP_N, PWM_INHC, PWM_INLB).

## Decision per master 10h mandate (NEVER accept 27/30)
Canonical preserved at `085dee9` (25/30 + T+U+V architecture).
Software-side levers PROVEN exhausted. Next options require master:
1. **AA negotiated congestion** — softens priority for 3 chronic nets
2. **B.Cu microvia class** — widens via-class set; KILL_RAIL_N J19.8↔R76.1 might escape via B.Cu
3. **Placement micro-relief** — R23+R19 cascade risk, but targeted to R76 only might be acceptable
4. **J19 pin micro-relief** — R19 + CH2/3/4 mirror cascade (high cost)

Recommend AA first (lowest cost, no placement change), then B.Cu microvia class.
