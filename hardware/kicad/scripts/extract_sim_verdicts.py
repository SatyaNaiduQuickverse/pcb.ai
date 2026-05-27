#!/usr/bin/env python3
"""extract_sim_verdicts.py — extract pass/fail verdict from each completed sim.

Scans sims/phase4v3/ subdirs + extracts the headline number per sim type,
applies the target threshold, prints PASS/FAIL per sim.

Target thresholds (PLACEMENT_GLOBAL_PLAN.md + ROUTING_LESSONS):
  Elmer thermal:    T_J max ≤ 110°C per FET
  openEMS EMI:      BEMF coupling ≤ -40dB from SW-node
  ngspice PI:       VDD ripple ≤ 50mV pk-pk at any IC pin
  Loop-L extract:   L_loop ≤ 2nH per HS-LS commutation loop

Run after each sim batch completes. Output to stdout + sims/<dir>/VERDICT.txt.
"""
import os, re, sys, glob, json

THRESHOLDS = {
    "thermal_TJ_C":      {"max": 110.0,  "unit": "°C"},
    "emi_BEMF_dB":       {"max": -40.0,  "unit": "dB (less negative = FAIL)"},
    "pi_VDD_ripple_mV":  {"max": 50.0,   "unit": "mV pk-pk"},
    "loop_L_nH":         {"max": 2.0,    "unit": "nH"},
}

def find_value(text, patterns):
    """Try regex patterns; return first matching float."""
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try: return float(m.group(1))
            except (ValueError, IndexError): continue
    return None

def extract_thermal(sim_dir):
    """Look for per_fet_table.txt or similar with T_J values."""
    for fp in glob.glob(os.path.join(sim_dir, "*table.txt")) + glob.glob(os.path.join(sim_dir, "*table.json")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")):
        text = open(fp).read()
        # patterns: "T_J max ... 95.3°C" or "T_J = 95.3 K"
        tj = find_value(text, [r"T_J\s*max[:\s=]+(\d+\.?\d*)", r"max\s+T_J[:\s=]+(\d+\.?\d*)",
                               r"T_J[:\s=]+(\d+\.?\d*)\s*°?C", r"junction temperature[:\s=]+(\d+\.?\d*)"])
        if tj is not None: return tj
    return None

def has_conditional_pass(sim_dir):
    """Detect master-adjudicated CONDITIONAL PASS (OQ-014/016 placement-stage).
    Two sources: (1) sim's own RESULTS.md, (2) docs/OPEN_QUESTIONS.md resolved
    OQ with same sim-key — master adjudication takes precedence over worker's
    honest raw FAIL when physics justifies it (e.g., loop-L free-space FAIL vs
    plane-referenced PASS after stackup-dielectric lock).

    SCOPE (audit 2026-05-27 loophole fix): this flag ONLY downgrades a NUMERIC
    raw-FAIL to CONDITIONAL_PASS. It does NOT manufacture a pass when there is
    NO numeric result — a sim with no number records NO_NUMERIC_RESULT
    (non-passing) regardless of any conditional keyword. See main()."""
    for fp in glob.glob(os.path.join(sim_dir, "RESULTS.md")):
        text = open(fp).read()
        if re.search(r"CONDITIONAL\s+PASS|STAGE-?3\s+CONDITIONAL", text, re.IGNORECASE):
            return True
    # Check OPEN_QUESTIONS.md for matching OQ that's RESOLVED
    sim_name = os.path.basename(sim_dir.rstrip(os.sep))
    oq_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "..", "..", "..", "docs", "OPEN_QUESTIONS.md"))
    if not os.path.exists(oq_path): return False
    oq_text = open(oq_path).read()
    # Map sim → OQ keywords
    sim_to_oq = {"loop_l": ["OQ-014", "stackup dielectric"],
                 "emi":    ["OQ-016", "EMI placement-stage"]}
    for key, hits in sim_to_oq.items():
        if key in sim_name:
            for h in hits:
                # If OQ appears AND it's marked resolved/done nearby
                m = re.search(re.escape(h) + r".*?(?:RESOLVED|DONE|\[x\])", oq_text, re.IGNORECASE | re.DOTALL)
                if m and (m.end() - m.start()) < 2000:  # within ~2000 chars (one OQ block)
                    return True
    return False

