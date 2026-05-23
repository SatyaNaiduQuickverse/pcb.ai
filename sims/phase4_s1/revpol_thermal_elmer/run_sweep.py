"""Run Elmer FEM rev-pol thermal sim across continuous + burst load conditions.

PER-FET T_J extraction at each FET center coordinate (Q1, Q2, Q3, Q4 individually).

Conditions:
  cont:  70A continuous bus → 17.5A per FET (4 in parallel) → P_FET = 2.4mΩ × 17.5² = 0.74 W
         (using R_DS(on) at T_J=100°C ≈ 2.4 mΩ); total 2.95 W
  burst: 100A 10s burst → 25A per FET → 2.4mΩ × 25² = 1.5 W per FET; total 6.0 W

Output: per-FET T_J for Q1-Q4 + overall verdict.

BC (Option A — master adjudication 2026-05-22):
  Q1/Q2 zone (y<10 mm): h_bottom = 400 W/m²·K (10×8 mm Cu pour + 16 thermal vias to
    In3.Cu VMOTOR plane 3oz; In3 spreads heat across full-board area)
  Q3/Q4 zone (y≥10 mm): h_bottom = 800 W/m²·K (existing 80×55 mm heatsink + fin_mult=10)
  F.Cu top (uniform): h = 80 (prop-wash)
  Sides: h = 10 (still-air)
"""
import subprocess
from pathlib import Path
import re
import meshio
import numpy as np

HERE = Path(__file__).parent
SIF = HERE / "revpol_thermal.sif"
VTU = HERE / "revpol_cluster" / "revpol_thermal_t0002.vtu"
ELMER = "/home/novatics64/local/elmer/bin/ElmerSolver"

CASES = [
    ("continuous", 2.95, 60.0, 100.0, "100°C operating spec"),
    ("burst10s",   6.00, 60.0, 175.0, "175°C abs-max (BSC014N06NS)"),
]
FETS = [('Q1', 6.0, 5.5), ('Q2', 14.0, 5.5),
        ('Q3', 6.0, 14.5), ('Q4', 14.0, 14.5)]

RHO = 2700.0
VOL = 0.030 * 0.021 * 0.0016


def run_case(P_total_W, T_amb_C):
    heat_source = P_total_W / (RHO * VOL)
    txt = SIF.read_text()
    txt = re.sub(r'Heat Source = [\d.eE+-]+',
                 f'Heat Source = {heat_source:.4f}', txt)
    txt = re.sub(r'External Temperature = [\d.]+',
                 f'External Temperature = {T_amb_C:.1f}', txt)
    SIF.write_text(txt)

    r = subprocess.run([ELMER, str(SIF.name)], cwd=str(HERE),
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit("Elmer failed")

    m = meshio.read(str(VTU))
    T = np.asarray(m.point_data['temperature']).flatten()
    pts = m.points * 1000
    per_fet = {}
    for label, fx, fy in FETS:
        d = np.sqrt((pts[:, 0] - fx)**2 + (pts[:, 1] - fy)**2)
        mask = d == d.min()
        per_fet[label] = float(T[mask].max())
    return per_fet, float(T.min()), float(T.mean()), float(T.max())


print("Phase 4-place-battery-input S1 — rev-pol FET cluster Elmer FEM")
print("                                 (Option A: per-FET pour+vias for Q1/Q2)")
print("=" * 78)
print(f"  Geometry: 30×21×1.6 mm board section; 4× BSC014N06NS at FET centers")
print(f"            Q1(6,5.5), Q2(14,5.5), Q3(6,14.5), Q4(14,14.5) mm")
print(f"  k=60 W/m·K composite (FR4+Cu, isotropic, conservative)")
print(f"  BC top h=80 (prop-wash); bottom h=400 for y<10 (Q1/Q2 pour+vias) | "
      f"h=800 for y≥10 (Q3/Q4 heatsink); sides h=10")
print()

all_pass = True
for label, P, Ta, Tlim, lim_str in CASES:
    per_fet, Tmin, Tmean, Tmax = run_case(P, Ta)
    print(f"--- {label} (P_total={P:.2f} W, T_amb={Ta:.0f}°C) ---")
    case_pass = True
    for fet_label, fx, fy in FETS:
        Tfet = per_fet[fet_label]
        margin = Tlim - Tfet
        fet_verdict = "PASS ✓" if Tfet <= Tlim else f"FAIL ✗ (over by {-margin:.1f}°C)"
        if Tfet > Tlim:
            case_pass = False; all_pass = False
        print(f"  {fet_label} @ ({fx},{fy}) mm: T_J = {Tfet:.2f} °C  margin to {Tlim:.0f}°C = {margin:.2f} °C  → {fet_verdict}")
    print(f"  Whole-domain min/mean/max: {Tmin:.2f} / {Tmean:.2f} / {Tmax:.2f} °C")
    print(f"  Case verdict (per-FET MAX governs): {'PASS ✓' if case_pass else 'FAIL ✗'}")
    print()

print(f"OVERALL: {'PASS ✓ — all 4 FETs PASS both cont. + burst' if all_pass else 'FAIL ✗ — at least one per-FET violation'}")
