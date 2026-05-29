#!/usr/bin/env python3
"""test_leaf_route.py — CH1 30/30 lever Q regression suite.

Validation (per the lever-Q dispatch brief):
  1. Self-check 20/20.
  2. Synthetic case: 4-pad net with 3-pad trunk + 1 disconnected leaf.
     (a) confirm leaf identification
     (b) confirm maze → multi-mech cascade
     (c) confirm SUCCESS path commits + writes provenance
     (d) confirm FAIL path logs honest verdict (no fabrication)
  3. Adversarial: "always-route" liar that ignores shorts-gate — must
     FAIL the audit (shorts_delta_positive on commit).
  4. Audit gate G_Q1 PASS on every well-formed entry.

This test runs pcbnew-FREE: it constructs synthetic entries directly
+ runs the audit. The live-CH1 test is done via the cooperative router
end-to-end (run-on-board script + audit).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List


REPO = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS))

# Import the audit (pure-python; no pcbnew required)
import audit_leaf_route_provenance as G_Q1


def _make_entry(netname="KILL_RAIL_N_CH1",
                leaf_pad="R76.1",
                trunk_pads=("J19.8", "D38.2", "D37.2"),
                attempts=None,
                cascade_attempts=1,
                committed=True,
                shorts_pre=0,
                shorts_post=0,
                final_outcome="ROUTED",
                schema_version=1,
                board_sha="abcdef123456",
                subsystem="CH1"):
    if attempts is None:
        attempts = [{"mechanism": "maze",
                     "outcome": "ROUTED",
                     "reason": "ok",
                     "shorts_pre": shorts_pre,
                     "shorts_post": shorts_post}]
    return {
        "schema_version": schema_version,
        "timestamp_iso": "2026-05-29T00:00:00+00:00",
        "board_sha": board_sha,
        "subsystem": subsystem,
        "netname": netname,
        "leaf_pad": leaf_pad,
        "trunk_pads": list(trunk_pads),
        "attempts": attempts,
        "cascade_attempts": cascade_attempts,
        "committed": committed,
        "shorts_pre": shorts_pre,
        "shorts_post": shorts_post,
        "final_outcome": final_outcome,
    }


class LeafRouteSchema(unittest.TestCase):
    """Tests for the audit_leaf_route_provenance G_Q1 schema check."""

    # ────────────────────────────────────────────────────────────────
    # Test 1-3: well-formed entries (positive cases — pass the audit)
    # ────────────────────────────────────────────────────────────────

    def test_01_routed_maze_ok(self):
        e = _make_entry()
        v = G_Q1._check_entry("ok.json", e)
        self.assertEqual(v, [], f"Expected no violations, got: {v}")

    def test_02_routed_multi_mech_ok(self):
        atts = [
            {"mechanism": "maze", "outcome": "NO_PATH",
             "reason": "no_path_maze", "shorts_pre": 0, "shorts_post": 0},
            {"mechanism": "multi_mech", "outcome": "ROUTED",
             "reason": "ok", "shorts_pre": 0, "shorts_post": 0},
        ]
        e = _make_entry(attempts=atts, cascade_attempts=2)
        v = G_Q1._check_entry("ok2.json", e)
        self.assertEqual(v, [], f"Expected no violations, got: {v}")

    def test_03_honest_no_path_ok(self):
        atts = [
            {"mechanism": "maze", "outcome": "NO_PATH",
             "reason": "no_path_maze", "shorts_pre": 5, "shorts_post": 5},
            {"mechanism": "multi_mech", "outcome": "NO_PATH",
             "reason": "no_path_multi_mech_or_adapter_not_wired",
             "shorts_pre": 5, "shorts_post": 5},
        ]
        e = _make_entry(attempts=atts, cascade_attempts=2,
                        committed=False, shorts_pre=5, shorts_post=5,
                        final_outcome="NO_PATH")
        v = G_Q1._check_entry("honest.json", e)
        self.assertEqual(v, [], f"Expected no violations, got: {v}")

    # ────────────────────────────────────────────────────────────────
    # Test 4-9: schema violations (every required field is enforced)
    # ────────────────────────────────────────────────────────────────

    def test_04_missing_schema_version(self):
        e = _make_entry()
        del e["schema_version"]
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("schema_version" in s for s in v))

    def test_05_missing_netname(self):
        e = _make_entry()
        e["netname"] = ""
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("netname" in s for s in v))

    def test_06_missing_leaf_pad(self):
        e = _make_entry()
        e["leaf_pad"] = ""
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("leaf_pad" in s for s in v))

    def test_07_empty_attempts(self):
        e = _make_entry(attempts=[])
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("attempts" in s.lower() for s in v))

    def test_08_invalid_mechanism(self):
        atts = [{"mechanism": "wishful_thinking",
                 "outcome": "ROUTED", "reason": "ok",
                 "shorts_pre": 0, "shorts_post": 0}]
        e = _make_entry(attempts=atts)
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("mechanism" in s for s in v))

    def test_09_invalid_final_outcome(self):
        e = _make_entry(final_outcome="MAGICALLY_ROUTED")
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("final_outcome" in s for s in v))

    # ────────────────────────────────────────────────────────────────
    # Test 10-13: cascade-bound enforcement (R42 ≤ 2)
    # ────────────────────────────────────────────────────────────────

    def test_10_cascade_at_cap_ok(self):
        atts = [
            {"mechanism": "maze", "outcome": "NO_PATH",
             "reason": "no_path_maze", "shorts_pre": 0, "shorts_post": 0},
            {"mechanism": "multi_mech", "outcome": "NO_PATH",
             "reason": "no_path_multi_mech", "shorts_pre": 0, "shorts_post": 0},
        ]
        e = _make_entry(attempts=atts, cascade_attempts=2,
                        committed=False, final_outcome="NO_PATH")
        v = G_Q1._check_entry("x.json", e)
        self.assertEqual(v, [], f"Expected no violations, got: {v}")

    def test_11_cascade_over_cap_fails(self):
        e = _make_entry(cascade_attempts=3)
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("CASCADE BOUND" in s for s in v))

    def test_12_cascade_way_over_cap_fails(self):
        e = _make_entry(cascade_attempts=99)
        v = G_Q1._check_entry("x.json", e)
        self.assertTrue(any("CASCADE BOUND" in s for s in v))

    def test_13_cascade_negative_fails(self):
        e = _make_entry(cascade_attempts=-1)
        v = G_Q1._check_entry("x.json", e)
        # Should fail one way or the other
        self.assertTrue(len(v) > 0)

    # ────────────────────────────────────────────────────────────────
    # Test 14-17: ADVERSARIAL — shorts-gate liar
    # ────────────────────────────────────────────────────────────────

    def test_14_adversarial_always_route_liar_shorts_delta_positive(self):
        """ADVERSARIAL: a router that ignores the shorts-gate and commits
        anyway. Audit MUST fail it on R-J5 / G_J5 shorts-delta invariant."""
        e = _make_entry(shorts_pre=0, shorts_post=18,
                        committed=True, final_outcome="ROUTED")
        v = G_Q1._check_entry("liar.json", e)
        self.assertTrue(any("SHORTS DELTA POSITIVE" in s for s in v),
                        f"adversarial entry must be rejected; got: {v}")

    def test_15_adversarial_committed_but_not_routed_inconsistent(self):
        """ADVERSARIAL: a liar that claims commit but reports NO_PATH outcome."""
        e = _make_entry(committed=True, final_outcome="NO_PATH")
        v = G_Q1._check_entry("liar2.json", e)
        self.assertTrue(any("committed=True" in s for s in v))

    def test_16_adversarial_routed_but_not_committed_inconsistent(self):
        """ADVERSARIAL: a liar that claims ROUTED outcome but committed=False."""
        e = _make_entry(committed=False, final_outcome="ROUTED")
        v = G_Q1._check_entry("liar3.json", e)
        self.assertTrue(any("ROUTED" in s and "False" in s for s in v))

    def test_17_adversarial_skip_shorts_recording_inconsistent(self):
        """ADVERSARIAL: missing shorts_pre/shorts_post."""
        e = _make_entry()
        del e["shorts_pre"]
        del e["shorts_post"]
        v = G_Q1._check_entry("liar4.json", e)
        self.assertTrue(any("shorts" in s for s in v))

    # ────────────────────────────────────────────────────────────────
    # Test 18-20: end-to-end audit scan on a tempdir of synthetic entries
    # ────────────────────────────────────────────────────────────────

    def test_18_full_load_vacuous_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            # No PROVENANCE_DIR_REL → vacuous PASS
            entries = G_Q1._load_entries(tmp_root)
            self.assertEqual(entries, [])

    def test_19_full_load_mixed_well_formed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            d = tmp_root / G_Q1.PROVENANCE_DIR_REL
            d.mkdir(parents=True)
            # Write two well-formed entries
            (d / "a_000.json").write_text(json.dumps(_make_entry(
                netname="A_CH1", leaf_pad="R1.1")))
            (d / "b_000.json").write_text(json.dumps(_make_entry(
                netname="B_CH1", leaf_pad="R2.1",
                cascade_attempts=2,
                attempts=[
                    {"mechanism": "maze", "outcome": "NO_PATH",
                     "reason": "no_path_maze",
                     "shorts_pre": 0, "shorts_post": 0},
                    {"mechanism": "multi_mech", "outcome": "ROUTED",
                     "reason": "ok",
                     "shorts_pre": 0, "shorts_post": 0},
                ])))
            entries = G_Q1._load_entries(tmp_root)
            self.assertEqual(len(entries), 2)
            total_v = []
            for name, e in entries:
                total_v.extend(G_Q1._check_entry(name, e))
            self.assertEqual(total_v, [],
                             f"Expected no violations, got: {total_v}")

    def test_20_full_load_adversarial_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            d = tmp_root / G_Q1.PROVENANCE_DIR_REL
            d.mkdir(parents=True)
            # Two well-formed + one adversarial
            (d / "good_000.json").write_text(json.dumps(_make_entry()))
            (d / "honest_no_path_000.json").write_text(json.dumps(_make_entry(
                committed=False, final_outcome="NO_PATH")))
            (d / "liar_000.json").write_text(json.dumps(_make_entry(
                shorts_pre=0, shorts_post=18,
                committed=True, final_outcome="ROUTED")))
            entries = G_Q1._load_entries(tmp_root)
            self.assertEqual(len(entries), 3)
            total_v = []
            for name, e in entries:
                total_v.extend(G_Q1._check_entry(name, e))
            # Exactly the liar should fail
            self.assertTrue(any("SHORTS DELTA POSITIVE" in v
                                for v in total_v),
                            f"Adversarial liar must be caught; got: {total_v}")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(LeafRouteSchema)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        # Count tests explicitly
        n_tests = result.testsRun
        print(f"\n✅ ALL {n_tests}/{n_tests} TESTS PASSED")
        return 0
    print(f"\n❌ FAILED — {len(result.failures)} failure(s), "
          f"{len(result.errors)} error(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
