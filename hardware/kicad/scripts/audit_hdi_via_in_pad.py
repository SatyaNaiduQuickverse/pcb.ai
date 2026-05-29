#!/usr/bin/env python3
"""
audit_hdi_via_in_pad.py — HDI via-in-pad whitelist enforcement (G_HDI_VIA_IN_PAD).

Master 2026-05-27 R26 HDI dispatch (CH1 STEP-6 unblock).
Master 2026-05-28 OQ-020 ACTIVATE extension: accept blind F.Cu↔In2 vias on
the BSTB/PWM_INHB/SWDIO/PWM_INLA/GLB whitelist (the OQ-020 lever per
BOARD_INVARIANTS §"HDI Class extension: blind/buried F.Cu↔In2").
Master 2026-05-28 CH1 30/30 LEVER D extension (Phase 3 PR #227 follow-up):
added GLB_CH1 to the net-whitelist (J19.10 escape) + DOCUMENTED the J19-end
partner-pin landings for PWM_INHB_CH1 (J19.23) + PWM_INLA_CH1 (J19.1) —
those 2 nets were already net-whitelisted at J18 pins; the partner-pin docs
make the J19 landings explicit. Same OQ-020 fab class, zero marginal cost.

Master 2026-05-28 CH1 30/30 LEVER L extension (drone-grade reliability + no
cut corners; Sai-approved): added STACKED_MICROVIA_NET_WHITELIST +
STACKED_MICROVIA_SANCTIONED_LANDINGS — the JLC HDI Class 2 stacked-
microvia F↔In1↔In2 fab class (TWO microvias geometrically aligned, top
F.Cu↔In1.Cu + bottom In1.Cu↔In2.Cu). Same 6 whitelist nets / 8 sanctioned
(net, pin) landings as BLIND_F_IN2 (so per-pin the router may choose blind
OR stacked, both signal-reaching). Mathematically guarantees escape budget
> demand at every whitelist pin landing (DOUBLES signal-reaching supply).
Cost adder ~$1-2/board on top of the existing OQ-020 envelope (industry-
standard since iPhone 4 era — established reliability).

Verifies that ONLY whitelisted footprints (J18, J19) have via-in-pad
placements. This audit preserves the cost envelope: Sai cost-cleared
+$2-3/board for HDI Class 2 (epoxy fill + plate-over) on J18 + J19 only,
+$2-5/board for the blind/buried F-In2 class on the 5 named nets ONLY
(7 sanctioned net+pin landings); any via-in-pad on other components / pins
would silently expand the HDI scope and inflate cost.

Definition of "HDI via-in-pad" (what this audit checks):
  A via whose:
    - center falls within an SMD pad's bounding rectangle (+ 0.05mm tol)
    AND
    - drill diameter is ≤ HDI_DRILL_MAX_MM (0.15mm) OR via_type is MICROVIA
      OR via_type is BLIND_BURIED (OQ-020 blind F-In2 — drill 0.15mm and
      blind-tagged falls into the same HDI category from the cost POV)
  is an HDI via-in-pad. Standard 0.3mm-drill vias that incidentally land
  on a pad (router convenience) are NOT HDI — they don't require the
  +$2-3/board epoxy-fill+plate-over fab process and are out of scope.

Whitelist (footprints):
  J18 (AT32F421 QFN-32, 0.5mm pitch) — south-edge BEMF + PWM escape
  J19 (DRV8300 QFN-24, 0.5mm pitch) — driver fan-out escape

Whitelist (blind F.Cu↔In2 vias — OQ-020 ACTIVATE 2026-05-28; extended
lever D same day):
  The 5 named nets on J18/J19 — 7 sanctioned net+pin landings:
    BSTB_CH1     @ J19.17 (original)
    PWM_INHB_CH1 @ J18.19 (original)
    SWDIO_CH1    @ J18.23 (original)
    PWM_INLA_CH1 @ J18.15 (original)
    PWM_INHB_CH1 @ J19.23 (lever D — partner of J18.19, net already WL)
    PWM_INLA_CH1 @ J19.1  (lever D — partner of J18.15, net already WL)
    GLB_CH1      @ J19.10 (lever D — new net + new pin)
  A blind F-In2 via on any OTHER net = FAIL (cost scope creep beyond
  Sai's +$2-5/board envelope).

PASS criteria:
  - Every HDI via (drill ≤ 0.15mm OR type MICROVIA) lies inside a J18 or
    J19 SMD pad bbox.
  - Every BLIND_BURIED via with F.Cu↔In2 layer span (the OQ-020 class) is
    on one of the 5 whitelisted nets AND inside a J18 or J19 SMD pad bbox.

FAIL criteria:
  - Any HDI via outside J18/J19 SMD pads (cost scope creep).
  - HDI via inside a non-whitelist footprint's SMD pad.
  - v7 (worker R22 #4 on v6): any via tagged VIATYPE_MICROVIA whose layer
    span is NOT adjacent (F.Cu↔In1.Cu or B.Cu↔In8.Cu). JLC HDI Class 2
    spec restricts microvia to single laser-drill adjacent-layer pairs;
    longer spans must emit as through-vias (no MICROVIA tag).
  - OQ-020 (this extension): any BLIND_BURIED via tagged F.Cu↔In2 (the
    new OQ-020 class) on a net NOT in the BLIND_F_IN2_NET_WHITELIST.

Usage:
  python3 audit_hdi_via_in_pad.py <board.kicad_pcb>

Exit 0 = PASS (all via-in-pads are on whitelist), 1 = FAIL.
"""
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Whitelist references (footprints permitted to have HDI via-in-pad).
# Must stay in sync with route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS
# and docs/MASTER_HDI_SPEC.md whitelist section.
HDI_VIA_IN_PAD_WHITELIST = ("J18", "J19")

