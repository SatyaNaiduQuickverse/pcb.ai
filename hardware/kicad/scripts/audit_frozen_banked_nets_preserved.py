#!/usr/bin/env python3
"""audit_frozen_banked_nets_preserved.py — G_J3 (R38 enforcement).

R38: Nets in `docs/BOARD_INVARIANTS.md` §"Frozen banked nets" CANNOT be
ripped under any targeted-ripup attempt. Power planes (+VMOTOR, GND),
+BATT, validated CH1 power routing — ripping these breaks PDN/EMI/sim
work that's been validated; the cost-benefit is never favourable.

Two-fold check:
  A. Provenance-side: scan all provenance entries (committed AND
     rolled-back). If ANY entry has a frozen-banked net in conflict_set,
     it MUST be rolled back (committed=False) with a rollback_reason
     citing "frozen-banked". A committed attempt that ripped a frozen
     net = FAIL.

  B. SSoT-side: verify the Python SSoT (targeted_ripup.FROZEN_BANKED_NETS)
     and the docs table (BOARD_INVARIANTS.md §"Frozen banked nets")
     have a non-empty intersection on the SAME canonical names. Drift
     between code-side and doc-side defeats the whole rule.

PASS: every provenance attempt on a frozen net was rolled back; SSoT
matches docs (>=10 nets in common, covering the key power classes).
FAIL: any committed entry ripped a frozen net; SSoT diverges from docs.

Vacuous-PASS on (A): zero entries. Never vacuous on (B): the doc check
runs unconditionally — drift between Python + doc is always wrong.

Per docs/RULES_MANIFEST.md R38; CH1 30/30 lever J 2026-05-28.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import targeted_ripup as TR  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent.parent.parent
BOARD_INV = REPO_ROOT / "docs/BOARD_INVARIANTS.md"

# Doc-side frozen-banked-nets section header (canonical)
DOC_SECTION_HEADER = "Frozen banked nets"


def parse_frozen_banked_from_doc(text: str) -> set[str]:
    """Extract net names from the BOARD_INVARIANTS.md frozen-banked table.

    The doc presents the table under a section header containing
    "Frozen banked nets". The table has a `Net` column. We tolerate either
    backtick-quoted names (`+VMOTOR`) or plain names, and skip header /
    separator rows.
    """
    # Find the section
    idx = text.find(DOC_SECTION_HEADER)
    if idx < 0:
        return set()
    # Read until the next ## header (or EOF)
    rest = text[idx:]
    next_h = re.search(r"\n## ", rest)
    section = rest[:next_h.start()] if next_h else rest
    # Pull markdown rows under the table — first column = Net
    nets = set()
    for ln in section.splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        if ln.startswith("|---"):
            continue
        if ln.lower().startswith("| net "):
            continue  # header row
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        # Strip backticks if present
        first = first.strip("`").strip()
        if not first:
            continue
        # Skip obvious non-net cells (the table SHOULD only have nets, but be
        # defensive — anything containing spaces or markdown is not a net name)
        if " " in first or ":" in first or "/" in first:
            continue
        nets.add(first)
    return nets


def audit(repo_root: Path = REPO_ROOT, verbose: bool = True) -> int:
    ok = True

    # ─── (B) SSoT / doc drift check (always runs) ─────────────────────────
    code_side = set(TR.FROZEN_BANKED_NETS)
    if verbose:
        print(f"audit_frozen_banked_nets_preserved G_J3 — SSoT check")
        print(f"  code side ({len(code_side)} nets): "
              f"{sorted(code_side)[:6]}{'...' if len(code_side) > 6 else ''}")
    if not BOARD_INV.exists():
        if verbose:
            print(f"  ❌ BOARD_INVARIANTS.md not found at {BOARD_INV}")
        return 1
    doc_text = BOARD_INV.read_text()
    doc_side = parse_frozen_banked_from_doc(doc_text)
    if verbose:
        print(f"  doc side  ({len(doc_side)} nets): "
              f"{sorted(doc_side)[:6]}{'...' if len(doc_side) > 6 else ''}")
    # Require >= 10 nets in common AND coverage of the key classes (power +
    # GND + BATT). A drift where one side lists a net the other does not =
    # FAIL.
    in_both = code_side & doc_side
    code_only = code_side - doc_side
    doc_only = doc_side - code_side
    KEY = {"+VMOTOR", "GND", "+BATT"}
    if not KEY.issubset(in_both):
        if verbose:
            missing = KEY - in_both
            print(f"  ❌ KEY power nets missing from intersection: {sorted(missing)}")
        ok = False
    if len(in_both) < 10:
        if verbose:
            print(f"  ❌ only {len(in_both)} nets in common (require ≥10 to "
                  "cover the validated power + safety set)")
        ok = False
    if code_only:
        if verbose:
            print(f"  ❌ in CODE but NOT in DOC: {sorted(code_only)}")
        ok = False
    if doc_only:
        if verbose:
            print(f"  ❌ in DOC but NOT in CODE: {sorted(doc_only)}")
        ok = False

    # ─── (A) provenance-side check (vacuous-PASS when no entries) ─────────
    entries = TR.load_provenance(repo_root)
    if verbose:
        print(f"  provenance side: {len(entries)} entry(ies)")
    for e in entries:
        frozen_in_set = [n for n in e.conflict_set if TR.is_frozen_banked(n)]
        if not frozen_in_set:
            continue
        if e.committed:
            if verbose:
                print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}: COMMITTED "
                      f"with frozen-banked in conflict_set: {frozen_in_set}")
            ok = False
        else:
            # Rolled back — must cite "frozen-banked" in rollback_reason
            if "frozen" not in e.rollback_reason.lower():
                if verbose:
                    print(f"  ❌ {e.blocked_net} @ {e.timestamp_iso}: "
                          f"rolled back with frozen-banked in conflict_set "
                          f"{frozen_in_set} but rollback_reason "
                          f"{e.rollback_reason!r} does not cite frozen-banked")
                ok = False

    if not ok:
        if verbose:
            print(f"\nG_J3 FAIL: frozen-banked-nets discipline violated "
                  f"(R38 violation).")
        return 1
    if verbose:
        print(f"\nG_J3 PASS: SSoT consistent ({len(in_both)} nets in both); "
              "no committed rips of frozen-banked nets.")
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
