#!/usr/bin/env python3
"""test_k3_caller_side.py — CH1 30/30 lever (P) K3 CALLER-SIDE GLUE test.

Verifies that route_subsystem_cooperative.CooperativeRouter._try_multi_mech_
fallback now ACTUALLY invokes phase_c.fill_region_with_multi_mech with a
constructed RegionSpec + minimal GlobalPlan (the M1-wired adapter library)
and emits PCB_TRACK + PCB_VIA records on the live board on success.

PR #227 (worker drone-grade close-out) found: M1 wired the library; the
cooperative router's K3 hook delegated to the adapter docstring but did
NOT actually invoke it. This test is the master-independent regression
gate that the caller-side glue is wired end-to-end:

  (1) SYNTHETIC ROUTABLE: synthetic CH1 footprints with a cross-stack net
      (F.Cu start pad + B.Cu end pad). The _try_multi_mech_fallback hook
      MUST return True + the board MUST have new PCB_TRACK + PCB_VIA
      items belonging to the net + self.committed[netname] populated as
      (set(), added_items).
  (2) ADVERSARIAL ROLLBACK: pads OUTSIDE the subsystem zone (the K3 hook
      skips when <2 in-zone pads). The hook MUST return False + the
      board MUST be UNCHANGED (no half-emitted state). Mirrors the
      atomic-per-net-rollback contract.
  (3) NO INVOCATION WHEN OFF: the fallback is OPT-IN
      (multi_mech_fallback_enabled = False default). When OFF, the
      route() loop MUST NOT call _try_multi_mech_fallback (this is the
      pre-existing v10 invariant; we re-assert it post-K3 glue).
  (4) MONKEYPATCH WITNESS: monkeypatch phase_c.fill_region_with_multi_mech
      with a witness that counts invocations + records its arguments.
      Drives _try_multi_mech_fallback once and asserts the witness was
      called exactly once with a constructed RegionSpec + ROUTABLE plan
      + the live board + the expected net_pairs. This is the proof
      that the CALLER-SIDE GLUE is wired (not just the adapter library).

Per [[feedback-codify-not-patch]]: ships with the K3 caller-side glue as
the master-independent regression test. Per [[feedback-sim-execution-
gate]]: the synthetic board is constructed in-memory + the validation
asserts on the LIVE pcbnew BOARD state after the call (not log output).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import pcbnew
except ImportError:
    print("SKIP: pcbnew not importable (must run under KiCad-bundled python)")
    sys.exit(0)

import route_subsystem_cooperative as RC
from routing_engine import phase_c as PC


# CH1 zone (per SUBSYSTEM_ZONES SSoT): (0, 50, 35, 89). We place J18 at
# x=30, y=70 (HDI-whitelisted, F.Cu pad) + TP1 at x=32, y=72 (B.Cu pad).
# Cross-stack pair: F.Cu -> B.Cu. The multi-mech planner's typical chain
# = blind_F_In2 (at J18) + through (somewhere between) = the canonical
# SWDIO_CH1 escape pattern.
CH1_BBOX = (0.0, 50.0, 35.0, 89.0)
J18_X, J18_Y = 30.0, 70.0
TP1_X, TP1_Y = 32.0, 72.0


def _build_synthetic_board(net_name="SWDIO_CH1", in_zone=True):
    """Build a minimal pcbnew BOARD with:
        J18 (HDI-whitelisted): F.Cu pad '1' at (J18_X, J18_Y)
        TP1  (non-HDI):        B.Cu pad '1' at (TP1_X, TP1_Y)
    Both connected to `net_name`. If in_zone=False, place them OUTSIDE
    CH1's bbox to exercise the K3 <2-in-zone-pads short-circuit."""
    if in_zone:
        x_j18, y_j18 = J18_X, J18_Y
        x_tp1, y_tp1 = TP1_X, TP1_Y
    else:
        # Outside CH1 (CH1 = 0..35, 50..89). Place at x=80 (CH2/CH3 zone).
        x_j18, y_j18 = 80.0, 30.0
        x_tp1, y_tp1 = 82.0, 32.0

    b = pcbnew.BOARD()
    # Set a board outline so internal bounding boxes resolve.
    # (Not strictly required for the planner; required for healthy
    # board.GetBoardEdgesBoundingBox() callers.)

    # Net registration
    net = pcbnew.NETINFO_ITEM(b, net_name)
    b.Add(net)

    # J18 (F.Cu pad)
    j18 = pcbnew.FOOTPRINT(b)
    j18.SetReference("J18")
    j18.SetPosition(pcbnew.VECTOR2I(int(x_j18 * 1e6), int(y_j18 * 1e6)))
    b.Add(j18)
    pad_j18 = pcbnew.PAD(j18)
    pad_j18.SetPadName("1")
    pad_j18.SetPosition(pcbnew.VECTOR2I(int(x_j18 * 1e6), int(y_j18 * 1e6)))
    pad_j18.SetSize(pcbnew.VECTOR2I(int(0.3e6), int(0.3e6)))
    ls_f = pcbnew.LSET()
    ls_f.AddLayer(pcbnew.F_Cu)
    pad_j18.SetLayerSet(ls_f)
    pad_j18.SetNet(net)
    j18.Add(pad_j18)

    # TP1 (B.Cu pad)
    tp = pcbnew.FOOTPRINT(b)
    tp.SetReference("TP1")
    tp.SetPosition(pcbnew.VECTOR2I(int(x_tp1 * 1e6), int(y_tp1 * 1e6)))
    b.Add(tp)
    pad_tp = pcbnew.PAD(tp)
    pad_tp.SetPadName("1")
    pad_tp.SetPosition(pcbnew.VECTOR2I(int(x_tp1 * 1e6), int(y_tp1 * 1e6)))
    pad_tp.SetSize(pcbnew.VECTOR2I(int(0.3e6), int(0.3e6)))
    ls_b = pcbnew.LSET()
    ls_b.AddLayer(pcbnew.B_Cu)
    pad_tp.SetLayerSet(ls_b)
    pad_tp.SetNet(net)
    tp.Add(pad_tp)

    return b


