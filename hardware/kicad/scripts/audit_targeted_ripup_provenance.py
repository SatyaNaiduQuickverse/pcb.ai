#!/usr/bin/env python3
"""audit_targeted_ripup_provenance.py — G_J1 (R36 enforcement).

R36: Every targeted-ripup commit MUST log {blocked_net, conflict_set,
re-route mapping}. A commit without provenance silently breaks the
audit chain — G_J1 catches this.

Algorithm:
  1. Scan `sims/routing_provenance/targeted_ripup/*.json`.
  2. For each entry, verify SCHEMA + REQUIRED FIELDS:
       - blocked_net non-empty
       - conflict_set is a tuple (possibly empty if rolled back)
       - rerouted is a dict
       - timestamp_iso non-empty
       - shorts_pre / shorts_post present (R-J5 inputs)
  3. For COMMITTED entries (committed=True), additionally require:
       - conflict_set non-empty (a committed ripup MUST have ripped >=1 net)
       - rerouted covers EVERY conflict-set net (the re-route mapping must
         explain where each ripped foreigner ended up)
       - each rerouted entry has a "path" or "summary" field (provenance,
         not just `True`)
  4. ROLLED-BACK entries (committed=False) MUST have a non-empty
     rollback_reason — a rolled-back attempt without a reason is silent
     abandonment, the very thing R36 prevents.

PASS: every entry has all required fields present AND consistent.
FAIL: any entry is missing a required field, OR a committed entry has
      conflict_set ≠ rerouted keys, OR a rolled-back entry has no reason.

Vacuous-PASS: zero entries (no targeted-ripup ever attempted) is PASS —
this matches the existing audit pattern (e.g. G_HDI_VIA_IN_PAD vacuous
passes on boards without HDI vias).

Per docs/RULES_MANIFEST.md R36; CH1 30/30 lever J 2026-05-28.
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
            print("audit_targeted_ripup_provenance G_J1 — 0 entries (vacuous PASS).")
            print("  (no targeted-ripup attempted on this commit — fine; the "
                  "router only writes entries when the targeted path is taken)")
        return 0

    if verbose:
        print(f"audit_targeted_ripup_provenance G_J1 — {len(entries)} provenance entry(ies)")

    bad = []
    for e in entries:
        problems = []
        if e.schema_version < 1:
            problems.append(f"schema_version={e.schema_version} "
                            "(< 1 = parse error or malformed JSON)")
        if not e.blocked_net:
            problems.append("blocked_net missing/empty")
        if not e.timestamp_iso:
            problems.append("timestamp_iso missing/empty")
        if not isinstance(e.conflict_set, tuple):
            problems.append(f"conflict_set wrong type: {type(e.conflict_set).__name__}")
        if not isinstance(e.rerouted, dict):
            problems.append(f"rerouted wrong type: {type(e.rerouted).__name__}")
        # Shorts gate (R-J5) inputs must be present
        if not isinstance(e.shorts_pre, int):
            problems.append("shorts_pre missing or non-int")
        if not isinstance(e.shorts_post, int):
            problems.append("shorts_post missing or non-int")

        if e.committed:
            # Committed ripup MUST have ripped >=1 net and explained each one.
            if not e.conflict_set:
                problems.append("committed=True with EMPTY conflict_set "
                                "(committed targeted ripup must rip ≥1 net)")
            ripped = set(e.conflict_set)
            mapped = set(e.rerouted.keys())
            missing_in_rerouted = ripped - mapped
            if missing_in_rerouted:
                problems.append(f"rerouted missing entries for ripped nets: "
                                f"{sorted(missing_in_rerouted)}")
            extra_in_rerouted = mapped - ripped
            if extra_in_rerouted:
                problems.append(f"rerouted has entries for non-ripped nets: "
                                f"{sorted(extra_in_rerouted)}")
            # Each rerouted entry must carry provenance (path or summary), not
            # just `True`.
            for nname, info in e.rerouted.items():
                if not isinstance(info, dict):
                    problems.append(f"rerouted[{nname}] is not a dict")
                    continue
                if not any(k in info for k in ("path", "summary", "length_mm")):
                    problems.append(f"rerouted[{nname}] has no path/"
                                    "summary/length_mm — no provenance")
        else:
            # Rolled-back attempt must explain WHY.
            if not e.rollback_reason:
                problems.append("committed=False with EMPTY rollback_reason "
                                "(rollback must be explained, not silent)")

        if problems:
            bad.append((e, problems))

    if verbose:
        for e, problems in bad:
            print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}:")
            for p in problems:
                print(f"     - {p}")

    if bad:
        if verbose:
            print(f"\nG_J1 FAIL: {len(bad)} provenance entry(ies) with problems "
                  f"(R36 violation).")
        return 1
    if verbose:
        print(f"\nG_J1 PASS: all {len(entries)} provenance entry(ies) have "
              "complete required fields.")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=None,
                    help="repo root (default: auto-detected)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    return audit(root, verbose=not args.quiet)


if __name__ == "__main__":
    sys.exit(main())
