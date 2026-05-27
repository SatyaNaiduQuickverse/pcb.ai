#!/usr/bin/env python3
"""
audit_hdi_via_in_pad.py — HDI via-in-pad whitelist enforcement (G_HDI_VIA_IN_PAD).

Master 2026-05-27 R26 HDI dispatch (CH1 STEP-6 unblock).

Verifies that ONLY whitelisted footprints (J18, J19) have via-in-pad
placements. This audit preserves the cost envelope: Sai cost-cleared
+$2-3/board for HDI Class 2 (epoxy fill + plate-over) on J18 + J19 only;
any via-in-pad on other components would silently expand the HDI scope
and inflate cost.

Definition of "HDI via-in-pad" (what this audit checks):
  A via whose:
    - center falls within an SMD pad's bounding rectangle (+ 0.05mm tol)
    AND
    - drill diameter is ≤ HDI_DRILL_MAX_MM (0.15mm) OR via_type is MICROVIA
  is an HDI via-in-pad. Standard 0.3mm-drill vias that incidentally land
  on a pad (router convenience) are NOT HDI — they don't require the
  +$2-3/board epoxy-fill+plate-over fab process and are out of scope.

Whitelist:
  J18 (AT32F421 QFN-32, 0.5mm pitch) — south-edge BEMF + PWM escape
  J19 (DRV8300 QFN-24, 0.5mm pitch) — driver fan-out escape

PASS criteria:
  - Every HDI via (drill ≤ 0.15mm OR type MICROVIA) lies inside a J18 or
    J19 SMD pad bbox.

FAIL criteria:
  - Any HDI via outside J18/J19 SMD pads (cost scope creep).
  - HDI via inside a non-whitelist footprint's SMD pad.
  - v7 (worker R22 #4 on v6): any via tagged VIATYPE_MICROVIA whose layer
    span is NOT adjacent (F.Cu↔In1.Cu or B.Cu↔In8.Cu). JLC HDI Class 2
    spec restricts microvia to single laser-drill adjacent-layer pairs;
    longer spans must emit as through-vias (no MICROVIA tag).

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

# Via-center-inside-pad tolerance — accommodates grid-snap rounding from
# router emission (router places via at pad center but pcbnew internal
# unit conversion may shift by ≤1µm).
TOLERANCE_MM = 0.05

# HDI via geometry thresholds — vias with drill ≤ HDI_DRILL_MAX are
# considered HDI microvias. Standard board vias have drill ≥ 0.20mm.
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
    pass_count = 0  # vias correctly in J18/J19 pads

    # v7: adjacent-layer pairs allowed for VIATYPE_MICROVIA tag (JLC HDI
    # Class 2 single laser-drill spec). Anything longer is a through-via
    # masquerading as microvia and must be re-emitted as VIATYPE_THROUGH.
    ADJACENT_MICROVIA_PAIRS = {
        (pcbnew.F_Cu, pcbnew.In1_Cu),
        (pcbnew.In1_Cu, pcbnew.F_Cu),
        (pcbnew.B_Cu, pcbnew.In8_Cu),
        (pcbnew.In8_Cu, pcbnew.B_Cu),
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
        is_hdi = (drill_mm <= HDI_DRILL_MAX_MM) or is_microvia_tag

        # v7: span check — any VIATYPE_MICROVIA must be adjacent-layer.
        if is_microvia_tag:
            try:
                L_top = t.TopLayer()
                L_bot = t.BottomLayer()
                if (L_top, L_bot) not in ADJACENT_MICROVIA_PAIRS:
                    fails_microvia_span.append(
                        (vx, vy, L_top, L_bot, drill_mm)
                    )
            except Exception:
                # Can't read layer pair — conservatively flag as non-adjacent
                fails_microvia_span.append(
                    (vx, vy, -1, -1, drill_mm)
                )

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

    total_fails = (len(fails_in_pad_nonwhitelist)
                   + len(fails_hdi_outside_whitelist)
                   + len(fails_microvia_span))
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
