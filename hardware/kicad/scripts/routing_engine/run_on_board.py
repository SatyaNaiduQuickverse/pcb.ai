#!/usr/bin/env python3
"""run_on_board.py — Engine Step 8a: the REAL-BOARD DRIVER + READ-ONLY VERDICT.

WHAT THIS IS
------------
The validated routing engine (Phases A/B/C, fixtures T1-T9) operates on an
ABSTRACT `fixtures.Problem` (pins/nets/doors/obstacles/via_slots/layers). This
driver is the BRIDGE: it reads the REAL CH1 geometry from a .kicad_pcb and builds
the SAME abstract `Problem` the engine consumes, then runs Phase A (capacity +
escape pre-check) → VERDICT + demand-vs-supply LEDGER, and Phase B (global plan)
IF Phase A is routable. It is the graduation exam's first half: point the proven
engine at the real board and get its HONEST verdict BEFORE any board mutation.

READ-ONLY. This driver NEVER writes a .kicad_pcb. It is the diagnosis, not the
cure (the mutation is Step 8b). It runs NO geometry router and NO sim — Phase A is
deterministic COUNTING; Phase B is a structural plan. Both are Pi-light and
subsystem-scoped (CH1 only — never loads/routes the full board).

THE KEY QUESTION (DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE + ..._2026-05-28)
---------------------------------------------------------------------------
The greedy cooperative router plateaued at 24/30 on CH1; 6 nets residual, ALL at
the J18 (QFN-32) / J19 (HVQFN-24) 0.5 mm-pitch escape ring. Does a GLOBAL PLAN
(with whitelisted HDI on J18/J19) route past 24/30 — i.e. does coordinated
regional escape allocation unlock the last ~6 nets that greedy could not? OR does
Phase A verdict that even a global plan + HDI cannot fit the escape demand at the
current placement → NEEDS-PLACEMENT-CHANGE (the honest "stop + escalate" T9
outcome)? Either answer is a valid graduation result — we report the LEDGER that
proves it; we DO NOT force a route.

THE REAL-GEOMETRY → ABSTRACT MAPPING (every assumption is documented here)
--------------------------------------------------------------------------
This mapping IS the bridge; it is stated explicitly + conservatively. See
`MODELLING_ASSUMPTIONS` (printed in --verdict) for the authoritative list.

PINS  — Every pad of every CH1-zone footprint, PLUS the numbered signal pins of
        J18 (QFN-32, pins 1-32) and J19 (HVQFN-24, pins 1-24). Pad ids are
        "<ref>.<padname>". The EP thermal pad + thermal-via pads are excluded
        from the J18/J19 escape-pin set (they are not signal escapes); they are
        still present as ordinary pins via the general pad sweep but contribute no
        escape demand.

NETS  — The CH1 SIGNAL nets that need within-subsystem routing: exactly the set
        `route_subsystem_cooperative.should_route(net) AND ≥2 pads in the CH1
        zone`. This REUSES the cooperative router's net classifier (its
        SKIP_NET_PATTERNS exclude poured planes GND/+VMOTOR/+V*/+3V*/MOTOR/SHUNT
        and NC/unnamed nets), so the engine sees exactly the nets the router was
        asked to route — apples-to-apples with the 24/30 result. Each net is
        tagged routed (≥2 tracks already) vs residual (<2 tracks) so the ledger
        can speak to "past 24/30".

DOORS — CH1's I/O ports from BOARD_INVARIANTS §Subsystem I/O ports:
          S2→CH1 (40,50) 4 mm  +VMOTOR/GND   (power feed; not a signal door)
          S5→CH1 (35,65) 2 mm  +V5/+V9/+3V3  (BEC rails; power)
          S6→CH1 (17,82) 2 mm  DShot/TLM/KILL (FC commands — SIGNAL door)
        PLUS the In8 FET-region universal escape (BOARD_INVARIANTS §In8 MULTI-USE
        item (b)) modelled as a door for residual stuck nets. Capacity per door =
        floor(width / track_pitch) × n_signal_layers_spanned (Door.capacity_from_
        width). CONSERVATIVE: we count only the SIGNAL layers a door realistically
        spans for these nets (see DOOR_LAYER_SPAN). Power doors carry power nets,
        which are NOT in the routable set, so their capacity is informational.

VIA_SLOTS — Per-IC-side escape slots at J18 and J19 (the T9/J18-J19 model — this
        is the BINDING supply for the verdict). For each of the 4 sides of each
        IC, the standard (non-HDI) escape supply = the number of dog-bone fanout
        vias that fit a single fanout band at standard via pitch
        (via_pad+clearance ≈ 0.8 mm) across the side's pin span:
            std_slots = floor(side_pin_span / STD_VIA_FANOUT_PITCH)
        The HDI-only extra supply (enabled only on the J18/J19 whitelist) is
        via-in-pad: ONE microvia directly under each pin pad, so the side's total
        supply with HDI = one per pin (= n_pins on the side). The HDI-only count
        is therefore (n_pins − std_slots), flagged hdi_only=True. This is the
        physical escalation lever (DEEP_RESEARCH 2026-05-28 §"DIAGNOSIS
        CORRECTION": HDI via-in-pad — not more layers — is the operative fix for
        the QFN pin-escape-density wall). Deeper full-stack escapes are NOT
        hdi_only here (they are standard through-vias; In1 is GND so they short
        neighbours — captured as the standard cap, not extra HDI supply).

OBSTACLES — Plane splits / keep-outs in the CH1 zone. We do NOT fabricate plane
        splits (the In1/In3/In7 GND + In5 +VMOTOR planes are continuous in CH1);
        we emit the residual escape constraint as the via-slot model, not as
        obstacles. (Body keep-outs would only affect the geometry-lite door
        reachability inference; the escape verdict is via-slot-governed.) Emitting
        zero plane_split obstacles is the conservative + honest choice — we have
        not measured a CH1-zone plane gap, so we assert none.

LAYERS — The 10L stackup from BOARD_INVARIANTS: F.Cu / In1=GND / In2=sig /
        In3=GND / In4=sig(BEMF) / In5=+VMOTOR / In6=sig(SW) / In7=GND / In8=sig /
        B.Cu = 6 signal + 4 plane (role tags drive the engine's signal/plane
        split).

WHY THE VERDICT IS ESCAPE-GOVERNED (not door-governed)
------------------------------------------------------
phase_a._decide_verdict: when via_slots exist (they do — J18/J19), the ESCAPE
LEDGER governs the verdict (the worst IC side, per [[reference-averaging-masks-
local-failure]]). The door bipartite feasibility is still computed + reported
(informational), but the binding question — "can the residual nets escape the QFN
pin ring?" — is exactly the escape ledger. This matches the empirical root cause:
the 24/30 wall is QFN escape-field saturation, NOT board-wide channel congestion.

USAGE
-----
  python3 run_on_board.py --board /tmp/ch1_board_readonly.kicad_pcb \
      --subsystem CH1 --verdict

pcbnew is LAZY-imported (only when a board is actually loaded) so this module
imports cleanly on hosts without KiCad (for unit-style inspection of the mapping).
Pure-stdlib otherwise; reuses route_subsystem_cooperative for net classification +
zone definition (single source of truth — no re-deriving the net filter).
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

# Engine modules (import-only view; no answer leakage — Phase A/B consume Problem).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SCRIPTS = os.path.dirname(_HERE)  # hardware/kicad/scripts
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import fixtures as F          # Pin/Net/Door/ViaSlot/Obstacle/Layer/Problem
import phase_a as PA
import phase_b as PB


# ----------------------------------------------------------------------------
# MODELLING CONSTANTS (every one cited to a doc / physics — conservative)
# ----------------------------------------------------------------------------

# Track pitch for door capacity = trace + clearance. The CH1 signal trace is
# 0.15 mm (MASTER_COOP_ROUTER TRACE) and board-min clearance is 0.20 mm
# (route_subsystem_cooperative.CLEARANCE_MM / audit_power_drc). 0.15+0.20 = 0.35.
# Conservative (wider pitch ⇒ fewer tracks ⇒ lower supply ⇒ no over-claim).
TRACK_PITCH_MM = 0.35

# Standard (non-HDI) dog-bone fanout via pitch in the escape band: a 0.6 mm via
# pad + 0.20 mm clearance ⇒ centre-to-centre ≈ 0.80 mm (MASTER_COOP_ROUTER pad
# model: "via must land ≥ pad_half+CLEARANCE+via_radius ≈ 0.83 mm from a foreign
# pad centre" — a single fanout row hosts one via per ~0.8 mm). At 0.5 mm pin
# pitch this is why standard fanout cannot give one via per pin (the 24/30 wall).
STD_VIA_FANOUT_PITCH_MM = 0.80

# Signal pins per side / pitch by footprint (verified from the real board geometry
# in extract_problem; these are the design values used to label the supply model).
# J18 = QFN-32 (8 pins/side), J19 = HVQFN-24 (6 pins/side), both 0.5 mm pitch.

# Which signal layers a CH1 signal DOOR realistically spans (for capacity). The
# S6→CH1 signal door feeds DShot/TLM/KILL which route on In2/In8 (MASTER_COOP_
# ROUTER LAYER_PREF). We count 1 effective signal layer per 2 mm door cross-
# section conservatively (a 2 mm door does not cleanly carry tracks on every one
# of the 6 signal layers at once through one corridor cross-section).
DOOR_SIGNAL_LAYERS = 1

# CH1 zone + net classifier come from the cooperative router (single source).
try:
    import route_subsystem_cooperative as RC
    _HAVE_RC = True
except Exception:  # pragma: no cover - RC is always present in repo
    RC = None
    _HAVE_RC = False

# OQ-020 ACTIVATE 2026-05-28: the 4-net whitelist for blind F.Cu↔In2 (the
# layer-aware HDI lever that DOES reach a signal layer — In2 — on the locked
# 10L stackup). Source-of-truth: BOARD_INVARIANTS §"HDI Class extension:
# blind/buried F.Cu↔In2" + audit_hdi_via_in_pad.BLIND_F_IN2_NET_WHITELIST +
# pcbai_fpv4in1.kicad_dru "HDI blind F-In2" rule set. Re-imported lazily
# from the audit module so the SSoT is the audit (which the JLC DRC also
# enforces); failing back to a hardcoded tuple keeps this module importable
# on hosts without pcbnew (the audit imports pcbnew at module load).
try:
    from audit_hdi_via_in_pad import BLIND_F_IN2_NET_WHITELIST  # type: ignore
except Exception:
    BLIND_F_IN2_NET_WHITELIST = ("BSTB", "PWM_INHB", "SWDIO", "PWM_INLA")


MODELLING_ASSUMPTIONS = [
    "PINS = all CH1-zone footprint pads + J18(QFN-32 pins 1-32) + J19(HVQFN-24 "
    "pins 1-24) numbered signal pins; EP/thermal-via pads excluded from escape set.",
    "NETS = route_subsystem_cooperative.should_route(net) AND >=2 pads in CH1 "
    "zone (REUSES the router's classifier so engine sees exactly the routed set). "
    "Poured planes (GND/+VMOTOR/+V*/+3V*/MOTOR/SHUNT) + NC/unnamed are EXCLUDED.",
    "Each net tagged routed (>=2 tracks on board) vs residual (<2 tracks) — the "
    "residual set is the 24/30 wall; demand attributed to the IC side its pin sits on.",
    "DOORS = BOARD_INVARIANTS S2->CH1(40,50,4mm power), S5->CH1(35,65,2mm power), "
    "S6->CH1(17,82,2mm SIGNAL) + In8 FET-region escape door; capacity = "
    f"floor(width/{TRACK_PITCH_MM}mm pitch) x {DOOR_SIGNAL_LAYERS} signal layer.",
    "VIA_SLOTS per IC side use REMAINING capacity (the honest 24/30 model) AND "
    "LAYER-AWARE classes (OQ-020 ACTIVATE 2026-05-28; T12 root fix): "
    f"std_total = floor(side_pin_span / {STD_VIA_FANOUT_PITCH_MM}mm fanout pitch) "
    "(through-vias reach B.Cu = SIGNAL = count as std supply); already-routed "
    "signal nets on the side CONSUMED std slots; std_REMAINING = max(0, "
    "std_total - routed_consumed). HDI microvia F.Cu↔In1 (target=In1=GND PLANE) "
    "= emitted for ledger honesty but DROPPED from signal-escape supply by the "
    "layer-aware engine (engine v1 counted it naively — the OQ-020 bug). "
    "HDI blind/buried F.Cu↔In2 (target=In2=SIGNAL) = the OQ-020 ACTIVATE lever, "
    "available ONLY for the 4 whitelisted nets (BSTB/PWM_INHB/SWDIO/PWM_INLA) "
    "per BOARD_INVARIANTS; one blind via per pin (via-in-pad). Power/NC/"
    "unconnected pins consume no escape slot.",
    "OBSTACLES = none fabricated: In1/In3/In7 GND + In5 +VMOTOR planes are "
    "continuous in CH1 (no measured CH1-zone plane split) — conservative/honest.",
    "LAYERS = 10L stackup (F.Cu/In1=GND/In2/In3=GND/In4=BEMF/In5=+VMOTOR/In6=SW/"
    "In7=GND/In8/B.Cu) = 6 signal + 4 plane.",
    "VERDICT is ESCAPE-governed (phase_a: via_slots present => escape ledger "
    "drives the verdict; worst IC side governs per averaging-masks-local-failure). "
    "Door feasibility is computed + reported but informational for this question.",
    "READ-ONLY: no .kicad_pcb is written; no geometry router, no sim is run.",
]


# ----------------------------------------------------------------------------
# Per-IC-side escape model (the binding supply structure).
# ----------------------------------------------------------------------------

@dataclass
class _SideModel:
    ic_side: str          # e.g. "J18_S"
    n_pins: int           # signal pins on this side
    span_mm: float        # pin-row span on this side
    std_total: int        # standard dog-bone fanout vias that fit the side span
    routed_consumed: int  # std slots ALREADY consumed by already-routed sig nets
    std_slots: int        # REMAINING std supply = max(0, std_total - consumed)
    hdi_total: int        # HDI via-in-pad TOTAL supply (per-pin microvia, n_pins-std_total)
    hdi_slots: int        # HDI via-in-pad supply still available (REMAINING)
    demand: int           # residual nets needing to escape this side
    residual_nets: tuple  # the residual net ids on this side
    # OQ-020 ACTIVATE 2026-05-28: blind F.Cu↔In2 supply (layer-aware).
    # The existing microvia F.Cu↔In1 class BOTTOMS ON the In1=GND PLANE
    # and is therefore DROPPED from signal escape supply by the layer-aware
    # engine (phase_a._slot_reaches_signal); the only HDI class that
    # delivers real signal escape for the 4 residual nets is the
    # blind/buried F.Cu↔In2. Per the BOARD_INVARIANTS whitelist this is
    # available ONLY on the 4 named nets (BSTB / PWM_INHB / SWDIO /
    # PWM_INLA), so blind_f_in2_supply == # of residual nets on this side
    # whose net name is in BLIND_F_IN2_NET_WHITELIST.
    blind_f_in2_supply: int = 0   # per-side OQ-020 blind F-In2 capacity (signal)
    blind_f_in2_nets: tuple = ()  # the residual nets entitled to a blind F-In2


def _classify_sides(board, ref, n_sig, residual_nets, routed_nets):
    """Return [_SideModel,...] for the 4 sides of `ref` (numbered signal pins
    1..n_sig only). Side = N/S/E/W by which axis dominates the pin's offset from
    the footprint centre.

    SUPPLY MODEL (the honest, REMAINING-capacity version — this is what makes the
    verdict faithful to the empirical 24/30 wall):
      std_total = floor(side_pin_span / STD_VIA_FANOUT_PITCH) — the dog-bone
                  fanout vias that physically fit a single band across the side.
      routed_consumed = # of ALREADY-ROUTED signal nets whose pin is on this side
                  — these have ALREADY placed an escape via in the fanout band,
                  consuming std slots. (The 24/30 routed nets are immovable here.)
      std_slots (REMAINING) = max(0, std_total - routed_consumed) — the std slots
                  left for the RESIDUAL nets. THIS is the binding std supply.
      hdi_slots = HDI via-in-pad supply still available = max(0, n_pins -
                  routed_consumed - std_slots): one microvia per pin, minus what
                  routed nets + remaining std already cover. The escalation lever.
    Power/NC/unconnected pins do NOT consume routing escape slots (no signal
    escape via). residual_nets is the residual signal demand sitting on this side.
    """
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return []
    c = fp.GetPosition()
    cx, cy = RC.iu_to_mm(c.x), RC.iu_to_mm(c.y)
    sides = {"N": [], "S": [], "E": [], "W": []}
    for pad in fp.Pads():
        pn = pad.GetPadName()
        if not pn.isdigit():
            continue
        ipn = int(pn)
        if ipn < 1 or ipn > n_sig:
            continue
        net = pad.GetNet()
        nn = net.GetNetname() if net else ""
        p = pad.GetPosition()
        x, y = RC.iu_to_mm(p.x), RC.iu_to_mm(p.y)
        dx, dy = x - cx, y - cy
        if abs(dx) > abs(dy):
            sides["E" if dx > 0 else "W"].append((ipn, nn, x, y))
        else:
            sides["S" if dy > 0 else "N"].append((ipn, nn, x, y))
    out = []
    for s in ("N", "S", "E", "W"):
        ps = sides[s]
        if not ps:
            continue
        if s in ("N", "S"):
            span = max(p[2] for p in ps) - min(p[2] for p in ps)
        else:
            span = max(p[3] for p in ps) - min(p[3] for p in ps)
        std_total = int(span // STD_VIA_FANOUT_PITCH_MM)
        # already-routed signal nets on this side (consume std fanout slots).
        consumed = len({p[1] for p in ps if p[1] in routed_nets})
        std_remaining = max(0, std_total - consumed)
        resid = tuple(sorted({p[1] for p in ps if p[1] in residual_nets}))
        # HDI microvia F.Cu↔In1 TOTAL = one per pin minus the std fanout band
        # (n_pins - std_total); REMAINING = total minus what routed beyond std
        # already used. WARNING — LAYER-AWARE NOTE: on the locked 10L stackup
        # this class BOTTOMS ON In1=GND (PLANE) so it is NOT a signal escape;
        # the engine's `phase_a.side_supply` DROPS it from supply via
        # `_slot_reaches_signal` (target_layer="In1" + role="plane"). We still
        # emit the slots into the Problem so the ledger shows them honestly
        # (helps diagnose old-engine miscounts), but they contribute 0 to
        # the layer-aware supply. This is the OQ-020 root fix.
        hdi_total = max(0, len(ps) - std_total)
        hdi_remaining = max(0, len(ps) - consumed - std_remaining)
        # OQ-020 ACTIVATE 2026-05-28 (Sai cost-OK): the blind/buried F.Cu↔In2
        # class IS a signal escape (target=In2, role=signal). Available ONLY
        # for residual nets whose name is in BLIND_F_IN2_NET_WHITELIST (per
        # BOARD_INVARIANTS §"HDI Class extension: blind/buried F.Cu↔In2";
        # NARROWEST-possible scope, exactly the 4 nets the worker analysis
        # identified). Supply = # of residual nets on this side eligible
        # (one blind via per pin, via-in-pad). This is the layer-aware lever
        # the engine v1 was missing.
        blind_eligible = tuple(sorted(n for n in resid
                                      if n in BLIND_F_IN2_NET_WHITELIST))
        blind_supply = len(blind_eligible)
        out.append(_SideModel(
            ic_side=f"{ref}_{s}",
            n_pins=len(ps),
            span_mm=round(span, 2),
            std_total=std_total,
            routed_consumed=consumed,
            std_slots=std_remaining,
            hdi_total=hdi_total,
            hdi_slots=hdi_remaining,
            demand=len(resid),
            residual_nets=resid,
            blind_f_in2_supply=blind_supply,
            blind_f_in2_nets=blind_eligible,
        ))
    return out


# ----------------------------------------------------------------------------
# extract_problem — the bridge: real .kicad_pcb -> abstract fixtures.Problem.
# ----------------------------------------------------------------------------

def extract_problem(board_path, subsystem="CH1"):
    """Build a SUBSYSTEM-SCOPED fixtures.Problem from REAL .kicad_pcb geometry.

    Returns (problem, meta) where `meta` carries provenance the verdict prints:
      meta['routable_nets']   : net ids the cooperative router would target
      meta['routed_nets']     : net ids already routed (>=2 tracks)
      meta['residual_nets']   : net ids unrouted (<2 tracks) — the 24/30 wall
      meta['side_models']     : list[_SideModel] (the escape supply structure)
      meta['n_footprints']    : CH1-zone footprint count
    """
    import pcbnew  # lazy — only needed when actually loading a board

    if not _HAVE_RC:
        raise RuntimeError("route_subsystem_cooperative not importable — needed "
                           "for the net classifier + zone definition")
    if subsystem not in RC.SUBSYSTEM_ZONES:
        raise ValueError(f"unknown subsystem {subsystem!r}; "
                         f"known: {sorted(RC.SUBSYSTEM_ZONES)}")
    zone = RC.SUBSYSTEM_ZONES[subsystem]  # (xmin,ymin,xmax,ymax)
    zx0, zy0, zx1, zy1 = zone

    board = pcbnew.LoadBoard(board_path)  # READ-ONLY: never .Save()
    bs = RC.BoardState(board, zone)

    # ---- NETS: should_route AND >=2 pads in zone (router's exact criterion) --
    # Also classify INTERNAL (all pads in zone — route within CH1, escape-
    # governed) vs CROSSING (>=1 pad outside zone — must traverse a CH1 I/O DOOR).
    # This distinction matters: the DOORS model subsystem I/O boundary crossings;
    # internal nets do NOT consume door supply (they route inside the channel).
    routable, routed, residual, crossing = [], [], [], []
    for nn, pads in bs.net_pads.items():
        if not RC.should_route(nn):
            continue
        in_zone = [p for p in pads if zx0 <= p[2] <= zx1 and zy0 <= p[3] <= zy1]
        if len(in_zone) < 2:
            continue
        routable.append(nn)
        tracks = sum(1 for lt in bs.track_obstacles_by_layer.values()
                     for (_, _, _, _, _, owner) in lt if owner == nn)
        (routed if tracks >= 2 else residual).append(nn)
        out_zone = [p for p in pads
                    if not (zx0 <= p[2] <= zx1 and zy0 <= p[3] <= zy1)]
        if out_zone:
            crossing.append(nn)
    routable.sort(); routed.sort(); residual.sort(); crossing.sort()
    residual_set = set(residual)

    # ---- PINS: every CH1-zone footprint pad (id = ref.padname) --------------
    pins = []
    seen = set()
    n_fp = 0
    for fp in board.GetFootprints():
        fpp = fp.GetPosition()
        fx, fy = RC.iu_to_mm(fpp.x), RC.iu_to_mm(fpp.y)
        if not (zx0 <= fx <= zx1 and zy0 <= fy <= zy1):
            # include footprint if ANY pad is in the zone (channel-internal)
            any_in = False
            for pad in fp.Pads():
                p = pad.GetPosition()
                px, py = RC.iu_to_mm(p.x), RC.iu_to_mm(p.y)
                if zx0 <= px <= zx1 and zy0 <= py <= zy1:
                    any_in = True
                    break
            if not any_in:
                continue
        n_fp += 1
        ref = fp.GetReference()
        for pad in fp.Pads():
            p = pad.GetPosition()
            px, py = RC.iu_to_mm(p.x), RC.iu_to_mm(p.y)
            pid = f"{ref}.{pad.GetPadName()}"
            if pid in seen:
                continue
            seen.add(pid)
            # signal layer the pad escapes on (first signal layer it occupies)
            layer_name = "F.Cu"
            pins.append(F.Pin(pid, round(px, 4), round(py, 4), layer_name))

    # ---- NETS as fixtures.Net: connect each net's in-zone pads -------------
    nets = []
    for nn in routable:
        pad_ids = []
        for (ref, padname, x, y, layers, sx, sy) in bs.net_pads.get(nn, []):
            if zx0 <= x <= zx1 and zy0 <= y <= zy1:
                pad_ids.append(f"{ref}.{padname}")
        # keep only pad ids that exist in pins (zone footprints)
        pad_ids = [pid for pid in pad_ids if pid in seen]
        if len(pad_ids) < 2:
            continue
        nets.append(F.Net(nn, tuple(pad_ids), net_class=_net_class(nn)))

    # ---- VIA_SLOTS: per-IC-side escape model at J18 + J19 ------------------
    routed_set = set(routed)
    side_models = []
    for ref, n_sig in (("J18", 32), ("J19", 24)):
        side_models.extend(
            _classify_sides(board, ref, n_sig, residual_set, routed_set))
    # Emit the per-side supply as LAYER-TAGGED via classes — the layer-aware
    # engine drops plane-bottoming classes (OQ-020 root fix). Three classes:
    #   1. STANDARD (target=None back-compat = signal-usable): the dog-bone
    #      fanout band — through-vias reach B.Cu signal, counted in std.
    #   2. HDI microvia F.Cu↔In1 (target="In1", role="plane"): the existing
    #      whitelisted microvia class. BOTTOMS ON GND on the 10L stackup so
    #      DROPPED from signal escape supply by the layer-aware engine.
    #      Emitted into the Problem honestly (visible in the ledger) but
    #      contributes 0 to layer-aware supply. (engine v1 counted it as +1
    #      supply naively — the OQ-020 bug; T12 fixture proves this.)
    #   3. HDI blind/buried F.Cu↔In2 (target="In2", role="signal"): the
    #      OQ-020 ACTIVATE lever — REAL signal escape. Available only on the
    #      4 named whitelist nets (BSTB / PWM_INHB / SWDIO / PWM_INLA),
    #      one blind via per pin (via-in-pad). NARROWEST-possible scope per
    #      BOARD_INVARIANTS + audit_hdi_via_in_pad.
    # The engine's REMAINING-capacity model (escape_ledger consumed_by_side)
    # still deducts already-consumed std slots; the driver feeds raw geometry
    # SUPPLY + CONSUMED count and the engine owns the remaining math.
    via_slots = []
    for sm in side_models:
        for i in range(sm.std_total):
            via_slots.append(F.ViaSlot(
                f"{sm.ic_side}_STD{i}", 0.0, 0.0, sm.ic_side,
                hdi_only=False, target_layer=None, via_class="through"))
        # The HDI microvia F-In1 class — PLANE-bottoming; emitted for ledger
        # honesty, DROPPED by layer-aware supply (T12 root fix).
        for i in range(sm.hdi_total):
            via_slots.append(F.ViaSlot(
                f"{sm.ic_side}_HDIuv_FIn1_{i}", 0.0, 0.0, sm.ic_side,
                hdi_only=True, target_layer="In1",
                via_class="microvia_F_In1"))
        # OQ-020 ACTIVATE: the blind F-In2 class — SIGNAL-targeting. Available
        # only for nets on the BLIND_F_IN2_NET_WHITELIST (NARROWEST scope).
        for i in range(sm.blind_f_in2_supply):
            via_slots.append(F.ViaSlot(
                f"{sm.ic_side}_HDIblind_FIn2_{i}", 0.0, 0.0, sm.ic_side,
                hdi_only=True, target_layer="In2",
                via_class="blind_F_In2"))

    # ---- DOORS: BOARD_INVARIANTS CH1 I/O ports + In8 escape door -----------
    doors = _ch1_doors()

    # ---- OBSTACLES: none fabricated (continuous planes in CH1) -------------
    obstacles = ()

    # ---- LAYERS: 10L stackup ------------------------------------------------
    layers = _stackup_10L()

    problem = F.Problem(
        name=f"{subsystem}_real",
        layers=layers,
        pins=tuple(pins),
        nets=tuple(nets),
        doors=doors,
        obstacles=obstacles,
        via_slots=tuple(via_slots),
    )
    meta = {
        "subsystem": subsystem,
        "zone": zone,
        "routable_nets": routable,
        "routed_nets": routed,
        "residual_nets": residual,
        "crossing_nets": crossing,    # boundary-crossing nets (the door demand)
        "side_models": side_models,
        "n_footprints": n_fp,
    }
    return problem, meta


def _net_class(nn):
    """Map a CH1 net name to the engine net_class family (MASTER_COOP_ROUTER
    LAYER_PREF families). Informational; does not change the escape verdict."""
    if nn.startswith("BEMF_"):
        return "BEMF"
    if nn.startswith("PWM_"):
        return "PWM"
    if nn.startswith("CSA_"):
        return "signal"
    if nn.startswith(("SWDIO", "SWCLK", "NRST", "BOOT0")):
        return "control"
    if nn.startswith(("GH", "GL", "BST")):
        return "control"
    return "signal"


def _ch1_doors():
    """CH1 I/O ports from BOARD_INVARIANTS §Subsystem I/O ports + In8 escape.
    capacity_tracks = floor(width/TRACK_PITCH) × DOOR_SIGNAL_LAYERS. The power
    doors (S2/S5) carry power nets (not in the routable signal set) — their
    capacity is informational. The S6 signal door + In8 escape door are the
    signal-relevant supply."""
    def cap(w):
        return F.Door.capacity_from_width(w, TRACK_PITCH_MM, DOOR_SIGNAL_LAYERS)
    return (
        F.Door("S2_CH1", 40.0, 50.0, 4.0, ("In2",), cap(4.0)),   # +VMOTOR/GND power
        F.Door("S5_CH1", 35.0, 65.0, 2.0, ("In2",), cap(2.0)),   # +V5/+V9/+3V3 power
        F.Door("S6_CH1", 17.0, 82.0, 2.0, ("In2", "In8"), cap(2.0)),  # DShot/TLM/KILL signal
        # In8 FET-region universal escape (BOARD_INVARIANTS §In8 MULTI-USE (b)):
        # thin In8 trace segments for residual stuck nets. Width ~3 mm pour band.
        F.Door("In8_FET_ESCAPE", 10.0, 65.0, 3.0, ("In8",), cap(3.0)),
    )


def _stackup_10L():
    """The 10L stackup from BOARD_INVARIANTS §Board geometry."""
    return (
        F.Layer("F.Cu", "signal"),
        F.Layer("In1", "plane", "GND"),
        F.Layer("In2", "signal"),
        F.Layer("In3", "plane", "GND"),
        F.Layer("In4", "signal"),       # BEMF dedicated
        F.Layer("In5", "plane", "+VMOTOR"),
        F.Layer("In6", "signal"),       # SW escape
        F.Layer("In7", "plane", "GND"),
        F.Layer("In8", "signal"),       # multi-use escape/overflow
        F.Layer("B.Cu", "signal"),
    )


# ----------------------------------------------------------------------------
# verdict — run Phase A (+ Phase B if routable), print the ledger.
# ----------------------------------------------------------------------------

def _measured_side_inputs(meta):
    """Translate the driver's geometry MEASUREMENT (the per-IC-side _SideModel
    extracted from the real board) into the two engine inputs the now-native
    `phase_a.escape_ledger` / `phase_b.plan` accept:

      demand_by_side[side]   = residual nets that must STILL escape that side
                               (the 24/30 wall demand the driver measured per side)
      consumed_by_side[side] = std fanout slots ALREADY consumed by the routed
                               nets on that side (so the engine's REMAINING-
                               capacity model deducts them natively)

    This is the ONLY escape math left in the driver — and it is pure geometry
    MEASUREMENT (which net's pin is on which side, how many already routed), NOT
    ledger/verdict logic. The engine owns the overflow + verdict (geometry in,
    verdict out). The per-side std/HDI SUPPLY itself is the via_slots the driver
    emitted into the Problem (side_supply reads them), so the engine derives the
    REMAINING std supply = std_total(from via_slots) - consumed here."""
    demand_by_side = {sm.ic_side: sm.demand for sm in meta["side_models"]}
    consumed_by_side = {sm.ic_side: sm.routed_consumed
                        for sm in meta["side_models"]}
    return demand_by_side, consumed_by_side


def verdict(board_path, subsystem="CH1"):
    """Run the ENGINE on the extracted Problem; print VERDICT + demand-vs-supply
    LEDGER per door + per J18/J19 IC-side escape. Run Phase B IF routable. Return
    (phase_a_result, phase_b_result_or_None, meta).

    THIN DRIVER (Step 8a.5): the per-side escape ledger + the internal/crossing
    distinction the driver used to compute LOCALLY now live in the engine
    (phase_a.escape_ledger per-side + REMAINING-capacity model; phase_b
    classify_net_topology). The driver only MEASURES the geometry inputs
    (demand_by_side / consumed_by_side / crossing_nets) and hands them to the
    engine — there is NO driver-side ledger math and NO verdict override."""
    problem, meta = extract_problem(board_path, subsystem)
    demand_by_side, consumed_by_side = _measured_side_inputs(meta)
    crossing = meta.get("crossing_nets", [])

    _print_header(problem, meta)

    # ---- PHASE A: the capacity + escape pre-check (the VERDICT) -------------
    # Native per-side escape ledger: feed the MEASURED per-side residual demand +
    # the std slots already consumed by routed nets; the engine derives REMAINING
    # std supply, the worst-side overflow, and the verdict (no driver override).
    a = PA.solve(problem, demand_by_side=demand_by_side,
                 consumed_by_side=consumed_by_side,
                 crossing_override=crossing)
    print()
    print(PA.format_report(f"{subsystem} (real board)", a))
    print()
    # The door ledger now reflects ONLY the genuine CROSSING nets (the engine
    # classifies internal vs crossing; the driver passes the measured boundary-
    # crossing set as the authoritative override). No phantom stranded nets.
    print(f"  DOOR LEDGER: {len(crossing)} CROSSING net(s) {crossing} traverse a "
          f"CH1 boundary door; the other {len(problem.nets) - len(crossing)} "
          f"net(s) are INTERNAL (escape/within-zone governed) and consume NO door "
          f"capacity — they are NOT bipartite-assigned to doors (no phantom "
          f"strand). The binding constraint is the QFN escape (via-slot ledger).")
    print()

    # ---- The escape ledger headline (the binding answer) -------------------
    _print_escape_headline(a, meta)

    # ---- PHASE B: global plan IF Phase A is routable -----------------------
    b = None
    if a["verdict"] in ("ROUTABLE", "NEEDS-HDI"):
        # NEEDS-HDI is routable WITH the whitelisted HDI lever (J18/J19) — the
        # global plan is meaningful; run it. NEEDS-PLACEMENT-CHANGE / INFEASIBLE:
        # the honest answer is STOP + escalate; we do NOT force a plan.
        print()
        print("=" * 72)
        print(f"PHASE A verdict {a['verdict']} is routable (HDI lever applies) — "
              "running Phase B GLOBAL PLAN...")
        print("=" * 72)
        # Phase B natively classifies internal/crossing (crossing override = the
        # driver's measured boundary set) AND uses the same per-side escape ledger
        # (measured demand + consumed). The verdict is the engine's — no override.
        gp = PB.plan(problem, crossing_override=crossing,
                     demand_by_side=demand_by_side,
                     consumed_by_side=consumed_by_side)
        b = gp
        print(PB.format_plan(f"{subsystem} (real board)", problem, gp))
    else:
        print()
        print("=" * 72)
        print(f"PHASE A verdict {a['verdict']} — NOT routable at this placement "
              "even with the lever; Phase B GLOBAL PLAN SKIPPED (honest STOP + "
              "escalate, the T9 lesson). The ledger above is the proof.")
        print("=" * 72)

    return a, b, meta


def _print_header(problem, meta):
    print("=" * 72)
    print(f"ENGINE STEP 8a — REAL-BOARD DRIVER (READ-ONLY) — {meta['subsystem']}")
    print("=" * 72)
    print(f"  zone: {meta['zone']}   footprints in zone: {meta['n_footprints']}")
    print(f"  pins extracted: {len(problem.pins)}")
    cross = meta.get("crossing_nets", [])
    print(f"  nets (routable signal): {len(problem.nets)}  "
          f"[routed {len(meta['routed_nets'])} / residual "
          f"{len(meta['residual_nets'])}]")
    print(f"  net topology: {len(problem.nets) - len(cross)} INTERNAL "
          f"(route within CH1, escape-governed) / {len(cross)} CROSSING "
          f"(traverse a CH1 I/O door): {cross}")
    print(f"  residual (24/30 wall) nets: {meta['residual_nets']}")
    print(f"  doors: {len(problem.doors)}  via_slots: {len(problem.via_slots)}")
    print("  PER-IC-SIDE ESCAPE MODEL (the binding supply; REMAINING after the "
          "24/30 routed nets):")
    for sm in meta["side_models"]:
        print(f"    {sm.ic_side}: pins={sm.n_pins} span={sm.span_mm}mm | "
              f"std_total={sm.std_total} routed_consumed={sm.routed_consumed} "
              f"=> std_REMAINING={sm.std_slots} "
              f"+HDIuv_FIn1(PLANE-DROPPED)={sm.hdi_slots} "
              f"+HDIblind_FIn2(OQ-020 signal)={sm.blind_f_in2_supply} "
              f"=> layer-aware-supply={sm.std_slots + sm.blind_f_in2_supply} | "
              f"residual_demand={sm.demand} {list(sm.residual_nets)} | "
              f"blind-eligible={list(sm.blind_f_in2_nets)}")
    print()
    print("  MODELLING ASSUMPTIONS:")
    for i, asm in enumerate(MODELLING_ASSUMPTIONS, 1):
        print(f"    {i}. {asm}")


def _print_escape_headline(a, meta):
    print("-" * 72)
    print("ESCAPE-LEDGER HEADLINE (the binding answer to 'past 24/30?'):")
    esc = a.get("escape_ledger", {})
    if not esc:
        print("  (no via_slots — escape model empty; verdict is door-governed)")
        return
    # worst side governs (phase_a picks it the same way)
    worst = max(esc.values(),
                key=lambda L: (L["overflow_std"], L["overflow_hdi"]))
    for sid, L in sorted(esc.items()):
        flag = " <== WORST (governs verdict)" if L is worst else ""
        print(f"  {sid}: demand={L['demand']} std={L['supply_std']} "
              f"(overflow_std={L['overflow_std']}) +HDI={L['supply_hdi']} "
              f"=> total={L['supply_std'] + L['supply_hdi']} "
              f"(overflow_hdi={L['overflow_hdi']}){flag}")
    print(f"  => VERDICT: {a['verdict']}")
    print(f"     {a['rationale']}")
    print("-" * 72)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Engine Step 8a — real-board driver + Phase A verdict "
                    "(READ-ONLY)")
    ap.add_argument("--board", help="path to .kicad_pcb (read-only)")
    ap.add_argument("--subsystem", default="CH1", help="subsystem (default CH1)")
    ap.add_argument("--verdict", action="store_true",
                    help="run Phase A verdict (+ Phase B if routable) and print "
                         "the ledger")
    ap.add_argument("--assumptions", action="store_true",
                    help="print the modelling assumptions and exit")
    args = ap.parse_args(argv)

    if args.assumptions:
        for i, asm in enumerate(MODELLING_ASSUMPTIONS, 1):
            print(f"{i}. {asm}")
        return 0

    if not args.board:
        ap.error("--board is required (unless --assumptions)")
    if not os.path.exists(args.board):
        ap.error(f"board not found: {args.board}")

    # The verdict (Phase A + Phase B-if-routable) is the only / default action.
    verdict(args.board, args.subsystem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
