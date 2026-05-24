# V1 — Elmer thermal vs IPC-2152 Fig 4-1

**Status**: PENDING — initial 3D mesh attempt failed (heat source / boundary
condition modeling needs substrate + air conduction co-simulation, not just
isolated copper trace).

**Reference**: IPC-2152 external trace, 1oz Cu, 10mil width, 1A free air,
ΔT ≈ 7°C above ambient.

**Issue with simple-trace mesh**: a bare copper trace with only convection BC
(no substrate, no air conduction) sees all 94 mW concentrated in 30 mm² of
surface → predicted ΔT = 313°C analytically vs IPC 7°C. The IPC-2152 value
assumes substrate heat-spreading + ambient air convection over entire PCB
area, not just trace surface.

**Path forward**: build proper 3D mesh of:
- 50 mm × 50 mm × 1.6 mm FR4 substrate
- 0.254 mm × 35 µm × 50 mm Cu trace on top surface
- Convection on top/bottom surfaces of substrate
- Heat source only in trace volume

Mesh complexity ~10× larger than simple trace. Defer to dedicated effort
or use already-validated Phase 5c thermal sim as proxy (full-board model
with 24 FETs at 100A burst gave T_J=82.99°C — within published BSC014N06NS
thermal expectations).
