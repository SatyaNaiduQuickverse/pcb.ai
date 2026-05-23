#!/usr/bin/env python3
"""extract_inrush.py — extract acceptance metrics from inrush_data.raw.

Reads ngspice wrdata output (text format) and reports peak inrush current +
V_BATT 95% rise time.

Run: python3 extract_inrush.py
"""
import numpy as np
import sys
from pathlib import Path

RAW = Path(__file__).parent / "inrush_data.raw"
if not RAW.exists():
    sys.exit(f"Missing {RAW}")

data = np.loadtxt(RAW, skiprows=1)
# Columns: time, I(V_sense), V(VBUS_S), V(VBUS_C)
t = data[:, 0]
i_sense = data[:, 1]
v_bus_c = data[:, 3]

V_BATT = 25.2
target_95 = 0.95 * V_BATT

ipeak = float(np.max(np.abs(i_sense)))
i_peak_t = float(t[np.argmax(np.abs(i_sense))])

above = np.where(v_bus_c >= target_95)[0]
t_95 = float(t[above[0]]) if len(above) else float('nan')

print(f"PR-S1 inrush acceptance metrics:")
print(f"  Peak inrush current: {ipeak:.2f} A at t={i_peak_t*1000:.3f} ms")
print(f"  V_VBUS_C final: {v_bus_c[-1]:.2f} V (target {V_BATT} V)")
print(f"  t_95% (V_VBUS_C ≥ {target_95:.2f} V): {t_95*1000:.3f} ms")
print()
PASS_PEAK = ipeak <= 200
PASS_RISE = t_95 <= 5e-3
print(f"  Peak ≤ 200A:    {'PASS' if PASS_PEAK else 'FAIL'} ({ipeak:.1f}A)")
print(f"  t_95 ≤ 5ms:     {'PASS' if PASS_RISE else 'FAIL'} ({t_95*1000:.2f}ms)")
print()
print("OVERALL:", "PASS" if PASS_PEAK and PASS_RISE else "FAIL")
sys.exit(0 if (PASS_PEAK and PASS_RISE) else 1)
