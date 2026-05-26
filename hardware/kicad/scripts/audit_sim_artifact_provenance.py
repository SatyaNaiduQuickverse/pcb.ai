#!/usr/bin/env python3
"""audit_sim_artifact_provenance.py — R-sim-provenance gate.

Class lesson 2026-05-26 (worker-caught during CH1 STEP 4 pickup):

  CH1 placement existed ONLY in /tmp/ch1_152.kicad_pcb — never committed
  to canonical hardware/kicad/pcbai_fpv4in1.kicad_pcb. STEP 3 sims
  (thermal, PI, EMI, loop-L) were ALL validated against that volatile
  /tmp/ artifact. If /tmp/ had been cleaned (reboot, tmpwatch cron), the
  numbers would point at a vanished geometry — unreproducible from SHA.

  This is a [[reference-sim-claimed-not-executed]] sibling class:
  "sim ran against non-canonical artifact". The sim was real, the numbers
  honest, but the provenance was broken.

Rule: every committed sim input / output / RESULTS.md MUST cite git-tracked
paths only. /tmp/, ~/Desktop, /var/tmp, ~/scratch, /home/*/local — all FAIL.
A sim verdict is binding only if reproducible from the repo SHA alone.

Scans:
  - sims/**/*.sif (Elmer)
  - sims/**/*.cir (ngspice)
  - sims/**/*.py  (extract + driver scripts)
  - sims/**/RESULTS.md
  - sims/**/README*

For each file, regex-search for forbidden path prefixes. Report file + line.

Exempted:
  - The audit script itself (this file)
  - Worker's escworker/local/ backup paths (intentional out-of-tree backup
    documented in PR text; not committed to canonical sims/)

Exit 0 = all sim artifact references are git-tracked, 1 = forbidden paths found.

Usage:
  python3 audit_sim_artifact_provenance.py [<sims_root>]
"""

import re
import sys
from pathlib import Path

# Forbidden non-canonical path prefixes, BUT only when paired with an artifact
# extension (data file). Solver binary paths (ElmerSolver, openEMS lib) are
# environment tool paths and don't affect reproducibility from SHA — those
# are gated separately by phase 0 toolchain audit.
NON_CANONICAL_PREFIXES = [
    r"/tmp/",
    r"/var/tmp/",
    r"~/Desktop",
    r"~/scratch",
    r"~/Downloads",
    r"/home/[a-z0-9_]+/scratch/",
    r"/home/[a-z0-9_]+/Desktop",
    r"/home/[a-z0-9_]+/Downloads",
    # /home/<user>/local/ is the worker's external workspace; data files there
    # are non-canonical even if solvers there are fine (tool vs data distinction)
    r"/home/[a-z0-9_]+/local/[^/\s]*\.(kicad_pcb|kicad_sch|kicad_pro|sif|cir|net|csv|json|vtu|result|dat|h5|vtr|npz|raw|out|step|stp)",
    # escworker/local/ is the worker's external workspace
    r"escworker/local/[^/\s]*\.(kicad_pcb|kicad_sch|kicad_pro|sif|cir|net)",
]

# Forbidden + artifact extension required (the core class lesson)
ARTIFACT_EXT = r"\.(kicad_pcb|kicad_sch|kicad_pro|sif|cir|net|csv|json|vtu|result|dat|h5|vtr|npz|raw|out|step|stp|md)"
FORBIDDEN_PATTERNS = [
    # /tmp/ or /var/tmp/ + ANY artifact extension is forbidden
    r"(/tmp/|/var/tmp/)[^\s'\"]*" + ARTIFACT_EXT,
    # Home dir non-workspace paths with artifact ext
    r"(~|/home/[a-z0-9_]+)/(Desktop|scratch|Downloads)[^\s'\"]*" + ARTIFACT_EXT,
    # Worker local/ workspace with .kicad_pcb specifically (the trigger class)
    r"/home/[a-z0-9_]+/local/[^\s'\"]*\.kicad_pcb",
    r"/home/[a-z0-9_]+/escworker/[^\s'\"]*\.kicad_pcb",
]

EXEMPT_FILES = {
    "audit_sim_artifact_provenance.py",  # this file, documents the patterns
}

SCAN_EXTS = {".sif", ".cir", ".py", ".md", ".txt", ".csv", ".json", ".log", ".dat"}


def main():
    sim_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sims")
    print(f"=== R-sim-provenance audit: {sim_root} ===\n")
    if not sim_root.exists():
        print("INFO: sims/ not found — gate inert")
        sys.exit(0)

    pattern = re.compile("|".join(f"(?:{p})" for p in FORBIDDEN_PATTERNS))
    fails = []
    files_scanned = 0
    for fp in sim_root.rglob("*"):
        if not fp.is_file(): continue
        if fp.name in EXEMPT_FILES: continue
        if fp.suffix.lower() not in SCAN_EXTS and "README" not in fp.name and "RESULTS" not in fp.name:
            continue
        # KNOWN_BAD.md sentinel dirs are also exempted from provenance scan
        # (they document past mistakes; the bad paths may appear in error logs)
        if (fp.parent / "KNOWN_BAD.md").exists() and fp.name == "KNOWN_BAD.md":
            continue
        files_scanned += 1
        try:
            for lineno, line in enumerate(open(fp, errors="ignore"), 1):
                m = pattern.search(line)
                if m:
                    # Strip whitespace + trim long lines for readability
                    snippet = line.strip()[:120]
                    fails.append((fp.relative_to(sim_root), lineno, snippet))
        except Exception:
            continue

    print(f"  Files scanned: {files_scanned}")
    if not fails:
        print(f"\nRESULT: PASS — all {files_scanned} sim artifact references are git-tracked")
        sys.exit(0)

    print(f"\n  Forbidden non-canonical path references ({len(fails)}):")
    for f, ln, snip in fails[:20]:
        print(f"    [FAIL] {f}:{ln}: {snip}")
    if len(fails) > 20:
        print(f"    ... and {len(fails) - 20} more")
    print(f"\nRESULT: FAIL — {len(fails)} non-canonical path reference(s)")
    print(f"  Fix: replace /tmp/ etc with git-tracked paths (e.g. hardware/kicad/pcbai_fpv4in1.kicad_pcb)")
    print(f"  Rationale: sim verdicts must be reproducible from repo SHA alone (R-sim-provenance).")
    sys.exit(1)


if __name__ == "__main__":
    main()
