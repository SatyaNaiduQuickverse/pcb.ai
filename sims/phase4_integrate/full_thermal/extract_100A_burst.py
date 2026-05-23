#!/usr/bin/env python3
"""extract_100A_burst.py — Phase 5c thermal-recheck result extractor.

Per master 2026-05-24 dispatch + [[feedback-sim-execution-gate]]:
  Reports T_J max from Elmer SaveScalars output at 100A burst per FET.
  Verifies against design limit (100°C) and master target margin (≥30°C
  to T_J_max=150°C → T_J ≤ 120°C design max).

Source artifact: ch1234_max_100A_burst.dat
Source SIF:       ch1234_thermal_100A_burst.sif (407→31543 W/m³ scale for
                  100A × 1.45mΩ R_DS_on = 14.5W per FET × 24 FETs = 348W board)
Exec command:     ElmerSolver ch1234_thermal_100A_burst.sif
"""
import sys
from pathlib import Path

DAT = Path(__file__).parent / "ch1234_max_100A_burst.dat"
val = float(open(DAT).readlines()[-1].strip())

DESIGN_LIMIT = 100.0      # design target T_J
SURVIVAL_LIMIT = 150.0    # T_J_max from BSC014N06NS datasheet
MARGIN_REQUIRED = 30.0    # master 2026-05-24 directive

margin_to_survival = SURVIVAL_LIMIT - val
margin_to_design = DESIGN_LIMIT - val

print(f"Phase 5c thermal recheck — 100A burst per FET")
print(f"  Sim source: {DAT.name}")
print(f"  Result:     T_J max = {val:.2f}°C")
print(f"  Design limit:    {DESIGN_LIMIT:.0f}°C  → margin = {margin_to_design:+.2f}°C")
print(f"  Survival limit:  {SURVIVAL_LIMIT:.0f}°C  → margin = {margin_to_survival:+.2f}°C")
print(f"  Master required margin (to T_J_max): {MARGIN_REQUIRED:.0f}°C")

ok_design = val <= DESIGN_LIMIT
ok_margin = margin_to_survival >= MARGIN_REQUIRED
verdict = "PASS" if (ok_design and ok_margin) else "FAIL"
print(f"  Acceptance:  T_J ≤ design AND margin ≥ {MARGIN_REQUIRED}°C to T_J_max")
print(f"  Verdict:     {verdict}")
print()
print(f"  Comparison to prior PR-A4-integrate baseline:")
print(f"    Prior (11A continuous):  T_J ≈ 60.30°C")
print(f"    Phase 5c (100A burst):    T_J = {val:.2f}°C")
print(f"    Delta from baseline:      {val - 60.30:+.2f}°C")
sys.exit(0 if (ok_design and ok_margin) else 1)
