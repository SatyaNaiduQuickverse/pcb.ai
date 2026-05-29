#!/usr/bin/env python3
"""test_ee_k3_chain_emit_fix.py — regression tests for lever EE.

Verifies the K3 chain emit pad-level exclude semantics:
  (a) `_board_obstacles_from_pcbnew(exclude_pads=...)` skips ONLY the named
      (ref, pad) pairs; sibling pads of the same footprint REMAIN as
      obstacles.
  (b) Legacy `exclude_refs=...` still skips whole footprints (back-compat).
  (c) Combined: exclude_refs + exclude_pads both honored.
  (d) The audit gate detects a fine-pitch through-via collision.
"""
from __future__ import annotations
import os
import sys
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
class ExcludePadsObstacleTests(unittest.TestCase):
    """Lever EE: _board_obstacles_from_pcbnew honors per-pad exclusion."""

    def _build_test_board(self):
        """Build a minimal board with a multi-pad footprint."""
        import pcbnew
        board = pcbnew.BOARD()
        # Add 3 footprints, each with 4 pads, to simulate fine-pitch QFN
        for i, ref in enumerate(["J19", "J18", "U1"]):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I(int(20e6 + i * 10e6), int(20e6)))
            for j in range(4):
                pad = pcbnew.PAD(fp)
                pad.SetNumber(str(j + 1))
                # 0.5mm pitch along Y
                pad.SetPosition(pcbnew.VECTOR2I(
                    int((20 + i * 10) * 1e6),
                    int((20 + j * 0.5) * 1e6)))
                pad.SetSize(pcbnew.VECTOR2I(int(0.25e6), int(0.6e6)))
                fp.Add(pad)
            board.Add(fp)
        return board

    def test_exclude_pads_skips_only_named(self):
        """Only J19.1 + J18.15 are excluded; sibling pads remain obstacles."""
        from routing_engine.phase_c import _board_obstacles_from_pcbnew
        from routing_engine import maze_router as MR

        board = self._build_test_board()
        # Region covers everything
        region = type("R", (), {"bbox": (0, 0, 100, 100),
                                  "allowed_layers": ("F.Cu", "B.Cu")})()
        obstacles = _board_obstacles_from_pcbnew(
            board, region,
            exclude_pads=(("J19", "1"), ("J18", "15")),
            mode="per_pad_and_tracks")
        # Expect: 3 footprints * 4 pads = 12, minus only 2 excluded
        # (J18.15 doesn't exist in our test board; J19.1 is excluded).
        # Sibling J19.2, J19.3, J19.4 + all J18 + all U1 = 11 obstacles.
        body_obs = [o for o in obstacles if o.kind == "body"]
        # Number of body obstacles equals total pads minus matching excludes
        # (J19.1 excluded). 4+4+4 = 12 pads, -1 excluded = 11.
        self.assertEqual(len(body_obs), 11,
                          f"got {len(body_obs)} body obstacles; "
                          f"expected 11 (12 pads - 1 excluded J19.1)")

    def test_exclude_refs_still_works(self):
        """exclude_refs=('J19',) skips all J19 pads."""
        from routing_engine.phase_c import _board_obstacles_from_pcbnew
        board = self._build_test_board()
        region = type("R", (), {"bbox": (0, 0, 100, 100),
                                  "allowed_layers": ("F.Cu", "B.Cu")})()
        obstacles = _board_obstacles_from_pcbnew(
            board, region,
            exclude_refs=("J19",),
            mode="per_pad_and_tracks")
        body_obs = [o for o in obstacles if o.kind == "body"]
        # 4+4 = 8 (J18 + U1, J19 all excluded)
        self.assertEqual(len(body_obs), 8)

    def test_exclude_refs_and_pads_both(self):
        """exclude_refs={J19} + exclude_pads={(J18,2)} → J19 all + J18.2 skip."""
        from routing_engine.phase_c import _board_obstacles_from_pcbnew
        board = self._build_test_board()
        region = type("R", (), {"bbox": (0, 0, 100, 100),
                                  "allowed_layers": ("F.Cu", "B.Cu")})()
        obstacles = _board_obstacles_from_pcbnew(
            board, region,
            exclude_refs=("J19",),
            exclude_pads=(("J18", "2"),),
            mode="per_pad_and_tracks")
        body_obs = [o for o in obstacles if o.kind == "body"]
        # 4 + 4 - 1 = 7
        self.assertEqual(len(body_obs), 7)


@unittest.skipUnless(_have_pcbnew(), "pcbnew required")
class AuditGateCollisionDetectionTests(unittest.TestCase):
    """The audit gate detects a fine-pitch via-vs-foreign-pad collision."""

    def test_detects_through_via_at_neighbor_pin(self):
        """Plant a through-via at J19.2's location; audit should FAIL."""
        import pcbnew
        import tempfile
        import audit_k3_chain_pitch_collision as AUD

        board = pcbnew.BOARD()
        # J19 footprint with 4 pads at 0.5mm pitch
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("J19")
        fp.SetPosition(pcbnew.VECTOR2I(int(20e6), int(20e6)))
        for j in range(4):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(j + 1))
            pad.SetPosition(pcbnew.VECTOR2I(int(20e6), int((20 + j * 0.5) * 1e6)))
            pad.SetSize(pcbnew.VECTOR2I(int(0.25e6), int(0.6e6)))
            fp.Add(pad)
        board.Add(fp)
        # Add a through-via AT J19.2's exact location (different/no net).
        # The audit treats unnamed/different net as "foreign" → collision
        # detected.
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(int(20e6), int(20.5e6)))   # J19.2 spot
        via.SetWidth(int(0.60e6))
        via.SetDrill(int(0.30e6))
        try:
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
        except Exception:
            pass
        board.Add(via)

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
            pcbnew.SaveBoard(tf.name, board)
            try:
                code, issues = AUD.audit(tf.name, ("J19",), 0.10)
                self.assertEqual(code, 1, f"audit should FAIL: {issues}")
                # Audit detects collision against the nearest J19 sibling
                # pad — could be J19.1 (above) or J19.2 (at via center)
                # depending on iteration order. Just verify a J19 collision
                # was reported.
                self.assertTrue(any("J19" in s for s in issues),
                                f"issue should name a J19 pad: {issues}")
            finally:
                os.unlink(tf.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
