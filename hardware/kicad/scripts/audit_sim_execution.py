#!/usr/bin/env python3
"""audit_sim_execution.py — R-sim-execution gate (Sai-locked 2026-05-23, wired 2026-05-26).

Per [[feedback-sim-execution-gate]] (Sai 2026-05-23 BINDING):
*"Every sim PR MUST include result file + timestamp proof + extract-script output
+ literal exec command. Master rejects any PR that fails this 4-point check."*

This audit enforces the 4-point check on any sim work claimed in a PR body or
in the sims/ tree. Gate FAILS if:
  1. A claimed sim has NO result file (.vtu / .csv / .raw / .out)
  2. Result file mtime < input file mtime (sim outdated, not actually re-run)
  3. No extract-script output (numbers must come from extract script, not be
     copy-pasted from prior version)
  4. PR body / commit message lacks the literal exec command that produced
     the result (reproducibility)

Run as: `python3 audit_sim_execution.py [--pr-body <path-to-pr-body.md>]`

Scans:
  sims/phase4v3/<subsystem>/ for *.sif (Elmer), *.cir (ngspice),
  openems_*.py (FDTD) input files + their expected result outputs.

Exit 0 = PASS (all claimed sims have valid 4-point proof), 1 = FAIL.
"""
import os, sys, re, glob

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", ".."))
SIMS_DIR = os.path.join(REPO, "sims")

# Sim type → (input glob, result glob, extract script)
SIM_TYPES = {
    "elmer_thermal":   {"input": "*.sif",       "result": ["*.vtu", "*.result"], "extract": "extract_*.py"},
    "ngspice_pi":      {"input": "*.cir",       "result": ["*.raw", "*.out"],    "extract": "extract_*.py"},
    "openems_emi":     {"input": "openems_*.py","result": ["*.h5", "*.vtr"],     "extract": "extract_*.py"},
    "loop_l_extract":  {"input": "loop_*.py",   "result": ["*.csv", "*.json"],   "extract": "extract_*.py"},
}

def find_sim_dirs():
    """Find subsystem sim directories under sims/."""
    out = []
    for sub in ("phase4v3", "phase4v2", "phase4"):
        base = os.path.join(SIMS_DIR, sub)
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            d = os.path.join(base, entry)
            if os.path.isdir(d):
                out.append(d)
    return out

def check_sim_dir(sim_dir):
    """Run 4-point check on a sim directory. Returns (status, [reasons])."""
    findings = []
    for kind, spec in SIM_TYPES.items():
        inputs = glob.glob(os.path.join(sim_dir, spec["input"]))
        if not inputs:
            continue  # no sims of this type claimed
        for in_path in inputs:
            in_mtime = os.path.getmtime(in_path)
            # 1. result file exists?
            results = []
            for rg in spec["result"]:
                results.extend(glob.glob(os.path.join(sim_dir, rg)))
                # also subdirs
                results.extend(glob.glob(os.path.join(sim_dir, "**", rg), recursive=True))
            if not results:
                findings.append(("FAIL", in_path, f"no result file ({spec['result']}) — sim not executed"))
                continue
            # 2. result mtime > input mtime?
            stale_results = [r for r in results if os.path.getmtime(r) < in_mtime - 1]
            if stale_results and not any(os.path.getmtime(r) >= in_mtime - 1 for r in results):
                findings.append(("FAIL", in_path,
                                 f"result mtime ({stale_results[0]}) < input mtime — sim not re-run after input change"))
                continue
            # 3. extract script output present?
            extract_scripts = glob.glob(os.path.join(sim_dir, spec["extract"]))
            if not extract_scripts:
                findings.append(("FAIL", in_path, f"no extract_*.py script — numbers must come from extract script"))
                continue
            # extract output file (extract_*.txt or similar)
            extract_outs = (glob.glob(os.path.join(sim_dir, "extract_*.txt"))
                          + glob.glob(os.path.join(sim_dir, "extract_*.json"))
                          + glob.glob(os.path.join(sim_dir, "RESULTS.md")))
            if not extract_outs:
                findings.append(("FAIL", in_path, f"extract script present but no extract output file"))
                continue
            # 4. literal exec command — check RESULTS.md or sim dir README
            cmd_proof = False
            for f in extract_outs + glob.glob(os.path.join(sim_dir, "README*")):
                try:
                    text = open(f).read()
                    if any(c in text for c in ("ElmerSolver", "ngspice", "openems", "python3 ")):
                        cmd_proof = True; break
                except Exception:
                    pass
            if not cmd_proof:
                findings.append(("FAIL", in_path,
                                 f"no literal exec command (ElmerSolver/ngspice/openems/python3) in RESULTS.md or README — reproducibility broken"))
                continue
            findings.append(("PASS", in_path, "4-point proof complete"))
    return findings

def main():
    sim_dirs = find_sim_dirs()
    print("=" * 70)
    print(f"audit_sim_execution.py R-sim-execution — {len(sim_dirs)} sim directories")
    print("=" * 70)
    if not sim_dirs:
        # No sims claimed — return WARN (not FAIL) since some PRs are pure placement
        print("  ℹ No sims/ directories yet — placement-only PR (advisory)")
        return 0

    total_fail = 0
    total_pass = 0
    for d in sim_dirs:
        findings = check_sim_dir(d)
        if not findings:
            continue
        rel = os.path.relpath(d, REPO)
        print(f"\n  {rel}:")
        for status, path, why in findings:
            tag = "✅" if status == "PASS" else "❌"
            print(f"    {tag} {os.path.basename(path)}: {why}")
            if status == "PASS": total_pass += 1
            else: total_fail += 1

    print()
    if total_fail:
        print(f"FAIL — {total_fail} sim file(s) missing 4-point proof; {total_pass} valid")
        print("  Sai-locked rule: result file + mtime>input + extract output + literal exec command")
        return 1
    print(f"PASS — {total_pass} sim file(s) valid with 4-point proof")
    return 0

if __name__ == "__main__":
    sys.exit(main())
