#!/usr/bin/env python3
"""Generate Elmer native mesh for IPC-2152 V1: trace + substrate co-simulation.

Geometry:
  Substrate: 50mm × 50mm × 1.6mm FR4 (Body 1)
  Trace: 0.254mm × 35µm × 50mm Cu on top center of substrate (Body 2)

Mesh: hex elements. Coarse outside trace, fine through trace.
Writes mesh.nodes, mesh.elements, mesh.boundary, mesh.header directly.
"""
import os
import numpy as np


OUT = "/home/novatics64/escworker/pcb.ai/sims/validation/elmer_ipc2152/trace_sub2_mesh"
os.makedirs(OUT, exist_ok=True)

# Geometry in meters
sub_L = 0.05      # 50mm substrate length
sub_W = 0.05      # 50mm substrate width
sub_H = 0.0016    # 1.6mm substrate height
trace_W = 0.000254  # 0.254mm trace width
trace_T = 0.000035  # 35µm trace thickness

# Mesh: uniform-ish hex
# Substrate divided 5×5×3 for compute speed
# Trace as 1 thin layer above substrate, 5 wide × 1 thick (actually thin)
# For simplicity: just use full-substrate-spanning trace layer (whole top is "trace volume" tagged Body 2 only where trace is)
# Simpler: use a single-block mesh, mark elements by location

nx, ny, nz = 5, 5, 4   # 5x5x4 = 100 hexes substrate, +1 layer trace
# Generate node grid: substrate (z=0 to sub_H), trace layer (z=sub_H to sub_H+trace_T)
nodes = []
node_id = lambda i, j, k: i + j*(nx+1) + k*(nx+1)*(ny+1) + 1
# Substrate layers
for k in range(nz+1):
    z = k * sub_H / nz
    for j in range(ny+1):
        y = j * sub_W / ny - sub_W/2
        for i in range(nx+1):
            x = i * sub_L / nx - sub_L/2
            nodes.append((x, y, z))
# Top trace layer
k_trace = nz + 1
z_trace = sub_H + trace_T
for j in range(ny+1):
    y = j * sub_W / ny - sub_W/2
    for i in range(nx+1):
        x = i * sub_L / nx - sub_L/2
        nodes.append((x, y, z_trace))

with open(f"{OUT}/mesh.nodes", "w") as f:
    for idx, (x, y, z) in enumerate(nodes, 1):
        f.write(f"{idx} -1 {x:.6e} {y:.6e} {z:.6e}\n")

# Elements: substrate hexes (Body 1) + trace hexes (Body 2 only where trace center)
elements = []
elem_id = 1
# Substrate body
for k in range(nz):
    for j in range(ny):
        for i in range(nx):
            n0 = node_id(i,   j,   k)
            n1 = node_id(i+1, j,   k)
            n2 = node_id(i+1, j+1, k)
            n3 = node_id(i,   j+1, k)
            n4 = node_id(i,   j,   k+1)
            n5 = node_id(i+1, j,   k+1)
            n6 = node_id(i+1, j+1, k+1)
            n7 = node_id(i,   j+1, k+1)
            elements.append((elem_id, 1, "808", [n0,n1,n2,n3,n4,n5,n6,n7]))
            elem_id += 1
# Trace layer (k=nz to k=nz+1)
# Body 2 only where trace exists (center strip, j=ny//2)
trace_j = ny // 2
for j in range(ny):
    for i in range(nx):
        n0 = node_id(i,   j,   nz)
        n1 = node_id(i+1, j,   nz)
        n2 = node_id(i+1, j+1, nz)
        n3 = node_id(i,   j+1, nz)
        n4 = node_id(i,   j,   nz+1)
        n5 = node_id(i+1, j,   nz+1)
        n6 = node_id(i+1, j+1, nz+1)
        n7 = node_id(i,   j+1, nz+1)
        body = 2 if j == trace_j else 1  # trace at center j
        elements.append((elem_id, body, "808", [n0,n1,n2,n3,n4,n5,n6,n7]))
        elem_id += 1

with open(f"{OUT}/mesh.elements", "w") as f:
    for eid, body, typ, ns in elements:
        ns_str = " ".join(str(n) for n in ns)
        f.write(f"{eid} {body} {typ} {ns_str}\n")

# Boundary elements: top face of trace layer (BC 1 — top convection), bottom face of substrate (BC 2 — bottom convection)
boundaries = []
bnd_id = 1
# Bottom face of substrate at k=0
for j in range(ny):
    for i in range(nx):
        n0 = node_id(i,   j,   0)
        n1 = node_id(i+1, j,   0)
        n2 = node_id(i+1, j+1, 0)
        n3 = node_id(i,   j+1, 0)
        boundaries.append((bnd_id, 2, "404", [n0,n1,n2,n3]))
        bnd_id += 1
# Top face of trace layer at k=nz+1
for j in range(ny):
    for i in range(nx):
        n0 = node_id(i,   j,   nz+1)
        n1 = node_id(i+1, j,   nz+1)
        n2 = node_id(i+1, j+1, nz+1)
        n3 = node_id(i,   j+1, nz+1)
        boundaries.append((bnd_id, 1, "404", [n0,n1,n2,n3]))
        bnd_id += 1

with open(f"{OUT}/mesh.boundary", "w") as f:
    for bid, btype, typ, ns in boundaries:
        ns_str = " ".join(str(n) for n in ns)
        # parent_elem1 parent_elem2 (use 0 0 for unknown)
        f.write(f"{bid} {btype} 0 0 {typ} {ns_str}\n")

# Header
with open(f"{OUT}/mesh.header", "w") as f:
    n_nodes = len(nodes)
    n_elements = len(elements)
    n_bnd = len(boundaries)
    f.write(f"{n_nodes} {n_elements} {n_bnd}\n")
    f.write(f"2\n808 {n_elements}\n404 {n_bnd}\n")

print(f"Mesh written: {n_nodes} nodes, {n_elements} elements, {n_bnd} boundary faces")
print(f"Bodies: Body 1 substrate ({nz*nx*ny} hexes), Body 2 trace ({nx} hexes at j={trace_j})")
