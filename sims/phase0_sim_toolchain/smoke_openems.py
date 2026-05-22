"""Phase 0 openEMS smoke test — short dipole radiator.

Verifies openEMS + CSXCAD Python bindings work end-to-end. Builds a simple
half-wave dipole at 1 GHz, runs a few timesteps, asserts no errors.
"""
import sys
import os
import tempfile

# openEMS lib path
os.environ['LD_LIBRARY_PATH'] = '/home/novatics64/local/openems/lib:' + os.environ.get('LD_LIBRARY_PATH', '')

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS.openEMS import openEMS

print('openEMS smoke test — half-wave dipole at 1 GHz')

# Setup grid in mm
unit = 1e-3
f0 = 1e9
wavelength_mm = 300.0
dipole_length_mm = wavelength_mm / 2.0

FDTD = openEMS(NrTS=2000, EndCriteria=1e-4)
FDTD.SetGaussExcite(f0, f0 / 2)
FDTD.SetBoundaryCond(['MUR'] * 6)

CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)

# Simulation domain
domain_mm = wavelength_mm * 1.5
mesh.AddLine('x', np.linspace(-domain_mm / 2, domain_mm / 2, 30))
mesh.AddLine('y', np.linspace(-domain_mm / 2, domain_mm / 2, 30))
mesh.AddLine('z', np.linspace(-domain_mm / 2, domain_mm / 2, 30))

# Dipole on z-axis
dipole = CSX.AddMetal('dipole')
start = [0, 0, -dipole_length_mm / 2]
stop = [0, 0,  dipole_length_mm / 2]
dipole.AddBox(start, stop, priority=10)

# Lumped port at center, z-aligned
gap = 2.0
port_start = [0, 0, -gap / 2]
port_stop  = [0, 0,  gap / 2]
port = FDTD.AddLumpedPort(1, 50, port_start, port_stop, 'z', 1.0, priority=20)

with tempfile.TemporaryDirectory() as tmpdir:
    FDTD.Run(tmpdir, verbose=0, debug_pec=False)
    print('Run completed without exception.')

print('openEMS smoke PASS')
