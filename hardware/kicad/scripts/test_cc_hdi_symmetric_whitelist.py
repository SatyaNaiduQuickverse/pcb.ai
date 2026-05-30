#!/usr/bin/env python3
"""test_cc_hdi_symmetric_whitelist.py — regression tests for lever CC.

Verifies:
  (a) route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS includes original
      J18/J19 + destination refs (R76, D37, D38, R50, TP22).
  (b) audit_hdi_via_in_pad.HDI_VIA_IN_PAD_WHITELIST mirrors the SoT
      (no drift).
  (c) BOTTOM_MICROVIA_REFS is a subset of HDI_VIA_IN_PAD_REFS (every
      destination has F-side via-in-pad too).
  (d) audit_hdi_symmetric_whitelist gate PASSES on the synchronized
      whitelists.
  (e) Synthetic drift (mismatched whitelist) → audit FAILS.
"""
from __future__ import annotations
import os
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


class WhitelistConsistencyTests(unittest.TestCase):

    def test_router_includes_original_and_destinations(self):
        import route_subsystem_cooperative as RC
        # Originals
        for ref in ("J18", "J19"):
            self.assertIn(ref, RC.HDI_VIA_IN_PAD_REFS,
                          f"{ref} missing from HDI_VIA_IN_PAD_REFS")
        # CC additions (chain destinations)
        for ref in ("TP22", "R50", "R76", "D37", "D38"):
            self.assertIn(ref, RC.HDI_VIA_IN_PAD_REFS,
                          f"{ref} missing — CC symmetric whitelist incomplete")

    def test_audit_mirrors_router(self):
        import route_subsystem_cooperative as RC
        import audit_hdi_via_in_pad as AUD
        self.assertEqual(set(RC.HDI_VIA_IN_PAD_REFS),
                          set(AUD.HDI_VIA_IN_PAD_WHITELIST),
                          "SoT drift: router and audit whitelists differ")

    def test_bottom_microvia_subset_of_hdi(self):
        """Every BOTTOM_MICROVIA destination must also have F-side HDI
        whitelisting (symmetric)."""
        import audit_hdi_via_in_pad as AUD
        bm = set(AUD.BOTTOM_MICROVIA_REFS)
        hdi = set(AUD.HDI_VIA_IN_PAD_WHITELIST)
        missing = bm - hdi
        self.assertEqual(missing, set(),
                          f"BOTTOM_MICROVIA destinations {missing} "
                          f"missing F-side HDI whitelist")


class AuditGateTests(unittest.TestCase):

    def test_audit_passes_on_clean_state(self):
        r = subprocess.run(
            [sys.executable,
             os.path.join(_HERE, "audit_hdi_symmetric_whitelist.py")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                          f"audit FAILED unexpectedly: {r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)

    def test_audit_detects_synthetic_drift(self):
        """Patch the router module in-memory to drop a destination; audit
        should detect the SoT drift."""
        import importlib
        import route_subsystem_cooperative as RC
        import audit_hdi_via_in_pad as AUD
        original = RC.HDI_VIA_IN_PAD_REFS
        try:
            # Drop R76 from router; audit retains it → SoT drift
            RC.HDI_VIA_IN_PAD_REFS = tuple(r for r in original if r != "R76")
            importlib.reload(AUD)  # reload to make sure modules sync
            import audit_hdi_symmetric_whitelist as AS
            code, failures = AS.audit(board_path=None)
            self.assertEqual(code, 1,
                              f"audit should detect drift: {failures}")
            self.assertTrue(any("drift" in f.lower() for f in failures))
        finally:
            RC.HDI_VIA_IN_PAD_REFS = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
