#!/usr/bin/env python3
"""extract_per_fet.py — Per-FET T_J extraction for CH1 thermal sim.

Per master 2026-05-24 spec:
  T_J = T_substrate + P_FET × R_θJC
  R_θJC = 1 K/W for BSC014N06NS PDFN-8 (datasheet)
  P_FET = 5W at 100A burst per spec

Analytical model (used pending Elmer BC debug):
  T_substrate = T_amb + Q_total / [(h_top + h_bot) × A_substrate]
  where Q_total = N_FET × P_FET, A_substrate = CH1 zone area

Heatsink scenario (Phase7 mechanical):
  h_top = 1000 W/m²K (heatsink + active cooling typical)
  h_bot = 5 W/m²K (natural convection from PCB underside)
  A = 35mm × 32mm = 1.12e-3 m²
"""

T_AMB = 25.0       # °C
N_FET = 6
P_FET_BURST = 5.0  # W per FET at 100A burst
R_THETA_JC = 1.0   # K/W BSC014N06NS PDFN-8 datasheet

A_SUBSTRATE = 0.035 * 0.032  # m²
H_TOP = 1000.0   # W/m²K Phase7 heatsink (assumed mounted directly on FETs)
H_BOT = 5.0      # W/m²K natural convection PCB underside

Q_TOTAL = N_FET * P_FET_BURST

# Analytical substrate temperature (Newton cooling balance)
T_substrate = T_AMB + Q_TOTAL / ((H_TOP + H_BOT) * A_SUBSTRATE)

# Per-FET T_J table (uniform distribution assumed; Q5-Q10 share load symmetrically)
FETS = [
    ('Q5',  12.0, 54.0),
    ('Q6',  30.0, 54.0),
    ('Q7',  12.0, 66.0),
    ('Q8',  30.0, 66.0),
    ('Q9',  12.0, 78.0),
    ('Q10', 30.0, 78.0),
]

print("=== CH1 thermal — per-FET T_J table (100A burst) ===\n")
print(f"Assumptions: T_amb={T_AMB}°C, N_FET={N_FET}, P_FET={P_FET_BURST}W, R_θJC={R_THETA_JC} K/W")
print(f"h_top={H_TOP} (Phase7 heatsink), h_bot={H_BOT} (natural)")
print(f"A_substrate = {A_SUBSTRATE*1e6:.0f} mm²")
print(f"Q_total = {Q_TOTAL} W")
print(f"T_substrate = {T_substrate:.1f}°C\n")

print(f"| FET | XY (mm) | T_substrate (°C) | P_FET (W) | R_θJC (K/W) | T_J (°C) | Margin to 100°C |")
print(f"|-----|---------|------------------|-----------|-------------|----------|-----------------|")
for ref, x, y in FETS:
    t_j = T_substrate + P_FET_BURST * R_THETA_JC
    margin = 100.0 - t_j
    print(f"| {ref} | ({x:.0f},{y:.0f}) | {T_substrate:.1f} | {P_FET_BURST:.1f} | {R_THETA_JC:.1f} | {t_j:.1f} | {margin:+.1f} |")

print(f"\nT_J_max = {T_substrate + P_FET_BURST * R_THETA_JC:.1f}°C")
print(f"Spec limit = 100°C")
if T_substrate + P_FET_BURST * R_THETA_JC <= 100.0:
    print("STATUS: PASS — within thermal margin")
else:
    print("STATUS: FAIL — exceeds 100°C limit; revisit heatsink + airflow design")
