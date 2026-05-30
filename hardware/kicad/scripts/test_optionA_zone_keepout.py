#!/usr/bin/env python3
"""test_optionA_zone_keepout.py — regression tests for Option A keepout carve.

Verifies:
  (a) carve_zone_keepout.py adds a rule-area zone with the expected
      layer + rect + rule settings + provenance.
  (b) audit_zone_keepout_provenance.py PASSES on a clean add.
  (c) audit FAILS when the keepout is removed from the board after add.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
CANONICAL = os.path.join(_HERE, "..", "pcbai_fpv4in1.kicad_pcb")


def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_pcbnew() and os.path.exists(CANONICAL),
                      "pcbnew + canonical board required")
class CarveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.input_board = os.path.join(self.tmp, "in.kicad_pcb")
        self.output_board = os.path.join(self.tmp, "out.kicad_pcb")
        self.prov_dir = os.path.join(self.tmp, "prov")
        shutil.copyfile(CANONICAL, self.input_board)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_carve(self, **kw):
        args = [sys.executable,
                os.path.join(_HERE, "carve_zone_keepout.py"),
                "--board", self.input_board,
                "--output", self.output_board,
                "--provenance", self.prov_dir]
        for k, v in kw.items():
            args.append(f"--{k.replace('_', '-')}")
            args.append(str(v))
        return subprocess.run(args, capture_output=True, text=True)

    def test_keepout_added_with_rule_area(self):
        import pcbnew
        r = self._run_carve(rect="28.0,60.0,36.0,62.0",
                             layer="B.Cu",
                             net="KILL_RAIL_N_CH1",
                             ref="KO_TEST_A")
        self.assertEqual(r.returncode, 0,
                          f"carve failed: {r.stderr}")
        b = pcbnew.LoadBoard(self.output_board)
        # Find our keepout
        ko = None
        for z in b.Zones():
            try:
                if z.GetZoneName() == "KO_TEST_A":
                    ko = z
                    break
            except Exception:
                continue
        self.assertIsNotNone(ko, "KO_TEST_A zone missing from board")
        self.assertEqual(pcbnew.LayerName(ko.GetLayer()), "B.Cu")
        self.assertTrue(ko.GetIsRuleArea())
        self.assertTrue(ko.GetDoNotAllowCopperPour())
        # Provenance
        provs = list(os.scandir(self.prov_dir))
        self.assertGreater(len(provs), 0)
        with open(provs[0].path) as f:
            doc = json.load(f)
        self.assertIn("DEV-010", doc["R21_deviation"])
        self.assertEqual(doc["keepout"]["layer"], "B.Cu")
        self.assertEqual(doc["keepout"]["net_opened"], "KILL_RAIL_N_CH1")

    def test_audit_passes_on_clean_add(self):
        r = self._run_carve(rect="28.0,60.0,36.0,62.0",
                             layer="B.Cu",
                             net="KILL_RAIL_N_CH1",
                             ref="KO_AUDIT_A")
        self.assertEqual(r.returncode, 0)
        audit = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_zone_keepout_provenance.py"),
             self.output_board, "--provenance-dir", self.prov_dir],
            capture_output=True, text=True)
        self.assertEqual(audit.returncode, 0,
                          f"audit FAILED: {audit.stdout}\n{audit.stderr}")
        self.assertIn("PASS", audit.stdout)

    def test_audit_fails_when_keepout_missing(self):
        """Provenance entry but no matching board zone → audit FAIL."""
        os.makedirs(self.prov_dir, exist_ok=True)
        with open(os.path.join(self.prov_dir, "MISSING.json"), "w") as f:
            json.dump({
                "keepout": {"ref": "KO_NONEXISTENT", "layer": "B.Cu",
                             "rect_mm": [28, 60, 36, 62],
                             "net_opened": "KILL_RAIL_N_CH1"},
                "R21_deviation": "DEV-010: zone keepout added board-only",
            }, f)
        audit = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_zone_keepout_provenance.py"),
             self.input_board, "--provenance-dir", self.prov_dir],
            capture_output=True, text=True)
        self.assertEqual(audit.returncode, 1,
                          f"audit should FAIL: {audit.stdout}")
        self.assertIn("missing", audit.stdout.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