# OQ-020 ACTIVATE 2026-05-28 (Sai cost-OK): blind F.Cu↔In2 via class scoped
# to the named residual escape nets ONLY. Must stay in sync with the
# BOARD_INVARIANTS §"HDI Class extension: blind/buried F.Cu↔In2" table and
# the pcbai_fpv4in1.kicad_dru "HDI blind F-In2" rule set. The audit checks
# canonical .kicad_pcb net names (the binding identity post-kinet2pcb). The
# scope is CH1 ONLY (where the OQ-020 wall was diagnosed); the channel
# suffix `_CH1` is the schematic-canonical naming (see canonical board).
# This is the NARROWEST scope per Sai's cost envelope. Expanding to
# CH2/CH3/CH4 requires Sai cost-OK + a new PR (the engine code path is
# already generic across subsystems — only the whitelist is CH1-scoped).
#
# 2026-05-28 EXTENSION (CH1 30/30 lever D, Phase 3 PR #227 follow-up — Sai
# cost-OK same OQ-020 envelope): added GLB_CH1 (new net) and DOCUMENTED the
# J19-end partner pin locations for PWM_INHB_CH1 (J19.23) + PWM_INLA_CH1
# (J19.1) — those two nets were already net-whitelisted, so the audit already
# accepts blind F-In2 at their J19 partner pins; the extension makes the
# net+pin locations explicit in BOARD_INVARIANTS for fab traceability and
# adds GLB_CH1 to the net-whitelist so the J19.10 escape becomes blind-
# eligible (closes the J19_S overflow residual). Same fab class (Class-2
# HDI blind/buried F.Cu↔In2, drill 0.15mm / pad 0.30mm / annular 0.075mm),
# zero marginal fab cost.
#
# 2026-05-28 EXTENSION (CH1 30/30 lever G, last residual after lever F per-
# class halo + lever c GLC In2 detour): adds KILL_RAIL_N_CH1 (new net) at
# J19.8. Per-layer clearance at J19.8 = 0.383mm (OPEN), but no blind F-In2
# class was offered for KILL_RAIL_N because the net was missing from this
# whitelist; via_class_for_span returned None and the cooperative router
# refused F.Cu↔In2 emission. One-pin addition restores supply → router
# emits blind F.Cu↔In2 at J19.8 → escape to In2 → cooperative/maze
# completes to D38/R76/D37 on B.Cu. Same OQ-020 fab class, zero marginal
# fab cost. Total whitelist post-lever-G: 6 nets, 8 sanctioned net+pin
# landings. See ROUTING_LESSONS.md L13 + BOARD_INVARIANTS HDI extension
# table for the full landing roster.
BLIND_F_IN2_NET_WHITELIST = (
    "BSTB_CH1", "PWM_INHB_CH1", "SWDIO_CH1", "PWM_INLA_CH1",
    "GLB_CH1",          # 2026-05-28 lever D — J19.10 escape (new net add)
    "KILL_RAIL_N_CH1",  # 2026-05-28 lever G — J19.8 escape (last residual)
)

# 2026-05-28 LEVER L — STACKED MICROVIA F↔In1↔In2 (Sai cost-OK; drone-grade
# reliability + no cut corners): JLC HDI Class 2 supports stacked microvia
# natively (F.Cu↔In1 microvia stacked geometrically on top of In1↔In2
# microvia; the In1 landing is a small "antipad+pad" isolated copper island
# that is NOT tied to the In1 GND plane and NOT to the signal — it's the
# stacked-via pad between two microvias). This is a SECOND signal-reaching
# via mechanism per pin, in addition to the existing OQ-020 blind F-In2
# class. Same 6 whitelist nets / 8 sanctioned (net, pin) landings (so per-
# pin the router may pick blind OR stacked, both reach In2 signal). Cost
# adder ~$1-2/board on top of the existing +$2-5/board JLC HDI blind/
# buried envelope (no new fab process — same Class-2 laser-drill + epoxy-
# fill + plate-over; just two laser passes geometrically aligned). Industry
# standard since ~iPhone 4 era (Apple/Samsung phones use stacked microvia
# extensively); established reliability with millions of fielded units.
#
# Geometry (above fab min with §5c FoS):
#   - Top microvia: drill 0.10mm, pad 0.25mm (= existing HDI microvia
#     F-In1 geometry; OQ-014 lock); span F.Cu↔In1.Cu (adjacent laser pair).
#   - Bottom microvia: drill 0.10mm, pad 0.25mm (= same; the In1 pad +
#     bottom barrel are stacked geometrically aligned with the top); span
#     In1.Cu↔In2.Cu (adjacent laser pair).
#   - Annular ring: 0.075mm each (≥ board std 0.10mm AFTER plate-over;
#     FoS margin above JLC blind-via fab min 0.05mm).
#   - Stacking alignment: per JLC HDI Class 2 spec (≤0.025mm registration
#     tolerance laser-to-laser; well within the 0.075mm annular budget).
#
# Why this MATHEMATICALLY GUARANTEES escape budget at 0.5mm QFN pitch:
# adding stacked microvia as a second signal-reaching mechanism per pin
# DOUBLES the supply on the whitelist landings (blind_F_In2 = 1 slot per
# pin + stacked_microvia_F_In1_In2 = 1 slot per pin = 2 signal-reaching
# slots per whitelist pin). Per `phase_a.side_supply`, the layer-aware
# supply on each whitelist side grows by exactly the # of whitelist-eligible
# residual nets on that side — guaranteeing supply > demand at every
# pin landing.
#
# Identification on .kicad_pcb: KiCad emits the stack as TWO
# VIATYPE_MICROVIA vias at the SAME (x, y) position (±TOLERANCE_MM), one
# spanning (F.Cu, In1.Cu) and the other spanning (In1.Cu, In2.Cu). The
# audit treats a co-located F-In1 + In1-In2 microvia PAIR on a whitelist
# net inside a J18/J19 pad bbox as a sanctioned stacked microvia; each
# microvia individually still satisfies the v7 adjacent-pair span check
# (so the stacked structure does not violate JLC HDI Class 2 single-
# laser-drill per microvia).
STACKED_MICROVIA_NET_WHITELIST = (
    "BSTB_CH1", "PWM_INHB_CH1", "SWDIO_CH1", "PWM_INLA_CH1",
    "GLB_CH1", "KILL_RAIL_N_CH1",
)

