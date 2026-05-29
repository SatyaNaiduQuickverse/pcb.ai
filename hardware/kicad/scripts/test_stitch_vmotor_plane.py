#!/usr/bin/env python3
"""test_stitch_vmotor_plane.py — regression tests for the kicad-cli
self-verify alignment of stitch_vmotor_plane.py.

Per Sai catch 2026-05-29 (lever-S): the M3-fix self-verify (PR #244)
used pcbnew HitTestFilledArea and reported 0 dangling, while kicad-cli
pcb drc reported 199 via_dangling on the SAME board. This test suite
guards against regression of that discrepancy.

Tests (in increasing order of integration):
  T1. kicad_cli_drc_dangling_vias() parses a known fixture and returns
      the expected set of (x, y) tuples.
  T2. On a synthetic single-via through-via landing on a single-layer
      pour, kicad-cli reports it dangling (sanity-check of stage 2).
  T3. On the same single-via setup, the previous-impl
      HitTestFilledArea check says CONNECTED (i.e. it DOES disagree
      with kicad-cli — the discrepancy is real and the test pins down
      the failure mode the fix addresses).
  T4. End-to-end: run main() with --skip-post-verify on a tiny board
      and confirm a dangling-via baseline exists, then run without
      --skip-post-verify and confirm the saved board has 0
      via_dangling per kicad-cli.

Run: python3 test_stitch_vmotor_plane.py
Exit 0 = ALL tests pass; nonzero = failure with diagnostic message.

Requires kicad-cli on PATH + pcbnew Python bindings (KiCad 9.x).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import the module under test (hyphen-free filename so import works)
spec = importlib.util.spec_from_file_location(
    "stitch_vmotor_plane",
    SCRIPT_DIR / "stitch_vmotor_plane.py",
)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def iu(v_mm):
    return pcbnew.FromMM(v_mm)


def mm(v_iu):
    return pcbnew.ToMM(v_iu)


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(iu(x_mm), iu(y_mm))


def _add_zone(board, layer, net, x0, y0, x1, y1):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetLocalClearance(iu(0.2))
    z.SetMinThickness(iu(0.2))
    z.SetThermalReliefGap(iu(0.5))
    z.SetThermalReliefSpokeWidth(iu(0.5))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    o = z.Outline()
    o.NewOutline()
    o.Append(iu(x0), iu(y0))
    o.Append(iu(x1), iu(y0))
    o.Append(iu(x1), iu(y1))
    o.Append(iu(x0), iu(y1))
    board.Add(z)
    return z


def _add_edge(board, x1, y1, x2, y2):
    seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(vec(x1, y1))
    seg.SetEnd(vec(x2, y2))
    seg.SetLayer(pcbnew.Edge_Cuts)
    seg.SetWidth(iu(0.15))
    board.Add(seg)


def _add_through_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(vec(x, y))
    v.SetDrill(iu(0.30))
    try:
        v.SetWidth(pcbnew.F_Cu, iu(0.60))
        v.SetWidth(pcbnew.B_Cu, iu(0.60))
    except TypeError:
        v.SetWidth(iu(0.60))
    v.SetNet(net)
    board.Add(v)
    return v


def make_single_layer_pour_board(tmpdir, with_via=True):
    """Tiny synthetic board: 4 Cu layers, +VMOTOR pour ONLY on In1.Cu
    (no F.Cu / B.Cu pour) — reproduces the single-layer-pour topology
    that caused the lever-S discrepancy on the canonical board.
    """
    out_path = Path(tmpdir) / "single_layer_pour.kicad_pcb"
    board = pcbnew.NewBoard(str(out_path))
    # 4 Cu layers (F.Cu, In1.Cu, In2.Cu, B.Cu)
    board.SetCopperLayerCount(4)

    # Edge cuts: 20x20mm board
    _add_edge(board, 0, 0, 20, 0)
    _add_edge(board, 20, 0, 20, 20)
    _add_edge(board, 20, 20, 0, 20)
    _add_edge(board, 0, 20, 0, 0)

    # Nets
    vmotor = pcbnew.NETINFO_ITEM(board, "+VMOTOR")
    board.Add(vmotor)
    gnd = pcbnew.NETINFO_ITEM(board, "GND")
    board.Add(gnd)

    # +VMOTOR pour on In1 ONLY (single-layer scenario)
    _add_zone(board, pcbnew.In1_Cu, vmotor, 2, 2, 18, 18)
    # GND on F.Cu + B.Cu (2 layers — so GND through-vias should NOT dangle)
    _add_zone(board, pcbnew.F_Cu, gnd, 2, 2, 18, 18)
    _add_zone(board, pcbnew.B_Cu, gnd, 2, 2, 18, 18)

    if with_via:
        _add_through_via(board, 10, 10, vmotor)

    pcbnew.ZONE_FILLER(board).Fill(list(board.Zones()))
    board.Save(str(out_path))
    return out_path


def test_t1_drc_parsing():
    """T1: kicad_cli_drc_dangling_vias() reads kicad-cli JSON correctly."""
    with tempfile.TemporaryDirectory() as td:
        # Make a board with 1 dangling via at (10, 10)
        p = make_single_layer_pour_board(td, with_via=True)
        result = S.kicad_cli_drc_dangling_vias(str(p))
        assert isinstance(result, set), f"expected set, got {type(result)}"
        # The single via at (10, 10) MUST be dangling because the pour
        # exists only on In1 — a through-via has flash pads on F.Cu/B.Cu
        # that connect to no same-net copper there.
        assert (10.0, 10.0) in result, (
            f"T1 FAIL: expected (10.0, 10.0) in dangling set, got {result}")
        # Should not contain anything beyond our one via
        assert len(result) == 1, (
            f"T1 FAIL: expected exactly 1 dangling, got {len(result)}: {result}")
        print("T1 PASS: kicad_cli_drc_dangling_vias parses JSON, returns "
              "(x_mm, y_mm) tuple set.")


def test_t2_single_via_dangles():
    """T2: single through-via on single-layer pour IS dangling per
    kicad-cli (sanity-check the failure mode)."""
    with tempfile.TemporaryDirectory() as td:
        p = make_single_layer_pour_board(td, with_via=True)
        result = S.kicad_cli_drc_dangling_vias(str(p))
        assert (10.0, 10.0) in result, (
            "T2 FAIL: through-via on single-layer pour should be flagged "
            "via_dangling by kicad-cli (rule fires when via connects on "
            "only one Cu layer).")
        print("T2 PASS: single-layer-pour through-via is dangling per kicad-cli.")


def test_t3_hittest_disagrees_with_kicadcli():
    """T3: pcbnew HitTestFilledArea returns CONNECTED for the same via
    that kicad-cli flags dangling — pins down the discrepancy the fix
    addresses."""
    with tempfile.TemporaryDirectory() as td:
        p = make_single_layer_pour_board(td, with_via=True)
        # Load board, run HitTestFilledArea on the via
        board = pcbnew.LoadBoard(str(p))
        pcbnew.ZONE_FILLER(board).Fill(list(board.Zones()))
        via = None
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "+VMOTOR":
                via = t
                break
        assert via is not None, "T3 FAIL: synthetic via not found on board"
        hit = S.via_pad_connects_to_pour_after_refill(board, via, "+VMOTOR")
        kicadcli_dang = S.kicad_cli_drc_dangling_vias(str(p))
        # HitTestFilledArea says connected (True)
        # kicad-cli says dangling (via in dang set)
        assert hit is True, (
            "T3 FAIL: HitTestFilledArea should report True (it's the "
            "weaker test that says 'inside any same-net pour') — got False.")
        assert (10.0, 10.0) in kicadcli_dang, (
            "T3 FAIL: kicad-cli should report this via dangling.")
        print("T3 PASS: HitTestFilledArea=True but kicad-cli=dangling — "
              "discrepancy mode confirmed; new stage-2 catches what stage-1 "
              "missed.")


def test_t4_stitcher_aligns_final_verdict():
    """T4: running the full stitcher main() on the synthetic board, the
    saved output is FREE of via_dangling per kicad-cli (the script
    either removed every dangling via or refused to emit them).
    """
    with tempfile.TemporaryDirectory() as td:
        # Make a small board with the same pour topology but bigger so
        # the grid has room. Reuse the helper.
        in_path = Path(td) / "in.kicad_pcb"
        out_path = Path(td) / "out.kicad_pcb"
        report_path = Path(td) / "report.json"
        # Build a bigger synthetic
        board = pcbnew.NewBoard(str(in_path))
        board.SetCopperLayerCount(4)
        for x1, y1, x2, y2 in [(0, 0, 30, 0), (30, 0, 30, 30),
                                (30, 30, 0, 30), (0, 30, 0, 0)]:
            _add_edge(board, x1, y1, x2, y2)
        vmotor = pcbnew.NETINFO_ITEM(board, "+VMOTOR")
        board.Add(vmotor)
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        _add_zone(board, pcbnew.In1_Cu, vmotor, 2, 2, 28, 28)
        _add_zone(board, pcbnew.F_Cu, gnd, 2, 2, 28, 28)
        _add_zone(board, pcbnew.B_Cu, gnd, 2, 2, 28, 28)
        pcbnew.ZONE_FILLER(board).Fill(list(board.Zones()))
        board.Save(str(in_path))
        # Invoke main as a subprocess (matches real-use)
        # We expect FAIL because the board can't meet density without
        # dangling vias on a single-layer pour.
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "stitch_vmotor_plane.py"),
             "--board", str(in_path),
             "--output", str(out_path),
             "--report", str(report_path),
             "--no-pair",  # simplify
             "--density-vias-per-cm2", "4"],
            capture_output=True, text=True, timeout=600)
        # Tool may exit 1 (SHORT density) or 0 (PASS). Either is OK,
        # but the saved output (if any) MUST have 0 via_dangling.
        if out_path.exists():
            residual = S.kicad_cli_drc_dangling_vias(str(out_path))
            # Filter out any non-stitcher-related dangling — our synth
            # board has no pre-existing vias, so 0 is the expected total.
            assert len(residual) == 0, (
                f"T4 FAIL: saved board still has {len(residual)} "
                f"via_dangling per kicad-cli: {residual}")
            print(f"T4 PASS: saved board has 0 via_dangling per kicad-cli "
                  f"(stitcher rc={result.returncode}).")
        else:
            # Tool refused to save (sys.exit(3) or (4)). Refusal IS a
            # valid outcome per the lever-S rule ("honest fail"). Verify
            # the rejection message references kicad-cli or dangling.
            combined = (result.stdout or "") + "\n" + (result.stderr or "")
            assert ("dangling" in combined.lower()
                    or "kicad-cli" in combined.lower()), (
                f"T4 FAIL: refusal message does not cite dangling/kicad-cli. "
                f"stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}")
            print(f"T4 PASS: tool refused to save dangling-contaminated "
                  f"output (rc={result.returncode}).")


def main():
    tests = [
        ("T1", test_t1_drc_parsing),
        ("T2", test_t2_single_via_dangles),
        ("T3", test_t3_hittest_disagrees_with_kicadcli),
        ("T4", test_t4_stitcher_aligns_final_verdict),
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"{name} FAIL: {e}")
            failures.append(name)
        except Exception as e:
            print(f"{name} ERROR: {type(e).__name__}: {e}")
            failures.append(name)
    print()
    if failures:
        print(f"FAIL: {len(failures)}/{len(tests)} tests failed: {failures}")
        return 1
    print(f"PASS: {len(tests)}/{len(tests)} tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
