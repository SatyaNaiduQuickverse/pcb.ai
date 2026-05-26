#!/usr/bin/env python3
"""extract_per_fet.py — Per-FET T_J extraction for Phase 4-v3 CH1 thermal sim.

Reads the Elmer VTU post-output (authoritative nodal temperature field, via
meshio) for the option-b substrate model, samples T_substrate at each FET's XY
on the relevant copper layer's surface (top z=1.6mm for the high-side F.Cu FETs,
bottom z=0 for the low-side B.Cu FETs), then computes the junction temperature:

    T_J = T_substrate(at FET XY) + P_FET × R_θJC ,  R_θJC = 1.0 K/W (BSC014N06NS PDFN-8)

Writes per_fet_table.txt with markdown tables for BOTH the 100A continuous and
150A burst cases, including margin to the 110°C target.

Per master sim-execution-gate: numbers here are reproduced directly from the
committed Elmer artifacts (ch1_full.vtu / ch1_full_150A.vtu); the VTU max is
cross-checked to equal the SaveScalars global .dat max.
"""
import numpy as np
import meshio

BASE = "/home/novatics64/escworker/pcb.ai/sims/phase4v3/ch1_thermal"
VTU_100A = f"{BASE}/ch1_full.vtu"
VTU_150A = f"{BASE}/ch1_full_150A.vtu"
DAT_100A = f"{BASE}/ch1_full_global.dat"
DAT_150A = f"{BASE}/ch1_full_150A_global.dat"
OUT = f"{BASE}/per_fet_table.txt"

R_THETA_JC = 1.0      # K/W, BSC014N06NS PDFN-8 datasheet
P_FET_100A = 11.1     # W per FET, 100A continuous (established loss model)
P_FET_150A = 24.1     # W per FET, 150A burst
TARGET_TJ = 110.0     # °C target per FET

SUB_H = 0.0016        # substrate thickness (m); top z=SUB_H, bottom z=0

# FETs in substrate-LOCAL coords (zone board-y 50..86mm -> local_y = board_y - 50).
#   x = 8.4mm (west FET column, inside body-2 strip 4..13mm).
#   HS Q5/Q7/Q9 (F.Cu, top surface)  at board y=53/66/79 -> local 3/16/29.
#   LS Q6/Q8/Q10 (B.Cu, bottom surface) offset +5.4mm in y (inside 0..39mm strip).
FETS = [
    ("Q5",  "HS", 8.4,  3.0),
    ("Q7",  "HS", 8.4, 16.0),
    ("Q9",  "HS", 8.4, 29.0),
    ("Q6",  "LS", 8.4,  8.4),
    ("Q8",  "LS", 8.4, 21.4),
    ("Q10", "LS", 8.4, 34.4),
]


def load(vtu, dat):
    m = meshio.read(vtu)
    pts = m.points                                   # (N,3) meters
    T = np.array(m.point_data["temperature"]).ravel()  # Kelvin
    dmax = float(open(dat).read().split()[0])
    assert abs(T.max() - dmax) < 0.05, \
        f"VTU max {T.max()} != SaveScalars {dmax} — artifact mismatch"
    return pts, T


def sample_Tsub(pts, T, x_mm, y_mm, side):
    """T_substrate at the surface node nearest the FET XY (top for HS, bottom for LS)."""
    x, y = x_mm * 1e-3, y_mm * 1e-3
    z_target = SUB_H if side == "HS" else 0.0
    on_surf = np.abs(pts[:, 2] - z_target) < 1e-9
    idx = np.where(on_surf)[0]
    d2 = (pts[idx, 0] - x) ** 2 + (pts[idx, 1] - y) ** 2
    return T[idx[np.argmin(d2)]] - 273.15            # °C


def build_table(pts, T, P_fet, label):
    out = []
    out.append(f"### {label}  (P_FET = {P_fet} W, R_θJC = {R_THETA_JC} K/W, target T_J ≤ {TARGET_TJ:.0f}°C)\n")
    out.append("| FET | side | XY local (mm) | T_sub (°C) | P_FET (W) | T_J (°C) | margin to 110°C |")
    out.append("|-----|------|---------------|-----------|-----------|----------|-----------------|")
    tj_max, worst = -1e9, None
    for ref, side, x, y in FETS:
        tsub = sample_Tsub(pts, T, x, y, side)
        tj = tsub + P_fet * R_THETA_JC
        if tj > tj_max:
            tj_max, worst = tj, ref
        out.append(f"| {ref} | {side} | ({x:.1f},{y:.1f}) | {tsub:.2f} | {P_fet:.1f} | {tj:.2f} | {TARGET_TJ-tj:+.2f} |")
    verdict = "PASS" if tj_max <= TARGET_TJ else "FAIL"
    out.append("")
    out.append(f"T_J max = {tj_max:.2f}°C at {worst}  ->  {verdict} (target ≤ {TARGET_TJ:.0f}°C)\n")
    return "\n".join(out), tj_max, verdict


def main():
    p100, T100 = load(VTU_100A, DAT_100A)
    p150, T150 = load(VTU_150A, DAT_150A)

    print(f"Nodes: {len(p100)}")
    print(f"100A: T_sub global max = {T100.max()-273.15:.2f}°C, min = {T100.min()-273.15:.2f}°C")
    print(f"150A: T_sub global max = {T150.max()-273.15:.2f}°C, min = {T150.min()-273.15:.2f}°C\n")

    t100, tj100, v100 = build_table(p100, T100, P_FET_100A, "100A continuous")
    t150, tj150, v150 = build_table(p150, T150, P_FET_150A, "150A burst")

    body = (
        "# CH1 Phase 4-v3 — per-FET junction temperature\n\n"
        "Source artifacts: ch1_full.vtu (100A), ch1_full_150A.vtu (150A); VTU max\n"
        "cross-checked == SaveScalars ch1_full_global.dat / ch1_full_150A_global.dat.\n"
        "T_J = T_substrate(at FET XY surface) + P_FET × R_θJC, R_θJC = 1.0 K/W (BSC014N06NS PDFN-8).\n\n"
        + t100 + "\n" + t150 + "\n"
        + "## Verdict\n"
        + f"- 100A continuous: T_J max = {tj100:.2f}°C -> {v100}\n"
        + f"- 150A burst:      T_J max = {tj150:.2f}°C -> {v150}\n"
    )
    open(OUT, "w").write(body)
    print(t100)
    print(t150)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