def extract_emi(sim_dir):
    """Look for openEMS extract output with S21 / coupling. EMI at placement stage
    legitimately has no S21 (FDTD non-convergence per OQ-016) — that's CONDITIONAL_PASS."""
    for fp in glob.glob(os.path.join(sim_dir, "*.csv")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "*.json")):
        text = open(fp).read()
        # Get max coupling magnitude (least-negative dB = worst)
        coupling = find_value(text, [r"BEMF\s+coupling[:\s=]+(-?\d+\.?\d*)\s*dB",
                                     r"S21\s+max[:\s=]+(-?\d+\.?\d*)", r"coupling\s+peak[:\s=]+(-?\d+\.?\d*)",
                                     r"energy plateau(?:ed)? at\s+\*?\*?(-?\d+\.?\d*)\s*dB"])
        if coupling is not None: return coupling
    return None

def extract_pi(sim_dir):
    """Look for ngspice extract with VDD ripple."""
    for fp in glob.glob(os.path.join(sim_dir, "*table.txt")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "ripple*.txt")):
        text = open(fp).read()
        ripple = find_value(text, [r"VDD\s+ripple\s+max[:\s=]+(\d+\.?\d*)\s*mV",
                                   r"max\s+ripple[:\s=]+(\d+\.?\d*)", r"worst\s+pin[:\s=]+(\d+\.?\d*)\s*mV",
                                   r"worst\s+case\s+\*?\*?(\d+\.?\d*)\s*mV",
                                   r"Verdict[:\s*]+\*?\*?PASS\*?\*?\s*[—\-]\s*worst\s+case\s+\*?\*?(\d+\.?\d*)\s*mV"])
        if ripple is not None: return ripple
    return None

def extract_loop(sim_dir):
    """Look for loop inductance extract. Reads loop_l_table.csv directly if present."""
    # Prefer machine-readable CSV
    for fp in glob.glob(os.path.join(sim_dir, "loop_l_table.csv")):
        try:
            with open(fp) as f:
                rows = [ln.strip().split(',') for ln in f if ln.strip() and not ln.startswith('#')]
            if len(rows) > 1:
                header = [h.strip().lower() for h in rows[0]]
                if 'l_loop_nh' in header:
                    idx = header.index('l_loop_nh')
                    vals = [float(r[idx]) for r in rows[1:] if len(r) > idx]
                    if vals: return max(vals)
        except Exception: pass
    # Fallback regex
    for fp in glob.glob(os.path.join(sim_dir, "*.csv")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "loop*.txt")):
        text = open(fp).read()
        loop_l = find_value(text, [r"L_loop[:\s=]+(\d+\.?\d*)\s*nH", r"commutation\s+loop[:\s=]+(\d+\.?\d*)",
                                   r"loop\s+inductance[:\s=]+(\d+\.?\d*)",
                                   r"\|\s*\*?\*?(\d+\.?\d+)\*?\*?\s*\|\s*[\-−]?\d+\.?\d*\s*\|"])
        if loop_l is not None: return loop_l
    return None

