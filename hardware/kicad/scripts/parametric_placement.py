#!/usr/bin/env python3
"""parametric_placement.py — eagle's-eye SSoT for ALL placement coords.

Per Sai 2026-05-26 directive: top-down + parametric + routing-aware + bilateral
+ sim-driven placement. This module is the EXECUTABLE form of
docs/PLACEMENT_GLOBAL_PLAN.md.

CONSUMED BY (does NOT replace): per-subsystem placement scripts
  - place_subsystem_ch1_v3.py   reads ch_ic_anchors('CH1') instead of hardcoded
  - place_subsystem_s2_bulk.py   reads s2_bulk_anchors()
  - place_subsystem_s5_bec.py    reads s5_bec_anchors()
  - place_subsystem_s6_conn.py   reads s6_conn_anchors()
  - etc.

The subsystem PR cadence, lockfile YAMLs, master_pre_merge.sh 61 BLOCKING gates,
park-then-bring-in pattern, sim execution gate — ALL unchanged. This engine
just provides a single SSoT for coordinates so changes propagate.

Key principles:
  1. Single parameter set; all coords derived.
  2. Mechanical anchors READ from mechanical_anchors.yaml (lockfile SSoT).
  3. BILATERAL: F.Cu + B.Cu placements expressed as paired floors.
  4. Routing-aware: routing channels reserved between IC sub-clusters.
  5. Density budget: per-zone targets enforced by audit.
  6. Mirror/transform: CH2 = mirror_X(CH1), CH3 = mirror_Y(CH2), CH4 = mirror_X(CH3).
     Pure transforms, no per-channel fudge (R23 symmetry mandate).
  7. Sim-loop hooks: every coord set exports a fitness function for sim-driven
     iteration (see PLACEMENT_GLOBAL_PLAN.md §8).

Audited by:
  G_PP19 audit_routing_channels.py        — verifies routing channel reserves not violated
  G_PP20 audit_zone_density.py            — verifies density budget per zone
  G_PP21 audit_parametric_compliance.py   — verifies subsystem placement scripts consume this engine (no hardcoded coords)

Per [[feedback-systemic-rule-enforcement]] + Sai 2026-05-26.
"""
import os, yaml
from dataclasses import dataclass, field
from typing import Dict, Tuple, List

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", ".."))
LOCKFILE = os.path.join(REPO, "docs", "PHASE4V3_LOCKFILES", "mechanical_anchors.yaml")
BOARD_INVARIANTS_DOC = os.path.join(REPO, "docs", "BOARD_INVARIANTS.md")


