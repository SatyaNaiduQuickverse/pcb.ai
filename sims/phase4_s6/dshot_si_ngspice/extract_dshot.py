#!/usr/bin/env python3
"""extract_dshot.py — DShot SI metrics."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "dshot_data.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; v_rx = data[:, 1]
mask = (t >= 100e-9) & (t <= 800e-9)
v_window = v_rx[mask]
t_window = t[mask]
v_max = float(np.max(v_window))
v_min_after_peak = float(np.min(v_window[len(v_window)//2:]))
overshoot = (v_max - 3.3) / 3.3 * 100
# Rise time 10%-90%
up_10 = np.where(v_rx >= 0.33)[0]
up_90 = np.where(v_rx >= 2.97)[0]
t_rise = float(t[up_90[0]] - t[up_10[0]]) if (len(up_10) and len(up_90)) else float('nan')
print(f"PR-S6 DShot600 SI metrics:")
print(f"  V_peak: {v_max:.3f} V (V_OH=3.3V)")
print(f"  Overshoot: {overshoot:+.2f}% (acceptance ≤5%)")
print(f"  Rise time 10-90%: {t_rise*1e9:.1f} ns (acceptance ≤200ns)")
ok = overshoot <= 5 and t_rise <= 200e-9
print(f"  OVERALL: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
