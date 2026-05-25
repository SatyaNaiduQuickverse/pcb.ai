#!/usr/bin/env python3
"""
audit_doc_sync.py — G_D1/G_D2/G_D3 combined doc-sync gate.

Proactive 2026-05-26 (catch class: docs drift from reality). Three sub-checks:

  G_D1: every OQ-NNN id referenced in source has matching entry in
        docs/OPEN_QUESTIONS.md
  G_D2: every file in memory/ has a corresponding row in MEMORY.md index
  G_D3: every hardware/kicad/scripts/audit_*.py has either a row in
        docs/AUDIT_VALIDATION.md results table OR is listed in TODO

Catches stale docs / orphan code / unclosed OQs that would otherwise rot
silently until fab review.

Exit 0 = all in sync, 1 = drift detected.

Usage:
  python3 audit_doc_sync.py
"""

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS = REPO / "hardware" / "kicad" / "scripts"
MEMORY_DIR = Path.home() / ".claude" / "projects" / "-home-novatics64-novapcbmaster" / "memory"


def collect_oq_ids_in_code():
    """Grep all *.py + *.md files for OQ-NNN references."""
    ids = set()
    for ext in ("*.py", "*.md", "*.yaml"):
        for p in REPO.rglob(ext):
            if ".git" in p.parts:
                continue
            try:
                for m in re.finditer(r"\bOQ-(\d{3})\b", p.read_text(errors="ignore")):
                    ids.add(m.group(0))
            except Exception:
                pass
    return ids


def collect_oq_ids_in_doc():
    p = REPO / "docs" / "OPEN_QUESTIONS.md"
    if not p.exists():
        return set()
    return set(re.findall(r"\bOQ-\d{3}\b", p.read_text()))


def check_oq_sync():
    in_code = collect_oq_ids_in_code()
    in_doc = collect_oq_ids_in_doc()
    missing_from_doc = in_code - in_doc
    return missing_from_doc, in_code, in_doc


def check_memory_index_sync():
    """Every memory/*.md file must have a row in MEMORY.md."""
    if not MEMORY_DIR.exists():
        return set(), 0, 0
    files = {p.stem for p in MEMORY_DIR.glob("*.md") if p.name != "MEMORY.md"}
    index_path = MEMORY_DIR / "MEMORY.md"
    indexed = set()
    if index_path.exists():
        for m in re.finditer(r"\]\(([\w-]+)\.md\)", index_path.read_text()):
            indexed.add(m.group(1))
    return files - indexed, len(files), len(indexed)


def check_audit_validation_sync():
    """Every audit_*.py in scripts/ should appear in docs/AUDIT_VALIDATION.md."""
    if not SCRIPTS.exists():
        return set(), 0
    audits = {p.stem for p in SCRIPTS.glob("audit_*.py")}
    val_path = REPO / "docs" / "AUDIT_VALIDATION.md"
    if not val_path.exists():
        return audits, len(audits)
    txt = val_path.read_text()
    missing = set()
    for a in audits:
        if a not in txt:
            missing.add(a)
    return missing, len(audits)


def main():
    print("=== Doc-sync audit (G_D1/G_D2/G_D3) ===\n")

    any_fail = False

    # G_D1: OQ-ids
    missing_oq, in_code, in_doc = check_oq_sync()
    print(f"G_D1 OQ sync: {len(in_code)} OQ-ids in code, {len(in_doc)} in OPEN_QUESTIONS.md")
    if missing_oq:
        any_fail = True
        print(f"  [FAIL] missing from doc: {sorted(missing_oq)}")
    else:
        print(f"  [PASS] all OQ-ids documented")

    # G_D2: memory index
    missing_mem, n_files, n_indexed = check_memory_index_sync()
    print(f"\nG_D2 memory index: {n_files} files, {n_indexed} indexed in MEMORY.md")
    if missing_mem:
        # WARN not FAIL — memory drift is per-user, not project-blocking
        print(f"  [WARN] {len(missing_mem)} memory files not in index:")
        for m in sorted(missing_mem)[:10]:
            print(f"    {m}.md")
        if len(missing_mem) > 10:
            print(f"    ... +{len(missing_mem)-10} more")
    else:
        print(f"  [PASS] all memory files indexed")

    # G_D3: audit validation
    missing_audit, n_audits = check_audit_validation_sync()
    print(f"\nG_D3 audit-validation sync: {n_audits} audit_*.py scripts")
    if missing_audit:
        any_fail = True
        print(f"  [FAIL] {len(missing_audit)} audits not in AUDIT_VALIDATION.md:")
        for a in sorted(missing_audit):
            print(f"    {a}.py")
    else:
        print(f"  [PASS] all audits documented")

    if any_fail:
        print("\nRESULT: FAIL — doc drift detected")
        sys.exit(1)
    print("\nRESULT: PASS — all docs in sync")


if __name__ == "__main__":
    main()