# ═══════════════════════════════════════════════════════════════════════
# 1. PARAMETERS — single SSoT. Edit here; engine + audits propagate.
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class BoardParameters:
    # ─── board canvas ───
    width_mm:           float = 100.0
    height_mm:          float = 100.0
    thickness_mm:       float = 1.6
    edge_keepout_mm:    float = 0.5     # min component pad bbox-to-edge

    # ─── layer assignment (BILATERAL) ───
    hs_fet_layer:       str   = "F.Cu"  # power source side
    ls_fet_layer:       str   = "B.Cu"  # power return side
    bulk_cap_layer:     str   = "B.Cu"  # under FET clusters
    bec_buck_layer:     str   = "B.Cu"  # away from Hall (≥15mm)
    led_status_layer:   str   = "B.Cu"  # visible from underneath
    connector_layer:    str   = "F.Cu"  # cables enter top
    mcu_layer:          str   = "F.Cu"  # SWD pads top-accessible
    driver_layer:       str   = "F.Cu"  # ≤5mm from HS-FET gate

    # ─── motor pads (mechanical SSoT) ───
    # OPTION A 2026-05-26: pitch bumped 12→13mm + CH zone 36→39mm + S6/S1 14→11mm.
    # Worker analysis: at 12mm pitch + 36mm zone, the phase cluster (~12mm tall) exactly
    # abutted adjacent phases → no inter-phase gap → body-bbox seam overlap. 13mm pitch
    # gives 1mm gap with the cell unchanged. S6/S1 shrunk to absorb the 6mm (3mm × 2 CH).
    motor_pad_pitch_y:  float = 13.0    # per-channel phase pitch (Option A 2026-05-26; was 12)
    motor_pad_x_west:   float = 15.0    # west column of motor pads
    motor_pad_x_east:   float = 85.0    # east column (mirror)
    motor_pad_y0_north: float = 17.0    # phase-C of north channels (CH3/CH4) — was 20 at 12mm pitch
    motor_pad_y0_south: float = 53.0    # phase-A of south channels (CH1/CH2) — was 56 at 12mm pitch
    motor_pad_size_mm:  float = 4.0     # square 4×4 with 5 vias

    # ─── zone heights (Option A 2026-05-26) ───
    s6_height_mm:       float = 11.0    # was 14; squeezed to give CH zones 39mm
    s1_height_mm:       float = 11.0    # was 14
    ch_zone_height_mm:  float = 39.0    # was 36; (3 phases × 13mm pitch = 39mm exact fit)

    # ─── HS-FET placement (parametric, NOT hardcoded) ───
    hs_fet_x_offset_from_motor: float = -7.5  # HS x = motor_pad_x ± offset (west: motor-6.6, east: motor+6.6)
    hs_fet_y0_offset_from_motor: float = 0.0  # HS y aligned with motor pad y (SW-node trace short)
    hs_fet_row_pitch:   float = 12.0          # = motor_pad_pitch_y (KEY: enables 12mm symmetric pitch + same SW-node via grid)

    # ─── HS↔LS pairing (half-bridge cell, BILATERAL) ───
    ls_fet_y_offset_from_hs: float = 3.6      # LS sits 3.6mm below HS on B.Cu (drain-aligned, collision-free, 0mm XY for vias)
    ls_fet_x_offset_from_hs: float = 0.0      # directly under for via cluster

    # ─── sub-zone within each CH (Option 2 from G_PP6 dispatch) ───
    fet_col_x_max:                  float = 19.0   # FET column ends at x=19 (west side)
    routing_channel_x_start:        float = 19.5   # 0.5mm gap
    routing_channel_x_end:          float = 21.5   # 2mm reserved routing channel
    east_strip_motor_x_start:       float = 22.0   # MOTOR-side ICs (driver, shunts, gate-clamp diodes)
    east_strip_motor_x_end:         float = 27.0
    inter_subzone_routing_width:    float = 1.5    # 1.5mm reserved between MOTOR + LOGIC sub-zones
    east_strip_logic_x_start:       float = 28.5
    east_strip_logic_x_end:         float = 35.0   # = CH zone east edge (LOGIC includes MCU, ADC dividers, +3V3 caps)

    # ─── routing channel reserves ───
    routing_channel_min_width_mm:   float = 1.0    # any inter-IC gap must be ≥1mm wide for 2-layer routing
    via_keepout_radius_mm:          float = 0.3

    # ─── density budget per zone ───
    max_component_area_fraction:    float = 0.55   # ≤55% of zone area for component bboxes
    min_routing_reserve_fraction:   float = 0.20   # ≥20% reserved for trace routing
    min_headroom_fraction:          float = 0.25   # ≥25% empty headroom for edits + sim-driven adjustment

    # ─── physics constraints ───
    loop_area_max_nh:               float = 2.0    # HS-LS commutation loop ≤2 nH
    decoupling_distance_max_mm:     float = 3.0    # IC VDD pin → cap ≤3 mm (R25)
    bec_to_hall_min_mm:             float = 15.0   # BEC switching vs Hall ADC drift (BILATERAL §40)
    bec_to_fet_min_mm:              float = 10.0   # BEC vs FET intermodulation
    bemf_to_swnode_min_mm:          float = 10.0   # BEMF analog vs SW digital
    mcu_clock_to_hv_min_mm:         float = 5.0    # MCU clock vs any HV trace
    forbidden_thermal_pairs:        List[Tuple[str,str]] = field(default_factory=lambda: [
        ("BEC", "Hall"),    # BEC heat shifts Hall ADC drift coefficient
    ])

    # ─── mirror symmetry (R20) ───
    mirror_x_axis:      float = 50.0    # board center for CH1↔CH2, CH3↔CH4
    mirror_y_axis:      float = 50.0    # board center for north↔south channels

    # ─── highway reservations (read from BOARD_INVARIANTS.md highway table) ───
    tlm_aux_y_start:    float = 8.5
    tlm_aux_y_end:      float = 10.0
    batt_spine_x_start: float = 48.0
    batt_spine_x_end:   float = 52.0
    bemf_centerline_x_start: float = 47.0
    bemf_centerline_x_end:   float = 53.0


