#!/usr/bin/env python3
"""test_emit_blind_f_in2.py — synthetic test for OQ-020 emitter patch (v8).

Verifies the route_subsystem_cooperative.emit_to_board() v8 patch (Phase 3
emitter gap fix; PR #227 diagnosis):
  (1) WHITELIST POSITIVE: emit_to_board called with target_pair=(F.Cu, In2.Cu)
      at an HDI cell for a BLIND_F_IN2_NET_WHITELIST net produces a via with:
        - VIATYPE_BLIND_BURIED
        - Layer pair F.Cu ↔ In2.Cu
        - Drill 0.15mm, pad 0.30mm
  (2) NEGATIVE: emit_to_board called with target_pair=(F.Cu, In2.Cu) at an
      HDI cell for a NON-whitelisted net REFUSES (raises ValueError) — the
      router MUST NOT silently fall through to THROUGH F↔B (the v6/v7
      shorts lesson).
  (3) NO REGRESSION: emit_to_board still emits VIATYPE_MICROVIA for
      (F.Cu, In1.Cu) and (B.Cu, In8.Cu) at HDI cells; VIATYPE_THROUGH for
      non-HDI cells.
  (4) WHITELIST + AUDIT: the emitted blind-F-In2 via saved to a temp board
      passes `audit_hdi_via_in_pad.py` when placed inside a J18/J19 pad
      bbox on the canonical placed board (OQ020_TEST_BOARD env override).
  (5) PER-NET WHITELIST SSoT: route_subsystem_cooperative.blind_f_in2_net_whitelist()
      returns the SAME tuple as audit_hdi_via_in_pad.BLIND_F_IN2_NET_WHITELIST
      (the single source of truth; mirrors run_on_board.py import pattern).

Per [[feedback-codify-not-patch]]: ships with the v8 patch as the master-
independent regression test. Per [[feedback-sim-execution-gate]] / [[feedback-
coord-pr-must-simulate-placement]]: this is the EMITTER analog of the layer-
aware-supply T12/T14 engine fixture — verifies via emission cannot drift
from the audit's whitelist enforcement.

Build pattern: a SyntheticGrid stub that satisfies the minimal interface
emit_to_board uses (xy_to_ij + hdi_via_cells lookup). No live .kicad_pcb
modification; all tests run on tempfile copies of pcbai_fpv4in1.kicad_pcb
to preserve the canonical board (R-sim-provenance equivalent).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add scripts dir to sys.path so we can import the router as a module.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import pcbnew
except ImportError:
    print("SKIP: pcbnew not importable (must run under KiCad-bundled python)")
    sys.exit(0)

import route_subsystem_cooperative as rsc
from route_subsystem_cooperative import (
    emit_to_board, via_class_for_span, via_span_layers,
    blind_f_in2_net_whitelist,
    F_CU, B_CU, IN1_CU, IN2_CU, IN8_CU, IN4_CU,
    BLIND_F_IN2_DRILL_MM, BLIND_F_IN2_DIAM_MM,
    HDI_VIA_DRILL_MM, HDI_VIA_DIAM_MM,
    VIA_DRILL_MM, VIA_DIAM_MM,
)
import audit_hdi_via_in_pad as audit_mod


CANONICAL_BOARD = HERE.parent / "pcbai_fpv4in1.kicad_pcb"
PLACED_BOARD = Path(os.environ.get("OQ020_TEST_BOARD",
                                    str(CANONICAL_BOARD)))


class SyntheticGrid:
    """Minimal grid stub for emit_to_board's hdi_via_cells lookup. The
    emitter only calls .xy_to_ij(x, y) on the grid + reads hdi_via_cells
    (a dict of (i, j) -> owner_net). We pin (i, j) = (0, 0) and put the
    via at (0, 0) so the HDI lookup hits."""
    def __init__(self, is_hdi=False):
        # Map any (x, y) to (0, 0) deterministically.
        self.hdi_via_cells = {(0, 0): "anyowner"} if is_hdi else {}

    def xy_to_ij(self, x, y):
        return (0, 0)


def _ensure_net(board, name):
    n = board.FindNet(name)
    if n is None or n.GetNetCode() == 0:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
    return n


def _emit_one(board, net_name, x_mm, y_mm, l_from, l_to, is_hdi):
    """Call emit_to_board with ONE via and return (via_obj, added_items)
    or (None, exception_str) on raise."""
    net_obj = _ensure_net(board, net_name)
    grid = SyntheticGrid(is_hdi=is_hdi)
    segments = []
    vias = [(x_mm, y_mm)]
    via_target_layers = {(round(x_mm, 3), round(y_mm, 3)): (l_from, l_to)}
    added = []
    try:
        emit_to_board(board, segments, vias, net_obj, width_mm=0.15,
                       added_items=added,
                       hdi_via_cells=grid.hdi_via_cells, grid=grid,
                       via_target_layers=via_target_layers)
    except ValueError as e:
        return None, str(e)
    via_obj = [it for it in added if isinstance(it, pcbnew.PCB_VIA)]
    return (via_obj[0] if via_obj else None), None


def test_classifier_ssoT():
    """(5) Classifier reads the same whitelist as the audit.

    2026-05-28 lever D extension: whitelist grew 4 → 5 nets (added GLB_CH1).
    The SSoT check asserts strict equality between router + audit + count == 5
    so any future drift (e.g. router-side hard-code, audit-side typo) fails
    fast. The 7-landing per-pin roster is documentary
    (BLIND_F_IN2_SANCTIONED_LANDINGS) — DRU + audit are net-name only."""
    router_wl = set(blind_f_in2_net_whitelist())
    audit_wl = set(audit_mod.BLIND_F_IN2_NET_WHITELIST)
    expected = {"BSTB_CH1", "PWM_INHB_CH1", "SWDIO_CH1", "PWM_INLA_CH1",
                "GLB_CH1"}
    ok = router_wl == audit_wl == expected and len(router_wl) == 5
    print(f"  [{'OK' if ok else 'BAD'}] SSoT: router whitelist == audit "
          f"whitelist = {sorted(router_wl)} (expected 5; "
          f"lever D added GLB_CH1)")
    return ok


def test_classifier_table():
    """Classifier produces the documented per-class verdicts."""
    cases = [
        # (L_from, L_to, net, is_hdi, expected)
        (F_CU, IN1_CU, "ANY",         True,  "microvia_F_In1"),
        (IN1_CU, F_CU, "ANY",         True,  "microvia_F_In1"),
        (B_CU, IN8_CU, "ANY",         True,  "microvia_B_In8"),
        (IN8_CU, B_CU, "ANY",         True,  "microvia_B_In8"),
        (F_CU, IN2_CU, "BSTB_CH1",    True,  "blind_F_In2"),
        (F_CU, IN2_CU, "PWM_INHB_CH1",True,  "blind_F_In2"),
        (F_CU, IN2_CU, "SWDIO_CH1",   True,  "blind_F_In2"),
        (F_CU, IN2_CU, "PWM_INLA_CH1",True,  "blind_F_In2"),
        (IN2_CU, F_CU, "BSTB_CH1",    True,  "blind_F_In2"),
        # 2026-05-28 lever D: GLB_CH1 added to net whitelist.
        (F_CU, IN2_CU, "GLB_CH1",     True,  "blind_F_In2"),
        (IN2_CU, F_CU, "GLB_CH1",     True,  "blind_F_In2"),
        # Non-whitelisted nets at HDI cell with F-In2 span = REFUSED.
        (F_CU, IN2_CU, "FOOBAR_CH1",  True,  None),
        (F_CU, IN2_CU, "BSTB",        True,  None),    # missing _CH1 suffix
        (F_CU, IN2_CU, "GLA_CH1",     True,  None),    # GLA NOT in WL (only GLB)
        (F_CU, IN2_CU, "GLC_CH1",     True,  None),    # GLC NOT in WL (only GLB)
        # Other HDI spans = REFUSED (e.g. F-In4, F-In8, In2-B).
        (F_CU, IN4_CU, "ANY",         True,  None),
        (F_CU, B_CU,   "ANY",         True,  None),
        (IN2_CU, IN8_CU, "ANY",       True,  None),
        # Non-HDI cell: any span = through.
        (F_CU, B_CU,   "ANY",         False, "through"),
        (F_CU, IN2_CU, "ANY",         False, "through"),  # non-HDI: no refusal
        (IN4_CU, IN8_CU, "ANY",       False, "through"),
    ]
    ok = True
    for (lf, lt, n, hdi, exp) in cases:
        got = via_class_for_span(lf, lt, n, hdi)
        good = got == exp
        ok &= good
        if not good:
            print(f"  [BAD] via_class_for_span({lf},{lt},{n!r},hdi={hdi}) "
                  f"= {got!r}, expected {exp!r}")
    print(f"  [{'OK' if ok else 'BAD'}] classifier table: {len(cases)} cases")
    return ok


def test_span_layers():
    """via_span_layers returns the documented per-class barrel layers."""
    assert via_span_layers('through') == tuple(rsc.ALL_COPPER_LAYERS)
    assert via_span_layers('microvia_F_In1') == (F_CU, IN1_CU)
    assert via_span_layers('microvia_B_In8') == (IN8_CU, B_CU)
    assert via_span_layers('blind_F_In2') == (F_CU, IN1_CU, IN2_CU)
    try:
        via_span_layers(None)
        print("  [BAD] via_span_layers(None) should have raised")
        return False
    except ValueError:
        pass
    print("  [OK] via_span_layers: all 4 sanctioned classes return correct "
          "barrel; None raises ValueError")
    return True


def test_emit_whitelist_blind_f_in2():
    """(1) WHITELIST POSITIVE — emit at HDI cell for whitelisted net."""
    board = pcbnew.LoadBoard(str(PLACED_BOARD))
    via, err = _emit_one(board, "BSTB_CH1", x_mm=33.0, y_mm=68.438,
                          l_from=F_CU, l_to=IN2_CU, is_hdi=True)
    if err:
        print(f"  [BAD] whitelist emit raised: {err}")
        return False
    if via is None:
        print("  [BAD] whitelist emit produced no via")
        return False
    vt = via.GetViaType()
    layer_top, layer_bot = via.TopLayer(), via.BottomLayer()
    drill_mm = via.GetDrill() / 1e6
    ok_type = vt == pcbnew.VIATYPE_BLIND_BURIED
    ok_layers = {layer_top, layer_bot} == {F_CU, IN2_CU}
    ok_drill = abs(drill_mm - BLIND_F_IN2_DRILL_MM) < 1e-6
    # Pad diameter is set per-layer; sample F.Cu.
    try:
        pad_mm = via.GetWidth(F_CU) / 1e6
    except TypeError:
        pad_mm = via.GetWidth() / 1e6
    ok_pad = abs(pad_mm - BLIND_F_IN2_DIAM_MM) < 1e-6
    ok = ok_type and ok_layers and ok_drill and ok_pad
    print(f"  [{'OK' if ok else 'BAD'}] (1) WHITELIST POSITIVE (BSTB_CH1, "
          f"F.Cu↔In2.Cu HDI): VIATYPE={vt} (exp {pcbnew.VIATYPE_BLIND_BURIED}), "
          f"layers={{{layer_top},{layer_bot}}}, drill={drill_mm}mm, "
          f"pad={pad_mm}mm")
    return ok


def test_emit_all_4_whitelist_nets():
    """(1+5) All 7 sanctioned (net, pin) landings emit BLIND_BURIED F.Cu↔In2.

    2026-05-28 lever D extension: added 3 J19-pin landings —
      - PWM_INHB_CH1 @ J19.23 (partner of J18.19; net already net-WL)
      - PWM_INLA_CH1 @ J19.1  (partner of J18.15; net already net-WL)
      - GLB_CH1      @ J19.10 (NEW net + NEW pin; closes J19_S residual)
    All 7 landings must emit VIATYPE_BLIND_BURIED + F.Cu↔In2.Cu pair +
    drill 0.15mm / pad 0.30mm. Pin coordinates verified on canonical
    placed board (env OQ020_TEST_BOARD)."""
    cases = [
        # --- original 4 (locked 2026-05-28 OQ-020 ACTIVATE) ---
        ("BSTB_CH1",    "J19.17", 26.137, 61.770),
        ("PWM_INHB_CH1","J18.19", 34.188, 66.750),
        ("SWDIO_CH1",   "J18.23", 34.188, 64.750),
        ("PWM_INLA_CH1","J18.15", 33.000, 68.438),
        # --- 2026-05-28 lever D additions (3 J19-end pins) ---
        ("PWM_INHB_CH1","J19.23", 23.450, 60.582),
        ("PWM_INLA_CH1","J19.1",  22.262, 61.270),
        ("GLB_CH1",     "J19.10", 24.450, 64.457),
    ]
    ok = True
    breakdown = []
    for (net, pad_label, x, y) in cases:
        board = pcbnew.LoadBoard(str(PLACED_BOARD))
        via, err = _emit_one(board, net, x, y, F_CU, IN2_CU, is_hdi=True)
        if err or via is None:
            ok = False
            breakdown.append(f"{net}@{pad_label}: FAIL ({err or 'no via'})")
            continue
        vt = via.GetViaType()
        good = (vt == pcbnew.VIATYPE_BLIND_BURIED and
                {via.TopLayer(), via.BottomLayer()} == {F_CU, IN2_CU})
        # Geometry check: drill 0.15mm + pad 0.30mm (the OQ-020 spec).
        drill_mm = via.GetDrill() / 1e6
        try:
            pad_mm = via.GetWidth(F_CU) / 1e6
        except TypeError:
            pad_mm = via.GetWidth() / 1e6
        good_geom = (abs(drill_mm - BLIND_F_IN2_DRILL_MM) < 1e-6 and
                     abs(pad_mm - BLIND_F_IN2_DIAM_MM) < 1e-6)
        good &= good_geom
        ok &= good
        breakdown.append(
            f"{net}@{pad_label}: VIATYPE={vt}=BLIND_BURIED, "
            f"layers=({via.TopLayer()},{via.BottomLayer()})=F↔In2, "
            f"drill={drill_mm}mm, pad={pad_mm}mm "
            f"{'OK' if good else 'BAD'}")
    print(f"  [{'OK' if ok else 'BAD'}] (1+5) ALL 7 SANCTIONED LANDINGS "
          f"(5 nets × 7 pins; lever D 2026-05-28) emit BLIND_BURIED F.Cu↔In2:")
    for line in breakdown:
        print(f"      {line}")
    return ok


def test_emit_negative_non_whitelist():
    """(2) NEGATIVE: non-whitelist net + HDI cell + F↔In2 = REFUSED."""
    board = pcbnew.LoadBoard(str(PLACED_BOARD))
    via, err = _emit_one(board, "FOOBAR_CH1", x_mm=33.0, y_mm=68.438,
                          l_from=F_CU, l_to=IN2_CU, is_hdi=True)
    refused = (via is None and err is not None
               and "refused" in err.lower())
    print(f"  [{'OK' if refused else 'BAD'}] (2) NEGATIVE (FOOBAR_CH1, "
          f"F.Cu↔In2.Cu HDI): refused={refused}, "
          f"err={err[:80] if err else 'NO ERR'!r}")
    return refused


def test_emit_negative_audit_catches_forced():
    """(2 + 4) If a non-whitelist blind F-In2 via is force-saved (bypassing
    the router), audit_hdi_via_in_pad.py FAILS — proves the whitelist scope
    is binding end-to-end (DRU + audit + router are aligned)."""
    # Build a board with a manually-injected non-whitelist blind F-In2.
    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        board = pcbnew.LoadBoard(str(PLACED_BOARD))
        net = _ensure_net(board, "FOOBAR_CH1")
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_BLIND_BURIED)
        via.SetPosition(pcbnew.VECTOR2I(int(33.0 * 1e6), int(68.438 * 1e6)))
        via.SetLayerPair(F_CU, IN2_CU)
        via.SetDrill(int(BLIND_F_IN2_DRILL_MM * 1e6))
        try:
            via.SetWidth(int(BLIND_F_IN2_DIAM_MM * 1e6), F_CU)
        except (TypeError, Exception):
            via.SetWidth(int(BLIND_F_IN2_DIAM_MM * 1e6))
        via.SetNet(net)
        board.Add(via)
        pcbnew.SaveBoard(str(tmp_path), board)
        res = subprocess.run(
            [sys.executable, str(HERE / "audit_hdi_via_in_pad.py"), str(tmp_path)],
            capture_output=True, text=True, timeout=60)
        # Expect audit FAIL (exit 1) for the off-whitelist blind F-In2.
        ok = res.returncode == 1
        print(f"  [{'OK' if ok else 'BAD'}] (2+4) audit rejects FORCED "
              f"off-whitelist blind F-In2 via: returncode={res.returncode} "
              f"(expected 1=FAIL)")
        return ok
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def test_emit_audit_accepts_whitelist():
    """(4) Emitted blind-F-In2 via on whitelist net inside J18/J19 pad bbox
    passes audit_hdi_via_in_pad.py. Uses the FULL emit_to_board pipeline."""
    if not (CANONICAL_BOARD.exists() or PLACED_BOARD.exists()):
        print("  [SKIP] (4) no canonical board to validate audit acceptance")
        return True
    # Need a board where J18 has pad 15 near (33.000, 68.438).
    pb = pcbnew.LoadBoard(str(PLACED_BOARD))
    has_j18 = False
    for fp in pb.GetFootprints():
        if fp.GetReference() == "J18":
            for pad in fp.Pads():
                if pad.GetPadName() == "15":
                    p = pad.GetPosition()
                    if abs(p.x / 1e6 - 33.0) < 1.0 and abs(p.y / 1e6 - 68.438) < 1.0:
                        has_j18 = True
                        break
    if not has_j18:
        print("  [SKIP] (4) PLACED_BOARD lacks J18 at (33.000, 68.438) — "
              "set OQ020_TEST_BOARD to canonical placed board to exercise")
        return True
    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        board = pcbnew.LoadBoard(str(PLACED_BOARD))
        via, err = _emit_one(board, "PWM_INLA_CH1", x_mm=33.0, y_mm=68.438,
                              l_from=F_CU, l_to=IN2_CU, is_hdi=True)
        if err or via is None:
            print(f"  [BAD] (4) emit failed: {err or 'no via'}")
            return False
        pcbnew.SaveBoard(str(tmp_path), board)
        res = subprocess.run(
            [sys.executable, str(HERE / "audit_hdi_via_in_pad.py"), str(tmp_path)],
            capture_output=True, text=True, timeout=60)
        ok = res.returncode == 0
        if not ok:
            for ln in res.stdout.splitlines()[-20:]:
                print(f"      {ln}")
        print(f"  [{'OK' if ok else 'BAD'}] (4) audit accepts EMITTED "
              f"whitelist blind F-In2 (PWM_INLA_CH1 @ J18.15): "
              f"returncode={res.returncode} (expected 0=PASS)")
        return ok
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def test_emit_no_regression():
    """(3) NO REGRESSION: microvia F-In1 / microvia B-In8 / through still
    emit correctly with their existing geometry."""
    board = pcbnew.LoadBoard(str(PLACED_BOARD))
    ok = True
    breakdown = []

    # F↔In1 at HDI cell → MICROVIA, 0.10/0.25mm.
    v, err = _emit_one(board, "MICROVIA_F_IN1_TEST", 30.0, 50.0,
                        F_CU, IN1_CU, is_hdi=True)
    good = (err is None and v is not None and
            v.GetViaType() == pcbnew.VIATYPE_MICROVIA and
            {v.TopLayer(), v.BottomLayer()} == {F_CU, IN1_CU} and
            abs(v.GetDrill() / 1e6 - HDI_VIA_DRILL_MM) < 1e-6)
    ok &= good
    breakdown.append(f"F↔In1 HDI microvia: {'OK' if good else 'BAD'} (type="
                     f"{v.GetViaType() if v else 'NONE'}, "
                     f"drill={(v.GetDrill()/1e6) if v else 'NONE'}mm)")

    # B↔In8 at HDI cell → MICROVIA, 0.10/0.25mm.
    v, err = _emit_one(board, "MICROVIA_B_IN8_TEST", 30.1, 50.1,
                        B_CU, IN8_CU, is_hdi=True)
    good = (err is None and v is not None and
            v.GetViaType() == pcbnew.VIATYPE_MICROVIA and
            {v.TopLayer(), v.BottomLayer()} == {B_CU, IN8_CU} and
            abs(v.GetDrill() / 1e6 - HDI_VIA_DRILL_MM) < 1e-6)
    ok &= good
    breakdown.append(f"B↔In8 HDI microvia: {'OK' if good else 'BAD'} (type="
                     f"{v.GetViaType() if v else 'NONE'}, "
                     f"drill={(v.GetDrill()/1e6) if v else 'NONE'}mm)")

    # Non-HDI cell, any span → THROUGH, 0.30/0.60mm.
    v, err = _emit_one(board, "THROUGH_TEST", 30.2, 50.2,
                        F_CU, IN4_CU, is_hdi=False)
    good = (err is None and v is not None and
            v.GetViaType() == pcbnew.VIATYPE_THROUGH and
            abs(v.GetDrill() / 1e6 - VIA_DRILL_MM) < 1e-6)
    ok &= good
    breakdown.append(f"non-HDI through: {'OK' if good else 'BAD'} (type="
                     f"{v.GetViaType() if v else 'NONE'}, "
                     f"drill={(v.GetDrill()/1e6) if v else 'NONE'}mm)")

    print(f"  [{'OK' if ok else 'BAD'}] (3) NO REGRESSION on existing classes:")
    for line in breakdown:
        print(f"      {line}")
    return ok


def main():
    if not PLACED_BOARD.exists():
        print(f"FAIL: board {PLACED_BOARD} not found")
        return 1
    print("=" * 72)
    print("test_emit_blind_f_in2 — synthetic OQ-020 EMITTER patch (v8)")
    print(f"  board: {PLACED_BOARD}")
    print(f"  audit: {HERE / 'audit_hdi_via_in_pad.py'}")
    print("=" * 72)
    results = []
    results.append(("classifier SSoT (5)", test_classifier_ssoT()))
    results.append(("classifier table", test_classifier_table()))
    results.append(("via_span_layers", test_span_layers()))
    results.append(("(1) WHITELIST blind F-In2", test_emit_whitelist_blind_f_in2()))
    results.append(("(1+5) all 7 WL landings (4 orig + 3 lever D)",
                    test_emit_all_4_whitelist_nets()))
    results.append(("(2) NEGATIVE refuse", test_emit_negative_non_whitelist()))
    results.append(("(2+4) audit catches forced off-WL",
                    test_emit_negative_audit_catches_forced()))
    results.append(("(4) audit accepts emitted WL", test_emit_audit_accepts_whitelist()))
    results.append(("(3) NO REGRESSION", test_emit_no_regression()))
    print("=" * 72)
    n_pass = sum(1 for (_, p) in results if p)
    n = len(results)
    for (name, p) in results:
        print(f"  {'PASS' if p else 'FAIL'}: {name}")
    print("=" * 72)
    if n_pass == n:
        print(f"RESULT: PASS — {n_pass}/{n} tests pass; OQ-020 EMITTER (v8 + "
              f"2026-05-28 lever D) correctly emits BLIND_BURIED F.Cu↔In2 "
              f"for all 5 whitelist nets at all 7 sanctioned landings, "
              f"REFUSES non-whitelist spans, and preserves existing via classes.")
        return 0
    print(f"RESULT: FAIL — {n_pass}/{n} tests pass; OQ-020 EMITTER (v8) has "
          f"regressions; see [BAD] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
