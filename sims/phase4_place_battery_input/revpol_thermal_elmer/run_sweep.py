"""Run Elmer FEM rev-pol thermal sim across three load conditions.

  cont:  70A continuous bus → 17.5A per FET (4 in parallel) → P_FET = R×I² = 1.45mΩ × 17.5² = 0.44 W
         (use 100°C R_DS(on) ~2.4mΩ → 0.73W per FET; total 2.95W)
  burst: 100A 10s burst → 25A per FET → 2.4mΩ × 25² = 1.5W per FET; total 6.0W (transient,
         but evaluate steady-state to bound peak T_J during a hypothetical sustained burst)
  hold:  worst continuous-on case at 100A → 25A per FET sustained (unrealistic for spec but
         bound for analysis); same 6.0W steady-state.

Output: max T_J per case + verdict vs 100°C continuous / 175°C abs-max thresholds.
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

# (label, P_total_W, T_amb_C, T_limit_C, label_for_limit)
CASES = [
    ("continuous", 2.95, 60.0, 100.0, "100°C operating"),
    ("burst10s",   6.00, 60.0, 175.0, "175°C abs-max (BSC014N06NS)"),
]

RHO = 2700.0     # kg/m³ (effective FR4 + Cu composite)
VOL = 0.030 * 0.021 * 0.0016  # 1.008e-6 m³


def run_case(P_total_W, T_amb_C):
    # Set body-force Heat Source per case (W/kg = P / (ρ × V))
    heat_source_W_per_kg = P_total_W / (RHO * VOL)
    txt = SIF.read_text()
    txt = re.sub(r'Heat Source = [\d.eE+-]+',
                 f'Heat Source = {heat_source_W_per_kg:.4f}', txt)
    # External temperature on all 3 BCs
    txt = re.sub(r'External Temperature = [\d.]+',
                 f'External Temperature = {T_amb_C:.1f}', txt)
    SIF.write_text(txt)

    r = subprocess.run([ELMER, str(SIF.name)], cwd=str(HERE),
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit(f"Elmer failed for P={P_total_W}W")

    m = meshio.read(str(VTU))
    T = np.asarray(m.point_data['temperature']).flatten()
    return T.min(), T.mean(), T.max()


print("Phase 4-place-battery-input S1 — rev-pol FET cluster Elmer FEM thermal sweep")
print("=" * 78)
print(f"  Geometry: 30×21×1.6 mm board section; 4× BSC014N06NS @ 2×2 cluster on B.Cu")
print(f"  Effective k=20 W/m·K (FR4 + Cu composite, conservative)")
print(f"  BC top (F.Cu): h=80 W/m²·K prop-wash | bottom (B.Cu): h=20 W/m²·K heatsink-natural")
print(f"  BC sides: h=10 W/m²·K still-air")
print()

results = {}
for label, P, Ta, Tlim, lim_str in CASES:
    Tmin, Tmean, Tmax = run_case(P, Ta)
    margin = Tlim - Tmax
    verdict = "PASS ✓" if Tmax <= Tlim else f"FAIL ✗ (over by {-margin:.1f} °C)"
    print(f"--- {label} ---")
    print(f"  Conditions: P_total={P:.2f} W, T_amb={Ta:.0f}°C")
    print(f"  T_J max  = {Tmax:.2f} °C  (min={Tmin:.2f}, mean={Tmean:.2f})")
    print(f"  Limit    = {Tlim:.0f} °C ({lim_str})")
    print(f"  Margin   = {margin:.2f} °C — {verdict}")
    print()
    results[label] = (Tmin, Tmean, Tmax, Tlim, margin, verdict)

# Final summary line
print("VERDICT SUMMARY:")
for label, (_, _, Tmax, Tlim, margin, verdict) in results.items():
    print(f"  {label:12s}: T_J max={Tmax:.1f}°C, limit={Tlim:.0f}°C, margin={margin:.1f}°C — {verdict}")
