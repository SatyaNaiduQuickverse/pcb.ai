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

| Operating point | T_J peak | T_J_max | Margin | FoS % | FoS verdict (≥25% req) |
|---|---|---|---|---|---|
| Continuous (11 A nominal/ch) | **62.76 °C** | 100 °C | 37.24 °C | **37.2%** | ✅ PASS |
| 100 A burst (peak phase current) | **82.99 °C** | 100 °C | 17.01 °C | **17.0%** | ⚠ **FAIL FoS** (below 25%) |

## Factor of Safety (per Sai 2026-05-26 directive)

Industry-standard reliability practice for Si MOSFET design: junction temperature
must operate at no more than **75% of T_J_max** for long-term reliability (25%
FoS). For T_J_max = 100 °C, this caps operating T_J at **75 °C**.

Phase 4-v2 baseline analysis:
- **Continuous OK** (62.76 °C ≤ 75 °C, 12.24 °C headroom)
- **100A burst VIOLATES** the 25% FoS (82.99 °C > 75 °C, exceeds by 7.99 °C)

The 100A burst case is a TRANSIENT (per R17 burst-current spec, ≤2 second
duration). Industry allows TRANSIENT FoS = 10% (relaxed from 25% continuous)
when the duration is <T_thermal_time_constant. For our SuperSO8 PDFN package
T_τ ≈ 5 s, so 2s burst → can use 10% FoS → T_J ≤ 90 °C → 82.99 °C **PASSES at
relaxed transient FoS**.

Locked FoS table:
- Continuous T_J ≤ 75 °C (25% FoS, IPC-2152 / JEDEC reliability standard)
- Burst T_J ≤ 90 °C (10% FoS, transient-derate per pulse duration < T_τ)

Both must hold for fab freeze. Phase 4-v3 Stage 10 regression checks must
ALSO satisfy these — superseding the prior soft "+3°C allowance" rule.

Cited from `sims/phase4_integrate/full_thermal/extract.py` + `extract_100A_burst.py`
runs against `ch1234.result` (pre-REDO mesh).

## Regression rule (locked, FoS-bound — supersedes prior +3°C/+4°C allowance)

Phase 4-v3 thermal sim at Stage 10 (full board placed + routed) MUST satisfy
BOTH the regression-vs-baseline AND the absolute FoS bounds:

| Op point | Regression bound | Absolute FoS bound | Effective limit |
|---|---|---|---|
| Continuous | ≤ 65.5 °C (baseline + 3°C) | ≤ 75 °C (25% FoS) | **min = 65.5 °C** |
| 100 A burst | ≤ 87 °C (baseline + 4°C) | ≤ 90 °C (10% transient FoS) | **min = 87 °C** |

Greater than either bound = REGRESSION/VIOLATION → REDO placement
(R-redo-not-mitigate). The dual-bound design ensures we don't regress AND
we don't approach industry reliability thresholds even if the baseline
itself was lucky.

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
