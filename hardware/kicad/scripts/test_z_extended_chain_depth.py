#!/usr/bin/env python3
"""test_z_extended_chain_depth.py — regression tests for lever Z.

Verifies:
  (a) K3_CHAIN_DEPTH_CHRONIC ≥ 6 (Sai spec); CHRONIC = 8 in current SoT.
  (b) K3_CHAIN_DEPTH_DEFAULT = 4 (preserved back-compat for non-chronics).
  (c) k3_chain_depth_for_net() returns CHRONIC for chronic nets + DEFAULT
      for everything else.
  (d) K3_CHAIN_DEPTH_OVERRIDES contains the 5 chronic residuals.
  (e) audit_k3_chain_depth_compliance.py PASSES on the current SoT state.
"""
from __future__ import annotations
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


class ChainDepthConstantTests(unittest.TestCase):

    def test_default_preserved(self):
        import route_subsystem_cooperative as RC
        self.assertEqual(RC.K3_CHAIN_DEPTH_DEFAULT, 4,
                          "DEFAULT depth must remain 4 for back-compat")

    def test_chronic_at_least_6(self):
        import route_subsystem_cooperative as RC
        self.assertGreaterEqual(RC.K3_CHAIN_DEPTH_CHRONIC, 6,
                                 "CHRONIC depth must be ≥ 6 per Sai Z spec")
        self.assertEqual(RC.K3_CHAIN_DEPTH_CHRONIC, 8,
                          "Current SoT: CHRONIC=8")

    def test_overrides_include_chronics(self):
        import route_subsystem_cooperative as RC
        for net in ("PWM_INLA_CH1", "GLB_CH1", "KILL_RAIL_N_CH1",
                    "PWM_INHB_CH1", "SWDIO_CH1"):
            self.assertIn(net, RC.K3_CHAIN_DEPTH_OVERRIDES,
                          f"{net} missing from K3_CHAIN_DEPTH_OVERRIDES")
            self.assertEqual(RC.K3_CHAIN_DEPTH_OVERRIDES[net],
                              RC.K3_CHAIN_DEPTH_CHRONIC,
                              f"{net} depth != CHRONIC")

    def test_selector_chronic_vs_default(self):
        import route_subsystem_cooperative as RC
        # Chronic
        for net in ("PWM_INLA_CH1", "GLB_CH1", "KILL_RAIL_N_CH1"):
            self.assertEqual(RC.k3_chain_depth_for_net(net),
                              RC.K3_CHAIN_DEPTH_CHRONIC)
        # Non-chronic
        for net in ("BEMF_A_CH1", "GND", "+VMOTOR", "MOTOR_A_CH1"):
            self.assertEqual(RC.k3_chain_depth_for_net(net),
                              RC.K3_CHAIN_DEPTH_DEFAULT)


class AuditGateTests(unittest.TestCase):

    def test_audit_passes_on_clean_sot(self):
        r = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_k3_chain_depth_compliance.py")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                          f"audit FAILED unexpectedly: {r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)

    def test_audit_detects_synthetic_chronic_drop(self):
        """Patch K3_CHAIN_DEPTH_OVERRIDES in-memory to drop a chronic;
        audit must detect."""
        import importlib
        import route_subsystem_cooperative as RC
        orig = dict(RC.K3_CHAIN_DEPTH_OVERRIDES)
        try:
            RC.K3_CHAIN_DEPTH_OVERRIDES = {k: v for k, v in orig.items()
                                            if k != "KILL_RAIL_N_CH1"}
            import audit_k3_chain_depth_compliance as AK
            importlib.reload(AK)
            code, failures = AK.audit(None)
            self.assertEqual(code, 1, f"audit should detect drop: {failures}")
            self.assertTrue(any("KILL_RAIL_N_CH1" in f for f in failures))
        finally:
            RC.K3_CHAIN_DEPTH_OVERRIDES = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
