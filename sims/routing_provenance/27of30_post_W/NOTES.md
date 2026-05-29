# Post-W canonical re-run — context-divergence detected

## Config
- master HEAD: `aa0783c` (W merged: courtyard vs bbox fix + K3 cap 200k→500k + chain depth 3→4)
- canonical: `085dee9` (T+U+V architecture, SHORTS=0, 25/30 routed)
- coop flags: `--multi-mech-fallback --via-in-pad-allowed --enable-targeted-ripup --enable-leaf-route`
- pre_route MD5: `f119ac7e8a42a78f06e1acd553cb60fb`

## Result: 27/30 (unchanged from pre-W in count, **different residual set**)
| Net | Pre-W K3 result | Post-W K3 result |
|---|---|---|
| PWM_INHB_CH1 | aggregate=partial chain=[] (J18.15→J19.1) | **✓ routed via multi-mech chain** (J18.19→J19.23) |
| PWM_INLA_CH1 | ✓ routed via multi-mech chain | **aggregate=partial** |
| GLB_CH1     | aggregate=partial (no chain) | aggregate=partial |
| KILL_RAIL_N_CH1 | aggregate=partial chain=['through'] (J18.23→TP22.1 1via/2tr) | aggregate=partial chain=['through','through'] (J18.23→TP22.1 2via/5tr) |
| SWDIO_CH1   | ✓ routed via multi-mech chain | ✓ routed via multi-mech chain |

## Verbatim K3 trace
```
[coop] multi-mech fallback (CH1 30/30 lever K3): attempting 5 unrouted net(s)
      pair J18.19->J19.23: chain=[] len_mm=14.07 tracks=5 vias=0
  [+] PWM_INHB_CH1: routed via multi-mech chain
  [.] PWM_INLA_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback (per-net)
  [.] GLB_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback (per-net)
  [.] KILL_RAIL_N_CH1: K3 multi-mech aggregate status=partial (0/2 pairs routed) — atomic rollback (per-net)
      pair J18.23->TP22.1: chain=['through', 'through'] len_mm=8.95 tracks=5 vias=2
  [+] SWDIO_CH1: routed via multi-mech chain
[coop] multi-mech fallback done; remaining unrouted = 3
[targeted-ripup] phase done: 0/3 attempts committed.  (all ROLLBACK — no_conflict)
[leaf-route] no disconnected leaves found (vacuous-PASS)
Result: full=2/5 partial=0 unrouted=3
```

## Context-divergence signal
- W standalone planner test: 5/5 multi-mech rescue PASS (per PR #254)
- W on canonical (this run): 2/5 (PWM_INHB +SWDIO route; PWM_INLA + GLB + KILL_RAIL_N fail)
- W's chain-depth bump 3→4 actually visible on KILL_RAIL_N (chain went 1→2 vias) — depth budget IS being used, but DRC still rejects.
- Net swap (PWM_INHB now routes, PWM_INLA newly fails) suggests **occupancy-dependent solvability**: the route order matters, and adding PWM_INHB consumes resources that PWM_INLA needed.

## Decision points for master (post-W escalation per 10h mandate)
1. **Standalone vs canonical divergence**: standalone test board lacks the **24 other already-routed nets** — those add occupancy/clearance pressure that K3 can't navigate on canonical even with W's larger budget. Standalone tests don't reproduce the **plateau-state context**.
2. **Net swap evidence (PWM_INHB ↔ PWM_INLA)** suggests **route order / iterative re-solve** would help: route PWM_INHB *and* PWM_INLA together with a joint planner, not greedy one-at-a-time atomic rollback.
3. **KILL_RAIL_N chain growth ['through']→['through','through']** without success suggests **the obstacle is geometric, not a search-budget issue** — the J18.23→TP22.1 corridor doesn't have a 2-via solution at current placement.

## Recommended escalation per master playbook
- (1) Joint K3 — solve PWM_INHB + PWM_INLA together (joint multi-mech, not sequential), OR
- (2) Move-the-obstacle for KILL_RAIL_N J19.8→R76.1 (the chronic 2-island MST split), GLB, PWM_INLA, OR
- (3) Add B.Cu microvia class (stack F→B end-to-end) for the 3 chronic residuals, OR
- (4) J19 pin micro-relief — re-place J19 by 1-2mm to widen corridor, OR
- (5) Accept-with-tradeoffs at 27/30 + document the 3 geometric-infeasible nets as Phase 4 carry-over.

Standing by per 10h autonomous mandate — push back to me.
