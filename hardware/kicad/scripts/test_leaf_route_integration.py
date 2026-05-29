#!/usr/bin/env python3
"""test_leaf_route_integration.py — CH1 30/30 lever Q integration test.

This test exercises the LEAF-ROUTE pass without needing a fully-loaded
pcbnew board. It builds MOCK objects for the small surface lever-Q
touches (verify_net_connectivity, commit_net, rip_net, _rebuild_grid,
state.net_pads, committed, grid, board) so the FULL cascade —
mechanism-a maze → mechanism-b multi-mech → shorts-gate → rollback —
is exercised end-to-end.

Per the lever-Q dispatch task validation:
  - Synthetic case: 4-pad net, 3-pad trunk, 1 leaf disconnected. Run
    targeted leaf-route. Confirm:
    (a) finds the disconnected leaf
    (b) attempts maze then multi-mech
    (c) on success commits cleanly
    (d) on failure logs honest verdict
  - Adversarial: "always-route" liar ignoring shorts-gate -> refused
    (rollback path triggered).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import route_subsystem_cooperative as RSC


# ─── Mock objects ─────────────────────────────────────────────────────────

class _MockBoard:
    """Bare-minimum board surface — we only need .GetTracks() / .GetNetsByName()
    for the parts of the leaf-route path that don't go through pcbnew."""
    def __init__(self):
        self.tracks = []

    def GetTracks(self):
        return list(self.tracks)


class _MockState:
    """Mirrors BoardState.net_pads structure: dict[netname -> list of
    (ref, padname, x, y, layers, sx, sy)] tuples."""
    def __init__(self, net_pads):
        self.net_pads = net_pads
        self.net_obj = {}


class _MockGrid:
    """Mirrors only the .xy_to_ij + .in_bounds + .pitch surface; cells are
    indexed by (i, j, layer) but for these tests we just emit deterministic
    integers."""
    def __init__(self, pitch=0.1):
        self.pitch = pitch

    def xy_to_ij(self, x, y):
        return (int(round(x * 10)), int(round(y * 10)))

    def in_bounds(self, i, j):
        return -10000 < i < 10000 and -10000 < j < 10000

    def allow_pad_access_rect(self, *a, **kw):
        pass


class _MockRouter:
    """Mock CooperativeRouter — just enough surface for lever-Q to do its
    work. We hardcode the responses verify_net_connectivity gives so each
    test can dial in its scenario (trunk islands, all-1-island, etc.).
    """
    F_CU = RSC.F_CU
    IN8_CU = RSC.IN8_CU

    def __init__(self, net_pads, connectivity_response, scenario_name=""):
        self.board = _MockBoard()
        self.subsystem = "CH1"
        self.state = _MockState(net_pads)
        self.grid = _MockGrid()
        self.zone = (0.0, 0.0, 100.0, 100.0)
        self.committed = {}
        self.via_in_pad_allowed = True
        self.leaf_route_enabled = True
        self._connectivity = connectivity_response
        self._commit_calls = []
        self._rip_calls = []
        self._rebuild_calls = 0
        self._scenario_name = scenario_name
        # Shorts pre/post — caller can override per-test
        self._shorts_sequence = [0, 0]  # [pre, post]; index advances per call
        self._shorts_idx = 0
        # Maze + multi-mech responses — caller can override per-test
        self._maze_returns_path = False
        self._multi_mech_returns_routed = False
        # Track find_path_astar calls
        self._maze_calls = []
        self._multi_mech_calls = []

    def verify_net_connectivity(self, netname):
        return self._connectivity.get(netname, (1, []))

    def commit_net(self, netname, paths, append=False):
        self._commit_calls.append((netname, len(paths), append))
        # Add a phantom track so _MockBoard.GetTracks() shows new geometry
        self.committed.setdefault(netname, (set(), []))

    def rip_net(self, netname):
        self._rip_calls.append(netname)
        if netname in self.committed:
            del self.committed[netname]

    def _rebuild_grid(self):
        self._rebuild_calls += 1

    def _pad_cells_for_net(self, netname):
        out = []
        for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
            cells = {(int(x * 10), int(y * 10), self.F_CU)}
            out.append((ref, padname, x, y, cells, list(layers), sx, sy))
        return out

    def _try_multi_mech_fallback(self, netname):
        self._multi_mech_calls.append(netname)
        return self._multi_mech_returns_routed

    def log(self, msg):
        # Quiet in tests — uncomment to debug
        # print(msg)
        pass


def _mock_count_shorts(router):
    """Mock shorts counter that increments per call along _shorts_sequence."""
    idx = router._shorts_idx
    if idx < len(router._shorts_sequence):
        val = router._shorts_sequence[idx]
    else:
        val = router._shorts_sequence[-1]
    router._shorts_idx += 1
    return val


