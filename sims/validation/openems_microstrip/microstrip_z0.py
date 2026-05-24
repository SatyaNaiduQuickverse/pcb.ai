#!/usr/bin/env python3
"""openEMS microstrip Z0 validation against Hammerstad-Jensen 1980.

Closes the gap flagged in Task 9: scikit-rf was matched only against H-J
closed-form (not against a 2D/3D field solver). openEMS is the 3D FDTD
field solver that will be used for USB SI / EMI / controlled-impedance
sign-off in Phase 6b.

Test case (same as val_skrf_microstrip.py):
  W=0.30mm, h=0.21mm, t=35µm, εr=4.3
  H-J 1980 analytical Z0 = 56.01 Ω

Extraction: long microstrip excited at one end with Gaussian pulse to
2 GHz. Port measurement plane back from feed by length/3 to let
evanescent feed modes decay. Z0(f) extracted from MSLPort.Z_ref which
is computed from E/H probe data at the measurement plane.

KEY MESHING POINT: must resolve the trace width and substrate thickness,
not just the far-field wavelength. λ/30 alone gives 0.96mm cells —
coarser than our 0.30mm trace. Force ≥8 cells across W and ≥5 cells
through h.
"""
import os, tempfile, math
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

# Geometry
unit = 1e-3
MSL_length = 25.0           # port half-length; total line = 2*25 = 50mm
MSL_width  = 1.60
substrate_thickness = 0.80
substrate_epr = 4.3
metal_thickness = 0.035
f_max = 2e9
# Feed and Meas planes must be well separated; otherwise V/I probes around
# Meas see feed transient.
FEED_SHIFT = 2.0            # 2mm from start: feed at x=-23
MEAS_SHIFT = 15.0           # 15mm from start: meas at x=-10  (13mm clean line between)

Sim_Path = os.path.join(tempfile.gettempdir(), 'openems_msl_val')
os.makedirs(Sim_Path, exist_ok=True)
for fn in os.listdir(Sim_Path):
    p = os.path.join(Sim_Path, fn)
    if os.path.isfile(p): os.remove(p)

# FDTD — NrTS bounds the run so we can extract Z0 from the clean incident
# wavefront before reflections from the line ends corrupt the time record.
# At ~50 fs/timestep, 30000 TS = 1.5 ns simulation; wave traverses the line
# (50mm in FR4 ≈ 350 ps) and the reflected energy reaches the meas plane
# only after that, leaving a clean window for FFT-based Z0 extraction.
FDTD = openEMS(NrTS=30000, EndCriteria=1e-4)
FDTD.SetGaussExcite(f_max/2, f_max/2)
FDTD.SetBoundaryCond(['PML_8', 'PML_8', 'MUR', 'MUR', 'PEC', 'MUR'])

CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)

# Mesh strategy:
#   - far-field λ/30 = 2.41mm at 2GHz in FR4 (used in air, away from trace)
#   - across trace width: ≥8 cells -> dy_strip = 0.03mm
#   - through substrate: ≥5 cells -> dz_sub = 0.04mm
#   - along strip: dx = 0.5mm (plenty for measurement; β extraction is averaged)
res_far = C0/(f_max*np.sqrt(substrate_epr))/unit/30
dy_strip = MSL_width/8.0       # 0.0375 mm
dz_sub   = substrate_thickness/5.0  # 0.042 mm
dx       = 0.5

# X mesh — explicit, finer than λ/30 along the strip
mesh.AddLine('x', np.arange(-MSL_length, MSL_length + dx/2, dx))

# Y mesh — fine across the trace, coarse in air
# Fine zone: -W/2 - margin .. +W/2 + margin
y_margin = 1.0
y_fine = np.arange(-MSL_width/2 - y_margin, MSL_width/2 + y_margin + dy_strip/2, dy_strip)
mesh.AddLine('y', y_fine)
mesh.AddLine('y', [-10.0, 10.0])
mesh.SmoothMeshLines('y', res_far)

