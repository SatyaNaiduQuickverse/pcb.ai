#!/usr/bin/env python3
"""extract_ripple.py — V_BUS ripple at C1-C4 terminals."""
import numpy as np
import sys
from pathlib import Path
RAW = Path(__file__).parent / "ripple_data.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; v_bus = data[:, 1]
# Skip startup transient (first 200µs)
mask = t > 200e-6
v_bus_ss = v_bus[mask]
v_pp = float(np.max(v_bus_ss) - np.min(v_bus_ss))
print(f"PR-S2 V_BUS ripple at C1-C4:")
print(f"  V_BUS peak-to-peak (200µs-2ms window): {v_pp:.3f} V")
print(f"  Acceptance: ≤ 1.0 V")
print(f"  Verdict: {'PASS' if v_pp <= 1.0 else 'FAIL'}")
sys.exit(0 if v_pp <= 1.0 else 1)
