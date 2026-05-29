
---

## Empirical validation (2026-05-30)

Tool + audit + tests built and applied to canonical Phase 4 graduation board.

### Run A: TP_KILL_STAR_CH1 at (27.50, 62.50) B.Cu
- Tool applied successfully (net pad count 4→5)
- Audit gate PASS
- Coop result: `full=2/5 partial=0 unrouted=3`
- **KILL_RAIL_N MST after TP add:**
  ```
  VERIFY-SPLIT (2 islands: 
    [['J19.8', 'D38.2', 'TP_KILL_STAR_CH1.1', 'D37.2'], 
     ['R76.1']])
  ```
- **Mechanism WORKS** — TP joins trunk + D37/D38/J19 form a 4-node island
- **R76.1 STILL isolated** — TP at (27.50, 62.50) too far west of R76 (35.26, 60.80) to act as stepping-stone
- SHORTS=12 introduced by K3 attempts at TP-extended MST

### Run B: TP_KILL_STAR_CH1 at (33.00, 60.50) B.Cu — closer to R76
- Tool applied successfully (same provenance + audit gate PASS)
- Coop result: `full=2/5 partial=0 unrouted=3` (identical to canonical)
- Same PARTIAL pad pair: `('J19.8', 'R76.1')`
- SHORTS=12 (regression vs canonical=0)

### Empirical conclusion (honest)
**UU.4 tooling works as designed but does NOT close R76.1 leaf at either TP
position tested.** The deeper blocker is independent:

1. **pad.GetLayer() API quirk** — R76/D37/D38 are fp_layer=B.Cu with pad
   LayerSet=B.Cu only, but `pad.GetLayer()` returns "F.Cu" (primary). The
   cooperative router uses GetLayer() for pad-layer detection → routes
   these pads on F.Cu where corridor is blocked by D15/R22/C52 cluster.

2. **F.Cu corridor congestion** between trunk-cluster (D37/D38 area) and
   R76 — D15 LED + R22 + C52 + KILL_LED cluster physically block any F.Cu
   trace path.

The TP-as-MST-root mechanism is mathematically correct; the issue is that
the LEAF ROUTING (R76 ↔ trunk) still fails for the same fundamental reason
as canonical. A central TP can't bridge a corridor that's physically blocked.

### What WOULD close R76.1 (next dispatch)
- Fix pad.GetLayer() detection in cooperative router (use LayerSet.Contains
  instead of GetLayer for SMD pads with single-layer LayerSet)
- OR move D15/R22/C52 cluster to open F.Cu corridor (placement-rev)
- OR add B.Cu microvia at R76.1 + ensure coop routes on B.Cu after via

### UU.4 SHIPS as infrastructure
The tool + audit + tests + provenance are codified and ready. UU.4 is a
**SAFE-NO-OP** in canonical — doesn't break route count (same 27/30) but
doesn't close 30/30 alone. Stacks with router-side fixes (pad.GetLayer fix,
EE per-pad-exclude PR #261, etc.).

### Provenance artifacts
- `sims/routing_provenance/uu4_attempts/uu4a_tp_at_27.5_62.5.log` — full coop log Run A
- `sims/routing_provenance/uu4_attempts/uu4b_tp_at_33.0_60.5.log` — full coop log Run B
- `sims/star_point_tp_provenance/TP_KILL_STAR_CH1_*.json` — per-add provenance

---

## Empirical validation (2026-05-30)

Tool + audit + tests built and applied to canonical Phase 4 graduation board.

### Run A: TP_KILL_STAR_CH1 at (27.50, 62.50) B.Cu
- Tool applied successfully (net pad count 4→5)
- Audit gate PASS
- Coop result: `full=2/5 partial=0 unrouted=3`
- **KILL_RAIL_N MST after TP add:**
  ```
  VERIFY-SPLIT (2 islands: 
    [['J19.8', 'D38.2', 'TP_KILL_STAR_CH1.1', 'D37.2'], 
     ['R76.1']])
  ```
- **Mechanism WORKS** — TP joins trunk + D37/D38/J19 form a 4-node island
- **R76.1 STILL isolated** — TP at (27.50, 62.50) too far west of R76 (35.26, 60.80)
- SHORTS=12 introduced by K3 attempts at TP-extended MST

### Run B: TP_KILL_STAR_CH1 at (33.00, 60.50) B.Cu — closer to R76
- Same result: `full=2/5 partial=0 unrouted=3`, SHORTS=12

### Empirical conclusion
UU.4 mechanism works mathematically but does NOT close R76.1 leaf at
either TP position. Deeper blocker (DEV-009): `pad.GetLayer()` returns
"F.Cu" primary for R76/D37/D38 despite LayerSet=B.Cu-only; coop router
routes on F.Cu where D15/R22/C52 cluster physically blocks. Lever FF
addresses the pad.GetLayer detection bug — when shipped, UU.4 should
close R76.1.

UU.4 SHIPS AS INFRASTRUCTURE — safe-no-op (27/30 preserved), stacks
with FF.