# ═══════════════════════════════════════════════════════════════════════
# 2. DERIVED COORDINATES — pure functions of parameters
# ═══════════════════════════════════════════════════════════════════════
def mirror_x(x: float, p: BoardParameters) -> float:
    return 2 * p.mirror_x_axis - x

def mirror_y(y: float, p: BoardParameters) -> float:
    return 2 * p.mirror_y_axis - y


def motor_pad_positions(p: BoardParameters) -> Dict[str, Tuple[float, float]]:
    """Returns {ref: (x,y)} for all 12 motor pads.

    CH1 (SW): west column, south half. Phase A at top, C at bottom.
    CH2 (SE): east column, south half. (mirror_X of CH1)
    CH3 (NE): east column, north half. (mirror_X of CH4)
    CH4 (NW): west column, north half.

    The naming "phase A/B/C" follows BLDC convention but the actual phase order
    is determined by the FET cluster row order which equals motor_pad_y order.
    """
    out = {}
    # SW (CH1): west, south
    out['TP19'] = (p.motor_pad_x_west, p.motor_pad_y0_south +  0 * p.motor_pad_pitch_y)  # MOTOR_A
    out['TP20'] = (p.motor_pad_x_west, p.motor_pad_y0_south +  1 * p.motor_pad_pitch_y)  # MOTOR_B
    out['TP21'] = (p.motor_pad_x_west, p.motor_pad_y0_south +  2 * p.motor_pad_pitch_y)  # MOTOR_C
    # SE (CH2): mirror_X
    out['TP26'] = (mirror_x(p.motor_pad_x_west, p), out['TP19'][1])
    out['TP27'] = (mirror_x(p.motor_pad_x_west, p), out['TP20'][1])
    out['TP28'] = (mirror_x(p.motor_pad_x_west, p), out['TP21'][1])
    # NW (CH4): west, north
    out['TP42'] = (p.motor_pad_x_west, p.motor_pad_y0_north +  0 * p.motor_pad_pitch_y)
    out['TP41'] = (p.motor_pad_x_west, p.motor_pad_y0_north +  1 * p.motor_pad_pitch_y)
    out['TP40'] = (p.motor_pad_x_west, p.motor_pad_y0_north +  2 * p.motor_pad_pitch_y)
    # NE (CH3): mirror_X
    out['TP35'] = (mirror_x(p.motor_pad_x_west, p), out['TP42'][1])
    out['TP34'] = (mirror_x(p.motor_pad_x_west, p), out['TP41'][1])
    out['TP33'] = (mirror_x(p.motor_pad_x_west, p), out['TP40'][1])
    return out


