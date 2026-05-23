import numpy as np, sys
from pathlib import Path
data = np.loadtxt(Path(__file__).parent / "full_board_data.raw", skiprows=1)
t = data[:,0]; v_bus = data[:,1]; v_ina = data[:,2]; v_hall = data[:,3]
mask = t > 2e-3
v_bus_min = float(np.min(v_bus[mask]))
v_ina_avg = float(np.mean(v_ina[mask]))
v_hall_pp = float(np.max(v_hall[mask]) - np.min(v_hall[mask]))
print(f"PR-A4-integrate full-board ngspice (4ch + supervisor + BEC + 200A DC):")
print(f"  V_BUS min: {v_bus_min:.2f} V (>12V acceptance)")
print(f"  V_INA avg: {v_ina_avg:.3f} V (trip 1.65V; {(1.65-v_ina_avg)*1000:.0f}mV margin)")
print(f"  V_HALL pk-pk: {v_hall_pp*1000:.3f} mV (<10mV)")
ok = v_bus_min > 12 and v_ina_avg < 1.65 and v_hall_pp < 0.010
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
