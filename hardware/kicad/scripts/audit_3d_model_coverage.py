#!/usr/bin/env python3
"""audit_3d_model_coverage.py — verify 3D model paths resolve for every fp.

For each footprint with a model3D reference, check whether the resolved file
exists on disk. Substitutes KICAD9_3DMODEL_DIR env var.

Exit 0 PASS (all models resolve); exit 1 FAIL (any missing). Print summary +
missing list.

Run: KICAD9_3DMODEL_DIR=/path/to/3dmodels python3 audit_3d_model_coverage.py <board.kicad_pcb>
"""
import os
import re
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: audit_3d_model_coverage.py <board.kicad_pcb>")
    pcb_path = sys.argv[1]
    if not os.path.exists(pcb_path):
        sys.exit(f"PCB not found: {pcb_path}")

    env_3d = os.environ.get('KICAD9_3DMODEL_DIR', '')
    if not env_3d:
        print("WARNING: KICAD9_3DMODEL_DIR env var not set; using empty (relative paths only).")

    with open(pcb_path) as f:
        text = f.read()

    # All model "..." references in the kicad_pcb file
    models = re.findall(r'model\s+"([^"]+)"', text)
    unique = sorted(set(models))
    print(f"Total model refs in PCB: {len(models)}")
    print(f"Unique model paths: {len(unique)}")

    missing = []
    present = []
    for m in unique:
        resolved = m.replace('${KICAD9_3DMODEL_DIR}', env_3d)
        # If still contains ${...} → unset env var still in path, treat as missing
        if '${' in resolved:
            missing.append((m, resolved, 'unresolved-env-var'))
            continue
        if os.path.isfile(resolved):
            present.append(m)
        else:
            missing.append((m, resolved, 'file-not-found'))

    print(f"\n  PRESENT: {len(present)} / {len(unique)} unique paths")
    print(f"  MISSING: {len(missing)} / {len(unique)} unique paths")
    if missing:
        print(f"\nMissing model paths:")
        for orig, resolved, reason in missing:
            print(f"  [{reason}]")
            print(f"    ref:      {orig}")
            print(f"    resolved: {resolved}")

    # Count how many FOOTPRINTS use a missing model (one model used N times)
    miss_set = {m[0] for m in missing}
    fp_count_using_missing = sum(1 for m in models if m in miss_set)
    print(f"\n  Footprints using a MISSING 3D model: {fp_count_using_missing} / {len(models)}")

    if missing:
        sys.exit(1)
    print("\nPASS — all 3D models resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
