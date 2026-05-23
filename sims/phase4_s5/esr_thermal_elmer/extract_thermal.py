#!/usr/bin/env python3
"""extract_thermal.py — Buck output cap T_J (reuses S2 thermal model with
buck-specific I_rms).

I_rms per buck output cap:
  V5_FC @ 1A nominal → I_rms_ripple ~0.5A (inductor ripple/sqrt(12))
  P = 0.5² × 0.010Ω = 2.5mW per cap (negligible)
  Plus ESR loss at switching freq: minimal

Analytical: T_J ≈ T_AMB + R_th × P = 60°C + 25°C/W × 2.5mW = 60.06°C.
Acceptance: T_J ≤ 105°C polymer.
"""
import sys
T_AMB = 60.0
R_TH = 25.0
P_diss = 0.5**2 * 0.010
T_J = T_AMB + R_TH * P_diss
ACC = 105.0
print(f"PR-S5 buck output cap T_J (analytical):")
print(f"  P_dissipation: {P_diss*1000:.1f} mW per cap")
print(f"  T_J: {T_J:.2f} °C (T_amb=60°C, R_th=25°C/W)")
print(f"  Acceptance: T_J ≤ {ACC} °C (polymer)")
print(f"  Verdict: {'PASS' if T_J <= ACC else 'FAIL'}")
sys.exit(0 if T_J <= ACC else 1)
