#!/usr/bin/env python3
"""build_mesh.py — Elmer 3D mesh for CH1 thermal sim (option b).

Per master 2026-05-24 APPROVE option (b):
- Substrate-only mesh with distributed heat source
- T_substrate sampled at FET XY positions
- T_J = T_substrate + P_FET × R_θJC (datasheet ~1 K/W for BSC014N06NS PDFN-8)
- Equivalent physics, simpler setup, no info loss

Substrate: CH1 zone 35×32×1.6mm FR4.
Heat: 6 FETs × 5W = 30W total, distributed as q_volumetric = 30W / 1.792e-6 m³ = 1.67e7 W/m³
BC: top h=15 (with Phase7 heatsink), bottom h=5 natural convection, T_amb=25°C
"""
import os

OUT = "/home/novatics64/escworker/pcb.ai/sims/phase4v2/ch1_thermal/ch1_mesh"
os.makedirs(OUT, exist_ok=True)

SUB_L, SUB_W, SUB_H = 0.035, 0.032, 0.0016
NX, NY, NZ = 14, 13, 4

nodes = []
def add_node(x, y, z):
    nodes.append((x, y, z))
    return len(nodes)

node_idx = {}
for k in range(NZ + 1):
    z = k * SUB_H / NZ
    for j in range(NY + 1):
        y = j * SUB_W / NY
        for i in range(NX + 1):
            x = i * SUB_L / NX
            node_idx[(i, j, k)] = add_node(x, y, z)

elements = []
eid = 0
for k in range(NZ):
    for j in range(NY):
        for i in range(NX):
            ns = [
                node_idx[(i, j, k)],
                node_idx[(i+1, j, k)],
                node_idx[(i+1, j+1, k)],
                node_idx[(i, j+1, k)],
                node_idx[(i, j, k+1)],
                node_idx[(i+1, j, k+1)],
                node_idx[(i+1, j+1, k+1)],
                node_idx[(i, j+1, k+1)],
            ]
            eid += 1
            elements.append((eid, 1, "808", ns))

boundaries = []
bid = 0
# Bottom (k=0) — BC 2 (h=5)
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, 0)],
            node_idx[(i+1, j, 0)],
            node_idx[(i+1, j+1, 0)],
            node_idx[(i, j+1, 0)],
        ]
        bid += 1
        boundaries.append((bid, 2, "404", ns))
# Top (k=NZ) — BC 1 (h=15 heatsink)
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, NZ)],
            node_idx[(i+1, j, NZ)],
            node_idx[(i+1, j+1, NZ)],
            node_idx[(i, j+1, NZ)],
        ]
        bid += 1
        boundaries.append((bid, 1, "404", ns))

with open(f"{OUT}/mesh.nodes", "w") as f:
    for nid, (x, y, z) in enumerate(nodes, 1):
        f.write(f"{nid} -1 {x:.6e} {y:.6e} {z:.6e}\n")
with open(f"{OUT}/mesh.elements", "w") as f:
    for eid_, body, typ, ns in elements:
        f.write(f"{eid_} {body} {typ} {' '.join(str(n) for n in ns)}\n")
with open(f"{OUT}/mesh.boundary", "w") as f:
    for bid_, bc, typ, ns in boundaries:
        f.write(f"{bid_} {bc} 0 0 {typ} {' '.join(str(n) for n in ns)}\n")
with open(f"{OUT}/mesh.header", "w") as f:
    f.write(f"{len(nodes)} {len(elements)} {len(boundaries)}\n")
    f.write("2\n808 {}\n404 {}\n".format(len(elements), len(boundaries)))

print(f"Mesh: {len(nodes)} nodes, {len(elements)} hex elements, {len(boundaries)} bnd faces")
