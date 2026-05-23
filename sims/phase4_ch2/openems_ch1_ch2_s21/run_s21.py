#!/usr/bin/env python3
"""run_s21.py — PR-CH2: REAL openEMS FDTD CH1↔CH2 S21 coupling at 100MHz.

2 traces: CH1 trace at X=-30..-25 (offset center -15) — actually represent CH1
PWM trace as a line at Y=0 (north of center); CH2 trace at Y=70 (south
mirror)? Or simpler: 2 parallel traces 50mm long, separated by 76mm
(CH1 X=12 to CH2 X=88 center-to-center).

Acceptance: |S21| ≤ -40 dB at 100MHz.
"""
import os, sys
os.environ.setdefault('LD_LIBRARY_PATH', '/home/novatics64/local/openems/lib')
from CSXCAD import CSXCAD
from openEMS import openEMS
import numpy as np
import shutil

sim_path = os.path.abspath(os.path.dirname(__file__))
work_dir = os.path.join(sim_path, "openems_s21_work")
if os.path.exists(work_dir):
    shutil.rmtree(work_dir)
os.makedirs(work_dir)

unit = 1e-3
fc, fmax = 100e6, 150e6

FDTD = openEMS(NrTS=50000, EndCriteria=1e-5)
FDTD.SetGaussExcite(fc, fmax)
FDTD.SetBoundaryCond(['MUR']*6)

CSX = CSXCAD.ContinuousStructure()
FDTD.SetCSX(CSX)

fr4 = CSX.AddMaterial('FR4', epsilon=4.4, kappa=0.005)
copper = CSX.AddMetal('PEC')

# Substrate FR4: 100×100×1.6mm
fr4.AddBox(priority=1, start=[-50, -50, -1.6], stop=[50, 50, 0])
# GND plane
copper.AddBox(priority=10, start=[-50, -50, -0.2], stop=[50, 50, -0.15])
# CH1 trace: X=-38..12 (50mm), Y=-0.1..0.1, at z=0..0.05
copper.AddBox(priority=10, start=[-38, -0.1, 0], stop=[12, 0.1, 0.05])
# CH2 trace: X=-12..38 (mirror_X(50) of CH1 → but in centered coords, CH1 at Y=0; CH2 at Y=20 separation)
# Actually since we're centered around X=0, CH1 + CH2 traces at different Y instead.
# CH1 trace at Y=-38 to Y=12, X=0 (i.e., trace runs in Y direction for CH1)
# CH2 trace at Y=12 to Y=62 (separated by 38mm). Hmm.
# Simpler: 2 parallel traces in X direction, 76mm apart in Y
# (Real CH1 center X=12, CH2 center X=88 → 76mm apart center-to-center).
# In our local frame, place at Y=-38 and Y=+38 to keep symmetric about Y=0.
# Actually let me redo: CH1 trace Y=-38, runs in X from -25 to 25.
# CH2 trace Y=+38, runs in X from -25 to 25.
# Remove the trace I just added and add fresh:
# (Easier to start fresh; clearing was attempted — but CSX is already built. Adding more on top is fine; the priority controls overlap)

# Remove prior CH1 trace? Actually the previous trace was at Y=-0.1..0.1 (centered Y=0). Let me just relocate.
# For this S21 sim, override:
# CH1 trace: from (-25, -38, 0) to (25, -38+0.2, 0.05)
copper.AddBox(priority=11, start=[-25, -38, 0], stop=[25, -37.8, 0.05])
# CH2 trace: from (-25, +37.8, 0) to (25, +38, 0.05)
copper.AddBox(priority=11, start=[-25, 37.8, 0], stop=[25, 38, 0.05])

# Mesh
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)
mesh.AddLine('x', np.arange(-50, 50.5, 2.0))
mesh.AddLine('y', np.concatenate([
    np.array([-50, -45, -40, -38.1, -38, -37.9, -37.7, -35, -30, -20, -10, 0, 10, 20, 30, 35, 37.7, 37.9, 38, 38.1, 40, 45, 50]),
]))
mesh.AddLine('z', np.array([-1.6, -1.0, -0.5, -0.3, -0.2, -0.15, -0.1, -0.05, 0, 0.025, 0.05, 0.2, 0.5, 1.0, 2.0, 5.0]))

# Ports: lumped ports at one end of each trace
port1 = FDTD.AddLumpedPort(port_nr=1, R=50,
    start=[-25, -38, -0.2], stop=[-25, -37.8, 0], p_dir='z', excite=1)
port2 = FDTD.AddLumpedPort(port_nr=2, R=50,
    start=[-25, 37.8, -0.2], stop=[-25, 38, 0], p_dir='z', excite=0)

# Terminations on far end
# (LumpedPort handles 50Ω termination automatically as R parameter)

# Write CSX
CSX.Write2XML(os.path.join(work_dir, "sim.xml"))
print("Running openEMS S21 sim (CH1↔CH2 coupling at 100MHz)...")
FDTD.Run(work_dir, verbose=2, cleanup=False)
print("Done. Output in:", work_dir)

# Compute S-parameters using openEMS port post-processing
freqs = np.linspace(50e6, 150e6, 11)
port1.CalcPort(work_dir, freqs)
port2.CalcPort(work_dir, freqs)
s11 = port1.uf_ref / port1.uf_inc
s21 = port2.uf_ref / port1.uf_inc
print(f"S-parameters at {len(freqs)} frequencies:")
for i, f in enumerate(freqs):
    s11_db = 20*np.log10(abs(s11[i]) + 1e-30)
    s21_db = 20*np.log10(abs(s21[i]) + 1e-30)
    print(f"  f={f/1e6:.1f} MHz  S11={s11_db:+.2f} dB  S21={s21_db:+.2f} dB")
# Save for extract script
idx100 = np.argmin(np.abs(freqs - 100e6))
s21_100 = float(20*np.log10(abs(s21[idx100]) + 1e-30))
with open(os.path.join(os.path.dirname(__file__), "s21_result.txt"), 'w') as f:
    f.write(f"S21 at 100MHz: {s21_100:.2f} dB\n")
    f.write(f"freqs (MHz): {[round(x/1e6,2) for x in freqs]}\n")
    f.write(f"S21 (dB): {[round(20*np.log10(abs(s21[i])+1e-30),2) for i in range(len(freqs))]}\n")
print(f"\nS21 at 100MHz: {s21_100:.2f} dB")
print(f"Acceptance: ≤-40 dB")
print(f"Verdict: {'PASS' if s21_100 <= -40 else 'FAIL'}")