# Z mesh — fine through substrate, coarser in air above
z_sub = np.linspace(0, substrate_thickness, 6)        # 0, 0.042, 0.084, 0.126, 0.168, 0.21
z_air = np.array([0.5, 1.0, 2.0, 4.0])
mesh.AddLine('z', np.concatenate([z_sub, z_air]))
mesh.SmoothMeshLines('z', res_far)

# Substrate
substrate = CSX.AddMaterial('FR4', epsilon=substrate_epr)
substrate.AddBox([-MSL_length, -10.0, 0],
                  [+MSL_length, +10.0, substrate_thickness])

# Metal layer
pec = CSX.AddMetal('PEC')

# MSL ports
port = [None, None]
portstart = [-MSL_length, -MSL_width/2, substrate_thickness]
portstop  = [ 0,          +MSL_width/2, 0]
port[0] = FDTD.AddMSLPort(1, pec, portstart, portstop, 'x', 'z',
                            excite=-1, FeedShift=FEED_SHIFT, Feed_R=50,
                            MeasPlaneShift=MEAS_SHIFT, priority=10)
portstart = [+MSL_length, -MSL_width/2, substrate_thickness]
portstop  = [ 0,          +MSL_width/2, 0]
# Terminate port[1] with 50Ω lumped load — without it the line is
# open-circuited at the PML and energy bounces back & forth, never
# decaying to the EndCriteria. With Feed_R=50, the un-excited port acts
# as a matched termination.
port[1] = FDTD.AddMSLPort(2, pec, portstart, portstop, 'x', 'z',
                            Feed_R=50,
                            MeasPlaneShift=MEAS_SHIFT, priority=10)

print(f"=== openEMS microstrip Z0 validation ===")
print(f"Geometry: W={MSL_width}mm, h={substrate_thickness}mm, t={metal_thickness}mm, εr={substrate_epr}")
print(f"Line length: {2*MSL_length}mm, f_max: {f_max/1e9} GHz")
print(f"Mesh: dy_strip={dy_strip:.4f}mm, dz_sub={dz_sub:.4f}mm, dx={dx}mm, res_far={res_far:.3f}mm")
print("Running FDTD simulation...")

FDTD.Run(Sim_Path, cleanup=True, verbose=1)

f_test = np.array([0.2e9, 0.5e9, 1.0e9, 1.5e9, 2.0e9])
for p in port:
    p.CalcPort(Sim_Path, f_test)

Z0_openems = np.abs(port[0].Z_ref)

# H-J 1980 analytical (same as val_skrf_microstrip.py)
W = MSL_width * 1e-3
H = substrate_thickness * 1e-3
T = metal_thickness * 1e-3
EpR = substrate_epr
W_eff = W + (T/math.pi) * (1 + math.log(2*H/T))
e_eff = (EpR + 1)/2 + (EpR - 1)/2 * (1 + 12*H/W_eff)**(-0.5)
if W_eff/H <= 1:
    Z0_hj = 60/math.sqrt(e_eff) * math.log(8*H/W_eff + W_eff/(4*H))
else:
    Z0_hj = 120*math.pi/math.sqrt(e_eff) / (W_eff/H + 1.393 + 0.667*math.log(W_eff/H+1.444))

print(f"\n{'Freq (GHz)':>12} {'Z0_openEMS':>14} {'Z0_H-J':>10} {'err_%':>10}")
for i, f in enumerate(f_test):
    err = abs(Z0_openems[i] - Z0_hj) / Z0_hj * 100
    print(f"{f/1e9:>12.2f} {Z0_openems[i]:>14.3f} {Z0_hj:>10.3f} {err:>10.3f}")

Z0_at_1GHz = Z0_openems[2]
err_1GHz = abs(Z0_at_1GHz - Z0_hj) / Z0_hj * 100
print(f"\nReference: 1 GHz openEMS Z0 = {Z0_at_1GHz:.3f} Ω")
print(f"Analytical H-J 1980          = {Z0_hj:.3f} Ω")
print(f"Error: {err_1GHz:.3f}%")
verdict = "PASS" if err_1GHz < 5.0 else "FAIL"
print(f"Verdict: {verdict}  (criterion <5% vs H-J)")