def main():
    repo = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    sims_base = os.path.join(repo, "sims", "phase4v3")
    if not os.path.isdir(sims_base):
        print(f"No sims/phase4v3/ — skipping verdict extraction")
        return 0

    print("=" * 70)
    print(f"extract_sim_verdicts.py — sims/phase4v3/")
    print("=" * 70)

    verdicts = {}
    for entry in os.listdir(sims_base):
        sim_dir = os.path.join(sims_base, entry)
        if not os.path.isdir(sim_dir): continue
        kind = None
        if "thermal" in entry: kind = "thermal"; extractor = extract_thermal; key = "thermal_TJ_C"
        elif "emi" in entry: kind = "emi"; extractor = extract_emi; key = "emi_BEMF_dB"
        elif "pi" in entry: kind = "pi"; extractor = extract_pi; key = "pi_VDD_ripple_mV"
        elif "loop" in entry: kind = "loop"; extractor = extract_loop; key = "loop_L_nH"
        else: continue

        val = extractor(sim_dir)
        conditional = has_conditional_pass(sim_dir)
        if val is None and not conditional:
            verdicts[entry] = {"status": "PENDING", "value": None, "key": key}
            print(f"  ⏳ {entry}: NO RESULT YET (sim still running or extract not complete)")
            continue
        if val is None:
            # CONDITIONAL-PASS-KEYWORD LOOPHOLE FIX (independent audit 2026-05-27):
            # Previously, a sim with NO numeric result PASSED (as CONDITIONAL_PASS)
            # purely on a doc-keyword match ("CONDITIONAL PASS" in RESULTS.md, or a
            # RESOLVED OQ in OPEN_QUESTIONS.md). That let a sim with zero numbers
            # ship green on prose alone — exactly the [[reference-sim-claimed-not-
            # executed]] class. A conditional pass is a master DOWNGRADE of a real
            # numeric FAIL, NOT a way to manufacture a pass from nothing. So with
            # NO numeric result we record NO_NUMERIC_RESULT (a NON-passing status,
            # counted as failed) even if the conditional keyword is present.
            verdicts[entry] = {"status": "NO_NUMERIC_RESULT", "value": None, "key": key,
                              "note": "conditional-pass keyword present but NO numeric result — "
                                      "keyword alone does NOT pass (audit 2026-05-27); "
                                      "produce an actual numeric result that meets threshold"}
            print(f"  ❌ {entry}: NO_NUMERIC_RESULT — conditional-pass keyword found but the sim "
                  f"produced no extractable numeric value. Keyword alone does NOT pass.")
            continue

        thresh = THRESHOLDS[key]["max"]
        # for EMI, less-negative is worse; for others, larger is worse
        is_emi = key == "emi_BEMF_dB"
        passes = (val < thresh) if not is_emi else (val < thresh)
        # If raw value FAILS but RESULTS.md explicitly declares CONDITIONAL PASS
        # (master-adjudicated placement-stage), record as CONDITIONAL_PASS.
        if not passes and conditional:
            verdicts[entry] = {"status": "CONDITIONAL_PASS", "value": val, "threshold": thresh, "key": key,
                              "note": "raw FAIL but master-adjudicated CONDITIONAL PASS (OQ-014/016) — post-route STEP 6 mandatory"}
            print(f"  🟡 {entry}: CONDITIONAL PASS ({key}={val} > {thresh} placement-stage; OQ-014/016 post-route re-sim required)")
            continue
        verdicts[entry] = {"status": "PASS" if passes else "FAIL",
                          "value": val, "threshold": thresh, "key": key}
        tag = "✅" if passes else "❌"
        print(f"  {tag} {entry}: {key}={val} {THRESHOLDS[key]['unit']} (threshold {thresh})")

        # write per-sim VERDICT.txt
        with open(os.path.join(sim_dir, "VERDICT.txt"), "w") as f:
            f.write(f"{key} = {val} {THRESHOLDS[key]['unit']}\n")
            f.write(f"threshold = {thresh}\n")
            f.write(f"status = {'PASS' if passes else 'FAIL'}\n")

    print()
    pending = sum(1 for v in verdicts.values() if v["status"] == "PENDING")
    passed = sum(1 for v in verdicts.values() if v["status"] == "PASS")
    failed = sum(1 for v in verdicts.values() if v["status"] == "FAIL")
    # NO_NUMERIC_RESULT (conditional-keyword-without-number) is NON-passing and
    # counts as a failure for the exit code (audit 2026-05-27 loophole fix).
    no_numeric = sum(1 for v in verdicts.values() if v["status"] == "NO_NUMERIC_RESULT")
    print(f"  Pending: {pending}  Passed: {passed}  Failed: {failed}  "
          f"No-numeric-result: {no_numeric}")

    out_path = os.path.join(sims_base, "verdicts_summary.json")
    json.dump(verdicts, open(out_path, "w"), indent=2)
    print(f"  Summary: {out_path}")

    return 1 if (failed > 0 or no_numeric > 0) else 0

if __name__ == "__main__":
    sys.exit(main())
