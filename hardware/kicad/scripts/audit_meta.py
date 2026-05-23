#!/usr/bin/env python3
"""audit_meta.py — meta-check that RULES_MANIFEST.md is internally consistent
with the actual audit + fix scripts.

Per Sai 2026-05-24 systemic directive: "put guidelines in place... change the
system in such way to prevent that... for rest of our rules.. redo whatever
needs to be done".

Master 2026-05-24 Gap #6: this is the 3rd artifact for every rule — meta-fence
that prevents silent regression of named-but-not-implemented gates.

What it does:
  1. Reads docs/RULES_MANIFEST.md
  2. For each row, extracts named audit-gate function (`check_*`) + fix script
  3. Greps both audit_layout_compliance.py + audit_routing.py for the function
  4. ls's the fix script path
  5. Fails with exit 1 if ANY rule has GAP (named artifact missing on disk)

Master runs this BEFORE every PR merge. Per [[feedback-codify-not-patch]]:
no rule can stay 'declared but not implemented'.

Run: python3 hardware/kicad/scripts/audit_meta.py
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent.parent.parent
MANIFEST = REPO / "docs/RULES_MANIFEST.md"
AUDIT_LAYOUT = REPO / "hardware/kicad/scripts/audit_layout_compliance.py"
AUDIT_ROUTING = REPO / "hardware/kicad/scripts/audit_routing.py"
SCRIPTS_DIR = REPO / "hardware/kicad/scripts"


def collect_audit_functions():
    """Return set of `check_*` function names defined in both audit scripts."""
    fns = set()
    for path in (AUDIT_LAYOUT, AUDIT_ROUTING):
        if not path.exists():
            continue
        txt = path.read_text()
        for m in re.finditer(r'^def (check_\w+)\(', txt, re.MULTILINE):
            fns.add(m.group(1))
    return fns


def collect_scripts():
    """Return set of script filenames in hardware/kicad/scripts/ + parent dir
    (e.g., setup_board.py lives at hardware/kicad/ not scripts/)."""
    out = set()
    if SCRIPTS_DIR.exists():
        out.update(p.name for p in SCRIPTS_DIR.glob("*.py"))
    parent = SCRIPTS_DIR.parent
    if parent.exists():
        out.update(p.name for p in parent.glob("*.py"))
    return out


def parse_manifest():
    """Extract (rule_id, function_or_script_names) tuples from manifest tables.
    Looks for backtick-wrapped names like `check_foo()` or `fix_bar.py`."""
    if not MANIFEST.exists():
        print(f"FATAL: manifest not found at {MANIFEST}", file=sys.stderr)
        sys.exit(2)
    txt = MANIFEST.read_text()
    # Find all `check_*` function references
    fn_refs = set(re.findall(r'`(check_\w+)\(\)`', txt))
    # Find all script references (e.g., `fix_tp_spacing.py`, `place_fiducials.py`)
    script_refs = set(re.findall(r'`((?:fix|place|flip|route|anchor|verify|setup|audit|post|export)_\w+\.py)`', txt))
    return fn_refs, script_refs


def main():
    print(f"audit_meta: reading {MANIFEST}")
    fn_refs, script_refs = parse_manifest()
    audit_fns = collect_audit_functions()
    scripts = collect_scripts()

    print(f"  Manifest names: {len(fn_refs)} audit functions, {len(script_refs)} fix/place scripts")
    print(f"  On disk: {len(audit_fns)} audit functions, {len(scripts)} scripts in {SCRIPTS_DIR.name}/")

    missing_fns = fn_refs - audit_fns
    missing_scripts = script_refs - scripts
    orphan_fns = audit_fns - fn_refs
    orphan_scripts = scripts - script_refs

    print("\n=== MISSING ARTIFACTS (declared in manifest, not on disk) ===")
    if missing_fns:
        print(f"  audit functions MISSING ({len(missing_fns)}):")
        for f in sorted(missing_fns):
            print(f"    {f}()")
    if missing_scripts:
        print(f"  fix/place scripts MISSING ({len(missing_scripts)}):")
        for s in sorted(missing_scripts):
            print(f"    {s}")
    if not (missing_fns or missing_scripts):
        print("  none ✓")

    print("\n=== ORPHANS (on disk, not in manifest) ===")
    if orphan_fns:
        print(f"  audit functions not in manifest ({len(orphan_fns)}):")
        for f in sorted(orphan_fns):
            print(f"    {f}()")
    if orphan_scripts:
        print(f"  scripts not in manifest ({len(orphan_scripts)}):")
        for s in sorted(orphan_scripts):
            print(f"    {s}")
    if not (orphan_fns or orphan_scripts):
        print("  none ✓")

    if missing_fns or missing_scripts:
        print("\n❌ MANIFEST INTEGRITY VIOLATION")
        print("   At least one rule declares an artifact (function or script) that doesn't exist.")
        print("   Either add the artifact, or remove the manifest reference if obsolete.")
        return 1
    print("\n✅ All manifest-declared audit functions + fix scripts are present on disk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
