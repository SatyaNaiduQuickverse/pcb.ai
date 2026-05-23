#!/usr/bin/env python3
"""efficiency.py — TPS54560 buck efficiency at typical 0.5A load.

P_OUT = 5V × 0.5A = 2.5W
Losses:
  - Switch FET conduction: I_RMS² × R_DS_on × duty = 0.5² × 0.060 × 0.198 = 3.0mW
  - LS FET conduction (sync): I² × R_DS × (1-duty) = 0.25 × 0.060 × 0.802 = 12.0mW
  - DCR loss: 0.5² × 0.050 = 12.5mW
  - Gate drive: ~30mW
  - Switching loss: 0.5 × V_IN × I × t_sw × f_sw = 0.5 × 25.2 × 0.5 × 30n × 500k = 95mW
  - Quiescent: ~5mA × 25.2 = 126mW
Total losses: ~280mW
η = 2.5 / (2.5 + 0.28) = 90%

Acceptance: η ≥85% at typical 0.5A load.
"""
import sys
V_OUT = 5.0
I_OUT = 0.5
V_IN = 25.2
P_OUT = V_OUT * I_OUT
duty = V_OUT / V_IN
# Loss model
P_hi_cond = I_OUT**2 * 0.060 * duty
P_lo_cond = I_OUT**2 * 0.060 * (1-duty)
P_dcr = I_OUT**2 * 0.050
P_gate = 0.030
P_sw = 0.5 * V_IN * I_OUT * 30e-9 * 500e3
P_q = 5e-3 * V_IN
P_losses = P_hi_cond + P_lo_cond + P_dcr + P_gate + P_sw + P_q
P_IN = P_OUT + P_losses
eta = P_OUT / P_IN * 100
print(f"PR-S5 TPS54560 efficiency at V_OUT=5V, I_OUT=0.5A:")
print(f"  P_OUT: {P_OUT:.3f} W")
print(f"  P_losses: {P_losses*1000:.1f} mW")
print(f"  η: {eta:.1f}%")
print(f"  Acceptance: η ≥ 85%")
print(f"  Verdict: {'PASS' if eta >= 85 else 'FAIL'}")
# Save data
with open("efficiency_data.txt", "w") as f:
    f.write(f"V_OUT={V_OUT} I_OUT={I_OUT} eta={eta:.2f}%\n")
sys.exit(0 if eta >= 85 else 1)
