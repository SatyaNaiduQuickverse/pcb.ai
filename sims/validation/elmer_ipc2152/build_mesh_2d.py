#!/usr/bin/env python3
"""Generate Elmer mesh for V1 v2: substrate-only 50×50×1.6mm with surface heat.

2D analytical reference:
  q (W/m²) = 0.094 W / 2.5e-3 m² = 37.6 W/m² uniform on top face
  Steady state: T_top - T_amb = q × t/k + q/h = 0.20 + 7.52 = 7.72°C
  → T_max = 32.72°C (with T_amb = 25°C, h=5 W/m²K, FR4 k=0.30, t=1.6mm)
"""
import os
OUT = "/home/novatics64/escworker/pcb.ai/sims/validation/elmer_ipc2152/sub2d_mesh"
os.makedirs(OUT, exist_ok=True)

sub_L = 0.05
sub_W = 0.05
sub_H = 0.0016
nx, ny, nz = 5, 5, 4

node_id = lambda i, j, k: i + j*(nx+1) + k*(nx+1)*(ny+1) + 1
nodes = []
for k in range(nz+1):
    z = k * sub_H / nz
    for j in range(ny+1):
        y = j * sub_W / ny - sub_W/2
        for i in range(nx+1):
            x = i * sub_L / nx - sub_L/2
            nodes.append((x, y, z))

with open(f"{OUT}/mesh.nodes", "w") as f:
    for idx, (x, y, z) in enumerate(nodes, 1):
        f.write(f"{idx} -1 {x:.6e} {y:.6e} {z:.6e}\n")

elements = []
elem_id = 1
for k in range(nz):
    for j in range(ny):
        for i in range(nx):
            n0=node_id(i,j,k); n1=node_id(i+1,j,k); n2=node_id(i+1,j+1,k); n3=node_id(i,j+1,k)
            n4=node_id(i,j,k+1); n5=node_id(i+1,j,k+1); n6=node_id(i+1,j+1,k+1); n7=node_id(i,j+1,k+1)
            elements.append((elem_id, 1, "808", [n0,n1,n2,n3,n4,n5,n6,n7]))
            elem_id += 1

with open(f"{OUT}/mesh.elements", "w") as f:
    for eid, body, typ, ns in elements:
        f.write(f"{eid} {body} {typ} {' '.join(str(n) for n in ns)}\n")

# Boundary: top face (BC 1 = heat in via flux), bottom face (BC 2 = convection)
boundaries = []
bnd_id = 1
# Top face at k=nz
for j in range(ny):
    for i in range(nx):
        n0=node_id(i,j,nz); n1=node_id(i+1,j,nz); n2=node_id(i+1,j+1,nz); n3=node_id(i,j+1,nz)
        boundaries.append((bnd_id, 1, "404", [n0,n1,n2,n3]))
        bnd_id += 1
# Bottom face at k=0
for j in range(ny):
    for i in range(nx):
        n0=node_id(i,j,0); n1=node_id(i+1,j,0); n2=node_id(i+1,j+1,0); n3=node_id(i,j+1,0)
        boundaries.append((bnd_id, 2, "404", [n0,n1,n2,n3]))
        bnd_id += 1

with open(f"{OUT}/mesh.boundary", "w") as f:
    for bid, btype, typ, ns in boundaries:
        f.write(f"{bid} {btype} 0 0 {typ} {' '.join(str(n) for n in ns)}\n")

with open(f"{OUT}/mesh.header", "w") as f:
    f.write(f"{len(nodes)} {len(elements)} {len(boundaries)}\n")
    f.write(f"2\n808 {len(elements)}\n404 {len(boundaries)}\n")

print(f"Mesh: {len(nodes)} nodes, {len(elements)} hex, {len(boundaries)} bnd")
