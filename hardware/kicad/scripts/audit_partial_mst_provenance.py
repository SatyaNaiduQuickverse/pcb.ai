#!/usr/bin/env python3
"""audit_partial_mst_provenance.py — G_K1 (R40 enforcement).

R40: Every multi-pad net that ends PARTIAL after the cooperative router's
K2 per-leaf rejoin retries MUST have a provenance entry under
`sims/routing_provenance/partial_mst/`. A PARTIAL net without an entry =
silent abandonment, the very thing R40 prevents (mirrors R36 / G_J1 for
targeted ripup).

Algorithm:
  1. Scan `sims/routing_provenance/partial_mst/*.json`.
  2. For each entry, verify SCHEMA + REQUIRED FIELDS:
       - schema_version >= 1
       - netname non-empty
       - timestamp_iso non-empty
       - pad_refs is a list of len >= 3 (multi-pad nets only — 2-pad nets
         have a single MST edge and never go PARTIAL by construction)
       - routed_edges is a non-negative int
       - failed_pad_pairs is a list of [a, b] pairs, non-empty (a PARTIAL
         net by definition has ≥ 1 failed edge — an entry with empty
         failed_pad_pairs is a malformed record)
       - retries_per_leaf is a dict; every recorded retry count is in
         the closed interval [1, MST_LEAF_RETRY_CAP = 3] (cascade-bounded)
       - reason non-empty
  3. CASCADE BOUND: any retry count exceeding MST_LEAF_RETRY_CAP = 3 is a
     R40 violation (the K2 retry loop is bounded; an entry claiming > 3
     means an unbounded variant slipped through).

PASS: every entry has all required fields present, consistent, and
  cascade-bounded.
FAIL: any entry is missing a required field OR a retry count exceeds the
  cap OR failed_pad_pairs is empty on a PARTIAL record.

Vacuous-PASS: zero entries (no multi-pad net went PARTIAL — the happy
path) is PASS. Matches the existing pattern (G_J1, G_HDI_VIA_IN_PAD).

Per docs/RULES_MANIFEST.md R40; CH1 30/30 lever K2 2026-05-28.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
PROVENANCE_DIR_REL = "sims/routing_provenance/partial_mst"

# SSoT mirror of route_subsystem_cooperative.MST_LEAF_RETRY_CAP.
# Kept in lock-step so the audit cap matches the code cap.
MST_LEAF_RETRY_CAP = 3


def _load_entries(repo_root: Path):
    d = repo_root / PROVENANCE_DIR_REL
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            raw = json.loads(p.read_text())
            raw["_file"] = p.name
            out.append(raw)
        except Exception as e:
            out.append({"_file": p.name,
                        "schema_version": -1,
                        "_parse_error": f"{type(e).__name__}: {e}"})
    return out


def audit(repo_root: Path = REPO_ROOT, verbose: bool = True) -> int:
    entries = _load_entries(repo_root)
    if not entries:
        if verbose:
            print("audit_partial_mst_provenance G_K1 — 0 entries "
                  "(vacuous PASS).")
            print("  (no multi-pad net went PARTIAL — the happy path)")
        return 0

    if verbose:
        print(f"audit_partial_mst_provenance G_K1 — {len(entries)} "
              "provenance entry(ies)")

    bad = []
    for e in entries:
        problems = []
        if "_parse_error" in e:
            problems.append(f"parse error: {e['_parse_error']}")
        sv = e.get("schema_version", 0)
        if not isinstance(sv, int) or sv < 1:
            problems.append(f"schema_version={sv} (< 1 = malformed)")
        if not e.get("netname"):
            problems.append("netname missing/empty")
        if not e.get("timestamp_iso"):
            problems.append("timestamp_iso missing/empty")
        pad_refs = e.get("pad_refs", [])
        if not isinstance(pad_refs, list) or len(pad_refs) < 3:
            problems.append(
                f"pad_refs has < 3 entries ({len(pad_refs) if isinstance(pad_refs, list) else 'N/A'}) "
                "— multi-pad partial requires ≥ 3 pads by construction"
            )
        re_edges = e.get("routed_edges")
        if not isinstance(re_edges, int) or re_edges < 0:
            problems.append(
                f"routed_edges wrong type/value: {re_edges!r}"
            )
        failed = e.get("failed_pad_pairs", [])
        if not isinstance(failed, list) or len(failed) == 0:
            problems.append(
                "failed_pad_pairs missing or empty — PARTIAL "
                "record without ≥ 1 failed pair is malformed"
            )
        else:
            for pair in failed:
                if not (isinstance(pair, list) and len(pair) == 2
                        and all(isinstance(s, str) and s for s in pair)):
                    problems.append(
                        f"failed_pad_pairs contains malformed entry: "
                        f"{pair!r}"
                    )
        rpl = e.get("retries_per_leaf", {})
        if not isinstance(rpl, dict):
            problems.append(
                f"retries_per_leaf wrong type: {type(rpl).__name__}"
            )
        else:
            for k, v in rpl.items():
                if not isinstance(v, int) or v < 1 \
                        or v > MST_LEAF_RETRY_CAP:
                    problems.append(
                        f"retries_per_leaf[{k}]={v} violates "
                        f"cascade bound [1, {MST_LEAF_RETRY_CAP}]"
                    )
        if not e.get("reason"):
            problems.append("reason missing/empty")
        if problems:
            bad.append((e, problems))

    if verbose:
        for e, problems in bad:
            print(f"  ❌ {e.get('netname','?')} "
                  f"@ {e.get('timestamp_iso','?')} "
                  f"({e.get('_file','?')}):")
            for p in problems:
                print(f"     - {p}")

    if bad:
        if verbose:
            print(f"\nG_K1 FAIL: {len(bad)} provenance entry(ies) "
                  "with problems (R40 violation).")
        return 1
    if verbose:
        print(f"\nG_K1 PASS: all {len(entries)} provenance entry(ies) "
              "have complete required fields + cascade-bounded retries.")
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
