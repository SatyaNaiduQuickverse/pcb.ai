#!/usr/bin/env python3
"""test_dd_mst_root_inversion.py — regression tests for lever DD.

Verifies:
  (a) MST_ROOT_OVERRIDE contains the 3 chronic nets.
  (b) mst_root_index_for_net() returns the override pad's index when
      present; 0 otherwise.
  (c) Non-overridden nets return 0 (back-compat).
  (d) audit_mst_root_provenance PASSES on the synchronized SoT.
  (e) audit detects synthetic drop of a required net.
"""
from __future__ import annotations
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


class MSTRootOverrideTests(unittest.TestCase):

    def test_overrides_contain_chronic_nets(self):
        import route_subsystem_cooperative as RC
        for net in ("KILL_RAIL_N_CH1", "PWM_INLA_CH1", "GLB_CH1"):
            self.assertIn(net, RC.MST_ROOT_OVERRIDE,
                          f"{net} missing from MST_ROOT_OVERRIDE")

    def test_selector_returns_override_index(self):
        import route_subsystem_cooperative as RC
        # synthetic pad_info list mimicking BoardState.net_pads format
        # 8-tuple: (ref, padname, x, y, layers, sx, sy) — index 0 is J19.8
        # and we want the selector to find R76.1 (override target)
        pad_info = [
            ("J19", "8", 23.45, 64.46, (), 0.25, 0.6),
            ("D38", "2", 32.2, 57.60, (), 0.6, 0.45),
            ("D37", "2", 30.7, 61.20, (), 0.6, 0.45),
            ("R76", "1", 35.26, 60.80, (), 0.54, 0.64),
        ]
        idx = RC.mst_root_index_for_net("KILL_RAIL_N_CH1", pad_info)
        self.assertEqual(idx, 3, "expected R76.1 at index 3")

    def test_selector_back_compat_default(self):
        import route_subsystem_cooperative as RC
        pad_info = [
            ("J19", "8", 0, 0, (), 0, 0),
            ("OTHER", "1", 1, 1, (), 0, 0),
        ]
        # Net not in MST_ROOT_OVERRIDE → returns 0
        self.assertEqual(
            RC.mst_root_index_for_net("BEMF_A_CH1", pad_info), 0)

    def test_selector_missing_target_falls_back(self):
        """When override target is set but the pad isn't in the list
        (e.g., synthetic test board lacks R76), selector returns 0."""
        import route_subsystem_cooperative as RC
        pad_info = [
            ("J19", "8", 0, 0, (), 0, 0),
            ("D38", "2", 0, 0, (), 0, 0),
        ]
        # KILL_RAIL_N override targets R76.1 — not in this list
        self.assertEqual(
            RC.mst_root_index_for_net("KILL_RAIL_N_CH1", pad_info), 0)


class AuditGateTests(unittest.TestCase):

    def test_audit_passes_on_clean_sot(self):
        r = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_mst_root_provenance.py")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                          f"audit FAILED unexpectedly: {r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)

    def test_audit_detects_synthetic_drop(self):
        import importlib
        import route_subsystem_cooperative as RC
        orig = dict(RC.MST_ROOT_OVERRIDE)
        try:
            RC.MST_ROOT_OVERRIDE = {k: v for k, v in orig.items()
                                     if k != "KILL_RAIL_N_CH1"}
            import audit_mst_root_provenance as AM
            importlib.reload(AM)
            code, failures = AM.audit(None)
            self.assertEqual(code, 1, f"audit should detect drop: {failures}")
            self.assertTrue(any("KILL_RAIL_N_CH1" in f for f in failures))
        finally:
            RC.MST_ROOT_OVERRIDE = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
