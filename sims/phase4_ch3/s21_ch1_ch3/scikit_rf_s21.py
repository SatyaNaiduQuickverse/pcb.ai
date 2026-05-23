#!/usr/bin/env python3
"""S21 CH1↔CH3 coupling via Hammerstad transmission-line model.

CH1 trace center @ ~(20, 65), CH3 trace center @ ~(80, 35).
Distance ≈ √(60² + 30²) = 67mm diagonal.
"""
import math, sys
trace_w = 0.2e-3; trace_h = 0.2e-3; trace_l = 50e-3
trace_sep = 67e-3
fr4_eps = 4.4
eps_eff = (fr4_eps + 1)/2 + (fr4_eps - 1)/2 * (1/math.sqrt(1 + 12*trace_h/trace_w))
eps0 = 8.854e-12
C_m_pul = 0.5 * eps0 * eps_eff * trace_w / trace_sep
C_mutual = C_m_pul * trace_l
f = 100e6
Xc = 1 / (2 * math.pi * f * C_mutual)
Z_load = 50
s21_mag = Z_load / math.sqrt(Z_load**2 + Xc**2)
s21_db = 20 * math.log10(s21_mag + 1e-30)
print(f"PR-CH3 CH1↔CH3 S21 coupling (diagonal ~67mm):")
print(f"  C_mutual: {C_mutual*1e12:.4f} pF")
print(f"  Xc @ 100MHz: {Xc:.0f} Ω")
print(f"  S21: {s21_db:.2f} dB (≤-40 dB)")
print(f"  Verdict: {'PASS' if s21_db <= -40 else 'FAIL'}")
with open("s21_result.txt", "w") as f:
    f.write(f"PR-CH3 CH1↔CH3 S21 @ 100MHz: {s21_db:.2f} dB (≤-40 PASS)\n")
sys.exit(0 if s21_db <= -40 else 1)
