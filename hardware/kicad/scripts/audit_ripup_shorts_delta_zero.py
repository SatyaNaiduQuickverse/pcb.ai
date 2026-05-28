#!/usr/bin/env python3
"""audit_ripup_shorts_delta_zero.py — G_J5 (R-J5 shorts-gate enforcement).

The v6/v7/F/I shorts-gate semantics are PRESERVED through the targeted-
ripup capability: every targeted-ripup attempt records `shorts_pre`
(SHORTS count on the canonical board before the attempt) and `shorts_post`
(after the atomic commit). delta = shorts_post - shorts_pre MUST be ≤ 0;
any delta > 0 means the targeted ripup introduced a net-new short and
should have been rolled back (or the rollback failed).

Algorithm:
  1. Load all provenance entries.
  2. For each COMMITTED entry, compute delta = shorts_post - shorts_pre.
  3. FAIL if any delta > 0.
  4. Additionally: for any ROLLED-BACK entry whose `rollback_reason` cites
     "shorts" (the router invokes the shorts-gate as a rollback trigger),
     verify the entry STILL records shorts_pre/shorts_post — a shorts-
     triggered rollback that doesn't record the shorts numbers is opaque
     (the audit cannot independently verify the rollback was warranted).

PASS: every committed entry has shorts_post ≤ shorts_pre; every shorts-
rolled-back entry has both shorts_pre and shorts_post recorded.
FAIL: any committed entry adds shorts; any shorts-rolled-back entry
hides the numbers.

Vacuous-PASS: zero entries.

Per docs/RULES_MANIFEST.md R-J5; CH1 30/30 lever J 2026-05-28.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import targeted_ripup as TR  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent.parent.parent


def audit(repo_root: Path = REPO_ROOT, verbose: bool = True) -> int:
    entries = TR.load_provenance(repo_root)
    if not entries:
        if verbose:
            print("audit_ripup_shorts_delta_zero G_J5 — 0 entries (vacuous PASS).")
        return 0

    if verbose:
        print(f"audit_ripup_shorts_delta_zero G_J5 — {len(entries)} entry(ies)")

    bad = []
    for e in entries:
        if e.committed:
            delta = int(e.shorts_post or 0) - int(e.shorts_pre or 0)
            if delta > 0:
                bad.append((e, f"committed with shorts_pre={e.shorts_pre} "
                              f"shorts_post={e.shorts_post} delta={delta} > 0 "
                              "(shorts-gate semantics violated)"))
        else:
            # If rollback cites shorts, the numbers must be present
            if "short" in e.rollback_reason.lower():
                if e.shorts_pre is None or e.shorts_post is None:
                    bad.append((e, f"shorts-rolled-back but shorts_pre/post "
                                  "missing — cannot verify rollback was "
                                  "warranted"))

    if verbose:
        for e, msg in bad:
            print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}: {msg}")

    if bad:
        if verbose:
            print(f"\nG_J5 FAIL: {len(bad)} shorts-gate violation(s) "
                  "(R-J5 / shorts-delta-zero).")
        return 1
    if verbose:
        n_commit = sum(1 for e in entries if e.committed)
        print(f"\nG_J5 PASS: {n_commit} committed entry(ies); all have "
              "shorts_post ≤ shorts_pre.")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    return audit(root, verbose=not args.quiet)


if __name__ == "__main__":
    sys.exit(main())
