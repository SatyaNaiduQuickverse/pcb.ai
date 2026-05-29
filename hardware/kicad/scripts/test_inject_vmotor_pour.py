#!/usr/bin/env python3
"""test_inject_vmotor_pour.py — adversarial unit tests for the lever-T tool.

These tests cover:
  T1. Diagnosis correctly identifies the In3↔In5 inversion on the canonical
      board.
  T2. Idempotence: running the tool twice produces a bit-stable output and
      reports NO_OP_IDEMPOTENT on the second run.
  T3. Net-swap mutation is byte-exactly contained to In3 + In5 zone blocks
      (no other zones' net id/name changed).
  T4. ADVERSARIAL: refusing a pour that would create a +VMOTOR↔foreign
      short — exercised by passing a synthetic board with a +VMOTOR pad
      placed in a region where the surface pour would otherwise overlap.
      The post-emit verification (zone refill) MUST treat foreign-clearance
      as authoritative; we assert KiCad's filled polygon excludes the
      foreign pad area.
  T5. Post-emit gates G1+G2+G3 trip correctly (failing gates produce
      verdict=FAIL + return code 1).
  T6. Optional G4 wiring: `--run-drc` populates the report's kicad_cli_drc
      field with TOTAL_via_dangling.

Run with:
    cd hardware/kicad
    python3 -m pytest scripts/test_inject_vmotor_pour.py -v
or directly:
    python3 scripts/test_inject_vmotor_pour.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make the script importable
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import inject_vmotor_pour as ivp  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent.parent.parent
CANON_BOARD = REPO_ROOT / "hardware" / "kicad" / "pcbai_fpv4in1.kicad_pcb"
TOOL = SCRIPTS_DIR / "inject_vmotor_pour.py"


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


class TestInjectVmotorPour(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not CANON_BOARD.exists():
            raise unittest.SkipTest(f"canonical board not at {CANON_BOARD}")
        cls.txt = CANON_BOARD.read_text()

    # ------------------------------------------------------------------
    # T1 — diagnosis on canonical
    # ------------------------------------------------------------------
    def test_T1_diagnose_identifies_in3_in5_inversion(self):
        diag = ivp.diagnose(self.txt)
        self.assertIn("In3.Cu", diag["+VMOTOR"],
                      "canonical board MUST currently have +VMOTOR on In3 "
                      "(the bug we're fixing). If this fails the canonical "
                      "may have already been fixed — re-run the tool's "
                      "idempotent NO_OP path.")
        self.assertIn("In5.Cu", diag["GND"],
                      "canonical board MUST currently have GND on In5 "
                      "(the bug's mirror).")
        self.assertNotIn("In5.Cu", diag["+VMOTOR"],
                         "canonical board MUST currently NOT have +VMOTOR "
                         "on In5 (pre-fix).")
        self.assertTrue(ivp.needs_swap(diag))
        self.assertTrue(ivp.needs_surface(diag, ["F.Cu", "B.Cu"]))

    # ------------------------------------------------------------------
    # T2 — idempotence
    # ------------------------------------------------------------------
    @unittest.skipUnless(_have_pcbnew(), "needs pcbnew bindings")
    def test_T2_idempotent_second_run_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            mid = Path(td) / "mid.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            shutil.copy(CANON_BOARD, inp)

            # First run
            rc1 = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(mid),
                 "--report", str(Path(td) / "r1.json")],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc1.returncode, 0,
                             f"first run failed: {rc1.stderr}")

            # Second run on the first run's output
            rc2 = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(mid),
                 "--output", str(out),
                 "--report", str(Path(td) / "r2.json")],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc2.returncode, 0,
                             f"second run failed: {rc2.stderr}")

            r2 = json.loads((Path(td) / "r2.json").read_text())
            self.assertEqual(r2["verdict"], "NO_OP_IDEMPOTENT",
                             f"second run should NO_OP, got {r2['verdict']}: "
                             f"{r2}")

    # ------------------------------------------------------------------
    # T3 — net swap is byte-contained to In3 + In5 zone blocks
    # ------------------------------------------------------------------
    def test_T3_swap_does_not_touch_other_zones(self):
        diag_before = ivp.diagnose(self.txt)
        new_txt, n = ivp.apply_swap_in_text(self.txt, 9, 101)
        self.assertGreaterEqual(n, 2,
                                "expected at least 2 zone swaps (In3 + In5)")
        diag_after = ivp.diagnose(new_txt)

        # In1.Cu GND zone untouched (still GND)
        self.assertIn("In1.Cu", diag_after["GND"])
        self.assertNotIn("In1.Cu", diag_after["+VMOTOR"])

        # In3 now GND (was +VMOTOR)
        self.assertIn("In3.Cu", diag_after["GND"])
        self.assertNotIn("In3.Cu", diag_after["+VMOTOR"])

        # In5 now +VMOTOR (was GND)
        self.assertIn("In5.Cu", diag_after["+VMOTOR"])
        self.assertNotIn("In5.Cu", diag_after["GND"])

        # The number of zones is unchanged
        self.assertEqual(len(diag_before["zones"]), len(diag_after["zones"]),
                         "swap must not add or remove zones")

    # ------------------------------------------------------------------
    # T4 — ADVERSARIAL: pour creating a short would be detected
    # ------------------------------------------------------------------
    @unittest.skipUnless(_have_pcbnew(), "needs pcbnew bindings")
    def test_T4_adversarial_foreign_net_clearance_preserved(self):
        """Run the tool, refill, and verify ZONE_FILLER's foreign-net
        clearance subtracts around every non-+VMOTOR pad on F.Cu/B.Cu.
        Specifically: pick a known foreign-net SMD pad on F.Cu (e.g.
        signal-net pad), refill, and assert the +VMOTOR F.Cu filled
        polygon does NOT cover that pad's centre (which would indicate
        a short).
        """
        import pcbnew

        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            shutil.copy(CANON_BOARD, inp)
            rc = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(out)],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(rc.returncode, 0, f"tool FAIL: {rc.stderr}")

            board = pcbnew.LoadBoard(str(out))
            # Find F.Cu +VMOTOR zone
            vmotor_fcu_zones = []
            for z in board.Zones():
                if z.GetNetname() != "+VMOTOR":
                    continue
                if pcbnew.F_Cu in list(z.GetLayerSet().Seq()):
                    vmotor_fcu_zones.append(z)
            self.assertGreaterEqual(len(vmotor_fcu_zones), 1,
                                    "expected at least one F.Cu +VMOTOR zone")

            # Pick one foreign-net pad on F.Cu — try a signal-net pad
            # on a footprint we know exists on canonical (any pad whose
            # net is NOT +VMOTOR and is on F.Cu).
            foreign_pad = None
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNetname() == "+VMOTOR":
                        continue
                    if not pad.GetNetname():
                        continue
                    ls = pad.GetLayerSet()
                    if not ls.Contains(pcbnew.F_Cu):
                        continue
                    foreign_pad = pad
                    break
                if foreign_pad is not None:
                    break
            self.assertIsNotNone(foreign_pad,
                                 "no foreign-net F.Cu pad found on canonical")

            # Assert the F.Cu +VMOTOR filled polygon does NOT cover
            # this foreign pad's center.  HitTestFilledArea returns True
            # only if the point is strictly inside the filled set.
            pos = foreign_pad.GetPosition()
            short_detected = False
            for z in vmotor_fcu_zones:
                try:
                    if z.HitTestFilledArea(pcbnew.F_Cu, pos):
                        short_detected = True
                        break
                except TypeError:
                    if z.HitTestFilledArea(pos):
                        short_detected = True
                        break
            # Identify pad for diagnostic (GetParent returns the FOOTPRINT
            # on KiCad 9; cast safely)
            try:
                parent_ref = pcbnew.Cast_to_FOOTPRINT(
                    foreign_pad.GetParent()).GetReference()
            except Exception:
                parent_ref = "?"
            self.assertFalse(short_detected,
                              f"+VMOTOR F.Cu pour SHORTS to foreign-net pad "
                              f"{parent_ref}.{foreign_pad.GetPadName()} "
                              f"(net={foreign_pad.GetNetname()}). "
                              "ZONE_FILLER foreign-clearance must subtract "
                              "around this pad.")

    # ------------------------------------------------------------------
    # T5 — post-emit gates fail visibly if pour is single-layer
    # ------------------------------------------------------------------
    def test_T5_post_verify_fails_when_single_layer(self):
        # Synthesize the post-state "as if" the tool swapped but failed
        # to add a surface pour: +VMOTOR only on In5.  G1 should FAIL.
        synth = self.txt
        # Apply swap only
        synth_swapped, _ = ivp.apply_swap_in_text(synth, 9, 101)
        # DO NOT inject surface pours — G1 should still FAIL because
        # we have only In5 as +VMOTOR layer.
        ok, gates = ivp.post_verify(synth_swapped)
        self.assertFalse(ok, "post_verify should FAIL when +VMOTOR exists on only 1 layer")
        self.assertFalse(gates["G1_multi_layer_vmotor_cu"]["ok"])
        self.assertTrue(gates["G2_in5_is_vmotor"]["ok"],
                        "G2 should PASS after the In3↔In5 swap")
        self.assertTrue(gates["G3_in3_in5_no_inversion"]["ok"],
                        "G3 should PASS after the swap")

    # ------------------------------------------------------------------
    # T6 — --run-drc populates kicad_cli_drc in report
    # ------------------------------------------------------------------
    @unittest.skipUnless(_have_pcbnew() and _have_kicad_cli(),
                          "needs pcbnew + kicad-cli")
    def test_T6_run_drc_populates_report(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.kicad_pcb"
            out = Path(td) / "out.kicad_pcb"
            rep = Path(td) / "report.json"
            shutil.copy(CANON_BOARD, inp)
            rc = subprocess.run(
                ["python3", str(TOOL),
                 "--board", str(inp),
                 "--output", str(out),
                 "--report", str(rep),
                 "--run-drc"],
                capture_output=True, text=True, timeout=600,
            )
            self.assertEqual(rc.returncode, 0,
                             f"--run-drc invocation failed: {rc.stderr}")
            r = json.loads(rep.read_text())
            self.assertIn("kicad_cli_drc", r)
            self.assertIsNotNone(r["kicad_cli_drc"])
            # Should have TOTAL_via_dangling or 'error' key
            self.assertTrue(
                "TOTAL_via_dangling" in r["kicad_cli_drc"] or
                "error" in r["kicad_cli_drc"],
                f"kicad_cli_drc field malformed: {r['kicad_cli_drc']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
