#!/usr/bin/env python3
"""audit_meta_coverage.py — G_META1 audit-suite completeness check.

The class of bug this prevents:

  An audit script gets written + committed (e.g. verify_placement.py with
  bbox-overlap from Phase 4-v1 Task #47). It works. Months later a phase
  migration happens (v1 → v2 → v3). The new master_pre_merge.sh references
  a curated subset of audits. The orphan never runs. Years later: Sai eye-
  catches a class of defect the orphaned audit was designed to catch.

  Cost: weeks of phantom "55 gates green" while a real bug ships.

This meta-audit scans `hardware/kicad/scripts/audit_*.py` + `verify_*.py`,
extracts each scriptname, and verifies it is referenced in
`hardware/kicad/scripts/master_pre_merge.sh`.

A script may be EXPLICITLY DEFERRED via `docs/AUDIT_DEFERRED.txt` with a
required reason (e.g., "diff_pair_z0 = Phase 5 routing — wire at routing PR").
No silent omissions.

Exit 0 = PASS, 1 = FAIL with list of orphans.

Per [[feedback-systemic-rule-enforcement]] + Sai 2026-05-26 mandate after
bbox-overlap catch: the audit suite gets its own audits.
"""
import os, re, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
PRE_MERGE = os.path.join(SCRIPT_DIR, "master_pre_merge.sh")
DEFERRED_LIST = os.path.join(REPO, "docs", "AUDIT_DEFERRED.txt")

def load_deferred():
    """{scriptname: reason} for explicitly-deferred audits."""
    d = {}
    if os.path.exists(DEFERRED_LIST):
        for ln in open(DEFERRED_LIST):
            ln = ln.split("#", 1)[0].strip()
            if not ln: continue
            if "=" not in ln: continue
            name, reason = ln.split("=", 1)
            d[name.strip()] = reason.strip()
    return d

def main():
    all_scripts = sorted(
        os.path.basename(f) for f in os.listdir(SCRIPT_DIR)
        if (f.startswith("audit_") or f.startswith("verify_")) and f.endswith(".py")
    )
    # Exclude this meta-audit itself + any utility helpers
    SELF = "audit_meta_coverage.py"
    all_scripts = [s for s in all_scripts if s != SELF]

    pm_text = open(PRE_MERGE).read()
    wired = set(re.findall(r'(audit_[a-z0-9_]+\.py|verify_[a-z0-9_]+\.py)', pm_text))
    deferred = load_deferred()

    orphans = []
    deferred_used = []
    for s in all_scripts:
        if s in wired:
            continue
        if s in deferred:
            deferred_used.append((s, deferred[s])); continue
        orphans.append(s)

    print("=" * 70)
    print(f"audit_meta_coverage.py G_META1 — {len(all_scripts)} audit scripts total")
    print("=" * 70)
    print(f"  Wired into master_pre_merge.sh: {len([s for s in all_scripts if s in wired])}")
    print(f"  Explicitly deferred:            {len(deferred_used)}")
    print(f"  ORPHANED (silent skip):         {len(orphans)}")

    if deferred_used:
        print()
        print("  Deferred (explicit, in docs/AUDIT_DEFERRED.txt):")
        for s, reason in deferred_used:
            print(f"    {s}  →  {reason}")

    if orphans:
        print()
        print("  ❌ ORPHAN audits (script exists but NEVER runs):")
        for s in orphans:
            print(f"    {s}")
        print()
        print(f"  FAIL — {len(orphans)} orphan audit(s).")
        print(f"  Fix: wire each into master_pre_merge.sh as BLOCKING (preferred),")
        print(f"  OR add to docs/AUDIT_DEFERRED.txt with reason if migration timing requires.")
        return 1

    print()
    print("  ✅ PASS — every audit script is either wired or explicitly deferred.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
