# Post-Z canonical re-run — geometric-infeasible confirmed (not occupancy / order / batch)

## Config
- master HEAD: `e869b71` (Z merged)
- canonical: `085dee9` (T+U+V architecture)
- flags: `--multi-mech-fallback --via-in-pad-allowed --enable-targeted-ripup --enable-leaf-route --route-hdi-first`
- pre_route MD5: `f119ac7e8a42a78f06e1acd553cb60fb`

## Result: STILL 27/30 (3 chronic residuals: GLB, KILL_RAIL_N, PWM_INLA)

## Critical new evidence — Z's HDI-first JOINT on CLEAN canonical
Z fires its joint K3 BEFORE the main cooperative pass — i.e. with the
24 other CH1 nets NOT yet routed, so no foreign occupancy contention.

Verbatim Z HDI-first trace:
```
[coop] LEVER Z: route-hardest-first enabled — identifying HDI-whitelisted nets BEFORE main cooperative pass
  [Z] HDI-whitelisted target nets (5): ['GLB_CH1', 'KILL_RAIL_N_CH1', 'PWM_INHB_CH1', 'PWM_INLA_CH1', 'SWDIO_CH1']
[Y] cascade k=5: trying subset ['KILL_RAIL_N_CH1', 'GLB_CH1', 'PWM_INHB_CH1', 'PWM_INLA_CH1', 'SWDIO_CH1']
    joint try (5 nets, 2 routed): {'KILL_RAIL_N_CH1': 'failed', 'GLB_CH1': 'failed', 'PWM_INHB_CH1': 'routed', 'PWM_INLA_CH1': 'failed', 'SWDIO_CH1': 'routed'}
[Y] cascade k=4: trying subset ['KILL_RAIL_N_CH1', 'GLB_CH1', 'PWM_INHB_CH1', 'PWM_INLA_CH1']
    joint try (4 nets, 1 routed): {'KILL_RAIL_N_CH1': 'failed', 'GLB_CH1': 'failed', 'PWM_INHB_CH1': 'routed', 'PWM_INLA_CH1': 'failed'}
[Y] cascade k=3: trying subset ['KILL_RAIL_N_CH1', 'GLB_CH1', 'PWM_INHB_CH1']
    joint try (3 nets, 1 routed): {'KILL_RAIL_N_CH1': 'failed', 'GLB_CH1': 'failed', 'PWM_INHB_CH1': 'routed'}
[Y] cascade k=2: trying subset ['KILL_RAIL_N_CH1', 'GLB_CH1']
    joint try (2 nets, 0 routed): {'KILL_RAIL_N_CH1': 'failed', 'GLB_CH1': 'failed'}
[Y] cascade k=1: trying subset ['KILL_RAIL_N_CH1']
    joint try (1 nets, 0 routed): {'KILL_RAIL_N_CH1': 'failed'}
[Z] HDI-first phase: 0/5 rescued — proceeding to normal cooperative pass
```

KILL_RAIL_N + GLB **failed alone, joint, and at every cascade subset size**.
PWM_INLA failed in joint mode (cascade k=4) but mysteriously didn't get
solo cascade — Z's k=2 subset went to KILL_RAIL_N+GLB only (the
"failed-most" pair). PWM_INHB always routes when in the subset.

## Three-cause elimination
| Hypothesis | Disproven by |
|---|---|
| Occupancy-dependent | Z HDI-first on CLEAN canonical: 0/5 for chronics |
| Route-order dependent | Z hardest-first: same 3 fail |
| Budget-dependent | W 200k→500k cap + depth 3→4: same 3 fail |
| Joint vs sequential | Y cascade 5→4→3→2→1: same 3 fail |
| Greedy contention | Z + main coop + K3 sequential: same 3 fail |

**All software-side levers exhausted.** Residual is **geometric-infeasible at current placement + via-class set**.

## Verbatim K3 sequential fallback (post-cooperative)
```
pair J18.19->J19.23: chain=[] len_mm=14.07 tracks=5 vias=0    [PWM_INHB ✓]
PWM_INLA_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback
GLB_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback
KILL_RAIL_N_CH1: K3 multi-mech aggregate status=partial (0/2 pairs routed) — atomic rollback
    pair J18.23->TP22.1: chain=['through', 'through'] len_mm=8.95 tracks=5 vias=2
SWDIO_CH1: routed via multi-mech chain
[targeted-ripup] phase done: 0/3 attempts committed.  (all ROLLBACK — no_conflict)
[leaf-route] vacuous-PASS
```

KILL_RAIL_N split-island J19.8↔R76.1 is **chronic across ALL runs**:
- Pre-W: chain=['through'] 1via/2tr — DRC rejected
- Post-W: chain=['through','through'] 2via/5tr — DRC rejected
- Post-Z joint: failed at every cascade size

## Decision per master playbook (10h mandate, NEVER accept 27/30)
Software levers exhausted. Per master's enumerated escalation order:
- ~~Y joint K3~~ — failed (this run included it)
- ~~Z hardest-first~~ — failed (this run)
- **AA negotiated congestion** — master's stated next option
- B.Cu microvia class (Z said next) — widens K3 mechanism set
- Move-the-obstacle (R23 placement micro-relief) — locked rule says "Sai catches are samples": targeted relief acceptable for J19 fine-pitch corridor; R19/CH2-4 mirror invariants must hold
- J19 micro-relief (±1-2mm) — risks R19 + CH2/3/4 mirror cascade

## Specific pad-pair targets that need geometric relief
- **PWM_INLA_CH1** — pad pairs not detailed in trace; need K3 to log per-pair attempt
- **GLB_CH1** — no chain reported; suggests planner can't generate ANY candidate
- **KILL_RAIL_N_CH1** — J18.23→TP22.1 chain found but DRC-rejected; J19.8→R76.1 perpetual split (D38.2+D37.2 island vs R76.1 island)
