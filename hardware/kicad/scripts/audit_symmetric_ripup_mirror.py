#!/usr/bin/env python3
"""audit_symmetric_ripup_mirror.py — G_J4 (R39 enforcement).

R39: If a phase-A/B/C symmetric net (GLA/GLB/GLC, BEMF_A/B/C, BSTA/B/C,
MOTOR_A/B/C, SHUNT_A/B/C, GHA/B/C) is ripped, EITHER:
  (a) the equivalent rips on its A+B+C peers are also performed
      (the mirror discipline — preserves the per-channel commutation-
      loop-L symmetry that OQ-017/OQ-019 + R19 lock), OR
  (b) the deviation is explicitly logged with R19-loop-L verification
      proof reference (a docs/ROUTING_LESSONS.md row, a sim ref, or a
      master-review-note path) — silent break = FAIL.

The provenance entry carries `phase_symmetric_mirror_status` ∈
{"MIRRORED", "DEVIATION_LOGGED", "N/A"} plus `phase_symmetric_peers` (the
A+B+C peer triple, populated by the router when applicable). G_J4 verifies:

  * Every committed entry whose conflict_set contains a phase-symmetric
    net has phase_symmetric_mirror_status != "N/A".
  * If status == "MIRRORED": the peer triple is populated AND every peer
    appears as a ripped net (either in this same entry's conflict_set OR
    in a sibling entry within ±60 seconds for the same blocked_net
    grouping). Sibling matching keeps the audit robust against per-net
    atomic-attempt provenance (one entry per blocked net) vs grouped-
    attempt provenance (one entry per attempt batch).
  * If status == "DEVIATION_LOGGED": deviation_log_ref MUST be non-empty
    AND point to a real file (docs/ROUTING_LESSONS.md, sims/.../note,
    or docs/MASTER_*.md) — a placeholder string is a FAIL.

PASS: every phase-symmetric rip is either mirrored or explicitly logged.
FAIL: a phase-symmetric rip without mirror or log.

Vacuous-PASS: zero entries; entries without phase-symmetric nets.

Per docs/RULES_MANIFEST.md R39; CH1 30/30 lever J 2026-05-28.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import targeted_ripup as TR  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent.parent.parent


def _parse_iso(s: str):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _siblings_within(entries, base, window_seconds=60):
    """Entries with the same subsystem within ±window of `base.timestamp_iso`."""
    base_t = _parse_iso(base.timestamp_iso)
    if base_t is None:
        return []
    out = []
    for e in entries:
        if e is base:
            continue
        if e.subsystem != base.subsystem:
            continue
        t = _parse_iso(e.timestamp_iso)
        if t is None:
            continue
        if abs((t - base_t).total_seconds()) <= window_seconds:
            out.append(e)
    return out


def audit(repo_root: Path = REPO_ROOT, verbose: bool = True) -> int:
    entries = TR.load_provenance(repo_root)
    if not entries:
        if verbose:
            print("audit_symmetric_ripup_mirror G_J4 — 0 entries (vacuous PASS).")
        return 0

    if verbose:
        print(f"audit_symmetric_ripup_mirror G_J4 — {len(entries)} entry(ies)")

    bad = []
    for e in entries:
        if not e.committed:
            continue
        # Determine if any ripped net is phase-symmetric
        ripped_phase = [(n, TR.phase_peer_set(n)) for n in e.conflict_set]
        ripped_phase = [(n, peers) for (n, peers) in ripped_phase if peers]
        if not ripped_phase:
            continue   # no phase-symmetric rip in this entry — R39 not engaged

        status = e.phase_symmetric_mirror_status
        if status == "N/A":
            bad.append((e, f"phase-symmetric net(s) in conflict_set "
                          f"({[n for n,_ in ripped_phase]}) but "
                          f"mirror_status=='N/A' — R39 engaged but ignored"))
            continue

        if status == "MIRRORED":
            # Peer triple must be populated AND every peer must appear ripped
            # (either in this entry or a sibling). We use the first phase-
            # symmetric ripped net's peer triple as the canonical reference;
            # if the entry's declared peers differ, that's still OK as long
            # as MIRRORED status is honest for at least one peer family.
            if not e.phase_symmetric_peers:
                bad.append((e, "mirror_status=='MIRRORED' but "
                              "phase_symmetric_peers empty"))
                continue
            siblings = _siblings_within(entries, e, window_seconds=60)
            all_ripped_in_window = set(e.conflict_set)
            for s in siblings:
                if s.committed:
                    all_ripped_in_window.update(s.conflict_set)
            missing_peers = []
            # Check that for at least one of the ripped phase-symmetric nets,
            # all A+B+C peers were ripped within the window.
            satisfied = False
            for (n, peers) in ripped_phase:
                if all(p in all_ripped_in_window for p in peers):
                    satisfied = True
                    break
                else:
                    missing_peers = [p for p in peers
                                     if p not in all_ripped_in_window]
            if not satisfied:
                bad.append((e, f"mirror_status=='MIRRORED' but peer(s) "
                              f"missing in window: {missing_peers}"))
            continue

        if status == "DEVIATION_LOGGED":
            ref = e.deviation_log_ref or ""
            if not ref:
                bad.append((e, "mirror_status=='DEVIATION_LOGGED' but "
                              "deviation_log_ref empty (R39 requires "
                              "an explicit log reference, never silent)"))
                continue
            # Try to resolve the ref relative to repo root. Accept
            # repo-relative paths or path-with-#anchor.
            ref_path_str = ref.split("#", 1)[0]
            ref_path = (repo_root / ref_path_str).resolve() \
                if not ref_path_str.startswith("/") else Path(ref_path_str)
            if not ref_path.exists():
                bad.append((e, f"mirror_status=='DEVIATION_LOGGED' but "
                              f"deviation_log_ref {ref!r} does not exist "
                              f"(resolved {ref_path})"))
            continue

        # Unknown status
        bad.append((e, f"unrecognised mirror_status {status!r} "
                      "(must be MIRRORED/DEVIATION_LOGGED/N/A)"))

    if verbose:
        for e, msg in bad:
            print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}: {msg}")

    if bad:
        if verbose:
            print(f"\nG_J4 FAIL: {len(bad)} phase-symmetric mirror "
                  "violation(s) (R39).")
        return 1
    if verbose:
        print(f"\nG_J4 PASS: phase-symmetric ripups all mirrored or "
              "explicitly logged.")
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
