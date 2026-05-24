#!/usr/bin/env python3
"""place_subsystem_ch1.py — Phase 4-v2 Step 2 CH1 clean-slate.

Starts from empty PCB (mount holes + fiducials only). Adds back ONLY CH1
components, placed in CH1 zone (0,50,35,82) with proper spacing.

CH1 components determined by net pattern: any fp with a pad on _CH1 net.
Plus hardcoded refs (J18, J19, etc.) that are CH1-specific by ref number.

Strategy:
1. Load full PCB (donor) — has all 573 components
2. Identify CH1 subset (~80 components)
3. Load empty PCB (recipient — 10 fps mount + fid)
4. Move CH1 fps from donor to recipient at new clean-slate positions
5. Save recipient as pcbai_fpv4in1.kicad_pcb (replacing)
"""
import pcbnew
import re
import math

FULL = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
EMPTY = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1_empty.kicad_pcb"
OUT = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

CH1_ZONE = (0, 50, 35, 82)

# Anchor positions for CH1 ICs + FETs (proper spacing)
ANCHORS = {
    'Q5':  (12.0, 56.0), 'Q6':  (30.0, 56.0),
    'Q7':  (12.0, 68.0), 'Q8':  (30.0, 68.0),
    'Q9':  (12.0, 80.0), 'Q10': (30.0, 80.0),
    'J18': (22.0, 78.0),  # MCU QFN-32
    'J19': (22.0, 62.0),  # DRV HVQFN-24
    'J20': (5.0, 62.0),   # INA SOT-363
    'J21': (5.0, 70.0),
    'J22': (5.0, 78.0),
    'U3':  (8.0, 78.0),   # LM393 SOIC-8 (14mm from J18)
    'U4':  (8.0, 70.0),
    'TP19': (5.0, 56.0), 'TP20': (5.0, 68.0), 'TP21': (5.0, 80.0),
}


def get_ch1_refs(donor):
    refs = set()
    for fp in donor.GetFootprints():
        ref = fp.GetReference()
        # By net pattern
        for pad in fp.Pads():
            n = pad.GetNetname() or ''
            if re.search(r'_CH1$', n):
                refs.add(ref); break
        # By hardcoded anchor
        if ref in ANCHORS:
            refs.add(ref)
    return refs


def main():
    donor = pcbnew.LoadBoard(FULL)
    recipient = pcbnew.LoadBoard(EMPTY)

    ch1_refs = get_ch1_refs(donor)
    print(f"CH1 components to add: {len(ch1_refs)}")

    # Build occupied-pad set in recipient (mount holes + fiducials)
    occupied_pads = []
    for fp in recipient.GetFootprints():
        for pad in fp.Pads():
            p = pad.GetPosition()
            occupied_pads.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

    # Place anchors first
    placed_pos = {}  # ref -> (x, y)
    for ref, (x, y) in ANCHORS.items():
        if ref not in ch1_refs: continue
        placed_pos[ref] = (x, y)

    # Grid for passives — 1.5mm pitch, skip anchor pad areas
    passives = sorted(ch1_refs - set(ANCHORS.keys()))
    # Available zones (away from FET/IC pads):
    # west strip 2-7 × 52-82 (5×30 = 150 mm² minus IC pads)
    # north strip 16-34 × 73-82 (18×9, minus J18 area)
    grid = []
    for y in [73, 75, 77, 79, 81]:
        for x in range(16, 34, 2):
            grid.append((x, y))
    # west strip available between INA cluster + FETs
    for y in range(52, 82, 2):
        for x in [2, 3.5, 18, 19]:
            grid.append((x, y))
    # below central
    for y in [60, 64, 66, 70, 72]:
        for x in [17, 19, 21, 23, 25, 27]:
            grid.append((x, y))

    # Get anchor pad keepouts
    keepouts = []
    for ref, (x, y) in placed_pos.items():
        # Approximate IC pad zone: ±3mm around center
        keepouts.append((x, y, 3.5))

    used_grid = set()
    relocated = 0
    for ref in passives:
        for (gx, gy) in grid:
            if (gx, gy) in used_grid: continue
            # In zone?
            if not (CH1_ZONE[0] <= gx <= CH1_ZONE[2] and CH1_ZONE[1] <= gy <= CH1_ZONE[3]):
                continue
            # Avoid keepouts
            if any(math.hypot(gx-kx, gy-ky) < kr for kx, ky, kr in keepouts):
                continue
            placed_pos[ref] = (gx, gy)
            used_grid.add((gx, gy))
            relocated += 1
            break

    print(f"Anchors: {len(set(ANCHORS.keys()) & ch1_refs)}, Passives placed: {relocated}, Total: {len(placed_pos)}/{len(ch1_refs)}")

    # Now copy CH1 footprints from donor to recipient
    for ref in ch1_refs:
        donor_fp = donor.FindFootprintByReference(ref)
        if donor_fp is None: continue
        if ref not in placed_pos:
            # Skip if no position
            continue
        new_pos = placed_pos[ref]
        # Clone via duplicate
        new_fp = donor_fp.Duplicate()
        new_fp.SetPosition(pcbnew.VECTOR2I(int(new_pos[0]*1e6), int(new_pos[1]*1e6)))
        recipient.Add(new_fp)

    recipient.Save(OUT)
    print(f"Saved CH1-only board to {OUT}")
    print(f"Total components: {len(list(recipient.GetFootprints()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
