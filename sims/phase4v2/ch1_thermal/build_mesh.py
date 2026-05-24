#!/usr/bin/env python3
"""build_mesh.py — Elmer 3D mesh for CH1 thermal sim.

Per master 2026-05-24 spec:
- 3D mesh: PCB substrate (CH1 zone 35×32mm × 1.6mm FR4) + 6 FET bodies as
  separate heat-source volumes (BSC014N06NS PDFN-8 ≈ 6×5×1mm).
- Each FET as a distinct body (Body 2..Body 7) so per-FET T_J can be
  extracted via SaveScalars Mask = Body N.

Mesh: structured hex grid.
  substrate: 35×32×1.6mm  → 7×8×2 elements (analytical match V1 pattern)
  FETs (6): each 5×6×1mm above substrate at FET XY positions
"""
import os, math

OUT = "/home/novatics64/escworker/pcb.ai/sims/phase4v2/ch1_thermal/ch1_mesh"
os.makedirs(OUT, exist_ok=True)

# CH1 zone (mm). Local origin = zone south-west corner.
# Q-positions in board coords (mm); transform to local = (x - zone_x0, y - zone_y0).
ZONE_X0, ZONE_Y0 = 0.0, 50.0
FETS = [
    ('Q5',  12.0, 54.0),
    ('Q6',  30.0, 54.0),
    ('Q7',  12.0, 66.0),
    ('Q8',  30.0, 66.0),
    ('Q9',  12.0, 78.0),
    ('Q10', 30.0, 78.0),
]

SUB_L, SUB_W, SUB_H = 0.035, 0.032, 0.0016     # 35×32×1.6 mm in m
FET_L, FET_W, FET_H = 0.006, 0.005, 0.001       # 6×5×1 mm in m (PDFN-8)
NX, NY, NZ = 14, 13, 3     # substrate hex grid
FNX, FNY, FNZ = 2, 2, 1    # FET hex grid (each)

nodes = []
elements = []
boundaries = []

node_idx = {}   # (i,j,k,'sub' or 'fet'+n) → node id
def add_node(x, y, z):
    nodes.append((x, y, z))
    return len(nodes)

# Substrate nodes (z=0..SUB_H)
for k in range(NZ + 1):
    z = k * SUB_H / NZ
    for j in range(NY + 1):
        y = j * SUB_W / NY
        for i in range(NX + 1):
            x = i * SUB_L / NX
            node_idx[(i, j, k, 'sub')] = add_node(x, y, z)

# Substrate hex elements (body 1)
eid = 0
for k in range(NZ):
    for j in range(NY):
        for i in range(NX):
            ns = [
                node_idx[(i, j, k, 'sub')],
                node_idx[(i+1, j, k, 'sub')],
                node_idx[(i+1, j+1, k, 'sub')],
                node_idx[(i, j+1, k, 'sub')],
                node_idx[(i, j, k+1, 'sub')],
                node_idx[(i+1, j, k+1, 'sub')],
                node_idx[(i+1, j+1, k+1, 'sub')],
                node_idx[(i, j+1, k+1, 'sub')],
            ]
            eid += 1
            elements.append((eid, 1, "808", ns))   # body=1 (substrate)

