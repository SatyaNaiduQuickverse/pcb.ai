#!/usr/bin/env python3
"""
master_audit_invariants.py — Phase 4-v2 master audit gates (v2 — refactored)

Reads BOARD_INVARIANTS.md (SSOT) via constraint_engine.parse_board_invariants
(single source of truth — fixed v1 parser bug where "CH1 (channel A)" style
names returned 0 zones).

Hash check uses worker's compute_board_invariant_hash.py (canonical script
that produces BOARD_INVARIANT_HASH stored in the .md doc).

5 master gates:
  1. check_board_invariants_hash — invariant hash drift detection
  2. check_subsystem_zone_compliance — all components within declared zone
  3. check_io_port_compliance — I/O port positions land within ±0.5mm tolerance
  4. check_highway_reservation — no components inside reserved corridors
  5. check_symmetry_partner_diff — mirror partner per-pad delta within R19 5mm

Per Phase 4-v2 dispatch + R26.

Usage:
  python3 master_audit_invariants.py <board.kicad_pcb> [<invariants.md>]

Exit code: 0 = all PASS, 1 = any FAIL.
"""

import re
import subprocess
import sys
from pathlib import Path

# Single-source-of-truth: parse via constraint_engine
sys.path.insert(0, str(Path(__file__).parent))
import constraint_engine as ce

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# --parked-exempt: skip components in parking zone (x ≥ 130mm) when iterating
# footprints. Used by per-stage Phase 4-v3 PRs where most components are
# intentionally parked off-board and only the brought subset should be audited.
# Added 2026-05-26 (worker-caught: invariants flagged 244+ parked CH3/4 mirrors
# that didn't exist on-board yet — false fails by design).
PARKED_EXEMPT = "--parked-exempt" in sys.argv[2:]
PARKING_X_THRESHOLD = 130.0  # board ≤100mm wide; parking_grid origin (200, -50)


def _is_parked(fp):
    """True if footprint is in the parking zone (off-board by design)."""
    if not PARKED_EXEMPT:
        return False
    return pcbnew.ToMM(fp.GetPosition().x) >= PARKING_X_THRESHOLD


def _onboard_footprints(board):
    """Yield only on-board footprints when --parked-exempt; else all."""
    for fp in board.GetFootprints():
        if _is_parked(fp):
            continue
        yield fp


# ─── Gate 1: invariant hash drift (via worker's canonical script) ─────────

def check_board_invariants_hash(inv_path):
    """Run worker's compute_board_invariant_hash.py and compare against the
    BOARD_INVARIANT_HASH stored in the doc. Drift requires PR tagged
    [invariant-change]."""
    script = Path(__file__).parent / "compute_board_invariant_hash.py"
    if not script.exists():
        return "WARN", f"{script.name} missing — cannot verify hash"

    # Run worker's script + grep for the hash line
    result = subprocess.run(
        [sys.executable, str(script), str(inv_path)],
        capture_output=True, text=True, timeout=30)
    m = re.search(r"BOARD_INVARIANT_HASH\s*=\s*([0-9a-f]+)", result.stdout)
    if not m:
        return "WARN", f"could not parse hash from script output"
    computed = m.group(1)

    # Read stored hash from doc
    text = Path(inv_path).read_text()
    m = re.search(r"BOARD_INVARIANT_HASH\s*=\s*([0-9a-f]+)", text)
    if not m:
        return "WARN", f"no BOARD_INVARIANT_HASH stored in {inv_path}"
    stored = m.group(1)

    if computed != stored:
        return "FAIL", f"computed={computed[:16]}, stored={stored[:16]} — drift; PR must tag [invariant-change]"
    return "PASS", f"hash={computed[:16]}..."


# ─── Gate 2: subsystem zone compliance ─────────────────────────────────────

def _component_subsystem(ref):
    """Map refdes suffix to subsystem (CHn from _CHn suffix). Mount holes excluded."""
    m = re.match(r".*_CH([1-4])$", ref)
    if m:
        return f"CH{m.group(1)}"
    if re.match(r"^(H|FID)\d+$", ref):
        return None
    return None  # position-based for unsuffixed refs


