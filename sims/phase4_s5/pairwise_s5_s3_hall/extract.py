#!/usr/bin/env python3
"""extract — S5→Hall crosstalk"""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "hall_noise_data.raw"
data = np.loadtxt(RAW, skiprows=1)
t = data[:,0]; v_hall = data[:,3]
mask = t > 1e-3
pp = float(np.max(v_hall[mask]) - np.min(v_hall[mask]))
print(f"PR-S5→S3 Hall: V_HALL_DIV pk-pk = {pp*1000:.3f} mV (≤10mV)")
print(f"Verdict: {'PASS' if pp <= 0.010 else 'FAIL'}")
sys.exit(0 if pp <= 0.010 else 1)