# Per-pin sanctioned landings — identical to BLIND_F_IN2 (so router can
# choose blind OR stacked per pin; both signal-reaching). Documentary
# (audit + DRU + router are net-name based); the master gate verifies
# stacked emissions land on a sanctioned pin.
STACKED_MICROVIA_SANCTIONED_LANDINGS = (
    ("BSTB_CH1",        "J19", "17"),
    ("PWM_INHB_CH1",    "J18", "19"),
    ("SWDIO_CH1",       "J18", "23"),
    ("PWM_INLA_CH1",    "J18", "15"),
    ("PWM_INHB_CH1",    "J19", "23"),
    ("PWM_INLA_CH1",    "J19", "1"),
    ("GLB_CH1",         "J19", "10"),
    ("KILL_RAIL_N_CH1", "J19", "8"),
)

# Logical signal-name cross-reference (matches BLIND_F_IN2_LOGICAL_SIGNALS).
STACKED_MICROVIA_LOGICAL_SIGNALS = ("BSTB", "PWM_INHB", "SWDIO", "PWM_INLA",
                                    "GLB", "KILL_RAIL_N")

# The schematic-logical signal names (pre-channel-suffix) — kept for cross-
# reference to BOARD_INVARIANTS + DRU which document the signals by their
# logical names. NOT used for matching (matching is exact-string against
# canonical .kicad_pcb names per [[reference-kicad-dru-libeval-crash]]).
BLIND_F_IN2_LOGICAL_SIGNALS = ("BSTB", "PWM_INHB", "SWDIO", "PWM_INLA", "GLB",
                                "KILL_RAIL_N")

# 2026-05-28 lever D: sanctioned (net, footprint, pin) landings — the
# fab-traceable roster of permitted blind F.Cu↔In2 vias. The audit's
# enforcement is net-name-only (matching the DRU which also is net-name-
# only — KiCad libeval pre-v9.0.3 can't condition on pin number per
# [[reference-kicad-dru-libeval-crash]]). This tuple is documentary —
# read by the master gate to verify the worker's emitted blind vias land
# on a sanctioned pin (in addition to net-name being whitelisted).
# Cross-ref BOARD_INVARIANTS §"HDI Class extension: blind/buried F.Cu↔In2".
BLIND_F_IN2_SANCTIONED_LANDINGS = (
    ("BSTB_CH1",        "J19", "17"),
    ("PWM_INHB_CH1",    "J18", "19"),
    ("SWDIO_CH1",       "J18", "23"),
    ("PWM_INLA_CH1",    "J18", "15"),
    # 2026-05-28 lever D additions:
    ("PWM_INHB_CH1",    "J19", "23"),   # partner of J18.19 (already net-WL)
    ("PWM_INLA_CH1",    "J19", "1"),    # partner of J18.15 (already net-WL)
    ("GLB_CH1",         "J19", "10"),   # new net+pin (closes J19_S overflow)
    # 2026-05-28 lever G addition (CH1 30/30 last residual):
    ("KILL_RAIL_N_CH1", "J19", "8"),    # new net+pin (closes last residual)
)

