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

def extract_emi(sim_dir):
    """Look for openEMS extract output with S21 / coupling."""
    for fp in glob.glob(os.path.join(sim_dir, "*.csv")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "*.json")):
        text = open(fp).read()
        # Get max coupling magnitude (least-negative dB = worst)
        coupling = find_value(text, [r"BEMF\s+coupling[:\s=]+(-?\d+\.?\d*)\s*dB",
                                     r"S21\s+max[:\s=]+(-?\d+\.?\d*)", r"coupling\s+peak[:\s=]+(-?\d+\.?\d*)"])
        if coupling is not None: return coupling
    return None

def extract_pi(sim_dir):
    """Look for ngspice extract with VDD ripple."""
    for fp in glob.glob(os.path.join(sim_dir, "*table.txt")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "ripple*.txt")):
        text = open(fp).read()
        ripple = find_value(text, [r"VDD\s+ripple\s+max[:\s=]+(\d+\.?\d*)\s*mV",
                                   r"max\s+ripple[:\s=]+(\d+\.?\d*)", r"worst\s+pin[:\s=]+(\d+\.?\d*)\s*mV"])
        if ripple is not None: return ripple
    return None

def extract_loop(sim_dir):
    """Look for loop inductance extract."""
    for fp in glob.glob(os.path.join(sim_dir, "*.csv")) + glob.glob(os.path.join(sim_dir, "RESULTS.md")) + glob.glob(os.path.join(sim_dir, "loop*.txt")):
        text = open(fp).read()
        loop_l = find_value(text, [r"L_loop[:\s=]+(\d+\.?\d*)\s*nH", r"commutation\s+loop[:\s=]+(\d+\.?\d*)",
                                   r"loop\s+inductance[:\s=]+(\d+\.?\d*)"])
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
        if val is None:
            verdicts[entry] = {"status": "PENDING", "value": None, "key": key}
            print(f"  ⏳ {entry}: NO RESULT YET (sim still running or extract not complete)")
            continue

        thresh = THRESHOLDS[key]["max"]
        # for EMI, less-negative is worse; for others, larger is worse
        is_emi = key == "emi_BEMF_dB"
        passes = (val < thresh) if not is_emi else (val < thresh)
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
    print(f"  Pending: {pending}  Passed: {passed}  Failed: {failed}")

    out_path = os.path.join(sims_base, "verdicts_summary.json")
    json.dump(verdicts, open(out_path, "w"), indent=2)
    print(f"  Summary: {out_path}")

    return 1 if failed > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
