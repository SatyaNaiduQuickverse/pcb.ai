# Thermal Baseline — Phase 4-v2 (pre-REDO) regression checkpoint

Per R32 (sureshot > SOTA) + R-redo-not-mitigate: when we REDO placement
in Phase 4-v3 (park-then-bring-in), we must verify the thermal envelope
does not regress vs the pre-REDO baseline. This doc captures the
authoritative pre-REDO Elmer FEM thermal numbers so they are not lost in
/tmp result files that may be overwritten by future runs.

## Pre-REDO baseline (Phase 4-v2 PR-A4-integrate, frozen 2026-05-24)

Source: `sims/phase4_integrate/full_thermal/ch1234_mesh/ch1234.result`
Sim: Elmer FEM, 4-channel symmetric placement with all 24 FETs active,
post-A4-integrate (CH4 = mirror_X(CH3) of CH3 = mirror_Y(CH2) of CH2
= mirror_X(CH1)).

| Operating point | T_J peak | T_J_max | Margin | Verdict |
|---|---|---|---|---|
| Continuous (11 A nominal/ch) | **62.76 °C** | 100 °C | 37.24 °C | ✅ PASS |
| 100 A burst (peak phase current) | **82.99 °C** | 100 °C | 17.01 °C | ✅ PASS |

Cited from `sims/phase4_integrate/full_thermal/extract.py` + `extract_100A_burst.py`
runs against `ch1234.result` (pre-REDO mesh).

## Regression rule (locked)

Phase 4-v3 thermal sim at Stage 10 (full board placed + routed) MUST satisfy:

- Continuous T_J ≤ 65.5 °C (≤ pre-REDO + 3 °C allowance)
- 100 A burst T_J ≤ 87 °C (≤ pre-REDO + 4 °C allowance)

The allowance covers small placement deltas + improved decoupling layout.
Greater than allowance = REGRESSION → REDO placement again (R-redo-not-mitigate).

## Why this matters

Phase 4-v3 reset destroyed the live Phase 4-v2 board state (park_all_components
moved 539 fps off-board at Stage 0 merge 2026-05-26). The original `.kicad_pcb`
that produced these numbers is preserved in git history at commit `428bc3d`.
The result file `ch1234.result` (built from that .kicad_pcb's exported geometry)
is preserved in-tree as a regression-detection asset.

If we lose either, the baseline cannot be regenerated without rebuilding
Phase 4-v2 placement — which we deliberately scrapped. Don't delete either.

## Status of related tasks

- **Task #43 Phase 4-via-stitching-audit**: closed pre-REDO, separate audit
- **Task #84 Allegro ACS770 STEP**: ALREADY DONE — board uses
  `Sensor_Current.3dshapes/Allegro_CB_PFF.step` (KiCad-shipped), not SOIC-8
  placeholder. Task description was stale from an earlier rev.
- **OQ-006 R17 ripple FoS**: still deferred to Stage 9 ngspice (routed plane needed)
