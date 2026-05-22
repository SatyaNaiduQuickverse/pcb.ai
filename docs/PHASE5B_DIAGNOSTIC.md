# Phase 5b — Diagnostic (autoroute deferred to post-Phase-4b-redo3)

Per master adjudication 2026-05-22: Phase 5b autoroute did not converge. F.Cu
signal-density bottleneck confirmed empirically. Phase 4b-redo3 grows board to
100×85 + adds signal-density gate before retry. This PR commits the DSN tooling
and setup_board.py side-fixes; autoroute deferred.

## What was tried

Three Freerouting runs against the Phase-4b-redo2-state placement (90×75 board,
360 footprints, 249 nets, F.Cu utilization ~62%):

1. **2-layer DSN, no planes.** Pass #1 = 78 unrouted / 249 nets = **68.7%** at 6m44s.
   Diagnosis at the time: no power planes — every GND/VMOTOR/5V/9V/3V3 pad routed as trace.
2. **2-layer DSN, planes after `(via)`.** Killed at 25-min wall, Pass #1 not finished.
   Diagnosis: plane order in `(structure)` was wrong (must be before `(via)` per novapcb pattern).
3. **4-layer DSN (F.Cu + In1.Cu + In2.Cu + B.Cu), planes correctly ordered.**
   GND on In1.Cu (full), +VMOTOR + +V3V3 split on In2.Cu, padstacks expanded for through-holes.
   Killed at 14-min, Pass #1 not finished. 1069+ "MazeSearchAlgo: no accessible expansion
   doors found" failures — placement is route-blocking signal nets regardless of plane support.

## Why autoroute is deferred (not just brute-forced further)

Per master's locked thresholds + `feedback-redo-not-mitigate`: <95% post-plane-injection
= genuine placement defect. The repeated "no accessible expansion doors" pattern
points to F.Cu signal-density on the middle band y=24..40 (5 buck columns + LC +
safety stacks) and lower band y=44..56 (~65 BEC supporting passives). Brute-force
retry would burn hours without resolution.

## What this PR commits (infra + diagnostic; no autoroute outcome)

| File | Purpose |
|---|---|
| `hardware/kicad/setup_board.py` | 3 side-fixes for ExportSpecctraDSN — gr_rect Edge.Cuts (was 4 gr_lines), proper mount-hole footprints (uuid/descr/Reference/Value), 2-layer fallback while 4-layer plane discipline matures |
| `hardware/kicad/scripts/export_dsn.py` | NEW — pcbnew Specctra DSN export wrapper |
| `hardware/kicad/scripts/dsn_strip_planes.py` | NEW — playbook T1 plane-stripper (idempotent; pass-through for 2-layer) |
| `hardware/kicad/scripts/dsn_inject_planes.py` | NEW — adds 4-layer pseudo-structure to DSN: In1.Cu/In2.Cu layers + GND/+VMOTOR/+3V3 planes + padstack expansion |
| `hardware/kicad/pcbai_fpv4in1.kicad_pcb` | regenerated via kinet2pcb (2-layer state, demonstrates ExportSpecctraDSN works after side-fixes) |
| `hardware/kicad/pcbai_fpv4in1.dsn` / `_raw.dsn` | reference DSNs (4-layer-injected + raw export) |
| `docs/PHASE5B_DIAGNOSTIC.md` | this document |
| `docs/artifacts/phase5b_autoroute/freerouting.log` | minimal startup log from final attempt |

## Findings worth surfacing (cross-master lesson candidates)

1. **playbook §Routing T1 incomplete recipe**: "Strip planes from DSN structure"
   only works for simple boards. For dense placements with high-pin power nets,
   planes MUST be retained for plane-served exclusion from autoroute. Updated dsn_inject_planes.py adds them via pseudo-inner-layers without disturbing .kicad_pcb's actual layer count.
2. **ExportSpecctraDSN silent-fail modes** found:
   - 4 separate `gr_line` Edge.Cuts (needs `gr_rect` or `gr_poly` instead)
   - Mount-hole footprints without `uuid`/`descr`/Reference/Value
   - Inner power-typed layers (signal-typed inner layers work; power-typed don't)
3. **Plane order in `(structure)` matters**: planes must come BEFORE `(via)` line, not after.

## Deferred to Phase 4b-redo3 (next PR per master adjudication)

- Grow board outline 90×75 → 100×85 mm (+14% area; F.Cu util target ~48%)
- Distribute +25 mm height: 5 mm relief between buck columns and BEC supporting passive zone; 3.5 mm relief in lower band
- Add signal-density gate to `verify_placement.py` (per-zone trace estimate; threshold ≥ 8 traces/mm² for 2-signal-layer denied)
- Phase 4c thermal sim re-check (heatsink zone unchanged; expect equal-or-better margin on larger board)
- Secondary: evaluate In3.Cu promotion to signal-routing layer (3rd signal layer if no impedance/coupling conflicts)
- After 4b-redo3 merge: re-export DSN via this PR's tooling, re-run Freerouting Pass #1, apply verdict per master's locked thresholds

## Rules check

Clean. URGENT mechanism used correctly (3 escalations during Phase 5b — DSN-export tooling, plane-injection adjudication, placement-defect verdict). `feedback-redo-not-mitigate` applied — placement redo planned per master adjudication. R17: tooling fixes + diagnostic captured here; nothing deferred silently.