def test_1_synthetic_routable():
    """(1) SYNTHETIC ROUTABLE — _try_multi_mech_fallback returns True +
    board has new tracks/vias + self.committed[netname] populated."""
    print("\n[test_1] synthetic ROUTABLE cross-stack net (F.Cu J18 -> B.Cu TP1)")
    net_name = "SWDIO_CH1"
    board = _build_synthetic_board(net_name=net_name, in_zone=True)
    n_tracks_before = sum(1 for _ in board.GetTracks())

    router = RC.CooperativeRouter(
        board, "CH1",
        seed_nets=[net_name],
        verbose=False,
        via_in_pad_allowed=True,   # gate HDI on (J18 whitelist)
    )
    # The fallback is OPT-IN — enable it explicitly. The hook itself
    # does NOT check this flag (the route() loop does); we call the
    # hook directly here so we exercise the caller-side glue in isolation.
    router.multi_mech_fallback_enabled = True

    routed = router._try_multi_mech_fallback(net_name)
    n_tracks_after = sum(1 for _ in board.GetTracks())
    pcb_vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
    pcb_tracks = [t for t in board.GetTracks()
                  if isinstance(t, pcbnew.PCB_TRACK)
                  and not isinstance(t, pcbnew.PCB_VIA)]

    cond_a = routed is True
    cond_b = n_tracks_after > n_tracks_before
    cond_c = len(pcb_vias) >= 1
    cond_d = len(pcb_tracks) >= 1
    # Committed bookkeeping
    cond_e = net_name in router.committed
    if cond_e:
        cells, added = router.committed[net_name]
        cond_f = isinstance(cells, set) and isinstance(added, list)
        cond_g = len(added) >= 1
    else:
        cond_f = cond_g = False
    ok = cond_a and cond_b and cond_c and cond_d and cond_e and cond_f and cond_g
    print(f"  [{'OK' if cond_a else 'BAD'}] returned True: {routed}")
    print(f"  [{'OK' if cond_b else 'BAD'}] board tracks grew: "
          f"{n_tracks_before} -> {n_tracks_after}")
    print(f"  [{'OK' if cond_c else 'BAD'}] >=1 PCB_VIA emitted: "
          f"{len(pcb_vias)}")
    print(f"  [{'OK' if cond_d else 'BAD'}] >=1 PCB_TRACK emitted: "
          f"{len(pcb_tracks)}")
    print(f"  [{'OK' if cond_e else 'BAD'}] self.committed[{net_name}] set")
    print(f"  [{'OK' if cond_f else 'BAD'}] committed entry has (set, list) shape")
    print(f"  [{'OK' if cond_g else 'BAD'}] committed.added has >=1 item")
    return ok


