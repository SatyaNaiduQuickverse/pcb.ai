#!/usr/bin/env python3
"""
openEMS FDTD: SW-node (MOTOR_A_CH1) EMI radiation + BEMF crosstalk
pcb.ai FPV 4-in-1 ESC, Phase 4-v3 CH1.

Physical model (extracted from /tmp/ch1_v56.kicad_pcb via pcbnew):
  - SW node = MOTOR_A_CH1, the half-bridge motor-phase switching node, fast 25.2V edges.
    Routed on F.Cu (3oz) from the FET (Q5/Q6 ~x=5.5mm) through TP19=(15,53) to the motor
    connector. Modeled as an aggressor microstrip over the nearest GND plane (In1.Cu).
  - Victim = BEMF_A_CH1 sense net. Nearest BEMF node to TP19 is C74 @ (17.67,60.30),
    centerline distance 7.77mm (R61/R60 @ 9.47mm). The dispatch guideline is >=10mm; the
    actual closest BEMF node is 7.77mm, so we model the WORST-CASE 7.77mm centerline
    separation (more conservative than 10mm).
  - Stack: F.Cu top copper, FR4 (eps_r=4.3) dielectric h=0.15mm to first GND plane (In1.Cu),
    GND plane = PEC. (8-layer 1.6mm board; top dielectric ~0.1-0.2mm -> use 0.15mm.)

Excitation: Gaussian pulse covering 30 MHz .. 1 GHz.
Ports: MSL (microstrip line) port on the aggressor (port 1, driven 50ohm) and on the
victim (port 2, 50ohm passive). S21 = BEMF coupling vs SW node across the band.

Mesh: graded. Fine ~60um near the conductors (>=5 cells across each trace + thin-gap
resolution), coarse in the bulk. lambda/15 air-cell cap at 1 GHz as a global ceiling.

Outputs (in this dir):
  - emi_field/  (openEMS dump dir: E-field .vtr time snapshots + port .dat files)
  - emi_S21.csv (freq_Hz, S11_dB, S21_dB)
"""

import os, sys, tempfile
import numpy as np

# --- shared libs for the openEMS/CSXCAD .so (binary uses libopenEMS directly) ---
os.environ.setdefault("LD_LIBRARY_PATH", "")
# (LD_LIBRARY_PATH must already include /home/novatics64/local/openems/lib at launch)

from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0, MUE0
from CSXCAD import ContinuousStructure

HERE = os.path.dirname(os.path.abspath(__file__))
SIM_PATH = os.path.join(HERE, "emi_field")
CSV_OUT  = os.path.join(HERE, "emi_S21.csv")

# ------------------------------------------------------------------ parameters
unit = 1e-3   # all geometry in mm

# Frequency band of interest
f_min = 30e6
f_max = 1e9
f0    = (f_min + f_max) / 2.0      # Gaussian center
fc    = (f_max - f_min) / 2.0      # Gaussian 20dB half-bandwidth

# Microstrip stack (from board)
eps_r   = 4.3        # FR4 relative permittivity
tan_d   = 0.02       # FR4 loss tangent (typical) -- physical, and damps spurious modes
h_sub   = 0.15       # dielectric height F.Cu -> first GND plane (mm)
t_cu    = 0.035      # modeled copper sheet thickness (thin; PEC sheet)

# Trace geometry (from extracted board)
w_sw    = 1.0        # SW aggressor (3oz motor phase) width (mm)
w_bemf  = 0.25       # BEMF victim sense width (mm)
sep_cl  = 7.77       # centerline separation SW<->BEMF (mm) -- actual worst-case C74<->TP19
# Coupled-trace length: the SW node + nearest BEMF node run parallel over ~10mm in the
# TP19 region. Reduced from 14mm -> 10mm to keep cell count tractable on this 4-core Pi
# (dispatch permits reduced volume). 10mm still fully spans the parallel-run coupling zone.
L_trace = 10.0

# y positions (traces run along x)
y_sw    = 0.0
y_bemf  = sep_cl

# Substrate + ground run the FULL x-extent into the PML (standard openEMS MSL practice:
# the microstrip line is absorbed by the PML at both ends). y/z get air margins so the
# PML/MUR sits in free space, NOT on the dielectric interface (that caused divergence).
# y margin must hold the PML_8 (8 cells) PLUS a buffer so the traces sit in the near
# field, not inside the PML. ~10mm at the lateral mesh pitch gives the PML clean room.
my = 10.0
gnd_below = -h_sub   # GND plane z

# traces occupy x in [0, L_trace]; substrate extends a bit beyond so ports + PML fit
x_pad = 3.0
sub_xmin = -x_pad
sub_xmax = L_trace + x_pad
sub_ymin = y_sw - my
sub_ymax = y_bemf + my

