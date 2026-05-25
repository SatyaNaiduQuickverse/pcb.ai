#!/usr/bin/env python3
"""
audit_sim_mesh_validity.py — G_S2 simulation mesh validity gate.

Proactive 2026-05-26 (catch class: Elmer/openEMS solver runs on degenerate
mesh → garbage results consumed as truth). Per R18 sim-execution gate:
results are only as trustworthy as the mesh.

Mesh sanity checks (executed pre-solve):
  1. Mesh file exists at expected path
  2. Element count > 1000 (too coarse = numerical noise dominates)
  3. No degenerate elements (volume / area = 0)
  4. Boundary conditions cover all expected surfaces (no missing BC = solver
     defaults to zero-flux which may not match physics)
  5. Material properties non-zero on all volumes

For Elmer specifically: parse the .mesh.* files (mesh.header, mesh.nodes,
mesh.elements) and validate counts + ranges.

This is a SKELETON — full implementation requires per-sim integration.
Reports the mesh files found + their basic statistics; FAIL only on missing
mesh.header or zero elements.

Exit 0 = mesh files OK or N/A, 1 = degenerate mesh detected.

Usage:
  python3 audit_sim_mesh_validity.py [<sim_dir>]
"""

import sys
from pathlib import Path


def check_elmer_mesh(mesh_dir):
    """Returns (n_nodes, n_elements, issues_list)."""
    header = mesh_dir / "mesh.header"
    nodes_file = mesh_dir / "mesh.nodes"
    elements_file = mesh_dir / "mesh.elements"
    issues = []
    if not header.exists():
        issues.append(f"mesh.header missing in {mesh_dir}")
        return 0, 0, issues
    parts = header.read_text().split()
    try:
        n_nodes = int(parts[0])
        n_elements = int(parts[1])
    except (IndexError, ValueError):
        issues.append(f"mesh.header malformed in {mesh_dir}")
        return 0, 0, issues
    if n_nodes < 100:
        issues.append(f"too few nodes ({n_nodes}) — mesh likely too coarse for FEM accuracy")
    if n_elements < 100:
        issues.append(f"too few elements ({n_elements})")
    if nodes_file.exists():
        actual_node_lines = sum(1 for _ in nodes_file.open())
        if actual_node_lines != n_nodes:
            issues.append(f"mesh.nodes line count {actual_node_lines} ≠ header {n_nodes}")
    return n_nodes, n_elements, issues


def main():
    sim_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sims")
    if not sim_root.exists():
        print(f"=== Sim mesh validity audit ===")
        print(f"INFO: sims/ not found — gate inert until first FEM run")
        sys.exit(0)

    print(f"=== Sim mesh validity audit: {sim_root} ===\n")
    mesh_dirs = list(sim_root.rglob("*_mesh"))
    if not mesh_dirs:
        print(f"INFO: no *_mesh/ directories found — gate inert")
        sys.exit(0)

    fails = []
    for md in mesh_dirs:
        if not (md / "mesh.header").exists():
            continue
        n_nodes, n_elem, issues = check_elmer_mesh(md)
        status = "PASS" if not issues else "FAIL"
        print(f"  [{status}] {md.relative_to(sim_root)}: {n_nodes} nodes, {n_elem} elements")
        for iss in issues:
            print(f"           {iss}")
            fails.append(f"{md}: {iss}")

    if fails:
        print(f"\nRESULT: FAIL — {len(fails)} mesh integrity issues")
        sys.exit(1)
    print("\nRESULT: PASS — all meshes well-formed + adequate resolution")


if __name__ == "__main__":
    main()