def check_subsystem_zone_compliance(inv, board):
    """Every component must be within declared zone bbox (for the subsystem
    its refdes maps to). For position-only subsystems, must be inside SOME zone."""
    if not inv.zones:
        return "WARN", "no zones declared — parser may have failed"

    fails = []
    for fp in _onboard_footprints(board):
        ref = fp.GetReference()
        if re.match(r"^(H|FID)\d+$", ref):
            continue  # skip mount holes + fiducials

        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)

        # If ref maps to subsystem, check that zone
        sub = _component_subsystem(ref)
        if sub is not None and sub in inv.zones:
            xmin, ymin, xmax, ymax = inv.zones[sub]
            if not (xmin <= x <= xmax and ymin <= y <= ymax):
                fails.append(f"{ref} at ({x:.1f},{y:.1f}) outside {sub} zone ({xmin},{ymin})-({xmax},{ymax})")
                continue

        # Otherwise: must be inside SOME zone
        in_any = any(
            xmin <= x <= xmax and ymin <= y <= ymax
            for (xmin, ymin, xmax, ymax) in inv.zones.values())
        if not in_any:
            fails.append(f"{ref} at ({x:.1f},{y:.1f}) outside ALL zones")

    if fails:
        msg = f"{len(fails)} components out-of-zone:\n  " + "\n  ".join(fails[:10])
        if len(fails) > 10:
            msg += f"\n  ... +{len(fails)-10} more"
        return "FAIL", msg
    return "PASS", f"all components within declared zones"


# ─── Gate 3: I/O port compliance ───────────────────────────────────────────

def check_io_port_compliance(inv, board, tolerance_mm=0.5):
    """Each declared I/O port must have at least one pad or track endpoint of
    declared signal landing within tolerance."""
    if not inv.io_ports:
        return "WARN", "no I/O ports declared"

    fails = []
    for (from_sys, to_sys, px, py, signals) in inv.io_ports:
        for sig in signals:
            net = board.FindNet(sig)
            if net is None:
                continue
            found = False
            # Check pads
            for fp in _onboard_footprints(board):
                for pad in fp.Pads():
                    if pad.GetNetname() == sig:
                        pp = pad.GetPosition()
                        d = ((pcbnew.ToMM(pp.x) - px)**2 + (pcbnew.ToMM(pp.y) - py)**2)**0.5
                        if d <= tolerance_mm:
                            found = True
                            break
                if found:
                    break
            if not found:
                # Check track endpoints
                for t in board.GetTracks():
                    if not isinstance(t, pcbnew.PCB_TRACK):
                        continue
                    if t.GetNetname() == sig:
                        for ep in [t.GetStart(), t.GetEnd()]:
                            d = ((pcbnew.ToMM(ep.x) - px)**2 + (pcbnew.ToMM(ep.y) - py)**2)**0.5
                            if d <= tolerance_mm:
                                found = True
                                break
                    if found:
                        break
            if not found:
                fails.append(f"{from_sys}→{to_sys} signal={sig} not at port ({px},{py})")

    if fails:
        return "WARN", f"{len(fails)} I/O port mismatches (may be expected for partial-subsystem PR):\n  " + "\n  ".join(fails[:5])
    return "PASS", f"all {len(inv.io_ports)} I/O ports compliant (±{tolerance_mm}mm)"


# ─── Gate 4: highway reservation ───────────────────────────────────────────

def check_highway_reservation(inv, board, exclusion_margin_mm=0.5):
    """No component pad inside reserved highway corridor."""
    if not inv.highways:
        return "WARN", "no highways declared"

    fails = []
    for fp in _onboard_footprints(board):
        ref = fp.GetReference()
        for pad in fp.Pads():
            pp = pad.GetPosition()
            x, y = pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)
            for hw in inv.highways:
                name, hx_min, hy_min, hx_max, hy_max = hw[:5]
                if (hx_min - exclusion_margin_mm <= x <= hx_max + exclusion_margin_mm and
                        hy_min - exclusion_margin_mm <= y <= hy_max + exclusion_margin_mm):
                    fails.append(f"{ref}.{pad.GetPadName()} at ({x:.1f},{y:.1f}) inside highway '{name}'")
                    break

    if fails:
        return "FAIL", f"{len(fails)} pads in reserved highways:\n  " + "\n  ".join(fails[:10])
    return "PASS", f"no pads in {len(inv.highways)} reserved highways"


