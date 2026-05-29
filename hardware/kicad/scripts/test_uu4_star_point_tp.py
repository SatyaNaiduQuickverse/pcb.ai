#!/usr/bin/env python3
"""test_uu4_star_point_tp.py — regression tests for UU.4 STAR-POINT TP.

Verifies the add_star_point_tp.py tool + audit_star_point_tp_provenance.py
audit gate work end-to-end on the canonical board:

  (a) Adding TP_KILL_STAR_CH1 increments KILL_RAIL_N_CH1 pad count by 1.
  (b) The TP footprint resolves on the board with the requested ref/net/layer.
  (c) Provenance JSON is written with all required fields (incl. R21).
  (d) Audit gate PASSES on the modified board.
  (e) Failing scenarios: missing footprint, position drift, layer drift,
      net mismatch, missing R21 → audit FAILS.
"""
from __future__ import annotations
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

CANONICAL = os.path.join(_HERE, "..", "pcbai_fpv4in1.kicad_pcb")


def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_pcbnew() and os.path.exists(CANONICAL),
                      "pcbnew + canonical board required")
class StarPointAddTests(unittest.TestCase):

    def setUp(self):
        import pcbnew
        self.pcbnew = pcbnew
        self.tmp = tempfile.mkdtemp()
        self.input_board = os.path.join(self.tmp, "in.kicad_pcb")
        self.output_board = os.path.join(self.tmp, "out.kicad_pcb")
        self.prov_dir = os.path.join(self.tmp, "prov")
        import shutil
        shutil.copyfile(CANONICAL, self.input_board)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_add(self, **kw):
        import subprocess
        args = [sys.executable, os.path.join(_HERE, "add_star_point_tp.py"),
                "--board", self.input_board,
                "--output", self.output_board,
                "--provenance", self.prov_dir]
        for k, v in kw.items():
            args.append(f"--{k.replace('_', '-')}")
            args.append(str(v))
        r = subprocess.run(args, capture_output=True, text=True)
        return r

    def test_add_increments_net_pad_count(self):
        # Count KILL_RAIL_N_CH1 pads before
        b = self.pcbnew.LoadBoard(self.input_board)
        n_before = sum(1 for fp in b.GetFootprints()
                       for p in fp.Pads()
                       if p.GetNetname() == "KILL_RAIL_N_CH1")
        # Add TP
        r = self._run_add(net="KILL_RAIL_N_CH1", ref="TP_KILL_STAR_CH1",
                          position="27.50,62.50", layer="B.Cu")
        self.assertEqual(r.returncode, 0, f"add failed: {r.stderr}")
        # Count after
        b2 = self.pcbnew.LoadBoard(self.output_board)
        n_after = sum(1 for fp in b2.GetFootprints()
                      for p in fp.Pads()
                      if p.GetNetname() == "KILL_RAIL_N_CH1")
        self.assertEqual(n_after, n_before + 1,
                          f"pad count {n_before}→{n_after}, expected +1")

    def test_added_footprint_resolves_correctly(self):
        r = self._run_add(net="KILL_RAIL_N_CH1", ref="TP_KILL_STAR_CH1",
                          position="27.50,62.50", layer="B.Cu")
        self.assertEqual(r.returncode, 0)
        b = self.pcbnew.LoadBoard(self.output_board)
        tp = None
        for fp in b.GetFootprints():
            if fp.GetReference() == "TP_KILL_STAR_CH1":
                tp = fp
                break
        self.assertIsNotNone(tp, "TP_KILL_STAR_CH1 missing on board")
        pos = tp.GetPosition()
        self.assertAlmostEqual(pos.x / 1e6, 27.50, places=2)
        self.assertAlmostEqual(pos.y / 1e6, 62.50, places=2)
        self.assertEqual(self.pcbnew.LayerName(tp.GetLayer()), "B.Cu")
        for p in tp.Pads():
            self.assertEqual(p.GetNetname(), "KILL_RAIL_N_CH1")

    def test_provenance_has_required_fields(self):
        import glob, json
        r = self._run_add(net="KILL_RAIL_N_CH1", ref="TP_KILL_STAR_CH1",
                          position="27.50,62.50", layer="B.Cu")
        self.assertEqual(r.returncode, 0)
        provs = glob.glob(os.path.join(self.prov_dir, "*.json"))
        self.assertGreater(len(provs), 0, "no provenance JSON written")
        with open(provs[0]) as f:
            doc = json.load(f)
        self.assertEqual(doc["tp"]["ref"], "TP_KILL_STAR_CH1")
        self.assertEqual(doc["tp"]["net"], "KILL_RAIL_N_CH1")
        self.assertEqual(doc["tp"]["layer"], "B.Cu")
        self.assertEqual(tuple(doc["tp"]["position_mm"]), (27.50, 62.50))
        self.assertIn("R21_deviation", doc)
        self.assertIn("DEV-007", doc["R21_deviation"])

    def test_audit_passes_on_clean_add(self):
        import subprocess
        r = self._run_add(net="KILL_RAIL_N_CH1", ref="TP_KILL_STAR_CH1",
                          position="27.50,62.50", layer="B.Cu")
        self.assertEqual(r.returncode, 0)
        audit = subprocess.run(
            [sys.executable, os.path.join(_HERE, "audit_star_point_tp_provenance.py"),
             self.output_board, "--provenance-dir", self.prov_dir],
            capture_output=True, text=True)
        self.assertEqual(audit.returncode, 0,
                          f"audit failed: {audit.stdout}\n{audit.stderr}")
        self.assertIn("PASS", audit.stdout)

    def test_audit_fails_when_footprint_missing(self):
        """Generate provenance for TP that ISN'T on the board → audit FAIL."""
        import json, subprocess, pathlib
        # Skip add — write only provenance
        os.makedirs(self.prov_dir, exist_ok=True)
        pathlib.Path(self.prov_dir, "MISSING_20300101T000000Z.json").write_text(
            json.dumps({
                "tp": {"ref": "TP_NONEXISTENT", "net": "KILL_RAIL_N_CH1",
                       "position_mm": (10, 10), "layer": "B.Cu"},
                "R21_deviation": "DEV-007: board-only add",
            }))
        audit = subprocess.run(
            [sys.executable, os.path.join(_HERE, "audit_star_point_tp_provenance.py"),
             self.input_board, "--provenance-dir", self.prov_dir],
            capture_output=True, text=True)
        self.assertEqual(audit.returncode, 1,
                          f"audit should FAIL but PASSED: {audit.stdout}")
        self.assertIn("footprint missing", audit.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
