#!/usr/bin/env python3
"""audit_ripup_cascade_depth.py — G_J2 (R37 enforcement).

R37: Any targeted-ripup chain capped at depth ≤ 2. The 6-step algorithm
explicitly allows depth=2 (rip foreigners → route N → re-route a ripped
foreigner X; if X's re-route ITSELF needs a rip Z, allowed ONCE). Beyond
that = unbounded cascade, ABORT.

Algorithm:
  1. Load all provenance entries.
  2. For each COMMITTED entry, read its declared cascade_depth.
  3. FAIL if any committed entry has cascade_depth > 2.
  4. Additionally: build a cross-entry chain — if entry A ripped net X AND
     entry B has blocked_net=X (so B is the re-route of X triggered by A),
     verify B.cascade_depth == A.cascade_depth + 1 AND B.cascade_depth ≤ 2.
     A chain depth that exceeds 2 even across entries = FAIL.

PASS: every committed entry has cascade_depth ≤ 2; cross-entry chains
respect the cap.
FAIL: any committed entry exceeds 2; any chain exceeds 2.

Vacuous-PASS: zero entries = PASS.

Per docs/RULES_MANIFEST.md R37; CH1 30/30 lever J 2026-05-28.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import targeted_ripup as TR  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CASCADE_CAP = 2


def _chain_depths(entries):
    """For each committed entry, compute the EFFECTIVE chain depth by walking
    the rip-edge graph backwards.

    rip_edge from A → B exists when B's blocked_net is in A's conflict_set
    (i.e. A ripped some foreigner whose re-route is captured by B). Then
    chain_depth(B) = max(A.cascade_depth, chain_depth(A) + 1) — i.e. an
    entry's effective depth is at least its own declared depth, and at
    least one more than the depth of whichever entry triggered it.
    """
    # Build reverse-edge map: blocked_net -> [entries whose conflict_set
    # ripped this net] (these are the parents that triggered this re-route).
    parents_by_blocked = {}
    for a in entries:
        if not a.committed:
            continue
        for ripped in a.conflict_set:
            parents_by_blocked.setdefault(ripped, []).append(a)
    # Memoised chain depth (entry id → int)
    memo = {}
    def depth_of(e):
        key = id(e)
        if key in memo:
            return memo[key]
        own = int(e.cascade_depth or 0)
        parents = parents_by_blocked.get(e.blocked_net, [])
        if not parents:
            memo[key] = own
            return own
        # Take the max of: declared own, or parent_chain + 1
        best = own
        for p in parents:
            if p is e:
                continue
            best = max(best, depth_of(p) + 1)
        memo[key] = best
        return best
    return {id(e): depth_of(e) for e in entries if e.committed}


def audit(repo_root: Path = REPO_ROOT, verbose: bool = True) -> int:
    entries = TR.load_provenance(repo_root)
    if not entries:
        if verbose:
            print("audit_ripup_cascade_depth G_J2 — 0 entries (vacuous PASS).")
        return 0

    if verbose:
        print(f"audit_ripup_cascade_depth G_J2 — {len(entries)} provenance "
              f"entry(ies), cap depth ≤ {CASCADE_CAP}")

    bad = []
    # Self-declared depth check
    for e in entries:
        if not e.committed:
            continue
        if int(e.cascade_depth or 0) > CASCADE_CAP:
            bad.append((e, f"declared cascade_depth={e.cascade_depth} > "
                          f"{CASCADE_CAP}"))

    # Cross-entry chain-depth check
    chains = _chain_depths(entries)
    for e in entries:
        if not e.committed:
            continue
        d = chains.get(id(e), 0)
        if d > CASCADE_CAP:
            bad.append((e, f"effective chain_depth={d} > {CASCADE_CAP} "
                          "(traced via rip-edge graph)"))

    if verbose:
        for e, msg in bad:
            print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}: {msg}")

    if bad:
        if verbose:
            print(f"\nG_J2 FAIL: {len(bad)} cascade-depth violation(s) "
                  f"(R37 cap = {CASCADE_CAP}).")
        return 1
    if verbose:
        max_seen = max((chains.get(id(e), 0) for e in entries if e.committed),
                       default=0)
        print(f"\nG_J2 PASS: all committed entries have effective "
              f"chain_depth ≤ {CASCADE_CAP} (max observed = {max_seen}).")
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
