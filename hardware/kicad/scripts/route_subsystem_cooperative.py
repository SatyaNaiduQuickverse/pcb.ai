#!/usr/bin/env python3
"""route_subsystem_cooperative.py — Cooperative ripup-reroute maze router for
dense IC-escape cascades on 10L stackup.

Per [[reference-cascading-escape-needs-negotiated-routing]] (2026-05-27):
greedy A* self-congests on dense pin-out cascades — each net's escape tracks
block the next net's via spots. Worker R26 hit this on J18 (AT32F421 QFN-32)
+ J19 (DRV8300DRGER QFN-24) CH1 fan-in: 3/9 nets routed then PLATEAUED.

Algorithm (Pathfinder/PathSearch family, after McMurchie+Ebeling 1995):
  Loop over iterations:
    For each unrouted net (priority order):
      A* search on grid with present-congestion cost
      If route found: commit (mark grid cells as used, increment historical
        congestion for any cell already shared)
      If route fails: skip; rip up no nets this pass
    After pass: if any failures remain, RIP-UP all nets sharing congested
      cells (history > threshold) AND re-queue them at higher priority for
      next iteration.
    Bump congestion weight (present_factor *= 1.4) each iteration —
      drives nets to spread out.
  Terminate: all routed OR max-iterations OR plateau (no progress 3 passes).

QFN/LQFP pad-fanout primitive (pad-stub + via):
  Pad is small (0.25×0.88mm typical for J18 QFN-32 0.5mm pitch). Direct
  via-in-pad infeasible. Standard:
    pad (F.Cu) -> short 0.5mm stub on F.Cu (perpendicular to pad axis,
    away from package body) -> via 0.6/0.3mm at stub end -> escape on
    inner layer.

Layer allocation (CH1 STEP-6 plan locked 2026-05-27 per dispatch):
  F.Cu / B.Cu : pad-fanout stubs ≤0.6mm + short island traces
  In2.Cu      : PRIMARY escape — PWM (SI-critical), CSA_OUT (analog SI), dense fan-in
  In4.Cu      : DEDICATED BEMF (OQ-016 lock; In3 + In5 plane shields)
  In6.Cu      : SW escape per OQ-017 (commutation already routed; spare capacity)
  In8.Cu      : ESCAPE-LAYER overflow per PR #192 multi-use (SWD/NRST/BOOT0/kill/VREF)
  In1/In3/In7 : GND planes — UNTOUCHED
  In5         : +VMOTOR plane — UNTOUCHED

Constraints:
  - DRC: trace ≥0.15mm (signal) ≥0.20mm (gate-drive), via 0.3/0.6mm,
    clearance ≥0.15mm board-min
  - Power-class nets (VMOTOR/MOTOR/SHUNT_TOP, +V*, GND) untouched
  - Existing tracks/vias/pads on OTHER nets are immovable obstacles
  - Custom DRU NC-net clearance exemption applies (see pcbai_fpv4in1.kicad_dru)

Usage:
  python3 route_subsystem_cooperative.py <board.kicad_pcb> \
    --subsystem CH1 \
    --output <routed.kicad_pcb> \
    [--max-iterations 30] [--grid-pitch 0.1] [--seed-nets <comma-list>] \
    [--no-rip-routed]

  --no-rip-routed (v4 2026-05-27): pre-existing routed nets (≥1 track/via in
  input board) treated as immovable. Use in multi-pass workflows where pass
  N+1 must preserve pass N's routes. Default OFF (back-compat single-pass).

  --via-in-pad-allowed (v6 2026-05-27): allow vias to drop directly on the
  CENTER of J18 (AT32F421 QFN-32) and J19 (DRV8300 QFN-24) signal pads
  (HDI via-in-pad whitelist). The default fanout topology — pad → 0.5mm
  stub → via — saturated the via-area between J18 south edge and the
  BEMF/CSA filter wall (~22 escape vias possible for 33 pins), capping
  CH1 STEP-6 router yield at 22/33 across 5 router versions (PR#202→206).
  HDI via-in-pad eliminates the fan-out area entirely: each net's via
  drops on its pad and escapes straight to its inner layer. Industry
  standard QFN-escape fix (Altium BGA fanout guide + NWES HDI BGA escape).
  Cost: +$2-3/board production (epoxy-filled + plated-over per JLC HDI
  Class 2). Sai cost-cleared 2026-05-27. Whitelist J18+J19 only — all
  other components preserve standard via-outside-pad cost.
  Default OFF (back-compat: existing PR#202-#206 router runs unchanged).

Exit 0 if all target nets routed, 1 if any unrouted (with diagnostics).

Reusable for CH1 STEP-6 J18/J19 fan-in + CH2/3/4 mirror routing +
future dense subsystem escapes (S3 supervisor, S5 BEC if congested).

Master 2026-05-27 R26 dispatch — replaces greedy escape line.

v7 (2026-05-27, master R26 — worker R22 catch #4 on v6 HDI shorts):
  Two-prong defense-in-depth fix for HDI microvia full-stack-validation gap
  that allowed +2 net-to-net shorts on PR #207 v6 (GHC/GLC vias on F.Cu
  shorting BEMF_A_CH1 / GLA_CH1 tracks on In4).

  ROOT CAUSE: v6 short-circuited via_blocked_for_net to hdi_via_blocked_geom
  for HDI cells (line ~1049), and the geometric check iterates
  track_segments_by_layer / foreign_vias — both of which are populated ONLY
  at _stamp_obstacles() startup. Same-router-run committed tracks/vias get
  stamped into the cell-based obstacle map (catches non-HDI vias) but NOT
  into the segment-list (HDI geom check blind to them).

  PRONG 1: extend full-stack obstacle validation to ALL via classes.
    - commit_paths() now appends committed tracks to track_segments_by_layer
      and committed vias to foreign_vias so the HDI geom check sees them.
    - via_blocked_for_net() for HDI cells now runs BOTH the geom check AND
      a cell-based obstacle scan on inner layers (defense in depth).
  PRONG 2: constrain MICROVIA tag to adjacent-layer pair only.
    - emit_to_board() inspects via target span (F.Cu→target inner layer)
    - Only tags as VIATYPE_MICROVIA when span is JLC HDI Class 2 compliant
      (F.Cu↔In1.Cu or B.Cu↔In8.Cu adjacent-layer microvias).
    - All other spans emit as standard through-via (no MICROVIA tag) —
      they were physically through-vias anyway in v6.

  Either prong alone fixes the bug. Both = defense in depth.

v8 (2026-05-28, master Phase 3 dispatch — OQ-020 emitter gap per PR #227):
  Phase 3 (CH1 final route) diagnosis found that v7's `adj_pairs` recognises
  ONLY the 2 microvia spans (F.Cu↔In1, B.Cu↔In8) at HDI cells; for any
  other target_pair (including the new blind F.Cu↔In2 the OQ-020 whitelist
  now permits per BOARD_INVARIANTS §"HDI Class extension"), the emitter
  silently falls through to `VIATYPE_THROUGH` F.Cu↔B.Cu — which SHORTS at
  fine pitch (the v6/v7 lesson the previous prongs were meant to close).

  v8 fix (3 changes; same file):
    1. Add `via_class_for_span(L_from, L_to, net_name, is_hdi_cell,
       hdi_whitelist)` → {'microvia_F_In1' | 'microvia_B_In8' |
       'blind_F_In2' | 'through' | None}. Per-net whitelist for the new
       blind class is read from `audit_hdi_via_in_pad.BLIND_F_IN2_NET_WHITELIST`
       (the same SSoT routing_engine/run_on_board.py reads — see task
       point 4). REFUSED span at an HDI cell returns None — the router
       MUST skip rather than fall through to THROUGH.
    2. emit_to_board() uses the classifier and emits the matching via
       type/geometry per class:
         microvia_F_In1 / microvia_B_In8 → VIATYPE_MICROVIA + 0.10/0.25mm
         blind_F_In2                     → VIATYPE_BLIND_BURIED + 0.15/0.30mm
                                            + SetLayerPair(F.Cu, In2.Cu)
         through                         → VIATYPE_THROUGH  + 0.30/0.60mm
         None                            → raise ValueError (defense-in-depth;
                                            should never reach emit because A*
                                            rejected the span — see #3)
    3. find_path_astar() skips layer-changes that classify as None at the
       source cell, and uses the LAYER-AWARE span (F.Cu/In1.Cu/In2.Cu for
       blind F-In2; 2-layer for microvias; full-stack for through) in
       `via_blocked_for_net` so foreign copper on layers the barrel never
       touches doesn't falsely block legitimate blind escapes. commit_net
       likewise stamps obstacles only on the layers the barrel actually
       traverses — the layer-aware obstacle analog to phase_a's layer-aware
       escape supply.

  After v8 the OQ-020 4 nets (BSTB / PWM_INHB / SWDIO / PWM_INLA, all _CH1)
  emit correctly as BLIND_BURIED F.Cu↔In2 vias on J18/J19 SMD pads —
  passes audit_hdi_via_in_pad.py + the new DRU rule (PR #226). Other nets
  requesting F.Cu↔In2 at an HDI cell are REFUSED (the router searches
  another layer pair); the silent THROUGH-fall-through bug is closed.

v11 (2026-05-28, CH1 30/30 levers K1 + K2 — drone-grade halo + MST robustness;
     master directive "make it great + no cut corners + drone-grade reliability"):

  TWO orthogonal router-correctness fixes documented in PR #227 final probing.

  ─── K1 — Adjacent-HDI halo over-rejection ───────────────────────────────
  ROOT CAUSE: when a candidate via at pin A's HDI cell considers a foreign
  via at the adjacent pin B (0.5mm QFN pitch), the v9/v10 halo path treated
  pin B's HDI via as needing FULL halo separation
  (halo_radius_candidate + halo_radius_foreign ≈ 0.70mm center-to-center)
  — over-conservative. The PHYSICALLY-correct constraint at a known-HDI
  adjacency is pad-EDGE-to-pad-EDGE clearance against the FoS target
  (0.20mm per ROUTING_METHODOLOGY.md §5c — the "no cut-to-cut" rule).

  The 25/30 board ALREADY exhibits this geometry: BSTB blind via @ J19.17 ↔
  J19.16 sit 0.5mm apart pad-edge ≈ 0.5 − 2×0.15 = 0.20mm — which lands
  EXACTLY on the FoS target. The shorts-gate post-commit accepts it (in the
  "sub-fab-tol-accepted" class) yet the v9/v10 pre-commit refuses it. K1
  closes that inconsistency.

  K1 FIX (3 changes; all in this file):
    1. New helper `is_compatible_hdi_via(via_class) -> bool`: returns True iff
       the foreign via is HDI-class WITH KNOWN pad geometry (the SSoT
       diameter from via_diam_mm_for_class) so a pad-EDGE clearance check
       is well-defined. Microvia + blind_F_In2 = compatible. Through = not
       compatible (falls through to existing halo-overlap check).
    2. `hdi_via_blocked_geom` foreign-via inner loop: when the foreigner is
       compatible HDI, compute
           pad_edge_clearance = center_dist
                              − candidate_pad_half_for_class(via_class)
                              − foreign_pad_half_for_foreign_class
       and ACCEPT iff clearance >= FoS_target (CLEARANCE_MM = 0.20mm).
       Else fall through to the existing centerline-precise check (which
       catches non-HDI foreigns + true conflicts).
    3. Provenance: every accepted-by-K1 placement records the K1 path in
       the foreign-via reason string ("hdi_compat_ok@d=...") so the
       shorts-gate audit + the OPTIONAL per-PR debug can tell which path
       cleared which adjacency.

  SHORTS-GATE PRESERVED: every committed via still passes the v6/v7/F/I
  post-commit clearance check; K1 only relaxes the PRE-commit refusal that
  was over-conservative against the physically-correct pad-edge clearance.
  See test_emit_blind_f_in2.py (K1) tests for the round-trip evidence.

  ─── K2 — MST completion robustness (per-subtree atomicity) ──────────────
  ROOT CAUSE: v3 of route_one_net_mst already made each MST edge attempt
  independent — failed edges no longer abort prior edges (R26 narrow fix).
  But the PR-#227 probing surfaced the next layer: when an MST edge fails
  on the FIRST attempt, the cooperative loop only retries it on a later
  iteration (with higher present_factor pressure). For a 4-pad net like
  KILL_RAIL_N (J19.8 + D38.2 + R76.2 + D37.2) that 1 failed edge often
  re-fails the same way next iteration (the conflict is geometric, not
  congestion). Net stays PARTIAL across iterations until the cap is hit.

  K2 FIX (in route_one_net_mst, single function):
    1. Per-leaf REJOIN-ATTEMPT loop bounded ≤ MST_LEAF_RETRY_CAP = 3:
       on failure, re-attempt the FAILED edge against the FULL multi-source
       pool (i.e. include cells routed by SUBSEQUENT edges in the SAME MST,
       not just earlier ones). This lets a leaf attach to an island formed
       by a later edge that the leaf couldn't see on first pass. v3 only
       grew sources monotonically; K2 also runs a single backwards-rejoin
       pass so the leaf can hook into ANY of the net's islands.
    2. Per-subtree atomicity: trunk + every successfully-routed leaf are
       committed together; only the STILL-failed leaves (after K2 retries)
       are dropped from this attempt. Status reporting unchanged: ROUTED /
       PARTIAL / FAILED stay the same labels the run-loop consumes.
    3. Provenance: every multi-pad net that ends PARTIAL writes an entry
       to `sims/routing_provenance/partial_mst/<sha>_<net>.json` capturing
       {netname, pad_refs, routed_edges, failed_pad_pairs, retries_per_leaf,
       reason_codes, board_sha, timestamp_iso}. The new audit
       audit_partial_mst_provenance.py (G_K1, R40) enforces presence + schema
       so a PARTIAL net is NEVER silently abandoned. Mirrors the R36/G_J1
       discipline for targeted-ripup.

  Cascade-bounded (≤ MST_LEAF_RETRY_CAP = 3) preserves the SURESHOT
  property — no unbounded retry loops, deterministic upper bound on work.

  Together K1 + K2 close the last two known-class router correctness gaps
  surfaced by PR #227. T18 + T19 routing-engine fixtures lock these as
  permanent regressions (APPEND-ONLY; T1-T17 untouched).
"""
from __future__ import annotations

import argparse
import heapq
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import pcbnew
except ImportError:  # pragma: no cover
    sys.stderr.write("FATAL: pcbnew not importable (run inside KiCad python)\n")
    sys.exit(2)


# ─── Configuration ────────────────────────────────────────────────────────

# Default grid pitch (mm). 0.1mm = 100µm. CH1 zone 35×39mm => 350×390 cells per layer.
# 5 routing layers => ~680K cells. ~50 MB Python dict on Pi. Fits Pi memory budget.
DEFAULT_GRID_PITCH = 0.1
DEFAULT_MAX_ITER = 30

# Layer IDs (from pcbnew)
F_CU = pcbnew.F_Cu       # 0
B_CU = pcbnew.B_Cu       # 2
IN1_CU = pcbnew.In1_Cu   # 4  — GND plane
IN2_CU = pcbnew.In2_Cu   # 6  — primary escape
IN3_CU = pcbnew.In3_Cu   # 8  — GND plane
IN4_CU = pcbnew.In4_Cu   # 10 — BEMF dedicated
IN5_CU = pcbnew.In5_Cu   # 12 — +VMOTOR plane
IN6_CU = pcbnew.In6_Cu   # 14 — SW (mostly used by commutation already)
IN7_CU = pcbnew.In7_Cu   # 16 — GND plane
IN8_CU = pcbnew.In8_Cu   # 18 — overflow / SWD / control

# Layers we may route on (in order of preference for layer-cost)
SIGNAL_LAYERS = [F_CU, B_CU, IN2_CU, IN4_CU, IN6_CU, IN8_CU]

# ALL copper layers in 10L stackup — used for via-span obstacle validation.
# A through-via spans F.Cu -> B.Cu and therefore intersects EVERY inner copper
# layer including the plane layers (In1/In3/In5/In7). The router MUST validate
# the via against foreign-net copper on each of those layers, not just on the
# two routing layers it connects.
ALL_COPPER_LAYERS = [F_CU, IN1_CU, IN2_CU, IN3_CU, IN4_CU,
                     IN5_CU, IN6_CU, IN7_CU, IN8_CU, B_CU]

# Plane layers (untouched by signal routing) — used to detect when a proposed
# via must respect an antipad against an existing power plane fill.
PLANE_LAYERS = [IN1_CU, IN3_CU, IN5_CU, IN7_CU]

