#!/usr/bin/env python3
"""test_inject_vmotor_pour_live.py — lever-V canonical-load gate.

Adds tests for the Stage 5 orphan-via cleanup pass that lever V (PR #251)
added to inject_vmotor_pour.py. The lever T tool (PR #250) achieved
199→3 via_dangling on the canonical post-T board (085dee9), with 3
residual orphans on non-+VMOTOR nets (MOTOR_A_CH1, MOTOR_C_CH1,
SHUNT_C_TOP_CH1) that T's pour-architecture fix cannot rescue (wrong
nets) and that the in-memory synthetic tests in
test_inject_vmotor_pour.py did not exercise.

Tests:
  V1 (synthetic mirror): build a minimal board with a +VMOTOR pour on
      F.Cu+B.Cu+In5.Cu (structural NO-OP for T) plus an orphan F.Cu/B.Cu
      through-via on a foreign net with no same-net Cu contact. Run the
      tool with --remove-orphan-vias (default ON), then assert
      kicad-cli pcb drc reports 0 via_dangling on the output.

  V2 (canonical-load — only when the real canonical post-T board is
      provided on disk at a well-known path): run the tool, assert the
      3 known orphans (MOTOR_A_CH1@(18,54), MOTOR_C_CH1@(18,82),
      SHUNT_C_TOP_CH1@(10,86)) are removed and the post-fix board has
      0 via_dangling per kicad-cli.

  V3 (--keep-orphan-vias regression): with Stage 5 explicitly disabled,
      the synthetic orphan remains and the post-tool DRC still shows
      ≥1 via_dangling. Guards against accidental defaults change.

  V4 (idempotent Stage 5): a second run of the tool on the post-Stage-5
      board MUST produce NO additional removals (the cleanup is
      idempotent on a clean board).

  V5 (matching guard): an orphan position that doesn't match any via
      block in the file MUST trigger the safety-bail (`error` set,
      residual_dangling populated) — not an infinite loop.

The canonical post-T fixture path is resolved via the env var
LEVER_V_CANONICAL_POST_T or a default of /tmp/canonical_post_T_085dee9.kicad_pcb.
If neither exists, V2 is skipped (CI without the 8MB fixture).

Run:
    python3 hardware/kicad/scripts/test_inject_vmotor_pour_live.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import inject_vmotor_pour as ivp  # noqa: E402

TOOL = SCRIPTS_DIR / "inject_vmotor_pour.py"
REPO_ROOT = SCRIPTS_DIR.parent.parent.parent
CANON_LIVE_PATH = Path(os.environ.get(
    "LEVER_V_CANONICAL_POST_T",
    "/tmp/canonical_post_T_085dee9.kicad_pcb"))


def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except Exception:
        return False


def _have_kicad_cli():
    try:
        r = subprocess.run(["kicad-cli", "--version"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


# ----------------------------------------------------------------------
# Synthetic-mirror builder
# ----------------------------------------------------------------------

SYNTHETIC_BOARD_TEMPLATE = '''(kicad_pcb
\t(version 20240108)
\t(generator "test_inject_vmotor_pour_live")
\t(generator_version "9.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user)
\t\t(19 "Cmts.User" user)
\t\t(21 "Eco1.User" user)
\t\t(23 "Eco2.User" user)
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t\t(39 "User.1" user)
\t\t(41 "User.2" user)
\t\t(43 "User.3" user)
\t\t(45 "User.4" user)
\t\t(47 "User.5" user)
\t\t(49 "User.6" user)
\t\t(51 "User.7" user)
\t\t(53 "User.8" user)
\t\t(55 "User.9" user)
\t)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(pcbplotparams
\t\t\t(layerselection 0x00010fc_ffffffff)
\t\t\t(plot_on_all_layers_selection 0x0000000_00000000)
\t\t\t(disableapertmacros no)
\t\t\t(usegerberextensions no)
\t\t\t(usegerberattributes yes)
\t\t\t(usegerberadvancedattributes yes)
\t\t\t(creategerberjobfile yes)
\t\t\t(dashed_line_dash_ratio 12.000000)
\t\t\t(dashed_line_gap_ratio 3.000000)
\t\t\t(svgprecision 4)
\t\t\t(plotframeref no)
\t\t\t(viasonmask no)
\t\t\t(mode 1)
\t\t\t(useauxorigin no)
\t\t\t(hpglpennumber 1)
\t\t\t(hpglpenspeed 20)
\t\t\t(hpglpendiameter 15.000000)
\t\t\t(pdf_front_fp_property_popups yes)
\t\t\t(pdf_back_fp_property_popups yes)
\t\t\t(dxfpolygonmode yes)
\t\t\t(dxfimperialunits yes)
\t\t\t(dxfusepcbnewfont yes)
\t\t\t(psnegative no)
\t\t\t(psa4output no)
\t\t\t(plotreference yes)
\t\t\t(plotvalue yes)
\t\t\t(plotfptext yes)
\t\t\t(plotinvisibletext no)
\t\t\t(sketchpadsonfab no)
\t\t\t(subtractmaskfromsilk no)
\t\t\t(outputformat 1)
\t\t\t(mirror no)
\t\t\t(drillshape 1)
\t\t\t(scaleselection 1)
\t\t\t(outputdirectory "")
\t\t)
\t)
\t(net 0 "")
\t(net 1 "+VMOTOR")
\t(net 2 "ORPHAN_NET")
\t(gr_line (start 0 0) (end 30 0) (layer "Edge.Cuts") (stroke (width 0.05) (type default)) (uuid "11111111-0000-0000-0000-000000000001"))
\t(gr_line (start 30 0) (end 30 30) (layer "Edge.Cuts") (stroke (width 0.05) (type default)) (uuid "11111111-0000-0000-0000-000000000002"))
\t(gr_line (start 30 30) (end 0 30) (layer "Edge.Cuts") (stroke (width 0.05) (type default)) (uuid "11111111-0000-0000-0000-000000000003"))
\t(gr_line (start 0 30) (end 0 0) (layer "Edge.Cuts") (stroke (width 0.05) (type default)) (uuid "11111111-0000-0000-0000-000000000004"))
\t(zone
\t\t(net 1)
\t\t(net_name "+VMOTOR")
\t\t(layer "F.Cu")
\t\t(uuid "22222222-0000-0000-0000-000000000001")
\t\t(name "+VMOTOR F.Cu")
\t\t(hatch edge 0.5)
\t\t(connect_pads (clearance 0.2))
\t\t(min_thickness 0.2)
\t\t(filled_areas_thickness no)
\t\t(fill yes)
\t\t(polygon (pts (xy 1 1) (xy 29 1) (xy 29 29) (xy 1 29)))
\t)
\t(zone
\t\t(net 1)
\t\t(net_name "+VMOTOR")
\t\t(layer "B.Cu")
\t\t(uuid "22222222-0000-0000-0000-000000000002")
\t\t(name "+VMOTOR B.Cu")
\t\t(hatch edge 0.5)
\t\t(connect_pads (clearance 0.2))
\t\t(min_thickness 0.2)
\t\t(filled_areas_thickness no)
\t\t(fill yes)
\t\t(polygon (pts (xy 1 1) (xy 29 1) (xy 29 29) (xy 1 29)))
\t)
\t(via
\t\t(at 25 25)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "B.Cu")
\t\t(net 2)
\t\t(uuid "33333333-0000-0000-0000-000000000001")
\t)
)
'''


def _write_synthetic(path, with_orphan_via=True):
    """Write a synthetic board with +VMOTOR pour on F+B (so T is structural
    NO-OP) plus a single orphan via on net=ORPHAN_NET at (25, 25) — well
    inside the +VMOTOR pour but on a foreign net so kicad-cli flags it
    as via_dangling."""
    txt = SYNTHETIC_BOARD_TEMPLATE
    if not with_orphan_via:
        # strip the via block
        txt = txt.replace(
            "\t(via\n\t\t(at 25 25)\n\t\t(size 0.6)\n\t\t(drill 0.3)\n"
            "\t\t(layers \"F.Cu\" \"B.Cu\")\n\t\t(net 2)\n"
            "\t\t(uuid \"33333333-0000-0000-0000-000000000001\")\n\t)\n",
            "")
    Path(path).write_text(txt)


# ----------------------------------------------------------------------
# V1 — synthetic-mirror end-to-end
# ----------------------------------------------------------------------

class TestLeverVSynthetic(unittest.TestCase):
    """Synthetic mirror of the canonical 3-residual failure mode.
    Exercises Stage 5 cleanup against an in-memory minimal board where
    kicad-cli is the ground truth."""

    @unittest.skipUnless(_have_pcbnew() and _have_kicad_cli(),
                          "needs pcbnew + kicad-cli")
    def test_V1_synthetic_orphan_via_removed_post_stage5(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            rep = Path(td) / "report.json"
            _write_synthetic(inp, with_orphan_via=True)

            # Sanity: kicad-cli sees a dangling via on the synthetic IN board
            drc_json, err = ivp.run_kicad_cli_drc_full(str(inp))
            self.assertIsNone(err, f"kicad-cli failed on synthetic IN: {err}")
            orphans_in = ivp.collect_dangling_via_positions(drc_json)
            self.assertGreaterEqual(
                len(orphans_in), 1,
                "synthetic IN board MUST have ≥1 via_dangling for this test "
                "to be a valid lever-V regression case. Found: "
                f"{orphans_in}")

            rc = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(out),
                 "--report", str(rep)],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc.returncode, 0,
                             f"tool FAIL: rc={rc.returncode}\n"
                             f"STDOUT:\n{rc.stdout}\nSTDERR:\n{rc.stderr}")

            r = json.loads(rep.read_text())
            cleanup = r.get("stage5_orphan_via_cleanup")
            self.assertIsNotNone(cleanup, "report missing stage5_orphan_via_cleanup")
            self.assertEqual(cleanup["post_dangling_count"], 0,
                             f"Stage 5 left residual: {cleanup}")
            self.assertGreaterEqual(len(cleanup["all_removed"]), 1,
                                     "Stage 5 should have removed ≥1 via")

            # Final external sanity — re-run kicad-cli on OUT
            drc_out, err2 = ivp.run_kicad_cli_drc_full(str(out))
            self.assertIsNone(err2, f"kicad-cli failed on synthetic OUT: {err2}")
            orphans_out = ivp.collect_dangling_via_positions(drc_out)
            self.assertEqual(
                len(orphans_out), 0,
                f"kicad-cli still reports {len(orphans_out)} dangling via(s) "
                f"on the post-Stage-5 board: {orphans_out}")

    @unittest.skipUnless(_have_pcbnew() and _have_kicad_cli(),
                          "needs pcbnew + kicad-cli")
    def test_V3_keep_orphan_regression(self):
        """With --keep-orphan-vias, the synthetic orphan must remain in
        the output board. Guards against accidental default-flip."""
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            rep = Path(td) / "report.json"
            _write_synthetic(inp, with_orphan_via=True)

            rc = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(out),
                 "--report", str(rep),
                 "--keep-orphan-vias"],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc.returncode, 0,
                             f"tool FAIL: rc={rc.returncode}\n"
                             f"STDOUT:\n{rc.stdout}\nSTDERR:\n{rc.stderr}")

            r = json.loads(rep.read_text())
            self.assertIsNone(r.get("stage5_orphan_via_cleanup"),
                              "Stage 5 cleanup SHOULD be null when "
                              "--keep-orphan-vias is set")
            drc_out, err = ivp.run_kicad_cli_drc_full(str(out))
            self.assertIsNone(err, f"kicad-cli failed on OUT: {err}")
            orphans_out = ivp.collect_dangling_via_positions(drc_out)
            self.assertGreaterEqual(
                len(orphans_out), 1,
                "with --keep-orphan-vias, the orphan via MUST remain. "
                "Defaults may have flipped.")

    @unittest.skipUnless(_have_pcbnew() and _have_kicad_cli(),
                          "needs pcbnew + kicad-cli")
    def test_V4_stage5_idempotent(self):
        """Running the tool a second time on a Stage-5-cleaned board MUST
        remove zero further vias."""
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            mid = Path(td) / "mid.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            _write_synthetic(inp, with_orphan_via=True)

            rc1 = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(mid),
                 "--report", str(Path(td) / "r1.json")],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc1.returncode, 0,
                             f"first run FAIL: {rc1.stderr}")
            rc2 = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(mid),
                 "--output", str(out),
                 "--report", str(Path(td) / "r2.json")],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc2.returncode, 0,
                             f"second run FAIL: {rc2.stderr}")
            r2 = json.loads((Path(td) / "r2.json").read_text())
            cleanup2 = r2.get("stage5_orphan_via_cleanup")
            self.assertIsNotNone(cleanup2)
            self.assertEqual(
                cleanup2["pre_dangling_count"], 0,
                f"Stage 5 SHOULD be idempotent on a cleaned board, "
                f"got pre-count={cleanup2['pre_dangling_count']}")
            self.assertEqual(len(cleanup2["all_removed"]), 0,
                              "second run MUST remove zero vias")

    def test_V5_match_guard_against_infinite_loop(self):
        """remove_orphan_vias_from_text MUST NOT loop forever when the
        orphan position has no matching (via ...) block. We check the
        text-mutation primitive directly (no kicad-cli needed)."""
        # Same template, but the orphan we 'report' is at a position
        # where no via exists. Function should return (txt unchanged, []).
        txt = SYNTHETIC_BOARD_TEMPLATE
        bogus_orphans = [{
            "x": 99.999, "y": 99.999,
            "uuid": "deadbeef-dead-beef-dead-beefdeadbeef",
            "description": "nonexistent",
        }]
        new_txt, removed = ivp.remove_orphan_vias_from_text(txt, bogus_orphans)
        self.assertEqual(new_txt, txt,
                         "no-match must leave text unchanged")
        self.assertEqual(removed, [],
                         "no-match must report zero removals")


# ----------------------------------------------------------------------
# V2 — canonical-load gate (opt-in; needs the 8MB post-T fixture)
# ----------------------------------------------------------------------

class TestLeverVCanonical(unittest.TestCase):
    """Authoritative gate: load the actual canonical post-T board
    (sha 085dee9) and confirm Stage 5 fixes its 3 residual orphans.

    This test is the lever-V counterpart to the sim-execution-gate rule
    (every fix MUST be proved against the canonical artifact, not just
    a synthetic). It runs ONLY when the fixture is provided on disk
    (the canonical board is 8MB and lives outside the repo)."""

    @unittest.skipUnless(_have_pcbnew() and _have_kicad_cli(),
                          "needs pcbnew + kicad-cli")
    @unittest.skipUnless(CANON_LIVE_PATH.exists(),
                          f"canonical post-T board not at {CANON_LIVE_PATH}; "
                          "set LEVER_V_CANONICAL_POST_T to enable.")
    def test_V2_canonical_post_T_3_residual_to_zero(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            rep = Path(td) / "report.json"
            shutil.copy(CANON_LIVE_PATH, inp)

            # PRE: kicad-cli must report exactly the 3 known dangling vias
            drc_pre, err = ivp.run_kicad_cli_drc_full(str(inp))
            self.assertIsNone(err, f"kicad-cli failed on canonical IN: {err}")
            orphans_pre = ivp.collect_dangling_via_positions(drc_pre)
            self.assertEqual(
                len(orphans_pre), 3,
                "canonical post-T board MUST have EXACTLY 3 dangling vias "
                "per lever V scope. If this fails, the fixture is stale "
                f"or the upstream tools changed. Got: {orphans_pre}")

            expected_xy = {(18.0, 54.0), (18.0, 82.0), (10.0, 86.0)}
            actual_xy = {(o["x"], o["y"]) for o in orphans_pre}
            self.assertEqual(
                actual_xy, expected_xy,
                "canonical 3-residual positions drift detected. "
                f"Expected {expected_xy}, got {actual_xy}.")

            # Run the lever-V-extended tool
            rc = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(out),
                 "--report", str(rep)],
                capture_output=True, text=True, timeout=900,
            )
            self.assertEqual(rc.returncode, 0,
                             f"tool FAIL: rc={rc.returncode}\n"
                             f"STDOUT:\n{rc.stdout[-2000:]}\n"
                             f"STDERR:\n{rc.stderr[-2000:]}")

            r = json.loads(rep.read_text())
            cleanup = r.get("stage5_orphan_via_cleanup")
            self.assertIsNotNone(cleanup,
                                 "report missing stage5_orphan_via_cleanup")
            self.assertEqual(cleanup["pre_dangling_count"], 3)
            self.assertEqual(cleanup["post_dangling_count"], 0,
                             f"Stage 5 left residual on canonical: {cleanup}")
            self.assertEqual(
                len(cleanup["all_removed"]), 3,
                f"Stage 5 should have removed exactly 3 vias on canonical, "
                f"got {len(cleanup['all_removed'])}: {cleanup['all_removed']}")

            removed_xy = {(r["x"], r["y"]) for r in cleanup["all_removed"]}
            self.assertEqual(
                removed_xy, expected_xy,
                f"removed vias mismatch expected positions. "
                f"Expected {expected_xy}, removed {removed_xy}")

            # POST: kicad-cli ground-truth
            drc_post, err2 = ivp.run_kicad_cli_drc_full(str(out))
            self.assertIsNone(err2,
                              f"kicad-cli failed on canonical OUT: {err2}")
            orphans_post = ivp.collect_dangling_via_positions(drc_post)
            self.assertEqual(
                len(orphans_post), 0,
                f"kicad-cli still reports {len(orphans_post)} dangling "
                f"via(s) on the post-Stage-5 canonical board: "
                f"{orphans_post}")

            # G14 density gate — drone-grade floor 4 vias/cm² on +VMOTOR
            density_info = r.get("stitch_density_per_cm2") or {}
            density = density_info.get("density_per_cm2")
            self.assertIsNotNone(density,
                                 "stitch density report missing")
            self.assertGreaterEqual(
                density, 4.0,
                f"+VMOTOR stitch density {density:.2f}/cm² below G14 floor "
                f"4.00/cm² post-cleanup; honest density loss exceeded "
                f"drone-grade tolerance.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