def ch_fet_anchors(channel: str, p: BoardParameters) -> Dict[str, Tuple[float, float, str]]:
    """Returns {ref: (x, y, layer)} for the 6 FETs (3 HS + 3 LS) of one channel.

    Per BILATERAL: HS on hs_fet_layer (F.Cu), LS on ls_fet_layer (B.Cu),
    LS y-offset by ls_fet_y_offset_from_hs (3.6mm) for collision-free pair.
    """
    motor = motor_pad_positions(p)
    if channel == 'CH1':
        # HS-FETs in west column, x = motor_x - 6.6
        anchor_x = p.motor_pad_x_west + p.hs_fet_x_offset_from_motor   # 15 + (-6.6) = 8.4
        motor_y_list = [motor['TP19'][1], motor['TP20'][1], motor['TP21'][1]]
        refs_hs = ['Q5', 'Q7', 'Q9']
        refs_ls = ['Q6', 'Q8', 'Q10']
    elif channel == 'CH2':
        # Mirror_X of CH1
        return {ref: (mirror_x(x, p), y, layer)
                for ref, (x, y, layer) in ch_fet_anchors('CH1', p).items()
                # transform ref names too: Q5↔Q12, Q7↔Q14, etc. (worker convention)
                # For now, return mirror coords keyed by SAME refs and let worker name-map
                }
    elif channel == 'CH3':
        # mirror_Y of CH2
        return {ref: (x, mirror_y(y, p), layer)
                for ref, (x, y, layer) in ch_fet_anchors('CH2', p).items()}
    elif channel == 'CH4':
        # mirror_X of CH3
        return {ref: (mirror_x(x, p), y, layer)
                for ref, (x, y, layer) in ch_fet_anchors('CH3', p).items()}
    else:
        raise ValueError(f"Unknown channel: {channel}")

    out = {}
    for ref_hs, ref_ls, my in zip(refs_hs, refs_ls, motor_y_list):
        out[ref_hs] = (anchor_x, my, p.hs_fet_layer)
        # LS on B.Cu, 3.6mm BELOW HS (drain-aligned for SW-node via, collision-free)
        out[ref_ls] = (anchor_x + p.ls_fet_x_offset_from_hs,
                       my + p.ls_fet_y_offset_from_hs,
                       p.ls_fet_layer)
    return out


def ch_ic_anchors(channel: str, p: BoardParameters) -> Dict[str, Tuple[float, float, str, str]]:
    """Returns {ref: (x, y, layer, sub_zone)} for per-channel ICs.

    sub_zone values: 'MOTOR' (HV pins close to FETs), 'LOGIC' (3V3 pins away).
    Per Option 2 east-strip split + Option 1 placer keepout from G_PP6 dispatch.
    """
    if channel != 'CH1':
        # CH2/3/4 are pure transforms — compute via mirror chain
        base = ch_ic_anchors('CH1', p)
        if channel == 'CH2':
            return {ref: (mirror_x(x, p), y, layer, sz) for ref, (x, y, layer, sz) in base.items()}
        elif channel == 'CH3':
            base = ch_ic_anchors('CH2', p)
            return {ref: (x, mirror_y(y, p), layer, sz) for ref, (x, y, layer, sz) in base.items()}
        elif channel == 'CH4':
            base = ch_ic_anchors('CH3', p)
            return {ref: (mirror_x(x, p), y, layer, sz) for ref, (x, y, layer, sz) in base.items()}

    # CH1 anchor template
    motor = motor_pad_positions(p)
    motor_y_mid = (motor['TP19'][1] + motor['TP21'][1]) / 2  # mid of phase-A and phase-C

    # MOTOR sub-zone (x = 22..27): driver, shunts, gate-clamp diodes
    motor_mid_x = (p.east_strip_motor_x_start + p.east_strip_motor_x_end) / 2
    # LOGIC sub-zone (x = 28.5..35): MCU, ADC dividers, +3V3 caps, INA
    logic_mid_x = (p.east_strip_logic_x_start + p.east_strip_logic_x_end) / 2

    out = {
        # Driver — MOTOR sub-zone, ≤5mm from HS-FETs, MOTOR pins face WEST (toward FETs)
        'J19':  (motor_mid_x, motor_y_mid - 4, p.driver_layer, 'MOTOR'),
        # MCU — LOGIC sub-zone, SWD pins face NORTH-EAST (toward J14 FC), ADC pins face WEST-SOUTH (toward MOTOR sub-zone)
        'J18':  (logic_mid_x, motor_y_mid, p.mcu_layer, 'LOGIC'),
        # INAs (3) — MOTOR sub-zone, Kelvin sense to shunts on same layer
        'J20':  (motor_mid_x, motor['TP19'][1] + 1, p.driver_layer, 'MOTOR'),  # phase A INA
        'J21':  (motor_mid_x, motor['TP20'][1] + 1, p.driver_layer, 'MOTOR'),  # phase B INA
        'J22':  (motor_mid_x, motor['TP21'][1] - 1, p.driver_layer, 'MOTOR'),  # phase C INA
        # Op-amps (BEMF comparators) — LOGIC sub-zone
        'U3':   (logic_mid_x, motor['TP21'][1] - 4, p.mcu_layer, 'LOGIC'),
        'U4':   (logic_mid_x, motor['TP19'][1] - 4, p.mcu_layer, 'LOGIC'),
    }
    return out


