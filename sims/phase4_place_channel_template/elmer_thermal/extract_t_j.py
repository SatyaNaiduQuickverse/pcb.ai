"""Extract per-FET T_J from Elmer FEM VTU output.

Sample T at 6 FET center locations + apply concentration factor to estimate
peak per-FET T_J (since uniform body source spreads heat).
"""
import meshio
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent
VTU_DIR = HERE / "ch1_cluster"

# Find latest VTU
vtu_files = sorted(VTU_DIR.glob("*.vtu")) if VTU_DIR.exists() else []
if not vtu_files:
    vtu_files = sorted(HERE.glob("*.vtu"))

if not vtu_files:
    print("No VTU file found")
    exit(1)

mesh = meshio.read(vtu_files[-1])
T = mesh.point_data.get('temperature', mesh.point_data.get('Temperature'))
if T is None:
    print("No temperature in VTU. Keys:", list(mesh.point_data.keys()))
    exit(1)

T_celsius = T - 273.15
points = mesh.points

print(f"Elmer FEM 8L thermal sim — S4 CH1 6-FET cluster (100A burst)")
print(f"  Mesh: {len(points)} nodes, {len(mesh.cells)} element groups")
print(f"  T range: {T_celsius.min():.1f} to {T_celsius.max():.1f} °C")
print()

# Sample at 6 FET mesh-local positions
# FETs at: Q5(7,3) Q6(25,3) Q7(7,16) Q8(25,16) Q9(7,28) Q10(25,28) — convert to meters
fet_positions = {
    'Q5 (Phase A hi)':  (0.007, 0.003, 0.0008),
    'Q6 (Phase A lo)':  (0.025, 0.003, 0.0008),
    'Q7 (Phase B hi)':  (0.007, 0.016, 0.0008),
    'Q8 (Phase B lo)':  (0.025, 0.016, 0.0008),
    'Q9 (Phase C hi)':  (0.007, 0.028, 0.0008),
    'Q10 (Phase C lo)': (0.025, 0.028, 0.0008),
}

# Concentration factor: uniform body source vs realistic per-FET hotspot
# FETs occupy ~30% of volume; concentration ratio ~3.3×
# Honest scaling: T_J_real = T_amb + (T_avg - T_amb) × concentration_factor
T_avg = T_celsius.mean()
T_amb = 60.0
CONC = 3.3  # 6-FET volume vs total mesh volume

print(f"  Mesh-averaged T: {T_avg:.1f} °C")
print(f"  Per-FET T_J estimate (with {CONC}× concentration scaling):")
print()
print(f"  {'FET':25s}  T_node (°C)  T_J_est (°C)  Spec  Verdict")
print(f"  {'-'*70}")

all_pass_continuous = True
all_pass_burst = True
for name, (x, y, z) in fet_positions.items():
    # Find nearest node
    dist = np.linalg.norm(points - np.array([x, y, z]), axis=1)
    i = np.argmin(dist)
    T_node = float(T_celsius.flatten()[i])
    T_J_est = T_amb + (T_node - T_amb) * CONC
    # Spec acceptance
    v_burst = T_J_est <= 150.0
    if not v_burst:
        all_pass_burst = False
    # Estimate continuous (70A) — power scales as I²
    T_J_continuous = T_amb + (T_node - T_amb) * CONC * (70.0/100.0)**2
    v_continuous = T_J_continuous <= 100.0
    if not v_continuous:
        all_pass_continuous = False
    print(f"  {name:25s}  {T_node:6.1f}     {T_J_est:6.1f}    ≤150°C burst  "
          f"{'PASS ✓' if v_burst else 'FAIL ✗'}")
    print(f"  {' '*25}             T_J_70A={T_J_continuous:.1f}    ≤100°C cont    "
          f"{'PASS ✓' if v_continuous else 'FAIL ✗'}")

print()
print(f"  OVERALL @ 100A burst (≤150°C): {'PASS ✓' if all_pass_burst else 'FAIL ✗'}")
print(f"  OVERALL @ 70A continuous (≤100°C): {'PASS ✓' if all_pass_continuous else 'FAIL ✗'}")
print()
print(f"  Honest methodology flag: uniform body heat source spreads heat;")
print(f"  per-FET T_J extracted via 3.3× concentration scaling (conservative).")
print(f"  Phase 5b autoroute: re-run with localized FET heat sources via mesh refinement.")
