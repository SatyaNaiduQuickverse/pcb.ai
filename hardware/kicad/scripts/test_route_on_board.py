#!/usr/bin/env python3
"""test_route_on_board.py — focused tests for routing_engine/route_on_board.py
the maze-router live-board harness (Phase 3 lever B).

Two layers of tests:
  1. Pure-python tests (no pcbnew) — config + helpers + region clamping +
     star-from-root MST + layer-name canonicalisation. Run from any env.
  2. pcbnew emission test — emit a HAND-CRAFTED Route to a real .kicad_pcb,
     save, reload, verify the pcbnew objects landed with the correct
     layer/width/drill/via-type/net attribution. Skipped when pcbnew is
     absent (master env).

These tests intentionally do NOT depend on a particular board's congestion
state — the maze's verdict on a real dense board is a separate physics
question. What we test here is that the *harness mechanics* are correct.
"""
from __future__ import annotations

import os
import sys
import unittest
import tempfile
import shutil

# canonical scripts dir on sys.path (mirrors run_suite.py pattern)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "routing_engine"))

from routing_engine.route_on_board import (   # noqa: E402
    VIA_GEOM_MM, DEFAULT_NET_CONFIG, NET_CONFIG, SUBSYSTEM_ZONES,
    REGION_MARGIN_MM, PadInfo, _pad_to_pin, _pad_needs_stitch,
    _mst_pairs, _region_bbox, _hdi_whitelisted_ref,
)
from routing_engine.maze_router import (   # noqa: E402
    LAYER_STACK, VIA_CLASSES, Route, Segment, Via as MazeVia,
)


# ─── pure-python tests ───────────────────────────────────────────────────────
class ConfigTests(unittest.TestCase):
    def test_via_geom_table_consistent(self):
        for cls, (drill, pad) in VIA_GEOM_MM.items():
            self.assertGreater(pad, drill, f"{cls}: pad {pad} > drill {drill}")
            self.assertGreaterEqual(drill, 0.05, f"{cls}: drill {drill} >= 0.05")
            self.assertLessEqual(drill, 0.40, f"{cls}: drill {drill} <= 0.40")

    def test_oq020_blind_geom_matches_dru(self):
        # The DRU rule "HDI blind F-In2 via diameter (whitelist)" mandates
        # drill 0.15mm + pad 0.25mm (epoxy-fill + plate-over, 4-net whitelist).
        self.assertEqual(VIA_GEOM_MM["blind"], (0.15, 0.25))

    def test_all_configs_reference_known_layers_and_classes(self):
        all_cfgs = [DEFAULT_NET_CONFIG] + list(NET_CONFIG.values())
        for cfg in all_cfgs:
            for L in cfg["route_layers"]:
                self.assertIn(L, LAYER_STACK,
                              f"route_layer {L!r} not in canonical stack")
            for vc in cfg.get("via_classes", ()):
                self.assertIn(vc, VIA_CLASSES)
                self.assertIn(vc, VIA_GEOM_MM)
            sv = cfg.get("stitch_via_class")
            if sv:
                self.assertIn(sv, VIA_CLASSES)
                self.assertIn(sv, VIA_GEOM_MM)


class StarMSTTests(unittest.TestCase):
    def test_star_from_root_pairs(self):
        p_root = PadInfo("J19", "8", "KILL_RAIL_N_CH1", 23.45, 64.46,
                         ("F.Cu",), (23.32, 64.02, 23.57, 64.89))
        p1 = PadInfo("D37", "2", "KILL_RAIL_N_CH1", 30.7, 61.2, ("B.Cu",),
                     (30.5, 61.0, 30.9, 61.4))
        p2 = PadInfo("D38", "2", "KILL_RAIL_N_CH1", 32.2, 57.6, ("B.Cu",),
                     (32.0, 57.4, 32.4, 57.8))
        p3 = PadInfo("R76", "1", "KILL_RAIL_N_CH1", 35.26, 60.8, ("B.Cu",),
                     (35.1, 60.6, 35.4, 61.0))
        pairs = _mst_pairs(p_root, [p1, p2, p3])
        self.assertEqual(len(pairs), 3)
        for src, _ in pairs:
            self.assertIs(src, p_root, "every edge must start at root")
        # destinations preserved in caller order (deterministic)
        self.assertEqual([d.ref for _, d in pairs], ["D37", "D38", "R76"])

    def test_single_destination_makes_one_pair(self):
        a = PadInfo("J19", "10", "GLB_CH1", 24.45, 64.46, ("F.Cu",),
                    (24.32, 64.02, 24.57, 64.89))
        b = PadInfo("R50", "1", "GLB_CH1", 6.81, 75.04, ("B.Cu",),
                    (6.5, 74.9, 7.1, 75.2))
        self.assertEqual(len(_mst_pairs(a, [b])), 1)