def _patched_find_path_astar_factory(router, returns_path):
    """Build a stub for find_path_astar that records calls + returns
    success/failure deterministically."""
    def stub(grid, sources, targets, netname, allowed, present_factor,
             move_set=None, time_budget_s=5.0):
        router._maze_calls.append({
            "netname": netname,
            "n_sources": len(sources),
            "n_targets": len(targets),
            "allowed_layers_count": len(allowed),
            "present_factor": present_factor,
        })
        if returns_path:
            # Return a 2-cell path
            path = list(sources)[:1] + list(targets)[:1]
            return path, 0.5
        return None, None
    return stub


# ─── Tests ────────────────────────────────────────────────────────────────

class LeafRouteIntegration(unittest.TestCase):

    NET = "KILL_RAIL_N_CH1"
    PADS = [
        # ref, padname, x, y, layers, sx, sy
        ("J19", "8", 50.0, 50.0, (RSC.F_CU,), 0.3, 0.3),
        ("D38", "2", 52.0, 50.0, (RSC.F_CU,), 0.5, 0.5),
        ("D37", "2", 54.0, 50.0, (RSC.F_CU,), 0.5, 0.5),
        ("R76", "1", 56.0, 50.0, (RSC.F_CU,), 0.4, 0.4),
    ]
    CONNECTIVITY = {
        # 3-pad trunk (J19.8, D38.2, D37.2) + 1 disconnected leaf (R76.1)
        NET: (2, [["J19.8", "D38.2", "D37.2"], ["R76.1"]]),
    }

    def _save_tr_count_shorts(self):
        self._saved_tr_count_shorts = RSC._tr_count_shorts

    def _restore_tr_count_shorts(self):
        RSC._tr_count_shorts = self._saved_tr_count_shorts

    def _save_find_path_astar(self):
        self._saved_find_path_astar = RSC.find_path_astar

    def _restore_find_path_astar(self):
        RSC.find_path_astar = self._saved_find_path_astar

    def setUp(self):
        self._save_tr_count_shorts()
        self._save_find_path_astar()

    def tearDown(self):
        self._restore_tr_count_shorts()
        self._restore_find_path_astar()

    # ────────────────────────────────────────────────────────────────
    # Task validation step 2(a): finds the disconnected leaf
    # ────────────────────────────────────────────────────────────────

    def test_2a_identify_leaves(self):
        """Verify _lq_identify_leaves correctly partitions trunk + leaves."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="2a")
        trunk, leaves = RSC._lq_identify_leaves(router, self.NET)
        self.assertEqual(set(trunk), {"J19.8", "D38.2", "D37.2"})
        self.assertEqual(leaves, ["R76.1"])

    def test_2a_no_leaves_when_single_island(self):
        """Vacuous: 1-island net returns (None, None)."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response={self.NET:
                (1, [["J19.8", "D38.2", "D37.2", "R76.1"]])},
            scenario_name="2a-vacuous")
        trunk, leaves = RSC._lq_identify_leaves(router, self.NET)
        self.assertIsNone(trunk)
        self.assertIsNone(leaves)

    # ────────────────────────────────────────────────────────────────
    # Task validation step 2(b): cascades maze → multi-mech on failure
    # ────────────────────────────────────────────────────────────────

    def test_2b_cascade_maze_then_multi_mech(self):
        """When maze returns NO_PATH, multi-mech must be tried as attempt #2."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="2b")
        router._shorts_sequence = [0, 0, 0, 0]   # no shorts changes
        # Patch shorts + maze
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        # Maze fails, multi-mech also fails — honest verdict path
        RSC.find_path_astar = _patched_find_path_astar_factory(router, False)
        router._multi_mech_returns_routed = False

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        self.assertEqual(len(router._maze_calls), 1,
                         f"Maze must be attempt #1; got {len(router._maze_calls)}")
        self.assertEqual(len(router._multi_mech_calls), 1,
                         f"Multi-mech must be attempt #2; got {len(router._multi_mech_calls)}")
        self.assertEqual(entry.cascade_attempts, 2,
                         "cascade_attempts must record both attempts")
        self.assertLessEqual(entry.cascade_attempts, RSC.LEAF_ROUTE_ATTEMPT_CAP,
                             "cascade ≤ LEAF_ROUTE_ATTEMPT_CAP=2 invariant")

    # ────────────────────────────────────────────────────────────────
    # Task validation step 2(c): success commits cleanly
    # ────────────────────────────────────────────────────────────────

    def test_2c_maze_success_commits_clean(self):
        """Maze returns a path + shorts_delta ≤ 0 → commit + ROUTED."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="2c-maze-clean")
        router._shorts_sequence = [5, 5]  # pre=5, post=5 → delta=0 → commit
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        RSC.find_path_astar = _patched_find_path_astar_factory(router, True)

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        self.assertEqual(entry.cascade_attempts, 1, "Maze success = attempt #1 only")
        self.assertTrue(entry.committed, "Clean shorts-delta must commit")
        self.assertEqual(entry.final_outcome, "ROUTED")
        self.assertEqual(len(router._commit_calls), 1,
                         "Exactly one commit_net call expected")
        # multi-mech must NOT be invoked on maze success
        self.assertEqual(len(router._multi_mech_calls), 0)

    def test_2c_multi_mech_success_commits_clean(self):
        """Maze fails, multi-mech returns routed, shorts clean → commit."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="2c-mm-clean")
        router._shorts_sequence = [3, 3]
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        RSC.find_path_astar = _patched_find_path_astar_factory(router, False)
        router._multi_mech_returns_routed = True

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        self.assertEqual(entry.cascade_attempts, 2)
        self.assertTrue(entry.committed)
        self.assertEqual(entry.final_outcome, "ROUTED")

    # ────────────────────────────────────────────────────────────────
    # Task validation step 2(d): failure logs honest verdict
    # ────────────────────────────────────────────────────────────────

    def test_2d_both_fail_honest_verdict(self):
        """Maze NO_PATH + multi-mech NO_PATH → final_outcome=NO_PATH, no commit."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="2d-both-fail")
        router._shorts_sequence = [7, 7]
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        RSC.find_path_astar = _patched_find_path_astar_factory(router, False)
        router._multi_mech_returns_routed = False

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        self.assertFalse(entry.committed, "Must NOT fabricate a commit on dual failure")
        self.assertEqual(entry.final_outcome, "NO_PATH")
        self.assertEqual(entry.cascade_attempts, 2)
        self.assertEqual(len(entry.attempts), 2,
                         "Both attempts must be recorded for provenance")
        # Each attempt must declare its mechanism + outcome + reason
        for att in entry.attempts:
            self.assertIn(att["mechanism"], {"maze", "multi_mech"})
            self.assertEqual(att["outcome"], "NO_PATH")
            self.assertTrue(att["reason"])

    # ────────────────────────────────────────────────────────────────
    # Task validation step 3: ADVERSARIAL always-route liar
    # ────────────────────────────────────────────────────────────────

    def test_3_adversarial_maze_shorts_positive_rolled_back(self):
        """Maze returns a path but commits cause shorts (3→18, delta=+15).
        The shorts-gate MUST reject the attempt (rollback + SHORTS_GATE_REJECT).
        A liar that ignored this gate would commit anyway — our code MUST NOT.
        """
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="3-adversarial-maze-shorts")
        router._shorts_sequence = [3, 18]  # pre=3, post=18, delta=+15
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        RSC.find_path_astar = _patched_find_path_astar_factory(router, True)

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        # Shorts-gate must reject + rollback
        self.assertFalse(entry.committed,
                         "Shorts delta +15 MUST trigger rollback (no commit)")
        self.assertEqual(entry.final_outcome, "SHORTS_GATE_REJECT")
        self.assertGreater(entry.shorts_post, entry.shorts_pre,
                           "Provenance MUST record the positive delta honestly")
        # rip_net + _rebuild_grid must have fired
        self.assertGreaterEqual(len(router._rip_calls), 1,
                                "Rollback must have called rip_net")
        self.assertGreaterEqual(router._rebuild_calls, 1)

    def test_3_adversarial_multi_mech_shorts_positive_rolled_back(self):
        """Same as above but the shorts increment happens on the multi-mech
        attempt (after a maze NO_PATH)."""
        router = _MockRouter(
            net_pads={self.NET: self.PADS},
            connectivity_response=self.CONNECTIVITY,
            scenario_name="3-adversarial-mm-shorts")
        # First shorts call = pre at very start (3)
        # Second shorts call = post-multi-mech (12 = delta +9)
        router._shorts_sequence = [3, 12]
        RSC._tr_count_shorts = lambda b: _mock_count_shorts(router)
        RSC.find_path_astar = _patched_find_path_astar_factory(router, False)
        router._multi_mech_returns_routed = True

        entry = RSC._lq_attempt_leaf_route(
            router, self.NET, "R76.1",
            trunk_pads=["J19.8", "D38.2", "D37.2"])

        self.assertFalse(entry.committed)
        self.assertEqual(entry.final_outcome, "SHORTS_GATE_REJECT")

    # ────────────────────────────────────────────────────────────────
    # Task validation step 5: audit_meta + audit_meta_coverage green
    # ────────────────────────────────────────────────────────────────

    def test_5_audit_meta_coverage_includes_g_q1(self):
        """G_Q1 audit must be wired in master_pre_merge.sh."""
        pm_text = (Path(SCRIPTS) / "master_pre_merge.sh").read_text()
        self.assertIn("audit_leaf_route_provenance.py", pm_text,
                      "G_Q1 audit must be wired into master_pre_merge.sh")
        self.assertIn("G_Q1_leaf_route_provenance", pm_text)


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(LeafRouteIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        n = result.testsRun
        print(f"\n✅ Integration tests: {n}/{n} PASSED")
        return 0
    print(f"\n❌ FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