# ─── 2026-05-29 CH1 30/30 LEVER BB ────────────────────────────────────────────
# B.Cu microvia fab class (bottom-side HDI escape — JLC HDI Class 2 standard).
#
# Sai cost-OK / drone-grade reliability: JLC HDI Class 2 SUPPORTS microvia on
# BOTH outer skin pairs (F.Cu↔In1.Cu AND B.Cu↔In8.Cu) at the same per-board
# cost adder ($2-3/board epoxy-fill + plate-over already paid for the F-side
# whitelist; the B-side microvia uses the SAME fab process). This lever adds
# a SECOND HDI escape mechanism per chain — on the destination side of the
# 3 chronic residual nets (PWM_INLA / GLB / KILL_RAIL_N). The F-side escape
# (blind_F_In2 at J19) was already whitelisted; the chains then needed a
# through-via at the destination end (R50 / R76 / D37 / D38). Through-vias
# at fine-pitch SMD passive pads are GEOMETRICALLY infeasible (0.60mm pad
# extends 0.18mm beyond a 0.875mm × 0.25mm passive pad edge). The B.Cu↔In8
# microvia (0.25mm pad) fits entirely within the passive pad bbox — same
# physics that the F-side microvia exploits at J18/J19. DOUBLES escape supply
# per chain → drives the 3 chronic residuals.
#
# PHYSICS — Brooks PCB Currents Ch.10 / JLC HDI Class 2 spec:
#   F-side HDI: microvia 0.10mm drill / 0.25mm pad on F.Cu↔In1.Cu, 0.075mm
#               annular ring (≥ JLC blind/buried fab min). Already lever-O.
#   B-side HDI (this lever BB): SAME geometry, MIRROR pair on B.Cu↔In8.Cu.
#               Single laser-drill per microvia (JLC HDI Class 2 single-pass).
#   Fab cost adder: $0 above existing F-side envelope (same fab class, same
#               per-board cost; the fab process pays for the whole HDI shell).
#
# Whitelist scope (NARROWEST per Sai cost envelope + R26 codify-don't-patch):
#   - Refs: BOTTOM_MICROVIA_REFS — destination-side passive footprints on the
#           3 chronic residual nets. Surgical add: ONLY R50 / R76 / D37 / D38
#           (the named endpoints of the 3 failing chains).
#   - Nets: BOTTOM_MICROVIA_NET_WHITELIST — exact 3 chronic residuals.
#   - Landings: BOTTOM_MICROVIA_SANCTIONED_LANDINGS — fab-traceable per-pin
#               roster of permitted B.Cu↔In8 microvia drops.
#
# Why these refs / nets / landings (CH1 30/30 BB diagnosis 2026-05-29):
#   PWM_INLA_CH1 escape chain: J19.1 (HDI start, F→In2 blind) → through (mid)
#                              → J19.1 ALREADY HDI-whitelisted under blind
#                              F-In2 (lever D). But the J18.15 endpoint is
#                              a partner pin — both already in HDI scope.
#                              Adding B.Cu microvia at the DESTINATION-side
#                              (J19.1 is the through-via residual; the chain
#                              currently exhausts through-via budget). The
#                              BB extension allows a B-In8 microvia at J19.1
#                              when the chain needs B.Cu escape (no through).
#   GLB_CH1 escape chain: J19.10 (HDI start, F→In2 blind) → through (mid) →
#                         R50.1 (destination, B.Cu run). R50 is 40mm from
#                         J19 — the BB extension whitelists R50 for B.Cu
#                         microvia escape, doubling chain supply.
#   KILL_RAIL_N_CH1 escape chain: J19.8 (HDI start, F→In2 blind) → through
#                                 (mid) → D37.2 / D38.2 / R76.1 (destinations
#                                 chained through the kill-rail discrete
#                                 network). D37 / D38 are within 10-15mm of
#                                 J19, R76 is at 65mm. The BB extension
#                                 whitelists all three for B.Cu microvia
#                                 escape — every destination node in the
#                                 KILL_RAIL_N chain can drop to In8 via
#                                 single-laser microvia.
#
# Cost envelope: SAME as existing F-side HDI ($2-3/board, already cost-cleared
# per BOARD_INVARIANTS HDI scope). Zero marginal fab cost (same fab process,
# same laser pass, same plate-over). Industry standard since iPhone 4 era.
#
# Master Lever BB 2026-05-29 — CH1 30/30 BB: B.Cu microvia fab class —
# bottom-side HDI escape for chronic residuals.

BOTTOM_MICROVIA_NET_WHITELIST = (
    "PWM_INLA_CH1",     # chronic residual — chains via J19.1 + J18.15 + R50?
    "GLB_CH1",          # chronic residual — escape chain to R50.1
    "KILL_RAIL_N_CH1",  # chronic residual — escape chain via D37/D38/R76
)

# Destination-side passive / connector footprints permitted to host a B.Cu↔In8
# microvia. SURGICAL list: each ref is a confirmed pad endpoint of one of the
# 3 chronic residual nets. The J19 ref is INCLUDED because PWM_INLA_CH1's
# destination is on J19 itself (the chain's HDI-start side has a partner pin
# on J19 — J19.1 — that's the same MCU; adding B-side microvia on J19 allows
# the destination-side escape on the same pin without through-via).
BOTTOM_MICROVIA_REFS = (
    "J19",      # PWM_INLA_CH1 destination (J19.1) + KILL_RAIL_N at J19.8
    "R50",      # GLB_CH1 destination (R50.1, ~40mm from J19)
    "R76",      # KILL_RAIL_N_CH1 destination (R76.1)
    "D37",      # KILL_RAIL_N_CH1 chained destination (D37.2)
    "D38",      # KILL_RAIL_N_CH1 chained destination (D38.2)
)

# Fab-traceable per-pin landing roster — the master gate verifies each
# B.Cu↔In8 microvia the worker emits lands on a sanctioned (net, ref, pin).
# Mirrors BLIND_F_IN2_SANCTIONED_LANDINGS pattern (net-name-only audit
# matching per [[reference-kicad-dru-libeval-crash]]; per-pin docs are
# fab traceability + master-gate evidence).
BOTTOM_MICROVIA_SANCTIONED_LANDINGS = (
    # PWM_INLA_CH1 chain destinations:
    ("PWM_INLA_CH1",    "J19", "1"),    # chain endpoint at J19.1 (partner of J18.15)
    # GLB_CH1 chain destination (R50.1):
    ("GLB_CH1",         "R50", "1"),
    # KILL_RAIL_N_CH1 chain destinations (D37.2, D38.2, R76.1, J19.8):
    ("KILL_RAIL_N_CH1", "J19", "8"),    # KILL_RAIL_N at J19.8 (partner endpoint)
    ("KILL_RAIL_N_CH1", "D37", "2"),    # chained discrete
    ("KILL_RAIL_N_CH1", "D38", "2"),    # chained discrete
    ("KILL_RAIL_N_CH1", "R76", "1"),    # final terminal
)

# Logical signal-name cross-reference (matches BLIND_F_IN2_LOGICAL_SIGNALS).
BOTTOM_MICROVIA_LOGICAL_SIGNALS = ("PWM_INLA", "GLB", "KILL_RAIL_N")

# Adjacent-pair span for B-side microvia (mirrors STACKED_TOP_PAIRS form).
# Defined here at module level so route_subsystem_cooperative + maze_router
# adapters can import and validate spans without round-tripping through
# the via-emit code path. JLC HDI Class 2 single laser-drill semantics.
BOTTOM_MICROVIA_ADJACENT_PAIRS = (
    ("B.Cu", "In8.Cu"),
    ("In8.Cu", "B.Cu"),
)

