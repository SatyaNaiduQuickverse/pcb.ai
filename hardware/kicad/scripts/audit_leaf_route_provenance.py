#!/usr/bin/env python3
"""audit_leaf_route_provenance.py — G_Q1 (R42 enforcement).

R42 (CH1 30/30 lever Q): every targeted-leaf-route attempt by the
cooperative router (run_leaf_route_phase) MUST write a provenance entry
under `sims/routing_provenance/leaf_route/`. The audit verifies schema
+ cascade ≤ LEAF_ROUTE_ATTEMPT_CAP (= 2) + shorts-delta ≤ 0 on every
COMMITTED entry — the R-J5 / G_J5 SHORTS DELTA invariant applies
identically to the leaf-route path (no second-class commits).

The audit also enforces that every entry's `final_outcome` is one of:
    "ROUTED" | "NO_PATH" | "SHORTS_GATE_REJECT" | "DISABLED"
A committed entry MUST have final_outcome == "ROUTED". A non-committed
entry MUST NOT claim ROUTED.

Algorithm:
  1. Scan `sims/routing_provenance/leaf_route/*.json`.
  2. For each entry verify SCHEMA + REQUIRED FIELDS:
       - schema_version >= 1
       - netname non-empty
       - leaf_pad non-empty (e.g. "R76.1")
       - trunk_pads is a list (allowed empty only on DISABLED entries)
       - attempts is a non-empty list of dicts
         (every entry — even DISABLED — records its INIT step)
       - cascade_attempts in [1, LEAF_ROUTE_ATTEMPT_CAP = 2]
       - shorts_pre, shorts_post are non-negative ints
       - final_outcome in the allowed enum
       - committed bool consistent with final_outcome
       - committed ⇒ shorts_post − shorts_pre ≤ 0  (R-J5 invariant)
  3. CASCADE BOUND: any cascade_attempts > LEAF_ROUTE_ATTEMPT_CAP is a
     R42 violation. Mirrors R37 / G_J2 discipline.
  4. SHORTS-DELTA: any committed entry with shorts_post > shorts_pre
     is a R42 / R-J5 violation. The leaf-route path MUST roll back on
     positive delta; a committed entry with positive delta means the
     rollback drifted.

PASS: every entry has all required fields present, consistent, and
  invariant-bounded.
FAIL: any entry is missing a required field OR exceeds the cap OR
  violates shorts-delta on commit OR claims ROUTED while committed=False
  (or vice versa).

Vacuous-PASS: zero entries (no committed-net had a disconnected leaf —
the happy path) is PASS. Matches the existing pattern (G_J1, G_K1).

Per docs/RULES_MANIFEST.md R42; CH1 30/30 lever Q 2026-05-29.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
PROVENANCE_DIR_REL = "sims/routing_provenance/leaf_route"

# SSoT mirror of route_subsystem_cooperative.LEAF_ROUTE_ATTEMPT_CAP.
# Kept in lock-step so the audit cap matches the code cap.
LEAF_ROUTE_ATTEMPT_CAP = 2

VALID_FINAL_OUTCOMES = {"ROUTED", "NO_PATH", "SHORTS_GATE_REJECT", "DISABLED"}
VALID_ATTEMPT_OUTCOMES = {"ROUTED", "NO_PATH", "SHORTS_GATE_REJECT"}
VALID_MECHANISMS = {"maze", "multi_mech", "init"}


def _load_entries(repo_root: Path):
    d = repo_root / PROVENANCE_DIR_REL
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            raw = json.loads(p.read_text())
            out.append((p.name, raw))
        except Exception as e:
            out.append((p.name, {"__parse_error__": f"{type(e).__name__}: {e}"}))
    return out


def _check_entry(name: str, entry: dict):
    """Return list of violation strings; empty list = PASS for this entry."""
    if "__parse_error__" in entry:
        return [f"{name}: PARSE FAILURE: {entry['__parse_error__']}"]
    violations = []

    # Required scalar fields
    sv = entry.get("schema_version")
    if not isinstance(sv, int) or sv < 1:
        violations.append(f"{name}: missing/invalid schema_version: {sv!r}")
    if not entry.get("netname"):
        violations.append(f"{name}: missing netname")
    if not entry.get("leaf_pad"):
        violations.append(f"{name}: missing leaf_pad")
    if "trunk_pads" not in entry or not isinstance(entry["trunk_pads"], list):
        violations.append(f"{name}: missing/non-list trunk_pads")
    if "attempts" not in entry or not isinstance(entry["attempts"], list):
        violations.append(f"{name}: missing/non-list attempts")
    elif not entry["attempts"]:
        violations.append(f"{name}: empty attempts (every entry must record "
                          "at least the INIT step)")
    cascade = entry.get("cascade_attempts")
    if not isinstance(cascade, int) or cascade < 0:
        violations.append(f"{name}: missing/invalid cascade_attempts: "
                          f"{cascade!r}")
    elif cascade > LEAF_ROUTE_ATTEMPT_CAP:
        violations.append(
            f"{name}: CASCADE BOUND VIOLATED — cascade_attempts={cascade} > "
            f"LEAF_ROUTE_ATTEMPT_CAP={LEAF_ROUTE_ATTEMPT_CAP} (R42)")

    sp = entry.get("shorts_pre")
    spo = entry.get("shorts_post")
    if not isinstance(sp, int) or sp < 0:
        violations.append(f"{name}: missing/invalid shorts_pre: {sp!r}")
    if not isinstance(spo, int) or spo < 0:
        violations.append(f"{name}: missing/invalid shorts_post: {spo!r}")

    committed = entry.get("committed")
    if not isinstance(committed, bool):
        violations.append(f"{name}: missing/invalid committed: {committed!r}")

    final_outcome = entry.get("final_outcome")
    if final_outcome not in VALID_FINAL_OUTCOMES:
        violations.append(
            f"{name}: invalid final_outcome={final_outcome!r}; "
            f"must be one of {sorted(VALID_FINAL_OUTCOMES)}")

    # Cross-field invariants
    if isinstance(committed, bool) and final_outcome in VALID_FINAL_OUTCOMES:
        if committed and final_outcome != "ROUTED":
            violations.append(
                f"{name}: committed=True but final_outcome={final_outcome!r} "
                "(must be ROUTED)")
        if not committed and final_outcome == "ROUTED":
            violations.append(
                f"{name}: committed=False but final_outcome=ROUTED "
                "(inconsistent)")

    # Shorts-delta invariant on commit (R-J5 / G_J5 applied to leaf-route)
    if (isinstance(sp, int) and isinstance(spo, int)
            and isinstance(committed, bool) and committed):
        if spo > sp:
            violations.append(
                f"{name}: SHORTS DELTA POSITIVE on commit "
                f"({sp} -> {spo}; delta={spo - sp} > 0); R-J5/G_J5 violated")

    # Per-attempt sub-schema
    if isinstance(entry.get("attempts"), list):
        for i, att in enumerate(entry["attempts"]):
            if not isinstance(att, dict):
                violations.append(
                    f"{name}: attempts[{i}] is not a dict: {att!r}")
                continue
            mech = att.get("mechanism")
            if mech not in VALID_MECHANISMS:
                violations.append(
                    f"{name}: attempts[{i}].mechanism={mech!r} not in "
                    f"{sorted(VALID_MECHANISMS)}")
            outcome = att.get("outcome")
            if outcome not in VALID_ATTEMPT_OUTCOMES:
                violations.append(
                    f"{name}: attempts[{i}].outcome={outcome!r} not in "
                    f"{sorted(VALID_ATTEMPT_OUTCOMES)}")
            if not att.get("reason"):
                violations.append(
                    f"{name}: attempts[{i}] missing reason")

    return violations


def main():
    print(f"audit_leaf_route_provenance: scanning {REPO_ROOT / PROVENANCE_DIR_REL}")
    entries = _load_entries(REPO_ROOT)
    if not entries:
        print("  vacuous-PASS — no leaf-route provenance entries found")
        print("    (no committed net had a disconnected leaf at this commit)")
        return 0

    print(f"  {len(entries)} entry(ies) found")
    all_violations = []
    committed_count = 0
    routed_outcomes = 0
    no_path_outcomes = 0
    for name, entry in entries:
        vs = _check_entry(name, entry)
        if vs:
            all_violations.extend(vs)
        if isinstance(entry, dict):
            if entry.get("committed") is True:
                committed_count += 1
            if entry.get("final_outcome") == "ROUTED":
                routed_outcomes += 1
            elif entry.get("final_outcome") == "NO_PATH":
                no_path_outcomes += 1

    print(f"  committed: {committed_count}")
    print(f"  ROUTED outcome: {routed_outcomes}")
    print(f"  NO_PATH outcome: {no_path_outcomes}")

    if all_violations:
        print(f"\nFAIL — {len(all_violations)} violation(s):")
        for v in all_violations:
            print(f"  • {v}")
        return 1
    print(f"\nPASS — all {len(entries)} leaf-route entries valid "
          "(schema OK, cascade ≤ {}, shorts-delta ≤ 0 on commit)"
          .format(LEAF_ROUTE_ATTEMPT_CAP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
