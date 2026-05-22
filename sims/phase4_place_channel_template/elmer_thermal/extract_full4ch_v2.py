"""Extract per-FET T_J from full 4-channel Elmer FEM v4 (A4-d).

Per master sim-execution-gate rule:
- Reads ch1_thermal_v4_full4ch from full4ch_mesh_v2/full4ch_thermal_v2.vtu_t0002.vtu
- Executed: /home/novatics64/local/elmer/bin/ElmerSolver full4ch_thermal_v2.sif
- Result file mtime > sif mtime (verified via ls -la)
"""
import meshio, numpy as np, glob

vtus = sorted(glob.glob('full4ch_mesh_v2/full4ch_thermal_v2.vtu_*.vtu'))
m = meshio.read(vtus[-1])
T = m.point_data.get('temperature').flatten() - 273.15
pts = m.points

print("Phase 4 A4-d FULL 4-channel Elmer FEM v4 — per-FET T_J extract")
print(f"  Source: {vtus[-1]}")
print(f"  Mesh T range: {T.min():.3f} to {T.max():.3f} °C")
print()

fets = [
    ('CH1 Q5 hi-A',12,54),  ('CH1 Q6 lo-A',30,54),
    ('CH1 Q7 hi-B',12,66),  ('CH1 Q8 lo-B',30,66),
    ('CH1 Q9 hi-C',12,78),  ('CH1 Q10 lo-C',30,78),
    ('CH2 Q11 hi-A',88,54), ('CH2 Q12 lo-A',70,54),
    ('CH2 Q13 hi-B',88,66), ('CH2 Q14 lo-B',70,66),
    ('CH2 Q15 hi-C',88,78), ('CH2 Q16 lo-C',70,78),
    ('CH3 Q17 hi-A',88,41), ('CH3 Q18 lo-A',70,41),
    ('CH3 Q19 hi-B',88,30), ('CH3 Q20 lo-B',70,30),
    ('CH3 Q21 hi-C',88,19), ('CH3 Q22 lo-C',70,19),
    ('CH4 Q23 hi-A',12,41), ('CH4 Q24 lo-A',30,41),
    ('CH4 Q25 hi-B',12,30), ('CH4 Q26 lo-B',30,30),
    ('CH4 Q27 hi-C',12,19), ('CH4 Q28 lo-C',30,19),
]
T_amb = 60.0
all_pass = True
print(f"  {'FET':18s}  T_burst (°C)  T_cont (°C)  Verdict")
for name, x_mm, y_mm in fets:
    d = np.linalg.norm(pts - np.array([x_mm*1e-3, y_mm*1e-3, 0.0008]), axis=1)
    i = np.argmin(d)
    T_burst = float(T[i])
    T_cont = T_amb + (T_burst - T_amb) * (5.88/12.0)
    v_burst = T_burst <= 150
    v_cont = T_cont <= 100
    if not (v_burst and v_cont):
        all_pass = False
    print(f"  {name:18s}  {T_burst:7.3f}      {T_cont:7.3f}     {'PASS ✓' if v_burst and v_cont else 'FAIL ✗'}")
print()
print(f"OVERALL Sim 1 verdict (all 24 FETs): {'PASS ✓' if all_pass else 'FAIL ✗'}")
