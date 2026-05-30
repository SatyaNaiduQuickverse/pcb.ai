#!/usr/bin/env python3
"""test_ii_obstacle_overlay.py — regression tests for lever II.

Verifies:
  (a) render_obstacle_overlay.py produces JSON with all required fields.
  (b) audit_obstacle_overlay.py PASSES on a complete JSON.
  (c) audit FAILS on a JSON missing required fields.
  (d) Zone-cover detection works (synthetic case).
"""
from __future__ import annotations
import json
import os
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
class RenderOverlayTests(unittest.TestCase):
    def test_produces_complete_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            out = tf.name
        try:
            r = subprocess.run([
                sys.executable,
                os.path.join(_HERE, "render_obstacle_overlay.py"),
                "--board", CANONICAL,
                "--location", "35.26,60.80",
                "--layer", "B.Cu",
                "--radius", "8.0",
                "--owner-net", "KILL_RAIL_N_CH1",
                "--output", out,
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0,
                              f"render failed: {r.stderr}")
            doc = json.loads(open(out).read())
            # required fields
            for k in ("location", "layer", "radius_mm", "owner_net",
                      "foreign_tracks", "foreign_pads", "foreign_vias",
                      "zone_fills", "owner_items"):
                self.assertIn(k, doc)
            # R76.1 should be the owner pad detected
            self.assertEqual(doc["owner_net"], "KILL_RAIL_N_CH1")
            self.assertTrue(any(
                i.get("type") == "pad" and i.get("ref") == "R76"
                for i in doc.get("owner_items", [])))
        finally:
            os.unlink(out)

    def test_detects_vmotor_zone_cover_on_r76(self):
        """On canonical, +VMOTOR zone fill covers R76.1 location on B.Cu —
        confirming the chronic leaf blocker."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            out = tf.name
        try:
            subprocess.run([
                sys.executable,
                os.path.join(_HERE, "render_obstacle_overlay.py"),
                "--board", CANONICAL,
                "--location", "35.26,60.80",
                "--layer", "B.Cu",
                "--radius", "8.0",
                "--owner-net", "KILL_RAIL_N_CH1",
                "--output", out,
            ], capture_output=True, text=True)
            doc = json.loads(open(out).read())
            zones_cover = [z for z in doc["zone_fills"]
                            if z.get("covers_location")]
            self.assertGreater(
                len(zones_cover), 0,
                "expected ≥1 zone to cover R76.1 location on B.Cu")
            # +VMOTOR specifically should be one of them
            self.assertTrue(any(z["net"] == "+VMOTOR" for z in zones_cover),
                             f"+VMOTOR not among covers: {zones_cover}")
        finally:
            os.unlink(out)


class AuditGateTests(unittest.TestCase):
    def test_audit_passes_on_complete_json(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = {
                "location": [35.26, 60.80], "layer": "B.Cu",
                "radius_mm": 8.0, "owner_net": "KILL_RAIL_N_CH1",
                "foreign_tracks": [], "foreign_pads": [],
                "foreign_vias": [], "zone_fills": [
                    {"net": "+VMOTOR", "bbox": [2, 2, 98, 98],
                     "covers_location": True}],
                "owner_items": [{"type": "pad", "ref": "R76", "pad": "1"}],
            }
            with open(os.path.join(tmp, "good.json"), "w") as f:
                json.dump(doc, f)
            r = subprocess.run([
                sys.executable,
                os.path.join(_HERE, "audit_obstacle_overlay.py"),
                "--diagnostic-dir", tmp,
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0,
                              f"audit FAILED unexpectedly: {r.stdout}")
            self.assertIn("PASS", r.stdout)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_fails_on_missing_field(self):
        tmp = tempfile.mkdtemp()
        try:
            # missing zone_fills field
            doc = {
                "location": [35.26, 60.80], "layer": "B.Cu",
                "radius_mm": 8.0, "owner_net": "KILL_RAIL_N_CH1",
                "foreign_tracks": [], "foreign_pads": [],
                "foreign_vias": [],
                "owner_items": [],
            }
            with open(os.path.join(tmp, "bad.json"), "w") as f:
                json.dump(doc, f)
            r = subprocess.run([
                sys.executable,
                os.path.join(_HERE, "audit_obstacle_overlay.py"),
                "--diagnostic-dir", tmp,
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1,
                              f"audit should FAIL: {r.stdout}")
            self.assertIn("zone_fills", r.stdout)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