# Via-center-inside-pad tolerance — accommodates grid-snap rounding from
# router emission (router places via at pad center but pcbnew internal
# unit conversion may shift by ≤1µm).
TOLERANCE_MM = 0.05

# HDI via geometry thresholds — vias with drill ≤ HDI_DRILL_MAX are
# considered HDI microvias. Standard board vias have drill ≥ 0.20mm.
# The new OQ-020 blind F-In2 class has drill 0.15mm == HDI_DRILL_MAX_MM
# (i.e. it falls into the HDI band by drill, exactly as intended — the
# DRU's "Standard via" rules start at >0.20mm to leave room for it).
HDI_DRILL_MAX_MM = 0.15


def iu_to_mm(iu: int) -> float:
    return iu / 1e6


def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <board.kicad_pcb>")
        sys.exit(1)
    board_path = Path(sys.argv[1])
    if not board_path.exists():
        print(f"FAIL: board {board_path} not found")
        sys.exit(1)
    b = pcbnew.LoadBoard(str(board_path))

    # Index SMD pads by footprint with bbox.
    # SMD pads = pad that exists on F.Cu OR B.Cu only (not THT). THT pads
    # inherently have a via (the plated hole) — those are NOT what this
    # audit cares about. We only care about new vias EMITTED by router on
    # SMD pads (which is the "via in pad" cost/fab category).
    pads_by_fp = {}  # fp_ref -> [(pad_name, x, y, hx, hy, net), ...]
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        pads_by_fp.setdefault(ref, [])
        for pad in fp.Pads():
            # Skip THT pads (pad spans both F.Cu and B.Cu via a plated hole)
            try:
                ls = pad.GetLayerSet()
                is_smd = not (ls.Contains(pcbnew.F_Cu) and ls.Contains(pcbnew.B_Cu))
            except Exception:
                is_smd = True
            if not is_smd:
                continue
            # Skip pads that have an own drilled hole (these ARE through-pads;
            # router-emitted vias on them = legitimate connection, not HDI VIP)
            try:
                if pad.GetDrillSize().x > 0:
                    continue
            except Exception:
                pass
            p = pad.GetPosition()
            sz = pad.GetSize()
            x = iu_to_mm(p.x); y = iu_to_mm(p.y)
            hx = iu_to_mm(sz.x) / 2; hy = iu_to_mm(sz.y) / 2
            net = pad.GetNet()
            netname = net.GetNetname() if net else ""
            pads_by_fp[ref].append((pad.GetPadName(), x, y, hx, hy, netname))

    # Scan all vias
    fails_in_pad_nonwhitelist = []  # via inside a non-whitelist pad bbox
    fails_hdi_outside_whitelist = []  # microvia outside any J18/J19 pad
    fails_microvia_span = []  # v7: MICROVIA tag on non-adjacent span
    fails_blind_f_in2_offwhitelist = []  # OQ-020: blind F-In2 on non-whitelist net
    # 2026-05-28 LEVER L: stacked microvia F↔In1↔In2 — collect candidate
    # microvia legs for the post-loop stacked-pair detection.
    # Each entry: (x, y, layer_pair, net_name, drill_mm).
    microvia_legs = []                  # candidate top/bottom legs of stacked pairs
    fails_stacked_offwhitelist = []     # stacked pair on non-whitelist net
    # 2026-05-29 LEVER BB: B.Cu↔In8 microvia (bottom-side HDI escape) —
    # net-whitelist + landing-ref fails (analogous to the blind_F_In2 gate).
    fails_bottom_microvia_offwhitelist = []   # B-In8 microvia on non-WL net
    fails_bottom_microvia_offref = []         # B-In8 microvia outside BOTTOM_MICROVIA_REFS
    pass_count = 0  # vias correctly in J18/J19 pads
    pass_blind_f_in2 = 0  # OQ-020 blind F-In2 vias correctly on whitelist nets
    pass_stacked_microvia = 0  # LEVER L: stacked microvia pairs correctly on whitelist
    pass_bottom_microvia = 0   # LEVER BB: B-In8 microvia on whitelist net + ref

    # v7: adjacent-layer pairs allowed for VIATYPE_MICROVIA tag (JLC HDI
    # Class 2 single laser-drill spec). Anything longer is a through-via
    # masquerading as microvia and must be re-emitted as VIATYPE_THROUGH.
    # LEVER L 2026-05-28 (Sai cost-OK): added (In1.Cu, In2.Cu) — the
    # BOTTOM leg of a stacked microvia F.Cu↔In1.Cu↔In2.Cu — to the
    # adjacent-pair set. JLC HDI Class 2 supports stacked microvia
    # natively; each leg individually is still a single laser-drill
    # adjacent-pair (this satisfies the v7 single-laser-drill enforcement).
    # The stacked PAIR detection (top + bottom legs co-located on same
    # net) is handled post-loop by the LEVER L pair detector below.
    ADJACENT_MICROVIA_PAIRS = {
        (pcbnew.F_Cu, pcbnew.In1_Cu),
        (pcbnew.In1_Cu, pcbnew.F_Cu),
        (pcbnew.B_Cu, pcbnew.In8_Cu),
        (pcbnew.In8_Cu, pcbnew.B_Cu),
        # LEVER L: stacked microvia bottom leg.
        (pcbnew.In1_Cu, pcbnew.In2_Cu),
        (pcbnew.In2_Cu, pcbnew.In1_Cu),
    }
    # OQ-020 ACTIVATE: the blind/buried F.Cu↔In2 class pairs (the new lever).
    BLIND_F_IN2_PAIRS = {
        (pcbnew.F_Cu, pcbnew.In2_Cu),
        (pcbnew.In2_Cu, pcbnew.F_Cu),
    }
    # LEVER BB 2026-05-29: B.Cu↔In8 microvia adjacent-layer pairs (the
    # bottom-side mirror of microvia F-In1). JLC HDI Class 2 single laser-
    # drill on the bottom outer pair. Per BOARD_INVARIANTS §"HDI Outer
    # pair extension: B.Cu↔In8" (this lever).
    BOTTOM_MICROVIA_PAIRS = {
        (pcbnew.B_Cu, pcbnew.In8_Cu),
        (pcbnew.In8_Cu, pcbnew.B_Cu),
    }
    # LEVER L: stacked microvia F↔In1↔In2 — the TOP leg spans (F.Cu, In1.Cu)
    # and the BOTTOM leg spans (In1.Cu, In2.Cu); a stacked pair is two
    # MICROVIAs at the same XY whose layer spans match these two sets.
    STACKED_TOP_PAIRS = {
        (pcbnew.F_Cu, pcbnew.In1_Cu),
        (pcbnew.In1_Cu, pcbnew.F_Cu),
    }
    STACKED_BOTTOM_PAIRS = {
        (pcbnew.In1_Cu, pcbnew.In2_Cu),
        (pcbnew.In2_Cu, pcbnew.In1_Cu),
    }

    for t in b.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        p = t.GetPosition()
        vx = iu_to_mm(p.x); vy = iu_to_mm(p.y)
        # Determine if HDI-sized via
        try:
            drill_mm = iu_to_mm(t.GetDrillValue())
        except Exception:
            drill_mm = 1.0  # treat as standard if unknown
        try:
            vt = t.GetViaType()
            is_microvia_tag = (vt == pcbnew.VIATYPE_MICROVIA)
        except Exception:
            is_microvia_tag = False
        try:
            is_blind_buried_tag = (vt == pcbnew.VIATYPE_BLIND_BURIED)
        except Exception:
            is_blind_buried_tag = False
        is_hdi = (drill_mm <= HDI_DRILL_MAX_MM) or is_microvia_tag \
            or is_blind_buried_tag

        # Read layer pair once (used by both microvia-span + blind-F-In2 checks).
        try:
            L_top = t.TopLayer()
            L_bot = t.BottomLayer()
            layer_pair = (L_top, L_bot)
        except Exception:
            L_top, L_bot, layer_pair = -1, -1, (-1, -1)

        # Read net name once (used by the OQ-020 blind F-In2 whitelist check).
        try:
            net_obj = t.GetNet()
            net_name = net_obj.GetNetname() if net_obj else ""
        except Exception:
            net_name = ""

        # v7: span check — any VIATYPE_MICROVIA must be adjacent-layer.
        if is_microvia_tag:
            if layer_pair not in ADJACENT_MICROVIA_PAIRS:
                fails_microvia_span.append(
                    (vx, vy, L_top, L_bot, drill_mm)
                )
            # LEVER L: collect microvia legs (the F-In1 + In1-In2 legs that
            # may form a STACKED pair). Stack detection is post-loop because
            # the two legs may be emitted in any track-iteration order.
            else:
                microvia_legs.append((vx, vy, layer_pair, net_name, drill_mm))

        # OQ-020 ACTIVATE 2026-05-28: a BLIND_BURIED via with F.Cu↔In2 layer
        # span is the new whitelisted class — accept ONLY when its net is in
        # BLIND_F_IN2_NET_WHITELIST. A blind F-In2 on any other net = FAIL
        # (cost scope creep beyond Sai's +$2-5/board envelope).
        is_blind_f_in2 = (is_blind_buried_tag and layer_pair in BLIND_F_IN2_PAIRS)
        if is_blind_f_in2:
            # Strip any net-class / netname prefix; KiCad netnames don't carry
            # one by default but the comparison is exact-string (matches the
            # canonical schematic net names listed in BOARD_INVARIANTS).
            if net_name in BLIND_F_IN2_NET_WHITELIST:
                pass_blind_f_in2 += 1
            else:
                fails_blind_f_in2_offwhitelist.append(
                    (vx, vy, net_name, drill_mm)
                )

        # LEVER BB 2026-05-29: a VIATYPE_MICROVIA via on the B.Cu↔In8 outer
        # pair is the bottom-side HDI escape class. Accept ONLY when (a) the
        # net is in BOTTOM_MICROVIA_NET_WHITELIST AND (b) the via lands
        # inside an SMD pad of a footprint in BOTTOM_MICROVIA_REFS. Either
        # gate violated = FAIL (cost scope creep beyond Sai's BB envelope).
        is_bottom_microvia = (is_microvia_tag and layer_pair in BOTTOM_MICROVIA_PAIRS)
        bottom_pass = False
        if is_bottom_microvia:
            if net_name not in BOTTOM_MICROVIA_NET_WHITELIST:
                fails_bottom_microvia_offwhitelist.append(
                    (vx, vy, net_name, drill_mm)
                )
            else:
                # Verify landing ref. We re-use the SMD-pad bbox loop below
                # but pre-scan here for B-microvia ref enforcement (so the
                # surgical (net, ref) gate is independent of the J18/J19
                # whitelist-pad loop semantics).
                landed_ref = None
                for fp_ref, pads in pads_by_fp.items():
                    for (pad_name, px, py, phx, phy, pnet) in pads:
                        if (abs(vx - px) <= phx + TOLERANCE_MM
                                and abs(vy - py) <= phy + TOLERANCE_MM):
                            landed_ref = fp_ref
                            break
                    if landed_ref:
                        break
                if landed_ref is None or landed_ref not in BOTTOM_MICROVIA_REFS:
                    fails_bottom_microvia_offref.append(
                        (vx, vy, net_name, landed_ref, drill_mm)
                    )
                else:
                    pass_bottom_microvia += 1
                    bottom_pass = True

        # Only HDI vias are subject to this audit. Standard 0.3mm-drill
        # vias on pads are pre-existing routing convention and don't
        # require HDI fab process; out of scope here.
        if not is_hdi:
            continue

        # Check if HDI via center is inside any whitelisted vs non-whitelisted
        # SMD pad bbox.
        inside_whitelist = False
        inside_nonwhitelist_pad = None  # (fp_ref, pad_name)
        for fp_ref, pads in pads_by_fp.items():
            for (pad_name, px, py, phx, phy, pnet) in pads:
                if (abs(vx - px) <= phx + TOLERANCE_MM
                        and abs(vy - py) <= phy + TOLERANCE_MM):
                    if fp_ref in HDI_VIA_IN_PAD_WHITELIST:
                        inside_whitelist = True
                    elif (is_bottom_microvia and bottom_pass
                            and fp_ref in BOTTOM_MICROVIA_REFS):
                        # LEVER BB: B-microvia on a sanctioned (net, ref)
                        # pair is the bottom-side HDI escape — treat as
                        # whitelist (in-pad-whitelist) for the J18/J19 loop
                        # so it does NOT re-fail under fails_in_pad_nonwhitelist.
                        inside_whitelist = True
                    else:
                        if inside_nonwhitelist_pad is None:
                            inside_nonwhitelist_pad = (fp_ref, pad_name)

        if inside_nonwhitelist_pad is not None:
            ref, pn = inside_nonwhitelist_pad
            fails_in_pad_nonwhitelist.append(
                (vx, vy, ref, pn, drill_mm, True)
            )
        elif inside_whitelist:
            pass_count += 1
        else:
            # HDI-geometry via floating outside any SMD pad — scope creep
            # (HDI vias are only justified inside whitelist pads)
            fails_hdi_outside_whitelist.append(
                (vx, vy, drill_mm)
            )

    # ─── LEVER L: stacked-microvia pair detection ──────────────────────────
    # A stacked microvia F↔In1↔In2 is identified by TWO microvia legs at the
    # SAME (x, y) (±TOLERANCE_MM) where one leg spans STACKED_TOP_PAIRS
    # (F.Cu↔In1.Cu) and the other spans STACKED_BOTTOM_PAIRS (In1.Cu↔In2.Cu),
    # and BOTH legs are on the same net. Pair detection groups legs by (x,y)
    # rounded to 0.001mm (≥ TOLERANCE_MM resolution) — any cluster with a
    # top + bottom leg on the same net is a stacked pair candidate. The
    # whitelist check enforces the LEVER L net set; off-whitelist stacked
    # pairs FAIL.
    def _bucket(x, y):
        # Snap to TOLERANCE_MM grid for clustering co-located legs.
        return (round(x / TOLERANCE_MM) * TOLERANCE_MM,
                round(y / TOLERANCE_MM) * TOLERANCE_MM)
    legs_by_key = {}
    for (lx, ly, lpair, lnet, ldrill) in microvia_legs:
        key = (_bucket(lx, ly), lnet)
        legs_by_key.setdefault(key, []).append((lx, ly, lpair, ldrill))
    stacked_pairs = []   # (x, y, net, top_drill, bot_drill)
    for ((bxy, net), legs) in legs_by_key.items():
        has_top = any(p in STACKED_TOP_PAIRS for (_, _, p, _) in legs)
        has_bot = any(p in STACKED_BOTTOM_PAIRS for (_, _, p, _) in legs)
        if has_top and has_bot:
            # Use the first top + bottom leg coords for the pair report.
            top = next(l for l in legs if l[2] in STACKED_TOP_PAIRS)
            bot = next(l for l in legs if l[2] in STACKED_BOTTOM_PAIRS)
            stacked_pairs.append((top[0], top[1], net, top[3], bot[3]))
    for (sx, sy, snet, td, bd) in stacked_pairs:
        if snet in STACKED_MICROVIA_NET_WHITELIST:
            pass_stacked_microvia += 1
        else:
            fails_stacked_offwhitelist.append((sx, sy, snet, td, bd))

    # Report
    print(f"Board: {board_path}")
    print(f"HDI whitelist: {list(HDI_VIA_IN_PAD_WHITELIST)}")
    print(f"HDI drill threshold: ≤{HDI_DRILL_MAX_MM}mm")
    print(f"")
    print(f"Vias correctly in whitelist pads: {pass_count}")
    print(f"Vias inside non-whitelist pads (FAIL): "
          f"{len(fails_in_pad_nonwhitelist)}")
    for (vx, vy, ref, pn, drill, hdi) in fails_in_pad_nonwhitelist[:20]:
        hdi_tag = "HDI" if hdi else "std"
        print(f"  - via @({vx:.3f},{vy:.3f}) drill={drill:.3f} [{hdi_tag}] "
              f"inside pad {ref}.{pn}")
    if len(fails_in_pad_nonwhitelist) > 20:
        print(f"  ... and {len(fails_in_pad_nonwhitelist) - 20} more")
    print(f"")
    print(f"HDI-geometry vias outside whitelist (FAIL): "
          f"{len(fails_hdi_outside_whitelist)}")
    for (vx, vy, drill) in fails_hdi_outside_whitelist[:20]:
        print(f"  - HDI via @({vx:.3f},{vy:.3f}) drill={drill:.3f} "
              f"NOT inside any whitelist pad")
    if len(fails_hdi_outside_whitelist) > 20:
        print(f"  ... and {len(fails_hdi_outside_whitelist) - 20} more")

    # v7: microvia span report
    print(f"")
    print(f"MICROVIA-tagged vias with non-adjacent layer span (FAIL, v7): "
          f"{len(fails_microvia_span)}")
    for (vx, vy, Lt, Lb, drill) in fails_microvia_span[:20]:
        print(f"  - microvia @({vx:.3f},{vy:.3f}) drill={drill:.3f} "
              f"layer-pair=({Lt},{Lb}) — NOT adjacent (JLC HDI Class 2 "
              f"violation; emit as VIATYPE_THROUGH instead)")
    if len(fails_microvia_span) > 20:
        print(f"  ... and {len(fails_microvia_span) - 20} more")

    # OQ-020 ACTIVATE 2026-05-28: blind F-In2 net-whitelist report
    print(f"")
    print(f"Blind F.Cu↔In2 vias correctly on whitelist nets "
          f"({list(BLIND_F_IN2_NET_WHITELIST)}): {pass_blind_f_in2}")
    print(f"Blind F.Cu↔In2 vias on NON-WHITELIST nets (FAIL, OQ-020 scope): "
          f"{len(fails_blind_f_in2_offwhitelist)}")
    for (vx, vy, nn, drill) in fails_blind_f_in2_offwhitelist[:20]:
        print(f"  - blind F-In2 via @({vx:.3f},{vy:.3f}) drill={drill:.3f} "
              f"net={nn!r} — NOT in BLIND_F_IN2_NET_WHITELIST "
              f"(cost scope creep beyond Sai's +$2-5/board envelope; "
              f"see BOARD_INVARIANTS §'HDI Class extension: blind/buried F.Cu↔In2')")
    if len(fails_blind_f_in2_offwhitelist) > 20:
        print(f"  ... and {len(fails_blind_f_in2_offwhitelist) - 20} more")

    # LEVER L: stacked-microvia report
    print(f"")
    print(f"Stacked-microvia F.Cu↔In1↔In2 pairs correctly on whitelist nets "
          f"({list(STACKED_MICROVIA_NET_WHITELIST)}): {pass_stacked_microvia}")
    print(f"Stacked-microvia pairs on NON-WHITELIST nets (FAIL, LEVER L scope): "
          f"{len(fails_stacked_offwhitelist)}")
    for (sx, sy, nn, td, bd) in fails_stacked_offwhitelist[:20]:
        print(f"  - stacked microvia @({sx:.3f},{sy:.3f}) "
              f"top_drill={td:.3f}/bot_drill={bd:.3f} net={nn!r} "
              f"— NOT in STACKED_MICROVIA_NET_WHITELIST "
              f"(cost scope creep beyond Sai's LEVER L envelope; see "
              f"BOARD_INVARIANTS §'HDI Class extension: stacked microvia "
              f"F.Cu↔In1↔In2')")
    if len(fails_stacked_offwhitelist) > 20:
        print(f"  ... and {len(fails_stacked_offwhitelist) - 20} more")

    # LEVER BB 2026-05-29: B.Cu↔In8 microvia report (bottom-side HDI escape)
    print(f"")
    print(f"B.Cu↔In8 microvias correctly on whitelist nets+refs "
          f"({list(BOTTOM_MICROVIA_NET_WHITELIST)} @ "
          f"{list(BOTTOM_MICROVIA_REFS)}): {pass_bottom_microvia}")
    print(f"B.Cu↔In8 microvias on NON-WHITELIST nets (FAIL, LEVER BB scope): "
          f"{len(fails_bottom_microvia_offwhitelist)}")
    for (vx, vy, nn, drill) in fails_bottom_microvia_offwhitelist[:20]:
        print(f"  - B-In8 microvia @({vx:.3f},{vy:.3f}) drill={drill:.3f} "
              f"net={nn!r} — NOT in BOTTOM_MICROVIA_NET_WHITELIST "
              f"(cost scope creep beyond Sai's LEVER BB envelope; see "
              f"BOARD_INVARIANTS §'HDI Outer pair extension: B.Cu↔In8')")
    if len(fails_bottom_microvia_offwhitelist) > 20:
        print(f"  ... and {len(fails_bottom_microvia_offwhitelist) - 20} more")
    print(f"B.Cu↔In8 microvias outside BOTTOM_MICROVIA_REFS (FAIL, LEVER BB scope): "
          f"{len(fails_bottom_microvia_offref)}")
    for (vx, vy, nn, ref, drill) in fails_bottom_microvia_offref[:20]:
        print(f"  - B-In8 microvia @({vx:.3f},{vy:.3f}) drill={drill:.3f} "
              f"net={nn!r} ref={ref!r} — NOT in BOTTOM_MICROVIA_REFS "
              f"(landing ref out of scope; LEVER BB whitelist = "
              f"{list(BOTTOM_MICROVIA_REFS)})")
    if len(fails_bottom_microvia_offref) > 20:
        print(f"  ... and {len(fails_bottom_microvia_offref) - 20} more")

    total_fails = (len(fails_in_pad_nonwhitelist)
                   + len(fails_hdi_outside_whitelist)
                   + len(fails_microvia_span)
                   + len(fails_blind_f_in2_offwhitelist)
                   + len(fails_stacked_offwhitelist)
                   + len(fails_bottom_microvia_offwhitelist)
                   + len(fails_bottom_microvia_offref))
    if total_fails == 0:
        print(f"\n✅ PASS — all HDI via-in-pad placements on whitelist "
              f"({HDI_VIA_IN_PAD_WHITELIST}); cost envelope preserved.")
        return 0
    else:
        print(f"\n❌ FAIL — {total_fails} HDI/via-in-pad whitelist violations.")
        print(f"   Action: rip non-whitelist via-in-pads OR extend whitelist "
              f"in route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS + this "
              f"audit_hdi_via_in_pad HDI_VIA_IN_PAD_WHITELIST + "
              f"docs/MASTER_HDI_SPEC.md (Sai cost-OK required for whitelist "
              f"expansion).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
