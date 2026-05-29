# Phase 5 Lever UU.4 — STAR-POINT TP for KILL_RAIL_N (Design Spec)

Per Sai 2026-05-30 directive: UU.4 highest-leverage low-BOM-cost lever solves
KILL_RAIL_N 3-island split structurally.

## The structural problem (Phase 4 empirical)
KILL_RAIL_N_CH1 has 4 nodes:
- J19.8  at (23.45, 64.46) F.Cu primary
- D37.2  at (30.70, 61.20) F.Cu primary (fp B.Cu, pad LayerSet B.Cu)
- D38.2  at (32.20, 57.60) F.Cu primary (fp B.Cu, pad LayerSet B.Cu)
- R76.1  at (35.26, 60.80) F.Cu primary (fp B.Cu, pad LayerSet B.Cu)

Coop's MST construction roots at J19.8 (the HDI-whitelisted pin). Reliable
3-island split observed across all Phase 4 levers:
```
KILL_RAIL_N_CH1: MST-ROUTED but VERIFY-SPLIT (2 islands: 
  [['J19.8', 'D38.2', 'D37.2'], ['R76.1']])
```
R76.1 leaf chronically NO_PATH from the trio's trunk because F.Cu corridor
between trio and R76 is blocked by D15 + R22 + C52 + LED cluster.

## UU.4 STAR-POINT TP solution
**Add ONE test point** at strategic position; net = KILL_RAIL_N_CH1.

### Choosing the TP location
- Centroid of 4 nodes: (30.40, 61.02) — overlaps D15/C52 cluster ❌
- TP_KILL_STAR proposed: **(27.50, 62.50) on B.Cu** — west of diode cluster,
  inside J19-east-escape corridor, B.Cu has space (less foreign traffic).

### MST topology after TP add
- TP_KILL_STAR is a central node connecting to all 4 endpoints via 1 edge each
- 4-edge star (not chain) — no leaf chronically isolated
- Each edge is short: TP↔J19.8 ~4mm; TP↔D37 ~3mm; TP↔D38 ~7mm; TP↔R76 ~8mm
- Router can grow the star incrementally, each edge independent

### Why B.Cu for TP
- All 3 destination pads (D37, D38, R76) already pad-LayerSet B.Cu
- TP on B.Cu allows direct trace on B.Cu to all 3 destinations (no via needed
  for those 3 edges)
- J19.8 edge needs F→B microvia at J19.8 (uses BB whitelist B.Cu microvia
  lever)

### Tool spec — `add_star_point_tp.py`
Inputs:
  - `--board <path>` source .kicad_pcb
  - `--output <path>` dest
  - `--net KILL_RAIL_N_CH1` target net
  - `--ref TP_KILL_STAR` test-point reference
  - `--position 27.50,62.50` mm
  - `--layer B.Cu` (default B.Cu for KILL_RAIL_N TP)
  - `--pad-size 0.6,0.6` mm

Behavior:
  1. Load board
  2. Create minimal FOOTPRINT instance with single PAD
  3. Set PAD net to target net via netcode lookup
  4. Set PAD layer set
  5. Add to board
  6. Provenance JSON with: net, ref, pos, layer, schematic-deviation flag
     (this is a board-only TP add; schematic doesn't have it — DEV-007)
  7. Save

### Audit gate — `audit_star_point_tp_provenance.py` (G_STAR_POINT_TP)
Checks every TP referenced in a star-point provenance JSON:
  1. TP footprint EXISTS on the board (per ref)
  2. TP pad NET matches the provenance net
  3. TP position within 0.1mm of provenance (placement integrity)
  4. Net pad count = original + 1 (TP added one pad)
  5. R21 deviation flag present for any TP not in schematic

### Per-channel R19 cascade plan
KILL_RAIL_N is per-channel. Adding TP_KILL_STAR_CH1 → CH2/3/4 mirror:
- TP_KILL_STAR_CH2 at mirror_X(50)(27.50, 62.50) = (72.50, 62.50)
- TP_KILL_STAR_CH3/4 similarly
- Phase 5 Step C must add these mirrors with R19 enforcement

### R21 DEV-007: schematic-board mismatch
TP added board-only ≠ schematic. Schematic must be updated post-TT to include
TP_KILL_STAR_CHx in KILL_RAIL_N net (KiCad schematic edit). Phase 5 Step E
integration sims must pull from schematic-updated source.

## Reproducibility chain (per Sai NEW G_VALIDATION_CHAIN)
1. Canonical SHA: `step6-ch1-27of30-phase4grad` (085dee9-era)
2. Apply `add_star_point_tp.py --net KILL_RAIL_N_CH1 --ref TP_KILL_STAR_CH1
   --position 27.50,62.50 --layer B.Cu`
3. Run cooperative router with full flag set: `--multi-mech-fallback
   --via-in-pad-allowed --bcu-microvia-allowed --route-hdi-first
   --enable-targeted-ripup --enable-leaf-route`
4. Validate: KILL_RAIL_N MST = 5-node star (TP center + 4 leaves)
5. DRC: SHORTS=0 (R-J5 atomic)
6. Loop-L per-phase sim (KILL_RAIL_N not in motor loop, so loop-L unchanged)
7. G_STAR_POINT_TP audit passes

## Honest status
Worker time-bound this turn — design spec shipped; implementation deferred to
next iteration or master subagent. Per "deliver-not-promise": this PR
documents the design + invites parallel dispatch.

R21 DEV-007 (schematic-board TP mismatch) requires schematic-edit follow-up
(KiCad eeschema not currently in worker scope).