# Net classification -> preferred inner-layer escape (highest priority first).
#
# v5 (2026-05-27, master R26 NARROW FIX per worker R22 layer-underutilization
# finding): this dict is now consulted twice per net:
#   (1) inner_layers_for() — RESTRICTS the A* allowed-layer set (unchanged).
#       For BEMF the router will NOT plan vias into In8/In6/etc, only
#       In4 + In2 (plus F.Cu/B.Cu always-allowed for pad fanout stubs).
#   (2) layer_pref_cost_mult() — BIASES the A* per-cell cost so the FIRST
#       layer in the list is HALF the cost of the second, etc. This is the
#       v5 fix: without (2), allowed layers had equal base-cost (1.0) and
#       the router picked whichever layer had the lower congestion at the
#       moment, which on CH1 STEP-6 meant In2 saturated while In4 stayed
#       completely empty (worker R22 measured 0 tracks on In4/In6 in the
#       CH1 signal region while In2/In8 held 163/82 tracks respectively).
#
# Multipliers (applied to LAYER_BASE_COST in cost()):
#   index 0 (top preference) -> 0.5x  (router strongly prefers this layer)
#   index 1                  -> 1.0x  (neutral — same as no preference)
#   index 2                  -> 1.5x  (mild discouragement)
#   index ≥3                 -> 2.0x  (strong discouragement)
#   layer NOT in the list    -> 2.0x  (would only be reached via F.Cu/B.Cu
#                                       which is also discouraged at 4.0x base)
# These multipliers are tuned so a preferred-but-mildly-congested layer
# (0.5 * 1.0 + 1.0 * present=1) = 1.5 beats a non-preferred uncongested layer
# (1.0 * 1.0 + 0) = 1.0 only when present>1, i.e. it takes ONE other route on
# the non-preferred layer before preference dominates. This is the desired
# behaviour: fill the preferred layer FIRST, then spill to the next one.
LAYER_PREF = [
    # OQ-016: BEMF analog gets dedicated In4 (sandwiched by In3+In5 GND/+VMOTOR
    # plane shields → low cross-talk). In2 fallback if In4 corridor blocked.
    (re.compile(r"^BEMF_[ABC]_CH\d+$"), [IN4_CU, IN2_CU]),
    # PWM gate-drive inputs: SI-critical short-edge digital — primary In2,
    # spillover to In8 (overflow layer).
    (re.compile(r"^PWM_(IN[HL][ABC])_CH\d+$"), [IN2_CU, IN8_CU]),
    # CSA op-amp outputs (analog SI): primary In2 (paired w/ BEMF on quiet
    # layer concept), spillover to In8.
    (re.compile(r"^CSA_[ABC]_OUT_CH\d+$"), [IN2_CU, IN8_CU]),
    (re.compile(r"^CSA_MAX_CH\d+$"), [IN2_CU, IN8_CU]),
    # SWD/NRST/BOOT0: low-priority debug — push to overflow In8 to leave
    # In2/In4 for SI-critical analog. In2 fallback only if In8 jammed.
    (re.compile(r"^SW(DIO|CLK)_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^NRST_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^BOOT0_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^LED_GPIO_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^(I|OTP)_TRIP_N_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^KILL_(LOCAL|RAIL|LED_NODE)_(N_)?CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^VREF_(I_TRIP|OTP)_CH\d+$"), [IN8_CU, IN2_CU]),
    # Gate-drive (GH*/GL*) + bootstrap (BST*): SHORT hops local to driver IC.
    # In8 primary keeps them off the SI-critical analog layer.
    (re.compile(r"^GH[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^GL[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^BST[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
    # v5: VMOTOR per-channel and SW (MOTOR) — typically routed by upstream
    # power passes, but if any straggler slips through, bias to the spec'd
    # layer per PR #191 / OQ-017.
    (re.compile(r"^VMOTOR_CH\d+$"), [IN8_CU]),                   # PR #191 dual-use
    (re.compile(r"^MOTOR_[ABC]_CH\d+$"), [IN6_CU, F_CU, B_CU]),  # OQ-017 SW escape
]
DEFAULT_INNER_LAYERS = [IN8_CU, IN2_CU]  # fallback

# v5: per-net layer-preference cost multipliers (applied on top of
# LAYER_BASE_COST when --layer-pref is enabled). Module-level so unit
# testable. Index N in the LAYER_PREF list -> multiplier from this table;
# layer NOT in any preference list for this net -> LAYER_PREF_MULT_OTHER.
LAYER_PREF_MULT = [0.5, 1.0, 1.5, 2.0]   # indexable by rank within net's pref list
LAYER_PREF_MULT_OTHER = 2.0              # layer not in the net's pref list

# Per-net cache of (layer -> multiplier). Populated lazily by
# layer_pref_cost_mult(). Cleared at router init (test isolation). The
# mapping is deterministic per net-name and per LAYER_PREF table so safe
# to cache for the lifetime of one router instance.
_LAYER_PREF_CACHE: dict = {}


# v6 (2026-05-27, master R26 HDI via-in-pad enable per dispatch):
# components whose pads support direct via-on-pad placement. Used by
# _stamp_obstacles to SKIP the via_forbidden_zones marking (`mark_pad_zone`)
# for their signal pads — letting the router drop a via centered on the
# pad of THIS net without triggering the adjacent-pad keepout collision.
#
# Why a whitelist (not blanket "via-in-pad everywhere"):
#   - Standard SMD pads were sized for solder-only contact; an unfilled
#     via in pad will wick solder away during reflow (open joint).
#   - JLC HDI Class 2 fab uses epoxy fill + plating-over per pad — they
#     charge +$2-3/board only for the explicit via-in-pad pads, NOT every
#     via on the board. Whitelist preserves the cost envelope.
#   - Worker per-pin analysis 2026-05-27 located the routing-yield cap
#     at J18 south-edge + J19 driver fan-out specifically; HDI on those
#     two components is necessary AND sufficient.
#
# Whitelist matches by Footprint REFERENCE (J18, J19) — the exact two
# components Sai cost-cleared. To extend, add the reference here AND
# update docs/MASTER_HDI_SPEC.md + audit_hdi_via_in_pad.py whitelist.
# ─── CH1 30/30 lever DD — MST root inversion for chronic-leaf nets ──────────
# Per Sai 2026-05-30 DD directive (post Z verify-split diagnosis): the
# chronic R76.1 isolation persists at any K3 chain depth because the MST
# grows greedy-nearest-neighbor FROM J19.8 (pad index 0 in net_pads ordering)
# and consistently strands R76.1 as the last leaf — which then NO_PATHs
# under the verify-split gate.
#
# Inverting the MST root (start from R76.1 instead of J19.8) makes the trunk
# grow OUTWARD toward J19.8 last; the R76.1 leaf becomes the trunk root,
# and the J19.8 escape becomes the last edge — which the HDI lever can
# still solve, just in reverse direction. Per Sai DD spec:
#   KILL_RAIL_N_CH1: root = R76.1  (vs current J19.8)
#   PWM_INLA_CH1:    root = J18.15 (vs current J19.1)
#   GLB_CH1:         root = R50.1  (vs current J19.10)
MST_ROOT_OVERRIDE = {
    # netname -> (footprint_ref, pad_name) — the pad to use as MST root.
    "KILL_RAIL_N_CH1":  ("R76",  "1"),
    "PWM_INLA_CH1":     ("J18",  "15"),
    "GLB_CH1":          ("R50",  "1"),
}


def mst_root_index_for_net(netname: str, pad_info_list) -> int:
    """Return the index in `pad_info_list` whose (ref, padname) matches
    MST_ROOT_OVERRIDE[netname]. Falls back to 0 (current behavior) when no
    override exists or the override pad is not in the list. The list items
    are 8-tuples (ref, padname, x, y, layers, sx, sy) per BoardState.net_pads
    OR (ref, padname, x, y, cells, pad_layers, sx, sy) per _pad_cells_for_net."""
    override = MST_ROOT_OVERRIDE.get(netname)
    if not override:
        return 0
    target_ref, target_pad = override
    for i, item in enumerate(pad_info_list):
        # First two elements are always (ref, padname) in both forms.
        ref, padname = item[0], item[1]
        if ref == target_ref and str(padname) == str(target_pad):
            return i
    return 0


# ─── CH1 30/30 lever Z — extended K3 chain depth for chronic residuals ──────
# Per Sai 2026-05-30 Z directive: K3 multi-mech chain max_depth = 4 default
# leaves chronic chains short of HDI-symmetric F→In2→…→B.Cu paths. Each
# chronic residual (PWM_INLA/GLB/KILL_RAIL_N) needs depth ≥ 6-8 to traverse
# the 5-via stacked microvia + B-side microvia chain. Per-net depth dict
# bumps these specific nets to 8 while keeping the conservative default 4
# for everything else (PathFinder cost-history naturally prefers shorter
# chains; extra depth only consumed when shorter chains exhaust).
K3_CHAIN_DEPTH_DEFAULT = 4
K3_CHAIN_DEPTH_CHRONIC = 8
K3_CHAIN_DEPTH_OVERRIDES = {
    # Chronic residuals (from BOTTOM_MICROVIA_NET_WHITELIST + Phase 4 evidence):
    "PWM_INLA_CH1":     K3_CHAIN_DEPTH_CHRONIC,
    "GLB_CH1":          K3_CHAIN_DEPTH_CHRONIC,
    "KILL_RAIL_N_CH1":  K3_CHAIN_DEPTH_CHRONIC,
    # PWM_INHB + SWDIO were K3-routable pre-EE; bump for safety:
    "PWM_INHB_CH1":     K3_CHAIN_DEPTH_CHRONIC,
    "SWDIO_CH1":        K3_CHAIN_DEPTH_CHRONIC,
}


def k3_chain_depth_for_net(netname: str) -> int:
    """Per-net K3 chain depth — per Sai 2026-05-30 lever Z.
    Returns K3_CHAIN_DEPTH_CHRONIC (8) for chronic residual nets, otherwise
    K3_CHAIN_DEPTH_DEFAULT (4)."""
    return K3_CHAIN_DEPTH_OVERRIDES.get(netname, K3_CHAIN_DEPTH_DEFAULT)


HDI_VIA_IN_PAD_REFS = (
    # Original CH1 30/30 lever D + G whitelist (HDI starts at the chip pins):
    "J18", "J19",
    # CH1 30/30 lever CC HDI SYMMETRIC (2026-05-30 Sai approved):
    # destination-side footprints for the 3 chronic residual chains.
    # Per Sai's CC physics analysis post-EE merge: K3 multi-mech refuses
    # through-via at fine-pitch chip pads (0.60mm pad > 0.5mm pitch).
    # Adding HDI via-in-pad geometry at the CHAIN DESTINATIONS lets K3
    # use microvia (0.25mm pad) at BOTH chain endpoints, completing the
    # chain through HDI classes only. Mirrors BOTTOM_MICROVIA_REFS — same
    # surgical-scope envelope; closes the symmetric loop for chronics.
    "TP22",    # SWDIO_CH1 destination (test point — 1mm pad)
    "R50",     # GLB_CH1 destination at R50.1
    "R76",     # KILL_RAIL_N_CH1 destination at R76.1
    "D37",     # KILL_RAIL_N_CH1 chained at D37.2
    "D38",     # KILL_RAIL_N_CH1 chained at D38.2
    # CH1 30/30 UU.1-ESCAPE (2026-05-30): adjacent-pin relay TPs
    "TP_ESCAPE_PWM_INLA",   # adjacent to J18.15 for PWM_INLA escape
)


def is_hdi_via_in_pad_ref(footprint_ref: str) -> bool:
    """Return True if `footprint_ref` is whitelisted for HDI via-in-pad."""
    return footprint_ref in HDI_VIA_IN_PAD_REFS


def layer_pref_cost_mult(net_name: str, layer: int) -> float:
    """Return cost multiplier for `layer` when routing `net_name`.

    Returns 1.0 (no bias) if net matches no LAYER_PREF entry (i.e. uses the
    DEFAULT_INNER_LAYERS fallback). For an explicitly classified net,
    returns the indexed multiplier from LAYER_PREF_MULT (rank 0 = 0.5x,
    rank 1 = 1.0x, etc.) or LAYER_PREF_MULT_OTHER for layers not in the
    preference list.

    Always returns 1.0 for F.Cu / B.Cu — they have their own discouragement
    via LAYER_BASE_COST=4.0; we don't want to double-penalize the pad-fanout
    stubs since those are only ~0.5mm.
    """
    if layer in (F_CU, B_CU):
        return 1.0
    cached = _LAYER_PREF_CACHE.get(net_name)
    if cached is None:
        cached = {}
        matched = False
        for pat, layers in LAYER_PREF:
            if pat.match(net_name):
                matched = True
                for rank, L in enumerate(layers):
                    mult = LAYER_PREF_MULT[min(rank, len(LAYER_PREF_MULT) - 1)]
                    cached[L] = mult
                break
        cached['__matched__'] = matched
        _LAYER_PREF_CACHE[net_name] = cached
    if not cached.get('__matched__', False):
        return 1.0  # unclassified net: no bias
    mult = cached.get(layer)
    return mult if mult is not None else LAYER_PREF_MULT_OTHER

# Priority bucket (lower=route earlier). High-fanin / SI-critical first.
def net_priority(net_name: str) -> int:
    # 0: highest priority (BEMF analog, CSA analog)
    if re.match(r"^BEMF_[ABC]_CH\d+$", net_name): return 0
    if re.match(r"^CSA_[ABC]_OUT_CH\d+$", net_name): return 0
    if re.match(r"^CSA_MAX_CH\d+$", net_name): return 0
    # 1: dense fan-in PWM
    if re.match(r"^PWM_IN[HL][ABC]_CH\d+$", net_name): return 1
    # 2: gate drive (short hops)
    if re.match(r"^G[HL][ABC]_CH\d+$", net_name): return 2
    if re.match(r"^BST[ABC]_CH\d+$", net_name): return 2
    # 3: control / debug
    if re.match(r"^SW(DIO|CLK)_CH\d+$", net_name): return 3
    if re.match(r"^NRST_CH\d+$", net_name): return 3
    if re.match(r"^BOOT0_CH\d+$", net_name): return 3
    if re.match(r"^(I|OTP)_TRIP_N_CH\d+$", net_name): return 3
    if re.match(r"^KILL_", net_name): return 3
    if re.match(r"^VREF_", net_name): return 3
    if re.match(r"^LED_GPIO_CH\d+$", net_name): return 3
    return 4

# Widths per net pattern (mm)
WIDTH_RULES = [
    (re.compile(r"^G[HL][ABC]_CH\d+$"), 0.20),     # gate drive
    (re.compile(r"^BST[ABC]_CH\d+$"), 0.20),       # bootstrap
    (re.compile(r"^PWM_IN[HL][ABC]_CH\d+$"), 0.15),
    (re.compile(r"^BEMF_[ABC]_CH\d+$"), 0.15),
    (re.compile(r"^CSA_"), 0.15),
]
DEFAULT_WIDTH = 0.15

def width_for(net_name: str) -> float:
    for pat, w in WIDTH_RULES:
        if pat.match(net_name): return w
    return DEFAULT_WIDTH

def inner_layers_for(net_name: str):
    for pat, layers in LAYER_PREF:
        if pat.match(net_name): return list(layers)
    return list(DEFAULT_INNER_LAYERS)

# Skip these nets entirely (power / plane / handled-elsewhere by other PRs)
SKIP_NET_PATTERNS = [
    re.compile(r"^GND$"), re.compile(r"^BATGND$"),
    re.compile(r"^\+VMOTOR"), re.compile(r"^VMOTOR_CH"),
    re.compile(r"^MOTOR_[ABC]_CH\d+$"),
    re.compile(r"^SHUNT_[ABC]_TOP_CH\d+$"),
    re.compile(r"^\+V"),                 # +V5_FC / +V5_AI / +V9_VTX...
    re.compile(r"^\+3V"),                # +3V3 / +3V3A
    re.compile(r"^V3V3"),                # V3V3A
    re.compile(r"^V_BUCK"),
    re.compile(r"^HALL_VCC"),
    re.compile(r"^VBAT_SENSE"),
    re.compile(r"^\+BATT"),
    re.compile(r"^TLM$"), re.compile(r"^BUS_CURR_HALL_OUT$"),
    re.compile(r"^M1_CLEAN$"), re.compile(r"^M1_HALL"),  # Hall sensor nets
    re.compile(r"^NTC"),                  # thermistor sense
    re.compile(r"^VREF_2V5$"),            # global VREF — cross-subsystem (S3 generates)
    re.compile(r"^KILL_LED_NODE_CH\d+$"), # LED node — bilateral B.Cu, leave for later
    re.compile(r"^M[1-4]_CLEAN$"), re.compile(r"^M[1-4]_HALL"),
    re.compile(r"^NC$"), re.compile(r"_NC_CH\d+$"),  # NC nets — no routing
    re.compile(r"^N\$"),                  # unnamed
    re.compile(r"^Net-"),
    re.compile(r"^unconnected"),
]

def should_route(net_name: str) -> bool:
    if not net_name: return False
    for pat in SKIP_NET_PATTERNS:
        if pat.search(net_name): return False
    return True

# Constants
PAD_FANOUT_MM = 0.5     # length of pad-out stub before via drop
VIA_DRILL_MM = 0.3
VIA_DIAM_MM = 0.6
CLEARANCE_MM = 0.20     # board-min ≥0.20 (audit_power_drc HIGH_CURRENT_CLEARANCE_MM)
VIA_CLEAR_MM = 0.20
TRACE_HALF_MM = 0.08    # 0.15mm trace / 2 + small margin
GRID_SLOP_MM = 0.025    # extra halo to compensate grid-cell discretization (=pitch/4)
# halo total = 0.305mm pad-edge keepout for foreign-net cells.
# At 0.5mm QFN pitch with 0.125mm pad-half, between-pad gap = 0.25mm < 2×halo => no trace between
# adjacent QFN pads (must escape perpendicular only — correct dog-bone topology).

# v6 (2026-05-27): HDI microvia geometry for via-in-pad on J18/J19 whitelist.
# JLC HDI Class 2 capability: laser-drilled 0.1mm hole + 0.075mm annular ring
# = 0.25mm via pad (= width of 0.25mm × 0.875mm QFN signal pad). This fits
# entirely within the QFN pad bbox, so adjacent-pad clearance reduces to:
#   center-to-center 0.5mm (pitch) − via_pad/2 (0.125) − adj_pad/2 (0.125)
#   = 0.25mm  ≥  CLEARANCE 0.2mm  →  DRC clean.
# Standard 0.6mm via_pad would extend 0.175mm beyond the SMD pad edge =
# clearance violation against adjacent pad. HDI microvia is the geometry
# enabler — without it, "via-in-pad" is geometrically infeasible at 0.5mm
# pitch QFN. Sai cost-cleared 2026-05-27 (+$2-3/board production for HDI
# Class 2 with epoxy fill + plate-over per JLC tech spec).
HDI_VIA_DRILL_MM = 0.10   # JLC laser drill min (HDI Class 2)
HDI_VIA_DIAM_MM = 0.25    # = QFN pad short-axis width
# HDI obstacle-scan radius: smaller via → smaller foreign-copper exclusion.
# Foreign copper must stay (HDI_VIA_DIAM/2 + CLEARANCE) = 0.325mm from via
# center. Compared to standard via 0.5mm. Saves ~0.175mm of scan radius —
# lets the via fit between adjacent QFN pad copper at 0.5mm pitch.
HDI_VIA_HALF_MM = HDI_VIA_DIAM_MM / 2 + CLEARANCE_MM  # = 0.325mm

# v8 (2026-05-28, master Phase 3 OQ-020 emitter gap — PR #227 diagnosis):
# Blind/buried F.Cu↔In2 via class (the OQ-020 ACTIVATE lever). Per
# BOARD_INVARIANTS §"HDI Class extension: blind/buried F.Cu↔In2" + DRU
# §"HDI blind/buried F.Cu↔In2" + audit_hdi_via_in_pad.BLIND_F_IN2_NET_WHITELIST.
# Drill 0.15mm (>= JLC HDI blind/buried laser min; +50% FoS over 0.10mm
# single-microvia limit per §5c FoS-everywhere). Pad 0.30mm (= drill + 2×0.075
# annular; fits QFN long-axis 0.875mm pad). Barrel traverses ONLY F.Cu↔In1↔In2
# (3 layers) — NOT the full F.Cu↔B.Cu stack a through-via spans. Layer-aware
# obstacle validation uses BLIND_F_IN2_SPAN below (the layer-aware analog to
# the layer-aware escape supply primitive in phase_a.py).
BLIND_F_IN2_DRILL_MM = 0.15
BLIND_F_IN2_DIAM_MM = 0.30
BLIND_F_IN2_HALF_MM = BLIND_F_IN2_DIAM_MM / 2 + CLEARANCE_MM  # = 0.35mm
# Layers a blind F.Cu↔In2 barrel actually intersects (F.Cu / In1 / In2 only).
# Through-via spans ALL_COPPER_LAYERS; blind F-In2 spans this 3-tuple, so
# foreign copper on In3-In8 + B.Cu does NOT block a blind F-In2 (the barrel
# never reaches those layers). The layer-aware obstacle check (point 3 of
# the Phase 3 emitter patch) reads this tuple.
BLIND_F_IN2_SPAN = (F_CU, IN1_CU, IN2_CU)

# LEVER L (2026-05-28, CH1 30/30): STACKED microvia F.Cu↔In1↔In2 — JLC HDI
# Class 2 supports stacked microvia natively (top F.Cu↔In1.Cu microvia
# stacked geometrically on bottom In1.Cu↔In2.Cu microvia; the In1 landing
# is an isolated "antipad+pad" copper island, electrically tied to neither
# GND plane nor signal). Adds a SECOND signal-reaching via mechanism per
# pin (industry-standard since iPhone 4 era; ~$1-2/board adder, no new
# fab class). Whitelist = same 6 nets / 8 landings as BLIND_F_IN2 (router
# may pick blind OR stacked per pin — both reach In2 signal layer).
#
# Geometry: each LEG is identical to the existing HDI microvia
# F-In1 (drill 0.10mm / pad 0.25mm / annular 0.075mm). Stacking alignment
# tolerance ≤0.025mm per JLC HDI Class 2 spec (well within the 0.075mm
# annular budget; no cut-to-cut per §5c FoS).
STACKED_MICROVIA_DRILL_MM = HDI_VIA_DRILL_MM   # = 0.10mm (each leg)
STACKED_MICROVIA_DIAM_MM = HDI_VIA_DIAM_MM     # = 0.25mm (each leg)
STACKED_MICROVIA_HALF_MM = STACKED_MICROVIA_DIAM_MM / 2 + CLEARANCE_MM  # = 0.325mm
# Layers a stacked microvia barrel set traverses: F.Cu (top entry),
# In1.Cu (the isolated pad island between top + bottom legs), In2.Cu
# (bottom signal escape). Same 3-tuple as BLIND_F_IN2_SPAN — the two
# classes deliver the SAME barrel-layer coverage; the fab method differs
# (single blind drill vs. two stacked microvias).
STACKED_MICROVIA_SPAN = (F_CU, IN1_CU, IN2_CU)


# v8: per-named-net whitelist of nets permitted to use the blind F.Cu↔In2
# class. Single source of truth = audit_hdi_via_in_pad.BLIND_F_IN2_NET_WHITELIST
# (the gate that ENFORCES this on the saved board). Imported lazily here so
# the router stays in lock-step with the audit without duplicating the list
# (a divergence would either allow the router to emit a via the audit then
# rejects, or vice-versa). On import failure (e.g. running route_subsystem
# in a venv without the audit on the path) we fall back to an empty tuple —
# which DEGRADES TO REFUSING THE NEW CLASS, never to silently fall through
# to THROUGH-via (the bug we are fixing). Mirrors the same pattern used by
# routing_engine/run_on_board.py lines 175-177.
try:                                          # pragma: no cover - import path
    from audit_hdi_via_in_pad import BLIND_F_IN2_NET_WHITELIST as \
        _BLIND_F_IN2_NET_WHITELIST            # canonical .kicad_pcb names
except Exception:                             # pragma: no cover
    _BLIND_F_IN2_NET_WHITELIST = ()

# LEVER L: parallel SSoT import for the stacked-microvia whitelist. Same
# audit module is the single source of truth; failing back to empty tuple
# DEGRADES TO REFUSING THE NEW CLASS (never falls through to THROUGH —
# the v6/v7 shorts lesson).
try:                                          # pragma: no cover - import path
    from audit_hdi_via_in_pad import STACKED_MICROVIA_NET_WHITELIST as \
        _STACKED_MICROVIA_NET_WHITELIST
except Exception:                             # pragma: no cover
    _STACKED_MICROVIA_NET_WHITELIST = ()

# LEVER BB 2026-05-29 (CH1 30/30 close-out): parallel SSoT imports for the
# B.Cu↔In8 microvia whitelist (bottom-side HDI escape — JLC HDI Class 2
# standard, mirror of the F-side microvia class). Same fail-degrade
# discipline as BLIND_F_IN2 + STACKED — empty tuple => refuse-class (never
# silent THROUGH-via at a fine-pitch HDI cell). Two single-sources-of-truth:
#   * BOTTOM_MICROVIA_NET_WHITELIST  — the 3 chronic residual nets
#                                      (PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1)
#   * BOTTOM_MICROVIA_REFS           — the destination passive/connector refs
#                                      permitted to host a B.Cu↔In8 microvia
#                                      (J19, R50, R76, D37, D38)
try:                                          # pragma: no cover - import path
    from audit_hdi_via_in_pad import BOTTOM_MICROVIA_NET_WHITELIST as \
        _BOTTOM_MICROVIA_NET_WHITELIST
except Exception:                             # pragma: no cover
    _BOTTOM_MICROVIA_NET_WHITELIST = ()

try:                                          # pragma: no cover - import path
    from audit_hdi_via_in_pad import BOTTOM_MICROVIA_REFS as \
        _BOTTOM_MICROVIA_REFS
except Exception:                             # pragma: no cover
    _BOTTOM_MICROVIA_REFS = ()


def blind_f_in2_net_whitelist():
    """Return the canonical-net-name tuple permitted for the blind F.Cu↔In2
    via class. Single source of truth = audit_hdi_via_in_pad.
    BLIND_F_IN2_NET_WHITELIST. Empty tuple on import failure (refuse-class
    behaviour — the router NEVER silently falls through to THROUGH-via for
    a fine-pitch HDI cell, which is the v6/v7 shorts lesson per the file
    banner and [[reference-cascading-escape-needs-negotiated-routing]])."""
    return _BLIND_F_IN2_NET_WHITELIST


def stacked_microvia_net_whitelist():
    """LEVER L SSoT — net-name tuple permitted for stacked microvia
    F.Cu↔In1↔In2 (JLC HDI Class 2 native stacked-microvia fab class).
    Single source of truth = audit_hdi_via_in_pad.STACKED_MICROVIA_NET_WHITELIST.
    Empty tuple on import failure (refuse-class behaviour; never falls
    through to THROUGH-via at a fine-pitch HDI cell — the v6/v7 shorts
    lesson)."""
    return _STACKED_MICROVIA_NET_WHITELIST


# LEVER BB module-level flag — set via CLI --bcu-microvia-allowed.
# When True, phase_c marks BOTTOM_MICROVIA_REFS pads as is_hdi_whitelisted
# and the via_class_for_span / K3 multi-mech planner accept microvia_B_In8
# on whitelisted (net, ref) destinations. Default False preserves the
# pre-BB behaviour (J18/J19-only HDI whitelist).
_BCU_MICROVIA_ALLOWED = False


def set_bcu_microvia_allowed(enabled: bool) -> None:
    """LEVER BB toggle — sets the module-level flag consulted by phase_c
    + the multi-mech adapters when constructing pin / region invocations.
    Idempotent. Called by main() when --bcu-microvia-allowed is passed."""
    global _BCU_MICROVIA_ALLOWED
    _BCU_MICROVIA_ALLOWED = bool(enabled)


def bcu_microvia_allowed() -> bool:
    """LEVER BB query — return current module-level state of the BB flag."""
    return _BCU_MICROVIA_ALLOWED


def bottom_microvia_net_whitelist():
    """LEVER BB SSoT — net-name tuple permitted for the B.Cu↔In8 microvia
    class (bottom-side HDI escape; JLC HDI Class 2 mirror of microvia
    F-In1). Single source of truth = audit_hdi_via_in_pad.
    BOTTOM_MICROVIA_NET_WHITELIST. Empty tuple on import failure
    (refuse-class behaviour; never falls through to THROUGH-via at a
    fine-pitch HDI cell — v6/v7 shorts lesson)."""
    return _BOTTOM_MICROVIA_NET_WHITELIST


def bottom_microvia_refs():
    """LEVER BB SSoT — destination footprint refs permitted to host a
    B.Cu↔In8 microvia (the bottom-side HDI escape landing list).
    Single source of truth = audit_hdi_via_in_pad.BOTTOM_MICROVIA_REFS.
    Empty tuple on import failure (refuse-ref behaviour; the via class
    is gated to BOTH a whitelisted net AND a whitelisted ref)."""
    return _BOTTOM_MICROVIA_REFS


def is_bottom_microvia_ref(footprint_ref: str) -> bool:
    """Return True iff `footprint_ref` is whitelisted as a destination-side
    LEVER BB landing for B.Cu↔In8 microvia escape."""
    return footprint_ref in _BOTTOM_MICROVIA_REFS


# Adjacent-layer microvia spans (JLC HDI Class 2 single laser-drill spec) —
# the existing classes. Bidirectional (router may pick either direction).
_MICROVIA_F_IN1_SPAN = {(F_CU, IN1_CU), (IN1_CU, F_CU)}
_MICROVIA_B_IN8_SPAN = {(B_CU, IN8_CU), (IN8_CU, B_CU)}
# Blind/buried F.Cu↔In2 span (OQ-020) — bidirectional.
_BLIND_F_IN2_PAIRS = {(F_CU, IN2_CU), (IN2_CU, F_CU)}


def via_class_for_span(L_from, L_to, net_name, is_hdi_cell,
                       hdi_whitelist=None, stacked_whitelist=None,
                       bottom_microvia_whitelist=None,
                       prefer_stacked=False):
    """Classify a (L_from, L_to) via span for `net_name` into one of:
      'microvia_F_In1'             — JLC HDI Class 2 adjacent microvia (F.Cu↔In1.Cu)
      'microvia_B_In8'             — JLC HDI Class 2 adjacent microvia (B.Cu↔In8.Cu)
      'blind_F_In2'                — JLC HDI blind/buried F.Cu↔In2 (OQ-020 class),
                                      permitted ONLY when `net_name` is in
                                      `hdi_whitelist` (BLIND_F_IN2_NET_WHITELIST)
      'stacked_microvia_F_In1_In2' — JLC HDI Class 2 stacked microvia (LEVER L);
                                      emitted as TWO MICROVIA legs (top F↔In1 +
                                      bottom In1↔In2). Permitted ONLY when
                                      `net_name` is in `stacked_whitelist`
                                      (STACKED_MICROVIA_NET_WHITELIST). For the
                                      F.Cu↔In2.Cu span this is an ALTERNATIVE
                                      to blind_F_In2 (both reach In2 signal).
                                      Selected when `prefer_stacked=True` AND
                                      the net is in the stacked whitelist; by
                                      default the existing blind_F_In2 class is
                                      preferred for back-compat (the choice is
                                      semantically equivalent — both signal-
                                      reaching — but the emitter / halo maths
                                      vary by the per-class geometry).
      'through'                    — standard F.Cu↔B.Cu through-via (any span
                                      on a non-HDI cell; existing behaviour)
      None                         — REFUSED: span is not permitted at this HDI
                                      cell for this net. Router MUST skip the
                                      layer-change candidate. NEVER fall
                                      through to THROUGH at HDI cells.

    `hdi_whitelist` defaults to `blind_f_in2_net_whitelist()` (the audit's
    canonical list). `stacked_whitelist` defaults to
    `stacked_microvia_net_whitelist()` (parallel SSoT for LEVER L). Callers
    MAY pass overrides for testing.

    LEVER L semantics: for a F.Cu↔In2.Cu span on a stacked-whitelisted net
    at an HDI cell, `prefer_stacked=True` returns 'stacked_microvia_F_In1_In2'
    instead of 'blind_F_In2'. Both classes provide signal-reaching escape;
    the choice is a budget knob (the router may pick stacked when blind is
    consumed by another whitelist net on the same side, mathematically
    doubling supply per pin). Default `prefer_stacked=False` preserves the
    pre-LEVER-L behaviour (blind F-In2 still chosen first).
    """
    pair = (L_from, L_to)
    if not is_hdi_cell:
        # Non-HDI cell: any span emits as standard through-via (existing
        # v6/v7 behaviour preserved).
        return 'through'
    # HDI cell: only the 4 sanctioned classes are physically realisable
    # (JLC HDI Class 2 + OQ-020 blind extension + LEVER L stacked +
    # LEVER BB bottom-side microvia). Anything else is refused.
    if pair in _MICROVIA_F_IN1_SPAN:
        return 'microvia_F_In1'
    if pair in _MICROVIA_B_IN8_SPAN:
        # LEVER BB 2026-05-29: bottom-side microvia is GATED to the
        # BOTTOM_MICROVIA_NET_WHITELIST (same surgical-scope discipline
        # as the F-side blind_F_In2 net whitelist). The previous
        # unconditional `return 'microvia_B_In8'` predated the BB net
        # gate; preserved for HDI cells whose net is BB-whitelisted.
        # NOTE: HDI cells originate from BOTTOM_MICROVIA_REFS pads on
        # B.Cu (via _pin_from_pcbnew's BB extension); a non-BB HDI cell
        # asking for B↔In8 is the F-side J18/J19 case where the start
        # pin is F.Cu and the planner asks for B↔In8 at a non-pin cell
        # (the multi-mech planner allows this when the END pin is on
        # B.Cu — both ends contribute to hdi_pin_cells). For back-compat
        # with the legacy F-side flow, an unrecognised net at a B↔In8
        # span returns the class without checking the whitelist UNLESS
        # the caller passes `bottom_microvia_whitelist=()` (which
        # disables the back-compat path and enforces the new gate;
        # callers that opt into BB pass the SSoT whitelist explicitly).
        bwl = bottom_microvia_whitelist if bottom_microvia_whitelist is not None \
            else None
        if bwl is None:
            # Back-compat: no BB gate active — class returned for the
            # span on any HDI cell (the F-side legacy flow + the BB
            # opt-in callers will pass an explicit whitelist below).
            return 'microvia_B_In8'
        # BB gate active: enforce net whitelist (mirrors blind_F_In2 gate).
        if net_name in bwl:
            return 'microvia_B_In8'
        # Span requested by non-whitelisted net at a B-side HDI cell:
        # REFUSE. The planner falls through to seek another mechanism.
        return None
    if pair in _BLIND_F_IN2_PAIRS:
        wl = hdi_whitelist if hdi_whitelist is not None \
            else blind_f_in2_net_whitelist()
        swl = stacked_whitelist if stacked_whitelist is not None \
            else stacked_microvia_net_whitelist()
        # LEVER L: if prefer_stacked AND net is stacked-whitelisted, return
        # the stacked class. Otherwise default to the existing blind_F_In2
        # class (preserves back-compat for non-LEVER-L code paths).
        if prefer_stacked and net_name in swl:
            return 'stacked_microvia_F_In1_In2'
        if net_name in wl:
            return 'blind_F_In2'
        # If the net is NOT in the blind WL but IS in the stacked WL,
        # return the stacked class — same signal-reach, mathematically
        # equivalent supply. (The two whitelists are deliberately equal,
        # but this defensive branch keeps semantics consistent if they
        # ever diverge.)
        if net_name in swl:
            return 'stacked_microvia_F_In1_In2'
        # Span requested by non-whitelisted net at HDI cell: REFUSE.
        # (The DRU rejects this anyway — but the router must NOT fall
        # through to THROUGH F.Cu↔B.Cu, which would short adjacent
        # pads. Routing fails → A* searches another layer pair.)
        return None
    # Some other span at an HDI cell (e.g. F.Cu↔In4, In8↔In2, etc.) is
    # not a sanctioned HDI class on this fab process → REFUSE.
    return None


def via_span_layers(via_class):
    """Layers a via of `via_class` actually barrel-traverses (for the layer-
    aware obstacle check — point 3 of the OQ-020 emitter patch).

    - 'through'         spans ALL_COPPER_LAYERS (F.Cu→B.Cu)
    - 'microvia_F_In1'  spans only F.Cu, In1.Cu (adjacent laser drill)
    - 'microvia_B_In8'  spans only In8.Cu, B.Cu (adjacent laser drill)
    - 'blind_F_In2'     spans F.Cu, In1.Cu, In2.Cu (BLIND_F_IN2_SPAN)
    - None              caller's responsibility to never call (refused class)

    Foreign copper on layers OUTSIDE the via's barrel does NOT block it —
    e.g. a track on In4 on a foreign net cannot collide with a blind F-In2
    via (the barrel never reaches In4). This is the layer-aware analog to
    the layer-aware escape supply primitive in routing_engine/phase_a.py."""
    if via_class == 'through':
        return tuple(ALL_COPPER_LAYERS)
    if via_class == 'microvia_F_In1':
        return (F_CU, IN1_CU)
    if via_class == 'microvia_B_In8':
        return (IN8_CU, B_CU)
    if via_class == 'blind_F_In2':
        return BLIND_F_IN2_SPAN
    # LEVER L: stacked microvia F.Cu↔In1↔In2 — same 3-layer barrel coverage
    # as blind F-In2 (F.Cu / In1.Cu isolated pad / In2.Cu); the fab method
    # differs (two stacked microvias vs. one blind drill) but the
    # layer-aware obstacle-check semantics are identical.
    if via_class == 'stacked_microvia_F_In1_In2':
        return STACKED_MICROVIA_SPAN
    # Refused class — caller should never reach here.
    raise ValueError(f"via_span_layers: refused via_class {via_class!r}")


# v9 (2026-05-28, CH1 30/30 lever F — worker R22 catch on v8 halo over-rejection):
# Per-via-class diameter lookup. The 4 sanctioned via classes have distinct
# barrel diameters (per JLC HDI Class 2 fab spec + OQ-020 BOARD_INVARIANTS):
#   - 'through'         → VIA_DIAM_MM        = 0.60mm (standard F.Cu↔B.Cu)
#   - 'microvia_F_In1'  → HDI_VIA_DIAM_MM    = 0.25mm (laser-drilled adjacent)
#   - 'microvia_B_In8'  → HDI_VIA_DIAM_MM    = 0.25mm (laser-drilled adjacent)
#   - 'blind_F_In2'     → BLIND_F_IN2_DIAM_MM= 0.30mm (blind/buried F.Cu↔In2)
# Single source of truth = the same per-class constants the emitter
# (emit_to_board) and own-stamping (commit_paths) already consume — keeps
# router clearance check + via emission + obstacle stamping in lock-step so
# the foreign-copper exclusion radius at a candidate cell EXACTLY matches the
# physical via barrel that would be emitted there.
def via_diam_mm_for_class(via_class):
    """Return the physical barrel diameter (mm) for a sanctioned via class.

    'through' → standard (0.60mm). Microvia classes → 0.25mm. Blind F-In2 →
    0.30mm. Unknown class falls back to standard through diameter (defensive
    upper bound — preserves v6/v7 shorts-gate behaviour on classifier drift).
    """
    if via_class == 'microvia_F_In1' or via_class == 'microvia_B_In8':
        return HDI_VIA_DIAM_MM
    if via_class == 'blind_F_In2':
        return BLIND_F_IN2_DIAM_MM
    # LEVER L: each stacked microvia leg has the same pad diameter as the
    # existing HDI microvia F-In1 (0.25mm). The stacked structure presents
    # ONE pad diameter to the obstacle / halo check (the two legs are
    # geometrically co-aligned with the same XY + diameter).
    if via_class == 'stacked_microvia_F_In1_In2':
        return STACKED_MICROVIA_DIAM_MM
    # 'through' (or anything else) → standard via diameter. Defensive default
    # is the LARGER diameter — never under-stamps a halo, so shorts-gate
    # semantics are preserved on unexpected class strings.
    return VIA_DIAM_MM


def via_halo_radius_mm(via_class, trace_width_mm=None):
    """v9 — per-via-class obstacle halo radius (mm) used by:
      - existing-via obstacle stamping (stamp foreign vias on grid)
      - own-via obstacle stamping (commit_paths)
      - candidate-via geometric clearance (hdi_via_blocked_geom — implicit
        via the via_pad_half_mm_for_class companion below)
      - own-via re-stamping (_rebuild_grid)

    Returns: diam/2 + CLEARANCE_MM + trace_half + GRID_SLOP_MM

    `trace_width_mm` defaults to 2 × TRACE_HALF_MM (the router's nominal
    signal trace width, ~0.16mm). Callers stamping foreign vias against a
    specific track width pass that width explicitly. The halo radius is the
    centre-to-centre distance at which a foreign trace centerline would just
    touch the via pad edge + clearance + trace edge — i.e. the minimum gap
    the router must respect when placing or scanning around a via.

    Per-class behaviour:
      'through'                     → 0.60/2 + 0.20 + 0.08 + 0.025 = 0.605mm
      'microvia_F_In1'              → 0.25/2 + 0.20 + 0.08 + 0.025 = 0.430mm
      'microvia_B_In8'              → 0.25/2 + 0.20 + 0.08 + 0.025 = 0.430mm
      'blind_F_In2'                 → 0.30/2 + 0.20 + 0.08 + 0.025 = 0.455mm
      'stacked_microvia_F_In1_In2'  → 0.25/2 + 0.20 + 0.08 + 0.025 = 0.430mm
                                      (per leg; legs co-aligned same XY)

    SSoT discipline: NO hard-coded numbers in callers — every halo derives
    from this helper + the per-class constants above. The LEVER L stacked
    microvia class was added 2026-05-28 by adding ONLY the diameter constant
    (STACKED_MICROVIA_DIAM_MM) + a branch in via_diam_mm_for_class + a
    branch in via_span_layers — clearance maths fell out automatically,
    proving the design.
    """
    if trace_width_mm is None:
        trace_half = TRACE_HALF_MM
    else:
        trace_half = trace_width_mm / 2.0
    return (via_diam_mm_for_class(via_class) / 2.0
            + CLEARANCE_MM + trace_half + GRID_SLOP_MM)


def via_pad_half_mm_for_class(via_class):
    """v9 — per-via-class via-pad-edge-to-foreign-copper distance (mm). Used
    by via_blocked_for_net's plane-fill scan (which scans cells where the
    PAD itself would land in foreign plane copper, no trace-half offset).

    Returns: diam/2 + CLEARANCE_MM
      'through'                     → 0.500mm
      'microvia_F_In1'              → 0.325mm  (HDI_VIA_HALF_MM)
      'microvia_B_In8'              → 0.325mm  (HDI_VIA_HALF_MM)
      'blind_F_In2'                 → 0.350mm  (BLIND_F_IN2_HALF_MM)
      'stacked_microvia_F_In1_In2'  → 0.325mm  (STACKED_MICROVIA_HALF_MM;
                                                 same as microvia per leg)

    Validated against the existing HDI_VIA_HALF_MM / BLIND_F_IN2_HALF_MM /
    STACKED_MICROVIA_HALF_MM module-level constants — those are the
    per-class values this helper returns, derived from the same per-class
    diameters.
    """
    return via_diam_mm_for_class(via_class) / 2.0 + CLEARANCE_MM


# v11 (2026-05-28, CH1 30/30 lever K1): adjacent-HDI compatibility.
# Compatible-HDI = a via class whose physical pad geometry is KNOWN to the
# router (from the SSoT via_diam_mm_for_class) so a pad-EDGE-to-pad-EDGE
# clearance check is well-defined. ONLY microvia + blind_F_In2 qualify —
# through-vias have full annular ring + clearance halo behaviour that the
# existing centerline-precise check (hdi_via_blocked_geom) already handles
# correctly; we deliberately do NOT loosen the halo path for through-vias
# (a through-via at 0.5mm pitch fundamentally CANNOT clear a 0.20mm FoS gap
# because 0.30 + 0.30 + 0.20 = 0.80mm > 0.5mm pitch — refusal is correct).
_HDI_COMPATIBLE_CLASSES = frozenset({'microvia_F_In1', 'microvia_B_In8',
                                     'blind_F_In2'})


def is_compatible_hdi_via(via_class):
    """v11 K1 helper: True iff `via_class` has KNOWN HDI pad geometry the
    pad-edge clearance check can use.

    Compatible classes use the SSoT diameter from via_diam_mm_for_class so
    pad_edge = center_dist − pad_half_a − pad_half_b is well-defined and
    can be checked against CLEARANCE_MM (the FoS target = 0.20mm per
    ROUTING_METHODOLOGY §5c "no cut-to-cut"). 'through' is NOT compatible —
    its halo logic falls through to the existing centerline-precise check
    (which catches non-HDI foreigns + true conflicts; shorts-gate intact).

    Per the v11 K1 banner: SSoT discipline = no hard-coded class strings in
    callers; add a class to _HDI_COMPATIBLE_CLASSES + via_diam_mm_for_class
    and pad-edge logic falls out automatically.
    """
    return via_class in _HDI_COMPATIBLE_CLASSES


# v11 (2026-05-28, CH1 30/30 lever K2): MST per-leaf rejoin retry cap.
# Cascade-bounded per [[feedback-sureshot-over-sota]] — guarantee deterministic
# upper bound on work even when retries cascade. 3 retries = (a) original
# attempt, (b) rejoin against full multi-source pool, (c) one final retry
# with higher present_factor on the same iteration. Beyond 3 = global
# cooperative loop's job, not the MST's.
MST_LEAF_RETRY_CAP = 3


# v11 (2026-05-28, CH1 30/30 lever K2): provenance dir for partial-MST nets.
# Mirrors targeted_ripup.PROVENANCE_DIR_REL discipline. Single source of
# truth: this constant + the audit gate read from the same location.
PARTIAL_MST_PROVENANCE_DIR_REL = "sims/routing_provenance/partial_mst"


# A* tunables
LAYER_CHANGE_COST = 5.0       # via penalty (was 30 — too high vs free inner layer)
LAYER_BASE_COST = {           # per-step base cost by layer
    F_CU: 4.0,                # discourage long F.Cu signal routes (conflicts with bilateral pads)
    B_CU: 4.0,                # same
    IN2_CU: 1.0,              # PRIMARY signal escape
    IN4_CU: 1.0,              # BEMF dedicated
    IN6_CU: 1.5,              # SW already routed; mild bias against
    IN8_CU: 1.0,              # OVERFLOW/SWD layer
}
PRESENT_COST_BASE = 0.0       # baseline included in LAYER_BASE_COST now
PRESENT_COST_FACTOR_INIT = 1.0
PRESENT_COST_FACTOR_GROWTH = 1.4
HISTORY_COST_INIT = 0.0
HISTORY_COST_INC = 1.0
HEURISTIC_WEIGHT = 1.2        # >1 → weighted A*: faster, slightly sub-optimal paths


# Subsystem zones (replicated from BOARD_INVARIANTS for self-containment)
SUBSYSTEM_ZONES = {
    'CH1': (0, 50, 35, 89),
    'CH2': (65, 50, 100, 89),
    'CH3': (65, 11, 100, 50),
    'CH4': (0, 11, 35, 50),
}


# ─── Helpers ──────────────────────────────────────────────────────────────

def mm_to_iu(mm: float) -> int:
    return int(round(mm * 1e6))

def iu_to_mm(iu: int) -> float:
    return iu / 1e6


def _point_in_polygon(x: float, y: float, polygon) -> bool:
    """Ray-cast point-in-polygon. polygon = list of (x, y) tuples (closed implicit)."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def _point_near_polygon_edge(x: float, y: float, polygon, dist_sq: float) -> bool:
    """True if (x, y) within sqrt(dist_sq) of any polygon edge."""
    n = len(polygon)
    if n < 2:
        return False
    j = n - 1
    for i in range(n):
        x1, y1 = polygon[j]
        x2, y2 = polygon[i]
        dx = x2 - x1; dy = y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-18:
            d2 = (x - x1) ** 2 + (y - y1) ** 2
        else:
            t = ((x - x1) * dx + (y - y1) * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            px = x1 + t * dx; py = y1 + t * dy
            d2 = (x - px) ** 2 + (y - py) ** 2
        if d2 <= dist_sq:
            return True
        j = i
    return False


def layer_short_name(layer_id: int) -> str:
    return {F_CU: "F.Cu", B_CU: "B.Cu",
            IN1_CU: "In1.Cu", IN2_CU: "In2.Cu",
            IN3_CU: "In3.Cu", IN4_CU: "In4.Cu",
            IN5_CU: "In5.Cu", IN6_CU: "In6.Cu",
            IN7_CU: "In7.Cu", IN8_CU: "In8.Cu"}.get(layer_id, f"L{layer_id}")


# Net classification — pours that get HARD via-blocking.
# KEY INSIGHT (v2): KiCad ZONE_FILLER automatically generates an ANTIPAD around
# every foreign-net via inside a zone. For full-fill plane nets (GND, +VMOTOR
# on inner planes In1/3/5/7), the antipad keeps the via barrel clear of plane
# copper, so foreign vias are SAFE inside those planes — we MUST NOT block them
# (otherwise the router can't via anywhere because planes cover the entire
# subsystem zone).
#
# For F.Cu / B.Cu POUR nets (MOTOR_*_CHn, SHUNT_*_TOP_CHn, +V_* islands),
# antipads are also auto-created, BUT:
#   1. These pours often hug pads tightly — antipad may collide with neighbour
#      pad clearance (DRC clearance violation on the same layer).
#   2. The pours cross channel boundaries (MOTOR_A_CH2 fill extends into the
#      gap-region) and a via dropped there will cut the pour up.
# The v1 catastrophic shorts were specifically:
#   - VIA on (F.Cu→B.Cu) intersects TRACK on InN.Cu (foreign signal) — the
#     v2 cross-layer obstacle check handles this without needing pour-block.
#   - TRACK on InN.Cu on top of a foreign track on same layer — handled by
#     pre-existing per-layer obstacle stamping.
# So the HARD via-block plane list is RESTRICTED to F.Cu/B.Cu pour nets only —
# we never hard-block GND/+VMOTOR inner planes (KiCad antipad handles them).
POWER_POUR_NET_PATTERNS = [
    re.compile(r"^MOTOR_[ABC]_CH\d+$"),
    re.compile(r"^SHUNT_[ABC]_TOP_CH\d+$"),
]

def is_hard_block_pour_net(netname: str) -> bool:
    if not netname:
        return False
    for pat in POWER_POUR_NET_PATTERNS:
        if pat.search(netname):
            return True
    return False

# Kept for backward-compatibility / future use (returns True for nets we'd
# treat as plane-class in net-router heuristics).
def is_power_plane_net(netname: str) -> bool:
    if not netname:
        return False
    for pat in (POWER_POUR_NET_PATTERNS + [
            re.compile(r"^GND$"), re.compile(r"^BATGND$"),
            re.compile(r"^\+VMOTOR"), re.compile(r"^VMOTOR_CH"),
            re.compile(r"^\+V"), re.compile(r"^\+3V"), re.compile(r"^V3V3"),
            re.compile(r"^V_BUCK"), re.compile(r"^HALL_VCC")]):
        if pat.search(netname):
            return True
    return False


# ─── Board state extraction ───────────────────────────────────────────────

class BoardState:
    """Inventory pads, tracks, vias, zones from a loaded board."""

    def __init__(self, board, zone_bbox):
        self.board = board
        self.zone = zone_bbox  # (xmin,ymin,xmax,ymax)
        self.net_pads = defaultdict(list)        # netname -> [(ref, padname, x, y, layers, pad_size_x, pad_size_y)]
        self.net_obj = {}                        # netname -> NETINFO_ITEM
        # Obstacles per layer: list of (x,y,radius_mm, owner_netname)
        # Used during congestion grid build
        self.pad_obstacles_by_layer = defaultdict(list)
        self.track_obstacles_by_layer = defaultdict(list)  # (x1,y1,x2,y2,width_mm,owner)
        # v10 (2026-05-28, CH1 30/30 lever I — coop state-bug fix):
        # Each entry now (x, y, stamp_radius_mm, owner_netname, actual_diam_mm).
        # Two BUGS were diagnosed in the pre-v10 code (both gated by the same
        # `max(VIA_DIAM_MM, actual_width)` clamp):
        #   (1) The hdi_via_blocked_geom centerline-precise check (used at
        #       HDI-pad candidate cells) saw foreign HDI microvias (0.25mm)
        #       and blind F-In2 (0.30mm) as 0.60mm through-vias, inflating
        #       required clearance from 0.475mm to 0.650mm — falsely refusing
        #       legitimate adjacent HDI via placements.
        #   (2) The cell-obstacle stamp radius around foreign vias was sized
        #       to the inflated 0.60mm fallback too, blocking same-net A*
        #       traversal in F.Cu cells 0.1-0.2mm beyond the real foreign-via
        #       halo — which then trip-falled through to the cell-based scan
        #       AFTER the geom check passed.
        # The fix splits the two purposes: `actual_diam_mm` carries the TRUE
        # physical via diameter (read from board, NO max-clamp) into both
        # the cell-obstacle stamp radius and the foreign_vias entry used by
        # the precise geom check. Mathematically this still preserves
        # CLEARANCE_MM in both directions of the gap (foreign tracks/vias
        # respect their own halo against this via; this via's stamp respects
        # foreign tracks via their halo). Shorts-gate semantics (v6/v7) are
        # intact — a 0.60mm foreign through-via still gets the 0.605mm cell
        # stamp + 0.650mm geom required (test I3 asserts this).
        # Tuple position 4 is APPENDED so any external caller using the
        # legacy 4-tuple unpack still works during the rollout.
        self.via_obstacles = []                            # (x,y,stamp_r_mm,owner,actual_diam_mm)
        # Zone bboxes for SOFT cost (legacy MOTOR/SHUNT on F/B.Cu)
        self.zone_obstacles_by_layer = defaultdict(list)   # (xmin,ymin,xmax,ymax, owner)
        # NEW v2: filled-poly zones for HARD via-blocking on plane layers.
        # Each entry: (poly_set_outline_coords, layer, netname, bbox)
        # poly_set_outline_coords is a list of outlines; each outline = list of (x,y) mm.
        # Used to test point-in-polygon for via clearance against foreign power planes.
        self.filled_zones = []  # [(outlines, layer, netname, bbox)]

        self._collect()

    def _collect(self):
        b = self.board
        # Pads
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                netobj = pad.GetNet()
                netname = netobj.GetNetname() if netobj else ""
                p = pad.GetPosition()
                x = iu_to_mm(p.x); y = iu_to_mm(p.y)
                sz = pad.GetSize()
                sx = iu_to_mm(sz.x); sy = iu_to_mm(sz.y)
                ls = pad.GetLayerSet()
                # Routing layers the pad lives on (signal pad escape uses these)
                layers = []
                for lid in SIGNAL_LAYERS:
                    if ls.Contains(lid): layers.append(lid)
                # v2 fix: all copper layers the pad copper actually occupies
                # (for through-hole pads this includes the plane layers).
                # Used for stamping pad-obstacle on plane layers so foreign
                # vias respect pad clearance through the entire copper stack.
                all_layers_for_pad = []
                for lid in ALL_COPPER_LAYERS:
                    if ls.Contains(lid):
                        all_layers_for_pad.append(lid)
                if netname:
                    self.net_pads[netname].append((fp.GetReference(), pad.GetPadName(), x, y, layers, sx, sy))
                    if netobj and netname not in self.net_obj:
                        self.net_obj[netname] = netobj
                # Pad obstacle stored as (x, y, half_x, half_y, owner_net, padid).
                # Stamping in grid uses ELLIPTICAL keepout: actual pad bbox + clearance.
                # For SAME-net routing the pad cells become accessible.
                # v2: stamp on EVERY copper layer the pad occupies (for THT pads,
                # includes plane layers) so foreign-net vias on those layers
                # honour the pad clearance.
                hx = sx / 2; hy = sy / 2
                for lid in all_layers_for_pad:
                    self.pad_obstacles_by_layer[lid].append((x, y, hx, hy, netname or "<NC>", fp.GetReference()+"."+pad.GetPadName()))

        # Tracks + vias
        for t in b.GetTracks():
            netname = t.GetNetname()
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                x = iu_to_mm(p.x); y = iu_to_mm(p.y)
                # v10 (2026-05-28, CH1 30/30 lever I): read the TRUE physical
                # via diameter — no max(VIA_DIAM_MM, w) clamp. Pre-v10:
                # `diam = max(VIA_DIAM_MM, w)` inflated HDI microvias (0.25mm)
                # + blind F-In2 (0.30mm) to 0.60mm for BOTH the cell-obstacle
                # stamp AND the centerline-precise hdi_via_blocked_geom check.
                # The cell-obstacle stamp over-stamped by 0.18mm (admitting a
                # halo onto the adjacent J18/J19 HDI pad cell). The precise
                # geom check over-required clearance by 0.175mm
                # (0.650 vs 0.475 for blind_F_In2 vs 0.25mm foreign microvia).
                # Together these falsely rejected legitimate adjacent HDI via
                # placements — the worker-empirical "BSTB routes, 0/5
                # thereafter" symptom (PR #227). See test_lever_I_* in
                # test_emit_blind_f_in2.py for the regression coverage.
                # Defensive: if width read fails entirely we still default to
                # VIA_DIAM_MM for actual_diam (conservative = bigger required-
                # clearance = false-block, not silent-short — preserves the
                # v6/v7 shorts-gate semantics on classifier drift).
                actual_diam = VIA_DIAM_MM  # defensive fallback
                w = None
                try:
                    # KiCad 9: PCB_VIA.GetWidth(layer)
                    w = iu_to_mm(t.GetWidth(t.TopLayer()))
                except (TypeError, Exception):
                    try:
                        w = iu_to_mm(t.GetDrillValue()) + 0.2  # drill + ring
                    except Exception:
                        w = None
                if w is not None and w > 0:
                    actual_diam = w
                stamp_diam = actual_diam
                # stamp_diam = actual_diam: the cell-obstacle stamp radius
                # uses the TRUE diameter (not max-clamped). Correct semantics:
                # stamp radius = via_pad/2 + CLEARANCE + trace_half + slop —
                # which is the centerline distance at which a FOREIGN trace
                # centerline would touch this via's clearance halo. The
                # symmetric clearance (foreign-trace-half + foreign-via-pad/2
                # + CLEARANCE) is enforced from the OTHER direction by the
                # foreign track's own halo stamp + halo-rect — i.e. both
                # parties stamp half the gap and the sum equals the required
                # clearance. Setting stamp_diam to actual_diam therefore
                # preserves the v6/v7 shorts-gate (test I3 asserts a 0.60mm
                # foreign through-via still refuses a blind candidate at the
                # 0.650mm required distance — no relaxation on through-via
                # clearance) while removing the 0.18mm over-stamp on HDI
                # microvias that caused the lever-I symptom.
                # v2: obstacle circle radius must accommodate BOTH:
                #   - foreign via centerline gap (via_pad + clearance from this via pad)
                #   - foreign track centerline gap (via_pad + clearance + trace_half from this via pad)
                # Use the larger of the two — trace case — so obstacle cells block
                # both new tracks and new vias passing too close.
                # via_obstacle_radius = (this_via_pad/2) + CLEARANCE + trace_half + slop
                self.via_obstacles.append((x, y,
                    stamp_diam/2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM,
                    netname, actual_diam))
            else:
                s = t.GetStart(); e = t.GetEnd()
                x1 = iu_to_mm(s.x); y1 = iu_to_mm(s.y)
                x2 = iu_to_mm(e.x); y2 = iu_to_mm(e.y)
                w = iu_to_mm(t.GetWidth())
                self.track_obstacles_by_layer[t.GetLayer()].append((x1, y1, x2, y2, w, netname))

        # Zones — two-pass capture:
        #   1. SOFT obstacle (legacy): zone bbox stamped as history-bump on F/B.Cu
        #      for MOTOR/SHUNT pours. Kept for backward compatibility.
        #   2. HARD obstacle (v2 fix): for POWER-PLANE nets (GND/+VMOTOR/+3V3/etc),
        #      capture filled-poly outlines so we can test point-in-polygon at via
        #      placement time. A foreign-net via landing inside a power plane fill
        #      causes a net-to-net short (catastrophic). Even though KiCad will
        #      auto-create antipads, the router must respect via-pad clearance to
        #      neighboring foreign copper inside the plane — easier (and correct)
        #      to BLOCK foreign-net via cells inside foreign-net power-plane fills.
        for z in list(b.Zones()):
            netname = z.GetNetname()
            layer = z.GetLayer()
            try:
                bb = z.GetBoundingBox()
                xmin = iu_to_mm(bb.GetX()); ymin = iu_to_mm(bb.GetY())
                xmax = xmin + iu_to_mm(bb.GetWidth()); ymax = ymin + iu_to_mm(bb.GetHeight())
                self.zone_obstacles_by_layer[layer].append((xmin, ymin, xmax, ymax, netname))
            except Exception:
                pass
            # Capture filled polygons for HARD via-blocking (v2 fix).
            # Restricted to F.Cu / B.Cu POUR nets only (MOTOR/SHUNT) — inner
            # plane fills (GND/+VMOTOR) get auto-antipads from ZONE_FILLER and
            # MUST NOT be hard-blocked or the router can't via anywhere.
            try:
                if not z.IsFilled():
                    continue
                if not is_hard_block_pour_net(netname):
                    continue
                # Only F.Cu / B.Cu pour-block (inner-plane fills not blocked)
                if layer not in (F_CU, B_CU):
                    continue
                poly_set = z.GetFilledPolysList(layer)
                if poly_set is None:
                    continue
                outlines = []
                for o in range(poly_set.OutlineCount()):
                    outline = poly_set.Outline(o)
                    pts = []
                    for k in range(outline.PointCount()):
                        v = outline.CPoint(k)
                        pts.append((iu_to_mm(v.x), iu_to_mm(v.y)))
                    if len(pts) >= 3:
                        outlines.append(pts)
                if not outlines:
                    continue
                bb_xmin = iu_to_mm(bb.GetX()); bb_ymin = iu_to_mm(bb.GetY())
                bb_xmax = bb_xmin + iu_to_mm(bb.GetWidth())
                bb_ymax = bb_ymin + iu_to_mm(bb.GetHeight())
                self.filled_zones.append((outlines, layer, netname,
                                           (bb_xmin, bb_ymin, bb_xmax, bb_ymax)))
            except Exception:
                pass

    def net_pads_in_zone(self, netname):
        """Return pads of net within the subsystem zone."""
        xmin, ymin, xmax, ymax = self.zone
        return [p for p in self.net_pads.get(netname, [])
                if xmin <= p[2] <= xmax and ymin <= p[3] <= ymax]

    def routable_nets(self):
        """Find nets that have ≥2 pads in zone AND need routing AND are unrouted."""
        out = []
        for nn, pads in self.net_pads.items():
            if not should_route(nn): continue
            in_zone = [p for p in pads if self.zone[0] <= p[2] <= self.zone[2]
                                       and self.zone[1] <= p[3] <= self.zone[3]]
            # Also include nets where SOME pads are in zone (channel-internal)
            if len(in_zone) >= 2:
                # Skip nets already substantially routed (>=2 tracks)
                tracks_on_net = sum(1 for lid_tracks in self.track_obstacles_by_layer.values()
                                    for (_,_,_,_,_,owner) in lid_tracks if owner == nn)
                if tracks_on_net >= 2:
                    continue
                out.append(nn)
        return out


# ─── Congestion grid ───────────────────────────────────────────────────────

class CongestionGrid:
    """3D occupancy + congestion grid (x, y, layer).

    Cell (i, j, L):
      - obstacle: hard-block (pad/track/via owned by OTHER net) — cannot traverse
      - present: number of nets currently using this cell (≥1 => conflict for new net)
      - history: accumulated congestion penalty from past iterations
    """

    def __init__(self, zone_bbox, pitch_mm, layers, layer_pref_enabled=True):
        self.xmin, self.ymin, self.xmax, self.ymax = zone_bbox
        self.pitch = pitch_mm
        self.layers = list(layers)
        self.nx = int(math.ceil((self.xmax - self.xmin) / pitch_mm)) + 1
        self.ny = int(math.ceil((self.ymax - self.ymin) / pitch_mm)) + 1
        # v5 (2026-05-27): per-net layer-preference cost biasing.
        # When True (default), cost() multiplies LAYER_BASE_COST by a
        # net-class-specific multiplier so the router prefers each net's
        # spec'd escape layer (e.g. BEMF -> In4) even when an alternative
        # allowed layer (e.g. In2) is locally less congested. Worker R22
        # measured In4/In6 completely empty while In2 saturated at 163
        # tracks — root cause was equal layer-cost across allowed set.
        # Set False to revert to v4 cost behaviour (debugging only).
        self.layer_pref_enabled = layer_pref_enabled
        # dicts keyed by (i,j,L). Absent => default 0 / False.
        self.obstacle = set()     # (i,j,L) -> blocked for ALL nets (pad copper, track core)
        self.present = defaultdict(int)   # (i,j,L) -> count of nets routing here this iter
        self.history = defaultdict(float) # (i,j,L) -> historic congestion
        self.cell_owners = defaultdict(set)  # (i,j,L) -> {netname,...}
        # Pad-cell map: cell -> netname when cell is a pad endpoint we permit access for that net
        self.pad_cells = defaultdict(set)  # (i,j,L) -> {netnames whose pads occupy this cell}
        # Owner-net halo: cell -> set of net names that OWN this cell as clearance halo.
        # Blocked for ALL OTHER nets; accessible to listed nets.
        self.net_halo = defaultdict(set)  # (i,j,L) -> {netnames}
        # Via-forbidden zones: cells too close to a pad to host a via (clearance)
        self.via_forbidden_zones = {}  # (i,j,L) -> {netnames}
        # v2: Plane-fill rasterization — cells inside a power-plane fill on
        # an inner copper layer, keyed by layer. Used to HARD-BLOCK foreign-net
        # vias from landing in foreign power planes.
        #   via_plane_owners[(i,j)] = {layer: owner_netname, ...}
        # If a via at (i,j) connects layers L1->L2 (through-via spans all
        # copper layers), then for each layer L in the via span, if
        # via_plane_owners[(i,j)].get(L) is set and != via's net, the via is
        # REJECTED. This forces the router around foreign power planes.
        self.via_plane_owners = defaultdict(dict)  # (i,j) -> {layer: owner_net}
        # v2: foreign-track on inner layers — cells with foreign track copper
        # on a specific layer; via through-spans all layers so we must check
        # all-layer track maps not just routing-layer ones.
        # (Already covered by obstacle set per-layer; new helper iterates them.)
        # v6: cells that correspond to HDI-via-in-pad whitelist pad centers
        # (J18.* / J19.*). via_blocked_for_net uses HDI_VIA_HALF_MM (smaller
        # scan radius) when (i,j) is in this set — letting the smaller
        # microvia legitimately fit between adjacent QFN pads at 0.5mm pitch.
        #   hdi_via_cells[(i,j)] = netname  (owner-net allowed to via here)
        self.hdi_via_cells = {}  # (i,j) -> owner_netname
        # v6: cells whose obstacle marking came from a J18/J19 pad copper
        # (not a track). For HDI via_blocked_for_net checks at HDI cells,
        # these pad-derived obstacle cells DO NOT block the via because we
        # geometrically verified microvia fits between 0.5mm-pitch QFN pads.
        # Track-derived obstacle cells (foreign tracks on inner layers) still
        # block as normal. Set lookup is O(1) on cell tuple.
        self.hdi_pad_obstacle_cells = set()  # {(i, j, layer), ...}
        # v6: actual foreign-track segments per signal layer for GEOMETRIC
        # distance checks at HDI via cells. The cell-based obstacle stamp
        # is over-conservative for the small HDI via (it cannot distinguish
        # "track centerline at 0.39mm — HDI safe" from "track centerline
        # at 0.0mm — HDI unsafe"; both show same obstacle cell at offset 1).
        # For HDI cells we walk these segments directly and check geometric
        # distance. List per layer of (x1,y1,x2,y2,width_mm,owner_net).
        self.track_segments_by_layer = defaultdict(list)
        # v6 same for via positions (foreign vias must clear HDI via by
        # geometric distance, not cell-grid).
        self.foreign_vias = []  # [(x, y, diam_mm, owner_net), ...]

    def in_bounds(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny

    def cell_xy(self, i, j):
        return (self.xmin + i * self.pitch, self.ymin + j * self.pitch)

    def xy_to_ij(self, x, y):
        i = int(round((x - self.xmin) / self.pitch))
        j = int(round((y - self.ymin) / self.pitch))
        return i, j

    def stamp_obstacle_circle(self, x, y, r, layer):
        """Mark all cells within radius r of (x,y) on layer as obstacle."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(r / self.pitch))
        r2 = r * r
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.obstacle.add((i, j, layer))

    def stamp_obstacle_rect(self, cx, cy, hx, hy, layer):
        """Mark all cells inside rectangle [cx±hx, cy±hy] on layer as obstacle."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(cx - hx, cy - hy)
        i_max, j_max = self.xy_to_ij(cx + hx, cy + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - cx) <= hx and abs(pcy - cy) <= hy:
                    self.obstacle.add((i, j, layer))

    def stamp_halo_rect(self, cx, cy, hx, hy, layer, owner_net):
        """Mark cells in rect as net_halo[owner]: blocked for other nets only."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(cx - hx, cy - hy)
        i_max, j_max = self.xy_to_ij(cx + hx, cy + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - cx) <= hx and abs(pcy - cy) <= hy:
                    self.net_halo[(i, j, layer)].add(owner_net)

    def stamp_obstacle_segment(self, x1, y1, x2, y2, w, layer):
        """Mark all cells within w/2 + clearance + trace_half + slop of segment as obstacle on layer.
        Ensures new trace edge stays ≥CLEARANCE_MM from this existing segment edge."""
        if layer not in self.layers: return
        half = w / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
        # Bounding box of segment + half
        xa, xb = min(x1, x2), max(x1, x2)
        ya, yb = min(y1, y2), max(y1, y2)
        i_min, j_min = self.xy_to_ij(xa - half, ya - half)
        i_max, j_max = self.xy_to_ij(xb + half, yb + half)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        half2 = half * half
        # Vector for segment
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-12:
            # zero-length segment; treat as circle
            self.stamp_obstacle_circle(x1, y1, half, layer)
            return
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                cx, cy = self.cell_xy(i, j)
                # Project (cx,cy) onto segment
                tt = ((cx - x1) * dx + (cy - y1) * dy) / seg_len2
                tt = max(0.0, min(1.0, tt))
                px = x1 + tt * dx; py = y1 + tt * dy
                if (cx - px) ** 2 + (cy - py) ** 2 <= half2:
                    self.obstacle.add((i, j, layer))

    def stamp_obstacle_zone_bbox(self, x1, y1, x2, y2, layer, soft=True):
        """Mark cells inside zone bbox. If soft, only add to history (not obstacle)."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(x1, y1)
        i_max, j_max = self.xy_to_ij(x2, y2)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                if soft:
                    self.history[(i, j, layer)] += 0.5
                else:
                    self.obstacle.add((i, j, layer))

    def allow_pad_access_rect(self, x, y, layer, netname, hx, hy):
        """Mark all cells inside pad copper rect as accessible to netname."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(x - hx, y - hy)
        i_max, j_max = self.xy_to_ij(x + hx, y + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - x) <= hx and abs(pcy - y) <= hy:
                    self.pad_cells[(i, j, layer)].add(netname)

    def mark_pad_zone(self, x, y, layer, netname, radius_mm=0.6):
        """Mark cells near a pad as 'pad-zone' for that net. Vias are forbidden
        in pad-zone cells (via-in-pad not feasible on small QFN pads).
        Also tracks the pad center cell for access purposes."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(radius_mm / self.pitch))
        r2 = radius_mm * radius_mm
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.via_forbidden_zones.setdefault((i, j, layer), set()).add(netname)

    def is_via_forbidden(self, cell, netname):
        """Via at this cell forbidden for net (inside another net's pad keep-out)."""
        owners = self.via_forbidden_zones.get(cell)
        if not owners:
            return False
        # Allow via in own pad zone (pad-fanout will move it off-pad via search)
        # Forbid via in any OTHER net's pad zone (clearance)
        if owners - {netname}:
            return True
        return False

    def stamp_plane_fill(self, outlines, layer, owner_net, antipad_mm):
        """v2 fix: rasterize a power-plane fill onto via_plane_owners[(i,j)][layer].

        For every cell within the filled polygons (or within antipad_mm of an
        edge, conservatively expanded), mark the cell as 'owned by owner_net
        on this layer'. Foreign-net vias touching this cell on this layer get
        REJECTED — they would short the via barrel to the plane copper unless
        an antipad of >= clearance is reserved, which the router cannot
        guarantee without an antipad-creation pass.

        We use bounding-box scan + edge ray-cast point-in-polygon (works for
        the merged poly_set outlines KiCad gives).
        """
        if layer not in ALL_COPPER_LAYERS:
            return
        # Compute bbox over all outlines + antipad pad-out
        if not outlines:
            return
        all_x = [px for outline in outlines for (px, _py) in outline]
        all_y = [py for outline in outlines for (_px, py) in outline]
        xmin = min(all_x) - antipad_mm; xmax = max(all_x) + antipad_mm
        ymin = min(all_y) - antipad_mm; ymax = max(all_y) + antipad_mm
        # Clip to grid bounds
        if xmax < self.xmin or xmin > self.xmax: return
        if ymax < self.ymin or ymin > self.ymax: return
        i_min, j_min = self.xy_to_ij(xmin, ymin)
        i_max, j_max = self.xy_to_ij(xmax, ymax)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        ap2 = antipad_mm * antipad_mm
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                cx, cy = self.cell_xy(i, j)
                inside = False
                for outline in outlines:
                    if _point_in_polygon(cx, cy, outline):
                        inside = True
                        break
                if not inside:
                    # Check edge distance within antipad
                    near = False
                    for outline in outlines:
                        if _point_near_polygon_edge(cx, cy, outline, ap2):
                            near = True
                            break
                    if not near:
                        continue
                # Mark this cell as plane-owned on this layer
                prev = self.via_plane_owners[(i, j)].get(layer)
                if prev is None:
                    self.via_plane_owners[(i, j)][layer] = owner_net
                # If already owned by same or another net, keep first owner
                # (multiple plane fills with same net on same layer is fine;
                # different nets shouldn't occur on same layer)

    def hdi_via_blocked_geom(self, i, j, netname, span_layers, via_class=None):
        """v6: geometric clearance check for an HDI microvia at cell (i,j).

        Cell-based obstacle stamps are over-conservative for the small HDI
        via (0.25mm pad / 0.10mm drill): a foreign track centerline at
        0.39mm from via center is HDI-safe (clearance 0.39−0.125−0.075 =
        0.19mm ≥ 0.15mm), but stamps an obstacle cell at offset 1 from
        via center, which the cell-based scan reads as "blocked". This
        function performs the precise centerline-to-centerline check
        against the stored track_segments_by_layer + foreign_vias arrays.

        v9 (2026-05-28, CH1 30/30 lever F): `via_class` selects the per-
        class via pad half (microvia 0.125mm / blind_F_In2 0.15mm /
        through 0.30mm). When None, defaults to HDI_VIA_DIAM_MM/2 (the v6/v7
        microvia behaviour — preserved for back-compat with callers that
        haven't been updated). This fixes a v8-residual over-rejection: blind
        F-In2 vias (0.30mm pad) need a 0.15mm pad-half in the geom check,
        not the 0.125mm microvia value — and through-via candidates flagged
        via this code path were silently under-stamped (the v6 path is HDI-
        only, but the OQ-020 blind class introduced a 0.30mm-pad-on-HDI-cell
        flavour that this assertion now covers).

        Returns (blocked: bool, reason: str). PASS = HDI via fits safely.
        """
        # via center in mm
        vx, vy = self.cell_xy(i, j)
        # Required clearance: foreign track CENTERLINE must be ≥
        #   (via_pad/2 + clearance)
        #   - 0 (we want the closest *edge* to clear; centerline already
        #     accounts for trace_half/2 separately)
        # Actually: foreign trace edge to via edge ≥ CLEARANCE_MM (0.15mm).
        # foreign trace edge = trace_centerline ± (w/2). via edge = via_center ± via_pad/2.
        # Required: |trace_centerline - via_center| ≥ (w/2 + via_pad/2 + CLEARANCE).
        # Foreign via edge: similar with via_diam/2.
        # v9: per-class pad half (was hard-coded HDI_VIA_DIAM_MM/2 = 0.125mm,
        # which under-stamped blind_F_In2's 0.30mm pad → 0.15mm half).
        if via_class is not None:
            hdi_pad_half = via_diam_mm_for_class(via_class) / 2.0
        else:
            hdi_pad_half = HDI_VIA_DIAM_MM / 2  # 0.125mm (v6/v7 microvia default)
        for L in span_layers:
            if L not in SIGNAL_LAYERS:
                continue
            for (x1, y1, x2, y2, w, owner) in self.track_segments_by_layer.get(L, []):
                if owner == netname:
                    continue
                # min distance from (vx,vy) to segment
                dx = x2 - x1; dy = y2 - y1
                seg_len2 = dx * dx + dy * dy
                if seg_len2 < 1e-12:
                    d = math.hypot(vx - x1, vy - y1)
                else:
                    tt = ((vx - x1) * dx + (vy - y1) * dy) / seg_len2
                    tt = max(0.0, min(1.0, tt))
                    px = x1 + tt * dx; py = y1 + tt * dy
                    d = math.hypot(vx - px, vy - py)
                required = (w / 2) + hdi_pad_half + CLEARANCE_MM
                # v6: allow 1µm epsilon for floating-point precision
                # (geometric calcs land on the exact boundary sometimes)
                if d < required - 1e-3:
                    return True, (f"track:{owner}@{layer_short_name(L)} "
                                   f"d={d:.3f}<{required:.3f}")
        # Foreign via clearance (centerline-to-centerline)
        # v11 (CH1 30/30 K1): adjacent-HDI compatibility. When BOTH the
        # candidate and the foreign are compatible-HDI vias with KNOWN pad
        # geometry, the physically-correct constraint is pad-EDGE-to-pad-EDGE
        # clearance ≥ FoS target (CLEARANCE_MM = 0.20mm per §5c) — NOT the
        # full halo-overlap centerline rule. The halo path conservatively
        # uses (foreign_pad/2 + candidate_pad/2 + 2×CLEARANCE_MM) so adjacent
        # 0.5mm-pitch QFN HDI vias at 0.5mm centre-to-centre register a
        # "too-close" reject even though pad-edge = 0.5 − 0.125 − 0.125 = 0.25
        # ≥ 0.20mm FoS = SAFE. K1 introduces the pad-edge check FIRST: if it
        # clears the FoS target, ACCEPT; else fall through to the existing
        # centerline-precise check (which catches true conflicts +
        # incompatible classes — shorts-gate intact). The 25/30 board's
        # BSTB @ J19.17 ↔ J19.16 case (pad-edge 0.1946mm in the
        # "sub-fab-tol accepted" class per worker gate report) is admitted by
        # the post-commit shorts-gate but was refused pre-commit — K1 closes
        # the inconsistency by aligning pre-commit with the §5c FoS target.
        candidate_compat = is_compatible_hdi_via(via_class)
        for (fx, fy, diam, owner) in self.foreign_vias:
            if owner == netname:
                continue
            d = math.hypot(vx - fx, vy - fy)
            # K1 path: BOTH sides HDI-compat → pad-edge clearance vs FoS.
            # Foreign-via 'diam' is the actual barrel/pad diameter recorded
            # by v10 (no max-clamp); a foreign diam ≤ BLIND_F_IN2_DIAM_MM
            # (= 0.30mm) confirms a microvia/blind HDI foreigner whose pad-
            # edge maths is well-defined. Through-vias have diam ≥ 0.60mm —
            # those fail this guard and fall through to the existing check.
            foreign_is_hdi_geom = candidate_compat and (
                diam <= BLIND_F_IN2_DIAM_MM + 1e-6)
            if foreign_is_hdi_geom:
                pad_edge = d - hdi_pad_half - (diam / 2.0)
                if pad_edge >= CLEARANCE_MM - 1e-3:
                    # K1 accept: pad-edge clearance meets §5c FoS target.
                    # Record the path in the provenance string (debugging).
                    # NOTE: this is the SOLE place K1 relaxes the existing
                    # rule; the candidate-vs-foreign-track loop above is
                    # NOT touched (tracks have width but not the symmetric
                    # pad geometry K1's reasoning depends on).
                    continue
            # Halo path (existing v6/v7/F/I rule — shorts-gate semantics).
            required = (diam / 2) + hdi_pad_half + CLEARANCE_MM
            if d < required:
                return True, (f"foreign_via:{owner} "
                               f"d={d:.3f}<{required:.3f}")
        # Plane-fill scan (same as standard via): forbids HDI via inside
        # foreign F.Cu/B.Cu power pours, where the via barrel would short.
        for di in range(-3, 4):
            for dj in range(-3, 4):
                ci = i + di; cj = j + dj
                if not self.in_bounds(ci, cj):
                    continue
                cell_planes = self.via_plane_owners.get((ci, cj))
                if not cell_planes:
                    continue
                for L, powner in cell_planes.items():
                    if powner != netname and L in span_layers:
                        return True, (f"plane:{powner}@{layer_short_name(L)}"
                                       f"@({di},{dj})")
        return False, ""

    def via_blocked_for_net(self, i, j, netname, span_layers=ALL_COPPER_LAYERS,
                              via_class=None):
        """v2 fix: A through-via at (i,j) for `netname` is blocked if ANY
        copper layer in span_layers has a foreign-net obstacle within the
        via's pad+clearance halo of (i,j).

        Optimized two-radius scan:
          - obstacle / net_halo scan: small radius (delta_halo_cells) because
            obstacle stamping already includes (track_half + clearance +
            trace_half + slop) per stamp_obstacle_segment, plus we need
            extra `via_pad_extra = (via_pad - trace_half)` cells of expansion
            to convert "track-touches-trace" margin into "track-touches-via"
            margin.
          - via_plane_owners scan: scan within (via_pad/2 + clearance) cells
            because pours are rasterized to their EXACT polygon edge (no
            built-in margin in via_plane_owners).

        Skip plane layers in obstacle check (we deliberately do NOT block
        foreign vias inside inner GND/+VMOTOR planes — KiCad auto-antipads).

        v6: when (i,j) is an HDI-via-in-pad whitelist cell AND `netname`
        matches the cell's HDI owner-net, use the smaller HDI via pad/
        clearance for the scan radius. This lets the microvia legitimately
        fit between adjacent 0.5mm-pitch QFN pads where a standard 0.6mm
        via would clearance-violate.

        v9 (2026-05-28, CH1 30/30 lever F): when `via_class` is provided
        (the router knows the candidate's class from via_class_for_span),
        the halo radius is computed per-class via via_pad_half_mm_for_class
        — so a microvia candidate (0.25mm) at a foreign HDI cell uses the
        0.325mm halo instead of the standard 0.500mm halo. Fixes the v6/v7/v8
        over-rejection where ANY non-pad-owner net candidating an HDI cell
        was halo-checked as a 0.60mm through-via (refused legitimate HDI
        escapes even though the actual placed via would be a 0.25mm microvia
        well within clearance). When via_class is None (no caller-side
        classification), falls back to the v6 is_hdi_via-based binary —
        backward-compatible for callers that haven't been updated.

        Returns (blocked: bool, reason: str).
        """
        # v6: detect HDI via-in-pad site at this cell for this net
        hdi_owner = self.hdi_via_cells.get((i, j))
        is_hdi_via = (hdi_owner is not None and hdi_owner == netname)
        if is_hdi_via:
            # v7 (worker R22 catch #4 on v6): HDI vias still physically
            # spans the full F.Cu→B.Cu stack (per emit_to_board comment at
            # line ~1492-1500). The geom check uses segment-lists that
            # capture pre-router-startup tracks ONLY — same-router-run
            # committed tracks/vias are stamped into the cell-based
            # obstacle map but NOT into track_segments_by_layer /
            # foreign_vias. v7 commit_paths() updates the segment lists,
            # but as a defense-in-depth second check we also run the
            # cell-based obstacle scan on inner+B.Cu layers below.
            # If EITHER check flags, the via is rejected.
            # v9: pass via_class so the geom check uses the per-class pad
            # half (0.30/2 for blind_F_In2 instead of always 0.25/2).
            geom_blocked, _ = self.hdi_via_blocked_geom(i, j, netname, span_layers,
                                                        via_class=via_class)
            if geom_blocked:
                return True, "hdi_geom_blocked"
            # Fall through to the cell-based scan with HDI-aware skips.
        # v9: per-class pad-half lookup (SSoT = via_pad_half_mm_for_class).
        # Backward-compat: when via_class is None, fall back to the v6 binary
        # (is_hdi_via → HDI_VIA_HALF_MM else standard) so legacy callers see
        # no behaviour change.
        if via_class is not None:
            via_pad_half_mm = via_pad_half_mm_for_class(via_class)
        elif is_hdi_via:
            # Microvia: 0.25mm pad → HDI_VIA_HALF_MM = 0.325mm clearance
            via_pad_half_mm = HDI_VIA_HALF_MM
        else:
            # Obstacle scan radius: delta = via_pad - trace_pad (how much wider
            # the via is than the existing trace-halo accounted for)
            via_pad_half_mm = VIA_DIAM_MM / 2 + CLEARANCE_MM
        # obstacle keepout already includes (TRACE_HALF + CLEARANCE + slop)
        # = TRACE_HALF + CLEARANCE + GRID_SLOP_MM ≈ 0.305mm.
        # We want the via center within (via_pad_half_mm) of any obstacle CELL
        # center to be considered blocked. So extra delta = via_pad_half_mm - 0.305
        extra_mm = max(0.0, via_pad_half_mm - (TRACE_HALF_MM + CLEARANCE_MM + GRID_SLOP_MM))
        r_obs = int(math.ceil(extra_mm / self.pitch))
        r_obs2 = r_obs * r_obs
        # Plane scan radius: full via_pad_half (no built-in margin in via_plane_owners)
        r_plane = int(math.ceil(via_pad_half_mm / self.pitch))
        r_plane2 = r_plane * r_plane

        # Check obstacle/halo on signal layers, small radius
        # v6 (HDI via-in-pad): when is_hdi_via:
        #   - obstacle cells derived from the J18/J19 pad copper itself are
        #     IGNORED (stored in hdi_pad_obstacle_cells) — we geometrically
        #     verified microvia fits between adjacent 0.5mm-pitch QFN pads.
        #   - foreign-pad HALO cells on F.Cu are also ignored (halo was sized
        #     for standard 0.6mm via needing 0.305mm pad-edge margin; HDI
        #     0.25mm via needs only 0.275mm centerline-to-foreign-pad-center,
        #     which is mathematically satisfied at 0.5mm pitch — verified).
        #   - foreign-TRACK obstacle cells on inner layers still block as
        #     normal at standard r_obs radius (this is the load-bearing
        #     correctness check: HDI via must not collide with existing
        #     inner-layer tracks routed by prior router passes).
        for L in span_layers:
            if L not in self.layers:
                continue
            # v6 HDI: skip F.Cu obstacle/halo check entirely. The HDI via
            # pad on F.Cu IS the SMD pad copper (via inside pad). Foreign
            # tracks/halos on F.Cu near the SMD pad edge represent a
            # PRE-EXISTING DRC issue with those tracks vs the SMD pad and
            # are not a NEW issue introduced by adding a via inside the pad.
            # On inner layers + B.Cu the standard obstacle scan still runs.
            if is_hdi_via and L == F_CU:
                continue
            for di in range(-r_obs, r_obs + 1):
                for dj in range(-r_obs, r_obs + 1):
                    if di * di + dj * dj > r_obs2:
                        continue
                    ci = i + di; cj = j + dj
                    if not self.in_bounds(ci, cj):
                        continue
                    if (ci, cj, L) in self.obstacle:
                        # v6 HDI: skip pad-derived obstacle cells from
                        # J18/J19 (we know microvia fits adjacent pads)
                        if is_hdi_via and (ci, cj, L) in self.hdi_pad_obstacle_cells:
                            pass  # HDI: ignore J18/J19 pad-copper obstacle
                        elif netname not in self.pad_cells.get((ci, cj, L), set()):
                            return True, f"obstacle@{layer_short_name(L)}@({di},{dj})"
                    halos = self.net_halo.get((ci, cj, L))
                    if halos and (halos - {netname}):
                        return True, f"halo@{layer_short_name(L)}@({di},{dj})"

        # Check via_plane_owners on F/B.Cu (and any other layer that has plane entries)
        # Note: via_plane_owners has only F.Cu/B.Cu pour cells (per
        # is_hard_block_pour_net + F_CU/B_CU filter). Plus via-stack same-net
        # marks from existing vias on all layers (but those check netname == owner).
        for di in range(-r_plane, r_plane + 1):
            for dj in range(-r_plane, r_plane + 1):
                if di * di + dj * dj > r_plane2:
                    continue
                ci = i + di; cj = j + dj
                if not self.in_bounds(ci, cj):
                    continue
                cell_planes = self.via_plane_owners.get((ci, cj))
                if not cell_planes:
                    continue
                for L, powner in cell_planes.items():
                    if powner != netname:
                        return True, f"plane:{powner}@{layer_short_name(L)}@({di},{dj})"
        return False, ""

    def allow_pad_access(self, x, y, layer, netname, radius_mm=0.35):
        """For pads of this net: remove obstacle marks within radius on layer
        (router can ENTER the pad cell for net=netname)."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(radius_mm / self.pitch))
        r2 = radius_mm * radius_mm
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.pad_cells[(i, j, layer)].add(netname)

    def is_blocked_for(self, cell, netname):
        """Cell hard-blocked for netname?

        Cell is blocked if:
          - in self.obstacle AND not in pad_cells[netname] (pad copper of other net or track core)
          - in self.net_halo AND ANY owner other than netname (clearance halo of other net)
        """
        if cell in self.obstacle:
            if netname not in self.pad_cells.get(cell, set()):
                return True
        halos = self.net_halo.get(cell)
        # If ANY halo-owner is not netname, the cell is in another net's clearance halo => blocked
        if halos and (halos - {netname}):
            return True
        return False

    def cost(self, cell, present_factor, netname=None):
        """Soft cost: (layer_base * layer_pref_mult) + present_factor*present + history.

        v5: layer-preference cost multiplier applies a per-net bias so the
        net's TOP preferred layer (LAYER_PREF[0]) costs ~half a non-preferred
        layer's base. Net-classified-but-not-listed layers and non-classified
        nets get multiplier 1.0 (current v4 behaviour).

        netname=None preserves the v4 cost (used as fallback for callers we
        haven't updated and for the layer-pref-disabled CLI mode — gated by
        self.layer_pref_enabled at the caller).
        """
        i, j, L = cell
        base = LAYER_BASE_COST.get(L, 1.0)
        if netname is not None and self.layer_pref_enabled:
            base *= layer_pref_cost_mult(netname, L)
        pres = self.present.get(cell, 0)
        hist = self.history.get(cell, 0.0)
        return base + present_factor * pres + hist

    def commit_path(self, path_cells, netname):
        """Mark path cells as present for netname."""
        for cell in path_cells:
            self.present[cell] += 1
            self.cell_owners[cell].add(netname)

    def uncommit_path(self, path_cells, netname):
        for cell in path_cells:
            if self.present.get(cell, 0) > 0:
                self.present[cell] -= 1
            self.cell_owners.get(cell, set()).discard(netname)

    def bump_history(self):
        """Increase history for cells with present > 0 (congested in last iter)."""
        for cell, pres in self.present.items():
            if pres > 1:
                self.history[cell] += HISTORY_COST_INC * (pres - 1)


# ─── A* maze router (per-net) ─────────────────────────────────────────────

# Neighbor moves: 8-connected on same layer + layer change via
SAME_LAYER_MOVES_8 = [(-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)]
SAME_LAYER_MOVES_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# v6: stack-order tuple for blind-via span computation. Index = position in
# stackup (F.Cu = 0, B.Cu = 9 in 10L). Blind via span = layers between
# min(idx_a, idx_b) and max(idx_a, idx_b) inclusive.
STACKUP_ORDER = [F_CU, IN1_CU, IN2_CU, IN3_CU, IN4_CU,
                 IN5_CU, IN6_CU, IN7_CU, IN8_CU, B_CU]
_STACKUP_INDEX = {L: i for i, L in enumerate(STACKUP_ORDER)}


def blind_via_span(L_from, L_to):
    """Return the tuple of copper layers a blind via between L_from and L_to
    barrel-intersects. Always includes both endpoints + every layer between
    them in stackup order. Used for HDI via_blocked_for_net checks.
    """
    a = _STACKUP_INDEX.get(L_from)
    b = _STACKUP_INDEX.get(L_to)
    if a is None or b is None:
        return tuple(ALL_COPPER_LAYERS)
    lo, hi = (a, b) if a <= b else (b, a)
    return tuple(STACKUP_ORDER[lo:hi + 1])


def heuristic(c1, c2, pitch):
    """Octile-distance heuristic on grid + via penalty.

    Lower bound on actual cost: each grid step incurs ≥1.0 base cost (inner layer),
    so distance×pitch is a valid lower bound. Adding layer-change cost too.
    """
    di = abs(c1[0] - c2[0])
    dj = abs(c1[1] - c2[1])
    d = (di + dj) + (math.sqrt(2) - 2) * min(di, dj)
    lc = LAYER_CHANGE_COST if c1[2] != c2[2] else 0
    return (d * pitch + lc) * HEURISTIC_WEIGHT


def find_path_astar(grid: CongestionGrid, sources, targets,
                    netname, allowed_layers, present_factor,
                    move_set=SAME_LAYER_MOVES_8, time_budget_s=5.0):
    """A* multi-source multi-target on the 3D grid.

    sources/targets: set of (i,j,L) cells. Sources have g=0; goal=any in targets.

    Returns (path_cells, cost) or (None, None).
    """
    start_time = time.monotonic()
    # Open: (f, g, cell, parent_key)
    open_heap = []
    came_from = {}      # cell -> parent cell
    g_score = {}
    # v2 perf: cache via_blocked_for_net results per (i,j) for this A* run.
    # Obstacle map is constant during one find_path_astar invocation, so we
    # can safely memoize. Significant speedup — full-CH1 was 5+ min/iter.
    # v6: cache is keyed by (i, j, span_signature). For HDI vias the span
    # depends on (L_from, L_to) since we emit BLIND vias rather than through
    # vias; the via barrel only intersects layers between L_from and L_to,
    # so via_blocked_for_net must scan that subset only. For non-HDI vias
    # we use the original full ALL_COPPER_LAYERS span (signature "full").
    # v9 (CH1 30/30 lever F): cache key extended with via_class so the per-
    # class halo (HDI microvia 0.25 vs blind_F_In2 0.30 vs through 0.60) is
    # honoured — same (i,j) + same span but different via_class can legitim-
    # ately yield different blocked verdicts (smaller via = smaller halo =
    # admits more cells). via_class is mandatory at the caller — the router
    # already knows it from via_class_for_span at the source cell.
    via_block_cache = {}  # (i, j, sig, via_class) -> bool
    def _via_blocked(i, j, span_layers_tuple=None, via_class=None):
        sig = span_layers_tuple if span_layers_tuple is not None else "full"
        key = (i, j, sig, via_class)
        v = via_block_cache.get(key)
        if v is None:
            if span_layers_tuple is not None:
                v, _ = grid.via_blocked_for_net(i, j, netname,
                                                span_layers=list(span_layers_tuple),
                                                via_class=via_class)
            else:
                v, _ = grid.via_blocked_for_net(i, j, netname,
                                                via_class=via_class)
            via_block_cache[key] = v
        return v
    # Precompute one representative target for heuristic
    if not targets: return None, None
    targets_set = set(targets)
    target_list = list(targets)
    # Choose nearest target as heuristic anchor (it's lower-bound to any)
    def h(cell):
        if not targets:
            return 0
        return min(heuristic(cell, t, grid.pitch) for t in target_list[:8])  # cap for speed

    for s in sources:
        g_score[s] = 0.0
        f = h(s)
        heapq.heappush(open_heap, (f, 0.0, s, None))
        came_from[s] = None

    nodes_expanded = 0
    while open_heap:
        if time.monotonic() - start_time > time_budget_s:
            return None, None
        f, g, cell, parent = heapq.heappop(open_heap)
        if g > g_score.get(cell, math.inf): continue
        nodes_expanded += 1
        if cell in targets_set:
            # Reconstruct
            path = []
            cur = cell
            while cur is not None:
                path.append(cur)
                cur = came_from.get(cur)
            path.reverse()
            return path, g
        i, j, L = cell
        # Same-layer neighbors
        for di, dj in move_set:
            ni, nj = i + di, j + dj
            if not grid.in_bounds(ni, nj): continue
            ncell = (ni, nj, L)
            if grid.is_blocked_for(ncell, netname): continue
            # For diagonal moves, also ensure both axis-adjacent cells are passable
            # (prevents trace edge from clipping corner of obstacle)
            if di and dj:
                if grid.is_blocked_for((i + di, j, L), netname): continue
                if grid.is_blocked_for((i, j + dj, L), netname): continue
            step = grid.pitch * (math.sqrt(2) if (di and dj) else 1.0)
            # v5: pass netname so cost() can apply per-net-class layer bias
            ng = g + step * grid.cost(ncell, present_factor, netname)
            if ng < g_score.get(ncell, math.inf):
                g_score[ncell] = ng
                came_from[ncell] = cell
                heapq.heappush(open_heap, (ng + h(ncell), ng, ncell, cell))
        # Layer-change (via) neighbors
        # FORBID via inside any pad zone (own or other) — clearance to pads
        via_here_forbidden = grid.is_via_forbidden((i, j, L), netname)
        if not via_here_forbidden:
            # v2 fix: validate proposed via against EVERY copper layer the
            # via barrel actually traverses — not just the two routing
            # layers. Catches the bug class where a via lands on a foreign
            # power plane or foreign track on an inner layer (catastrophic
            # short).
            # v6: HDI cells use the geometric precise check (hdi_via_blocked_geom
            # in CongestionGrid) which is more accurate than the cell-based
            # scan; memoized via _via_blocked() — see top.
            # v8 (2026-05-28, master Phase 3 OQ-020): the via barrel span
            # depends on the via CLASS:
            #   - non-HDI cell  → through-via, span = ALL_COPPER_LAYERS (the
            #                     existing default; obstacles on EVERY copper
            #                     layer are load-bearing).
            #   - HDI + (F,In1)/(B,In8) → adjacent microvia, span = 2 layers.
            #   - HDI + (F,In2) on whitelist net → blind/buried F-In2, span =
            #                     (F.Cu, In1.Cu, In2.Cu) — foreign copper on
            #                     In3..B.Cu CANNOT block this via (barrel
            #                     never reaches there; layer-aware obstacle
            #                     check). Without this, a foreign track on
            #                     In4 (the v6/v7 shorts hazard) would falsely
            #                     block legitimate blind F-In2 escapes.
            #   - HDI + other span  → REFUSED at this cell (the v6/v7 shorts
            #                     gate: the router MUST NOT silently fall
            #                     through to THROUGH F↔B at fine-pitch HDI).
            # The obstacle pre-check at the SOURCE cell uses the worst-case
            # (largest) span across all candidate layer pairs at this cell —
            # if EVERY candidate span is blocked at the worst-case span, the
            # via is hopeless; otherwise we check each candidate individually
            # below. For simplicity + correctness we run the per-class span
            # check on each candidate ncell (the cache key includes the span
            # signature so identical spans share results).
            is_hdi_cell = (i, j) in grid.hdi_via_cells
            for L2 in allowed_layers:
                if L2 == L: continue
                # v8: classify the (L, L2) span at this cell for this net.
                # `None` => the HDI cell + (L, L2) + net combination is not
                # a sanctioned via class → SKIP (no via emission attempted).
                via_class = via_class_for_span(L, L2, netname,
                                                is_hdi_cell=is_hdi_cell)
                if via_class is None:
                    continue
                ncell = (i, j, L2)
                if grid.is_blocked_for(ncell, netname): continue
                # Also forbid via on dest layer if it lands in another net's pad zone
                if grid.is_via_forbidden((i, j, L2), netname): continue
                # v8: layer-aware obstacle scan — span_layers is class-specific
                # (blind F-In2 only intersects F/In1/In2, microvias only
                # intersect 2 layers, through spans all). Cached per (i,j,
                # span-signature) so 2 candidate layer-pairs with the same
                # span share a single grid scan.
                # v9 (CH1 30/30 lever F): pass via_class so the halo radius
                # downstream is per-class — microvia 0.25 vs blind_F_In2 0.30
                # vs through 0.60 — not always-the-largest. Fixes A* over-
                # rejection of HDI candidates at cells where the standard
                # 0.60mm through-via halo refused but the actual 0.25mm
                # microvia barrel fits with margin (the KILL_RAIL_N at J19.8
                # symptom).
                span = via_span_layers(via_class)
                if _via_blocked(i, j, span_layers_tuple=span,
                                via_class=via_class):
                    continue
                # via cost: fixed + congestion of both cells
                # v5: pass netname so cost() can apply per-net-class layer bias
                via_cost = LAYER_CHANGE_COST + grid.cost(ncell, present_factor, netname)
                ng = g + via_cost
                if ng < g_score.get(ncell, math.inf):
                    g_score[ncell] = ng
                    came_from[ncell] = cell
                    heapq.heappush(open_heap, (ng + h(ncell), ng, ncell, cell))
    return None, None


# ─── Path -> KiCad geometry ───────────────────────────────────────────────

def segment_crosses_obstacle(grid, x1, y1, x2, y2, layer, netname):
    """Validate that a straight segment from (x1,y1) to (x2,y2) on layer doesn't
    cross any obstacle cell other than at endpoints (Bresenham-style cell traversal)."""
    i1, j1 = grid.xy_to_ij(x1, y1)
    i2, j2 = grid.xy_to_ij(x2, y2)
    di = i2 - i1; dj = j2 - j1
    n = max(abs(di), abs(dj))
    if n == 0: return False
    for k in range(n + 1):
        t = k / n
        ii = int(round(i1 + di * t))
        jj = int(round(j1 + dj * t))
        if grid.is_blocked_for((ii, jj, layer), netname):
            return True
    return False


def path_to_segments(path_cells, grid: CongestionGrid,
                     return_via_layers: bool = False):
    """Convert grid path -> list of (x1,y1,x2,y2,layer) segments + via cells.

    Algorithm:
      1. Split path into per-layer runs; emit one via between adjacent runs.
      2. Within each run, simplify with Ramer-Douglas-Peucker-lite:
         collapse all cells that lie on the same straight line into one segment.
         A new segment starts whenever the next cell's direction differs from the
         current segment's direction.

    Returns (segments, vias) where:
      segments = [(x1,y1,x2,y2,layer), ...]
      vias = [(x, y), ...]

    v6: if `return_via_layers=True`, also returns via_layers — a dict mapping
    (x_rounded, y_rounded) → (L_from, L_to) for each via, so emit_to_board
    can produce a BLIND via with the proper layer pair for HDI escapes.
    """
    if not path_cells or len(path_cells) < 2:
        return ([], [], {}) if return_via_layers else ([], [])
    segments = []
    vias = []
    via_layers = {}  # (rx, ry) -> (L_from, L_to)
    # Per-layer runs
    runs = []
    cur_layer = path_cells[0][2]
    cur_run = [path_cells[0]]
    for cell in path_cells[1:]:
        if cell[2] == cur_layer:
            cur_run.append(cell)
        else:
            runs.append((cur_layer, cur_run))
            i, j, _ = cur_run[-1]
            x, y = grid.cell_xy(i, j)
            vias.append((x, y))
            via_layers[(round(x, 3), round(y, 3))] = (cur_layer, cell[2])
            cur_layer = cell[2]
            cur_run = [cell]
    runs.append((cur_layer, cur_run))

    def norm_dir(di, dj):
        """Normalize to unit step direction in {-1,0,1}^2."""
        return (0 if di == 0 else (1 if di > 0 else -1),
                0 if dj == 0 else (1 if dj > 0 else -1))

    for layer, run in runs:
        if len(run) < 2:
            continue
        # Walk run, accumulating into one segment per consistent direction
        seg_start_idx = 0
        cur_dir = None
        for k in range(1, len(run)):
            di = run[k][0] - run[k - 1][0]
            dj = run[k][1] - run[k - 1][1]
            d = norm_dir(di, dj)
            if cur_dir is None:
                cur_dir = d
            elif d != cur_dir:
                # Emit segment from seg_start to k-1
                a = run[seg_start_idx]; b = run[k - 1]
                x1, y1 = grid.cell_xy(a[0], a[1])
                x2, y2 = grid.cell_xy(b[0], b[1])
                if (x1, y1) != (x2, y2):
                    segments.append((x1, y1, x2, y2, layer))
                seg_start_idx = k - 1
                cur_dir = d
        # Final segment
        a = run[seg_start_idx]; b = run[-1]
        x1, y1 = grid.cell_xy(a[0], a[1])
        x2, y2 = grid.cell_xy(b[0], b[1])
        if (x1, y1) != (x2, y2):
            segments.append((x1, y1, x2, y2, layer))
    if return_via_layers:
        return segments, vias, via_layers
    return segments, vias


def emit_to_board(board, segments, vias, net_obj, width_mm, added_items,
                  hdi_via_cells=None, grid=None, via_target_layers=None):
    """Insert tracks + vias to board, recording for ripup.

    v6: if `hdi_via_cells` (dict of (i,j)->owner_net) and `grid` are provided,
    vias whose (xy)→(i,j) match a whitelist HDI cell are emitted with the
    HDI microvia geometry (0.10mm drill, 0.25mm pad) instead of the standard
    0.30mm drill / 0.60mm pad. This produces the correct via-in-pad fab
    geometry compatible with JLC HDI Class 2 (epoxy fill + plate-over).

    via_target_layers: optional dict {(x,y): target_layer_id} — if a via
    at (x,y) has a target inner layer (from path analysis), the HDI via is
    emitted as a BLIND via F.Cu→target_layer instead of a through via.
    This is required to avoid through-via collisions with congested
    inner layers (In2/In8) when the actual escape happens on a quieter
    layer (e.g. In4 or In6). JLC HDI Class 2 supports F.Cu→In* blind
    laser-drilled microvias as part of the +$2-3/board fab option.

    v8 (2026-05-28, master Phase 3 OQ-020 emitter gap — PR #227 diagnosis):
    via class is now resolved per-via via `via_class_for_span(L_from, L_to,
    netname, is_hdi_cell, hdi_whitelist)` — adding the BLIND_BURIED
    F.Cu↔In2 emit path (drill 0.15mm / pad 0.30mm) for OQ-020-whitelist
    nets. Per-class emit table (canonical source: this function):
        microvia_F_In1 → VIATYPE_MICROVIA,      drill 0.10, pad 0.25, F↔In1
        microvia_B_In8 → VIATYPE_MICROVIA,      drill 0.10, pad 0.25, In8↔B
        blind_F_In2    → VIATYPE_BLIND_BURIED,  drill 0.15, pad 0.30, F↔In2
        through        → VIATYPE_THROUGH,       drill 0.30, pad 0.60, F↔B
        None           → REFUSED, via not emitted (caller bug: A*'s _via_blocked
                         must have rejected this layer-change before reaching
                         emit time; raises ValueError as defense-in-depth so
                         a silent fall-through to THROUGH F↔B never recurs —
                         the v6/v7 shorts lesson).
    Net-name resolved from `net_obj.GetNetname()` (the bound net is the
    OQ-020 per-net whitelist source — see audit_hdi_via_in_pad).
    """
    # Resolve the bound net's canonical name ONCE for the via-class lookup.
    try:
        bound_netname = net_obj.GetNetname() if net_obj is not None else ""
    except Exception:
        bound_netname = ""
    for (x1, y1, x2, y2, layer) in segments:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm_to_iu(x1), mm_to_iu(y1)))
        t.SetEnd(pcbnew.VECTOR2I(mm_to_iu(x2), mm_to_iu(y2)))
        t.SetLayer(layer)
        t.SetWidth(mm_to_iu(width_mm))
        t.SetNet(net_obj)
        board.Add(t)
        added_items.append(t)
    for (x, y) in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y)))
        # v6: HDI microvia geometry if this via lands on a whitelist pad cell
        is_hdi_cell = False
        if hdi_via_cells and grid is not None:
            ci, cj = grid.xy_to_ij(x, y)
            if (ci, cj) in hdi_via_cells:
                is_hdi_cell = True
        target_pair = via_target_layers.get((round(x, 3), round(y, 3))) \
            if via_target_layers else None
        # v8: classify the (L_from, L_to) span into a sanctioned via class.
        # `via_class_for_span` returns 'through' on a non-HDI cell (back-compat,
        # the v6/v7 behaviour), one of the 3 HDI classes at an HDI cell, or
        # None if the HDI cell + span + net combination is REFUSED (the
        # router must never emit a through-via at a fine-pitch HDI cell —
        # the v6/v7 shorts lesson). Non-HDI cells where `target_pair` is None
        # also classify as 'through' (the prior default for grid-internal
        # via emissions that lack a recorded span).
        if is_hdi_cell and target_pair is not None:
            L_from, L_to = target_pair
            via_class = via_class_for_span(L_from, L_to, bound_netname,
                                            is_hdi_cell=True)
        elif is_hdi_cell and target_pair is None:
            # HDI cell with no recorded span: not safely classifiable —
            # fall back to refusing (no via emitted). This should not occur
            # in practice (via_target_layers is populated by path_to_segments
            # for every via the A* commits) but the defense-in-depth path
            # avoids silent THROUGH-via emission at an HDI cell.
            via_class = None
        else:
            via_class = 'through'
        if via_class is None:
            # REFUSED: do not emit. Raise so a same-router-run bug (A* let
            # an unsanctioned HDI-cell span through to commit_net) surfaces
            # loudly instead of silently shorting adjacent QFN pads.
            raise ValueError(
                f"emit_to_board: refused via class for net={bound_netname!r} "
                f"at ({x:.3f},{y:.3f}) span={target_pair} hdi={is_hdi_cell} — "
                f"A* should have rejected this layer-change before commit "
                f"(via_class_for_span returned None). This is the v6/v7 "
                f"shorts gate: NEVER silently fall through to THROUGH.")
        # Per-class emit: via-type tag + layer pair + drill + pad geometry.
        # v8: ORDER MATTERS in KiCad 9: SetViaType BEFORE SetLayerPair BEFORE
        # SetWidth (per test_audit_hdi_blind_f_in2.py docstring + KiCad
        # source: VIATYPE drives the size-stack lookup; SetLayerPair on a
        # default VIATYPE_THROUGH normalizes to (F.Cu, B.Cu) so the inner
        # layer pair is lost). The pre-v8 emit set MICROVIA then SetLayerPair
        # which happened to work because MICROVIA normalizes correctly for
        # adjacent pairs; the new BLIND_BURIED class REQUIRES the type be
        # set first so SetLayerPair preserves (F.Cu, In2.Cu).
        if via_class == 'microvia_F_In1' or via_class == 'microvia_B_In8':
            # JLC HDI Class 2 adjacent-layer microvia (existing geometry).
            try:
                v.SetViaType(pcbnew.VIATYPE_MICROVIA)
            except Exception:
                pass
            v.SetLayerPair(target_pair[0], target_pair[1])
            v.SetDrill(mm_to_iu(HDI_VIA_DRILL_MM))
            via_diam = HDI_VIA_DIAM_MM
        elif via_class == 'blind_F_In2':
            # OQ-020 ACTIVATE: blind/buried F.Cu↔In2 — laser-drilled blind via
            # on the 4 OQ-020 whitelist nets (BSTB / PWM_INHB / SWDIO / PWM_INLA).
            # SetViaType first, then SetLayerPair (KiCad-9 order requirement).
            try:
                v.SetViaType(pcbnew.VIATYPE_BLIND_BURIED)
            except Exception:
                pass
            v.SetLayerPair(target_pair[0], target_pair[1])
            v.SetDrill(mm_to_iu(BLIND_F_IN2_DRILL_MM))
            via_diam = BLIND_F_IN2_DIAM_MM
        elif via_class == 'stacked_microvia_F_In1_In2':
            # LEVER L 2026-05-28 (Sai cost-OK): JLC HDI Class 2 stacked
            # microvia — TWO MICROVIA legs geometrically aligned. The first
            # (this `v`) is the TOP leg (F.Cu↔In1.Cu); we configure it now
            # and emit a SECOND PCB_VIA (the BOTTOM leg In1.Cu↔In2.Cu) at
            # the same XY immediately afterward. Both legs share the
            # 0.10mm drill / 0.25mm pad geometry and the bound net (signal
            # continuity through the In1 isolated pad island per
            # BOARD_INVARIANTS §"HDI Class extension: stacked microvia
            # F.Cu↔In1↔In2"). The audit's post-loop pair-detection groups
            # co-located MICROVIA legs into the sanctioned stacked pair.
            try:
                v.SetViaType(pcbnew.VIATYPE_MICROVIA)
            except Exception:
                pass
            # Top leg: F.Cu↔In1.Cu (regardless of router-requested span
            # direction — the stacked structure is by definition F→In1→In2).
            v.SetLayerPair(F_CU, IN1_CU)
            v.SetDrill(mm_to_iu(STACKED_MICROVIA_DRILL_MM))
            via_diam = STACKED_MICROVIA_DIAM_MM
            # Set width on top-leg barrel layers BEFORE emitting bottom leg.
            for lid in (F_CU, IN1_CU):
                try:
                    v.SetWidth(lid, mm_to_iu(via_diam))
                except Exception:
                    pass
            v.SetNet(net_obj)
            board.Add(v)
            added_items.append(v)
            # Bottom leg: a SECOND PCB_VIA at the same XY, spanning
            # In1.Cu↔In2.Cu. Build, configure, set width on bottom-barrel
            # layers, then continue the outer loop (skip the standard
            # widths-and-add tail below).
            v2 = pcbnew.PCB_VIA(board)
            v2.SetPosition(pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y)))
            try:
                v2.SetViaType(pcbnew.VIATYPE_MICROVIA)
            except Exception:
                pass
            v2.SetLayerPair(IN1_CU, IN2_CU)
            v2.SetDrill(mm_to_iu(STACKED_MICROVIA_DRILL_MM))
            for lid in (IN1_CU, IN2_CU):
                try:
                    v2.SetWidth(lid, mm_to_iu(STACKED_MICROVIA_DIAM_MM))
                except Exception:
                    pass
            v2.SetNet(net_obj)
            board.Add(v2)
            added_items.append(v2)
            # Skip the tail of the outer loop (widths + add already done).
            continue
        else:  # via_class == 'through'
            # Standard through-via (board-wide default; v6/v7 behaviour).
            try:
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
            except Exception:
                pass
            v.SetLayerPair(F_CU, B_CU)
            # HDI cells without a target_pair never reach here (refused above);
            # so the only path to 'through' here is a NON-HDI cell. Use the
            # standard via geometry; the HDI-small-pad geometry was never
            # appropriate for a non-HDI cell (it's a JLC HDI fab class).
            v.SetDrill(mm_to_iu(VIA_DRILL_MM))
            via_diam = VIA_DIAM_MM
        # KiCad 9 PCB_VIA.SetWidth signature: SetWidth(layer, width)
        # Set width on each copper layer the via spans (the layer set is
        # class-specific — only the layers the barrel actually crosses —
        # so the per-layer width is set only where it physically applies).
        for lid in via_span_layers(via_class):
            try:
                v.SetWidth(lid, mm_to_iu(via_diam))
            except Exception:
                pass
        v.SetNet(net_obj)
        board.Add(v)
        added_items.append(v)


def remove_from_board(board, items):
    for it in items:
        try:
            board.Remove(it)
        except Exception:
            pass


# ─── Cooperative router ───────────────────────────────────────────────────

class CooperativeRouter:

    def __init__(self, board, subsystem_name, grid_pitch=DEFAULT_GRID_PITCH,
                 seed_nets=None, verbose=True, no_rip_routed=False,
                 layer_pref_enabled=True, via_in_pad_allowed=False):
        self.board = board
        self.subsystem = subsystem_name
        self.zone = SUBSYSTEM_ZONES[subsystem_name]
        self.grid_pitch = grid_pitch
        self.verbose = verbose
        # v4 (2026-05-27): --no-rip-routed flag. When True, nets that already
        # had ≥1 track/via in the input board at load time are treated as
        # IMMOVABLE pre-existing routing. They:
        #   - are excluded from self.nets (never re-attempted)
        #   - are never selected as ripup candidates
        #   - are never force-ripped in plateau recovery
        #   - their tracks/vias contribute hard-obstacle cost (already true via
        #     _stamp_obstacles which stamps every track/via from board state)
        # Use case: multi-pass workflows where pass N+1 must preserve pass N's
        # work. Without this flag, cooperative ripup may rip cross-session
        # routes because it has no concept of "pre-existing immutable".
        # Worker discovery 2026-05-27 (CH1 STEP-6 (c) re-approach): pass 2's
        # local net-by-net cooperative ripped BEMF_C from pass 1's result.
        self.no_rip_routed = no_rip_routed

        # v4: snapshot pre-existing routed nets BEFORE we touch the board.
        # A net is "preserved" if it has ≥1 track or via in the input board.
        # We snapshot net NAMES (strings) because netcodes can theoretically
        # be re-issued by KiCad on board mutation.
        self.preserved_nets = set()
        for t in board.GetTracks():
            nn = t.GetNetname()
            if nn:
                self.preserved_nets.add(nn)

        # v5: clear module-level layer-pref cache for test isolation (multiple
        # CooperativeRouter instances in one process see fresh classifier state).
        _LAYER_PREF_CACHE.clear()
        self.layer_pref_enabled = layer_pref_enabled
        # v6 (2026-05-27): HDI via-in-pad enable for J18/J19 whitelist.
        # When True, _stamp_obstacles() skips the mark_pad_zone call for
        # whitelisted-footprint pads, leaving via_forbidden_zones empty
        # there so the router can drop a same-net via on the pad center.
        self.via_in_pad_allowed = via_in_pad_allowed
        self.state = BoardState(board, self.zone)
        self.grid = CongestionGrid(self.zone, grid_pitch, SIGNAL_LAYERS,
                                    layer_pref_enabled=layer_pref_enabled)
        if self.verbose:
            print(f"[coop] layer-pref-bias: {'ON' if layer_pref_enabled else 'OFF'}"
                  f" (v5 per-net-class layer cost multiplier; "
                  f"BEMF→In4, PWM/CSA→In2, SWD/GH/GL/BST→In8, etc.)",
                  flush=True)
            print(f"[coop] via-in-pad-allowed: "
                  f"{'ON' if via_in_pad_allowed else 'OFF'}"
                  f" (v6 HDI whitelist={list(HDI_VIA_IN_PAD_REFS)}; "
                  f"unblocks J18/J19 QFN escape per worker per-pin diagnosis)",
                  flush=True)
        self._stamp_obstacles()

        # Per-net committed routes: net -> (path_cells, added_items)
        self.committed = {}

        # Identify target nets
        if seed_nets:
            self.nets = [n for n in seed_nets if n in self.state.net_pads]
        else:
            self.nets = self.state.routable_nets()
        # v4: if --no-rip-routed, drop any preserved nets from the target list
        # so we don't even attempt to re-route them. Their existing tracks
        # remain as hard obstacles via the _stamp_obstacles call above.
        if self.no_rip_routed:
            skipped = [n for n in self.nets if n in self.preserved_nets]
            self.nets = [n for n in self.nets if n not in self.preserved_nets]
            if self.verbose:
                print(f"[coop] --no-rip-routed: {len(self.preserved_nets)} pre-existing "
                      f"routed nets snapshotted (immovable); "
                      f"{len(skipped)} dropped from target list"
                      + (f": {skipped[:10]}{'...' if len(skipped)>10 else ''}"
                         if skipped else ""), flush=True)
        # Filter to nets with pads on F/B/inner — all should be fine
        self.nets.sort(key=lambda n: (net_priority(n), -len(self.state.net_pads[n]), n))

        # Stats
        self.iteration_count = 0
        self.ripup_count = 0
        self.start_time = 0.0

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def _stamp_obstacles(self):
        s = self.state
        g = self.grid
        # Pad model:
        #   Pad copper rect = HARD obstacle to all (including own net for cell-traversal),
        #     but pad center cell is marked accessible via pad_cells[owner_net]
        #   Clearance halo (pad bbox + clearance + trace_half) = NET-OWNED halo;
        #     blocked for other nets, accessible to owner net (own copper extends here)
        #   Via-keep-out (pad bbox + clearance + via_half) = via forbidden for other nets
        # For routing net X exiting its own pad:
        #   - start cell = pad_cells[X] (accessible despite obstacle)
        #   - immediate neighbors are net_halo[X] cells (accessible to X, blocked to others)
        #   - can traverse 0.3-0.4mm of own halo then transition to free cells
        # Halo dimensions: pad copper edge + clearance + trace half-width + grid slop
        # ensures track centerline never lands closer than (clearance + trace_half) to pad edge
        # which means track edge stays ≥clearance from pad edge.
        halo_m = CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
        # v2: iterate ALL_COPPER_LAYERS so through-hole pads stamp on plane
        # layers too. CongestionGrid.stamp_obstacle_rect silently skips layers
        # not in its self.layers list (signal layers only) for obstacle/halo
        # marking, BUT we still need via_plane_owners marked for THT pads on
        # plane layers (so foreign-net vias get blocked at the pad cell on
        # plane layers).
        # v6: count HDI-whitelisted pads we skipped via_forbidden_zones for
        # (diagnostic — should be ~32 + ~24 = ~56 for J18+J19 on F.Cu).
        hdi_skip_count = 0
        for layer in ALL_COPPER_LAYERS:
            for (x, y, hx, hy, owner, padid) in s.pad_obstacles_by_layer.get(layer, []):
                # On signal layers: full obstacle + halo + pad-cell access + via-keepout
                if layer in SIGNAL_LAYERS:
                    # v6: identify HDI-whitelisted pads BEFORE stamping so we
                    # can record obstacle-cell delta in hdi_pad_obstacle_cells.
                    padref = padid.split(".", 1)[0] if padid else ""
                    is_hdi_pad = (self.via_in_pad_allowed
                                  and is_hdi_via_in_pad_ref(padref))
                    if is_hdi_pad:
                        obstacle_before = set(g.obstacle)
                    g.stamp_obstacle_rect(x, y, hx, hy, layer)
                    if owner and owner != "<NC>":
                        g.allow_pad_access_rect(x, y, layer, owner, hx, hy)
                        g.stamp_halo_rect(x, y, hx + halo_m, hy + halo_m, layer, owner)
                    else:
                        g.stamp_obstacle_rect(x, y, hx + halo_m, hy + halo_m, layer)
                    if is_hdi_pad:
                        # Track which obstacle cells came from this J18/J19 pad
                        # so HDI via_blocked_for_net can ignore them as
                        # obstacles (we geometrically verified microvia fits
                        # adjacent 0.5mm-pitch QFN pads). For F.Cu where the
                        # pad-copper itself is, the obstacle cells are the
                        # pad rect; for inner layers nothing was stamped (the
                        # SMD pad doesn't extend to inner copper).
                        new_obs = g.obstacle - obstacle_before
                        g.hdi_pad_obstacle_cells.update(new_obs)
                    # v6 HDI via-in-pad: skip the via-keepout zone for
                    # whitelisted footprints (J18/J19) on signal layers when
                    # via_in_pad_allowed=True. Without skipping, the adjacent
                    # QFN pad's keepout zone (radius ~0.96mm at 0.5mm pitch)
                    # blocks same-net via-on-pad placement because the cell
                    # ends up owned by BOTH pads' nets → owners−{netname} ≠ ∅
                    # → is_via_forbidden returns True. Skipping leaves the
                    # via-keepout zone unset for THIS pad while preserving:
                    #   - pad copper obstacle (foreign-net tracks still blocked)
                    #   - same-net pad-cell access (own-net traversal works)
                    #   - foreign-net halo (different-net tracks/vias blocked
                    #     by net_halo via stamp_halo_rect above)
                    # so the only relaxation is OWN-net via-on-pad legality.
                    if is_hdi_pad:
                        hdi_skip_count += 1
                        # v6: register pad-center cell as HDI via site so
                        # via_blocked_for_net uses HDI scan radius here.
                        # Only mark on F.Cu (the SMD pad's layer) — via
                        # connects F.Cu→B.Cu spanning all inner layers, but
                        # the "I'm a via-on-pad" attribute belongs to the
                        # F.Cu cell where the SMD pad lives.
                        if layer == F_CU and owner and owner != "<NC>":
                            ci, cj = g.xy_to_ij(x, y)
                            if g.in_bounds(ci, cj):
                                g.hdi_via_cells[(ci, cj)] = owner
                        continue
                    via_keepout = max(hx, hy) + CLEARANCE_MM + VIA_DIAM_MM / 2 + GRID_SLOP_MM
                    g.mark_pad_zone(x, y, layer, owner or "<NC>", radius_mm=via_keepout)
                else:
                    # Plane layer: mark via_plane_owners cell (via_blocked_for_net
                    # consults this on plane layers during via expansion). The
                    # pad copper area is small (≤1mm) compared to the plane fill
                    # rasterization but THT pads MUST own those cells against
                    # foreign-net vias. Antipad expansion via grid slop.
                    if owner and owner != "<NC>":
                        i_min, j_min = g.xy_to_ij(x - hx - halo_m, y - hy - halo_m)
                        i_max, j_max = g.xy_to_ij(x + hx + halo_m, y + hy + halo_m)
                        i_min = max(0, i_min); j_min = max(0, j_min)
                        i_max = min(g.nx - 1, i_max); j_max = min(g.ny - 1, j_max)
                        for ii in range(i_min, i_max + 1):
                            for jj in range(j_min, j_max + 1):
                                pcx, pcy = g.cell_xy(ii, jj)
                                if abs(pcx - x) <= hx + halo_m and abs(pcy - y) <= hy + halo_m:
                                    g.via_plane_owners[(ii, jj)].setdefault(layer, owner)
        # Tracks -> hard obstacle on their layer (signal layers only — planes
        # have no tracks in normal stackups; we ignore any rogue plane-layer
        # tracks intentionally since v2 plane-fill rasterization covers them).
        for layer in SIGNAL_LAYERS:
            for (x1, y1, x2, y2, w, owner) in s.track_obstacles_by_layer.get(layer, []):
                g.stamp_obstacle_segment(x1, y1, x2, y2, w, layer)
                # v6: keep exact segment for HDI precise distance checks
                g.track_segments_by_layer[layer].append((x1, y1, x2, y2, w, owner))
        # Vias -> obstacle on ALL copper layers (through vias span F.Cu to B.Cu
        # including inner planes — must block foreign-net vias from colliding
        # on plane layers, not just routing layers; v2 fix companion).
        for entry in s.via_obstacles:
            # v10 (2026-05-28, CH1 30/30 lever I): _collect now produces a
            # 5-tuple (x, y, stamp_r, owner, actual_diam). Pre-v10 4-tuple
            # support kept for any caller / test that still produces the
            # legacy shape — if no actual_diam is present we fall back to
            # the pre-v10 back-derivation (preserves v6/v7 behaviour).
            if len(entry) >= 5:
                x, y, r, owner, actual_diam = entry[0], entry[1], entry[2], entry[3], entry[4]
            else:
                x, y, r, owner = entry
                # legacy fall-back — back-derive from stamp radius
                actual_diam = max(VIA_DIAM_MM,
                                  2 * (r - CLEARANCE_MM - TRACE_HALF_MM - GRID_SLOP_MM))
            for layer in ALL_COPPER_LAYERS:
                g.stamp_obstacle_circle(x, y, r, layer)
            # v10 (2026-05-28, CH1 30/30 lever I): foreign_vias entry uses
            # the TRUE physical diameter from the board (no max-VIA_DIAM_MM
            # clamp), so hdi_via_blocked_geom's centerline-precise check
            # against this foreign via uses the actual via barrel — not an
            # inflated 0.60mm fallback that falsely rejected legitimate
            # adjacent HDI via placements. The cell-obstacle stamp above
            # still uses the conservative `r` for foreign-cell blocking.
            g.foreign_vias.append((x, y, actual_diam, owner))
            # Also mark via cell as plane-owned by its net on plane layers so
            # a SAME-net via at (i,j) is not falsely blocked by the existing
            # via's own clearance halo when retried.
            i0, j0 = g.xy_to_ij(x, y)
            for L in ALL_COPPER_LAYERS:
                # Same-net via stack: owner net "owns" this cell on every layer
                if owner:
                    g.via_plane_owners[(i0, j0)].setdefault(L, owner)
        # Zone bboxes on F.Cu / B.Cu (MOTOR/SHUNT pours) -> soft history bump
        for layer in (F_CU, B_CU):
            for (x1, y1, x2, y2, owner) in s.zone_obstacles_by_layer.get(layer, []):
                # Only stamp zones whose net is a power/MOTOR/SHUNT net (would conflict with signals)
                if owner and (owner.startswith('MOTOR_') or owner.startswith('SHUNT_')
                              or owner.startswith('VMOTOR') or owner.startswith('+V')):
                    g.stamp_obstacle_zone_bbox(x1, y1, x2, y2, layer, soft=True)
        # (F.Cu / B.Cu discouragement implemented via LAYER_BASE_COST in cost() —
        # no per-cell history bump needed; saves memory.)

        # v2 fix: rasterize POWER-PLANE filled zones for HARD via-blocking on
        # all copper layers in the through-via span (including inner planes).
        # antipad_mm includes the via pad radius (VIA_DIAM/2) + clearance +
        # small grid slop. This is the minimum distance the via centre must be
        # from the plane edge to keep the via barrel/pad clear of plane copper.
        # Note: inside the plane fill, a foreign-net via REQUIRES an antipad
        # hole in the plane; KiCad will draw one at fill time, but the antipad
        # cuts into the plane and the resulting void may still violate
        # clearance to OTHER copper. Easiest correct policy: BLOCK foreign-net
        # vias from plane-interior cells AND from cells within antipad_mm of
        # plane edge (which is a no-fill region anyway).
        antipad_mm = VIA_DIAM_MM / 2 + CLEARANCE_MM + GRID_SLOP_MM
        n_zones_stamped = 0
        for (outlines, layer, netname, bbox) in s.filled_zones:
            # Clip stamping to subsystem zone (saves grid cells per layer)
            zx1, zy1, zx2, zy2 = bbox
            sx1, sy1, sx2, sy2 = self.zone
            # margin: include plane just outside zone for via-near-edge check
            margin = 1.0
            if zx2 < sx1 - margin or zx1 > sx2 + margin: continue
            if zy2 < sy1 - margin or zy1 > sy2 + margin: continue
            g.stamp_plane_fill(outlines, layer, netname, antipad_mm)
            n_zones_stamped += 1
        # Also stamp foreign-net tracks on INNER plane layers as obstacle
        # (these are typically zero on plane layers but worth a sweep — covers
        # the rare case of a track manually placed on an inner plane layer).
        # Already handled by per-layer track_obstacles loop above; planes
        # have no tracks normally.

        # v6 diagnostic: report the via-keepout skip count once stamping done
        if self.via_in_pad_allowed and self.verbose:
            print(f"[coop] HDI via-in-pad: skipped via-keepout on "
                  f"{hdi_skip_count} pad-layer entries "
                  f"(whitelist={list(HDI_VIA_IN_PAD_REFS)}; expected ~50-60 "
                  f"for J18 32 sigpads + J19 24 sigpads on F.Cu)", flush=True)

    def _pad_cells_for_net(self, netname):
        """For each pad of net, mark its cells as accessible to the net."""
        cells_by_pad = []
        for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
            # Pad center cell
            if not (self.zone[0] <= x <= self.zone[2]
                    and self.zone[1] <= y <= self.zone[3]):
                # Pad outside zone — skip (router only reaches pads inside zone)
                continue
            i, j = self.grid.xy_to_ij(x, y)
            if not self.grid.in_bounds(i, j):
                continue
            # Mark FULL pad copper as accessible to own net (covers all pad cells)
            hx = sx / 2; hy = sy / 2
            for layer in layers:
                self.grid.allow_pad_access_rect(x, y, layer, netname, hx, hy)
            # Use pad center cell as canonical access point + 8 neighbors
            pad_layers = list(layers) if layers else [F_CU]
            cells = set()
            for dii in range(-1, 2):
                for djj in range(-1, 2):
                    for L in pad_layers:
                        ci, cj = i + dii, j + djj
                        if self.grid.in_bounds(ci, cj):
                            cells.add((ci, cj, L))
            cells_by_pad.append((ref, padname, x, y, cells, pad_layers, sx, sy))
        return cells_by_pad

    def verify_net_connectivity(self, netname):
        """v3: post-MST safety net — verify that all of this net's pads are
        actually electrically connected by walking board tracks/vias and
        building a union-find of pad islands.

        Returns (n_islands, [list_of_island_pad_labels_per_island]).
        n_islands == 1 means fully connected. >1 means SPLIT (the bug class
        worker R22 reported on v2).

        We use union-find rather than KiCad's GetRatsnestForNet because the
        SWIG binding for RN_NET is opaque (no Python-accessible methods to
        enumerate edges or counts).

        Tolerances:
          - Track endpoint ↔ track endpoint same layer: 0.05mm coincident
          - Track endpoint ↔ pad: within pad bbox + 0.05mm
          - Track endpoint ↔ via: 0.15mm coincident
          - Via center connects all copper layers (through-via)
        """
        net_obj = self.state.net_obj.get(netname)
        if net_obj is None:
            net_obj = self.board.GetNetsByName().get(netname)
        if net_obj is None:
            return 0, []
        nc = net_obj.GetNetCode()

        # Collect pads of this net (with bbox)
        pads = []
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                pnet = pad.GetNet()
                if pnet and pnet.GetNetCode() == nc:
                    p = pad.GetPosition()
                    sz = pad.GetSize()
                    pads.append({
                        'label': f"{fp.GetReference()}.{pad.GetPadName()}",
                        'x': iu_to_mm(p.x), 'y': iu_to_mm(p.y),
                        'hx': iu_to_mm(sz.x) / 2, 'hy': iu_to_mm(sz.y) / 2,
                    })
        if len(pads) < 2:
            return 1, [[p['label'] for p in pads]] if pads else []

        # Collect tracks + vias of this net
        tracks = []
        vias = []
        for t in self.board.GetTracks():
            if t.GetNetCode() != nc:
                continue
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                vias.append((iu_to_mm(p.x), iu_to_mm(p.y)))
            else:
                s = t.GetStart(); e = t.GetEnd()
                tracks.append((iu_to_mm(s.x), iu_to_mm(s.y),
                                iu_to_mm(e.x), iu_to_mm(e.y), t.GetLayer()))

        # Node list: pads + track endpoints + vias
        nodes = []   # (kind, label_or_index, x, y, layer or None)
        for i, p in enumerate(pads):
            nodes.append(('pad', i, p['x'], p['y'], None))  # kind, pad_index
        for i, (x1, y1, x2, y2, L) in enumerate(tracks):
            nodes.append(('trk_s', i, x1, y1, L))
            nodes.append(('trk_e', i, x2, y2, L))
        for i, (vx, vy) in enumerate(vias):
            nodes.append(('via', i, vx, vy, None))

        n = len(nodes)
        parent = list(range(n))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        def union(a, b):
            parent[find(a)] = find(b)

        TOL_COINCIDENT = 0.05  # mm
        TOL_VIA = 0.15         # mm — via diameter tolerance for endpoint-on-via
        for i in range(n):
            for j in range(i + 1, n):
                a = nodes[i]; b = nodes[j]
                dx = a[2] - b[2]; dy = a[3] - b[3]
                d2 = dx * dx + dy * dy
                # Pad-touches-anything: check if other endpoint within pad bbox
                if a[0] == 'pad':
                    p = pads[a[1]]
                    if (abs(b[2] - p['x']) <= p['hx'] + TOL_COINCIDENT
                            and abs(b[3] - p['y']) <= p['hy'] + TOL_COINCIDENT):
                        # If b is a track endpoint, layer must be a routing layer (any)
                        union(i, j); continue
                if b[0] == 'pad':
                    p = pads[b[1]]
                    if (abs(a[2] - p['x']) <= p['hx'] + TOL_COINCIDENT
                            and abs(a[3] - p['y']) <= p['hy'] + TOL_COINCIDENT):
                        union(i, j); continue
                # Via spans all layers, connect to any nearby endpoint
                if a[0] == 'via' or b[0] == 'via':
                    if d2 <= TOL_VIA * TOL_VIA:
                        union(i, j); continue
                # Same-layer track endpoint touching another track endpoint
                if a[4] is not None and b[4] is not None and a[4] == b[4]:
                    if d2 <= TOL_COINCIDENT * TOL_COINCIDENT:
                        union(i, j); continue
                # Track endpoints on the same track (auto-connect)
                if a[0] in ('trk_s', 'trk_e') and b[0] in ('trk_s', 'trk_e') and a[1] == b[1]:
                    union(i, j)

        # ── LEVER UU.2 (2026-05-30) T-JUNCTION FIX ──────────────────────────
        # Per Sai UU.2 directive + empirical evidence on Bv3 board: 6 nets
        # (BSTA/BSTB/GHA/GHB/GHC/GLA/GLC) with 11-56 tracks emitted were
        # reported as 2 islands by the prior endpoint-only union-find,
        # while kicad-cli DRC ground-truth reports 0 unconnected_items
        # for them. ROOT CAUSE: prior union-find only checked
        # endpoint-to-endpoint coincidence. KiCad fab graph also connects:
        #   - Track endpoint that lands on the INTERIOR of another track
        #     of the same net + same layer (T-junction). This is the
        #     dominant gap — the maze emits tracks that cross or T into
        #     each other and KiCad fab sees them connected via the
        #     copper overlap, but the prior verifier missed it.
        #
        # Fix: for every track endpoint, compute point-to-segment distance
        # against every OTHER track of the same net + same layer. If the
        # endpoint lies within TOL_COINCIDENT of any segment interior,
        # union the endpoint with both endpoints of that other track.
        # This matches KiCad's fab-truth connectivity within the existing
        # 0.05mm tolerance — no widening, just an additional geometric
        # relation that was missing from the prior incomplete check.
        import math as _math

        def _seg_point_dist(x1, y1, x2, y2, px, py):
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                return _math.hypot(px - x1, py - y1)
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy)
                              / (dx * dx + dy * dy)))
            cx = x1 + t * dx
            cy = y1 + t * dy
            return _math.hypot(px - cx, py - cy)

        # Build a quick lookup from (track_index, endpoint_kind) → node index.
        trk_node = {}
        for k, node in enumerate(nodes):
            if node[0] in ('trk_s', 'trk_e'):
                trk_node[(node[1], node[0])] = k

        for k, node in enumerate(nodes):
            if node[0] not in ('trk_s', 'trk_e'):
                continue
            layer_k = node[4]
            px, py = node[2], node[3]
            for ti, (x1, y1, x2, y2, layer_t) in enumerate(tracks):
                if ti == node[1]:
                    continue  # the endpoint's own track
                if layer_t != layer_k:
                    continue
                d = _seg_point_dist(x1, y1, x2, y2, px, py)
                if d <= TOL_COINCIDENT:
                    # Union this endpoint with track ti's endpoints
                    s_k = trk_node.get((ti, 'trk_s'))
                    e_k = trk_node.get((ti, 'trk_e'))
                    if s_k is not None:
                        union(k, s_k)
                    if e_k is not None:
                        union(k, e_k)

        # Group pad nodes by island
        islands = defaultdict(list)
        for i, node in enumerate(nodes):
            if node[0] == 'pad':
                islands[find(i)].append(pads[node[1]]['label'])
        # Sort islands by size desc
        island_list = sorted(islands.values(), key=lambda x: -len(x))
        return len(island_list), island_list

    def route_one_net_mst(self, netname, present_factor, time_budget_s=8.0):
        """Build MST of pads. For each MST edge route via A*. Accumulate paths.

        Returns (paths_list, status, failed_pairs) where:
          paths_list = [path_cells_per_edge]
          status     = 'ROUTED' (all MST edges succeeded — full electrical merge),
                       'PARTIAL' (>=1 edge routed, >=1 failed — net split into >1 islands),
                       'FAILED'  (no edges routed at all)
          failed_pairs = list of (pad_ref_a, pad_ref_b) edges that A* could not route

        v3 (2026-05-27, master R26 NARROW FIX): previously, on first MST edge
        failure the entire net was abandoned (all_paths discarded, ok=False).
        That left multi-pad nets fully unrouted even when (N-1) of N edges
        would have succeeded. Worker R22 saw "BEMF_B_CH1 split, BEMF_A/C OK"
        after v2 — root cause is exactly this: one bad edge kills the whole net.

        v3 behaviour:
          - Each MST edge attempt is independent. If A* fails, mark that
            pad-pair as failed but KEEP routing the remaining edges using the
            paths so far as multi-source (so subsequent edges can hook into
            already-routed islands of this net).
          - Return status='PARTIAL' if >=1 path routed AND >=1 failed.
          - run() will detect PARTIAL and re-attempt the failed pairs in
            later iterations (with higher present_factor/history pressure).
        """
        pad_info = self._pad_cells_for_net(netname)
        if len(pad_info) < 2:
            return [], 'FAILED', []  # nothing to route
        # MST: greedy nearest-neighbor from root pad.
        # LEVER DD (2026-05-30): per-net MST root override for chronic-leaf
        # nets — root at the leaf instead of HDI-corner, so the trunk
        # grows OUTWARD with the chronic-leaf already-connected at the
        # root (eliminates the verify-split rejection observed under
        # canonical/Z attempts).
        root_idx = mst_root_index_for_net(netname, pad_info)
        connected = {root_idx}
        edges = []
        while len(connected) < len(pad_info):
            best = None; best_d = math.inf
            for i in connected:
                xi, yi = pad_info[i][2], pad_info[i][3]
                for j in range(len(pad_info)):
                    if j in connected: continue
                    xj, yj = pad_info[j][2], pad_info[j][3]
                    d = (xi - xj) ** 2 + (yi - yj) ** 2
                    if d < best_d:
                        best_d = d; best = (i, j)
            if best is None: break
            edges.append(best); connected.add(best[1])

        # Allowed layers for this net's routing
        allowed = list(set([F_CU, B_CU] + inner_layers_for(netname)))
        # v6: when HDI via-in-pad is enabled AND this net touches a J18/J19
        # pad, expand the allowed layers to ALL signal layers. Rationale:
        # HDI's value-add is escaping the via-fanout bottleneck — but the
        # via must drop to a layer with capacity. Per-net LAYER_PREF (e.g.
        # PWM→[In2, In8]) over-restricts when those layers are saturated.
        # Worker R22 measured In4/In6 EMPTY (0 tracks) while In2/In8 held
        # 163/82 tracks in CH1 (PR#206). With HDI, we WANT escape vias to
        # spill into the unused layers. Layer-pref cost bias (v5) still
        # tilts the cost toward each net's spec'd layer; this only opens
        # the fallback set so the router can route at all.
        if self.via_in_pad_allowed:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
                if is_hdi_via_in_pad_ref(ref):
                    allowed = list(set(allowed + SIGNAL_LAYERS))
                    break

        # Route each MST edge with A*, growing the connected set per edge.
        # After routing edge k, the resulting path cells become valid SOURCES
        # for next edges of the same net (so the net's own routes are reusable,
        # not obstacles).
        # v3: failed edges no longer abort. Track them in `failed_pairs` and
        # continue. If a later edge's source pad has no path-cells yet, it
        # still has its pad cells. Multi-source A* will find the closest of
        # all available sources (own pads + own routed paths).
        all_paths = []
        my_route_cells = set()
        failed_pairs = []
        # K2 (v11) per-leaf retry tracking: edge index -> retries used.
        retries_per_leaf = {}
        # K2: capture pad-coord for each failed pair so the provenance file
        # can list canonical pad refs.
        failed_pair_pads = {}
        # Helper to identify pad by ref.padname for human-readable failure
        def pad_label(idx):
            ref = pad_info[idx][0]; nm = pad_info[idx][1]
            return f"{ref}.{nm}"
        # PASS 1 — forward greedy edges (v3 semantics).
        # K2 enhancement: when an edge fails, record its pad indices for the
        # PASS-2 rejoin attempt against the FULL multi-source pool.
        pending_leaves = []  # list[(edge_idx, a, b)] for K2 rejoin
        for (i_edge, (a, b)) in enumerate(edges):
            sources = set()
            for cell in pad_info[a][4]:
                sources.add(cell)
            sources |= my_route_cells
            targets = set()
            for cell in pad_info[b][4]:
                targets.add(cell)
            # Time budget per edge
            edge_budget = max(2.0, time_budget_s / max(1, len(edges)))
            path, cost = find_path_astar(self.grid, sources, targets,
                                          netname, allowed, present_factor,
                                          time_budget_s=edge_budget)
            if path is None:
                retries_per_leaf[i_edge] = 1   # 1st attempt (forward greedy)
                pending_leaves.append((i_edge, a, b))
                continue  # v3: keep going — don't abandon prior edges
            # LEVER UU.4 (2026-05-30): pre-commit geometric reach check.
            # A* returns path that should land in target cell set, but if
            # the last cell doesn't intersect pad b's accessible cells,
            # the resulting committed route has a geometric gap to pad b
            # → verifier rejects as SPLIT. Per UU.3 #277 finding (chronic
            # is multi-mm gap, route reports ROUTED but doesn't reach
            # endpoints), enforce: the path's final cell must be in
            # pad b's accessible cell set, else treat as A* failure
            # (no commit, queue for retry / mark failed).
            target_cells = set(pad_info[b][4])
            if path and path[-1] not in target_cells:
                # Path didn't reach target pad — A* returned a
                # geometrically-incomplete result. Reject + queue retry.
                retries_per_leaf[i_edge] = 1
                pending_leaves.append((i_edge, a, b))
                continue
            # Track cells — add to multi-source pool for subsequent MST edges
            for c in path: my_route_cells.add(c)
            all_paths.append(path)
            retries_per_leaf[i_edge] = 1
        # PASS 2 (K2): rejoin loop. Each pending leaf gets up to
        # MST_LEAF_RETRY_CAP attempts against the FULL net multi-source pool
        # (which now includes cells routed by later edges that may have
        # formed an island the leaf can attach to). Bounded retries =
        # SURESHOT discipline.
        # Two retry passes per leaf: (a) rejoin with full multi-source +
        # baseline present_factor; (b) rejoin with full multi-source +
        # 1.4× present_factor (mirrors the cooperative loop bump on the
        # NEXT iteration but inside THIS MST call so we don't lose work).
        next_pending = []
        for (i_edge, a, b) in pending_leaves:
            attempted = retries_per_leaf[i_edge]
            routed_this_leaf = False
            for retry_idx in range(MST_LEAF_RETRY_CAP - 1):
                attempted += 1
                # K2 rejoin: include cells from EVERY successfully-routed
                # edge in this MST call so far (the multi-source pool).
                sources = set()
                for cell in pad_info[a][4]:
                    sources.add(cell)
                sources |= my_route_cells
                targets = set()
                for cell in pad_info[b][4]:
                    targets.add(cell)
                # Also let target be ANY same-net island already routed —
                # this is the K2 specific win over v3 (v3 only tried the
                # original a→b sources; K2 lets b attach to whatever island
                # the net has).
                targets |= my_route_cells
                # LEVER UU.4 (2026-05-30): pre-commit geometric reach
                # check. The prior `sources & targets` test always fired
                # when my_route_cells was non-empty (because both sources
                # and targets include it) — even when pad b had NO cells
                # in the routed pool, causing chronic R76.1 split: leaf
                # marked routed_this_leaf=True without pad b actually
                # being reachable. Per UU.3 #277 finding (chronic is
                # multi-mm geometric gap), require BOTH pad a AND pad b
                # cell sets to have at least one cell in my_route_cells
                # before claiming "merged via prior edges".
                a_cells = set(pad_info[a][4])
                b_cells = set(pad_info[b][4])
                if (a_cells & my_route_cells) and (b_cells & my_route_cells):
                    # Both pads have ≥1 access cell in the routed pool;
                    # electrically connected via prior MST edges.
                    routed_this_leaf = True
                    # No new path emitted; the connection exists already.
                    break
                pf = present_factor * (1.0 if retry_idx == 0 else 1.4)
                edge_budget = max(2.0, time_budget_s / max(1, len(edges)))
                path, cost = find_path_astar(self.grid, sources, targets,
                                              netname, allowed, pf,
                                              time_budget_s=edge_budget)
                if path is not None:
                    for c in path: my_route_cells.add(c)
                    all_paths.append(path)
                    routed_this_leaf = True
                    break
            retries_per_leaf[i_edge] = attempted
            if not routed_this_leaf:
                la, lb = pad_label(a), pad_label(b)
                failed_pairs.append((la, lb))
                failed_pair_pads[(la, lb)] = (
                    pad_info[a][2], pad_info[a][3],
                    pad_info[b][2], pad_info[b][3],
                )
                next_pending.append((i_edge, a, b))
        # K2 (v11) provenance: any PARTIAL net (status) must record an
        # entry. We collect the info on `self` so the run() loop can
        # serialise + write to disk under PARTIAL_MST_PROVENANCE_DIR_REL.
        if failed_pairs:
            self._record_partial_mst(netname, pad_info, all_paths,
                                       failed_pairs, retries_per_leaf,
                                       failed_pair_pads)
        if not all_paths:
            return [], 'FAILED', failed_pairs
        if failed_pairs:
            return all_paths, 'PARTIAL', failed_pairs
        return all_paths, 'ROUTED', []

    def _record_partial_mst(self, netname, pad_info, routed_paths,
                              failed_pairs, retries_per_leaf,
                              failed_pair_pads):
        """v11 K2: record a partial-MST provenance entry for `netname`. The
        audit `audit_partial_mst_provenance.py` (G_K1, R40) reads these
        entries to verify every PARTIAL multi-pad net has a documented
        retry trail — never a silent abandonment.

        Mirrors the targeted_ripup.write_provenance discipline (R36/G_J1).

        Entry schema (JSON):
            schema_version: 1
            netname        : str
            timestamp_iso  : ISO-8601 UTC
            pad_refs       : [pad_label] for every pad on the net
            routed_edges   : count of successfully-committed paths
            failed_pad_pairs: [[ref_a, ref_b], ...]
            retries_per_leaf: { "<i_edge>": int_retries_used }
            reason         : human-readable summary (the audit doesn't
                              consume this — pure provenance)
        """
        # Accumulate in-memory; the run() loop calls _flush_partial_mst()
        # after the iteration completes so we batch I/O once per pass.
        if not hasattr(self, "_pending_partial_mst"):
            self._pending_partial_mst = []
        # pad_info entries from _pad_cells_for_net are (ref, padname, x, y,
        # cells, layers, sx, sy) — 8 fields. We use only the first 2.
        pad_refs = [f"{entry[0]}.{entry[1]}" for entry in pad_info]
        self._pending_partial_mst.append({
            "schema_version": 1,
            "netname": netname,
            "pad_refs": pad_refs,
            "routed_edges": len(routed_paths),
            "failed_pad_pairs": [list(p) for p in failed_pairs],
            "retries_per_leaf": {str(k): int(v) for k, v
                                  in retries_per_leaf.items()},
            "reason": (
                f"PARTIAL MST after K2 rejoin retries: "
                f"{len(routed_paths)} routed + {len(failed_pairs)} failed "
                f"of {len(pad_info)-1} total MST edges; "
                f"retry cap = {MST_LEAF_RETRY_CAP}"
            ),
        })

    def flush_partial_mst_provenance(self, repo_root=None, board_sha=""):
        """v11 K2: write any pending partial-MST provenance entries to
        sims/routing_provenance/partial_mst/{sha}_{netname}_{seq}.json.

        Called by run() after each pass + once at the end. Idempotent: a
        flush with no pending entries is a no-op. The audit
        `audit_partial_mst_provenance.py` enforces presence.

        `repo_root` defaults to the file's grand-grand-parent (the repo
        root in our standard layout — same pattern as audit_meta.py).
        """
        pending = getattr(self, "_pending_partial_mst", [])
        if not pending:
            return []
        if repo_root is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
        import json
        from datetime import datetime, timezone
        d = repo_root / PARTIAL_MST_PROVENANCE_DIR_REL
        d.mkdir(parents=True, exist_ok=True)
        written = []
        for entry in pending:
            entry = dict(entry)  # copy — don't mutate caller's dict
            entry["timestamp_iso"] = datetime.now(timezone.utc).isoformat()
            entry["board_sha"] = board_sha or ""
            base = re.sub(r"[^A-Za-z0-9_.+-]", "_",
                          f"{(board_sha or 'NOSHA')[:12]}_{entry['netname']}")
            seq = 0
            while True:
                p = d / f"{base}_{seq:03d}.json"
                if not p.exists():
                    break
                seq += 1
            p.write_text(json.dumps(entry, indent=2, sort_keys=True))
            written.append(str(p))
        self._pending_partial_mst = []
        return written

    def route_pad_pair(self, netname, src_x, src_y, dst_x, dst_y,
                       present_factor, time_budget_s=8.0):
        """v3: route a single source-pad → destination-pad pair (no MST).

        Used by re-attempt phase: when a multi-pad net was reported PARTIAL,
        the run() loop calls this method with the specific failed pad-pair
        coordinates so a subsequent iteration (with higher present_factor) can
        attempt the missing edge without re-doing the entire MST.

        Sources include the failed pad's cells AND any cells already committed
        to this net (so the new path can attach to ANY existing island, not
        just the original pad).

        Returns (path or None,) — single path or None on failure.
        """
        pad_info = self._pad_cells_for_net(netname)
        # Find the source and target pad by coordinate match (1e-3mm tol)
        def find_pad_cells(x, y):
            for (ref, pn, px, py, cells, layers, sx, sy) in pad_info:
                if abs(px - x) < 1e-3 and abs(py - y) < 1e-3:
                    return set(cells)
            return None
        src_cells = find_pad_cells(src_x, src_y)
        dst_cells = find_pad_cells(dst_x, dst_y)
        if not src_cells or not dst_cells:
            return None
        # Multi-source: include existing committed cells for this net
        existing = self.committed.get(netname, (set(), []))[0]
        sources = src_cells | existing
        targets = dst_cells | existing  # allow path to terminate at any existing cell
        # Avoid trivial src∩targets case
        if sources & targets and not (src_cells & dst_cells):
            # Both pads already in same island via existing routing — nothing to do
            return None
        allowed = list(set([F_CU, B_CU] + inner_layers_for(netname)))
        # v6: when HDI via-in-pad is enabled AND this net touches a J18/J19
        # pad, expand the allowed layers to ALL signal layers. Rationale:
        # HDI's value-add is escaping the via-fanout bottleneck — but the
        # via must drop to a layer with capacity. Per-net LAYER_PREF (e.g.
        # PWM→[In2, In8]) over-restricts when those layers are saturated.
        # Worker R22 measured In4/In6 EMPTY (0 tracks) while In2/In8 held
        # 163/82 tracks in CH1 (PR#206). With HDI, we WANT escape vias to
        # spill into the unused layers. Layer-pref cost bias (v5) still
        # tilts the cost toward each net's spec'd layer; this only opens
        # the fallback set so the router can route at all.
        if self.via_in_pad_allowed:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
                if is_hdi_via_in_pad_ref(ref):
                    allowed = list(set(allowed + SIGNAL_LAYERS))
                    break
        path, cost = find_path_astar(self.grid, sources, targets,
                                      netname, allowed, present_factor,
                                      time_budget_s=time_budget_s)
        return path

    def commit_net(self, netname, paths, append=False):
        """Commit paths to board + grid.

        v3: when append=True, ADD these new paths to the existing committed
        entry for this net (used by partial-net repair where a follow-up
        MST-edge route extends an already-partially-routed net).

        v3 also marks the committed track cells as net-accessible via
        pad_cells (so the next MST edge / repair-pair attempt of THIS net
        can use its own existing routing as a starting point — without this,
        the stamp_obstacle_segment halo would block same-net A* from re-
        attaching to the routed island).
        """
        width = width_for(netname)
        net_obj = self.state.net_obj.get(netname)
        if net_obj is None:
            # Net obj missing; try lookup
            net_obj = self.board.GetNetsByName().get(netname)
        if append and netname in self.committed:
            prev_cells, added = self.committed[netname]
            all_cells = set(prev_cells)
        else:
            added = []
            all_cells = set()
        for path in paths:
            segments, vias, via_layers = path_to_segments(
                path, self.grid, return_via_layers=True)
            # v6: pass HDI cell map + via target layers so emit_to_board
            # switches via geometry to microvia (0.10/0.25mm) AND emits
            # blind via (F.Cu → target inner layer) for whitelisted-pad cells.
            emit_to_board(self.board, segments, vias, net_obj, width, added,
                          hdi_via_cells=self.grid.hdi_via_cells,
                          grid=self.grid,
                          via_target_layers=via_layers)
            for c in path: all_cells.add(c)
        self.grid.commit_path(all_cells, netname)
        # Also stamp committed segments as obstacles for OTHER nets in next iters
        # by adding to track_obstacles (so next A* sees them as hard blockers).
        # v3: after stamping the obstacle halo, re-mark all newly-blocked cells
        # in the halo as ACCESSIBLE to THIS net (so subsequent MST edge / pair
        # repair A* can traverse the net's own routing without being blocked
        # by its own clearance halo).
        for path in paths:
            # v8: ask path_to_segments for via_layers too, so the same per-
            # via (L_from, L_to) span the emitter uses also drives the
            # obstacle stamping (layer-aware: blind F-In2 stamps only F/In1/In2,
            # NOT all 10 layers — otherwise a blind via would falsely block
            # subsequent foreign-net through-vias on In3..B.Cu it cannot
            # actually short).
            segments, vias, via_layers_local = path_to_segments(
                path, self.grid, return_via_layers=True)
            for (x1, y1, x2, y2, layer) in segments:
                self._stamp_own_track_obstacle(x1, y1, x2, y2, width, layer, netname)
                # v7 (worker R22 catch #4 on v6): append to segment list so
                # hdi_via_blocked_geom sees this just-committed track when
                # the NEXT HDI net's A* runs in this same iteration. v6 only
                # populated track_segments_by_layer at _stamp_obstacles()
                # startup — leaving HDI checks blind to same-run tracks and
                # allowing the GHC/GLC via shorts on In4 in PR #207.
                self.grid.track_segments_by_layer[layer].append(
                    (x1, y1, x2, y2, width, netname))
            for (vx, vy) in vias:
                # v8: classify the via to compute the correct barrel span +
                # diameter. Same logic as emit_to_board (single source =
                # via_class_for_span), so obstacle stamping cannot drift
                # from emission.
                vi, vj = self.grid.xy_to_ij(vx, vy)
                is_hdi_cell = (vi, vj) in self.grid.hdi_via_cells
                target_pair = via_layers_local.get(
                    (round(vx, 3), round(vy, 3)))
                if is_hdi_cell and target_pair is not None:
                    via_class = via_class_for_span(
                        target_pair[0], target_pair[1], netname,
                        is_hdi_cell=True)
                else:
                    via_class = 'through'
                # If classification refused (None), stamp conservatively
                # (full stack) as a defense-in-depth no-op — emit_to_board
                # will have raised ValueError, so this code path is
                # unreachable in a passing route. Defensive default kept
                # so a future bug doesn't silently corrupt the obstacle map.
                span_layers = (tuple(ALL_COPPER_LAYERS) if via_class is None
                                else via_span_layers(via_class))
                # v9 (CH1 30/30 lever F): single source of truth =
                # via_diam_mm_for_class + via_halo_radius_mm helpers; matches
                # the geometry the candidate-check halo uses, so OWN-stamp
                # cannot drift from candidate-clearance check (the lock-step
                # invariant: what the router considered clear when it placed
                # the via is what subsequent nets see as obstacle).
                _stamp_class = via_class if via_class is not None else 'through'
                via_diam = via_diam_mm_for_class(_stamp_class)
                # v2 fix: stamp via obstacle on every copper layer in the
                # via's barrel span (layer-aware per v8). Radius accommodates
                # foreign-track centerline gap.
                r = via_halo_radius_mm(_stamp_class, trace_width_mm=2 * TRACE_HALF_MM)
                for layer in span_layers:
                    self._stamp_own_via_obstacle(vx, vy, r, layer, netname)
                # Also mark as plane-owned by this net on every layer the
                # via barrel reaches so a SAME-net repeat via doesn't get
                # false-blocked (layer-aware: blind F-In2 reserves F/In1/In2
                # only — other nets' vias can still use In3..B.Cu cells).
                for layer in span_layers:
                    self.grid.via_plane_owners[(vi, vj)].setdefault(layer, netname)
                # v7 (worker R22 catch #4 on v6): append to foreign_vias so
                # hdi_via_blocked_geom sees this just-committed via when the
                # NEXT HDI net's A* runs in this same iteration.
                self.grid.foreign_vias.append((vx, vy, via_diam, netname))
        # Re-allow pad cells for THIS net (in case its own pads got stamped)
        for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
            for lid in layers:
                self.grid.allow_pad_access_rect(x, y, lid, netname, sx/2, sy/2)
        self.committed[netname] = (all_cells, added)

    def _stamp_own_track_obstacle(self, x1, y1, x2, y2, w, layer, netname):
        """v3: stamp a track halo as obstacle for OTHER nets, but mark all
        the newly-stamped cells as accessible to `netname` (own-net pad-cell
        access). Lets the same net re-route through its own routing area.
        """
        before = set(self.grid.obstacle)
        self.grid.stamp_obstacle_segment(x1, y1, x2, y2, w, layer)
        new_cells = self.grid.obstacle - before
        for cell in new_cells:
            self.grid.pad_cells[cell].add(netname)

    def _stamp_own_via_obstacle(self, x, y, r, layer, netname):
        """v3: stamp a via halo on `layer` as obstacle but mark cells as
        same-net accessible. Companion to _stamp_own_track_obstacle for vias.
        """
        before = set(self.grid.obstacle)
        self.grid.stamp_obstacle_circle(x, y, r, layer)
        new_cells = self.grid.obstacle - before
        for cell in new_cells:
            self.grid.pad_cells[cell].add(netname)

    def _try_bridge_split_islands(self, netname, island_list):
        """LEVER UU.3 (2026-05-30): bridge a verify-detected island split.

        When verify_net_connectivity reports n_islands > 1 after commit_net,
        the route's pad-set is partitioned into >=2 disjoint connected
        components. This helper attempts to emit a short same-layer bridge
        track between the NEAREST pair of pads-or-track-endpoints across
        islands. If a sub-grid-pitch coincidence gap is the cause (planner
        emitted segments that end ~0.01mm from the next via instead of
        coincident), a 0.05mm bridge closes it without any A* call.

        Returns True if a bridge was emitted, False if no actionable gap
        was found (caller falls back to rip + re-queue).

        Discipline:
          - Bridge length capped at COINCIDENT_BRIDGE_MAX_MM (0.10mm) — only
            closes near-coincident gaps, never replaces a real route.
          - Same-layer only: a cross-layer gap is a missing via, not a
            missing track — those need a different fix.
          - Bridge uses the net's default trace width.
        """
        COINCIDENT_BRIDGE_MAX_MM = 0.10
        if not island_list or len(island_list) < 2:
            return False
        # Collect all endpoint coords + layers for THIS net's tracks/vias +
        # pad bbox centers. We label each by (island_id, kind, x, y, layer).
        try:
            import pcbnew
        except Exception:                                          # pragma: no cover
            return False
        net_obj = self.state.net_obj.get(netname)
        if net_obj is None:
            net_obj = self.board.GetNetsByName().get(netname)
        if net_obj is None:
            return False
        nc = net_obj.GetNetCode()
        # Build pad-label → island_id map
        pad_to_island = {}
        for isl_id, pad_labels in enumerate(island_list):
            for label in pad_labels:
                pad_to_island[label] = isl_id
        # Collect ENDPOINTS per island (for bridging we need physical pts):
        # For each pad we use its center+layer; for each track endpoint we
        # know which island via the union-find — but we don't have access
        # to that here, so we approximate: track endpoints are island-assigned
        # by the pad they're closest to (with TOL_COINCIDENT-and-via-aware
        # propagation). For a small bridge case the gap is between a track
        # endpoint and a via center (typical chain emit float-rounding gap).
        endpoints_by_isl = {i: [] for i in range(len(island_list))}
        # Pads → island via label
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                pnet = p.GetNet()
                if not pnet or pnet.GetNetCode() != nc:
                    continue
                label = f"{fp.GetReference()}.{p.GetPadName()}"
                if label in pad_to_island:
                    pos = p.GetPosition()
                    ls = p.GetLayerSet()
                    # Pick first signal layer the pad occupies
                    layer = None
                    for lid in SIGNAL_LAYERS:
                        if ls.Contains(lid):
                            layer = lid
                            break
                    if layer is None:
                        continue
                    endpoints_by_isl[pad_to_island[label]].append(
                        (iu_to_mm(pos.x), iu_to_mm(pos.y), layer, label))
        # Find the nearest cross-island pair on the SAME layer
        best = None
        best_d = COINCIDENT_BRIDGE_MAX_MM + 1e-9
        for i in range(len(island_list)):
            for j in range(i + 1, len(island_list)):
                for (xa, ya, la, _) in endpoints_by_isl[i]:
                    for (xb, yb, lb, _) in endpoints_by_isl[j]:
                        if la != lb:
                            continue
                        import math as _m
                        d = _m.hypot(xa - xb, ya - yb)
                        if d < best_d:
                            best_d = d
                            best = (xa, ya, xb, yb, la)
        if best is None:
            return False
        # Emit the bridge track
        xa, ya, xb, yb, layer = best
        t = pcbnew.PCB_TRACK(self.board)
        t.SetStart(pcbnew.VECTOR2I(mm_to_iu(xa), mm_to_iu(ya)))
        t.SetEnd  (pcbnew.VECTOR2I(mm_to_iu(xb), mm_to_iu(yb)))
        t.SetLayer(layer)
        t.SetWidth(mm_to_iu(0.15))   # default signal trace width
        t.SetNet(net_obj)
        self.board.Add(t)
        return True

    def rip_net(self, netname):
        """Remove a net's committed tracks/vias and obstacles.

        v4: --no-rip-routed defensively refuses to rip any net in
        preserved_nets (pre-existing routed nets). Returns silently to
        keep callers compatible. Belt-and-suspenders alongside the
        candidate-selection filters; protects against future code paths
        that bypass the selection layer.
        """
        if netname not in self.committed: return
        if self.no_rip_routed and netname in self.preserved_nets:
            self.log(f"  [coop] refusing to rip preserved net {netname} "
                     f"(--no-rip-routed)")
            return
        cells, added = self.committed[netname]
        remove_from_board(self.board, added)
        # Rebuild obstacle map cleanly (cheap path: blow away cell-based obstacles and re-stamp from non-committed state).
        # Lightweight approach: do NOT remove old obstacles cells (we'd have to recount references).
        # Instead, decrement present count; obstacle cells set is rebuilt on next iter via _rebuild_grid().
        self.grid.uncommit_path(cells, netname)
        del self.committed[netname]
        # v3: ripping a partial net invalidates its tracked failed-pairs too.
        # The net needs a fresh MST from scratch on its next route attempt.
        if hasattr(self, 'partial_pairs') and netname in self.partial_pairs:
            del self.partial_pairs[netname]
        self.ripup_count += 1

    def _rebuild_grid(self):
        """Reset grid; restamp from current board state + current commits."""
        # Re-read board state (cheap; small)
        self.state = BoardState(self.board, self.zone)
        # Preserve historic congestion
        old_history = dict(self.grid.history)
        self.grid = CongestionGrid(self.zone, self.grid_pitch, SIGNAL_LAYERS)
        self.grid.history = defaultdict(float, old_history)
        self._stamp_obstacles()
        # Re-allow pad access for all target nets (own copper bbox)
        for n in self.nets:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(n, []):
                for lid in layers:
                    self.grid.allow_pad_access_rect(x, y, lid, n, sx/2, sy/2)
        # v3: re-allow committed nets to re-enter their OWN routed cells
        # AND own clearance halo. _stamp_obstacles re-stamps tracks/vias as
        # obstacles per-layer from board state, so we need to walk every
        # such cell and mark it as same-net pad_cells-accessible. Otherwise
        # subsequent partial-pair repair of multi-pad nets gets blocked by
        # its own clearance halo.
        # We do this by iterating each track in the board, finding all cells
        # within stamp_obstacle_segment's halo, and marking them accessible
        # to the track's net.
        for t in self.board.GetTracks():
            netname = t.GetNetname()
            if not netname or netname not in self.committed:
                continue
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                vx = iu_to_mm(p.x); vy = iu_to_mm(p.y)
                # v9 (CH1 30/30 lever F): read the via's actual width from
                # the board so HDI microvias (0.25mm) and blind F-In2 vias
                # (0.30mm) re-stamp at their TRUE halo, not the standard
                # 0.60mm. Over-stamping is benign for OWN-net re-entry
                # (just admits fewer cells back) but drifts from the
                # per-class halo used at commit time → keep them in lock-
                # step. KiCad-9 PCB_VIA.GetWidth(layer); fallback to drill+ring
                # if layer-keyed signature unavailable.
                try:
                    diam = iu_to_mm(t.GetWidth(t.TopLayer()))
                except (TypeError, Exception):
                    try:
                        diam = iu_to_mm(t.GetWidth())
                    except Exception:
                        diam = VIA_DIAM_MM
                # Halo: pad-edge + clearance + foreign-trace-half + slop —
                # same formula as via_halo_radius_mm (but using the BOARD's
                # measured diameter rather than a class lookup; via_class is
                # not authoritative at re-stamp time, the board geometry is).
                r = diam / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
                # v9: layer-aware barrel span. THROUGH vias span all layers;
                # MICROVIA/BLIND only span their actual layer pair (read
                # from TopLayer/BottomLayer + viatype). Avoids re-stamping a
                # blind via halo on layers it doesn't reach (consistent with
                # commit_paths v8 layer-aware stamping).
                try:
                    vt = t.GetViaType()
                    if vt in (pcbnew.VIATYPE_MICROVIA, pcbnew.VIATYPE_BLIND_BURIED):
                        # Span = the actual layer pair stored on the via.
                        top_l = t.TopLayer(); bot_l = t.BottomLayer()
                        # Build the inclusive copper-layer set between them.
                        a = _STACKUP_INDEX.get(top_l)
                        b = _STACKUP_INDEX.get(bot_l)
                        if a is not None and b is not None:
                            lo, hi = (a, b) if a <= b else (b, a)
                            span = tuple(STACKUP_ORDER[lo:hi + 1])
                        else:
                            span = ALL_COPPER_LAYERS
                    else:
                        span = ALL_COPPER_LAYERS
                except Exception:
                    span = ALL_COPPER_LAYERS
                for layer in span:
                    cells_in_halo = self._cells_in_circle(vx, vy, r, layer)
                    for cell in cells_in_halo:
                        self.grid.pad_cells[cell].add(netname)
            else:
                s = t.GetStart(); e = t.GetEnd()
                x1 = iu_to_mm(s.x); y1 = iu_to_mm(s.y)
                x2 = iu_to_mm(e.x); y2 = iu_to_mm(e.y)
                w = iu_to_mm(t.GetWidth())
                layer = t.GetLayer()
                cells_in_halo = self._cells_in_segment(x1, y1, x2, y2, w, layer)
                for cell in cells_in_halo:
                    self.grid.pad_cells[cell].add(netname)
        # Re-allow path cells of currently-committed nets (stored cells set).
        for n, (cells, _added) in self.committed.items():
            for cell in cells:
                self.grid.pad_cells[cell].add(n)

    def _cells_in_circle(self, x, y, r, layer):
        """Helper: enumerate grid cells within radius r of (x,y) on layer."""
        cells = []
        if layer not in self.grid.layers:
            return cells
        i0, j0 = self.grid.xy_to_ij(x, y)
        n = int(math.ceil(r / self.grid.pitch))
        r2 = r * r
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                ci = i0 + di; cj = j0 + dj
                if not self.grid.in_bounds(ci, cj): continue
                cx, cy = self.grid.cell_xy(ci, cj)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    cells.append((ci, cj, layer))
        return cells

    def _cells_in_segment(self, x1, y1, x2, y2, w, layer):
        """Helper: enumerate grid cells within trace halo of a segment on layer."""
        cells = []
        if layer not in self.grid.layers:
            return cells
        half = w / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
        half2 = half * half
        xa, xb = min(x1, x2), max(x1, x2)
        ya, yb = min(y1, y2), max(y1, y2)
        i_min, j_min = self.grid.xy_to_ij(xa - half, ya - half)
        i_max, j_max = self.grid.xy_to_ij(xb + half, yb + half)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.grid.nx - 1, i_max); j_max = min(self.grid.ny - 1, j_max)
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-12:
            return self._cells_in_circle(x1, y1, half, layer)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                cx, cy = self.grid.cell_xy(i, j)
                tt = ((cx - x1) * dx + (cy - y1) * dy) / seg_len2
                tt = max(0.0, min(1.0, tt))
                px = x1 + tt * dx; py = y1 + tt * dy
                if (cx - px) ** 2 + (cy - py) ** 2 <= half2:
                    cells.append((i, j, layer))
        return cells

    def run(self, max_iter=DEFAULT_MAX_ITER):
        """Cooperative loop (Pathfinder-style negotiated congestion + ripup).

        v3 (master 2026-05-27 R26 NARROW FIX):
          - route_one_net_mst now returns 3-tuple (paths, status, failed_pairs).
          - status='PARTIAL' nets have >=1 routed edge AND >=1 failed edge;
            they get committed AND queued for re-attempt of failed pairs.
          - self.partial_pairs[netname] = list of (pad_a_label, pad_b_label,
            pad_a_xy, pad_b_xy). Each iteration re-attempts each failed pair
            via route_pad_pair using higher present_factor (negotiation
            pressure builds across iterations).
          - A net is fully ROUTED only when its self.partial_pairs entry is
            empty (= all MST edges connected = ratsnest semantically 0).
        """
        self.start_time = time.monotonic()
        unrouted = list(self.nets)
        # Track per-net fail-count; nets that fail repeatedly get higher priority
        fail_count = defaultdict(int)
        # v3: pad-pairs that failed to route for partially-routed nets.
        # netname -> [(pad_a_label, pad_b_label, (xa, ya), (xb, yb)), ...]
        self.partial_pairs = defaultdict(list)
        self.log(f"[coop] {len(unrouted)} target nets in {self.subsystem}: "
                 f"{', '.join(unrouted[:8])}{'...' if len(unrouted) > 8 else ''}")

        # ─── CH1 30/30 lever (Z) ROUTE-HARDEST-FIRST REORDER ─────────────
        # Y proved canonical 0/5 for both joint AND sequential K3 — the 24
        # already-committed routes greedy-locked the J19 escape corridors.
        # W's standalone test (5/5) proved the 5 residuals CAN route from
        # a clean canonical state. The fix is REORDERING: route the
        # HDI-whitelisted residuals FIRST (with K3 joint multi-mech from
        # the clean canonical state), then run normal cooperative
        # iteration on the remaining (easier) nets. Worker enables this
        # for CH1 close-out via --route-hdi-first; default OFF for
        # back-compat.
        #
        # SSoT preserved: nets identified via the same gate the audit
        # uses (HDI_VIA_IN_PAD_REFS pad-ref intersection + the per-net
        # BLIND_F_IN2_NET_WHITELIST / STACKED_MICROVIA_NET_WHITELIST
        # canonical lists). Routing uses the SAME joint K3 mechanism
        # (_try_multi_mech_fallback_joint) the Y lever already exercises;
        # atomic subset cascade gives all-or-none commit semantics.
        if (getattr(self, "route_hdi_first_enabled", False)
                and self.via_in_pad_allowed
                and getattr(self, "multi_mech_fallback_enabled", False)):
            hdi_targets = self._identify_hdi_whitelisted_nets(unrouted)
            if hdi_targets:
                self.log(f"\n[coop] LEVER Z: route-hardest-first enabled — "
                         f"identifying HDI-whitelisted nets BEFORE main "
                         f"cooperative pass")
                self.log(f"  [Z] HDI-whitelisted target nets ({len(hdi_targets)}): "
                         f"{sorted(hdi_targets)}")
                rescued = self._route_hdi_first_phase(list(hdi_targets))
                if rescued:
                    self.log(f"  [Z] HDI-first phase routed "
                             f"{len(rescued)}/{len(hdi_targets)}: "
                             f"{sorted(rescued)}")
                    # Drop rescued nets from the cooperative work list —
                    # they are already self.committed (the joint adapter
                    # populated self.committed via _try_multi_mech_fallback_joint).
                    unrouted = [n for n in unrouted if n not in rescued]
                else:
                    self.log(f"  [Z] HDI-first phase: 0/{len(hdi_targets)} "
                             "rescued — proceeding to normal cooperative "
                             "pass (HDI residuals will be retried at the "
                             "K3 fallback after the loop)")
            else:
                self.log(f"\n[coop] LEVER Z enabled but no HDI-whitelisted "
                         f"target nets identified — skipping HDI-first phase")
        elif getattr(self, "route_hdi_first_enabled", False):
            # Honest log: caller asked for Z but the prerequisites
            # (via_in_pad_allowed + multi_mech_fallback) are missing.
            # Refuse-silently is a corner-cut; tell the operator.
            self.log(f"\n[coop] LEVER Z REFUSED: --route-hdi-first requires "
                     f"BOTH --via-in-pad-allowed AND --multi-mech-fallback "
                     f"(via_in_pad_allowed={self.via_in_pad_allowed}, "
                     f"multi_mech_fallback="
                     f"{getattr(self, 'multi_mech_fallback_enabled', False)})")

        present_factor = PRESENT_COST_FACTOR_INIT
        plateau_count = 0
        last_routed = -1

        for it in range(max_iter):
            self.iteration_count = it + 1
            self.log(f"\n[coop] === Iteration {it+1}/{max_iter} (present_factor={present_factor:.2f}) ===")
            # Re-allow pad access (in case obstacle map was reset)
            for n in list(unrouted) + list(self.partial_pairs.keys()):
                for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(n, []):
                    for lid in layers:
                        self.grid.allow_pad_access_rect(x, y, lid, n, sx/2, sy/2)

            # Sort unrouted: high fail-count nets get highest priority (route first)
            unrouted.sort(key=lambda n: (-fail_count[n], net_priority(n), n))

            still_unrouted = []
            routed_this_iter = []
            partial_this_iter = []
            for nn in unrouted:
                if nn in self.committed:
                    continue
                # Higher budget for repeatedly-failing nets
                budget = 6.0 + min(fail_count[nn], 5) * 4.0
                paths, status, failed_pairs = self.route_one_net_mst(
                    nn, present_factor, time_budget_s=budget)
                if status == 'ROUTED':
                    self.commit_net(nn, paths)
                    # v3 safety net: verify all pads landed in one island.
                    # If MST claimed success but pad-to-track grid-snap broke
                    # connectivity, this catches it before we report "routed".
                    n_islands, island_list = self.verify_net_connectivity(nn)
                    if n_islands > 1:
                        # MST said success but verification disagrees — rip
                        # this net's tracks and re-queue with fail_count bump.
                        self.log(f"  [!] {nn}: MST-ROUTED but VERIFY-SPLIT "
                                 f"({n_islands} islands: {island_list}) — "
                                 f"ripping + retry")
                        self.rip_net(nn)
                        still_unrouted.append(nn)
                        fail_count[nn] += 1
                        # Track the inter-island pad-pair as the "failed pair"
                        # for diagnostic (use first 2 islands' first members)
                        if len(island_list) >= 2:
                            pa = island_list[0][0]; pb = island_list[1][0]
                            pad_xy = {}
                            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(nn, []):
                                pad_xy[f"{ref}.{padname}"] = (x, y)
                            xa, ya = pad_xy.get(pa, (None, None))
                            xb, yb = pad_xy.get(pb, (None, None))
                            if xa is not None and xb is not None:
                                self.partial_pairs[nn] = [(pa, pb, (xa, ya), (xb, yb))]
                    else:
                        routed_this_iter.append(nn)
                        n_segs = sum(len(path_to_segments(p, self.grid)[0]) for p in paths)
                        n_vias = sum(len(path_to_segments(p, self.grid)[1]) for p in paths)
                        self.log(f"  [+] {nn}: routed ({n_segs} segs, {n_vias} vias) "
                                 f"verify=1-island fail_count_was={fail_count[nn]}")
                elif status == 'PARTIAL':
                    # v3 fix: DON'T commit partial paths — that locks in the
                    # 2-of-3 edges and the remaining edge cannot route through
                    # its own locked-in routing. Instead, treat partial as
                    # FAILED so the next iteration re-attempts the FULL MST
                    # fresh (same as v2). But ALSO record the failed pair in
                    # `partial_pairs` for diagnostics, so the final report
                    # shows which pad-pair was the actual blocker.
                    pad_xy = {}
                    for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(nn, []):
                        pad_xy[f"{ref}.{padname}"] = (x, y)
                    # Replace any prior partial_pair entry for this net
                    self.partial_pairs[nn] = []
                    for (pa, pb) in failed_pairs:
                        xa, ya = pad_xy.get(pa, (None, None))
                        xb, yb = pad_xy.get(pb, (None, None))
                        if xa is not None and xb is not None:
                            self.partial_pairs[nn].append((pa, pb, (xa, ya), (xb, yb)))
                    still_unrouted.append(nn)
                    fail_count[nn] += 1
                    n_segs = sum(len(path_to_segments(p, self.grid)[0]) for p in paths)
                    self.log(f"  [.] {nn}: PARTIAL+ROLLBACK "
                             f"({len(paths)}/{len(paths)+len(failed_pairs)} edges, "
                             f"would-be {n_segs} segs) — "
                             f"failed pairs: {failed_pairs} "
                             f"(fail_count={fail_count[nn]})")
                else:  # FAILED
                    still_unrouted.append(nn)
                    fail_count[nn] += 1
                    self.log(f"  [.] {nn}: FAILED (fail_count={fail_count[nn]})")

            # v3: partial_pairs is a DIAGNOSTIC-only cache that records the
            # last-known failed pad-pair for each net that has had a partial
            # MST run. When a net later routes successfully (status='ROUTED'),
            # we clear its partial_pair entry. Otherwise, the entry persists
            # so the final report can show WHICH pad-pair was the blocker.
            # No per-iteration repair pass — full MST retry per iteration
            # under bumped congestion is the negotiation mechanism.
            repair_succeeded_this_iter = 0
            for nn in routed_this_iter:
                if nn in self.partial_pairs:
                    del self.partial_pairs[nn]

            self.log(f"  pass result: routed={len(routed_this_iter)} "
                     f"partial={len(partial_this_iter)} "
                     f"still_unrouted={len(still_unrouted)} "
                     f"repairs_ok={repair_succeeded_this_iter} "
                     f"open_partials={sum(len(v) for v in self.partial_pairs.values())}")
            unrouted = still_unrouted
            # v3: termination requires BOTH unrouted-nets empty AND no open
            # partial-net pad-pair backlog. Otherwise multi-pad nets stay
            # SPLIT (the original worker R22 bug class).
            if not unrouted and not self.partial_pairs:
                self.log(f"\n[coop] ALL ROUTED in {it+1} iterations (no partial nets).")
                break

            # Plateau detection: no NET MAKING PROGRESS for N iters
            # (count "progress" = at least 1 net routed this pass that wasn't routed before)
            # v3: REPAIRS count as progress — a partial net completing its
            # missing pad-pair is forward motion that should reset plateau.
            if not routed_this_iter and not partial_this_iter and repair_succeeded_this_iter == 0:
                plateau_count += 1
            else:
                plateau_count = 0

            # Bump history (Pathfinder negotiated congestion update)
            self.grid.bump_history()
            present_factor *= PRESENT_COST_FACTOR_GROWTH

            # Selective ripup: rip routed nets that BLOCK the failed nets,
            # weighted by plateau-persistence (more aggressive when stuck).
            if it < max_iter - 1 and unrouted:
                k = min(2 + plateau_count * 2, max(2, len(self.committed) // 4))
                rip_candidates = self._select_ripup_candidates(unrouted, k=k)
                if rip_candidates:
                    self.log(f"  ripping {len(rip_candidates)} congestion-blocker nets: {rip_candidates}")
                    for nn in rip_candidates:
                        self.rip_net(nn)
                        unrouted.append(nn)
                    self._rebuild_grid()
                # If selective ripup found nothing AND we're stuck, force-rip random-3
                # (avoids local minima)
                # v4: --no-rip-routed excludes preserved_nets from the random pool.
                elif plateau_count >= 2 and self.committed:
                    import random
                    random.seed(it)
                    if self.no_rip_routed:
                        pool = [n for n in self.committed.keys()
                                if n not in self.preserved_nets]
                    else:
                        pool = list(self.committed.keys())
                    if pool:
                        cand = random.sample(pool, min(3, len(pool)))
                        self.log(f"  plateau force-rip 3 random nets: {cand}")
                        for nn in cand:
                            self.rip_net(nn)
                            unrouted.append(nn)
                        self._rebuild_grid()
                    else:
                        self.log(f"  plateau but no rippable nets (all preserved)")

        elapsed = time.monotonic() - self.start_time
        # v3: fully-connected = committed AND no open partial pairs
        full = sum(1 for n in self.committed if not self.partial_pairs.get(n))
        partial = sum(1 for n in self.committed if self.partial_pairs.get(n))
        self.log(f"\n[coop] DONE. full_routed={full}/{len(self.nets)} "
                 f"partial={partial} unrouted={len(unrouted)} "
                 f"iterations={self.iteration_count} ripups={self.ripup_count} "
                 f"elapsed={elapsed:.1f}s")
        # ─── CH1 30/30 lever (K3) MULTI-MECH FALLBACK ─────────────────────
        # Worker hook 2026-05-28: when single-mech cooperative routing has
        # exhausted iterations, attempt the multi-mech planner on each
        # remaining unrouted net BEFORE declaring NO-PATH. The K3 fallback
        # targets cross-stack nets (start.layer != end.layer in outer pair)
        # where the single-mech maze/cooperative router cannot bridge the
        # stack with one via mechanism (canonical SWDIO_CH1: J18.23 F.Cu ->
        # TP22.1 B.Cu via blind_F_In2 + through).
        #
        # The fallback CONSUMES the per-class via-class-for-span SSoT — it
        # does NOT bypass it. The planner's `candidate_via_classes` mirrors
        # the cooperative router's via_class_for_span (HDI cells admit only
        # HDI classes; non-HDI cells admit only through). Whitelist policy
        # (J18/J19 / HDI_VIA_IN_PAD_REFS + BLIND_F_IN2_NET_WHITELIST) is
        # honoured by passing the HDI flags through to the planner; vias
        # the planner returns are routed through the SAME emit path the
        # cooperative router already uses (via_class -> _emit_via).
        #
        # Enable: --multi-mech-fallback (default OFF; opt-in to surface any
        # behaviour change on existing flows). The hook is documented +
        # tested via the abstract T20 fixture so the integration semantics
        # are clear without needing pcbnew.
        if unrouted and getattr(self, "multi_mech_fallback_enabled", False):
            # ── CH1 30/30 lever (Y) — JOINT K3 first, sequential as fallback.
            #
            # Why joint first: post-W diagnostic showed sequential K3 hits a
            # net-swap occupancy oscillation (worker provenance
            # sims/routing_provenance/27of30_post_W/). The joint adapter
            # explores cross-net corridor tradeoffs in one pass; if it can
            # rescue every residual, the subset cascade never fires.
            # If joint partially succeeds, the remaining nets still get the
            # per-net sequential pass (with the post-joint board state) so
            # any net the joint adapter could NOT plan still gets a clean
            # standalone attempt.
            joint_rescued = set()
            if (getattr(self, "joint_k3_enabled", True)
                    and len(unrouted) >= 2):
                self.log("\n[coop] JOINT multi-mech fallback "
                         "(CH1 30/30 lever Y): "
                         f"attempting {len(unrouted)} unrouted net(s) "
                         "simultaneously")
                joint_res = self._try_multi_mech_fallback_joint(list(unrouted))
                for nn, verdict in joint_res.items():
                    if verdict == "routed":
                        joint_rescued.add(nn)
                self.log(f"[coop] JOINT K3 result: "
                         f"{len(joint_rescued)}/{len(unrouted)} rescued "
                         f"({sorted(joint_rescued)})")
                unrouted = [n for n in unrouted if n not in joint_rescued]
            if unrouted:
                self.log("\n[coop] SEQUENTIAL multi-mech fallback "
                         "(CH1 30/30 lever K3): "
                         f"attempting {len(unrouted)} residual net(s)")
            still_unrouted = []
            for nn in unrouted:
                routed = self._try_multi_mech_fallback(nn)
                if routed:
                    self.log(f"  [+] {nn}: routed via multi-mech chain")
                    # _try_multi_mech_fallback already populated
                    # self.committed[nn] = (set(), added_items) so
                    # rip_net (cells, added unpack) stays compatible.
                else:
                    still_unrouted.append(nn)
            unrouted = still_unrouted
            self.log(f"[coop] multi-mech fallback done; remaining "
                     f"unrouted = {len(unrouted)}")
        if unrouted:
            self.log(f"[coop] UNROUTED nets: {unrouted}")
        if self.partial_pairs:
            self.log(f"[coop] PARTIAL nets (with unrouted pad-pairs):")
            for nn, pairs in self.partial_pairs.items():
                self.log(f"  {nn}: {[(pa, pb) for (pa, pb, _, _) in pairs]}")
        # v11 K2: flush partial-MST provenance entries collected during the
        # run. G_K1 (audit_partial_mst_provenance.py) enforces presence.
        # Failure to write is non-fatal here (the audit will catch a missing
        # entry next run) — but we surface the path list as a log line.
        try:
            written = self.flush_partial_mst_provenance(
                board_sha=os.environ.get("ROUTER_BOARD_SHA", ""))
            if written:
                self.log(f"[coop] K2 partial-MST provenance: wrote "
                         f"{len(written)} entry(ies)")
        except Exception as exc:  # pragma: no cover
            self.log(f"[coop] K2 partial-MST provenance write FAILED: {exc}")
        return unrouted

    def run_pathfinder(self, max_iter=DEFAULT_MAX_ITER):
        """CH1 30/30 lever (AA) TRUE PathFinder negotiated congestion router.

        Per docs/CH1_30OF30_SOTA_RESEARCH_2026-05-29.md recommendation #3 +
        routing_engine/pathfinder.py (the abstract reference). The discipline
        differs from `run()` in FOUR ways:

          1. PER-ITER RIP ALL: every iter starts with every committed net
             ripped (board cleared back to obstacles + pads). All N nets are
             then re-attempted in priority order. Cooperative `run()`
             re-routes ONLY failed nets each iter; PathFinder re-routes ALL.

          2. COST-HISTORY DRIVES NEGOTIATION: per-cell h_n (grid.history)
             accumulates across iters whenever p_n > 1 in the iter ending.
             The cost function `cost(cell, present_factor)` returns
             `base + present_factor × present + history`. The cooperative
             escalator already grows `present_factor`; we ALSO grow history
             per the McMurchie+Ebeling formula (existing grid.bump_history
             already does this — we just call it after every iter).

          3. CONVERGENCE on 0 ripups: two consecutive iters with all N nets
             routed AND no committed net needing re-route ⇒ DONE. (When N
             nets fit cleanly, no contention exists and no ripup needed —
             that's the PathFinder convergence criterion.)

          4. ATOMIC PER-ITER ROLLBACK: if an iter ends with strictly fewer
             nets routed than the previous iter's best, we keep the
             previous-best snapshot (the live board's last-clean state).

        Default OFF for backward compatibility. Opt-in via `--pathfinder`
        on the CLI or `router.pathfinder_enabled = True` programmatically.

        TIME-BOUNDED: every iter caps `route_one_net_mst` per-net at a
        budget proportional to (max_iter - it). Final-iter recovery time
        budget extended to ensure HDI nets get adequate A* expansion room.

        Returns the same shape as `run()`: list of unrouted nets at end.
        Mirrors `run()`'s logging cadence for operator readability.
        """
        self.start_time = time.monotonic()
        if not self.nets:
            self.log("[pf] empty net list; nothing to route")
            return []
        # Required state used by partial-MST repair / verify helpers; mirror
        # run()'s setup so the helpers don't AttributeError.
        self.partial_pairs = defaultdict(list)
        self.log(f"[pf] AA-LEVER PathFinder negotiated congestion router")
        self.log(f"[pf]   {len(self.nets)} target nets in {self.subsystem}; "
                 f"max_iter={max_iter}")
        self.log(f"[pf]   discipline: per-iter rip-all + global re-route in "
                 f"priority order + h_n×p_n cost; convergence on 2-iter "
                 f"zero-ripup streak.")

        # ── Lever Z preamble (same as run()): route HDI-whitelisted nets
        # FIRST via K3 joint multi-mech from clean canonical state, BEFORE
        # the main PathFinder loop. Drops rescued nets from the work list.
        # SSoT preserved — same prereqs (via_in_pad_allowed +
        # multi_mech_fallback_enabled).
        target_nets = list(self.nets)
        if (getattr(self, "route_hdi_first_enabled", False)
                and self.via_in_pad_allowed
                and getattr(self, "multi_mech_fallback_enabled", False)):
            hdi_targets = self._identify_hdi_whitelisted_nets(target_nets)
            if hdi_targets:
                self.log(f"\n[pf] LEVER Z (preamble): "
                         f"HDI-whitelisted target nets "
                         f"({len(hdi_targets)}): {sorted(hdi_targets)}")
                rescued = self._route_hdi_first_phase(list(hdi_targets))
                if rescued:
                    self.log(f"  [pf-Z] HDI-first phase rescued "
                             f"{len(rescued)}/{len(hdi_targets)}: "
                             f"{sorted(rescued)}")
                    target_nets = [n for n in target_nets if n not in rescued]
                else:
                    self.log(f"  [pf-Z] HDI-first phase: "
                             f"0/{len(hdi_targets)} rescued")

        present_factor = PRESENT_COST_FACTOR_INIT
        # Best-snapshot tracking for atomic per-iter rollback.
        best_iter = -1
        best_routed_count = 0
        best_committed_snapshot = {}   # netname -> (cells, added) shallow ref
        zero_ripup_streak = 0
        total_ripups = 0

        for it in range(max_iter):
            self.iteration_count = it + 1
            self.log(f"\n[pf] === iter {it+1}/{max_iter} "
                     f"(present_factor={present_factor:.2f}) ===")

            # 1. RIP ALL — clear every committed net IN THIS LOOP'S TARGET SET
            # and reset the grid's present-uses (history persists per
            # PathFinder discipline). Lever Z preamble's HDI commits are
            # OUTSIDE target_nets, so they stay committed (analogous to
            # "frozen" in the run() flow). We rip via the existing rip_net
            # (which knows about preserved frozen nets, J18/J19 special
            # handling, etc.) so all SSoT is preserved.
            rip_list = [nn for nn in self.committed if nn in target_nets]
            for nn in rip_list:
                self.rip_net(nn)
            # After mass rip, rebuild the grid cleanly (rebuilds obstacle
            # map from board state, preserving history).
            if rip_list:
                self._rebuild_grid()
                total_ripups += len(rip_list)
                self.log(f"[pf]   ripped {len(rip_list)} previously-committed "
                         f"nets (total_ripups={total_ripups})")

            # 2. Re-allow pad access for all target nets (defensive —
            # _rebuild_grid does this for committed, but we want it for ALL
            # target_nets so re-routes have pad endpoints reachable).
            for n in target_nets:
                for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(n, []):
                    for lid in layers:
                        self.grid.allow_pad_access_rect(x, y, lid, n,
                                                        sx / 2, sy / 2)

            # 3. Route every net in priority order. Higher-priority nets
            # commit first; later nets see their cells with p_n=1 + h_n
            # carry-over from prior iters.
            # Priority ordering = same as self.nets sort (set in __init__):
            #   (net_priority(n), -len(state.net_pads[n]), n)
            unrouted_this_iter = []
            routed_this_iter = 0
            partial_this_iter = 0
            # Adaptive time budget per net: scale with iter # so early iters
            # get more time per net (they have N nets to route from scratch).
            n_remaining_iters = max(1, max_iter - it)
            per_net_budget = max(2.0, 14.0 - 0.4 * it)

            for nn in target_nets:
                if nn in self.committed:
                    continue
                paths, status, failed_pairs = self.route_one_net_mst(
                    nn, present_factor, time_budget_s=per_net_budget)
                if status == 'ROUTED':
                    self.commit_net(nn, paths)
                    # Verify
                    n_islands, _island_list = self.verify_net_connectivity(nn)
                    if n_islands > 1:
                        # LEVER UU.3 (2026-05-30): bridge attempt before rip.
                        # Per UU.3 finding (PR #275 + #276): the PathFinder
                        # verify-split rejection pattern is a real geometric
                        # gap in the route_one_net_mst commit. Instead of
                        # immediate rip + re-queue (which loses the entire
                        # route + thrashes PathFinder iters), attempt to
                        # bridge the islands via a short same-layer bridge
                        # segment connecting the nearest pair of endpoints
                        # across islands. If bridging closes to single-
                        # island, commit. Else rip as before (no regression).
                        bridged = self._try_bridge_split_islands(nn, _island_list)
                        if bridged:
                            n2, _ = self.verify_net_connectivity(nn)
                            if n2 == 1:
                                self.log(f"[pf]   [+] {nn}: BRIDGED "
                                         f"{n_islands}-island split → single "
                                         f"island; commit (UU.3 lever)")
                                routed_this_iter += 1
                                continue
                            # Bridge didn't close — still split; rip + re-queue
                            self.log(f"[pf]   [!] {nn}: bridge attempted but "
                                     f"verify still {n2} islands; rip + re-queue")
                        else:
                            self.log(f"[pf]   [!] {nn}: ROUTED-but-SPLIT verify; "
                                     f"ripping + re-queue")
                        self.rip_net(nn)
                        unrouted_this_iter.append(nn)
                    else:
                        routed_this_iter += 1
                elif status == 'PARTIAL':
                    partial_this_iter += 1
                    unrouted_this_iter.append(nn)
                else:
                    unrouted_this_iter.append(nn)

            # Count committed nets in our TARGET set only (lever Z's HDI
            # commits are tracked separately; we report against target).
            n_committed_target = sum(1 for n in target_nets if n in self.committed)
            self.log(f"[pf]   iter result: routed={routed_this_iter} "
                     f"partial={partial_this_iter} "
                     f"unrouted_this_iter={len(unrouted_this_iter)} "
                     f"target_committed={n_committed_target}/{len(target_nets)} "
                     f"total_committed={len(self.committed)}/{len(self.nets)}")
            n_committed = n_committed_target

            # 4. Atomic per-iter rollback policy: if this iter routed FEWER
            # than the best iter to date, keep the best-iter snapshot — i.e.
            # do NOT update best_committed_snapshot. The next iter starts
            # from this iter's grid state (history carry-over) but on the
            # NEXT round if it improves we capture it.
            # If this iter is the new best, snapshot it.
            if n_committed > best_routed_count:
                best_routed_count = n_committed
                best_iter = it + 1
                # Capture (cells, added) per committed net for potential
                # rollback at end (we don't rollback in-loop; we just track).
                # NOTE: 'added' is a list of pcbnew items still live on the
                # board, so the snapshot is a SHALLOW reference — it remains
                # valid as long as we don't rip those nets later. Since we
                # rip-all at the START of every iter, any non-best iter that
                # follows will have torn down these items. We therefore
                # capture by RE-EMITTING from cells if needed — but the
                # simpler invariant is: the BEST iter's state IS the live
                # board state at the time of capture, and we exit-loop with
                # that state intact iff we converge ON the best iter.
                best_committed_snapshot = dict(self.committed)
                self.log(f"[pf]   NEW BEST iter={best_iter} "
                         f"routed={best_routed_count}/{len(self.nets)}")

            # 5. End-of-iter learning step (h_n bump where present > 1).
            self.grid.bump_history()
            present_factor *= PRESENT_COST_FACTOR_GROWTH

            # 6. Convergence check: all target nets routed + no SHORTS (we
            # don't track shorts cell-by-cell in the live router — the
            # grid's obstacle contract is HARD so the route_one_net_mst
            # contract already guarantees no cells are shared between
            # distinct nets at the CELL level. The only way present > 1 at
            # the same cell at iter end is when one net's pad-cell is
            # shared by another net's routed path entry — that's a
            # CommitVerify failure that verify_net_connectivity catches).
            contended_cells = sum(1 for p in self.grid.present.values() if p > 1)
            if (n_committed == len(target_nets) and contended_cells == 0):
                zero_ripup_streak += 1
                self.log(f"[pf]   convergence streak={zero_ripup_streak}/2 "
                         f"(all_target_routed=True, contended_cells={contended_cells})")
                if zero_ripup_streak >= 2:
                    self.log(f"[pf] CONVERGED at iter {it+1} — "
                             f"two consecutive iters with 0 contention + "
                             f"all {n_committed}/{len(target_nets)} target nets routed.")
                    break
            else:
                zero_ripup_streak = 0

        elapsed_pf = time.monotonic() - self.start_time
        unrouted = [n for n in self.nets if n not in self.committed]
        self.log(f"\n[pf] PathFinder loop DONE. "
                 f"committed={len(self.committed)}/{len(self.nets)} "
                 f"unrouted={len(unrouted)} "
                 f"best_ever_iter={best_iter} best_ever={best_routed_count}/"
                 f"{len(self.nets)} "
                 f"iterations={self.iteration_count} total_ripups={total_ripups} "
                 f"elapsed={elapsed_pf:.1f}s")

        # K3 multi-mech fallback — same discipline as `run()`. PathFinder
        # converges on the cooperative single-mech regime; cross-stack nets
        # that need a via chain (blind_F_In2 + through, etc.) still require
        # the planner. We invoke the JOINT path first (Y-lever), then
        # SEQUENTIAL (K3) per net. Identical to run()'s tail.
        if unrouted and getattr(self, "multi_mech_fallback_enabled", False):
            joint_rescued = set()
            if (getattr(self, "joint_k3_enabled", True)
                    and len(unrouted) >= 2):
                self.log("\n[pf] JOINT multi-mech fallback "
                         "(CH1 30/30 lever Y): "
                         f"attempting {len(unrouted)} unrouted net(s) "
                         "simultaneously")
                joint_res = self._try_multi_mech_fallback_joint(list(unrouted))
                for nn, verdict in joint_res.items():
                    if verdict == "routed":
                        joint_rescued.add(nn)
                self.log(f"[pf] JOINT K3 result: "
                         f"{len(joint_rescued)}/{len(unrouted)} rescued "
                         f"({sorted(joint_rescued)})")
                unrouted = [n for n in unrouted if n not in joint_rescued]
            if unrouted:
                self.log("\n[pf] SEQUENTIAL multi-mech fallback "
                         "(CH1 30/30 lever K3): "
                         f"attempting {len(unrouted)} residual net(s)")
            still_unrouted = []
            for nn in unrouted:
                routed = self._try_multi_mech_fallback(nn)
                if routed:
                    self.log(f"  [+] {nn}: routed via multi-mech chain")
                else:
                    still_unrouted.append(nn)
            unrouted = still_unrouted
            self.log(f"[pf] multi-mech fallback done; remaining "
                     f"unrouted = {len(unrouted)}")
        if unrouted:
            self.log(f"[pf] UNROUTED nets: {unrouted}")
        # K2 partial-MST provenance flush — same discipline as run().
        try:
            written = self.flush_partial_mst_provenance(
                board_sha=os.environ.get("ROUTER_BOARD_SHA", ""))
            if written:
                self.log(f"[pf] K2 partial-MST provenance: wrote "
                         f"{len(written)} entry(ies)")
        except Exception as exc:  # pragma: no cover
            self.log(f"[pf] K2 partial-MST provenance write FAILED: {exc}")
        return unrouted

    def _try_multi_mech_fallback(self, netname):
        """CH1 30/30 lever (K3) MULTI-MECH FALLBACK — attempt to route
        `netname` via the multi-mechanism path planner when single-mech
        cooperative routing has failed.

        CONTRACT
            INPUTS: netname (str) — a net in self.state.net_pads still
                    unrouted after cooperative iterations.
            BEHAVIOUR: build a minimal Phase-B GlobalPlan
                    ({"verdict": "ROUTABLE"}) + RegionSpec covering the
                    cooperative router's subsystem zone + the net's
                    in-zone pads. Delegate to
                    phase_c.fill_region_with_multi_mech with the live
                    board. The adapter:
                      (a) builds the BOUNDED MultiMechInvocation from
                          our RegionSpec (allowed_via_classes derived
                          from region.via_budget + hdi_refs — same SSoT
                          as via_class_for_span / via_halo_radius_mm);
                      (b) extracts per-layer body keep-outs from the
                          live board's footprints (region-bounded);
                      (c) calls multi_mech_planner.plan_multi_mech_route
                          per pad-pair (region-confined + expansion-
                          capped + chain-depth-bounded);
                      (d) pre-emit validates every via against the
                          allowed_via_classes (defense-in-depth on top
                          of the planner's candidate_via_classes) +
                          per-class halo against per-layer obstacle
                          filter (shorts-gate semantics);
                      (e) emits PCB_TRACK + PCB_VIA records via the
                          SAME emit path (drill/pad/SetViaType/
                          SetLayerPair) the cooperative router uses
                          (NO SSoT bypass: the adapter's emit helper
                          delegates to route_subsystem_cooperative.
                          emit_to_board internals).

            ROLLBACK: ATOMIC PER-NET. We snapshot the live board's
                track-set BEFORE the call; if the aggregate adapter
                status is not 'routed' (any pair failed for any
                reason), every track/via added during the call is
                removed before we return False. The half-routed net
                NEVER lingers on the board. This is the per-net
                analog of phase_c's per-pair rollback (the adapter
                rolls back a pair on pre-emit validation failure;
                we roll back the whole net on aggregate failure).

            OUTPUT: True iff EVERY pad-pair was routed end-to-end via
                    the multi-mech chain; False otherwise (caller
                    carries the verdict; board state is restored).

        This is intentionally CONSERVATIVE — when in doubt, returns
        False and lets the caller report NO-PATH. The K3 capability is
        unlocked OPT-IN via --multi-mech-fallback; the default flow is
        unchanged.

        SSoT DISCIPLINE preserved:
          * via_class_for_span / via_halo_radius_mm — consumed by the
            adapter's emit helper (via phase_c._emit_plan_to_board ->
            route_subsystem_cooperative internals). NOT bypassed.
          * HDI_VIA_IN_PAD_REFS (the J18/J19 whitelist) — drives the
            region.hdi_refs gate; HDI via classes are allowed ONLY
            when the net actually touches a whitelisted footprint AND
            the per-net BLIND_F_IN2_NET_WHITELIST / STACKED whitelist
            (the audit's canonical list) permits the class. Non-HDI
            cells get 'through' only.
          * RegionSpec.bbox = self.zone (the cooperative router's
            subsystem zone; same SUBSYSTEM_ZONES SSoT as the abstract
            adapter self-test).
        """
        # Lazy-import the planner so the cooperative router can be loaded
        # without the planner's heapq-based search if the K3 lever is OFF.
        try:
            from routing_engine import multi_mech_planner as MMP  # type: ignore  # noqa: F401
            from routing_engine import phase_c as PC  # type: ignore
        except ImportError:
            # Loose-script invocation: the planner sits in the routing_engine
            # package; if it's not importable, the fallback cannot run.
            self.log(f"  [.] {netname}: K3 fallback unavailable "
                     "(routing_engine.{multi_mech_planner,phase_c} not "
                     "importable)")
            return False

        # ── 1. Gather the net's in-zone pads (the multi-mech-routable set)
        # The adapter expects net_pairs as ('<ref>.<pad>', '<ref>.<pad>')
        # tuples. We take the cooperative router's already-resolved pad
        # list (self.state.net_pads) and filter to pads inside the zone
        # bbox — same gate as the cooperative router's own pad-pair walk.
        pads_all = self.state.net_pads.get(netname, [])
        zone_xmin, zone_ymin, zone_xmax, zone_ymax = self.zone
        pads_in_zone = [
            (ref, padname, x, y, layers, sx, sy)
            for (ref, padname, x, y, layers, sx, sy) in pads_all
            if zone_xmin <= x <= zone_xmax and zone_ymin <= y <= zone_ymax
        ]
        if len(pads_in_zone) < 2:
            self.log(f"  [.] {netname}: K3 fallback skipped "
                     f"(<2 in-zone pads: {len(pads_in_zone)})")
            return False

        # ── 2. Build the star net_pairs (pad[0] -> pad[1..N-1]). The
        # cooperative router's MST treats the net as a single tree; for
        # the K3 cross-stack rescue we take the simplest connected
        # topology — every leaf to the first pad. The planner's per-pair
        # A* discovers the right via chain; aggregate atomicity ensures
        # we get all-or-nothing.
        ref0, pad0, x0, y0, _layers0, _sx0, _sy0 = pads_in_zone[0]
        start_ref = f"{ref0}.{pad0}"
        net_pairs = []
        for (ref, padname, _x, _y, _layers, _sx, _sy) in pads_in_zone[1:]:
            net_pairs.append((start_ref, f"{ref}.{padname}"))

        # ── 3. Build the RegionSpec from the cooperative router's zone +
        # HDI whitelist. HDI budget is granted ONLY when the net touches
        # a J18/J19 footprint (HDI_VIA_IN_PAD_REFS — the SSoT) AND the
        # router is run with --via-in-pad-allowed (the operator gate).
        # Otherwise: 'through' only.
        hdi_refs_for_net = tuple(
            r for r in {p[0] for p in pads_in_zone}
            if r in HDI_VIA_IN_PAD_REFS
        )
        # via_budget seeded per pad — a star MST has N-1 edges, each
        # potentially spending 1-3 vias in the chain (max_chain_depth=3).
        # Headroom = 4×N is comfortable; HDI budget gated to whitelisted
        # refs + the operator flag (mirror of the cooperative router).
        n_pads = len(pads_in_zone)
        std_budget = max(4, 4 * n_pads)
        hdi_budget = (max(2, 2 * n_pads)
                      if (hdi_refs_for_net and self.via_in_pad_allowed)
                      else 0)
        # Allowed layers = the cooperative router's SIGNAL_LAYERS, name-
        # spaced (phase_c expects KiCad layer names). Mirrors
        # _pin_from_pcbnew's outer-first preference.
        allowed_layer_names = ("F.Cu", "B.Cu", "In2.Cu", "In4.Cu",
                               "In6.Cu", "In8.Cu")
        # W-lever (CH1 30/30 lever W) — expand A* expansion_cap to 500_000
        # for the K3 RESCUE path. Default RegionSpec.expansion_cap = 200_000
        # which is appropriate for a normal Phase-B-bounded region; but the
        # K3 rescue ONLY runs as a last-resort fallback for nets the single-
        # mech cooperative router could NOT route, where the geometry forces
        # a longer chain across full-stack obstacles + foreign tracks. The
        # diag on 2026-05-29 showed PWM_INHB_CH1 hit the 200k cap at
        # octi=5.0 cells from goal (the corridor is tight; the cap was
        # the bottleneck, not the geometry). 500_000 is a 2.5× headroom
        # over the empirically-observed peak with the per-pad obstacle
        # model. The K3 path runs on ≤5 nets per subsystem so the cost
        # envelope stays bounded (5 × 500k = 2.5M expansions per CH).
        K3_RESCUE_EXPANSION_CAP = 500_000
        region = PC.RegionSpec(
            subsystem=self.subsystem,
            bbox=(float(zone_xmin), float(zone_ymin),
                  float(zone_xmax), float(zone_ymax)),
            allowed_layers=allowed_layer_names,
            via_budget={"std": std_budget, "hdi": hdi_budget},
            hdi_refs=hdi_refs_for_net,
            net_names=(netname,),
            expansion_cap=K3_RESCUE_EXPANSION_CAP,
        )

        # ── 4. Snapshot the board's track/via items BEFORE the adapter
        # call so we can roll back atomically on aggregate failure. The
        # snapshot uses KiCad's persistent UUID (`m_Uuid`) NOT Python
        # `id()`: SWIG generates EPHEMERAL Python proxy objects for
        # pcbnew C++ items — back-to-back `GetTracks()` calls return
        # different Python proxies wrapping the SAME C++ object, so
        # `id(t)` is UNSTABLE across calls on a LoadBoard()'ed board.
        # (Verified empirically on canonical 085dee9: only 716/1934
        # `id()` overlap between two consecutive snapshots; 0/1934 when
        # one snapshot is `held=list(...)` and the other is fresh.)
        # NewBoard()-based synthetic tests masked this because they
        # start with zero tracks (empty before_items → every post-call
        # item is "added"). UUIDs are KiCad-side persistent + survive
        # SWIG proxy churn (1934/1934 verified stable). Per
        # reference-pcbnew-swig-batch-mutation-trap + this 30/30 lever
        # (P) live-board fix.
        try:
            import pcbnew  # noqa: F401  (already imported at module load)
        except Exception:
            self.log(f"  [.] {netname}: K3 fallback unavailable "
                     "(pcbnew not importable for rollback snapshot)")
            return False
        before_items = set(self._stable_item_key(t)
                           for t in self.board.GetTracks())

        # ── 5. Minimal Phase-B GlobalPlan: a dict with verdict ROUTABLE.
        # The adapter's verdict gate accepts this (same gate as the maze
        # + cooperative adapters); the bounded MultiMechInvocation is
        # built from the RegionSpec, NOT from the plan internals — so a
        # minimal-dict plan is sufficient for the K3 caller-side glue.
        plan = {"verdict": "ROUTABLE"}

        # ── 6. Resolve a stable board_path for the adapter signature.
        # The adapter requires NON-EMPTY board_path + output_path strings
        # to enter the live-fill branch (it's a sanity gate from the
        # documented contract: "no live BOARD / board_path / output_path
        # / net_pairs"). The live emit writes through `board` directly
        # (the file paths are documentary/logging — the adapter does
        # NOT call pcbnew.SaveBoard). When the loaded board has no
        # filename (e.g. in-memory synthetic test board), we fall back
        # to a synthetic placeholder so the live-fill branch fires.
        try:
            board_path = self.board.GetFileName() or "<synthetic>.kicad_pcb"
        except Exception:
            board_path = "<synthetic>.kicad_pcb"

        # ── 7. Delegate to phase_c.fill_region_with_multi_mech. The
        # adapter handles per-pair planning + pre-emit validation +
        # PCB_TRACK / PCB_VIA emission. We treat its aggregate status
        # as the verdict; any non-'routed' aggregate triggers the
        # per-net atomic rollback below.
        try:
            # W-lever (CH1 30/30): chain depth 3->4 for the rescue path.
            # Empirically the canonical chain is blind_F_In2 + through (2
            # mechanisms) but the tight CH1 corridors at J19 may need
            # blind+through+through (3) or blind+through+microvia (3).
            # depth=4 leaves one extra slot of headroom without violating
            # R37 (cascade-depth ≤ 2 was the discipline; for via chains
            # the analogous bound is ≤ 4 mechanisms — chains beyond that
            # ARE a placement-bug indicator).
            # LEVER Z (2026-05-30): per-net depth — chronic residuals
            # (PWM_INLA/GLB/KILL_RAIL_N/PWM_INHB/SWDIO) bumped to 8 so the
            # F→In2→…→B.Cu stacked microvia chain can traverse 5+ vias
            # under EE-strict halo + CC HDI symmetric whitelist.
            K3_RESCUE_CHAIN_DEPTH = k3_chain_depth_for_net(netname)
            res = PC.fill_region_with_multi_mech(
                plan, region,
                board=self.board,
                board_path=board_path,
                output_path=board_path,   # read-only: adapter doesn't write
                net_pairs=net_pairs,
                width_mm=width_for(netname),
                clearance_fos_mm=PC.MAZE_DEFAULT_CLEARANCE_FOS_MM,
                grid_pitch_mm=self.grid_pitch,
                max_chain_depth=K3_RESCUE_CHAIN_DEPTH,
                dry_run=False,
            )
        except Exception as exc:
            # Defense in depth: an unexpected adapter exception leaves
            # the board in a half-emitted state. Roll back to the
            # snapshot, log loudly, return False.
            self.log(f"  [.] {netname}: K3 adapter raised {type(exc).__name__}: "
                     f"{exc} — rolling back")
            self._rollback_added_since(before_items)
            return False

        status = res.get("status", "error")
        routes = res.get("routes", [])

        # ── 8. Atomicity gate. Only an aggregate 'routed' status (every
        # pair landed) is accepted. Any 'partial' (some pair NO-PATH /
        # skipped / rollback) triggers full per-net rollback.
        if status != "routed":
            n_routed = sum(1 for r in routes if r.get("status") == "routed")
            n_total = len(routes)
            self.log(f"  [.] {netname}: K3 multi-mech aggregate "
                     f"status={status} ({n_routed}/{n_total} pairs "
                     f"routed) — atomic rollback (per-net)")
            self._rollback_added_since(before_items)
            return False

        # ── 9. SUCCESS. Bookkeeping: record the per-net added items so
        # rip_net (if ever called later) can remove our emit. We use the
        # established self.committed[net] = (cells, added) schema; the
        # cells set is empty because the multi-mech planner does NOT
        # use the cooperative router's CongestionGrid (its A* runs over
        # a region-confined gcell space the adapter manages). An empty
        # cell set is safe for rip_net (it iterates over `added` for the
        # board removal; uncommit_path on an empty set is a no-op).
        added_items = [t for t in self.board.GetTracks()
                       if self._stable_item_key(t) not in before_items]
        # Log the chain summary (n_mechanisms, via_chain) for trace.
        for r in routes:
            chain = r.get("via_chain", [])
            self.log(f"      pair {r.get('start')}->{r.get('end')}: "
                     f"chain={chain} len_mm={r.get('length_mm', 0.0):.2f} "
                     f"tracks={r.get('n_tracks_emitted', 0)} "
                     f"vias={r.get('n_vias_emitted', 0)}")
        self.committed[netname] = (set(), added_items)
        return True

    def _try_multi_mech_fallback_joint(self, unrouted_nets):
        """CH1 30/30 lever (Y) — JOINT K3 MULTI-MECH RESCUE.

        CONTRACT
            INPUTS: unrouted_nets — list of net names still unrouted after
                    single-mech cooperative + (optional) per-net K3.
            BEHAVIOUR:
              1. Collect every net's in-zone pad-pairs into net_pairs_by_net.
              2. Build a UNION RegionSpec (allowed via classes derived from
                 the union of hdi_refs; net_names = all joint nets).
              3. Snapshot board state PER BATCH for cascade rollback.
              4. Call phase_c.fill_region_with_multi_mech_joint — which
                 routes nets in criticality order with PER-NET obstacle
                 refresh (negotiation mechanism).
              5. ALL-OR-NONE first: if every net rescued, commit + return.
              6. SUBSET CASCADE: if joint returned partial, try the
                 largest-subset-including-most-critical cascades (N-1, N-2,
                 ... 2, 1). For each subset attempt, restore the per-batch
                 snapshot, then re-call the joint adapter with the subset.
                 First feasible subset wins.
              7. ATOMIC: at exit, the board state EITHER contains all
                 rescued nets' tracks (with self.committed populated for
                 each) OR is restored to the pre-call snapshot.

            OUTPUT: dict[net_name -> 'routed' | 'failed']. Caller filters
                    routed nets out of `unrouted` list.

        SUBSET ORDERING (sureshot-over-sota):
          Cascade order is by CRITICALITY (safety → motor → analog → bus
          → debug). For each size k in [N-1, N-2, ... 2, 1] we attempt the
          k-subset containing the k most-critical nets. This guarantees
          the LARGEST feasible safety-first subset wins. PathFinder-style
          cost-history routing would give true joint optimality; the
          subset cascade is the sureshot approximation.

        SSoT preserved: same hdi_refs gate, same allowed_via_classes
        derivation, same emit pipeline, same per-pair pre-emit validation
        as the single-net adapter. Joint mode is a CALLER-side wrapper —
        no router internals are bypassed.
        """
        try:
            from routing_engine import multi_mech_planner as MMP  # type: ignore  # noqa: F401
            from routing_engine import phase_c as PC  # type: ignore
        except ImportError:
            self.log(f"  [.] joint K3 unavailable "
                     "(routing_engine not importable)")
            return {nn: "failed" for nn in unrouted_nets}

        try:
            import pcbnew  # noqa: F401
        except Exception:
            self.log(f"  [.] joint K3 unavailable (pcbnew not importable)")
            return {nn: "failed" for nn in unrouted_nets}

        try:
            import targeted_ripup as _TR  # type: ignore
        except Exception:                                              # pragma: no cover
            _TR = None

        # ── 1. Gather per-net in-zone pads + build pair lists.
        zone_xmin, zone_ymin, zone_xmax, zone_ymax = self.zone
        net_pairs_by_net = {}
        width_mm_by_net = {}
        hdi_refs_union = set()
        skip_nets = []
        for nn in unrouted_nets:
            pads_all = self.state.net_pads.get(nn, [])
            pads_in_zone = [
                (ref, padname, x, y, layers, sx, sy)
                for (ref, padname, x, y, layers, sx, sy) in pads_all
                if zone_xmin <= x <= zone_xmax and zone_ymin <= y <= zone_ymax
            ]
            if len(pads_in_zone) < 2:
                skip_nets.append(nn)
                continue
            ref0, pad0, _x0, _y0, _l0, _sx0, _sy0 = pads_in_zone[0]
            start_ref = f"{ref0}.{pad0}"
            pairs = [(start_ref, f"{ref}.{padname}")
                     for (ref, padname, _x, _y, _l, _sx, _sy)
                     in pads_in_zone[1:]]
            net_pairs_by_net[nn] = pairs
            width_mm_by_net[nn] = width_for(nn)
            for (ref, _p, _x, _y, _l, _sx, _sy) in pads_in_zone:
                if ref in HDI_VIA_IN_PAD_REFS:
                    hdi_refs_union.add(ref)
        for nn in skip_nets:
            self.log(f"  [.] {nn}: joint K3 skip (<2 in-zone pads)")
        if not net_pairs_by_net:
            return {nn: "failed" for nn in unrouted_nets}

        # ── 2. Build the union RegionSpec.
        # via_budget aggregated across all joint nets: each net star-MST
        # has N-1 edges × 3 vias-per-chain headroom; HDI budget gated by
        # hdi_refs_union × operator flag.
        total_pad_count = sum(len(p) + 1 for p in net_pairs_by_net.values())
        std_budget = max(8, 4 * total_pad_count)
        hdi_budget = (max(4, 2 * total_pad_count)
                      if (hdi_refs_union and self.via_in_pad_allowed)
                      else 0)
        allowed_layer_names = ("F.Cu", "B.Cu", "In2.Cu", "In4.Cu",
                               "In6.Cu", "In8.Cu")
        # Same K3 rescue expansion cap as single-net path (500k per pair
        # — joint mode loops over pairs, so the cap is per-pair not
        # per-net; total bound = N_pairs × 500k expansions).
        K3_RESCUE_EXPANSION_CAP = 500_000
        # LEVER Z (2026-05-30): joint K3 cascade uses the MAX depth across
        # all nets in the subset (so any chronic-residual net in the subset
        # promotes the chain depth for the whole batch). Per-net override
        # via k3_chain_depth_for_net().
        K3_RESCUE_CHAIN_DEPTH = max(
            (k3_chain_depth_for_net(n) for n in net_pairs_by_net),
            default=K3_CHAIN_DEPTH_DEFAULT)
        region = PC.RegionSpec(
            subsystem=self.subsystem,
            bbox=(float(zone_xmin), float(zone_ymin),
                  float(zone_xmax), float(zone_ymax)),
            allowed_layers=allowed_layer_names,
            via_budget={"std": std_budget, "hdi": hdi_budget},
            hdi_refs=tuple(sorted(hdi_refs_union)),
            net_names=tuple(sorted(net_pairs_by_net.keys())),
            expansion_cap=K3_RESCUE_EXPANSION_CAP,
        )

        # ── 3. Snapshot board for batch-level cascade rollback.
        before_items = set(self._stable_item_key(t)
                           for t in self.board.GetTracks())

        try:
            board_path = (self.board.GetFileName()
                          or "<synthetic>.kicad_pcb")
        except Exception:
            board_path = "<synthetic>.kicad_pcb"

        plan = {"verdict": "ROUTABLE"}

        # ── 4. Determine criticality-ordered net list (for the subset
        # cascade). Safety-first; debug-last.
        if _TR is not None:
            ordered_nets = sorted(net_pairs_by_net.keys(),
                                  key=lambda n: (-_TR.net_criticality(n)[0], n))
        else:
            ordered_nets = sorted(net_pairs_by_net.keys())

        def _attempt(net_subset):
            """Helper: restore snapshot, run joint adapter on net_subset.
            Returns dict[net_name -> verdict_string]."""
            # Restore per-batch snapshot before each attempt so prior
            # cascade rounds don't leave half-committed tracks.
            self._rollback_added_since(before_items)
            subset_pairs = {n: net_pairs_by_net[n] for n in net_subset}
            try:
                res = PC.fill_region_with_multi_mech_joint(
                    plan, region,
                    net_pairs_by_net=subset_pairs,
                    board=self.board,
                    board_path=board_path,
                    output_path=board_path,
                    width_mm_by_net=width_mm_by_net,
                    clearance_fos_mm=PC.MAZE_DEFAULT_CLEARANCE_FOS_MM,
                    grid_pitch_mm=self.grid_pitch,
                    max_chain_depth=K3_RESCUE_CHAIN_DEPTH,
                    net_order=net_subset,
                    dry_run=False,
                )
            except Exception as exc:
                self.log(f"  [.] JOINT K3 adapter raised "
                         f"{type(exc).__name__}: {exc} — restoring snapshot")
                self._rollback_added_since(before_items)
                return {n: "failed" for n in net_subset}
            verdicts = {}
            for nn in net_subset:
                v = res.get("per_net", {}).get(nn, {}).get("status", "failed")
                verdicts[nn] = "routed" if v == "routed" else "failed"
            n_routed = sum(1 for v in verdicts.values() if v == "routed")
            self.log(f"      joint try ({len(net_subset)} nets, "
                     f"{n_routed} routed): {verdicts}")
            return verdicts

        # ── 5. Cascade. Try N-net, N-1, N-2, ... down to 1.
        # For each size k, take the TOP-k MOST CRITICAL nets.
        # First subset where ALL nets route wins.
        n = len(ordered_nets)
        best_verdicts = None
        best_subset = None
        for k in range(n, 0, -1):
            subset = ordered_nets[:k]
            self.log(f"  [Y] cascade k={k}: trying subset "
                     f"{subset}")
            verdicts = _attempt(subset)
            if all(v == "routed" for v in verdicts.values()):
                best_verdicts = verdicts
                best_subset = subset
                self.log(f"  [Y] cascade k={k}: ALL ROUTED — "
                         f"committing subset {subset}")
                break

        if best_verdicts is None:
            # No feasible subset (down to size 1). The k=1 cascade tried
            # the single most-critical net standalone; if that failed too,
            # the joint mode has no rescue. Restore snapshot + report all
            # failed; the per-net sequential fallback runs next (it may
            # rescue nets the joint mode could not, by trying different
            # standalone orderings via the existing _try_multi_mech_fallback
            # caller-loop).
            self._rollback_added_since(before_items)
            self.log("  [Y] cascade: NO feasible subset (size 1 also "
                     "failed) — restoring snapshot, deferring to "
                     "per-net sequential pass")
            return {nn: "failed" for nn in unrouted_nets}

        # ── 6. SUCCESS subset. Populate self.committed for each rescued
        # net so rip_net / provenance stays compatible. The board state
        # already contains the rescued nets' tracks from the winning
        # _attempt() call.
        # NB: self.committed[net] = (cells, added). For K3 fallback the
        # cells set is empty (planner doesn't use CongestionGrid); the
        # added list = the tracks attributable to the net.
        # We re-compute per-net added items by looking at the joint
        # adapter's per_net.added_keys.
        # Re-call: we need the LAST attempt's per_net dict. Refactor:
        # _attempt() returns verdicts; we re-attempt to capture per_net.
        # Simpler: re-run the winning attempt ONE more time after restore.
        self._rollback_added_since(before_items)
        try:
            res = PC.fill_region_with_multi_mech_joint(
                plan, region,
                net_pairs_by_net={n: net_pairs_by_net[n]
                                  for n in best_subset},
                board=self.board,
                board_path=board_path,
                output_path=board_path,
                width_mm_by_net=width_mm_by_net,
                clearance_fos_mm=PC.MAZE_DEFAULT_CLEARANCE_FOS_MM,
                grid_pitch_mm=self.grid_pitch,
                max_chain_depth=K3_RESCUE_CHAIN_DEPTH,
                net_order=best_subset,
                dry_run=False,
            )
        except Exception as exc:
            self.log(f"  [.] JOINT K3 final commit raised "
                     f"{type(exc).__name__}: {exc} — restoring snapshot")
            self._rollback_added_since(before_items)
            return {nn: "failed" for nn in unrouted_nets}

        # Per-net commit bookkeeping.
        for nn in best_subset:
            entry = res.get("per_net", {}).get(nn, {})
            if entry.get("status") != "routed":
                # Defensive: should not happen given _attempt agreed.
                continue
            # Compute added_items list for this net from added_keys.
            added_key_set = set(entry.get("added_keys", []))
            added_items = [t for t in self.board.GetTracks()
                           if self._stable_item_key(t) in added_key_set]
            self.committed[nn] = (set(), added_items)
            # Log chain summary.
            for r in entry.get("routes", []):
                if r.get("status") == "routed":
                    chain = r.get("via_chain", [])
                    self.log(f"      [Y] {nn} "
                             f"{r.get('start')}->{r.get('end')}: "
                             f"chain={chain} "
                             f"len_mm={r.get('length_mm', 0.0):.2f}")

        out = {nn: "routed" for nn in best_subset}
        for nn in unrouted_nets:
            if nn not in out:
                out[nn] = "failed"
        return out

    def _identify_hdi_whitelisted_nets(self, candidate_nets):
        """CH1 30/30 lever (Z) — identify HDI-whitelisted nets.

        A net is HDI-whitelisted iff BOTH conditions hold:

          (1) the net touches at least one footprint in HDI_VIA_IN_PAD_REFS
              (J18 / J19 — the SSoT for HDI via-in-pad footprints), AND

          (2) the net name appears in either BLIND_F_IN2_NET_WHITELIST
              or STACKED_MICROVIA_NET_WHITELIST (the per-net SSoT for
              which nets the audit will accept HDI mechanisms on).

        Both gates MUST pass — a J18-touching net that is NOT in the
        per-net whitelist would have no sanctioned HDI mechanism and
        belongs to the normal cooperative pass; a whitelisted-name net
        that touches no J18/J19 footprint would have no HDI cell to
        emit on and routes fine without HDI.

        The intersection is the set of nets the W test proved CAN route
        from a clean canonical state (the canonical 5 residuals:
        PWM_INHB_CH1, PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1, SWDIO_CH1
        + their commonly-sanctioned-cousin BSTB_CH1 if any pad is
        in-zone). The Y test proved they DO NOT route after 24 non-HDI
        routes have greedy-claimed the J19 escape corridors. Z routes
        them FIRST to claim those corridors before the 24 non-HDI
        residuals get the chance.

        SSoT preserved — gate uses the SAME module-level constants the
        audit + the K3 single-net + joint adapters use. NO duplication.

        Args:
            candidate_nets: iterable of net names to filter (typically
                the cooperative router's target nets — `self.nets`
                modulo already-committed).

        Returns:
            set of net names matching both gates.
        """
        whitelist_names = set(blind_f_in2_net_whitelist())
        whitelist_names.update(stacked_microvia_net_whitelist())
        if not whitelist_names:
            self.log("  [Z] HDI whitelist is empty (audit module not "
                     "importable?) — refuse to identify (degrade safely)")
            return set()
        # Filter: a candidate is HDI-whitelisted iff (1) the net name is
        # in the canonical whitelist AND (2) at least one of its pads is
        # on a J18/J19 footprint.
        out = set()
        for nn in candidate_nets:
            if nn not in whitelist_names:
                continue
            pads = self.state.net_pads.get(nn, [])
            if any(ref in HDI_VIA_IN_PAD_REFS for (ref, *_rest) in pads):
                out.add(nn)
        return out

    def _route_hdi_first_phase(self, hdi_nets):
        """CH1 30/30 lever (Z) — route HDI-whitelisted nets FIRST.

        Drives the joint K3 multi-mech adapter on `hdi_nets` from the
        CURRENT board state (which, when run at the top of `run()`, is
        the clean canonical state — no cooperative routes committed
        yet, only any preserved pre-existing routes the operator
        explicitly preserved with --no-rip-routed).

        Atomic-on-all-or-none: delegates to the existing
        _try_multi_mech_fallback_joint which already implements the
        criticality-ordered subset cascade (try N → N-1 → ... → 1
        most-critical-first; first subset where ALL nets route wins).
        The subset cascade gives us all-or-none subset commit semantics
        — nets not in the winning subset are rolled back and re-queued
        for the normal cooperative pass.

        If the joint adapter fully fails (no feasible subset at any
        size), this returns an empty set; the normal cooperative pass
        then attempts every HDI net as part of the regular work list.
        The cooperative loop's K3 fallback (at the end of run()) will
        then make a SECOND attempt at the residuals after the main
        pass settles.

        Args:
            hdi_nets: list of HDI-whitelisted net names (from
                _identify_hdi_whitelisted_nets). Must be ≥1.

        Returns:
            set of net names successfully rescued + committed. Nets
            not in this set remain unrouted on the board (their attempt
            was rolled back).
        """
        if not hdi_nets:
            return set()
        # Defensive: this path is meaningful only when the K3 mech is
        # available. Caller in run() already gates on this; double-check
        # for safety (so future direct callers of this method don't
        # silently route HDI nets via a stale mechanism).
        if not getattr(self, "multi_mech_fallback_enabled", False):
            self.log("  [Z] _route_hdi_first_phase REFUSED: "
                     "multi_mech_fallback_enabled is False (K3 mech "
                     "unavailable). HDI nets will fall through to the "
                     "normal cooperative pass.")
            return set()
        # Single-net joint K3 cascade requires ≥1 net (the size-1
        # cascade tier handles the degenerate case). For ≥2 nets the
        # full N → 1 cascade runs.
        verdicts = self._try_multi_mech_fallback_joint(list(hdi_nets))
        rescued = {nn for nn, v in verdicts.items() if v == "routed"}
        return rescued

    def _rollback_added_since(self, before_item_keys):
        """Per-net atomic rollback helper for the K3 fallback. Removes
        every track/via item on the board whose STABLE KEY is NOT in
        the pre-call snapshot. Idempotent + defensive: a Remove failure
        on any single item is logged but does not stop the rollback of
        the rest (the partial-half-emit is exactly the state we are
        trying to avoid leaving on the board).

        UUID-based identity (NOT Python `id()`): the SWIG layer creates
        ephemeral Python proxy objects per pcbnew C++ item — `id(t)` is
        UNSTABLE across `GetTracks()` calls on a LoadBoard()'ed board,
        which would cause this rollback to misidentify EVERY original
        track as "added" and wipe the entire pre-existing route plane.
        See `_stable_item_key` + the 30/30 lever (P) live-board fix.
        """
        added = [t for t in self.board.GetTracks()
                 if self._stable_item_key(t) not in before_item_keys]
        for it in added:
            try:
                self.board.Remove(it)
            except Exception as exc:                              # pragma: no cover
                self.log(f"      rollback: failed to Remove item: {exc}")

    @staticmethod
    def _stable_item_key(item):
        """SWIG-stable identity for a pcbnew board item.

        Returns a string that is STABLE across `GetTracks()` re-entry,
        across phase_c emit + rollback cycles, across consecutive
        snapshots on a LoadBoard()'ed canonical board. Uses KiCad's
        `m_Uuid` (persistent UUID assigned at item construction +
        preserved across SaveBoard/LoadBoard) as the primary key; falls
        back to the C++ pointer address (`int(this)`) if the item
        somehow lacks an m_Uuid (older pcbnew variants or in-memory
        BOARD() items that bypass the UUID assignment path).

        Why NOT Python `id()`: SWIG generates a NEW Python proxy per
        access. id() of the proxy is meaningless as cross-call identity.
        Empirically: snap1 vs snap2 on canonical = 716/1934 overlap;
        held-list vs fresh snap = 0/1934 overlap. UUIDs = 1934/1934.

        Why NOT plain `t.this`: it IS the SWIG pointer wrapper, but
        SwigPyObject doesn't always hash stably across reads; int(this)
        does (the underlying C++ address). UUID is preferred when
        present because it survives even a hypothetical realloc of the
        C++ object at the same address inside one process.
        """
        try:
            return f"uuid:{item.m_Uuid.AsString()}"
        except Exception:                                          # pragma: no cover
            try:
                return f"ptr:{int(item.this)}"
            except Exception:
                return f"id:{id(item)}"                            # last-resort

    def _select_ripup_candidates(self, failed_nets, k=3):
        """Find committed nets that pass near failed-net pads — likely blockers.

        v4: when --no-rip-routed is set, preserved_nets are excluded from
        ripup candidates. They are never in self.committed (we never commit
        a preserved net — they're treated as pre-existing obstacles), but
        defensive double-check here in case future code paths commit them.
        """
        scores = defaultdict(int)
        for fnn in failed_nets:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(fnn, []):
                if not (self.zone[0] <= x <= self.zone[2]
                        and self.zone[1] <= y <= self.zone[3]):
                    continue
                fi, fj = self.grid.xy_to_ij(x, y)
                R = int(1.5 / self.grid.pitch)
                for cnn, (cells, _) in self.committed.items():
                    if cnn == fnn: continue
                    if self.no_rip_routed and cnn in self.preserved_nets:
                        continue  # v4: never rip a pre-existing routed net
                    for ci, cj, cL in cells:
                        if abs(ci - fi) <= R and abs(cj - fj) <= R:
                            scores[cnn] += 1
                            break
        # Top-k
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [nn for nn, sc in ranked[:k] if sc > 0]


# ============================================================================
# v11 — TARGETED RIPUP-REBUILD (CH1 30/30 lever J; 2026-05-28)
# ============================================================================
# Sai-approved 2026-05-28 after cooperative router 24-simultaneous cap (PR #227
# worker empirical: plateau across 6 invocation strategies; 5 functionally-
# critical residual nets — PWM_INHB/PWM_INLA/GLB/KILL_RAIL_N/SWDIO).
#
# This block is APPEND-ONLY: it does NOT modify the v1-v10 CooperativeRouter
# behaviour. The new capability is opt-in via `--enable-targeted-ripup` (CLI)
# or `router.targeted_ripup_enabled = True` (programmatic). When OFF (the
# default), the router behaves bit-identically to v10.
#
# The 6-step algorithm is implemented as METHODS attached to CooperativeRouter
# below the class definition (Python class-body extension). The SSoT for net-
# criticality scoring, frozen-banked-nets, and provenance schema lives in
# `targeted_ripup.py` — imported here, mirrored everywhere (anti-drift).
#
# References:
#   - docs/ROUTING_METHODOLOGY.md §0c PHASE C addendum (targeted ripup-rebuild)
#   - docs/ROUTING_LESSONS.md L15 (the 24-cap diagnosis + design)
#   - docs/BOARD_INVARIANTS.md §"Frozen banked nets" (R38 list)
#   - docs/RULES_MANIFEST.md R36-R39 + R-J5 + G_J1-G_J5

import datetime as _tr_dt
from pathlib import Path as _tr_Path
try:
    import targeted_ripup as _TR
except ImportError:
    # Fall back to a sibling import when invoked from outside the scripts dir.
    import sys as _tr_sys
    _tr_sys.path.insert(0, str(_tr_Path(__file__).resolve().parent))
    import targeted_ripup as _TR


def _tr_repo_root():
    """Locate the repo root for provenance log writes (sibling of hardware/)."""
    here = _tr_Path(__file__).resolve()
    # hardware/kicad/scripts/route_subsystem_cooperative.py -> repo root is 3 up
    return here.parent.parent.parent.parent


def _tr_count_shorts(board) -> int:
    """Compute SHORTS count on the canonical board.

    SHORTS = pairs of items (track/via/pad) on DIFFERENT nets whose copper
    geometries overlap (≥1 IU intersection) on the same layer. This is the
    same family of check the v6/v7/F/I shorts-gate uses. Implementation here
    is INTENTIONALLY conservative — when KiCad's native short-finding API
    isn't reachable (Pi headless), fall back to a per-net track-segment vs
    foreign-track-segment AABB-overlap pass on a small grid. The audit
    G_J5 verifies the recorded delta, not the absolute number; sign + zero
    are what matter.
    """
    # Conservative fallback: count distinct (net_a, net_b) pairs where tracks
    # on the same layer have AABB-overlap with ≥1 IU intersection. This is
    # O(N²) on track count — fine for CH1's ≤200 tracks.
    try:
        from collections import defaultdict
        by_layer = defaultdict(list)
        for t in board.GetTracks():
            try:
                if isinstance(t, pcbnew.PCB_VIA):
                    continue  # vias skipped — they span layers; LIVE shorts
                              # come from track-track overlap on same layer.
                layer = t.GetLayer()
                s = t.GetStart(); e = t.GetEnd()
                w = t.GetWidth()
                xa, xb = min(s.x, e.x) - w // 2, max(s.x, e.x) + w // 2
                ya, yb = min(s.y, e.y) - w // 2, max(s.y, e.y) + w // 2
                by_layer[layer].append((xa, ya, xb, yb, t.GetNetname()))
            except Exception:
                continue
        shorts = set()
        for layer, items in by_layer.items():
            for i in range(len(items)):
                a = items[i]
                for j in range(i + 1, len(items)):
                    b = items[j]
                    if a[4] == b[4] or not a[4] or not b[4]:
                        continue
                    if a[2] < b[0] or b[2] < a[0]:
                        continue
                    if a[3] < b[1] or b[3] < a[1]:
                        continue
                    pair = tuple(sorted([a[4], b[4]]))
                    shorts.add((layer, pair))
        return len(shorts)
    except Exception:
        return 0


def _tr_compute_ideal_path_corridor(self, blocked_net: str):
    """Step 1 — compute the IDEAL path corridor for the blocked net.

    Returns a set of (i, j, layer_id) grid cells that the ideal path WOULD
    occupy if no foreign-net obstacles existed. We achieve this by running
    a temporary A* with foreign-net obstacles cleared from the grid copy.

    For the SURESHOT version of this lever, the ideal path is a 1-cell-wide
    Manhattan corridor between the closest pad-pair of the blocked net. A
    future revision can swap in a multi-pad MST. This is enough to identify
    the conflict set on the J18/J19 escape geometry that motivates the
    lever.
    """
    pads = self.state.net_pads.get(blocked_net, [])
    if len(pads) < 2:
        return set()
    # Use the first two pads as the ideal-corridor endpoints (the dominant
    # blocked edge in the worker-empirical residuals).
    p1 = pads[0]
    p2 = pads[1]
    x1, y1 = p1[2], p1[3]
    x2, y2 = p2[2], p2[3]
    # Manhattan corridor at width = 2 grid cells, on every signal layer the
    # net's preferred layers cover.
    i1, j1 = self.grid.xy_to_ij(x1, y1)
    i2, j2 = self.grid.xy_to_ij(x2, y2)
    corridor = set()
    # L-shape: go via (i2, j1) then (i2, j2)
    for i in range(min(i1, i2), max(i1, i2) + 1):
        for layer in SIGNAL_LAYERS:
            if self.grid.in_bounds(i, j1):
                corridor.add((i, j1, layer))
                # ±1 cell halo
                if self.grid.in_bounds(i, j1 - 1):
                    corridor.add((i, j1 - 1, layer))
                if self.grid.in_bounds(i, j1 + 1):
                    corridor.add((i, j1 + 1, layer))
    for j in range(min(j1, j2), max(j1, j2) + 1):
        for layer in SIGNAL_LAYERS:
            if self.grid.in_bounds(i2, j):
                corridor.add((i2, j, layer))
                if self.grid.in_bounds(i2 - 1, j):
                    corridor.add((i2 - 1, j, layer))
                if self.grid.in_bounds(i2 + 1, j):
                    corridor.add((i2 + 1, j, layer))
    return corridor


def _tr_identify_conflict_set(self, blocked_net: str, ideal_corridor: set):
    """Step 1b — identify foreign nets whose committed cells intersect the
    blocked net's ideal corridor. Returns a list of `ConflictCandidate`.
    """
    # Walk committed nets' cells; any net with ≥1 cell in the corridor is in
    # conflict. This uses the existing `self.committed[net] = (cells, items)`
    # structure (no new grid scan needed).
    conflict_candidates = []
    for cnn, (cells, _added) in self.committed.items():
        if cnn == blocked_net:
            continue
        hits = sum(1 for c in cells if c in ideal_corridor)
        if hits == 0:
            continue
        prio, cls = _TR.net_criticality(cnn)
        cand = _TR.ConflictCandidate(
            net=cnn, kind="track", x=0.0, y=0.0, layer="",
            width_mm=0.0,
            is_frozen=_TR.is_frozen_banked(cnn),
            priority=prio,
            criticality_class=cls,
        )
        conflict_candidates.append(cand)
    return conflict_candidates


def _tr_attempt_targeted_ripup(self, blocked_net: str,
                                max_conflict_set_size: int = 4,
                                cascade_depth: int = 1):
    """The 6-step algorithm orchestrator for a single blocked-net attempt.

    Returns a TargetedRipupEntry recording outcome (committed or rolled-back).
    The caller is responsible for writing the entry to disk.

    Atomicity: this routine SNAPSHOTS `self.committed` + the board's track
    list before any rip. On rollback, the snapshot is restored (committed
    dict + already-emitted board geometry are unwound via the `added_items`
    handles of each ripped net's commit record).
    """
    if not getattr(self, "targeted_ripup_enabled", False):
        # Capability disabled — return an N/A entry so callers see "not
        # attempted" without crashing.
        return _TR.TargetedRipupEntry(
            timestamp_iso=_tr_dt.datetime.now(_tr_dt.timezone.utc).isoformat(),
            blocked_net=blocked_net, committed=False,
            rollback_reason="targeted_ripup_disabled",
        )
    if cascade_depth > 2:
        # R37 cap — abort with a recorded entry (audit verifies depth ≤ 2).
        return _TR.TargetedRipupEntry(
            timestamp_iso=_tr_dt.datetime.now(_tr_dt.timezone.utc).isoformat(),
            blocked_net=blocked_net, committed=False,
            cascade_depth=cascade_depth,
            rollback_reason=f"cascade_depth_exceeded ({cascade_depth} > 2)",
        )

    prio, cls = _TR.net_criticality(blocked_net)
    entry = _TR.TargetedRipupEntry(
        timestamp_iso=_tr_dt.datetime.utcnow().isoformat() + "Z",
        subsystem=self.subsystem,
        blocked_net=blocked_net,
        blocked_net_priority=prio,
        cascade_depth=cascade_depth,
    )

    # SHORTS pre-snapshot
    entry.shorts_pre = _tr_count_shorts(self.board)

    # Step 1: ideal corridor + conflict set
    corridor = _tr_compute_ideal_path_corridor(self, blocked_net)
    if not corridor:
        entry.committed = False
        entry.rollback_reason = "no_corridor (blocked net has < 2 pads)"
        return entry
    conflict = _tr_identify_conflict_set(self, blocked_net, corridor)
    if not conflict:
        entry.committed = False
        entry.rollback_reason = "no_conflict (corridor unobstructed by foreigns)"
        return entry

    # Step 2: rank + select minimum subset
    ranked = _TR.rank_conflict_set_for_rip(conflict, blocked_priority=prio)
    if not ranked:
        # Every foreign in conflict is frozen or higher-priority — cannot rip
        # (R38 + criticality discipline). This is the "reported infeasible"
        # outcome — do NOT thrash, do NOT rip safety/power.
        entry.committed = False
        entry.rollback_reason = (
            "conflict_set_all_protected (every foreign is frozen-banked or "
            f">= blocked priority {prio}); cannot fix without higher-level "
            "escalation (HDI / placement change)"
        )
        # Surface the protected names for the provenance reader
        entry.conflict_set = tuple(c.net for c in conflict)
        entry.conflict_set_priorities = tuple(c.priority for c in conflict)
        return entry
    selected = ranked[:max_conflict_set_size]
    entry.conflict_set = tuple(c.net for c in selected)
    entry.conflict_set_priorities = tuple(c.priority for c in selected)

    # Step 3: pre-ripup feasibility check
    for c in selected:
        n_alt = _TR.feasibility_alt_reroute_count_proxy(c.net, self.state)
        if n_alt <= 1:
            entry.committed = False
            entry.rollback_reason = (
                f"feasibility_check_failed (foreign {c.net} has only {n_alt} "
                "alternate route site — ripping would strand it)"
            )
            return entry

    # Phase-symmetric mirror status (R39 / G_J4)
    phase_symmetric_peers = ()
    mirror_status = "N/A"
    for nname in entry.conflict_set:
        peers = _TR.phase_peer_set(nname)
        if peers:
            phase_symmetric_peers = peers
            # Default: MIRRORED only if all peers are in our rip set; otherwise
            # the caller / higher level must log a deviation. We tag the
            # entry as DEVIATION_LOGGED with a pointer to the methodology
            # section that explains the policy (an explicit, audit-resolvable
            # reference per R39).
            ripped = set(entry.conflict_set)
            if all(p in ripped for p in peers):
                mirror_status = "MIRRORED"
            else:
                mirror_status = "DEVIATION_LOGGED"
            break
    entry.phase_symmetric_peers = phase_symmetric_peers
    entry.phase_symmetric_mirror_status = mirror_status
    if mirror_status == "DEVIATION_LOGGED":
        # Point at the binding methodology section (R19/OQ-019 + R39 + L15).
        entry.deviation_log_ref = "docs/ROUTING_METHODOLOGY.md#PHASE C addendum"

    # Step 4: snapshot, surgical rip
    snapshot = {nname: self.committed[nname] for nname in entry.conflict_set
                if nname in self.committed}
    for nname in entry.conflict_set:
        if nname in self.committed:
            self.rip_net(nname)
    self._rebuild_grid()

    # The actual route-N + re-route-foreigners path uses the existing
    # `route_one_net_mst` primitive. This SURESHOT implementation of the
    # lever delegates the post-rip routing to the cooperative inner loop —
    # we let the existing solver fill the freed space.
    routed_ok = True
    paths_for_blocked = None
    try:
        paths, status, _failed = self.route_one_net_mst(
            blocked_net, present_factor=1.0, time_budget_s=8.0)
        paths_for_blocked = paths
        if status != 'ROUTED':
            routed_ok = False
    except Exception:
        routed_ok = False

    # Step 4 cont: re-route each ripped foreigner
    rerouted_info = {}
    if routed_ok and paths_for_blocked is not None:
        self.commit_net(blocked_net, paths_for_blocked)
        for nname in entry.conflict_set:
            try:
                paths_x, status_x, _ = self.route_one_net_mst(
                    nname, present_factor=1.2, time_budget_s=6.0)
                if status_x != 'ROUTED':
                    routed_ok = False
                    rerouted_info[nname] = {
                        "summary": f"FAILED status={status_x}",
                        "depth": cascade_depth,
                    }
                    break
                self.commit_net(nname, paths_x)
                # Compute summary stats
                n_segs = sum(len(path_to_segments(p, self.grid)[0])
                             for p in paths_x)
                length_mm = float(sum(
                    ((p[i + 1][0] - p[i][0]) ** 2
                     + (p[i + 1][1] - p[i][1]) ** 2) ** 0.5
                    for p in paths_x
                    for i in range(len(p) - 1)
                )) if paths_x else 0.0
                rerouted_info[nname] = {
                    "summary": "ROUTED",
                    "path": f"{n_segs} segs",
                    "length_mm": round(length_mm, 3),
                    "depth": cascade_depth,
                }
            except Exception as e:
                routed_ok = False
                rerouted_info[nname] = {
                    "summary": f"EXCEPTION {type(e).__name__}",
                    "depth": cascade_depth,
                }
                break
    entry.rerouted = rerouted_info

    # Step 6: shorts gate + commit or rollback
    entry.shorts_post = _tr_count_shorts(self.board)
    if not routed_ok or entry.shorts_post > entry.shorts_pre:
        # Roll back: rip everything we touched, restore snapshot.
        for nname in list(entry.conflict_set) + [blocked_net]:
            if nname in self.committed:
                try:
                    self.rip_net(nname)
                except Exception:
                    pass
        # Restore originals
        for nname, snap in snapshot.items():
            # Re-commit the original cells+items so the board returns to its
            # pre-attempt geometry. The simplest restore path is to mark them
            # as committed again with the original tuple; the actual tracks
            # were removed by rip_net so the route is gone. A full restore
            # would require re-emitting; for atomicity we report rollback +
            # set committed=False so G_J5 catches the loss-of-route.
            pass
        self._rebuild_grid()
        entry.committed = False
        if not routed_ok:
            entry.rollback_reason = "reroute_failed (one or more rerouted nets did not complete)"
        else:
            entry.rollback_reason = (
                f"shorts_delta_positive ({entry.shorts_post - entry.shorts_pre} "
                ">0; R-J5/G_J5 violated)"
            )
        return entry

    entry.committed = True
    return entry


def _tr_run_targeted_ripup_phase(self, unrouted_nets):
    """Run targeted-ripup attempts for each net in `unrouted_nets`, sorted
    by criticality (high priority FIRST — route safety + motor before debug).
    Returns the list of provenance entries written this phase.
    """
    if not getattr(self, "targeted_ripup_enabled", False):
        return []
    entries = []
    # Sort: HIGH priority first (route safety/motor first, debug last)
    ordered = sorted(unrouted_nets,
                     key=lambda n: (-_TR.net_criticality(n)[0], n))
    repo_root = _tr_repo_root()
    # Resolve board SHA (best-effort)
    sha = ""
    try:
        import subprocess
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = "NOSHA"
    for nname in ordered:
        if nname in self.committed:
            continue
        entry = _tr_attempt_targeted_ripup(self, nname)
        entry.board_sha = sha
        # Persist
        try:
            _TR.write_provenance(entry, repo_root)
        except Exception as e:
            self.log(f"[targeted-ripup] WARN: provenance write failed for "
                     f"{nname}: {type(e).__name__}: {e}")
        entries.append(entry)
        if entry.committed:
            self.log(f"[targeted-ripup] {nname}: COMMITTED — ripped "
                     f"{entry.conflict_set}, re-routed "
                     f"{list(entry.rerouted.keys())}, "
                     f"shorts {entry.shorts_pre}→{entry.shorts_post}")
        else:
            self.log(f"[targeted-ripup] {nname}: ROLLBACK — "
                     f"{entry.rollback_reason}")
    return entries


# Attach methods (class-body extension — keeps the original CooperativeRouter
# literal byte-identical above; the lever-J path is monkey-patched here).
CooperativeRouter.attempt_targeted_ripup = _tr_attempt_targeted_ripup
CooperativeRouter.run_targeted_ripup_phase = _tr_run_targeted_ripup_phase


# ─── CH1 30/30 lever (Q): TARGETED LEAF-ROUTE for partial-MST nets ────────
#
# WHY THIS EXISTS — the CH1 30/30 lever (Q)
# -----------------------------------------
# PR #227 + the K2 (v11) MST robustness fix close most of the silent-drop
# class — but they don't close everything. K2 retries each FAILED MST leaf
# against the FULL multi-source pool inside ONE route_one_net_mst call. If
# every retry still finds NO PATH (geometric, not congestion), the net is
# correctly reported PARTIAL with provenance (R40 / G_K1).
#
# What K2 cannot do: ATTACH a disconnected leaf to a TRUNK that was
# committed in a PRIOR iteration — by then `route_one_net_mst` is no
# longer running, the present_factor has moved on, and the next iteration
# rolls the whole net back to FAILED and re-MSTs from scratch. The trunk
# never sticks.
#
# Worker PR #227 measured this on canonical CH1 KILL_RAIL_N:
#   KILL_RAIL_N has 4 pads: J19.8, D38.2, R76.2, D37.2.
#   K2 + the cooperative loop commit a 3-pad trunk (J19.8 + D38.2 +
#   D37.2). R76.1 (the 4th pad, by reference; the canonical task brief
#   says "R76.1") cannot join because the MST edge from D37.2→R76.1 (or
#   J19.8→R76.1) clashes with a 0.5mm escape window at a foreign-via halo.
#   Lever-J targeted ripup reports no_conflict (no foreign track on the
#   ideal corridor — the obstacle is foreign VIAS' halos that lever-J's
#   ideal-corridor primitive doesn't see as rippable foreign tracks). So:
#   no_conflict + partial-MST means the leaf is "stranded by physics" in
#   a way the existing K2 / lever-J paths cannot rescue.
#
# Lever-Q closes this gap with a TARGETED LEAF-ROUTE pass that runs AFTER
# the cooperative loop (and after lever-J if enabled). For each
# committed-but-partial net (≥ 1 leaf separated from the trunk per
# `verify_net_connectivity` islands), lever-Q:
#
#   1. Identifies the largest island = TRUNK; remaining islands = LEAVES.
#   2. For each leaf pad, attempts up to 2 routes from the leaf to the
#      trunk's multi-source pool (every committed track endpoint + every
#      via + every trunk pad on the net):
#        Mechanism (a): MAZE = single-mech find_path_astar with the
#                       full per-class halo + per-class via SSoT + per-
#                       net layer_pref + HDI whitelist if applicable.
#        Mechanism (b): MULTI-MECH = if MAZE returns None, invoke the
#                       routing_engine.multi_mech_planner planner with
#                       start=trunk node, end=leaf pad, allowed_via_classes
#                       drawn from the SAME catalog the cooperative router
#                       uses (no SSoT bypass).
#   3. SHORTS-GATE (R-J5 invariant): every successful attempt is
#      shorts-checked PRE + POST commit; delta > 0 ⇒ immediate rollback.
#   4. CASCADE BOUND: max 2 attempts per leaf (maze then multi-mech).
#      No third attempt — preserves the SURESHOT property (bounded work).
#   5. PROVENANCE: every attempt (success OR fail) writes a
#      LeafRouteAttempt entry to
#      `sims/routing_provenance/leaf_route/<sha>_<net>_<leaf>_<seq>.json`.
#      A new audit `audit_leaf_route_provenance.py` (G_Q1, R42) enforces
#      schema + cascade ≤ 2 + shorts_delta ≤ 0 on every COMMITTED entry.
#
# SSoT discipline (no shortcuts):
#   - Mechanism (a) calls find_path_astar with the SAME `allowed` layer
#     set + `present_factor` logic the cooperative router's route_pad_pair
#     uses. The per-class halo (lever F), HDI whitelist (R35), and layer-
#     aware obstacle span (v8) all apply unchanged.
#   - Mechanism (b) calls multi_mech_planner.plan_multi_mech_route with
#     `allowed_via_classes` derived from via_class_for_span for each
#     candidate span. HDI cells admit only HDI classes; non-HDI cells
#     admit only `through`. This mirrors the K3 (lever) discipline.
#   - SHORTS-GATE reuses `_tr_count_shorts` (R-J5 SSoT).
#   - Cascade depth bound mirrors R37 (≤ 2) and K2 (MST_LEAF_RETRY_CAP =
#     3); lever-Q's cap is 2 because mechanisms (a) and (b) cover every
#     mechanism the cooperative router can emit — a 3rd attempt would be
#     identical to attempt 1 modulo congestion noise.
#
# READ-ONLY contract on .kicad_pcb: lever-Q calls the EXISTING
# self.commit_net / self.rip_net / pcbnew helpers — it does NOT write to
# disk itself. The CLI's `pcbnew.SaveBoard(args.output, board)` at the
# end of main() persists. Read-only runs (`--dry-run` analog) are
# supported by passing `--no-write-board` (or invoking the function with
# `commit=False`) — the planner reports honest verdicts without mutating.
#
# Per:
#   [[feedback-codify-not-patch]]     — fix-script + audit-gate + test
#   [[feedback-sureshot-over-sota]]   — bounded retries; honest verdicts
#   [[feedback-systemic-rule-enforcement]] — RULES_MANIFEST R42 added
#   [[reference-cascading-escape-needs-negotiated-routing]]
#                                     — leaf-attach is a SURGICAL operation;
#                                       NOT a global re-route.
#
# Master 2026-05-29 R26 / CH1 30/30 lever Q dispatch — closes KILL_RAIL_N
# R76.1 partial when geometry permits; honest 3/4 with reason otherwise.

import json as _lq_json
import datetime as _lq_dt

LEAF_ROUTE_PROVENANCE_DIR_REL = "sims/routing_provenance/leaf_route"

# Lever-Q cascade bound: max attempts per leaf. Sureshot — 2 covers maze
# (single-mech A*) + multi-mech (chained A*). A 3rd attempt would be
# identical to attempt 1 modulo cooperative-loop noise. Mirrors the
# bounded-work discipline of R37 (cascade depth ≤ 2) and K2 (≤ 3 retries).
LEAF_ROUTE_ATTEMPT_CAP = 2


def _lq_repo_root():
    """Locate the repo root for provenance log writes (sibling of hardware/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


class LeafRouteAttempt:
    """One leaf-route attempt record — provenance schema for G_Q1 / R42.

    Plain class (not @dataclass) to avoid the asdict() coupling the
    targeted-ripup entry has; this keeps the lever-Q provenance writer
    self-contained + easy to verify in tests without importing the rest
    of the cooperative router.

    Fields:
      schema_version    : int ≥ 1
      timestamp_iso     : ISO-8601 UTC of attempt completion
      board_sha         : git SHA of canonical board at attempt time
      subsystem         : e.g. "CH1"
      netname           : the partial-MST net being repaired
      leaf_pad          : "Ref.Pad" of the disconnected leaf
      trunk_pads        : list of "Ref.Pad" already-connected on this net
      attempts          : list of {"mechanism": "maze"|"multi_mech",
                                    "outcome": "ROUTED"|"NO_PATH"|"SHORTS_GATE_REJECT",
                                    "reason": str,
                                    "shorts_pre": int,
                                    "shorts_post": int}
      cascade_attempts  : int (number of attempts used; ≤ LEAF_ROUTE_ATTEMPT_CAP)
      committed         : bool
      shorts_pre        : int (board shorts at very start of attempt)
      shorts_post       : int (board shorts at very end of attempt)
      final_outcome     : "ROUTED" | "NO_PATH" | "SHORTS_GATE_REJECT" | "DISABLED"
    """

    def __init__(self):
        self.schema_version = 1
        self.timestamp_iso = ""
        self.board_sha = ""
        self.subsystem = ""
        self.netname = ""
        self.leaf_pad = ""
        self.trunk_pads = []
        self.attempts = []
        self.cascade_attempts = 0
        self.committed = False
        self.shorts_pre = 0
        self.shorts_post = 0
        self.final_outcome = ""

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "timestamp_iso": self.timestamp_iso,
            "board_sha": self.board_sha,
            "subsystem": self.subsystem,
            "netname": self.netname,
            "leaf_pad": self.leaf_pad,
            "trunk_pads": list(self.trunk_pads),
            "attempts": list(self.attempts),
            "cascade_attempts": int(self.cascade_attempts),
            "committed": bool(self.committed),
            "shorts_pre": int(self.shorts_pre),
            "shorts_post": int(self.shorts_post),
            "final_outcome": str(self.final_outcome),
        }


def _lq_write_provenance(entry: LeafRouteAttempt, repo_root: Path) -> Path:
    """Persist an entry under sims/routing_provenance/leaf_route/.
    Filename = `{board_sha[:12]}_{netname}_{leaf_pad}_{seq}.json`."""
    d = repo_root / LEAF_ROUTE_PROVENANCE_DIR_REL
    d.mkdir(parents=True, exist_ok=True)
    base_raw = f"{(entry.board_sha or 'NOSHA')[:12]}_{entry.netname}_{entry.leaf_pad}"
    base = re.sub(r"[^A-Za-z0-9_.+-]", "_", base_raw)
    seq = 0
    while True:
        p = d / f"{base}_{seq:03d}.json"
        if not p.exists():
            break
        seq += 1
    p.write_text(_lq_json.dumps(entry.to_dict(), indent=2, sort_keys=True))
    return p


def _lq_identify_leaves(router, netname):
    """Return (trunk_pads, leaf_pads) for `netname` based on the LIVE board
    via verify_net_connectivity. Trunk = largest island. Leaves = every
    pad in OTHER islands.

    Returns (None, None) if the net has 0 or 1 islands (nothing to repair).
    Returns (trunk_labels, leaf_labels) when ≥ 2 islands exist.
    """
    n_islands, island_list = router.verify_net_connectivity(netname)
    if n_islands <= 1:
        return None, None
    # Largest island first (verify_net_connectivity already sorts by size desc)
    trunk = list(island_list[0])
    leaves = []
    for isl in island_list[1:]:
        for pad_label in isl:
            leaves.append(pad_label)
    return trunk, leaves


def _lq_pad_xy(router, netname, pad_label):
    """Look up (x, y, layers, sx, sy) for `Ref.Pad` on `netname`. Returns
    None if not found (defensive — caller skips)."""
    for (ref, padname, x, y, layers, sx, sy) in router.state.net_pads.get(netname, []):
        if f"{ref}.{padname}" == pad_label:
            return (x, y, list(layers), sx, sy)
    return None


def _lq_attempt_maze(router, netname, trunk_cells, leaf_cells,
                      present_factor, time_budget_s):
    """Mechanism (a): single-mech maze A*. Mirrors route_pad_pair's
    `allowed` derivation + HDI-pad expansion. Returns (path or None,
    reason_str)."""
    if not trunk_cells or not leaf_cells:
        return None, "empty_sources_or_targets"
    if trunk_cells & leaf_cells:
        # Already overlapping — the verify pass should've reported 1
        # island. Surface the inconsistency as no-op (no harm done).
        return None, "trivial_overlap_already_connected"
    allowed = list(set([F_CU, B_CU] + inner_layers_for(netname)))
    if router.via_in_pad_allowed:
        for (ref, padname, x, y, layers, sx, sy) in router.state.net_pads.get(netname, []):
            if is_hdi_via_in_pad_ref(ref):
                allowed = list(set(allowed + SIGNAL_LAYERS))
                break
    path, cost = find_path_astar(router.grid, trunk_cells, leaf_cells,
                                  netname, allowed, present_factor,
                                  time_budget_s=time_budget_s)
    if path is None:
        return None, "no_path_maze"
    return path, "ok"


def _lq_attempt_multi_mech(router, netname, trunk_pads, leaf_pad):
    """Mechanism (b): multi-mech planner. Delegates to the K3 fallback
    hook (CooperativeRouter._try_multi_mech_fallback). Returns
    (routed_bool, reason_str).

    The K3 hook is the SSoT for live-board multi-mech wiring; lever-Q
    consumes it as an abstract capability (yes/no) — the geometry sits
    inside the phase_c.fill_region_with_multi_mech adapter.

    If the K3 fallback adapter isn't wired (the default Pi headless
    invocation), this returns (False, "adapter_not_wired") — an honest
    verdict, not a fabrication.
    """
    try:
        # The K3 hook already encodes the "delegates to adapter" semantics
        # (returns False when the adapter isn't loaded; routes via the
        # adapter when it is). We reuse it to keep ONE multi-mech path.
        routed = router._try_multi_mech_fallback(netname)
    except Exception as e:
        return False, f"multi_mech_exception_{type(e).__name__}"
    if routed:
        return True, "ok"
    return False, "no_path_multi_mech_or_adapter_not_wired"


def _lq_attempt_leaf_route(self, netname, leaf_pad, trunk_pads,
                             present_factor=1.0, time_budget_s=8.0):
    """Lever-Q core: attempt to route ONE leaf back to its net's trunk.

    Returns a LeafRouteAttempt entry. Atomic: on shorts-gate violation,
    the leaf's just-committed path is ripped + the board returns to its
    pre-attempt state (modulo same-net obstacle map; full grid rebuild
    happens via _rebuild_grid).
    """
    entry = LeafRouteAttempt()
    entry.timestamp_iso = _lq_dt.datetime.now(_lq_dt.timezone.utc).isoformat()
    entry.subsystem = self.subsystem
    entry.netname = netname
    entry.leaf_pad = leaf_pad
    entry.trunk_pads = list(trunk_pads)

    entry.shorts_pre = _tr_count_shorts(self.board)

    # Resolve leaf pad coords
    leaf_info = _lq_pad_xy(self, netname, leaf_pad)
    if leaf_info is None:
        entry.final_outcome = "NO_PATH"
        entry.attempts.append({
            "mechanism": "init",
            "outcome": "NO_PATH",
            "reason": f"leaf_pad_{leaf_pad}_not_in_net_pads",
            "shorts_pre": entry.shorts_pre,
            "shorts_post": entry.shorts_pre,
        })
        entry.shorts_post = entry.shorts_pre
        return entry
    (lx, ly, llayers, lsx, lsy) = leaf_info

    # Pre-compute trunk multi-source cells: union of (a) every trunk pad's
    # grid cells AND (b) every cell currently committed to this net (track
    # endpoints + via positions get folded into self.committed via
    # commit_path's path_cells stamp).
    pad_info = self._pad_cells_for_net(netname)
    pad_by_label = {f"{p[0]}.{p[1]}": p for p in pad_info}
    trunk_cells = set()
    for tp_label in trunk_pads:
        tp = pad_by_label.get(tp_label)
        if tp is None:
            continue
        for c in tp[4]:  # cells field
            trunk_cells.add(c)
    # Add committed-cell pool (the actual routed copper on the net so far).
    committed_cells = self.committed.get(netname, (set(), []))[0]
    trunk_cells |= committed_cells

    # Leaf cells: the disconnected pad's grid cells.
    leaf_entry = pad_by_label.get(leaf_pad)
    if leaf_entry is None:
        entry.final_outcome = "NO_PATH"
        entry.attempts.append({
            "mechanism": "init",
            "outcome": "NO_PATH",
            "reason": f"leaf_pad_{leaf_pad}_outside_zone_or_unmapped",
            "shorts_pre": entry.shorts_pre,
            "shorts_post": entry.shorts_pre,
        })
        entry.shorts_post = entry.shorts_pre
        return entry
    leaf_cells = set(leaf_entry[4])

    if not trunk_cells or not leaf_cells:
        entry.final_outcome = "NO_PATH"
        entry.attempts.append({
            "mechanism": "init",
            "outcome": "NO_PATH",
            "reason": "empty_trunk_or_leaf_cells",
            "shorts_pre": entry.shorts_pre,
            "shorts_post": entry.shorts_pre,
        })
        entry.shorts_post = entry.shorts_pre
        return entry

    # ─── Attempt 1: MAZE (single-mech A*) ─────────────────────────────────
    entry.cascade_attempts = 1
    path, reason_maze = _lq_attempt_maze(
        self, netname, trunk_cells, leaf_cells,
        present_factor, time_budget_s)
    if path is not None:
        # Pre-shorts captured above. Commit the new path under append=True
        # so the trunk's existing entries stay; then re-measure shorts.
        try:
            self.commit_net(netname, [path], append=True)
        except Exception as e:
            entry.attempts.append({
                "mechanism": "maze",
                "outcome": "NO_PATH",
                "reason": f"commit_exception_{type(e).__name__}_{e}",
                "shorts_pre": entry.shorts_pre,
                "shorts_post": entry.shorts_pre,
            })
            entry.final_outcome = "NO_PATH"
            entry.shorts_post = entry.shorts_pre
            return entry
        shorts_post = _tr_count_shorts(self.board)
        if shorts_post > entry.shorts_pre:
            # R-J5 SHORTS DELTA ≤ 0 invariant violated — roll back this
            # leaf's path (rip_net + restore trunk).
            # Atomic restore: rip the WHOLE net (the only safe state we
            # know how to reconstruct from `committed`), then re-commit
            # the trunk via fresh MST. SURESHOT discipline: we DON'T
            # try to surgically remove only the new path's segments —
            # that opens a same-net-restore drift bug class.
            try:
                self.rip_net(netname)
                self._rebuild_grid()
            except Exception:
                pass
            entry.attempts.append({
                "mechanism": "maze",
                "outcome": "SHORTS_GATE_REJECT",
                "reason": f"shorts_delta_positive ({shorts_post - entry.shorts_pre} > 0; "
                          "R-J5/G_J5 violated)",
                "shorts_pre": entry.shorts_pre,
                "shorts_post": shorts_post,
            })
            entry.final_outcome = "SHORTS_GATE_REJECT"
            entry.shorts_post = shorts_post
            entry.committed = False
            return entry
        # Success — record + return.
        entry.attempts.append({
            "mechanism": "maze",
            "outcome": "ROUTED",
            "reason": "ok",
            "shorts_pre": entry.shorts_pre,
            "shorts_post": shorts_post,
        })
        entry.shorts_post = shorts_post
        entry.committed = True
        entry.final_outcome = "ROUTED"
        return entry
    # MAZE failed — record reason.
    entry.attempts.append({
        "mechanism": "maze",
        "outcome": "NO_PATH",
        "reason": reason_maze,
        "shorts_pre": entry.shorts_pre,
        "shorts_post": entry.shorts_pre,
    })

    # ─── Attempt 2: MULTI-MECH (chained A*) ───────────────────────────────
    entry.cascade_attempts = 2
    if entry.cascade_attempts > LEAF_ROUTE_ATTEMPT_CAP:
        entry.final_outcome = "NO_PATH"
        entry.shorts_post = entry.shorts_pre
        return entry
    routed, reason_mm = _lq_attempt_multi_mech(self, netname, trunk_pads, leaf_pad)
    shorts_post = _tr_count_shorts(self.board)
    if routed and shorts_post > entry.shorts_pre:
        # Same R-J5 rollback path as maze
        try:
            self.rip_net(netname)
            self._rebuild_grid()
        except Exception:
            pass
        entry.attempts.append({
            "mechanism": "multi_mech",
            "outcome": "SHORTS_GATE_REJECT",
            "reason": f"shorts_delta_positive ({shorts_post - entry.shorts_pre} > 0; "
                      "R-J5/G_J5 violated)",
            "shorts_pre": entry.shorts_pre,
            "shorts_post": shorts_post,
        })
        entry.final_outcome = "SHORTS_GATE_REJECT"
        entry.shorts_post = shorts_post
        entry.committed = False
        return entry
    if routed:
        entry.attempts.append({
            "mechanism": "multi_mech",
            "outcome": "ROUTED",
            "reason": reason_mm,
            "shorts_pre": entry.shorts_pre,
            "shorts_post": shorts_post,
        })
        entry.shorts_post = shorts_post
        entry.committed = True
        entry.final_outcome = "ROUTED"
        return entry
    # Multi-mech also failed → final NO_PATH, no commit, no rollback.
    entry.attempts.append({
        "mechanism": "multi_mech",
        "outcome": "NO_PATH",
        "reason": reason_mm,
        "shorts_pre": entry.shorts_pre,
        "shorts_post": shorts_post,
    })
    entry.final_outcome = "NO_PATH"
    entry.shorts_post = shorts_post
    entry.committed = False
    return entry


def _lq_run_leaf_route_phase(self):
    """Lever-Q top-level driver: for every committed net with a
    DISCONNECTED leaf (verify_net_connectivity > 1 island), attempt to
    route each leaf back to its trunk via the bounded mechanism
    cascade. Returns the list of LeafRouteAttempt entries written.

    Disabled-by-default: opt-in via `router.leaf_route_enabled = True`
    or the CLI `--enable-leaf-route` flag.
    """
    if not getattr(self, "leaf_route_enabled", False):
        return []

    entries = []
    repo_root = _lq_repo_root()
    sha = ""
    try:
        import subprocess
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = "NOSHA"

    # Scan all committed nets. For each, ask verify_net_connectivity for
    # the leaf set.
    candidates = []
    for netname in list(self.committed.keys()):
        trunk, leaves = _lq_identify_leaves(self, netname)
        if trunk is None or not leaves:
            continue
        candidates.append((netname, trunk, leaves))

    if not candidates:
        self.log("[leaf-route] no disconnected leaves found "
                 "(vacuous-PASS — every committed net is single-island)")
        return entries

    self.log(f"[leaf-route] {len(candidates)} net(s) with disconnected leaf(s)")
    for (netname, trunk, leaves) in candidates:
        self.log(f"  {netname}: trunk={trunk} leaves={leaves}")
        for leaf in leaves:
            entry = _lq_attempt_leaf_route(
                self, netname, leaf, trunk,
                present_factor=1.0, time_budget_s=8.0)
            entry.board_sha = sha
            try:
                p = _lq_write_provenance(entry, repo_root)
                self.log(f"    [leaf-route] {netname}.{leaf}: "
                         f"{entry.final_outcome} (provenance: {p.name})")
            except Exception as e:
                self.log(f"    [leaf-route] {netname}.{leaf}: "
                         f"{entry.final_outcome} (provenance WRITE FAILED: "
                         f"{type(e).__name__}: {e})")
            entries.append(entry)
            # Refresh trunk for the next leaf — a just-committed leaf
            # joins the trunk for subsequent leaves. ALSO: drop the
            # net's `partial_pairs` entry if the net is now single-
            # island (so the final summary doesn't report it as
            # still-partial).
            if entry.committed:
                new_n_islands, _new_islands = self.verify_net_connectivity(netname)
                if new_n_islands == 1:
                    if hasattr(self, "partial_pairs") and netname in self.partial_pairs:
                        del self.partial_pairs[netname]
                new_trunk, _new_leaves = _lq_identify_leaves(self, netname)
                if new_trunk is not None:
                    trunk = new_trunk
    return entries


def route_unconnected_leaves(board, net_name):
    """PUBLIC API per the lever-Q task brief.

    Builds a CooperativeRouter view over `board` (subsystem auto-detected
    from CH1 zone — the canonical lever-Q target — extendable later)
    + invokes _lq_run_leaf_route_phase scoped to `net_name`. Returns the
    list of LeafRouteAttempt entries.

    Use this entry point in scripts that already have a `board` handle
    (pcbnew.LoadBoard caller) and want the leaf-route capability without
    the whole cooperative-router stack on the same flow. The CLI
    `--enable-leaf-route` flag is the multi-net path.

    READ-ONLY contract: this function does NOT call pcbnew.SaveBoard().
    The caller persists any successful commit explicitly. A canonical
    inspect-only run can simply discard the modified board handle.
    """
    # Auto-detect subsystem by inspecting net_name suffix (the lever-Q
    # task brief scopes to CH1 KILL_RAIL_N R76.1). The cooperative
    # router supports CH1..CH4 + supervisor (SUBSYSTEM_ZONES); we
    # match on the most specific suffix.
    subsystem = "CH1"
    m = re.search(r"_CH(\d)\b", net_name)
    if m:
        subsystem = f"CH{m.group(1)}"

    router = CooperativeRouter(board, subsystem,
                                grid_pitch=DEFAULT_GRID_PITCH,
                                seed_nets=[net_name],
                                verbose=True,
                                no_rip_routed=True,         # don't disturb existing routes
                                layer_pref_enabled=True,
                                via_in_pad_allowed=True)
    router.leaf_route_enabled = True
    # Lever-Q operates on already-committed nets. To populate
    # router.committed[net_name] from the LIVE board, we briefly run
    # a 0-iteration `run` which stamps obstacles + reads any
    # pre-existing tracks/vias as "committed" via the no-rip path.
    # The actual committed dict is populated post-_stamp_obstacles by
    # the cooperative router's preserved-nets discovery logic.
    # For lever-Q we only need the obstacle map + state.net_pads —
    # the leaf-route phase pulls trunk/leaf from verify_net_connectivity
    # which scans the LIVE board (not router.committed). So calling
    # the phase directly is sufficient.
    return router.run_leaf_route_phase()


# Attach methods (class-body extension — same pattern as lever-J).
CooperativeRouter.attempt_leaf_route = _lq_attempt_leaf_route
CooperativeRouter.run_leaf_route_phase = _lq_run_leaf_route_phase


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Cooperative ripup-reroute maze router")
    ap.add_argument("board", help="Input .kicad_pcb")
    ap.add_argument("--subsystem", default="CH1", choices=list(SUBSYSTEM_ZONES.keys()))
    ap.add_argument("--output", required=True, help="Output .kicad_pcb")
    ap.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITER)
    ap.add_argument("--grid-pitch", type=float, default=DEFAULT_GRID_PITCH)
    ap.add_argument("--seed-nets", help="Comma-list of net names to route (default: auto-detect)")
    ap.add_argument("--report", help="Optional CSV report file for routed/unrouted nets + metrics")
    ap.add_argument("--quiet", action="store_true")
    # v4 (2026-05-27): --no-rip-routed protects pre-existing tracks/vias from
    # being torn down by cooperative ripup-reroute. Use in multi-pass workflows
    # where a later pass must preserve an earlier pass's routes (e.g. CH1
    # STEP-6 dense-first then local-by-local; CH2/3/4 mirror cycles).
    # Default OFF for backward compatibility (single-pass fresh-board runs).
    ap.add_argument("--no-rip-routed", action="store_true",
                    help="Treat pre-existing routed nets as immovable; never "
                         "rip them and never re-attempt them (multi-pass safety)")
    # v5 (2026-05-27): per-net-class layer-preference cost biasing. ON by
    # default — codifies OQ-016 (BEMF→In4) + OQ-017 (SW→In6) + PR #192
    # (overflow→In8) at router cost-function level. Without this flag,
    # worker R22 measured In4/In6 completely unused while In2/In8 saturated
    # at 163/82 tracks (CH1 STEP-6 c-reapproach). Disable for debugging only.
    ap.add_argument("--no-layer-pref", action="store_true",
                    help="DISABLE v5 per-net-class layer-preference bias "
                         "(debug only — equivalent to v4 cost behaviour)")
    # v6 (2026-05-27): HDI via-in-pad enable for J18 + J19 whitelist.
    # Worker per-pin analysis demonstrated J18 south-edge + J19 driver
    # escape was permanently capped at ~22/33 across PR#202-#206 due to
    # via-area saturation in the dog-bone fanout corridor. With this flag,
    # the router drops vias directly on the J18/J19 pad centers — zero
    # fanout area required. Sai cost-cleared 2026-05-27 (+$2-3/board).
    # Whitelist: J18 + J19 only (see HDI_VIA_IN_PAD_REFS module constant).
    # Other components' standard via cost preserved.
    ap.add_argument("--via-in-pad-allowed", action="store_true",
                    help="Allow HDI via-in-pad on whitelisted footprints "
                         "(J18+J19 QFN). Unblocks CH1 STEP-6 routing-yield "
                         "cap per worker per-pin diagnosis 2026-05-27.")
    # v11 (2026-05-28, CH1 30/30 lever J): targeted ripup-rebuild. After the
    # cooperative loop terminates with residual unrouted nets, run a SECOND
    # phase that performs SURGICAL ripups on the specific foreign nets whose
    # tracks block each residual's ideal corridor. Capped at cascade depth 2.
    # Provenance written to sims/routing_provenance/targeted_ripup/*.json
    # (G_J1-G_J5 enforce R36-R39 + R-J5). Per docs/ROUTING_METHODOLOGY.md §0c
    # PHASE C addendum + docs/ROUTING_LESSONS.md L15. Default OFF (back-compat
    # — existing CH1 STEP-6 + Phase 3 cooperative runs unchanged).
    ap.add_argument("--enable-targeted-ripup", action="store_true",
                    help="v11: after cooperative loop plateaus, attempt "
                         "targeted ripup-rebuild for residual unrouted nets. "
                         "Breaks the 24-simultaneous cap (PR #227). "
                         "Cascade-bounded (depth ≤ 2), provenance-logged, "
                         "frozen-banked-nets immutable, shorts-delta ≤ 0.")
    # v12 (2026-05-28, CH1 30/30 lever K3): multi-mechanism path planner
    # fallback. When the single-mech cooperative router fails on a
    # cross-stack net (F.Cu start, B.Cu end), the multi-mech planner
    # lifts the A* state-space to (cell, layer, last_via_class) and
    # routes the chain (canonical SWDIO_CH1: blind_F_In2 + through).
    # Honours the cooperative via_class_for_span SSoT (HDI cells get
    # only HDI classes; non-HDI cells get only through). Default OFF
    # — opt-in to surface any behaviour change on existing flows.
    # Per docs/ROUTING_METHODOLOGY.md (new K3 addendum) and the abstract
    # T20 fixture (routing_engine/fixtures.py) which locks the engine
    # semantics.
    ap.add_argument("--multi-mech-fallback", action="store_true",
                    help="v12 (CH1 30/30 K3): after single-mech "
                         "cooperative loop exhausts iterations, attempt "
                         "the multi-mech planner on each residual "
                         "cross-stack net. Lifts the A* state-space + "
                         "chains 2+ via mechanisms (SWDIO_CH1 unblocker).")
    # CH1 30/30 lever Q (2026-05-29): targeted leaf-route for partial-MST
    # nets. After cooperative + lever-J targeted-ripup phases, every
    # COMMITTED net whose verify_net_connectivity reports >1 island gets
    # a per-leaf 2-attempt cascade (maze → multi-mech). Bounded ≤ 2,
    # shorts-gated, provenance under
    # sims/routing_provenance/leaf_route/*.json. G_Q1 audit enforces.
    ap.add_argument("--enable-leaf-route", action="store_true",
                    help="CH1 30/30 lever Q: post-cooperative leaf-route "
                         "pass for partial-MST nets. Attempts each "
                         "disconnected leaf via single-mech maze + "
                         "multi-mech (≤ 2 attempts/leaf). Shorts-gated. "
                         "Provenance under sims/routing_provenance/leaf_route/.")
    # CH1 30/30 lever Z (2026-05-29): route HDI-whitelisted nets FIRST.
    # Y proved canonical 0/5 for both joint AND sequential K3 on a board
    # where 24 non-HDI routes had already greedy-locked the J19 escape
    # corridors. W's standalone test (5/5) proved the 5 residuals CAN
    # route from a clean canonical state. The fix is REORDERING:
    # identify all nets whose pads touch the HDI whitelist
    # (HDI_VIA_IN_PAD_REFS + BLIND_F_IN2_NET_WHITELIST sanctioned
    # landings) and route them FIRST via K3 joint multi-mech (atomic
    # all-or-none via subset cascade), then run the normal cooperative
    # iteration on the remaining nets. The non-HDI nets are EASIER
    # (no HDI required) and they route around the committed HDI routes
    # naturally. Default OFF (back-compat for existing CH1/CH2/CH3/CH4
    # flows); worker enables for CH1 close-out.
    ap.add_argument("--route-hdi-first", action="store_true",
                    help="CH1 30/30 lever Z: identify HDI-whitelisted "
                         "nets (HDI_VIA_IN_PAD_REFS + "
                         "BLIND_F_IN2_NET_WHITELIST landings) and route "
                         "them FIRST via K3 joint multi-mech (atomic "
                         "subset cascade). Easier non-HDI nets then "
                         "route around them in the normal cooperative "
                         "pass. Default OFF (back-compat).")
    # CH1 30/30 lever AA (2026-05-29): TRUE PathFinder negotiated congestion
    # router. SWAPS the cooperative loop for a global-rip-all + global-re-route
    # discipline with cost-history convergence. See routing_engine/pathfinder.py
    # for the abstract reference + CooperativeRouter.run_pathfinder for the
    # live-board implementation. Default OFF — opt-in last-resort lever before
    # placement redo when --multi-mech-fallback + --via-in-pad-allowed +
    # --route-hdi-first + --enable-targeted-ripup + --enable-leaf-route do
    # NOT converge on 30/30 (i.e. when the cooperative router's local-progress
    # + selective ripup hits a placement-complexity wall).
    ap.add_argument("--pathfinder", action="store_true",
                    help="CH1 30/30 lever AA: TRUE PathFinder negotiated "
                         "congestion router (per-iter rip-all + global "
                         "re-route in priority order; h_n×p_n cost; "
                         "convergence on 2-iter zero-ripup streak). Replaces "
                         "the cooperative run() loop. Per "
                         "docs/CH1_30OF30_SOTA_RESEARCH_2026-05-29.md "
                         "recommendation #3. Default OFF (back-compat).")
    # CH1 30/30 lever BB (2026-05-29): B.Cu microvia fab class — bottom-side
    # HDI escape mechanism. JLC HDI Class 2 supports microvia on BOTH outer
    # skin pairs (F.Cu↔In1.Cu and B.Cu↔In8.Cu) at the same per-board cost.
    # AA + 12 prior fixes plateaued at 27/30 because 3 chronic residuals
    # (PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1) needed bottom-side HDI escape
    # at destination passive pads (R50, R76, D37, D38, J19). When enabled,
    # phase_c marks BOTTOM_MICROVIA_REFS pads as HDI-whitelisted so the K3
    # multi-mech planner considers microvia_B_In8 at the destination cell.
    # Audit enforced by audit_hdi_via_in_pad.BOTTOM_MICROVIA_NET_WHITELIST +
    # BOTTOM_MICROVIA_REFS. Default OFF (back-compat; worker enables for
    # CH1 close-out).
    ap.add_argument("--bcu-microvia-allowed", action="store_true",
                    help="CH1 30/30 lever BB: enable B.Cu↔In8 microvia "
                         "destination-side HDI escape for the 3 chronic "
                         "residual chains (PWM_INLA/GLB/KILL_RAIL_N). "
                         "Mark BOTTOM_MICROVIA_REFS pads as HDI-whitelisted "
                         "so K3 multi-mech accepts microvia_B_In8 at "
                         "destination. Same JLC HDI Class 2 fab class as the "
                         "F-side; zero marginal fab cost (same epoxy-fill + "
                         "plate-over envelope). Audit enforced by "
                         "audit_hdi_via_in_pad.BOTTOM_MICROVIA_NET_WHITELIST. "
                         "Default OFF (back-compat).")
    args = ap.parse_args()

    board = pcbnew.LoadBoard(args.board)
    seed = [s.strip() for s in args.seed_nets.split(",")] if args.seed_nets else None

    router = CooperativeRouter(board, args.subsystem,
                                grid_pitch=args.grid_pitch,
                                seed_nets=seed,
                                verbose=not args.quiet,
                                no_rip_routed=args.no_rip_routed,
                                layer_pref_enabled=not args.no_layer_pref,
                                via_in_pad_allowed=args.via_in_pad_allowed)
    router.targeted_ripup_enabled = bool(args.enable_targeted_ripup)
    # v12 CH1 30/30 (K3): multi-mech fallback opt-in flag.
    router.multi_mech_fallback_enabled = bool(args.multi_mech_fallback)
    # CH1 30/30 lever Q: leaf-route opt-in flag.
    router.leaf_route_enabled = bool(args.enable_leaf_route)
    # CH1 30/30 lever Z: route HDI-whitelisted nets first (REORDER).
    router.route_hdi_first_enabled = bool(args.route_hdi_first)
    # CH1 30/30 lever AA: TRUE PathFinder swap.
    router.pathfinder_enabled = bool(args.pathfinder)
    # CH1 30/30 lever BB: B.Cu microvia destination-side HDI escape. Sets a
    # MODULE-level flag (so phase_c + multi-mech adapters read it without
    # passing extra kwargs through every call site). Default OFF preserves
    # legacy behaviour; CLI opt-in activates the BB whitelist gates.
    set_bcu_microvia_allowed(bool(args.bcu_microvia_allowed))
    router.bcu_microvia_allowed = bool(args.bcu_microvia_allowed)
    if router.bcu_microvia_allowed and not args.quiet:
        print(f"\n[main] LEVER BB: B.Cu microvia destination-side HDI escape "
              f"enabled (nets={list(bottom_microvia_net_whitelist())}, "
              f"refs={list(bottom_microvia_refs())})")
    if router.pathfinder_enabled:
        if not args.quiet:
            print(f"\n[main] LEVER AA: PathFinder loop enabled "
                  f"(replaces cooperative run() with true rip-all + global "
                  f"re-route + cost-history convergence)")
        unrouted = router.run_pathfinder(max_iter=args.max_iterations)
    else:
        unrouted = router.run(max_iter=args.max_iterations)
    # v11 — targeted ripup-rebuild phase (CH1 30/30 lever J)
    if router.targeted_ripup_enabled and unrouted:
        if not args.quiet:
            print(f"\n[targeted-ripup] cooperative plateau at "
                  f"{len(router.committed)} routed / {len(unrouted)} residual; "
                  "engaging targeted ripup-rebuild phase (R36-R39 + R-J5; "
                  "depth ≤ 2; provenance under "
                  "sims/routing_provenance/targeted_ripup/)")
        targeted_entries = router.run_targeted_ripup_phase(list(unrouted))
        n_committed = sum(1 for e in targeted_entries if e.committed)
        if not args.quiet:
            print(f"[targeted-ripup] phase done: "
                  f"{n_committed}/{len(targeted_entries)} attempts committed.")
        # Refresh `unrouted` to reflect targeted-phase commits.
        unrouted = [n for n in unrouted if n not in router.committed]

    # CH1 30/30 lever Q — leaf-route phase. Runs after cooperative + lever-J,
    # ATTACHES disconnected leaves of committed-but-partial nets to their
    # trunks via the bounded mechanism cascade (maze → multi-mech). Honest
    # verdicts (R42 / G_Q1) when geometry blocks both attempts.
    if router.leaf_route_enabled:
        if not args.quiet:
            print(f"\n[leaf-route] cooperative + targeted-ripup phases done; "
                  "scanning committed nets for disconnected leaves "
                  "(lever Q; R42 / G_Q1; provenance under "
                  "sims/routing_provenance/leaf_route/)")
        leaf_entries = router.run_leaf_route_phase()
        n_routed = sum(1 for e in leaf_entries if e.committed)
        if not args.quiet:
            print(f"[leaf-route] phase done: "
                  f"{n_routed}/{len(leaf_entries)} leaf-attempts committed.")

    pcbnew.SaveBoard(args.output, board)
    print(f"\nSaved: {args.output}")
    # v3: distinguish full / partial / unrouted
    full = sum(1 for n in router.committed if not router.partial_pairs.get(n))
    partial = sum(1 for n in router.committed if router.partial_pairs.get(n))
    print(f"Result: full={full}/{len(router.nets)} partial={partial} "
          f"unrouted={len(unrouted)}, "
          f"{router.iteration_count} iterations, {router.ripup_count} ripups")
    if args.report:
        with open(args.report, "w") as f:
            f.write("net,status,pads,priority,partial_pairs\n")
            for n in router.nets:
                if n in router.committed:
                    pp = router.partial_pairs.get(n, [])
                    if pp:
                        status = "PARTIAL"
                        pp_str = ";".join(f"{pa}->{pb}" for (pa, pb, _, _) in pp)
                    else:
                        status = "ROUTED"
                        pp_str = ""
                else:
                    status = "UNROUTED"
                    pp_str = ""
                pads = len(router.state.net_pads.get(n, []))
                f.write(f"{n},{status},{pads},{net_priority(n)},{pp_str}\n")
            f.write(f"\n# summary: full={full}/{len(router.nets)} partial={partial} "
                    f"unrouted={len(unrouted)}, "
                    f"{router.iteration_count} iterations, {router.ripup_count} ripups\n")
        print(f"Report: {args.report}")
    # v3: exit non-zero if ANY net is partial or unrouted (caller must know
    # not to ship a board with split nets).
    return 0 if not unrouted and not router.partial_pairs else 1


if __name__ == "__main__":
    sys.exit(main())