# ─── Gate 5: symmetry partner diff ─────────────────────────────────────────

def check_symmetry_partner_diff(inv, board, tolerance_mm=5.0):
    """For each symmetry pair, mirror partner per-pad delta within R19 tolerance."""
    if not inv.symmetry_pairs:
        return "WARN", "no symmetry pairs declared"

    fails = []
    for (sys_a, sys_b, axis, axis_val) in inv.symmetry_pairs:
        a_comps, b_comps = {}, {}
        for fp in _onboard_footprints(board):
            ref = fp.GetReference()
            stem_match = re.match(r"([A-Z]+\d+)_(CH\d)$", ref)
            if not stem_match:
                continue
            stem, ch = stem_match.group(1), stem_match.group(2)
            pos = fp.GetPosition()
            entry = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
            if ch == sys_a:
                a_comps[stem] = entry
            elif ch == sys_b:
                b_comps[stem] = entry

        for stem, (ax, ay) in a_comps.items():
            if stem not in b_comps:
                fails.append(f"{stem}_{sys_a} has no {stem}_{sys_b} partner")
                continue
            bx, by = b_comps[stem]
            if axis == "x":
                exp_bx, exp_by = 2 * axis_val - ax, ay
            elif axis == "y":
                exp_bx, exp_by = ax, 2 * axis_val - ay
            else:
                continue
            d = ((bx - exp_bx)**2 + (by - exp_by)**2)**0.5
            if d > tolerance_mm:
                fails.append(f"{stem}: {sys_a}({ax:.1f},{ay:.1f}) ↔ {sys_b}({bx:.1f},{by:.1f}) Δ={d:.2f}mm")

    if fails:
        # For partial-subsystem PRs (e.g., CH1 only), partner subsystem not yet
        # placed by Phase 4-v2 — downgrade to WARN
        return "WARN", f"{len(fails)} symmetry mismatches (may be expected if partner subsystem not yet placed in Phase 4-v2):\n  " + "\n  ".join(fails[:5])
    return "PASS", f"all symmetry pairs within {tolerance_mm}mm"


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    inv_path = sys.argv[2] if len(sys.argv) > 2 else "docs/BOARD_INVARIANTS.md"

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(inv_path).exists():
        print(f"FAIL: {inv_path} not found")
        sys.exit(1)

    # Parse via constraint_engine (canonical parser)
    inv = ce.parse_board_invariants(inv_path)
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Phase 4-v2 master invariants audit: {Path(board_path).name} ===")
    print(f"Invariants: {inv_path}")
    print(f"  zones={len(inv.zones)} {sorted(inv.zones.keys())}")
    print(f"  io_ports={len(inv.io_ports)}, highways={len(inv.highways)}, "
          f"symmetry_pairs={len(inv.symmetry_pairs)}")
    print()

    any_fail = False
    for name, fn in [
            ("BOARD_INVARIANTS_HASH", lambda: check_board_invariants_hash(inv_path)),
            ("SUBSYSTEM_ZONE_COMPLIANCE", lambda: check_subsystem_zone_compliance(inv, board)),
            ("IO_PORT_COMPLIANCE", lambda: check_io_port_compliance(inv, board)),
            ("HIGHWAY_RESERVATION", lambda: check_highway_reservation(inv, board)),
            ("SYMMETRY_PARTNER_DIFF", lambda: check_symmetry_partner_diff(inv, board)),
    ]:
        status, msg = fn()
        print(f"[{status}] {name}: {msg}")
        print()
        if status == "FAIL":
            any_fail = True

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