# air box above the board (radiation region)
air_z = 10.0         # mm of air above the board

# mesh resolution
res_fine = 0.060     # 60 um near conductors (dispatch fine cell)
# global air ceiling: lambda/15 at f_max in air
lambda_min_air = C0 / f_max / unit   # mm
res_coarse = lambda_min_air / 15.0   # ~20 mm -> bounded by box anyway

print(f"[geom] L_trace={L_trace}mm  w_sw={w_sw}  w_bemf={w_bemf}  sep={sep_cl}mm  h_sub={h_sub}mm eps_r={eps_r}")
print(f"[mesh] res_fine={res_fine*1000:.0f}um  lambda_min_air@1GHz={lambda_min_air:.1f}mm  res_coarse_cap={res_coarse:.2f}mm")

# ------------------------------------------------------------------ FDTD setup
# NrTS must exceed the excitation length so energy can ring out + decay AFTER the pulse.
# EndCriteria=1e-4 (-40 dB residual energy) stops the run early once it decays (if stable).
FDTD = openEMS(NrTS=300000, EndCriteria=1e-4)
FDTD.SetGaussExcite(f0, fc)

# Boundaries: PML_8 on x AND y absorbs the microstrip mode (x) and the lateral substrate
# parallel-plate mode (y). Combined with the FR4 loss tangent (added to the material
# below), this kills the trapped parallel-plate resonance that pinned the lossless+MUR
# run flat at -8 dB. zmin = PEC (GND / reference floor); zmax = MUR (radiation into air).
# Order: [xmin, xmax, ymin, ymax, zmin, zmax].
FDTD.SetBoundaryCond(['PML_8','PML_8','PML_8','PML_8','PEC','MUR'])

CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)

# ----- materials
# FR4 substrate, from the GND plane (z=gnd_below, the PEC zmin boundary) up to z=0.
# Lossy dielectric: kappa = 2*pi*f0*eps0*eps_r*tan_d  (electric conductivity from loss
# tangent at the band center). Physical for FR4 and damps spurious cavity modes.
kappa = 2*np.pi*f0*EPS0*eps_r*tan_d
sub = CSX.AddMaterial('FR4', epsilon=eps_r, kappa=kappa)
sub.AddBox([sub_xmin, sub_ymin, gnd_below], [sub_xmax, sub_ymax, 0.0])
# The ground plane IS the zmin PEC boundary (set in SetBoundaryCond). Modeling it as the
# domain floor (rather than a floating PEC sheet with air beneath) removes the unstable
# air-below-plane region and is the standard microstrip-over-PEC-floor setup.

# ----- mesh lines
# X: full coupled-line length spans the substrate; ports sit at the ends.
mesh.AddLine('x', [sub_xmin, 0.0, L_trace, sub_xmax])
mesh.SmoothMeshLines('x', res_fine*8)         # ~0.5mm baseline along length

# Y: fine across each trace edge (thirds-rule) + graded fill, coarser in margins.
y_sw_lo, y_sw_hi   = y_sw - w_sw/2,   y_sw + w_sw/2
y_bf_lo, y_bf_hi   = y_bemf - w_bemf/2, y_bemf + w_bemf/2
mesh.AddLine('y', [sub_ymin, sub_ymax])
# >=5 cells across the SW trace; resolve the narrow BEMF trace with edges + center.
mesh.AddLine('y', np.linspace(y_sw_lo,  y_sw_hi,  6))   # 5 cells across 1.0mm SW (~60um)
mesh.AddLine('y', [y_bf_lo, y_bemf, y_bf_hi])           # BEMF edges+center (~62um)
# graded fill across the gap between traces
mesh.AddLine('y', np.linspace(y_sw_hi+0.06, y_bf_lo-0.06, 8))
mesh.SmoothMeshLines('y', res_fine*6)                  # ~60um floor near traces

# Z: resolve the thin dielectric with 4 cells (~37.5um), coarse up into air.
# 4 cells across a microstrip substrate is accurate (openEMS MSL tutorials use 2-4); using
# fewer cells than the original 6 lifts the Courant timestep ~1.5x -> shorter run on the Pi.
mesh.AddLine('z', [gnd_below, 0.0])
mesh.AddLine('z', np.linspace(gnd_below, 0.0, 5))   # 4 cells in dielectric (~37.5um)
mesh.AddLine('z', [air_z])
mesh.SmoothMeshLines('z', res_fine*4)               # coarser air grading