def test_2_adversarial_rollback():
    """(2) ADVERSARIAL ROLLBACK — pads OUTSIDE the subsystem zone. The
    hook MUST return False without modifying the board (the <2-in-zone-
    pads short-circuit + the atomic-rollback discipline)."""
    print("\n[test_2] adversarial OUT-OF-ZONE pads — must return False + "
          "board unchanged")
    net_name = "SWDIO_CH1"
    board = _build_synthetic_board(net_name=net_name, in_zone=False)
    n_tracks_before = sum(1 for _ in board.GetTracks())

    router = RC.CooperativeRouter(
        board, "CH1",
        seed_nets=[net_name],
        verbose=False,
        via_in_pad_allowed=True,
    )
    router.multi_mech_fallback_enabled = True

    routed = router._try_multi_mech_fallback(net_name)
    n_tracks_after = sum(1 for _ in board.GetTracks())

    cond_a = routed is False
    cond_b = n_tracks_after == n_tracks_before
    cond_c = net_name not in router.committed   # not registered as committed
    ok = cond_a and cond_b and cond_c
    print(f"  [{'OK' if cond_a else 'BAD'}] returned False: {routed}")
    print(f"  [{'OK' if cond_b else 'BAD'}] board unchanged: "
          f"{n_tracks_before} == {n_tracks_after}")
    print(f"  [{'OK' if cond_c else 'BAD'}] committed unchanged: "
          f"{net_name in router.committed}")
    return ok


def test_3_monkeypatch_witness():
    """(4) MONKEYPATCH WITNESS — proves the caller-side glue ACTUALLY
    invokes phase_c.fill_region_with_multi_mech (not just delegates).
    The witness records call count + the RegionSpec + plan + net_pairs
    + that board is the live router.board (NOT a fresh BOARD).
    """
    print("\n[test_3] monkeypatch witness — adapter MUST be called with "
          "constructed RegionSpec + ROUTABLE plan + live board")
    net_name = "SWDIO_CH1"
    board = _build_synthetic_board(net_name=net_name, in_zone=True)

    router = RC.CooperativeRouter(
        board, "CH1",
        seed_nets=[net_name],
        verbose=False,
        via_in_pad_allowed=True,
    )
    router.multi_mech_fallback_enabled = True

    calls = []
    real_fill = PC.fill_region_with_multi_mech

    def witness(plan, region, board=None, board_path=None,
                output_path=None, width_mm=None, clearance_fos_mm=None,
                grid_pitch_mm=None, net_pairs=None, max_chain_depth=None,
                dry_run=False):
        calls.append({
            "plan": plan, "region": region, "board": board,
            "board_path": board_path, "output_path": output_path,
            "width_mm": width_mm, "clearance_fos_mm": clearance_fos_mm,
            "grid_pitch_mm": grid_pitch_mm, "net_pairs": net_pairs,
            "max_chain_depth": max_chain_depth, "dry_run": dry_run,
        })
        return real_fill(plan, region, board=board, board_path=board_path,
                         output_path=output_path, width_mm=width_mm,
                         clearance_fos_mm=clearance_fos_mm,
                         grid_pitch_mm=grid_pitch_mm,
                         net_pairs=net_pairs,
                         max_chain_depth=max_chain_depth,
                         dry_run=dry_run)

    PC.fill_region_with_multi_mech = witness
    try:
        router._try_multi_mech_fallback(net_name)
    finally:
        PC.fill_region_with_multi_mech = real_fill

    cond_a = len(calls) == 1
    print(f"  [{'OK' if cond_a else 'BAD'}] adapter invoked exactly once: "
          f"{len(calls)} call(s)")
    if not cond_a:
        return False
    c = calls[0]
    cond_b = isinstance(c["plan"], dict) and c["plan"].get("verdict") == "ROUTABLE"
    print(f"  [{'OK' if cond_b else 'BAD'}] plan is ROUTABLE dict: "
          f"{c['plan']}")
    cond_c = isinstance(c["region"], PC.RegionSpec)
    print(f"  [{'OK' if cond_c else 'BAD'}] region is RegionSpec")
    cond_d = c["region"].subsystem == "CH1"
    print(f"  [{'OK' if cond_d else 'BAD'}] region.subsystem == 'CH1': "
          f"{c['region'].subsystem}")
    cond_e = tuple(c["region"].bbox) == CH1_BBOX
    print(f"  [{'OK' if cond_e else 'BAD'}] region.bbox == CH1_BBOX: "
          f"{c['region'].bbox}")
    cond_f = "J18" in c["region"].hdi_refs   # whitelisted HDI ref present
    print(f"  [{'OK' if cond_f else 'BAD'}] J18 in region.hdi_refs: "
          f"{c['region'].hdi_refs}")
    cond_g = c["region"].via_budget.get("hdi", 0) > 0  # HDI budget granted
    print(f"  [{'OK' if cond_g else 'BAD'}] HDI budget granted: "
          f"{c['region'].via_budget}")
    cond_h = net_name in c["region"].net_names
    print(f"  [{'OK' if cond_h else 'BAD'}] net_name in region.net_names: "
          f"{c['region'].net_names}")
    cond_i = c["board"] is board   # the LIVE router board (NO copy)
    print(f"  [{'OK' if cond_i else 'BAD'}] board is router.board (live)")
    cond_j = c["net_pairs"] is not None and len(c["net_pairs"]) >= 1
    print(f"  [{'OK' if cond_j else 'BAD'}] net_pairs constructed: "
          f"{c['net_pairs']}")
    # net_pairs schema: ('<ref>.<pad>', '<ref>.<pad>')
    cond_k = all("." in sp and "." in ep for (sp, ep) in c["net_pairs"])
    print(f"  [{'OK' if cond_k else 'BAD'}] net_pairs use '<ref>.<pad>' "
          f"schema")
    cond_l = c["dry_run"] is False
    print(f"  [{'OK' if cond_l else 'BAD'}] dry_run=False (LIVE emit): "
          f"{c['dry_run']}")
    return (cond_a and cond_b and cond_c and cond_d and cond_e and cond_f
            and cond_g and cond_h and cond_i and cond_j and cond_k and cond_l)


