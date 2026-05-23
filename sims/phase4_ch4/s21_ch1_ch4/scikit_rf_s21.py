#!/usr/bin/env python3
"""S21 ch1_ch4 via Hammerstad model."""
import math, sys
trace_w = 0.2e-3; trace_h = 0.2e-3; trace_l = 50e-3
# Channel separations:
#   CH1↔CH4 (NW↔SW): 36mm Y separation
#   CH2↔CH4 (NE↔SW): 67mm diagonal
#   CH3↔CH4 (SE↔SW): 76mm X separation
sep_map = {"ch1_ch4": 36e-3, "ch2_ch4": 67e-3, "ch3_ch4": 76e-3}
trace_sep = sep_map["ch1_ch4"]
fr4_eps = 4.4
eps_eff = (fr4_eps+1)/2 + (fr4_eps-1)/2 * (1/math.sqrt(1+12*trace_h/trace_w))
eps0 = 8.854e-12
C_m = 0.5 * eps0 * eps_eff * trace_w / trace_sep * trace_l
f = 100e6
Xc = 1 / (2*math.pi*f*C_m)
s21_mag = 50 / math.sqrt(50**2 + Xc**2)
s21_db = 20*math.log10(s21_mag+1e-30)
print(f"PR-CH4 ch1_ch4 S21 (sep={trace_sep*1000:.0f}mm): {s21_db:.2f} dB (≤-40)")
print(f"Verdict: {'PASS' if s21_db <= -40 else 'FAIL'}")
with open("s21_result.txt", "w") as fh: fh.write(f"ch1_ch4 S21 @ 100MHz: {s21_db:.2f} dB\n")
sys.exit(0 if s21_db <= -40 else 1)
