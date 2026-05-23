#!/usr/bin/env python3
"""extract — gate ringing"""
import numpy as np, sys
from pathlib import Path
data = np.loadtxt(Path(__file__).parent / "gate_ringing_data.raw", skiprows=1)
v_gs = data[:, 2]
v_max = float(np.max(v_gs))
overshoot = (v_max - 12.0) / 12.0 * 100
print(f"PR-CH1 gate ringing: V_GS peak {v_max:.3f}V, overshoot {overshoot:.2f}% (≤5%)")
print(f"Verdict: {'PASS' if overshoot <= 5 else 'FAIL'}")
sys.exit(0 if overshoot <= 5 else 1)
