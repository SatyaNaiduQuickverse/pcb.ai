# Phase 4-v2 CH1 thermal sim — RESULTS

**Status**: HISTORICAL — Phase 4-v2 sim using analytical proxy (Elmer BC debug pending). Superseded by Phase 4-v3 CH1 sims at `sims/phase4v3/ch1_thermal/` (worker-pending per Sai 2026-05-26 flow lock STEP 3).

## What was run

Analytical model implemented in `extract_per_fet.py`:
- T_J = T_substrate + P_FET × R_θJC
- R_θJC = 1 K/W (BSC014N06NS PDFN-8 datasheet)
- P_FET = 5W at 100A burst
- Heatsink scenario: h_top = 1000 W/m²K, h_bot = 5 W/m²K, A = 35×32mm

## Reproducibility — literal exec command

```bash
python3 extract_per_fet.py > per_fet_table.txt
```

Optional Elmer FEM (post BC debug, not yet executed):
```bash
ElmerSolver ch1.sif
ElmerSolver ch1_v1.sif
```

## Result file

- `per_fet_table.txt` — analytical T_J per FET at 100A burst (heatsink + no-heatsink scenarios)
- `ch1_global.dat`, `ch1_v1.dat` — Elmer global variables (placeholder; full mesh solve TBD)
- `ch1_mesh/`, `ch1_v1mesh/` — Elmer mesh directories (generated, not yet solved)

## Verdict

T_J analytical estimate ≤ 60°C with heatsink, ≤ 110°C without. Within spec (T_J_max = 175°C per datasheet, derated to 150°C).

**This sim does NOT satisfy Phase 4-v3 STEP 3 sim requirement** — Phase 4-v3 CH1 needs fresh Elmer FEM thermal (worker-dispatched 2026-05-26 per PR #153 + #154).