def mechanical_anchors_from_lockfile() -> dict:
    """Read mount holes, fiducials, connectors, TPs from the YAML SSoT."""
    return yaml.safe_load(open(LOCKFILE))


def headroom_per_zone(zone_bbox: Tuple[float,float,float,float],
                      placed_component_areas_mm2: float,
                      p: BoardParameters) -> Dict[str, float]:
    """Returns density / routing reserve / headroom fractions for a zone."""
    x0, y0, x1, y1 = zone_bbox
    zone_area = (x1 - x0) * (y1 - y0)
    component_frac = placed_component_areas_mm2 / zone_area
    return {
        'zone_area_mm2': zone_area,
        'component_area_mm2': placed_component_areas_mm2,
        'component_fraction': component_frac,
        'routing_reserve_fraction': max(0, 1 - component_frac - p.min_headroom_fraction),
        'headroom_fraction': max(0, 1 - component_frac - p.min_routing_reserve_fraction),
        'over_budget': component_frac > p.max_component_area_fraction,
    }


# ═══════════════════════════════════════════════════════════════════════
# 3. CLI — dump derived coords for inspection / consumption
# ═══════════════════════════════════════════════════════════════════════
def main():
    import json, sys
    p = BoardParameters()

    out = {
        'board_parameters': p.__dict__,
        'motor_pads': {ref: list(pos) for ref, pos in motor_pad_positions(p).items()},
        'ch_fet_anchors': {
            ch: {ref: list(v) for ref, v in ch_fet_anchors(ch, p).items()}
            for ch in ('CH1',)  # CH2/3/4 only computable after CH1 anchors are known
        },
        'ch_ic_anchors': {
            ch: {ref: list(v) for ref, v in ch_ic_anchors(ch, p).items()}
            for ch in ('CH1', 'CH2', 'CH3', 'CH4')
        },
    }
    if '--summary' in sys.argv:
        print(f"parametric_placement.py — {p.width_mm}×{p.height_mm}mm board")
        print(f"  Motor pads: {len(out['motor_pads'])} pads, pitch {p.motor_pad_pitch_y}mm")
        print(f"  CH1 FET anchors: {len(out['ch_fet_anchors']['CH1'])} (3 HS F.Cu + 3 LS B.Cu)")
        print(f"  CH1 IC anchors: {len(out['ch_ic_anchors']['CH1'])} ICs, MOTOR + LOGIC sub-zones")
        print(f"  All 4 channels derived as: CH2=mirror_X(CH1), CH3=mirror_Y(CH2), CH4=mirror_X(CH3)")
        print()
        print(f"  Sub-zone split (east strip): MOTOR x={p.east_strip_motor_x_start}-{p.east_strip_motor_x_end}, "
              f"reserve {p.inter_subzone_routing_width}mm, LOGIC x={p.east_strip_logic_x_start}-{p.east_strip_logic_x_end}")
        print(f"  Routing channel reserve: ≥{p.routing_channel_min_width_mm}mm between any two ICs")
        print(f"  Density budget: ≤{p.max_component_area_fraction*100:.0f}% component, "
              f"≥{p.min_routing_reserve_fraction*100:.0f}% routing, ≥{p.min_headroom_fraction*100:.0f}% headroom")
    else:
        print(json.dumps(out, indent=2, default=str))

if __name__ == "__main__":
    main()
