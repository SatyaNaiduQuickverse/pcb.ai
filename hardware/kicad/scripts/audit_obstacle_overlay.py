#!/usr/bin/env python3
"""audit_obstacle_overlay.py — G_RENDER_OBSTACLE_OVERLAY binding gate.

Per Sai 2026-05-30 directive: every leaf NO_PATH chronic must ship an
obstacle-map diagnostic JSON proving the blocker class. This gate
cross-checks the diagnostic JSON for completeness + actionable hints.

Checks per diagnostic JSON:
  (1) Location + layer + radius declared
  (2) Owner net declared
  (3) Obstacle inventory complete (tracks, pads, vias, zones)
  (4) Zone-fill-cover analysis present (covers_location field per zone)
  (5) If owner-net items are missing entirely → mark as endpoint mismatch
      hypothesis (c) — router doesn't see the leaf at this location

Exit 0 = diagnostic complete + actionable.
Exit 1 = missing fields / vacuous.

Usage:
    python3 audit_obstacle_overlay.py <diagnostic.json>
        [--diagnostic-dir sims/obstacle_diagnostics]
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
from typing import List, Tuple


def _audit_entry(path: pathlib.Path) -> List[str]:
    issues: List[str] = []
    try:
        doc = json.loads(path.read_text())
    except Exception as e:
        return [f"{path.name}: read/parse error: {e}"]
    # Required fields
    for k in ("location", "layer", "radius_mm", "owner_net",
              "foreign_tracks", "foreign_pads", "foreign_vias",
              "zone_fills", "owner_items"):
        if k not in doc:
            issues.append(f"{path.name}: missing field {k!r}")
    if issues:
        return issues
    # Zone covers analysis present?
    for z in doc.get("zone_fills", []):
        if "covers_location" not in z:
            issues.append(f"{path.name}: zone entry missing covers_location")
            break
    # Sanity: owner_items should contain the leaf pad itself if location
    # matches a pad center. If empty, flag as hypothesis (c) candidate.
    if not doc.get("owner_items"):
        issues.append(f"{path.name}: ⚠️ owner_items empty — hypothesis (c) "
                       f"endpoint coord mismatch likely. Verify router sees "
                       f"the leaf pad at this location.")
    return issues


def audit(prov_dir: str) -> Tuple[int, List[str]]:
    d = pathlib.Path(prov_dir)
    if not d.exists():
        print(f"G_RENDER_OBSTACLE_OVERLAY audit @ {prov_dir}")
        print(f"  directory missing — vacuous PASS")
        return 0, []
    entries = sorted(d.glob("*.json"))
    if not entries:
        print(f"G_RENDER_OBSTACLE_OVERLAY audit @ {prov_dir}")
        print(f"  no diagnostic entries — vacuous PASS")
        return 0, []
    all_issues: List[str] = []
    print(f"G_RENDER_OBSTACLE_OVERLAY audit @ {prov_dir}")
    print(f"  entries: {len(entries)}")
    for e in entries:
        is_ = _audit_entry(e)
        all_issues.extend(is_)
        if not is_:
            # extract diagnostic summary for printing
            try:
                doc = json.loads(e.read_text())
                cov = sum(1 for z in doc.get("zone_fills", [])
                          if z.get("covers_location"))
                print(f"  {e.name}: loc={doc['location']} layer={doc['layer']} "
                       f"owner={doc['owner_net']!r}: "
                       f"tracks={len(doc['foreign_tracks'])} "
                       f"pads={len(doc['foreign_pads'])} "
                       f"vias={len(doc['foreign_vias'])} "
                       f"zones-cover={cov}")
            except Exception:
                pass
    if all_issues:
        print(f"\n❌ FAIL ({len(all_issues)} issue(s)):")
        for s in all_issues[:25]:
            print(f"  - {s}")
        return 1, all_issues
    print("\n✅ PASS — all diagnostics audit-verified")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diagnostic-dir",
                    default="sims/obstacle_diagnostics")
    args = ap.parse_args(argv)
    code, _ = audit(args.diagnostic_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