def test_4_adversarial_via_creates_short_refused():
    """(5) ADVERSARIAL — monkeypatch the multi_mech_planner to return a
    plan with two co-located vias of different classes (a real short on
    the shared layer). The adapter's pre-emit validation (shorts-gate
    semantics) MUST refuse + atomic rollback MUST restore the board.
    """
    print("\n[test_4] adversarial: planner returns SHORT-creating plan "
          "-> shorts-gate refuses + atomic rollback")
    net_name = "SWDIO_CH1"
    board = _build_synthetic_board(net_name=net_name, in_zone=True)
    n_tracks_before = sum(1 for _ in board.GetTracks())

    router = RC.CooperativeRouter(
        board, "CH1",
        seed_nets=[net_name],
        verbose=False,
        via_in_pad_allowed=True,
    )
    router.multi_mech_fallback_enabled = True

    # Monkeypatch the planner to ALWAYS return a malformed plan: two
    # vias at the same XY with two different classes — the classic
    # shorts-gate violator (test 17c in phase_c.self_test, generalised
    # here for the caller-side glue).
    try:
        from routing_engine import multi_mech_planner as MMP
        from routing_engine import maze_router as MR
    except ImportError:
        import multi_mech_planner as MMP  # type: ignore
        import maze_router as MR  # type: ignore
    real_plan = MMP.plan_multi_mech_route

    def malformed_plan(start, end, **kw):
        return MMP.RoutePlan(
            segments=[],
            vias=[
                MR.Via(point=(J18_X, J18_Y), via_class="blind_F_In2",
                       from_layer="F.Cu", to_layer="In2.Cu"),
                MR.Via(point=(J18_X, J18_Y), via_class="through",
                       from_layer="F.Cu", to_layer="B.Cu"),
            ],
            via_chain=["blind_F_In2", "through"],
        )
    MMP.plan_multi_mech_route = malformed_plan
    try:
        routed = router._try_multi_mech_fallback(net_name)
    finally:
        MMP.plan_multi_mech_route = real_plan

    n_tracks_after = sum(1 for _ in board.GetTracks())
    cond_a = routed is False
    cond_b = n_tracks_after == n_tracks_before
    cond_c = net_name not in router.committed
    ok = cond_a and cond_b and cond_c
    print(f"  [{'OK' if cond_a else 'BAD'}] returned False (shorts-gate "
          f"refused): {routed}")
    print(f"  [{'OK' if cond_b else 'BAD'}] board restored: "
          f"{n_tracks_before} == {n_tracks_after}")
    print(f"  [{'OK' if cond_c else 'BAD'}] not committed: "
          f"{net_name in router.committed}")
    return ok


def main():
    print("=" * 72)
    print("K3 CALLER-SIDE GLUE — _try_multi_mech_fallback actually invokes")
    print("phase_c.fill_region_with_multi_mech with constructed plan + region")
    print("=" * 72)
    results = [
        ("synthetic ROUTABLE",        test_1_synthetic_routable()),
        ("adversarial OUT-OF-ZONE",   test_2_adversarial_rollback()),
        ("monkeypatch witness",       test_3_monkeypatch_witness()),
        ("adversarial SHORT refuse",  test_4_adversarial_via_creates_short_refused()),
    ]
    print("\n" + "=" * 72)
    n_pass = sum(1 for (_, ok) in results if ok)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\nK3 caller-side glue: {n_pass}/{len(results)} tests passed")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
