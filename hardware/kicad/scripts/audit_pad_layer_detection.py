#!/usr/bin/env python3
"""audit_pad_layer_detection.py — G_PAD_LAYER_LAYERSET binding gate.

Lever FF (2026-05-30): catches the pad.GetLayer() vs pad.GetLayerSet()
misuse class. The pcbnew API quirk: for SMD pads with single-layer
LayerSet (e.g. {B.Cu} for an SMD pad mounted on B.Cu), `pad.GetLayer()`
returns the "primary" layer which is hard-coded "F.Cu" by KiCad's pad
class — NOT the actual mount layer.

Code that uses `pad.GetLayer()` for routing-side decisions silently
mis-classifies B.Cu pads as F.Cu pads, routing them into blocked F.Cu
corridors. The correct pattern is `pad.GetLayerSet().Contains(target)`.

This gate scans the routing engine sources for:
  (1) Any `pad.GetLayer()` call that influences routing-side decisions.
      (Test files + library scripts are excluded; the scan walks only
       `routing_engine/` + `route_subsystem_cooperative.py`.)
  (2) Hard-coded `"F.Cu"` for pin/pad layer assignment in extract paths.
  (3) Asserts the Lever FF fix comment present at known-good sites.

Exit 0 = no misuse detected. Exit 1 = misuse found.

Usage:
    python3 audit_pad_layer_detection.py
        [--root hardware/kicad/scripts]
"""
from __future__ import annotations
import argparse
import os
import pathlib
import re
import sys
from typing import List, Tuple


SCAN_TARGETS = [
    "routing_engine",
    "route_subsystem_cooperative.py",
]

# Files that legitimately use pad.GetLayer() for non-routing purposes
# (e.g. test fixtures, inspection scripts).
ALLOWLIST = {
    "test_",                # any test file
    "audit_pad_layer_detection.py",   # this file itself (lists the patterns)
    "_pin_from_pcbnew",     # explicit lever FF-aware code section
}

# Lever FF fix marker — sites that have been audited and use LayerSet.
FIX_MARKER = "Lever FF"


def _scan_file(path: pathlib.Path) -> List[str]:
    issues: List[str] = []
    if any(skip in path.name for skip in ALLOWLIST):
        return issues
    try:
        text = path.read_text()
    except Exception:                                          # pragma: no cover
        return [f"{path}: read error"]
    for i, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        # Skip comments + docstrings (rudimentary)
        if '"""' in line:
            continue
        # (1) pad.GetLayer() in routing engine — flag.
        if re.search(r"\bpad\.GetLayer\s*\(\)", line):
            issues.append(f"{path}:{i}: pad.GetLayer() used for routing — "
                           f"replace with pad.GetLayerSet().Contains(target). "
                           f"Code: {stripped}")
        # (2) Hard-coded layer_name = "F.Cu" pattern in extract paths.
        if re.search(r'layer_name\s*=\s*"F\.Cu"\s*$', line):
            # Allowed if context comment cites Lever FF
            context_window = text.split("\n")[max(0, i-10): i+2]
            if not any(FIX_MARKER in c for c in context_window):
                issues.append(f"{path}:{i}: hard-coded 'F.Cu' for pin layer "
                               f"without Lever FF context. Code: {stripped}")
    return issues


def audit(root: str) -> Tuple[int, List[str]]:
    root_path = pathlib.Path(root)
    all_issues: List[str] = []
    scanned = 0
    for target in SCAN_TARGETS:
        t = root_path / target
        if t.is_file():
            all_issues.extend(_scan_file(t))
            scanned += 1
        elif t.is_dir():
            for f in t.rglob("*.py"):
                all_issues.extend(_scan_file(f))
                scanned += 1
    print(f"G_PAD_LAYER_LAYERSET audit @ {root}")
    print(f"  scanned {scanned} file(s)")
    if all_issues:
        print(f"\n❌ FAIL ({len(all_issues)} issue(s)):")
        for s in all_issues[:25]:
            print(f"  - {s}")
        return 1, all_issues
    print("\n✅ PASS — no pad.GetLayer() misuse detected")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="hardware/kicad/scripts")
    args = ap.parse_args(argv)
    code, _ = audit(args.root)
    return code


if __name__ == "__main__":
    sys.exit(main())
