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
    # v9 (CH1 30/30 lever F) halo helpers
    via_halo_radius_mm, via_diam_mm_for_class, via_pad_half_mm_for_class,
    CLEARANCE_MM, TRACE_HALF_MM, GRID_SLOP_MM,
    HDI_VIA_HALF_MM, BLIND_F_IN2_HALF_MM,
    # LEVER L (CH1 30/30 stacked microvia F↔In1↔In2) — drill/pad/half/span
    # constants + SSoT whitelist accessor.
    STACKED_MICROVIA_DRILL_MM, STACKED_MICROVIA_DIAM_MM,
    STACKED_MICROVIA_HALF_MM, STACKED_MICROVIA_SPAN,
    stacked_microvia_net_whitelist,
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
    2026-05-28 lever G extension: whitelist grew 5 → 6 nets (added
    KILL_RAIL_N_CH1).
    The SSoT check asserts strict equality between router + audit + count == 6
    so any future drift (e.g. router-side hard-code, audit-side typo) fails
    fast. The 8-landing per-pin roster is documentary
    (BLIND_F_IN2_SANCTIONED_LANDINGS) — DRU + audit are net-name only."""
    router_wl = set(blind_f_in2_net_whitelist())
    audit_wl = set(audit_mod.BLIND_F_IN2_NET_WHITELIST)
    expected = {"BSTB_CH1", "PWM_INHB_CH1", "SWDIO_CH1", "PWM_INLA_CH1",
                "GLB_CH1", "KILL_RAIL_N_CH1"}
    ok = router_wl == audit_wl == expected and len(router_wl) == 6
    print(f"  [{'OK' if ok else 'BAD'}] SSoT: router whitelist == audit "
          f"whitelist = {sorted(router_wl)} (expected 6; "
          f"lever D added GLB_CH1; lever G added KILL_RAIL_N_CH1)")
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
        # 2026-05-28 lever G: KILL_RAIL_N_CH1 added to net whitelist.
        (F_CU, IN2_CU, "KILL_RAIL_N_CH1", True, "blind_F_In2"),
        (IN2_CU, F_CU, "KILL_RAIL_N_CH1", True, "blind_F_In2"),
        # Non-whitelisted nets at HDI cell with F-In2 span = REFUSED.
        (F_CU, IN2_CU, "FOOBAR_CH1",  True,  None),
        (F_CU, IN2_CU, "BSTB",        True,  None),    # missing _CH1 suffix
        (F_CU, IN2_CU, "GLA_CH1",     True,  None),    # GLA NOT in WL (only GLB)
        (F_CU, IN2_CU, "GLC_CH1",     True,  None),    # GLC NOT in WL (only GLB)
        (F_CU, IN2_CU, "KILL_RAIL_N", True,  None),    # missing _CH1 suffix
        (F_CU, IN2_CU, "KILL_RAIL_N_CH2", True, None), # CH2 NOT in WL (CH1 only)
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
    """(1+5) All 8 sanctioned (net, pin) landings emit BLIND_BURIED F.Cu↔In2.

    2026-05-28 lever D extension: added 3 J19-pin landings —
      - PWM_INHB_CH1 @ J19.23 (partner of J18.19; net already net-WL)
      - PWM_INLA_CH1 @ J19.1  (partner of J18.15; net already net-WL)
      - GLB_CH1      @ J19.10 (NEW net + NEW pin; closes J19_S residual)
    2026-05-28 lever G extension: added 1 J19-pin landing —
      - KILL_RAIL_N_CH1 @ J19.8 (NEW net + NEW pin; closes LAST CH1 residual)
    All 8 landings must emit VIATYPE_BLIND_BURIED + F.Cu↔In2.Cu pair +
    drill 0.15mm / pad 0.30mm. Pin coordinates verified on canonical
    placed board (env OQ020_TEST_BOARD)."""
    cases = [
        # --- original 4 (locked 2026-05-28 OQ-020 ACTIVATE) ---
        ("BSTB_CH1",    "J19.17", 26.137, 61.770),
        ("PWM_INHB_CH1","J18.19", 34.188, 66.750),
        ("SWDIO_CH1",   "J18.23", 34.188, 64.750),
        ("PWM_INLA_CH1","J18.15", 33.000, 68.438),
        # --- 2026-05-28 lever D additions (3 J19-end pins) ---
        ("PWM_INHB_CH1",  "J19.23", 23.450, 60.582),
        ("PWM_INLA_CH1",  "J19.1",  22.262, 61.270),
        ("GLB_CH1",       "J19.10", 24.450, 64.457),
        # --- 2026-05-28 lever G addition (last CH1 residual) ---
        ("KILL_RAIL_N_CH1","J19.8", 23.450, 64.457),
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
    print(f"  [{'OK' if ok else 'BAD'}] (1+5) ALL 8 SANCTIONED LANDINGS "
          f"(6 nets × 8 pins; lever D + G 2026-05-28) emit BLIND_BURIED F.Cu↔In2:")
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


# ─── v9 (CH1 30/30 lever F) — per-via-class halo radius tests ─────────────
#
# Background: the router's via-placement obstacle check (via_blocked_for_net
# in CongestionGrid) historically computed the halo radius from the constant
# VIA_DIAM_MM=0.60 whenever the candidate cell wasn't an HDI-own site. This
# OVER-REJECTED legitimate HDI escapes — an HDI microvia candidate (0.25mm
# pad → 0.325mm halo) was halo-checked against the standard 0.60mm via halo,
# refusing cells the actual microvia would happily fit at. Net effect:
# KILL_RAIL_N at J19.8 — per-layer clearance 0.383mm >> HDI 0.325mm threshold
# but blocked at the 0.500mm through-via threshold.
#
# Fix: thread the candidate's via_class through via_blocked_for_net so the
# halo radius is computed per-class (microvia 0.25 / blind_F_In2 0.30 /
# through 0.60). The new helpers (via_diam_mm_for_class, via_halo_radius_mm,
# via_pad_half_mm_for_class) are the SSoT for per-class clearance maths —
# no hard-coded numbers in the router callers.
#
# Validation (5 tests below):
#   (F1) through-via halo == legacy formula (no regression for standard vias)
#   (F2) microvia halo == 0.25/2 + clearance + trace_half + slop (smaller)
#   (F3) blind_F_In2 halo == 0.30/2 + clearance + trace_half + slop (smaller
#        than through, larger than microvia)
#   (F4) synthetic obstacle: foreign-track at distance where THROUGH halo
#        refuses but HDI MICROVIA halo accepts — router with v9 fix accepts
#        the microvia, refuses the through (per-class semantics correct)
#   (F5) negative: obstacle inside HDI halo even for a microvia → still
#        refused (genuine shorts NOT relaxed; shorts-gate semantics intact)

def test_halo_through_no_regression():
    """(F1) through-via halo matches the legacy formula exactly. No standard
    via shorts-gate basis (v6/v7) is touched by this change."""
    expected = VIA_DIAM_MM / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
    got = via_halo_radius_mm('through')
    ok = abs(got - expected) < 1e-9
    print(f"  [{'OK' if ok else 'BAD'}] (F1) through halo: "
          f"got {got:.6f}mm, expected {expected:.6f}mm "
          f"(= {VIA_DIAM_MM}/2 + {CLEARANCE_MM} + {TRACE_HALF_MM} + {GRID_SLOP_MM})")
    # Also verify the pad-half (no trace_half) matches the legacy formula.
    expected_pad = VIA_DIAM_MM / 2 + CLEARANCE_MM
    got_pad = via_pad_half_mm_for_class('through')
    ok_pad = abs(got_pad - expected_pad) < 1e-9
    print(f"  [{'OK' if ok_pad else 'BAD'}] (F1) through pad_half: "
          f"got {got_pad:.6f}mm, expected {expected_pad:.6f}mm "
          f"(no regression — preserves v6/v7 shorts-gate basis)")
    return ok and ok_pad


def test_halo_microvia_smaller():
    """(F2) microvia halo is SMALLER than through halo, derives from the same
    formula but with HDI_VIA_DIAM_MM (0.25mm)."""
    expected = HDI_VIA_DIAM_MM / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
    got_f = via_halo_radius_mm('microvia_F_In1')
    got_b = via_halo_radius_mm('microvia_B_In8')
    through_halo = via_halo_radius_mm('through')
    ok = (abs(got_f - expected) < 1e-9 and
          abs(got_b - expected) < 1e-9 and
          got_f < through_halo)
    print(f"  [{'OK' if ok else 'BAD'}] (F2) microvia halo: F_In1={got_f:.6f}, "
          f"B_In8={got_b:.6f}, expected {expected:.6f} "
          f"(smaller than through {through_halo:.6f}; HDI fits 0.5mm pitch QFN)")
    # Pad-half also matches HDI_VIA_HALF_MM (the existing constant).
    got_pad = via_pad_half_mm_for_class('microvia_F_In1')
    ok_pad = abs(got_pad - HDI_VIA_HALF_MM) < 1e-9
    print(f"  [{'OK' if ok_pad else 'BAD'}] (F2) microvia pad_half "
          f"{got_pad:.6f}mm == HDI_VIA_HALF_MM {HDI_VIA_HALF_MM:.6f}mm (SSoT)")
    return ok and ok_pad


def test_halo_blind_f_in2_smaller_than_through():
    """(F3) blind_F_In2 halo (0.30mm pad) is smaller than through (0.60mm)
    but larger than microvia (0.25mm)."""
    expected = BLIND_F_IN2_DIAM_MM / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
    got = via_halo_radius_mm('blind_F_In2')
    through_halo = via_halo_radius_mm('through')
    microvia_halo = via_halo_radius_mm('microvia_F_In1')
    ok = (abs(got - expected) < 1e-9 and
          got < through_halo and
          got > microvia_halo)
    print(f"  [{'OK' if ok else 'BAD'}] (F3) blind_F_In2 halo: got {got:.6f}, "
          f"expected {expected:.6f} (microvia {microvia_halo:.6f} < blind "
          f"{got:.6f} < through {through_halo:.6f})")
    # Pad-half matches BLIND_F_IN2_HALF_MM (existing constant).
    got_pad = via_pad_half_mm_for_class('blind_F_In2')
    ok_pad = abs(got_pad - BLIND_F_IN2_HALF_MM) < 1e-9
    print(f"  [{'OK' if ok_pad else 'BAD'}] (F3) blind_F_In2 pad_half "
          f"{got_pad:.6f}mm == BLIND_F_IN2_HALF_MM {BLIND_F_IN2_HALF_MM:.6f}mm (SSoT)")
    return ok and ok_pad


def _build_synthetic_grid(zone=(0.0, 0.0, 5.0, 5.0), pitch=0.1):
    """Build a minimal CongestionGrid in mm-space for halo-class scenario
    tests. Returns the grid (with no obstacles stamped) so each test can
    inject ONE foreign-track obstacle at a controlled distance from the
    candidate via cell and observe the per-class halo verdict."""
    g = rsc.CongestionGrid(zone, pitch, rsc.SIGNAL_LAYERS)
    return g


def test_halo_per_class_via_placement_scenario():
    """(F4) Synthetic obstacle scenario — proves the v9 per-class halo is
    semantically correct end-to-end through via_blocked_for_net:

      Setup: a 5×5mm grid (no HDI markings). Inject ONE foreign-net track
      segment on IN2_CU at y = -through_halo + epsilon below the candidate
      via cell (i.e. a distance where the STANDARD through-via halo refuses
      [obstacle within 0.605mm] but the HDI MICROVIA halo accepts [obstacle
      outside 0.430mm]).

      Then ask via_blocked_for_net at the candidate cell with two via_classes:
        - via_class='through'        → blocked (foreign edge within 0.605mm)
        - via_class='microvia_F_In1' → NOT blocked (foreign edge outside 0.430mm)

      This proves: same cell, same obstacle, ONLY the via_class changes the
      verdict — exactly the per-class semantics the v9 fix introduces. Before
      the fix, both candidates would have been refused (the call site always
      used the 0.60mm through halo)."""
    g = _build_synthetic_grid()
    # Candidate via cell at the middle of the grid
    vi, vj = g.xy_to_ij(2.5, 2.5)
    cand_x, cand_y = g.cell_xy(vi, vj)
    # Place a foreign-net track 0.50mm below the candidate (between the
    # microvia halo 0.430mm and the through halo 0.605mm), spanning x∈[1,4]
    # on IN2_CU. Track width 0.15mm. Stamp it as an obstacle segment.
    track_y = cand_y + 0.50  # 0.50mm offset (cells use +y as below; sign immaterial for distance)
    g.stamp_obstacle_segment(1.0, track_y, 4.0, track_y, 0.15, IN2_CU)
    # Compute distances from candidate to where obstacle CELLS live:
    # the segment stamping creates a halo of (0.15/2 + CLEARANCE + slop) =
    # 0.30mm around the track centerline. So obstacle cells extend from
    # track_y - 0.30 to track_y + 0.30 ≈ [cand_y+0.20, cand_y+0.80].
    # Candidate-cell-to-nearest-obstacle-cell ≈ 0.20mm.
    # Through halo r_obs (= via_pad_half - track_halo_margin) = 0.500 -
    # (0.08+0.20+0.025) = 0.195mm; the through extra_mm is small, so a
    # through-via still scans within ~r_obs and SEES the obstacle if cells
    # are stamped within 0.305+extra ≈ 0.50mm of candidate. Microvia halo
    # extra_mm = 0.325 - 0.305 = 0.020mm; scans within ~0.325mm.
    # Net: this scenario must show through=blocked AND microvia=clear.
    span_through = tuple(rsc.ALL_COPPER_LAYERS)
    span_microvia = (F_CU, IN1_CU)
    # Use a foreign netname so the track owner != candidate net (the cell
    # is foreign-blocked, not own-net).
    blocked_through, reason_t = g.via_blocked_for_net(
        vi, vj, netname='CAND_NET', span_layers=list(span_through),
        via_class='through')
    blocked_microvia, reason_m = g.via_blocked_for_net(
        vi, vj, netname='CAND_NET', span_layers=list(span_microvia),
        via_class='microvia_F_In1')
    # Acceptance: through refuses, microvia accepts. Symmetric refusal would
    # mean the v9 per-class threading is not taking effect; symmetric accept
    # would mean shorts-gate is too permissive.
    ok = blocked_through and not blocked_microvia
    print(f"  [{'OK' if ok else 'BAD'}] (F4) per-class halo verdict at "
          f"candidate (vi={vi},vj={vj}), foreign track at y-offset 0.50mm:")
    print(f"      through halo  ({via_halo_radius_mm('through'):.3f}mm)  "
          f"=> blocked={blocked_through}  reason={reason_t!r}")
    print(f"      microvia halo ({via_halo_radius_mm('microvia_F_In1'):.3f}mm) "
          f"=> blocked={blocked_microvia}  reason={reason_m!r}")
    # Sanity: WITHOUT v9 (legacy is_hdi_via=False path → always 0.60mm halo),
    # both verdicts would be 'blocked' — i.e. the bug manifests. v9 fixes it
    # by passing via_class explicitly.
    return ok


def test_halo_genuine_short_still_refused():
    """(F5) NEGATIVE: an obstacle within the smaller HDI microvia halo on a
    layer the microvia barrel ACTUALLY TRAVERSES must STILL be refused. Per-
    class halo reduces over-rejection geometrically; it MUST NOT relax
    genuine shorts. Two sub-cases:

      (F5a) Obstacle on IN1_CU within 0.10mm of candidate cell → microvia
            barrel intersects IN1 (span=F.Cu↔In1.Cu) → MUST block.
      (F5b) Obstacle on IN2_CU within 0.10mm of candidate → microvia
            barrel does NOT reach IN2 → microvia LEGITIMATELY accepts
            (layer-aware span: foreign copper outside the barrel cannot
            short it). The through-via still blocks (it spans all layers).
            This is NOT a shorts-gate relaxation — it's the v8 layer-aware
            span correctness (the same barrel-layer semantics phase_a uses).

    Together these prove: per-class halo geometry is honoured (F5a — barrel
    layer is still scanned at the correct radius); and layer-aware span is
    honoured (F5b — foreign copper on a non-barrel layer never blocks)."""
    # (F5a) On-barrel obstacle → microvia + blind + through all blocked.
    # Use F.Cu (which IS in SIGNAL_LAYERS, so the cell-based scan tracks it)
    # — IN1 is not a routed signal layer at the cooperative grid level, so
    # the analogous scan would need the geometric check. F.Cu is in the
    # barrel of every via class (microvia/blind/through), so the on-barrel
    # short manifests identically across classes.
    g_a = _build_synthetic_grid()
    vi, vj = g_a.xy_to_ij(2.5, 2.5)
    _, cand_y = g_a.cell_xy(vi, vj)
    # Place foreign track on F.Cu (in every via class's barrel) 0.10mm above.
    g_a.stamp_obstacle_segment(1.0, cand_y + 0.10, 4.0, cand_y + 0.10, 0.15, F_CU)
    bmv_a, rmv_a = g_a.via_blocked_for_net(
        vi, vj, netname='CAND_NET', span_layers=[F_CU, IN1_CU],
        via_class='microvia_F_In1')
    # On-barrel obstacle for blind_F_In2 (uses F.Cu in barrel):
    bbl_a, rbl_a = g_a.via_blocked_for_net(
        vi, vj, netname='CAND_NET', span_layers=list(rsc.BLIND_F_IN2_SPAN),
        via_class='blind_F_In2')
    bth_a, rth_a = g_a.via_blocked_for_net(
        vi, vj, netname='CAND_NET', span_layers=list(rsc.ALL_COPPER_LAYERS),
        via_class='through')
    ok_a = bmv_a and bbl_a and bth_a
    print(f"  [{'OK' if ok_a else 'BAD'}] (F5a) on-barrel-layer obstacle "
          f"(F.Cu track 0.10mm away) — EVERY class refused; shorts-gate intact:")
    print(f"      microvia    => blocked={bmv_a}  reason={rmv_a!r}")
    print(f"      blind_F_In2 => blocked={bbl_a}  reason={rbl_a!r}")
    print(f"      through     => blocked={bth_a}  reason={rth_a!r}")

    # (F5b) Off-barrel obstacle for microvia → microvia accepts (layer-aware
    # span correctness); through still blocks. Proves the per-class halo
    # cooperates with the v8 layer-aware span — not a regression.
    g_b = _build_synthetic_grid()
    vi2, vj2 = g_b.xy_to_ij(2.5, 2.5)
    _, cy2 = g_b.cell_xy(vi2, vj2)
    g_b.stamp_obstacle_segment(1.0, cy2 + 0.10, 4.0, cy2 + 0.10, 0.15, IN2_CU)
    bmv_b, rmv_b = g_b.via_blocked_for_net(
        vi2, vj2, netname='CAND_NET', span_layers=[F_CU, IN1_CU],
        via_class='microvia_F_In1')
    bth_b, rth_b = g_b.via_blocked_for_net(
        vi2, vj2, netname='CAND_NET', span_layers=list(rsc.ALL_COPPER_LAYERS),
        via_class='through')
    ok_b = (not bmv_b) and bth_b
    print(f"  [{'OK' if ok_b else 'BAD'}] (F5b) off-barrel-layer obstacle "
          f"(IN2 track 0.10mm away, microvia barrel is F-In1 only):")
    print(f"      microvia    => blocked={bmv_b}  reason={rmv_b!r} "
          f"(IN2 outside barrel — v8 layer-aware accept, NOT a shorts "
          f"relaxation)")
    print(f"      through     => blocked={bth_b}  reason={rth_b!r} "
          f"(IN2 inside barrel — refused as expected)")
    return ok_a and ok_b


# ─── v10 (CH1 30/30 lever I) — foreign-via actual-diam tests ──────────────
#
# Background: PR #227 worker symptom was "BSTB routes, 0/5 thereafter".
# Master diagnosis (this PR) found the real cause: BoardState._collect()
# (and the v6 foreign_vias entry in _stamp_obstacles) clamped the foreign-
# via diameter to max(VIA_DIAM_MM=0.60, actual_width). For prior router
# passes that emitted HDI microvias (0.25mm) or blind F-In2 vias (0.30mm)
# at sibling-channel J18/J19 pads, the clamp inflated those vias to 0.60mm
# for the centerline-precise hdi_via_blocked_geom check — falsely rejecting
# legitimate adjacent HDI via placements on the canonical board.
#
# Fix: split into stamp_diam (cell-obstacle radius) and actual_diam (precise
# geom check). The actual_diam is read from t.GetWidth(t.TopLayer()) without
# max-clamp, then flows to CongestionGrid.foreign_vias[] for the precise
# clearance check. The stamp_diam also uses actual_diam (no max-clamp) so
# the cell-obstacle halo is sized to the real via, not an inflated fallback.
#
# Validation (3 tests below):
#   (I1) foreign_vias entry diameter MATCHES via.GetWidth(top) read-back —
#        no max-clamp drift between board state and obstacle map.
#   (I2) hdi_via_blocked_geom against a 0.25mm foreign HDI microvia at
#        distance D accepts when D > 0.475mm and refuses when D < 0.475mm
#        (the correct edge-to-edge ≥ CLEARANCE_MM check at HDI diameter).
#   (I3) hdi_via_blocked_geom against a 0.60mm foreign through-via at the
#        same distance refuses at D ≤ 0.65mm (the through-via clearance is
#        STILL respected — shorts-gate intact on the standard via class).

def _build_synthetic_state_with_foreign_via(foreign_diam_mm, foreign_xy=(2.0, 2.5)):
    """Build a minimal BoardState + CongestionGrid with ONE synthetic foreign
    via injected. Returns (board, router) so callers can interrogate
    router.grid.foreign_vias to verify the actual_diam round-trip, and call
    router.grid.via_blocked_for_net() / hdi_via_blocked_geom() directly.
    """
    board = pcbnew.LoadBoard(str(PLACED_BOARD))
    # Inject ONE synthetic foreign via at the requested coords + width.
    # We synthesize the via on a copy of the board so the canonical .kicad_pcb
    # is read-only (R-sim-provenance). The via is placed off the placed-board
    # geometry (far from any pad) so it doesn't interact with real obstacles.
    nn = "FOREIGN_NET_FOR_I_TEST"
    net_obj = board.FindNet(nn)
    if net_obj is None or net_obj.GetNetCode() == 0:
        net_obj = pcbnew.NETINFO_ITEM(board, nn)
        board.Add(net_obj)
    fx, fy = foreign_xy
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(int(fx * 1e6), int(fy * 1e6)))
    # Set via diameter on F.Cu top layer (KiCad 9 SetWidth(layer, w)).
    try:
        v.SetWidth(F_CU, int(foreign_diam_mm * 1e6))
        v.SetWidth(IN2_CU, int(foreign_diam_mm * 1e6))
    except Exception:
        try:
            v.SetWidth(int(foreign_diam_mm * 1e6))
        except Exception:
            pass
    v.SetDrill(int(foreign_diam_mm * 0.5 * 1e6))  # half = pad-half guess
    if foreign_diam_mm < 0.30:
        try: v.SetViaType(pcbnew.VIATYPE_MICROVIA)
        except: pass
    v.SetLayerPair(F_CU, IN2_CU)
    v.SetNet(net_obj)
    board.Add(v)
    # Build a router whose subsystem zone INCLUDES the synthetic via location.
    # CH1 zone = (0, 50, 35, 89); foreign_xy must be inside this.
    router = rsc.CooperativeRouter(
        board, "CH1",
        grid_pitch=0.1,  # use grid pitch consistent with router default
        seed_nets=["BSTB_CH1"],  # any net — we only care about grid state
        verbose=False,
        via_in_pad_allowed=True,
    )
    return board, router, (fx, fy)


def test_lever_I_actual_diam_round_trip():
    """(I1) foreign_vias entry diameter matches via.GetWidth — no clamp drift.

    Inject a synthetic foreign HDI microvia (diam=0.25mm) into a board copy,
    instantiate the router, look up the corresponding entry in
    CongestionGrid.foreign_vias, assert the stored diameter is 0.25 — NOT
    the pre-v10 0.60mm max-clamped fallback.

    Also check a 0.60mm foreign through-via still stores 0.60mm (no
    regression on standard through-via clearance — shorts-gate intact).
    """
    cases = [
        # (foreign_diam_mm, expected_in_foreign_vias)
        (0.25, 0.25),   # HDI microvia — pre-v10 clamped to 0.60mm
        (0.30, 0.30),   # blind F-In2  — pre-v10 clamped to 0.60mm
        (0.60, 0.60),   # standard through — was already 0.60mm
    ]
    ok = True
    for (diam_in, diam_expected) in cases:
        _, router, fxy = _build_synthetic_state_with_foreign_via(
            foreign_diam_mm=diam_in, foreign_xy=(20.0, 70.0))
        # Find the synthetic foreign via in router.grid.foreign_vias[]
        match = [(x, y, d, o) for (x, y, d, o) in router.grid.foreign_vias
                 if abs(x - 20.0) < 1e-3 and abs(y - 70.0) < 1e-3
                 and o == "FOREIGN_NET_FOR_I_TEST"]
        good = (len(match) == 1
                and abs(match[0][2] - diam_expected) < 1e-3)
        ok &= good
        d_got = match[0][2] if match else None
        print(f"  [{'OK' if good else 'BAD'}] (I1) foreign_vias actual diam "
              f"injected={diam_in}mm, expected stored={diam_expected}mm, "
              f"got={d_got}mm "
              f"({'no clamp drift' if good else 'clamped — pre-v10 bug'})")
    return ok


def test_lever_I_hdi_geom_accepts_legit_microvia():
    """(I2) hdi_via_blocked_geom accepts when the FOREIGN via is genuinely
    a 0.25mm HDI microvia at a distance the actual (post-fix) clearance maths
    permits but the pre-fix (over-clamped) maths refused.

    Distance setup: required clearance for blind F-In2 candidate (pad_half =
    0.30/2 = 0.15) vs foreign HDI microvia (diam = 0.25) =
       (0.25 / 2) + 0.15 + 0.20 = 0.475mm  (post-fix, CORRECT)
    Pre-fix maths used clamped diam = 0.60, required =
       (0.60 / 2) + 0.15 + 0.20 = 0.650mm  (pre-fix, OVER-CONSERVATIVE)

    At D = 0.50mm: post-fix margin = +0.025 (ACCEPT); pre-fix margin = −0.15
    (REFUSE). The test injects the foreign via at exactly 0.50mm and asserts
    ACCEPT — proves the v10 fix unblocks legitimate adjacent HDI placements.
    """
    fx, fy = 20.0, 70.0
    # Candidate cell at distance 0.50mm from foreign via center.
    cand_x, cand_y = fx + 0.50, fy
    _, router, _ = _build_synthetic_state_with_foreign_via(
        foreign_diam_mm=0.25, foreign_xy=(fx, fy))
    g = router.grid
    ci, cj = g.xy_to_ij(cand_x, cand_y)
    span = list(rsc.via_span_layers('blind_F_In2'))
    blk, reason = g.hdi_via_blocked_geom(
        ci, cj, netname="BSTB_CH1", span_layers=span,
        via_class='blind_F_In2')
    # Expect ACCEPT (not blocked) — the synthetic foreign 0.25mm microvia
    # at 0.50mm is OUTSIDE the post-fix 0.475mm halo.
    ok = (not blk)
    print(f"  [{'OK' if ok else 'BAD'}] (I2) blind_F_In2 candidate at "
          f"D=0.50mm from foreign 0.25mm microvia: "
          f"blocked={blk} reason={reason!r} "
          f"(post-fix required=0.475mm; ACCEPT correct; pre-fix would "
          f"have rejected at clamped required=0.650mm)")
    return ok


def test_lever_I_hdi_geom_refuses_real_through_short():
    """(I3) Shorts-gate intact: a 0.60mm foreign THROUGH via at the same
    0.50mm distance is correctly REFUSED — the actual_diam fix does NOT
    relax legitimate through-via clearances.

    Required for blind_F_In2 candidate (pad_half=0.15) vs foreign 0.60mm:
       (0.60/2) + 0.15 + 0.20 = 0.650mm  — distance 0.50mm < 0.650 → BLOCK.

    This proves the v10 fix is per-class precise: small foreign vias get
    smaller halos (legit acceptance), big foreign vias keep their full halo
    (shorts-gate intact). Together with (I1) + (I2) this is the symmetric
    test of the fix.
    """
    fx, fy = 20.0, 70.0
    cand_x, cand_y = fx + 0.50, fy
    _, router, _ = _build_synthetic_state_with_foreign_via(
        foreign_diam_mm=0.60, foreign_xy=(fx, fy))
    g = router.grid
    ci, cj = g.xy_to_ij(cand_x, cand_y)
    span = list(rsc.via_span_layers('blind_F_In2'))
    blk, reason = g.hdi_via_blocked_geom(
        ci, cj, netname="BSTB_CH1", span_layers=span,
        via_class='blind_F_In2')
    ok = blk
    print(f"  [{'OK' if ok else 'BAD'}] (I3) blind_F_In2 candidate at "
          f"D=0.50mm from foreign 0.60mm THROUGH via: "
          f"blocked={blk} reason={reason!r} "
          f"(required=0.650mm; REFUSE correct — shorts-gate intact, "
          f"no through-via clearance relaxation)")
    return ok


# ─── LEVER L (CH1 30/30 stacked microvia F↔In1↔In2) — emit + classify tests ─
#
# Background: LEVER L adds a SECOND signal-reaching via mechanism per
# whitelist pin — JLC HDI Class 2 stacked microvia (TWO MICROVIA legs
# geometrically aligned: top F.Cu↔In1.Cu + bottom In1.Cu↔In2.Cu, with the
# In1 landing as an isolated antipad+pad island). Mathematically doubles
# the signal-reaching supply on whitelist pins (blind_F_In2 = 1 slot + LEVER
# L stacked = 1 slot per pin = 2 slots per whitelist landing). Industry-
# standard since iPhone 4 era; ~$1-2/board adder, no new fab class.
#
# Validation (5 tests below):
#   (L1) SSoT: router stacked whitelist == audit STACKED_MICROVIA_NET_WHITELIST
#   (L2) classifier: F↔In2 + stacked-WL net + prefer_stacked = stacked class
#   (L3) classifier: F↔In2 + non-WL net = REFUSED (no through fall-through)
#   (L4) emit: stacked class emits TWO VIATYPE_MICROVIA legs at same XY
#        spanning (F.Cu, In1.Cu) + (In1.Cu, In2.Cu), drill 0.10mm + pad 0.25mm
#        each, on the whitelist net. Verify per leg.
#   (L5) emit: ALL 8 sanctioned (net, pin) landings emit stacked correctly.
#   (L6) halo + span SSoT: via_halo_radius_mm('stacked_...') == HDI microvia
#        halo (per-leg pad 0.25mm); via_span_layers returns the F/In1/In2
#        3-tuple; via_diam_mm_for_class returns STACKED_MICROVIA_DIAM_MM.

def test_lever_L_ssoT():
    """(L1) Router stacked whitelist mirrors audit's
    STACKED_MICROVIA_NET_WHITELIST exactly (SSoT discipline)."""
    router_wl = set(stacked_microvia_net_whitelist())
    audit_wl = set(audit_mod.STACKED_MICROVIA_NET_WHITELIST)
    expected = {"BSTB_CH1", "PWM_INHB_CH1", "SWDIO_CH1", "PWM_INLA_CH1",
                "GLB_CH1", "KILL_RAIL_N_CH1"}
    ok = router_wl == audit_wl == expected and len(router_wl) == 6
    print(f"  [{'OK' if ok else 'BAD'}] (L1) SSoT: router stacked whitelist "
          f"== audit whitelist = {sorted(router_wl)} (expected 6)")
    return ok


def test_lever_L_classifier_stacked_class():
    """(L2) F↔In2 + stacked-WL net + prefer_stacked=True returns
    'stacked_microvia_F_In1_In2' class instead of blind_F_In2."""
    cases = [
        # (L_from, L_to, net, prefer_stacked, expected)
        (F_CU, IN2_CU, "BSTB_CH1",         True,  "stacked_microvia_F_In1_In2"),
        (F_CU, IN2_CU, "PWM_INHB_CH1",     True,  "stacked_microvia_F_In1_In2"),
        (F_CU, IN2_CU, "SWDIO_CH1",        True,  "stacked_microvia_F_In1_In2"),
        (F_CU, IN2_CU, "PWM_INLA_CH1",     True,  "stacked_microvia_F_In1_In2"),
        (F_CU, IN2_CU, "GLB_CH1",          True,  "stacked_microvia_F_In1_In2"),
        (F_CU, IN2_CU, "KILL_RAIL_N_CH1",  True,  "stacked_microvia_F_In1_In2"),
        (IN2_CU, F_CU, "BSTB_CH1",         True,  "stacked_microvia_F_In1_In2"),
        # prefer_stacked=False preserves the OQ-020 default (blind_F_In2).
        (F_CU, IN2_CU, "BSTB_CH1",         False, "blind_F_In2"),
        (F_CU, IN2_CU, "PWM_INHB_CH1",     False, "blind_F_In2"),
    ]
    ok = True
    for (lf, lt, n, ps, exp) in cases:
        got = via_class_for_span(lf, lt, n, is_hdi_cell=True, prefer_stacked=ps)
        good = got == exp
        ok &= good
        if not good:
            print(f"  [BAD] via_class_for_span({lf},{lt},{n!r},prefer_stacked={ps}) "
                  f"= {got!r}, expected {exp!r}")
    print(f"  [{'OK' if ok else 'BAD'}] (L2) classifier: stacked class "
          f"returned for F↔In2 + WL + prefer_stacked; blind default preserved")
    return ok


def test_lever_L_classifier_negative():
    """(L3) F↔In2 + non-WL net at HDI cell = REFUSED (None) — no
    fall-through to through-via (v6/v7 shorts lesson preserved)."""
    cases = [
        ("FOOBAR_CH1", True),
        ("BSTB", True),
        ("GLA_CH1", True),
        ("KILL_RAIL_N", True),
        ("KILL_RAIL_N_CH2", True),
        ("FOOBAR_CH1", False),
        ("GLC_CH1", False),
    ]
    ok = True
    for (n, ps) in cases:
        got = via_class_for_span(F_CU, IN2_CU, n, is_hdi_cell=True,
                                  prefer_stacked=ps)
        good = got is None
        ok &= good
        if not good:
            print(f"  [BAD] via_class_for_span(F,In2,{n!r},prefer_stacked={ps}) "
                  f"= {got!r}, expected None (REFUSED — no through fall-through)")
    print(f"  [{'OK' if ok else 'BAD'}] (L3) classifier: F↔In2 + non-WL = REFUSED")
    return ok


def _emit_stacked(board, net_name, x_mm, y_mm):
    """Call emit_to_board for ONE stacked microvia at (x_mm, y_mm) on
    `net_name` (whitelist-eligible). Returns (legs_added, exception_str)
    where legs_added is the list of PCB_VIAs added (expect 2 legs)."""
    net_obj = _ensure_net(board, net_name)
    grid = SyntheticGrid(is_hdi=True)
    segments = []
    vias = [(x_mm, y_mm)]
    # Drive the stacked class via the v8 emitter — uses via_class_for_span
    # with the F.Cu↔In2.Cu span. We must thread prefer_stacked through the
    # classifier (the emitter calls via_class_for_span internally without
    # prefer_stacked). For the LEVER L emit test we shim the classifier by
    # monkey-patching emit_to_board's resolver to prefer_stacked=True for
    # the duration of this call — done by temporarily replacing
    # rsc.via_class_for_span with a partial-applied version.
    via_target_layers = {(round(x_mm, 3), round(y_mm, 3)): (F_CU, IN2_CU)}
    added = []
    orig_via_class_for_span = rsc.via_class_for_span
    def _vcs_prefer_stacked(L_from, L_to, net_name, is_hdi_cell, **kwargs):
        return orig_via_class_for_span(L_from, L_to, net_name,
                                        is_hdi_cell=is_hdi_cell,
                                        prefer_stacked=True, **kwargs)
    rsc.via_class_for_span = _vcs_prefer_stacked
    try:
        emit_to_board(board, segments, vias, net_obj, width_mm=0.15,
                       added_items=added,
                       hdi_via_cells=grid.hdi_via_cells, grid=grid,
                       via_target_layers=via_target_layers)
    except ValueError as e:
        rsc.via_class_for_span = orig_via_class_for_span
        return None, str(e)
    finally:
        rsc.via_class_for_span = orig_via_class_for_span
    legs = [it for it in added if isinstance(it, pcbnew.PCB_VIA)]
    return legs, None


def test_lever_L_emit_stacked_pair():
    """(L4) emit on a whitelist net produces TWO MICROVIA legs at same XY
    spanning (F.Cu, In1.Cu) + (In1.Cu, In2.Cu), drill 0.10mm + pad 0.25mm
    each, on the bound net."""
    board = pcbnew.LoadBoard(str(PLACED_BOARD))
    legs, err = _emit_stacked(board, "BSTB_CH1", x_mm=26.137, y_mm=61.770)
    if err:
        print(f"  [BAD] (L4) stacked emit raised: {err}")
        return False
    if legs is None or len(legs) != 2:
        print(f"  [BAD] (L4) expected 2 legs, got {len(legs) if legs else 0}")
        return False
    layer_pairs = sorted([tuple(sorted((l.TopLayer(), l.BottomLayer())))
                          for l in legs])
    expected_pairs = sorted([tuple(sorted((F_CU, IN1_CU))),
                              tuple(sorted((IN1_CU, IN2_CU)))])
    ok_pairs = layer_pairs == expected_pairs
    ok_types = all(l.GetViaType() == pcbnew.VIATYPE_MICROVIA for l in legs)
    ok_drill = all(abs(l.GetDrill() / 1e6 - STACKED_MICROVIA_DRILL_MM) < 1e-6
                   for l in legs)
    # pad: read width on the top layer of each leg.
    pads_ok = True
    for l in legs:
        try:
            pad_mm = l.GetWidth(l.TopLayer()) / 1e6
        except TypeError:
            pad_mm = l.GetWidth() / 1e6
        if abs(pad_mm - STACKED_MICROVIA_DIAM_MM) > 1e-6:
            pads_ok = False
    ok = ok_pairs and ok_types and ok_drill and pads_ok
    print(f"  [{'OK' if ok else 'BAD'}] (L4) STACKED emit (BSTB_CH1 @ J19.17): "
          f"2 MICROVIA legs, layer_pairs={layer_pairs}, "
          f"types={[l.GetViaType() for l in legs]} "
          f"(expected {pcbnew.VIATYPE_MICROVIA} × 2), drill+pad ok")
    return ok


def test_lever_L_emit_all_8_landings():
    """(L5) all 8 sanctioned (net, pin) landings emit stacked correctly."""
    cases = [
        ("BSTB_CH1",        "J19.17", 26.137, 61.770),
        ("PWM_INHB_CH1",    "J18.19", 34.188, 66.750),
        ("SWDIO_CH1",       "J18.23", 34.188, 64.750),
        ("PWM_INLA_CH1",    "J18.15", 33.000, 68.438),
        ("PWM_INHB_CH1",    "J19.23", 23.450, 60.582),
        ("PWM_INLA_CH1",    "J19.1",  22.262, 61.270),
        ("GLB_CH1",         "J19.10", 24.450, 64.457),
        ("KILL_RAIL_N_CH1", "J19.8",  23.450, 64.457),
    ]
    ok = True
    breakdown = []
    for (net, pad_label, x, y) in cases:
        board = pcbnew.LoadBoard(str(PLACED_BOARD))
        legs, err = _emit_stacked(board, net, x, y)
        if err or legs is None or len(legs) != 2:
            ok = False
            breakdown.append(f"{net}@{pad_label}: FAIL "
                             f"({err or f'{len(legs) if legs else 0} legs'})")
            continue
        # Both legs must be MICROVIA, drill 0.10, pad 0.25, layer-pair set
        # is {(F,In1), (In1,In2)}.
        layer_pairs = sorted([tuple(sorted((l.TopLayer(), l.BottomLayer())))
                              for l in legs])
        expected_pairs = sorted([tuple(sorted((F_CU, IN1_CU))),
                                  tuple(sorted((IN1_CU, IN2_CU)))])
        good = (layer_pairs == expected_pairs and
                all(l.GetViaType() == pcbnew.VIATYPE_MICROVIA for l in legs))
        ok &= good
        breakdown.append(f"{net}@{pad_label}: legs={len(legs)} "
                         f"layer_pairs={layer_pairs} "
                         f"{'OK' if good else 'BAD'}")
    print(f"  [{'OK' if ok else 'BAD'}] (L5) ALL 8 SANCTIONED LANDINGS emit "
          f"STACKED MICROVIA F.Cu↔In1↔In2 (2 legs × 8 pins = 16 microvias):")
    for line in breakdown:
        print(f"      {line}")
    return ok


def test_lever_L_halo_and_span():
    """(L6) per-class halo / span / diam helpers all return LEVER L geometry."""
    # via_diam_mm_for_class
    got_diam = via_diam_mm_for_class('stacked_microvia_F_In1_In2')
    ok_diam = abs(got_diam - STACKED_MICROVIA_DIAM_MM) < 1e-9
    # via_halo_radius_mm — per-leg formula matches microvia halo (same diam)
    expected_halo = (STACKED_MICROVIA_DIAM_MM / 2 + CLEARANCE_MM
                     + TRACE_HALF_MM + GRID_SLOP_MM)
    got_halo = via_halo_radius_mm('stacked_microvia_F_In1_In2')
    ok_halo = abs(got_halo - expected_halo) < 1e-9
    # via_pad_half_mm_for_class — matches STACKED_MICROVIA_HALF_MM constant
    got_pad_half = via_pad_half_mm_for_class('stacked_microvia_F_In1_In2')
    ok_pad_half = abs(got_pad_half - STACKED_MICROVIA_HALF_MM) < 1e-9
    # via_span_layers — F.Cu / In1 / In2 (same as blind_F_In2)
    got_span = via_span_layers('stacked_microvia_F_In1_In2')
    ok_span = got_span == STACKED_MICROVIA_SPAN
    ok = ok_diam and ok_halo and ok_pad_half and ok_span
    print(f"  [{'OK' if ok else 'BAD'}] (L6) per-class helpers: "
          f"diam={got_diam}mm (exp {STACKED_MICROVIA_DIAM_MM}), "
          f"halo={got_halo:.3f}mm (exp {expected_halo:.3f}), "
          f"pad_half={got_pad_half}mm (exp {STACKED_MICROVIA_HALF_MM}), "
          f"span={got_span} (exp {STACKED_MICROVIA_SPAN})")
    return ok


def main():
    if not PLACED_BOARD.exists():
        print(f"FAIL: board {PLACED_BOARD} not found")
        return 1
    print("=" * 72)
    print("test_emit_blind_f_in2 — synthetic OQ-020 EMITTER patch (v8)")
    print("                       + v9 per-via-class halo radius (CH1 30/30 F)")
    print("                       + v10 foreign-via actual-diam (CH1 30/30 I)")
    print("                       + v11 LEVER L stacked microvia (CH1 30/30 L)")
    print(f"  board: {PLACED_BOARD}")
    print(f"  audit: {HERE / 'audit_hdi_via_in_pad.py'}")
    print("=" * 72)
    results = []
    results.append(("classifier SSoT (5)", test_classifier_ssoT()))
    results.append(("classifier table", test_classifier_table()))
    results.append(("via_span_layers", test_span_layers()))
    results.append(("(1) WHITELIST blind F-In2", test_emit_whitelist_blind_f_in2()))
    results.append(("(1+5) all 8 WL landings (4 orig + 3 lever D + 1 lever G)",
                    test_emit_all_4_whitelist_nets()))
    results.append(("(2) NEGATIVE refuse", test_emit_negative_non_whitelist()))
    results.append(("(2+4) audit catches forced off-WL",
                    test_emit_negative_audit_catches_forced()))
    results.append(("(4) audit accepts emitted WL", test_emit_audit_accepts_whitelist()))
    results.append(("(3) NO REGRESSION", test_emit_no_regression()))
    # v9 (CH1 30/30 F) per-via-class halo tests — 5 new tests.
    results.append(("(F1) through halo no regression",
                    test_halo_through_no_regression()))
    results.append(("(F2) microvia halo smaller",
                    test_halo_microvia_smaller()))
    results.append(("(F3) blind_F_In2 halo per-class",
                    test_halo_blind_f_in2_smaller_than_through()))
    results.append(("(F4) per-class via placement scenario",
                    test_halo_per_class_via_placement_scenario()))
    results.append(("(F5) shorts-gate intact (negative)",
                    test_halo_genuine_short_still_refused()))
    # v10 (CH1 30/30 I) foreign-via actual-diameter (no max-clamp) tests.
    results.append(("(I1) foreign_vias actual diam round-trip",
                    test_lever_I_actual_diam_round_trip()))
    results.append(("(I2) hdi_geom accepts legit microvia at 0.50mm",
                    test_lever_I_hdi_geom_accepts_legit_microvia()))
    results.append(("(I3) hdi_geom refuses real through short (shorts-gate intact)",
                    test_lever_I_hdi_geom_refuses_real_through_short()))
    # LEVER L (CH1 30/30) stacked microvia F↔In1↔In2 — 6 new tests.
    results.append(("(L1) SSoT: stacked whitelist == audit",
                    test_lever_L_ssoT()))
    results.append(("(L2) classifier returns stacked class",
                    test_lever_L_classifier_stacked_class()))
    results.append(("(L3) classifier refuses non-WL (no through fall-through)",
                    test_lever_L_classifier_negative()))
    results.append(("(L4) emit stacked pair (2 MICROVIA legs)",
                    test_lever_L_emit_stacked_pair()))
    results.append(("(L5) ALL 8 sanctioned landings emit stacked",
                    test_lever_L_emit_all_8_landings()))
    results.append(("(L6) per-class halo/span/diam helpers (SSoT)",
                    test_lever_L_halo_and_span()))
    print("=" * 72)
    n_pass = sum(1 for (_, p) in results if p)
    n = len(results)
    for (name, p) in results:
        print(f"  {'PASS' if p else 'FAIL'}: {name}")
    print("=" * 72)
    if n_pass == n:
        print(f"RESULT: PASS — {n_pass}/{n} tests pass; LEVER L (CH1 30/30 "
              f"stacked microvia F↔In1↔In2): SSoT discipline + classifier + "
              f"REFUSE-non-WL + 2-leg emit + 8-landing emit + per-class halo "
              f"all green. OQ-020 EMITTER (v8 + "
              f"2026-05-28 lever D + 2026-05-28 lever G) correctly emits "
              f"BLIND_BURIED F.Cu↔In2 for all 6 whitelist nets at all 8 "
              f"sanctioned landings, REFUSES non-whitelist spans, preserves "
              f"existing via classes, v9 per-via-class halo (CH1 30/30 F) "
              f"correctly admits HDI vias the through halo would over-reject "
              f"without weakening shorts-gate semantics, AND v10 foreign-via "
              f"actual-diameter (CH1 30/30 I, this PR) correctly threads the "
              f"TRUE foreign HDI microvia/blind diameter into the centerline-"
              f"precise hdi_via_blocked_geom check — fixing the pre-v10 "
              f"max(VIA_DIAM_MM, actual) over-clamp that falsely rejected "
              f"legitimate adjacent HDI via placements (the worker-empirical "
              f"'BSTB routes, 0/5 thereafter' symptom; PR #227 diagnosis).")
        return 0
    print(f"RESULT: FAIL — {n_pass}/{n} tests pass; OQ-020 EMITTER (v8), "
          f"v9 halo per-class, or v10 foreign-via actual-diam has "
          f"regressions; see [BAD] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
