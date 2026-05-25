#!/usr/bin/env python3
"""
audit_bom_lcsc.py — G_M4 BOM LCSC stock + part-number presence gate.

Proactive 2026-05-26 (catch class: BOM ships with parts not stocked at
JLC SMT, triggers rejection / 5-day rework cycle). Every BOM line must:
  1. Have an LCSC C-number (Cxxxxxxx format) part identifier
  2. Have stock ≥ MIN_STOCK in LCSC inventory (JLC SMT pulls from LCSC)

Reads docs/PHASE4V3_BOM.yaml (per-component):
  components:
    C1:
      lcsc: C2861274     # PCH1V151MCL1GS
      lcsc_stock: 12500
      lcsc_extended: false  # "basic" lib parts cheaper to assemble

Inert until BOM populated. Final check pre-fab.

Exit 0 = all PASS or SKIP, 1 = any out-of-stock or missing LCSC.

Usage:
  python3 audit_bom_lcsc.py [bom.yaml]
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed"); sys.exit(1)


MIN_STOCK = 100   # below this = supply risk for production run
WARN_STOCK = 1000


def main():
    bom_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/PHASE4V3_BOM.yaml")
    if not bom_path.exists():
        print(f"=== BOM LCSC stock audit ===")
        print(f"INFO: {bom_path} not found — gate inert until BOM populated with lcsc metadata")
        sys.exit(0)

    bom = yaml.safe_load(bom_path.read_text()) or {}
    comps = (bom.get("components") or {})

    print(f"=== BOM LCSC stock audit: {bom_path.name} ===")
    print(f"Stock floor: {MIN_STOCK} units (warn at {WARN_STOCK})\n")

    fails = []
    warns = []
    audited = 0
    for ref, info in comps.items():
        lcsc = info.get("lcsc")
        stock = info.get("lcsc_stock")
        extended = info.get("lcsc_extended", False)
        if lcsc is None:
            fails.append(f"  [FAIL] {ref}: no LCSC part number — cannot assemble at JLC")
            continue
        if not str(lcsc).startswith("C"):
            fails.append(f"  [FAIL] {ref}: lcsc='{lcsc}' invalid (expect Cxxxxxxx)")
            continue
        audited += 1
        if stock is None:
            warns.append(f"  [WARN] {ref} ({lcsc}): no lcsc_stock — update before fab")
        elif stock < MIN_STOCK:
            fails.append(f"  [FAIL] {ref} ({lcsc}): stock {stock} < min {MIN_STOCK}")
        elif stock < WARN_STOCK:
            warns.append(f"  [WARN] {ref} ({lcsc}): stock {stock} < {WARN_STOCK} (procurement risk)")
        elif extended:
            warns.append(f"  [WARN] {ref} ({lcsc}): EXTENDED part — added JLC assembly cost (~$3 setup + line item)")

    print(f"Audited {audited} BOM lines\n")
    for w in warns[:10]:
        print(w)
    if warns and len(warns) > 10:
        print(f"  ... +{len(warns)-10} more")

    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} BOM LCSC violations")
        sys.exit(1)
    if audited == 0:
        print("RESULT: SKIP — no BOM entries have lcsc metadata yet")
        sys.exit(0)
    print("RESULT: PASS — all BOM lines have LCSC part + adequate stock")


if __name__ == "__main__":
    main()
