#!/usr/bin/env python3
"""
audit_fos_cap_voltage.py — G_FoS3 capacitor voltage derating gate.

Proactive 2026-05-26 (Sai FoS mandate). Industry-standard derating:
  Electrolytic / Polymer: V_rated ≥ V_max × 1.4 (40% margin, JEDEC reliability)
  Ceramic X7R / X5R:      V_rated ≥ V_max × 1.5 (Class II caps lose 50%+ C
                          at rated V — derate by 1.5× to keep C accurate)
  Ceramic C0G / NP0:      V_rated ≥ V_max × 1.1 (Class I, no V coefficient)

Reads docs/PHASE4V3_BOM.yaml (TODO — not yet populated; gate runs inert):
  components:
    C1:
      part: PCH1V151MCL1GS
      v_rated: 35
      type: polymer
      v_max_on_net: 25.2   # 6S nominal
      v_max_burst: 27.0    # 6S × 1.07 charge ceiling

If BOM file missing: SKIP cleanly with note.

Exit 0 = all PASS or SKIP, 1 = any FAIL.

Usage:
  python3 audit_fos_cap_voltage.py [bom.yaml]
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed")
    sys.exit(1)


FOS_BY_TYPE = {
    "polymer":     1.4,
    "electrolytic": 1.4,
    "ceramic_x7r": 1.5,
    "ceramic_x5r": 1.5,
    "ceramic_c0g": 1.1,
    "ceramic_np0": 1.1,
    "tantalum":    1.5,  # tantalum is unforgiving — extra margin
}


def main():
    bom_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/PHASE4V3_BOM.yaml")
    if not bom_path.exists():
        print(f"=== Cap voltage FoS audit ===")
        print(f"INFO: {bom_path} not found — gate inert until BOM populated with v_rated metadata")
        sys.exit(0)

    bom = yaml.safe_load(bom_path.read_text()) or {}
    comps = (bom.get("components") or {})

    print(f"=== Capacitor voltage FoS audit: {bom_path.name} ===")
    print(f"Derating per type: polymer 1.4×, X7R 1.5×, C0G 1.1×\n")

    fails = []
    audited = 0
    for ref, info in comps.items():
        if not ref.startswith(("C", "CP")):
            continue
        v_rated = info.get("v_rated")
        v_max = max(info.get("v_max_on_net", 0), info.get("v_max_burst", 0))
        ctype = (info.get("type") or "polymer").lower()
        if v_rated is None or v_max == 0:
            continue
        audited += 1
        fos = FOS_BY_TYPE.get(ctype, 1.4)
        required = v_max * fos
        if v_rated < required:
            fails.append(f"  [FAIL] {ref} ({ctype}): V_rated={v_rated}V < required {required:.1f}V "
                         f"(V_max {v_max}V × {fos} FoS)")
        else:
            print(f"  [PASS] {ref} ({ctype}): {v_rated}V ≥ {required:.1f}V")

    print()
    print(f"Audited {audited} caps with v_rated metadata\n")
    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} cap voltage derating violations")
        sys.exit(1)
    if audited == 0:
        print("RESULT: SKIP — no caps have v_rated metadata yet (BOM annotation pending)")
        sys.exit(0)
    print("RESULT: PASS — all caps meet voltage derating FoS")


if __name__ == "__main__":
    main()
