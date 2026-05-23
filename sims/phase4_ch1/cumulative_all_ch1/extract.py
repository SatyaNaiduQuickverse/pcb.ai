#!/usr/bin/env python3
"""extract — Cumulative ALL+CH1 board operating validation."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "cumulative_data.raw"
data = np.loadtxt(RAW, skiprows=1)
t = data[:,0]
v_bus = data[:,1]; v_ina = data[:,2]; v_hall = data[:,3]
mask = t > 500e-6
v_bus_pp = float(np.max(v_bus[mask]) - np.min(v_bus[mask]))
v_ina_pp = float(np.max(v_ina[mask]) - np.min(v_ina[mask]))
v_ina_avg = float(np.mean(v_ina[mask]))
v_hall_pp = float(np.max(v_hall[mask]) - np.min(v_hall[mask]))
print(f"PR-CH1 cumulative ALL+CH1 board operating @ 50A DC + 25A AC PWM:")
print(f"  V_BUS pk-pk: {v_bus_pp*1000:.1f} mV (target stable, <1V)")
print(f"  V_INA (supervisor) avg: {v_ina_avg:.3f}V (trip threshold 1.65V; margin {(1.65-v_ina_avg)*1000:.1f} mV)")
print(f"  V_INA pk-pk: {v_ina_pp*1000:.1f} mV (no false-trip if avg+pp/2 < 1.65V)")
print(f"  V_HALL_DIV pk-pk: {v_hall_pp*1000:.3f} mV (target <10mV)")
ok = v_bus_pp < 1.0 and (v_ina_avg + v_ina_pp/2) < 1.65 and v_hall_pp < 0.010
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