class RegionBboxTests(unittest.TestCase):
    def setUp(self):
        self.zone = SUBSYSTEM_ZONES["CH1"]

    def test_clamps_to_zone(self):
        far = [PadInfo("X", "1", "DEMO", 1.0, 88.0, ("F.Cu",),
                       (0.5, 87.5, 1.5, 88.5))]
        r = _region_bbox(far, self.zone, REGION_MARGIN_MM)
        self.assertGreaterEqual(r[0], self.zone[0] - 1e-6)
        self.assertGreaterEqual(r[1], self.zone[1] - 1e-6)
        self.assertLessEqual(r[2], self.zone[2] + 1e-6)
        self.assertLessEqual(r[3], self.zone[3] + 1e-6)

    def test_contains_all_pads(self):
        pads = [PadInfo("J19", "10", "GLB_CH1", 24.45, 64.46, ("F.Cu",),
                        (24.32, 64.02, 24.57, 64.89)),
                PadInfo("R50", "1", "GLB_CH1", 6.81, 75.04, ("B.Cu",),
                        (6.5, 74.9, 7.1, 75.2))]
        r = _region_bbox(pads, self.zone, REGION_MARGIN_MM)
        for p in pads:
            self.assertLessEqual(r[0] - 1e-6, p.x_mm)
            self.assertGreaterEqual(r[2] + 1e-6, p.x_mm)

    def test_degenerate_widens_to_two_margins(self):
        one = [PadInfo("X", "1", "DEMO", 17.5, 70.0, ("F.Cu",),
                       (17.3, 69.8, 17.7, 70.2))]
        r = _region_bbox(one, self.zone, REGION_MARGIN_MM)
        self.assertGreaterEqual(r[2] - r[0], 2 * REGION_MARGIN_MM - 1e-6)
        self.assertGreaterEqual(r[3] - r[1], 2 * REGION_MARGIN_MM - 1e-6)


class HdiWhitelistTests(unittest.TestCase):
    def test_j18_j19_whitelisted(self):
        self.assertTrue(_hdi_whitelisted_ref("J18"))
        self.assertTrue(_hdi_whitelisted_ref("J19"))

    def test_other_refs_not_whitelisted(self):
        for ref in ("D29", "C60", "R50", "U1", "Q5", "J17", "J20"):
            self.assertFalse(_hdi_whitelisted_ref(ref))


class StitchDecisionTests(unittest.TestCase):
    def test_pad_on_primary_layer_no_stitch(self):
        p = PadInfo("J19", "10", "GLB_CH1", 24.45, 64.46, ("F.Cu",),
                    (24.32, 64.02, 24.57, 64.89))
        self.assertFalse(_pad_needs_stitch(p, "F.Cu"))

    def test_pad_on_other_layer_needs_stitch(self):
        p = PadInfo("R50", "1", "GLB_CH1", 6.81, 75.04, ("B.Cu",),
                    (6.5, 74.9, 7.1, 75.2))
        self.assertTrue(_pad_needs_stitch(p, "F.Cu"))

    def test_pin_layer_uses_primary(self):
        p = PadInfo("R50", "1", "GLB_CH1", 6.81, 75.04, ("B.Cu",),
                    (6.5, 74.9, 7.1, 75.2))
        pin = _pad_to_pin(p, "F.Cu")
        self.assertEqual(pin.layer, "F.Cu")
        self.assertFalse(pin.is_hdi_whitelisted)


# ─── pcbnew emission test (skipped if pcbnew absent) ─────────────────────────
def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_pcbnew(), "pcbnew not available in this environment")
class EmissionPathTests(unittest.TestCase):
    """Emit a hand-crafted Route to a real board; verify the pcbnew objects
    landed correctly. Uses the canonical board as a host (we attribute the
    test trace to an existing net + place it in EMPTY board-corner space so
    it doesn't perturb any real routing)."""

    CANONICAL = os.path.join(
        os.path.dirname(os.path.dirname(_HERE)), "kicad",
        "pcbai_fpv4in1.kicad_pcb")

    def setUp(self):
        import pcbnew
        if not os.path.exists(self.CANONICAL):
            self.skipTest(f"canonical board missing at {self.CANONICAL!r}")
        self.tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False)
        self.tmp.close()
        shutil.copyfile(self.CANONICAL, self.tmp.name)
        self.board = pcbnew.LoadBoard(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_emit_track_via_track(self):
        from routing_engine.route_on_board import emit_route_to_board
        import pcbnew

        ni = self.board.GetNetInfo().GetNetItem("SWDIO_CH1")
        self.assertIsNotNone(ni, "expected SWDIO_CH1 to exist on canonical")

        # Place the test trace at the board corner (x≈60-65, y≈5-10) where the
        # real routing doesn't go — pure emission-path check, not routing.
        rt = Route(segments=[
            Segment((60.0, 5.0), (65.0, 5.0), 0.20, "F.Cu"),
            Segment((65.0, 5.0), (65.0, 10.0), 0.20, "B.Cu"),
        ], vias=[
            MazeVia((65.0, 5.0), "through", "F.Cu", "B.Cu"),
        ])
        n_tr, n_via = emit_route_to_board(self.board, ni, [rt])
        self.assertEqual(n_tr, 2)
        self.assertEqual(n_via, 1)
        pcbnew.SaveBoard(self.tmp.name, self.board)

        # reload to make sure persistence + attribute round-trip work
        b2 = pcbnew.LoadBoard(self.tmp.name)
        found_tracks = found_vias = 0
        for t in b2.GetTracks():
            if t.GetNetname() != "SWDIO_CH1":
                continue
            s, e = t.GetStart(), t.GetEnd()
            if t.GetClass() == "PCB_VIA":
                if (abs(s.x / 1e6 - 65.0) < 0.01
                        and abs(s.y / 1e6 - 5.0) < 0.01):
                    found_vias += 1
                    self.assertEqual(t.GetViaType(),
                                     pcbnew.VIATYPE_THROUGH)
                    self.assertAlmostEqual(
                        t.GetDrillValue() / 1e6, 0.30, places=2)
            else:
                if 59 <= s.x / 1e6 <= 66 and 4 <= s.y / 1e6 <= 11:
                    found_tracks += 1
        self.assertEqual(found_tracks, 2, "expected 2 emitted tracks on reload")
        self.assertEqual(found_vias, 1, "expected 1 emitted via on reload")


if __name__ == "__main__":
    unittest.main(verbosity=2)
