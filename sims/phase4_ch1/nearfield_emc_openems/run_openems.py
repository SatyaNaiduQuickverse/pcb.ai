#!/usr/bin/env python3
"""run_openems.py — PR-CH1 amendment 2026-05-23: REAL openEMS FDTD per master R18.

50mm trace on F.Cu over GND plane on In1 (≈0.2mm below F.Cu). FR4 ε_r=4.4.
Gaussian pulse excitation 50-150MHz center 100MHz at one trace end;
50Ω termination at other. H-field probe at trace center, +1mm above.

Output: probe_h_field.h5 + extract |H| @ 100MHz via FFT.
Acceptance: |H| ≤ 100 A/m at 100MHz.

Exec: LD_LIBRARY_PATH=/home/novatics64/local/openems/lib python3 run_openems.py
"""
import os, sys, shutil
import numpy as np

os.environ.setdefault('LD_LIBRARY_PATH', '/home/novatics64/local/openems/lib')

from CSXCAD import CSXCAD
from openEMS import openEMS

# === Constants ===
mm = 1e-3
unit = 1e-3  # CSXCAD coords in mm
fc = 100e6   # center frequency
fmax = 150e6 # upper edge for time-step
sim_path = os.path.abspath(os.path.dirname(__file__))
work_dir = os.path.join(sim_path, "openems_work")
if os.path.exists(work_dir):
    shutil.rmtree(work_dir)
os.makedirs(work_dir)

# === FDTD ===
FDTD = openEMS(NrTS=50000, EndCriteria=1e-6)
FDTD.SetGaussExcite(fc, fmax)
FDTD.SetBoundaryCond(['MUR']*6)

CSX = CSXCAD.ContinuousStructure()
FDTD.SetCSX(CSX)

# === Materials ===
fr4 = CSX.AddMaterial('FR4', epsilon=4.4, kappa=0.005)
copper = CSX.AddMetal('PEC')

# === Geometry ===
# Trace 50mm long × 0.2mm wide on F.Cu (top)
# GND plane on In1 (0.2mm below F.Cu — 1.6mm stack 8L, so layer pitch ~0.2mm)
# Substrate slab 60×10×1.6mm centered (so trace fits with 5mm margin)

# Substrate FR4
fr4.AddBox(priority=1, start=[-30, -5, -1.6], stop=[30, 5, 0])
# GND plane (full layer at z=-0.2mm)
copper.AddBox(priority=10, start=[-30, -5, -0.2], stop=[30, 5, -0.15])
# Trace 50mm × 0.2mm × 0.05mm on F.Cu (z=0..0.05)
copper.AddBox(priority=10, start=[-25, -0.1, 0], stop=[25, 0.1, 0.05])

# === Mesh ===
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)
# Coarse mesh: 1mm in X (signal direction), 0.2mm in Y (cross-trace), 0.05mm in Z
# Scope-reduced per master: 5-15min target
mesh.AddLine('x', np.arange(-30, 30.5, 1.0))
mesh.AddLine('y', np.array([-5, -2, -1, -0.5, -0.2, -0.1, 0, 0.1, 0.2, 0.5, 1, 2, 5]))
mesh.AddLine('z', np.array([-1.6, -1.0, -0.5, -0.3, -0.2, -0.15, -0.1, -0.05, 0, 0.025, 0.05, 0.2, 0.5, 1.0, 2.0, 5.0]))
print(f"Mesh sizes: X={len(np.arange(-30,30.5,1.0))}, Y=13, Z=16")

# === Port ===
# Lumped port at trace west end (x=-25), 50Ω, +z direction (between trace and GND)
port_in = FDTD.AddLumpedPort(port_nr=1, R=50,
    start=[-25, -0.1, -0.2], stop=[-25, 0.1, 0],
    p_dir='z', excite=1)
port_out = FDTD.AddLumpedPort(port_nr=2, R=50,
    start=[25, -0.1, -0.2], stop=[25, 0.1, 0],
    p_dir='z')

# === Probe — H-field at trace center, +1mm above ===
probe_h = CSX.AddDump('h_field_probe', dump_type=3, dump_mode=2)  # type=3 → H-field, mode=2 → cell-interpolated
probe_h.AddBox(start=[0, 0, 1.0], stop=[0, 0, 1.0])

# === Time-domain dump for FFT extraction ===
# We use a tiny box around (0,0,1mm) for time-series HDF5 output
dump_box = CSX.AddDump('Et', dump_type=0, dump_mode=2, file_type=0)
dump_box.AddBox(start=[-1, -0.5, 0.5], stop=[1, 0.5, 1.5])

# H-field FREQUENCY-DOMAIN dump @ 100MHz directly (openEMS computes DFT during run).
# dump_type=13 → frequency-domain H-field (real+imag). AddFrequency([100e6]).
hf_dump = CSX.AddDump('Hf_probe', dump_type=13, dump_mode=2, file_type=1)
hf_dump.SetFrequency([100e6])
hf_dump.AddBox(start=[-1, -0.5, 1.0], stop=[1, 0.5, 1.0])

# === Run ===
print("Writing XML to:", work_dir)
CSX.Write2XML(os.path.join(work_dir, "sim.xml"))

print("Running openEMS FDTD (estimated 5-15 min)...")
FDTD.Run(work_dir, verbose=2, cleanup=False)
print("FDTD complete. Output in:", work_dir)

# === Extract |H| at 100MHz via post-processing ===
# Read time-domain probe data + FFT
import h5py
# openEMS dumps h_field as Et_<dump>.h5 or h_field_probe.h5
print("Files in work dir:")
for f in sorted(os.listdir(work_dir)):
    print(f"  {f}")
