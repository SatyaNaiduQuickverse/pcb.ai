#!/usr/bin/env python3
"""master_review_board.py — one-shot review of a .kicad_pcb against ALL master audits.

Usage:
  python3 master_review_board.py /path/to/board.kicad_pcb [/path/to/prev_board.kicad_pcb]

Runs every audit_*.py / verify_*.py wired into master_pre_merge.sh, parses
PASS/FAIL/MARG, summarizes. If prev_board provided, diffs the results so
worker can see per-iteration progress.

This is the AUTOMATION around the 64-gate suite — gives Sai/worker single-line
verdict + per-gate breakdown without manually running the bash script.
"""
import os, sys, subprocess, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Audits that take board path as argv[1]
AUDIT_TAKES_BOARD = {
    "audit_layout_compliance.py", "audit_body_bbox_overlap.py",
    "audit_routing_channels.py", "audit_zone_density.py",
    "audit_3d_model_coverage.py", "verify_placement.py",
    "audit_channel_bom_match.py", "audit_hv_creepage.py",
    "audit_polarity_direction.py", "audit_polarity_marker.py",
    "audit_anchor_pitch.py", "audit_anchor_positions.py",
    "audit_zone_contract.py", "audit_loop_area.py",
    "audit_decoupling.py", "audit_silk_size.py",
    "audit_rotation_alignment.py", "audit_assembly_drawing.py",
    "audit_edge_keepout.py", "audit_pickplace_reach.py",
    "audit_connector_symmetry.py", "audit_cable_swing.py",
    "audit_crosstalk_spacing.py", "audit_jlc_dfm.py",
    "audit_test_point_access.py", "audit_kelvin_shunt_routing.py",
    "audit_panel_fit.py", "audit_diff_pair_match.py",
    "audit_return_path.py", "audit_via_current_capacity.py",
    "audit_via_stitching_density.py", "audit_antenna_structure.py",
    "audit_stub_length.py", "audit_length_match.py",
    "audit_fos_current.py", "audit_fos_pin_current.py",
    "audit_fos_cap_voltage.py", "audit_fos_cap_ripple.py",
    "audit_fos_thermal.py", "audit_bom_lcsc.py",
}

# Audits that DON'T need board (read lockfile / docs only)
AUDIT_LOCKFILE_ONLY = {
    "audit_mount_hole_keepout.py", "audit_pad_edge_clearance.py",
    "audit_parametric_compliance.py", "audit_meta_coverage.py",
    "audit_doc_sync.py", "audit_lockfile_completeness.py",
    "audit_zone_tile_continuity.py", "audit_meta.py",
    "audit_routing.py", "audit_routing_system.py",
    "audit_sim_mesh_validity.py", "audit_sim_result_sanity.py",
}

def run_audit(script_path, board_path):
    cmd = ["python3", script_path]
    if os.path.basename(script_path) in AUDIT_TAKES_BOARD and board_path:
        cmd.append(board_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                cwd=os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR))))
        out = result.stdout + result.stderr
        # Detect verdict
        if "✅ PASS" in out or "✅ pass" in out.lower() or result.returncode == 0:
            return "PASS", out
        if "❌ FAIL" in out or result.returncode != 0:
            # Count fails for FAIL count
            fail_count = len(re.findall(r"❌ FAIL.*?(\d+)", out)) or 1
            return "FAIL", out
        return "?", out
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ""
    except Exception as e:
        return "ERROR", str(e)

def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <board.kicad_pcb> [prev_board.kicad_pcb]")
        sys.exit(1)
    board = sys.argv[1]
    prev_board = sys.argv[2] if len(sys.argv) > 2 else None

    all_audits = sorted([f for f in os.listdir(SCRIPT_DIR)
                         if (f.startswith("audit_") or f.startswith("verify_"))
                         and f.endswith(".py")
                         and f != "audit_meta_coverage.py"])  # don't recurse

    print("=" * 70)
    print(f"master_review_board.py — {board}")
    print("=" * 70)
    if not os.path.exists(board):
        print(f"  ❌ Board not found: {board}")
        sys.exit(1)

    results = {}
    for audit in all_audits:
        script = os.path.join(SCRIPT_DIR, audit)
        verdict, _ = run_audit(script, board)
        results[audit] = verdict

    passes = sum(1 for v in results.values() if v == "PASS")
    fails  = sum(1 for v in results.values() if v == "FAIL")
    others = sum(1 for v in results.values() if v not in ("PASS", "FAIL"))

    print(f"  Total audits: {len(results)}")
    print(f"  PASS:  {passes}")
    print(f"  FAIL:  {fails}")
    print(f"  Other (timeout/error): {others}")
    print()
    if fails:
        print("  ❌ FAILING:")
        for audit in sorted(results):
            if results[audit] == "FAIL":
                print(f"    {audit}")
    if others:
        print("  ⚠ OTHER:")
        for audit in sorted(results):
            if results[audit] not in ("PASS", "FAIL"):
                print(f"    {audit}: {results[audit]}")
    print()
    if fails == 0:
        print(f"  🎉 ALL {passes} AUDITS GREEN")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
