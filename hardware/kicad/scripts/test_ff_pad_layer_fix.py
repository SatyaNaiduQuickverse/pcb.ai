#!/usr/bin/env python3
"""test_ff_pad_layer_fix.py — regression tests for lever FF pad-layer fix.

Verifies:
  (a) extract_problem in run_on_board.py derives pin layer from LayerSet
      (B.Cu-only SMD pads correctly identified as B.Cu, not F.Cu).
  (b) audit_pad_layer_detection.py PASSES on the fixed source.
  (c) audit_pad_layer_detection.py FAILS on a planted-bug stub file.
"""
from __future__ import annotations
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "routing_engine"))


def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_pcbnew(), "pcbnew required")
class PadLayerExtractionTests(unittest.TestCase):
    """The Lever FF fix at run_on_board.py:457 must derive B.Cu for SMD
    pads with single-layer LayerSet={B.Cu}."""

    def test_b_cu_only_pad_resolves_to_b_cu(self):
        """Build a synthetic board with one B.Cu-only SMD pad; verify the
        extract_problem path produces Pin.layer == 'B.Cu'."""
        import pcbnew
        import run_on_board as ROB
        # Lazy import the F module (fixtures)
        from routing_engine import fixtures as F

        board = pcbnew.BOARD()
        # Add 2 footprints in CH1 zone with B.Cu pads (so net has 2 pads)
        fps = []
        for i, ref in enumerate(["R76_TEST_A", "R76_TEST_B"]):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I(int((15 + i * 5) * 1e6),
                                            int(70e6)))
            pad = pcbnew.PAD(fp)
            pad.SetNumber("1")
            pad.SetPosition(pcbnew.VECTOR2I(int((15 + i * 5) * 1e6),
                                             int(70e6)))
            pad.SetSize(pcbnew.VECTOR2I(int(0.6e6), int(0.6e6)))
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.B_Cu)
            pad.SetLayerSet(ls)
            fp.Add(pad)
            board.Add(fp)
            fps.append(fp)
        # Save board
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
            path = tf.name
        try:
            pcbnew.SaveBoard(path, board)
            # extract_problem honors CH1 zone; pads at x=15-20 y=70 are in CH1
            problem, meta = ROB.extract_problem(path, subsystem="CH1")
            # Find our test pins
            test_pin_layers = [p.layer for p in problem.pins
                                if p.id.startswith("R76_TEST_")]
            if not test_pin_layers:
                self.skipTest("test pins not in CH1 zone / not extracted")
            # Pre-FF would all be "F.Cu"; post-FF should be "B.Cu"
            self.assertTrue(all(L == "B.Cu" for L in test_pin_layers),
                             f"expected all B.Cu, got {test_pin_layers}")
        finally:
            os.unlink(path)


class AuditScannerTests(unittest.TestCase):
    """The audit_pad_layer_detection scanner correctly accepts the fixed
    source and rejects a planted-bug stub."""

    def test_audit_passes_on_clean_source(self):
        import subprocess
        r = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_pad_layer_detection.py"),
             "--root", os.path.join(_HERE, "..")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                          f"audit FAILED unexpectedly: {r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)

    def test_audit_fails_on_planted_misuse(self):
        """Make a temp file that uses pad.GetLayer() in routing context."""
        import subprocess
        tmp = tempfile.mkdtemp()
        try:
            scripts_dir = os.path.join(tmp, "scripts")
            os.makedirs(os.path.join(scripts_dir, "routing_engine"))
            # Planted bug file
            with open(os.path.join(scripts_dir, "routing_engine",
                                     "planted_bug.py"), "w") as f:
                f.write("# planted lever FF bug\n")
                f.write("def get_pad_layer(pad):\n")
                f.write("    return pad.GetLayer()\n")
            r = subprocess.run(
                [sys.executable,
                 os.path.join(_HERE, "audit_pad_layer_detection.py"),
                 "--root", scripts_dir],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 1,
                              f"audit should FAIL: {r.stdout}")
            self.assertIn("pad.GetLayer", r.stdout)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
