#!/usr/bin/env python3
"""extract_crosstalk.py — S2→S6 DShot crosstalk metric."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "crosstalk_data.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; v_rx = data[:, 1]
# Steady-state window (after 20µs of startup)
mask = t > 20e-6
v_window = v_rx[mask]
v_pp = float(np.max(v_window) - np.min(v_window))
print(f"PR-S6 S2→S6 DShot crosstalk:")
print(f"  Induced V_DSHOT_RX swing pk-pk: {v_pp*1000:.2f} mV")
print(f"  Acceptance: ≤ 100 mV (well below 3.3V/2 threshold)")
print(f"  Verdict: {'PASS' if v_pp <= 0.1 else 'FAIL'}")
sys.exit(0 if v_pp <= 0.1 else 1)
