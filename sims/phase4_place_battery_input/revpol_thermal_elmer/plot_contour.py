"""Plot 2D temperature contour from Elmer VTU output at z=mid-plane."""
import meshio
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from pathlib import Path

HERE = Path(__file__).parent
VTU = HERE / "revpol_cluster" / "revpol_thermal_t0002.vtu"
PNG = HERE / "revpol_thermal_contour.png"

m = meshio.read(str(VTU))
pts = m.points
T = np.asarray(m.point_data['temperature']).flatten()

# Slice at z = mid-plane (0.0008 m)
z_mid = 0.0008
mask = np.abs(pts[:, 2] - z_mid) < 0.0001
if mask.sum() < 10:
    # Fallback: use top z
    z_mid = pts[:, 2].max()
    mask = np.abs(pts[:, 2] - z_mid) < 0.0001

xs = pts[mask, 0] * 1000  # → mm
ys = pts[mask, 1] * 1000
Ts = T[mask]

# Interpolate to regular grid
xi = np.linspace(xs.min(), xs.max(), 100)
yi = np.linspace(ys.min(), ys.max(), 80)
Xi, Yi = np.meshgrid(xi, yi)
Ti = griddata((xs, ys), Ts, (Xi, Yi), method='linear')

fig, ax = plt.subplots(figsize=(10, 7), dpi=120)
cs = ax.contourf(Xi, Yi, Ti, levels=20, cmap='hot')
plt.colorbar(cs, ax=ax, label='Temperature (°C)')

# Mark FET centers (offset back to local coords)
# Mesh is 0..30 × 0..21 corresponding to S1 cluster 35..65 × 4..21 in board frame
# So board-frame FET position (40, 10) corresponds to local (5, 6).
fet_positions_local = [(5, 6, 'Q1'), (25, 6, 'Q2'), (5, 13, 'Q3'), (25, 13, 'Q4')]
for x, y, label in fet_positions_local:
    ax.plot(x, y, 'wo', markersize=8, markeredgecolor='black')
    ax.annotate(label, (x, y), textcoords="offset points",
                xytext=(10, 5), fontsize=10, color='white',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))

ax.set_xlabel('x (mm) — local to S1 cluster')
ax.set_ylabel('y (mm) — local to S1 cluster')
ax.set_title(f'S1 rev-pol FET 2×2 cluster — Elmer FEM thermal contour\n'
             f'(continuous load 2.95 W, T_amb=60°C, h_bottom_eff=200 W/m²·K)\n'
             f'T_max = {Ts.max():.1f} °C  margin to 100°C = {100 - Ts.max():.1f} °C')
ax.set_aspect('equal')
plt.tight_layout()
plt.savefig(PNG, dpi=120)
print(f'Wrote {PNG}')
