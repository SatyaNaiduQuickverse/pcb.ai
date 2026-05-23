# Phase 7-prep mechanical commitments (Sai-locked 2026-05-23)

Locks mechanical-design commitments required by Phase 4 simulations + Phase 6 reliability spec.

## Heatsink coverage — FULL-BACK (Sai pick 2026-05-23)

**Commitment**: B.Cu-side cooling solution provides **full-back coverage ~100×95 mm minimum** with h_bot ≥ 1500 W/m²·K typical.

**Implementation requirements**:
- Thermal interface material (TIM): k ≥ 4 W/m·K, ≤ 0.5 mm thickness
- Heatsink mass + fin geometry adequate to maintain h ≥ 1500 W/m²·K under enclosure airflow (prop-wash + active heatsink if needed)
- Mounted via M3 screws through corner mount holes at (5,5)/(95,5)/(5,90)/(95,90)
- Insulation gap between heatsink and B.Cu pads where required (DRV signals, sense traces)

**Sim dependency**: this assumption used in all Phase 4 thermal sims (CH1 v3 P=12 + full 4-channel v4_v2 + v5). Per-FET T_J results (max 90.42°C burst / 74.91°C cont) ASSUME this h_bot=1500 envelope is achieved by mechanical design.

**If mechanical design cannot achieve h_bot ≥ 1500**: thermal sims must be re-run with realistic BCs; per-FET T_J may exceed spec.

## Other Phase 7-prep items (placeholders)

- Form factor: 100×95 mm board, fits FPV stack constraints (Sai earlier directive)
- Enclosure airflow: prop-wash assumed available (h_top=80 W/m²·K)
- Cable cooling envelope: TBD
- IP rating: TBD per Phase 7-prep

## Reference

- thermal sim methodology + per-FET acceptance: `sims/phase4_place_channel_template/elmer_thermal/`
- 4-channel v5 results: `full4ch_mesh_v2/full4ch_thermal_v5.vtu_t0002.vtu`
- Sim-execution-gate evidence per locked rule [[feedback-sim-execution-gate]]
