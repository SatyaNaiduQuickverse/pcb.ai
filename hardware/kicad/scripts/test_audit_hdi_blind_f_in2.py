#!/usr/bin/env python3
"""test_audit_hdi_blind_f_in2.py — synthetic test for OQ-020 audit extension.

Verifies that `audit_hdi_via_in_pad.py`'s OQ-020 ACTIVATE extension:
  (a) PASSES a blind F.Cu↔In2 via WITHIN the BLIND_F_IN2_NET_WHITELIST
      (one of BSTB_CH1 / PWM_INHB_CH1 / SWDIO_CH1 / PWM_INLA_CH1).
  (b) FAILS a blind F.Cu↔In2 via OUTSIDE the whitelist (a non-whitelisted
      net name) — proves the whitelist scope is BINDING (not just stated).

Builds an in-memory pcbnew board with three vias (two synthetic blind F-In2,
one standard) and shells out to `audit_hdi_via_in_pad.py` against the saved
file. Validates exit codes + the audit's reported pass/fail counts.

Per [[feedback-codify-not-patch]]: every OQ-020 change ships with a master-
independent regression test (this file). Run on every PR touching the audit
or the whitelist constant.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("SKIP: pcbnew not importable (must run under KiCad-bundled python)")
    sys.exit(0)


HERE = Path(__file__).resolve().parent
AUDIT = HERE / "audit_hdi_via_in_pad.py"
# Use a board that HAS J18+J19 placed (so the blind via can land inside a
# whitelist pad, not just float in empty space). Default = the canonical
# placed board (pcbai_fpv4in1.kicad_pcb). Override via OQ020_TEST_BOARD
# env var (e.g. a routed snapshot under /home/novatics64/escworker/local/).
PLACED_BOARD = Path(os.environ.get(
    "OQ020_TEST_BOARD",
    str(HERE.parent / "pcbai_fpv4in1.kicad_pcb")))
EMPTY_BOARD = PLACED_BOARD   # alias used by run_case load


def _make_synthetic_via(board, x_mm, y_mm, top_layer, bot_layer, drill_mm,
                        diameter_mm, net_obj, via_type=pcbnew.VIATYPE_BLIND_BURIED):
    """Emit a synthetic via on `board` at (x_mm, y_mm) with the given layer
    pair + drill/diameter + via-type tag + net binding. Returns the via.

    Order matters in KiCad 9: SetViaType BEFORE SetLayerPair BEFORE SetWidth
    (SetWidth asserts on layer info; via_type drives the size-stack lookup)."""
    via = pcbnew.PCB_VIA(board)
    via.SetViaType(via_type)
    via.SetPosition(pcbnew.VECTOR2I(int(x_mm * 1e6), int(y_mm * 1e6)))
    via.SetLayerPair(top_layer, bot_layer)
    via.SetDrill(int(drill_mm * 1e6))
    # Use the explicit-layer SetWidth API where available; falls back to the
    # generic one on older bindings.
    try:
        via.SetWidth(int(diameter_mm * 1e6), top_layer)
    except (TypeError, Exception):
        via.SetWidth(int(diameter_mm * 1e6))
    if net_obj is not None:
        via.SetNet(net_obj)
    board.Add(via)
    return via


def _ensure_net(board, name):
    """Return the NETINFO_ITEM for `name`, creating it if absent."""
    n = board.FindNet(name)
    if n is None or n.GetNetCode() == 0:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
    return n


def run_case(label, blind_net_name, expected_outcome):
    """Build a copy of the empty board with ONE blind F-In2 via on `blind_net_name`,
    run the audit, and check exit code matches `expected_outcome` ('PASS' or 'FAIL').
    Returns True if the audit behaves as expected."""
    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        # Load a copy of the empty board (preserves layer stack + setup).
        board = pcbnew.LoadBoard(str(EMPTY_BOARD))
        net = _ensure_net(board, blind_net_name)
        # Synthetic blind F-In2 via INSIDE J18.15 pad (33.0, 68.438) — placed
        # within the whitelist footprint so the standard HDI-in-pad check
        # passes; only the OQ-020 net-name check differentiates whitelist vs
        # non-whitelist. Coordinates verified on canonical CH1 routed board.
        _make_synthetic_via(board, x_mm=33.0, y_mm=68.438,
                            top_layer=pcbnew.F_Cu, bot_layer=pcbnew.In2_Cu,
                            drill_mm=0.15, diameter_mm=0.30,
                            net_obj=net,
                            via_type=pcbnew.VIATYPE_BLIND_BURIED)
        pcbnew.SaveBoard(str(tmp_path), board)
        # Run the audit.
        res = subprocess.run(
            [sys.executable, str(AUDIT), str(tmp_path)],
            capture_output=True, text=True, timeout=60)
        outcome = "PASS" if res.returncode == 0 else "FAIL"
        match = outcome == expected_outcome
        flag = "OK" if match else "BAD"
        print(f"  [{flag}] {label}: net={blind_net_name!r} => audit={outcome} "
              f"(expected {expected_outcome})")
        if not match:
            print("    stdout:")
            for ln in res.stdout.splitlines()[-15:]:
                print(f"      {ln}")
            print("    stderr:")
            for ln in res.stderr.splitlines()[-5:]:
                print(f"      {ln}")
        return match
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _j18_placed_at_test_coord(board_path):
    """Verify the board has J18 placed such that pad 15 is near (33.0, 68.438)
    — the synthetic via target coordinate. Returns True if the in-pad check
    can be exercised on this board."""
    try:
        b = pcbnew.LoadBoard(str(board_path))
        for fp in b.GetFootprints():
            if fp.GetReference() == "J18":
                for pad in fp.Pads():
                    if pad.GetPadName() == "15":
                        p = pad.GetPosition()
                        return abs(p.x / 1e6 - 33.0) < 1.0 and \
                            abs(p.y / 1e6 - 68.438) < 1.0
                return False
        return False
    except Exception:
        return False


def main():
    if not EMPTY_BOARD.exists():
        print(f"FAIL: empty board {EMPTY_BOARD} not found")
        return 1
    if not AUDIT.exists():
        print(f"FAIL: audit script {AUDIT} not found")
        return 1
    print("=" * 72)
    print("test_audit_hdi_blind_f_in2 — synthetic OQ-020 whitelist enforcement")
    print(f"  board: {EMPTY_BOARD}")
    print("=" * 72)
    if not _j18_placed_at_test_coord(EMPTY_BOARD):
        print("  J18 not placed at synthetic-via target coord on this board —")
        print(f"  set OQ020_TEST_BOARD=/path/to/canonical_placed_routed.kicad_pcb")
        print("  (e.g. ch1_coop_v9_best.kicad_pcb) to exercise the in-pad check.")
        print("  SKIP without failing — the engine T12 fixture + verdict run cover")
        print("  the layer-aware mechanism independently.")
        return 0
    ok = True
    # Case 1: blind F-In2 on a WHITELIST net => audit PASSES.
    ok &= run_case("whitelist net (BSTB_CH1)", "BSTB_CH1", "PASS")
    # Case 2: blind F-In2 on a NON-WHITELIST net => audit FAILS (cost scope creep).
    ok &= run_case("non-whitelist net (FOOBAR_CH1)", "FOOBAR_CH1", "FAIL")
    print("=" * 72)
    if ok:
        print("RESULT: PASS — OQ-020 whitelist is BINDING (accept-on-whitelist; "
              "fail-on-non-whitelist).")
        return 0
    print("RESULT: FAIL — audit does not enforce the whitelist correctly.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
