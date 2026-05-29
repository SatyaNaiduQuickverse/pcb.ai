# 27/30 with --via-in-pad-allowed ON — K3 multi-mech bounded-budget exhaustion

## Result
- **Full routed:** 27/30 (was 25/30; +2 from K3 multi-mech)
- **K3 successes:** PWM_INLA_CH1, SWDIO_CH1 (via multi-mech chain)
- **K3 failures (aggregate=partial, atomic rollback):** PWM_INHB_CH1, GLB_CH1, KILL_RAIL_N_CH1

## K3 trace verbatim
```
[coop] multi-mech fallback (CH1 30/30 lever K3): attempting 5 unrouted net(s)
  [.] PWM_INHB_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback (per-net)
      pair J18.15->J19.1: chain=[] len_mm=17.13 tracks=5 vias=0
  [+] PWM_INLA_CH1: routed via multi-mech chain
  [.] GLB_CH1: K3 multi-mech aggregate status=partial (0/1 pairs routed) — atomic rollback (per-net)
  [.] KILL_RAIL_N_CH1: K3 multi-mech aggregate status=partial (0/2 pairs routed) — atomic rollback (per-net)
      pair J18.23->TP22.1: chain=['through'] len_mm=8.07 tracks=2 vias=1
  [+] SWDIO_CH1: routed via multi-mech chain
[coop] multi-mech fallback done; remaining unrouted = 3
[targeted-ripup] phase done: 0/3 attempts committed.  (all ROLLBACK — no_conflict)
[leaf-route] no disconnected leaves found (vacuous-PASS)
```

## Why canonical NOT promoted
K3-routed PWM_INLA + SWDIO introduce **9 on-board SHORTS** clustered at
J18 fine-pitch escape (x∈25–34, y∈60–70mm) — the multi-mech chain
overlaps existing copper at the QFN entry pads.

Per discipline ("verify artifact, not tool exit code" R22; "no
softening, report verbatim"), canonical preserved at `085dee9`
(SHORTS=0, 25/30 + clean T architecture); this artifact bundle
ships for master lever (W) dispatch.

## Decision for master (lever W)
3 residuals are **bounded-budget-infeasible** at current K3 settings:
- PWM_INHB_CH1: J18.15→J19.1 → multi-mech returns empty chain (chain=[])
- GLB_CH1: no diagnostic detail in trace (chain not reported)
- KILL_RAIL_N_CH1: J18.23→TP22.1 → chain=['through'] tried but rolled
  back (likely DRC verdict)

Suggested W approach (master domain):
- (a) expand K3 A* budget per net (currently bounded ≤2 attempts/leaf)
- (b) targeted obstacle-move per failing net (which passives block
  J18.15, J18.23, J19.1)
- (c) widen via-class set for K3 (currently {through, blind, stacked})

Plus: **SHORTS forensics needed** for K3 multi-mech overlap rule —
when the planner emits a chain, it should pre-verify pad-region
clearance to existing routed traces (the 9 shorts suggest absent
clearance gate in chain-emit).