# ----- LUMPED-PORT crosstalk model (robust fixed 50 ohm reference)
# The MSL-port characteristic-impedance auto-extraction was numerically unreliable on this
# thin, electrically-small structure (it returned nan capacitance and non-physical >0 dB
# S-params). Lumped ports use a FIXED 50 ohm reference -> clean, well-defined S-parameters.
#
# Each trace is an explicit thin PEC strip along x at z=0. At BOTH ends of each trace a
# vertical (z) lumped element connects strip->ground plane (z=gnd_below):
#   Port 1  : aggressor (SW)  near end (x=0)         excited, 50 ohm  -> S11 ref
#   R_a_far : aggressor far end (x=L_trace)          50 ohm matched termination
#   Port 2  : victim (BEMF)   near end (x=0)         50 ohm           -> S21 = coupling
#   R_v_far : victim far end (x=L_trace)             50 ohm matched termination
# S21 (port2/port1) is the SW->BEMF crosstalk coupling we want vs 30 MHz..1 GHz.

# Aggressor SW strip (thin PEC) along x
sw = CSX.AddMetal('sw_trace')
sw.AddBox([0.0, y_sw_lo, 0.0], [L_trace, y_sw_hi, 0.0])
# Victim BEMF strip (thin PEC) along x
bf = CSX.AddMetal('bemf_trace')
bf.AddBox([0.0, y_bf_lo, 0.0], [L_trace, y_bf_hi, 0.0])

# small inset so the lumped port box sits on mesh lines just inside the strip ends
xn = 0.0
xf = L_trace

# Port 1: aggressor near end, vertical lumped port (z from gnd_below to strip 0.0)
port1 = FDTD.AddLumpedPort(1, 50,
                           [xn, y_sw_lo, gnd_below], [xn, y_sw_hi, 0.0],
                           'z', excite=1.0, priority=5)
# Aggressor far-end matched 50 ohm load (lumped element, not a port)
Ra = CSX.AddLumpedElement('R_agg_far', ny='z', caps=True, R=50)
Ra.AddBox([xf, y_sw_lo, gnd_below], [xf, y_sw_hi, 0.0], priority=5)

# Port 2: victim near end, 50 ohm (passive, measures coupled wave)
port2 = FDTD.AddLumpedPort(2, 50,
                           [xn, y_bf_lo, gnd_below], [xn, y_bf_hi, 0.0],
                           'z', excite=0, priority=5)
# Victim far-end matched 50 ohm load
Rv = CSX.AddLumpedElement('R_vic_far', ny='z', caps=True, R=50)
Rv.AddBox([xf, y_bf_lo, gnd_below], [xf, y_bf_hi, 0.0], priority=5)

# ----- E-field time dump over a plane just above the board (for .vtr radiation field)
Edump = CSX.AddDump('emi_Et', dump_type=0, dump_mode=2)  # E-field, time domain, node-interp
Edump.AddBox([sub_xmin, sub_ymin, h_sub*0.5],
             [sub_xmax, sub_ymax, h_sub*0.5])

# ----- run
if os.path.isdir(SIM_PATH):
    import shutil; shutil.rmtree(SIM_PATH)
os.makedirs(SIM_PATH, exist_ok=True)

SETUP_ONLY = ('--setup-only' in sys.argv)
print(f"[run] starting openEMS FDTD ... (setup_only={SETUP_ONLY})")
FDTD.Run(SIM_PATH, cleanup=False, verbose=3, numThreads=4, setup_only=SETUP_ONLY)
print("[run] FDTD finished.")
if SETUP_ONLY:
    sys.exit(0)

# ------------------------------------------------------------------ post-proc
f = np.linspace(f_min, f_max, 401)
port1.CalcPort(SIM_PATH, f)
port2.CalcPort(SIM_PATH, f)

s11 = port1.uf_ref / port1.uf_inc
s21 = port2.uf_ref / port1.uf_inc   # coupling SW(1) -> BEMF(2)

s11_db = 20*np.log10(np.abs(s11))
s21_db = 20*np.log10(np.abs(s21))

# write CSV
import csv
with open(CSV_OUT, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['freq_Hz', 'S11_dB', 'S21_dB_BEMF_coupling'])
    for fi, a, b in zip(f, s11_db, s21_db):
        w.writerow([f"{fi:.6e}", f"{a:.4f}", f"{b:.4f}"])

imax = int(np.argmax(s21_db))
print(f"[result] wrote {CSV_OUT}")
print(f"[result] worst-case (max) BEMF coupling S21 = {s21_db[imax]:.2f} dB @ {f[imax]/1e6:.1f} MHz")
print(f"[result] S21 @30MHz={s21_db[0]:.2f}dB  @1GHz={s21_db[-1]:.2f}dB")
print(f"[verdict] target <= -40 dB -> {'PASS' if s21_db[imax] <= -40 else 'FAIL'}")
