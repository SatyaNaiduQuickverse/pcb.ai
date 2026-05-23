#!/usr/bin/env python3
"""extract — S2+S5 cumulative V_BATT noise"""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "cumulative_data.raw"
data = np.loadtxt(RAW, skiprows=1)
t = data[:,0]; v_bat = data[:,1]
mask = t > 200e-6
pp = float(np.max(v_bat[mask]) - np.min(v_bat[mask]))
print(f"PR-S5 S2+S5 cumulative V_BATT pk-pk: {pp*1000:.1f} mV (≤500mV)")
print(f"Verdict: {'PASS' if pp <= 0.500 else 'FAIL'}")
sys.exit(0 if pp <= 0.500 else 1)
