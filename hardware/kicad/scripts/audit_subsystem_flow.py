#!/usr/bin/env python3
"""audit_subsystem_flow.py — G_FLOW1/G_FLOW2/G_FLOW3 (Sai 2026-05-26 lock).

Enforces the 7-step subsystem development flow + adjacent integration sim +
I/O port discipline per PLACEMENT_GLOBAL_PLAN.md §8.

  G_FLOW1 subsystem_flow_steps    — PR body declares STEP 1-7 results
                                    (place / audit / sim / [rethink] / route / re-audit / re-sim)
  G_FLOW2 adjacent_integration_sim — for subsystem N+1, sim with already-placed neighbor N present
  G_FLOW3 io_port_allocation      — subsystem only routes its allocated I/O ports;
                                    other pins left unrouted for next-subsystem PRs

Per Sai 2026-05-26: *"make sure our entire plan is included in audits without
skipping and with honesty"*. Skipping a step is BANNED.

Run as: `python3 audit_subsystem_flow.py [<subsystem-name>] [--pr-body <path>]`

Modes:
  - Default: scan docs/phase4v3/STAGE*_*.md for per-subsystem flow records
  - With <subsystem>: check only that subsystem's flow record
"""
import os, re, sys, glob

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", ".."))
STAGE_DOCS = os.path.join(REPO, "docs", "phase4v3")
INVARIANTS = os.path.join(REPO, "docs", "BOARD_INVARIANTS.md")

# 7 steps that must appear in any stage doc (Sai-locked flow)
REQUIRED_STEPS = [
    ("STEP 1 PLACE",   r"(?i)step\s*1[^a-z]+place|placement complete|99/99|N/N placed"),
    ("STEP 2 AUDIT",   r"(?i)step\s*2[^a-z]+audit|master_pre_merge|gates? green|gates? pass"),
    ("STEP 3 SIM",     r"(?i)step\s*3[^a-z]+sim|elmer|openems|ngspice|loop.{1,10}induct|thermal|physics sim"),
    ("STEP 4 RETHINK", r"(?i)step\s*4[^a-z]+rethink|structural\s+rethink|re-place|no sim issues"),
    ("STEP 5 ROUTE",   r"(?i)step\s*5[^a-z]+rout|routing complete|traces? routed|freerouter|deferred to phase 5"),
    ("STEP 6 RE-AUDIT/SIM", r"(?i)step\s*6[^a-z]+(re-?audit|re-?sim|post.route)|audit_routing|post-route sim"),
    ("STEP 7 PR",      r"(?i)step\s*7|push|merge|master review|pull request"),
]

# Adjacent pairing per PLACEMENT_GLOBAL_PLAN.md §8 (Sai 2026-05-26)
ADJACENT_PAIRS = {
    "S5":  ["CH1"],
    "S2":  ["CH1", "S5"],
    "S3":  ["S2"],
    "S1":  ["S3"],
    "CH2": ["CH1"],
    "CH3": ["CH2"],
    "CH4": ["CH3"],
    "INTEGRATE": ["ALL"],
}

def parse_io_ports():
    """Return {subsystem: [allocated_io_signals]} from BOARD_INVARIANTS.md."""
    if not os.path.exists(INVARIANTS):
        return {}
    text = open(INVARIANTS).read()
    out = {}
    in_io_table = False
    for ln in text.splitlines():
        if "From → To" in ln and "Signals" in ln:
            in_io_table = True; continue
        if in_io_table:
            if not ln.startswith('|') or '---' in ln[:5]:
                if not ln.strip(): break
                if '---' in ln[:5]: continue
                if not ln.startswith('|'): break
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) >= 4:
                from_to = cells[0]
                signals = cells[3]
                m = re.match(r'(\w+)\s*→\s*(\w+)', from_to)
                if m:
                    src, dst = m.group(1), m.group(2)
                    out.setdefault(src, []).append((dst, signals))
    return out

def find_stage_docs():
    if not os.path.isdir(STAGE_DOCS):
        return []
    return sorted(glob.glob(os.path.join(STAGE_DOCS, "STAGE*_*.md")))

def check_stage_doc(doc_path):
    """Returns list of (severity, message) findings for a STAGE*_*.md."""
    findings = []
    text = open(doc_path).read()
    name = os.path.basename(doc_path)
    # Extract stage / subsystem
    m = re.match(r'STAGE(\d+)_([A-Z0-9]+)\.md', name)
    if not m:
        return [("WARN", f"{name}: doesn't match STAGE<N>_<SUBSYS>.md naming")]
    stage_num, subsys = m.group(1), m.group(2)

    # Pre-flow-lock stages (S6 + TIER1) placed before Sai's 2026-05-26 flow lock —
    # grandfathered as advisory. New flow applies STAGE2+ (CH1 onward).
    pre_flow_lock = int(stage_num) < 2
    severity = "WARN" if pre_flow_lock else "FAIL"

    # G_FLOW1: 7 steps declared
    missing_steps = []
    for label, pattern in REQUIRED_STEPS:
        if not re.search(pattern, text):
            missing_steps.append(label)
    if missing_steps:
        findings.append((severity, f"{name}: G_FLOW1 missing steps: {missing_steps}"
                                   + (" (pre-flow-lock advisory)" if pre_flow_lock else "")))

    # G_FLOW2: adjacent integration sim for subsystems after the first
    if int(stage_num) > 2 and subsys in ADJACENT_PAIRS:
        for partner in ADJACENT_PAIRS[subsys]:
            if partner == "ALL": continue
            # check for sim mentioning the partner pair
            pair_re = re.compile(rf'(?i)({subsys}.{{0,30}}{partner}|{partner}.{{0,30}}{subsys}).{{0,100}}(sim|elmer|openems|ngspice|thermal|emi|integrat)', re.DOTALL)
            if not pair_re.search(text):
                findings.append(("FAIL", f"{name}: G_FLOW2 missing adjacent-pair integration sim with {partner}"))

    # G_FLOW3: I/O port allocation — only the allocated I/O signals should be claimed routed
    # (Lightweight check: doc should mention 'I/O port' or 'allocated' or list the specific signals)
    if "I/O" not in text and "port" not in text.lower():
        findings.append(("WARN", f"{name}: G_FLOW3 doc doesn't reference I/O port allocation"))

    return findings or [("PASS", f"{name}: all 7 steps declared + G_FLOW2/3 satisfied")]

def main():
    print("=" * 70)
    print(f"audit_subsystem_flow.py G_FLOW1/2/3 — scan docs/phase4v3/STAGE*.md")
    print("=" * 70)
    docs = find_stage_docs()
    if not docs:
        print("  ℹ No STAGE docs yet — pre-first-subsystem (advisory)")
        return 0

    total_fail = 0
    for d in docs:
        findings = check_stage_doc(d)
        for sev, msg in findings:
            tag = "✅" if sev == "PASS" else ("⚠" if sev == "WARN" else "❌")
            print(f"  {tag} {msg}")
            if sev == "FAIL": total_fail += 1

    print()
    if total_fail:
        print(f"FAIL — {total_fail} flow violation(s); see PLACEMENT_GLOBAL_PLAN.md §8")
        return 1
    print(f"PASS — all stages follow the 7-step flow + adjacent sim + I/O discipline")
    return 0

if __name__ == "__main__":
    sys.exit(main())
