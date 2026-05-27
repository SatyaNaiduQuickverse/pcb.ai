#!/usr/bin/env python3
"""audit_stackup_dielectric.py — G_M17 stackup-PRESENCE + dielectric-lock gate.

THE CLASS OF BUG THIS PREVENTS
------------------------------
The board carries the 10-copper-layer STACK (the (layers ...) block — checked by
G_M16) but had NO `(setup (stackup ...))` block. The F.Cu→In1.Cu = 0.10mm
prepreg — which the SW commutation loop-L verdict is LOAD-BEARING on (OQ-014,
STEP-6 0.1953nH/phase) — existed only as a human comment in a layer descriptor,
never as a real fabricable stackup definition. JLC would build a DEFAULT 1.6mm
10L dielectric split → the 0.10mm reference is NOT guaranteed → the loop-L
assumption silently breaks at fab.

G_M16 counts copper LAYERS. It says nothing about the DIELECTRIC between them.
This gate (G_M17) closes that: it FAILS if the board lacks a (stackup) block OR
if the F.Cu→In1.Cu dielectric ≠ 0.10mm (±0.005). Fixed by running
hardware/kicad/scripts/inject_stackup.py.

Per the independent audit 2026-05-27 + [[feedback-audit-coverage-not-count]]
(gate count is vanity, coverage is sanity) + [[feedback-root-cause-not-symptom]]
(inject_stackup.py = the root-cause fix; this gate = recurrence prevention).

WHAT IT CHECKS
--------------
1. (stackup ...) block present in the board.
2. First dielectric (F.Cu→In1.Cu prepreg) thickness == 0.10mm (±0.005).
3. (advisory) total copper+dielectric thickness in a sane 1.2-1.8mm window.

Exit 0 PASS, 1 FAIL, 2 usage / inert.

Usage:
  python3 audit_stackup_dielectric.py <board.kicad_pcb>
"""

import re
import sys
from pathlib import Path

# OQ-014 LOCK — docs/BOARD_INVARIANTS.md line 16.
F_CU_TO_IN1_MM = 0.10
TOL_MM = 0.005


def find_stackup_block(txt):
    """Return the (stackup ...) block substring, or None. Paren-counted."""
    j = txt.find("(stackup")
    if j < 0:
        return None
    depth = 0
    k = j
    while k < len(txt):
        if txt[k] == '(':
            depth += 1
        elif txt[k] == ')':
            depth -= 1
            if depth == 0:
                return txt[j:k + 1]
        k += 1
    return None


def first_dielectric_thickness(stackup_txt):
    """Extract thickness of 'dielectric 1' (the F.Cu→In1.Cu prepreg). Returns
    float mm, or None if not parseable."""
    # locate (layer "dielectric 1" ... (thickness X) ...)
    m = re.search(r'\(layer\s+"dielectric 1".*?\(thickness\s+([\d.]+)\)',
                  stackup_txt, re.DOTALL)
    if m:
        return float(m.group(1))
    return None


def all_dielectric_thicknesses(stackup_txt):
    """Return [(name, thk), ...] for every dielectric layer, in file order."""
    out = []
    for m in re.finditer(r'\(layer\s+"(dielectric \d+)".*?\(thickness\s+([\d.]+)\)',
                         stackup_txt, re.DOTALL):
        out.append((m.group(1), float(m.group(2))))
    return out


def copper_thicknesses(stackup_txt):
    """Return [thk, ...] for every copper layer (type 'copper')."""
    out = []
    for m in re.finditer(
            r'\(layer\s+"[^"]*\.Cu".*?\(type\s+"copper"\).*?\(thickness\s+([\d.]+)\)',
            stackup_txt, re.DOTALL):
        out.append(float(m.group(1)))
    return out


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {Path(__file__).name} <board.kicad_pcb>", file=sys.stderr)
        return 2

    pcb_path = Path(sys.argv[1])
    print("=== Stackup dielectric audit (G_M17) ===")
    if not pcb_path.exists():
        print(f"INFO: board not found ({pcb_path}) — gate inert")
        return 0

    txt = pcb_path.read_text()
    fails = []

    stackup = find_stackup_block(txt)
    if stackup is None:
        print(f"  ❌ board has NO (stackup ...) block")
        print(f"     The dielectric stack is undefined → JLC builds a default split →")
        print(f"     OQ-014 F.Cu→In1.Cu = 0.10mm loop-L reference is NOT guaranteed.")
        print(f"     FIX: python3 hardware/kicad/scripts/inject_stackup.py {pcb_path}")
        print(f"\nRESULT: FAIL — no stackup block")
        return 1

    print(f"  ✅ (stackup ...) block present")

    # F.Cu→In1.Cu (first dielectric) thickness lock
    d1 = first_dielectric_thickness(stackup)
    if d1 is None:
        fails.append("could not parse 'dielectric 1' (F.Cu→In1.Cu) thickness from stackup")
    else:
        ok = abs(d1 - F_CU_TO_IN1_MM) <= TOL_MM
        marker = "  ✅" if ok else "  ❌"
        print(f"{marker} F.Cu→In1.Cu (dielectric 1) = {d1}mm "
              f"(OQ-014 lock = {F_CU_TO_IN1_MM}mm ±{TOL_MM})")
        if not ok:
            fails.append(f"F.Cu→In1.Cu dielectric = {d1}mm ≠ {F_CU_TO_IN1_MM}mm "
                         f"(OQ-014 loop-L plane-reference LOCK)")

    # advisory: report the full dielectric stack + total thickness
    diels = all_dielectric_thicknesses(stackup)
    coppers = copper_thicknesses(stackup)
    print(f"  dielectric layers: {len(diels)}  copper layers: {len(coppers)}")
    if diels:
        print(f"     dielectric stack (mm): {[t for _, t in diels]}")
    total = sum(t for _, t in diels) + sum(coppers)
    print(f"  copper+dielectric total = {total:.3f}mm (sane window 1.2-1.8mm)")
    if total and not (1.2 <= total <= 1.8):
        fails.append(f"total copper+dielectric {total:.3f}mm outside sane 1.2-1.8mm window")

    if fails:
        print(f"\nRESULT: FAIL — {len(fails)} dielectric issue(s)")
        for f in fails:
            print(f"  {f}")
        return 1

    print(f"\nRESULT: PASS — stackup present + F.Cu→In1.Cu = {F_CU_TO_IN1_MM}mm "
          f"(OQ-014 loop-L reference fabricable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