# Each FET body (cuboid above substrate at FET XY)
for fet_i, (ref, qx, qy) in enumerate(FETS, start=2):  # body 2..7
    lx = (qx - ZONE_X0 - FET_L*1000/2) / 1000.0    # convert to m
    ly = (qy - ZONE_Y0 - FET_W*1000/2) / 1000.0
    lz0 = SUB_H
    for k in range(FNZ + 1):
        z = lz0 + k * FET_H / FNZ
        for j in range(FNY + 1):
            y = ly + j * FET_W / FNY
            for i in range(FNX + 1):
                x = lx + i * FET_L / FNX
                node_idx[(i, j, k, f'fet{fet_i}')] = add_node(x, y, z)
    for k in range(FNZ):
        for j in range(FNY):
            for i in range(FNX):
                ns = [
                    node_idx[(i, j, k, f'fet{fet_i}')],
                    node_idx[(i+1, j, k, f'fet{fet_i}')],
                    node_idx[(i+1, j+1, k, f'fet{fet_i}')],
                    node_idx[(i, j+1, k, f'fet{fet_i}')],
                    node_idx[(i, j, k+1, f'fet{fet_i}')],
                    node_idx[(i+1, j, k+1, f'fet{fet_i}')],
                    node_idx[(i+1, j+1, k+1, f'fet{fet_i}')],
                    node_idx[(i, j+1, k+1, f'fet{fet_i}')],
                ]
                eid += 1
                elements.append((eid, fet_i, "808", ns))

# Boundaries: substrate top face (BC 1, convection h=15), substrate bottom (BC 2, h=5)
bid = 0
# Bottom (k=0 of substrate)
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, 0, 'sub')],
            node_idx[(i+1, j, 0, 'sub')],
            node_idx[(i+1, j+1, 0, 'sub')],
            node_idx[(i, j+1, 0, 'sub')],
        ]
        bid += 1
        boundaries.append((bid, 2, "404", ns))   # BC 2 = bottom
# Top of substrate (k=NZ)
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, NZ, 'sub')],
            node_idx[(i+1, j, NZ, 'sub')],
            node_idx[(i+1, j+1, NZ, 'sub')],
            node_idx[(i, j+1, NZ, 'sub')],
        ]
        bid += 1
        boundaries.append((bid, 1, "404", ns))   # BC 1 = top of substrate
# FET top faces (BC 3, h=15 with heatsink) — heatsink touches FET tops
for fet_i in range(2, 8):
    for j in range(FNY):
        for i in range(FNX):
            ns = [
                node_idx[(i, j, FNZ, f'fet{fet_i}')],
                node_idx[(i+1, j, FNZ, f'fet{fet_i}')],
                node_idx[(i+1, j+1, FNZ, f'fet{fet_i}')],
                node_idx[(i, j+1, FNZ, f'fet{fet_i}')],
            ]
            bid += 1
            boundaries.append((bid, 3, "404", ns))

# Write Elmer mesh files
with open(f"{OUT}/mesh.nodes", "w") as f:
    for nid, (x, y, z) in enumerate(nodes, 1):
        f.write(f"{nid} -1 {x:.6e} {y:.6e} {z:.6e}\n")

with open(f"{OUT}/mesh.elements", "w") as f:
    for eid_, body, typ, ns in elements:
        f.write(f"{eid_} {body} {typ} {' '.join(str(n) for n in ns)}\n")

with open(f"{OUT}/mesh.boundary", "w") as f:
    # Format: bnd_id, body_parent, bc_id, type, nodes
    for bid_, bc, typ, ns in boundaries:
        f.write(f"{bid_} {bc} 0 0 {typ} {' '.join(str(n) for n in ns)}\n")

with open(f"{OUT}/mesh.header", "w") as f:
    nb_types = set(e[2] for e in elements) | set(b[2] for b in boundaries)
    f.write(f"{len(nodes)} {len(elements)} {len(boundaries)}\n")
    f.write(f"{len(nb_types)}\n")
    for t in sorted(nb_types):
        count = sum(1 for e in elements if e[2] == t) + sum(1 for b in boundaries if b[2] == t)
        f.write(f"{t} {count}\n")

print(f"Mesh written: {len(nodes)} nodes, {len(elements)} elements, {len(boundaries)} boundary faces")
print(f"  Bodies: 1=substrate(FR4), 2-7=Q5/Q6/Q7/Q8/Q9/Q10 (PDFN-8)")
print(f"  BCs: 1=top-substrate(conv h=5), 2=bottom(conv h=5), 3=FET-top(heatsink h=15)")
