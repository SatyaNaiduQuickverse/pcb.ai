#!/usr/bin/env python3
"""build_mesh.py — Elmer 3D mesh for Phase 4-v3 CH1 thermal sim (option b).

Master-approved option (b), substrate-distributed model:
- Substrate-only mesh with a distributed (volumetric) heat source.
- T_substrate is sampled from the FEM at the FET XY positions; the junction
  temperature is then added analytically: T_J = T_substrate + P_FET × R_θJC.
- R_θJC = 1.0 K/W for BSC014N06NS PDFN-8 (datasheet).

Geometry (Phase 4-v3, 13mm-pitch CH1 zone):
  Substrate = FR4 block 35mm × 39mm × 1.6mm  (v2 used 35×32 — updated here).
  NX=70, NY=78, NZ=4 -> 0.5mm in XY. This uniform grid is appropriate for the
  option-b *distributed-heat* model: heat is spread volumetrically over the FET
  sub-region, so there are no point singularities at the pads and the 0.1mm
  graded-mesh-at-pads spec (from the dispatch) is NOT needed here — that spec
  belongs to an option-a discrete-FET model. Documented modeling choice.

Two bodies:
  Body 1 = passive FR4 spreader (no heat source).
  Body 2 = FET-cluster sub-region (the west strip where Q5..Q10 sit):
           x in [FET_X0, FET_X1] (4mm..13mm), full y, full z thickness.
           The volumetric heat source (Body Force) is applied here only.

Boundaries:
  BC 1 = top surface  (z = SUB_H) — Phase-7 heatsink, h = 15 W/m²K
  BC 2 = bottom surface (z = 0)    — natural convection, h = 5 W/m²K
"""
import os

OUT = "/home/novatics64/escworker/pcb.ai/sims/phase4v3/ch1_thermal/ch1_mesh"
os.makedirs(OUT, exist_ok=True)

# Substrate dimensions (m)
SUB_L, SUB_W, SUB_H = 0.035, 0.039, 0.0016   # x=35mm, y=39mm, z=1.6mm
NX, NY, NZ = 70, 78, 4                         # 0.5mm in XY, 0.4mm in Z

# FET-cluster sub-region in x (m). West strip where the 6 FETs sit (x 4..13mm),
# full y, full thickness. Q5/Q7/Q9 (HS, F.Cu) + Q6/Q8/Q10 (LS, B.Cu) at x=8.4mm.
FET_X0, FET_X1 = 0.004, 0.013

DX = SUB_L / NX
DY = SUB_W / NY
DZ = SUB_H / NZ

nodes = []
def add_node(x, y, z):
    nodes.append((x, y, z))
    return len(nodes)

node_idx = {}
for k in range(NZ + 1):
    z = k * DZ
    for j in range(NY + 1):
        y = j * DY
        for i in range(NX + 1):
            x = i * DX
            node_idx[(i, j, k)] = add_node(x, y, z)

elements = []
eid = 0
n_fet_elems = 0
elem_id = {}  # (i,j,k) -> bulk element id, for boundary parent references
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
            elem_id[(i, j, k)] = eid
            # element x-center decides body
            xc = (i + 0.5) * DX
            if FET_X0 <= xc <= FET_X1:
                body = 2
                n_fet_elems += 1
            else:
                body = 1
            elements.append((eid, body, "808", ns))

boundaries = []
bid = 0
# Bottom (k=0) — BC 2 (h=5 natural convection). Parent = element (i,j,0).
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, 0)],
            node_idx[(i+1, j, 0)],
            node_idx[(i+1, j+1, 0)],
            node_idx[(i, j+1, 0)],
        ]
        bid += 1
        boundaries.append((bid, 2, elem_id[(i, j, 0)], "404", ns))
# Top (k=NZ) — BC 1 (h=15 heatsink). Parent = element (i,j,NZ-1).
for j in range(NY):
    for i in range(NX):
        ns = [
            node_idx[(i, j, NZ)],
            node_idx[(i+1, j, NZ)],
            node_idx[(i+1, j+1, NZ)],
            node_idx[(i, j+1, NZ)],
        ]
        bid += 1
        boundaries.append((bid, 1, elem_id[(i, j, NZ-1)], "404", ns))

with open(f"{OUT}/mesh.nodes", "w") as f:
    for nid, (x, y, z) in enumerate(nodes, 1):
        f.write(f"{nid} -1 {x:.6e} {y:.6e} {z:.6e}\n")
with open(f"{OUT}/mesh.elements", "w") as f:
    for eid_, body, typ, ns in elements:
        f.write(f"{eid_} {body} {typ} {' '.join(str(n) for n in ns)}\n")
with open(f"{OUT}/mesh.boundary", "w") as f:
    # Elmer format: <bndElemId> <bcId> <parentElem1> <parentElem2> <type> <nodes...>
    # parentElem2 = 0 (exterior face has only one adjacent bulk element).
    for bid_, bc, parent, typ, ns in boundaries:
        f.write(f"{bid_} {bc} {parent} 0 {typ} {' '.join(str(n) for n in ns)}\n")
with open(f"{OUT}/mesh.header", "w") as f:
    f.write(f"{len(nodes)} {len(elements)} {len(boundaries)}\n")
    f.write("2\n808 {}\n404 {}\n".format(len(elements), len(boundaries)))

# FET-region volume (m³) for heat-density calculation
RHO_FR4 = 1850.0  # kg/m³ — Elmer Heat Source is SPECIFIC (W/kg); q_spec = q_vol/rho
fet_vol = n_fet_elems * DX * DY * DZ
print(f"Mesh: {len(nodes)} nodes, {len(elements)} hex elements, {len(boundaries)} bnd faces")
print(f"FET-region (body 2): {n_fet_elems} elements, volume = {fet_vol:.6e} m^3")
print(f"  x-range [{FET_X0*1e3:.1f},{FET_X1*1e3:.1f}]mm, full y [0,{SUB_W*1e3:.1f}]mm, z [0,{SUB_H*1e3:.1f}]mm")
# Elmer 'Heat Source' in a Body Force is SPECIFIC power (W/kg) and is multiplied by
# Density internally. So the .sif value must be q_vol / rho, NOT q_vol. Verified
# against an exact lumped+conduction analytic check (test_uniform2.sif).
for P, lbl in [(66.7, "100A continuous"), (144.5, "150A burst")]:
    q_vol = P / fet_vol
    q_spec = P / (fet_vol * RHO_FR4)
    print(f"  -> {lbl}: P={P}W  q_vol={q_vol:.6e} W/m^3  q_specific={q_spec:.6e} W/kg  <-- use this in .sif")
