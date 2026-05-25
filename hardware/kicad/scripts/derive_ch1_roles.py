#!/usr/bin/env python3
"""derive_ch1_roles.py — generate CH1 routing_topology component roles from netlist.

CH1 is the Tier-2/Tier-3 template (CH2/3/4 mirror it). 106 components is too many
to hand-author reliably, so this derives role/parent/parent_pin/max_distance from
the SKiDL netlist connectivity + values, and emits the routing_topology.yaml
`components:` block for CH1. Per PLACEMENT_METHODOLOGY Tier 2/3 + R23/R25.

Structure (verified from connectivity):
  Phase A/B/C → motor pad TP19/20/21 (Tier-1 anchor, switching node):
    HS FET (Qodd: S→MOTOR), LS FET (Qeven: D→MOTOR, S→SHUNT_x_TOP), shunt R(0.2mR),
    gate-R (15R, driver↔FET.G), gate clamp Zener(BZT52C5V6)+pulldown(10K)/FET,
    phase TVS (SMBJ33A), bootstrap/bypass caps on the phase node.
  Gate driver J19 (DRV8300): cluster anchor near the FET cluster.
  MCU J18 (AT32F421): near driver. INA J20-22: across each shunt.
  Decoupling caps: parent = IC sharing the cap's non-GND rail net, ≤3mm same-layer.

Emits to stdout; review then paste into routing_topology.yaml.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import roster as roster_mod

NET = "hardware/kicad/pcbai_fpv4in1.net"


def connectivity():
    txt = Path(NET).read_text()
    comp = txt[txt.find("(components"):txt.find("(libparts")]
    val, fp = {}, {}
    for b in re.split(r"\(comp\s+", comp)[1:]:
        m = re.search(r'\(ref "([^"]+)"', b)
        v = re.search(r'\(value "([^"]*)"', b)
        f = re.search(r'\(footprint "([^"]*)"', b)
        if m:
            val[m.group(1)] = v.group(1) if v else ""
            fp[m.group(1)] = (f.group(1) if f else "").split(":")[-1]
    ns = txt[txt.find("(nets"):]
    rpn, net_nodes = defaultdict(dict), defaultdict(list)
    for nb in re.split(r"\(net\b", ns)[1:]:
        nm = re.search(r'\(name "([^"]*)"', nb)
        if not nm:
            continue
        for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"', nb):
            rpn[ref][pin] = nm.group(1)
            net_nodes[nm.group(1)].append((ref, pin))
    return val, fp, rpn, net_nodes


def derive():
    val, fp, rpn, net_nodes = connectivity()
    ro = roster_mod.derive_roster(roster_mod.parse_netlist())
    ch1 = {k for k, v in ro.items() if v == "CH1"}
    roles = {}  # ref -> dict

    DRV, MCU = "J19", "J18"
    motor_of = {"MOTOR_A_CH1": "TP19", "MOTOR_B_CH1": "TP20", "MOTOR_C_CH1": "TP21"}
    # FETs: HS has S on a MOTOR net; LS has D on a MOTOR net.
    for q in [r for r in ch1 if val[r] == "BSC014N06NS"]:
        pins = rpn[q]
        mnet = next((pins[p] for p in pins if pins[p] in motor_of), None)
        pad = motor_of.get(mnet)
        is_hs = pins.get("S") in motor_of
        roles[q] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                    "parent": pad, "parent_pin": "1",
                    "relation": "hs-fet" if is_hs else "ls-fet",
                    "max_distance_mm": 7, "same_layer_as_parent": True,  # 6×5mm SuperSO8
                    "loop_member": True}
    # Shunts (0.2mR): SHUNT_x_TOP ↔ GND; parent = the LS FET whose S is that net.
    for s in [r for r in ch1 if val[r] == "0.2mR"]:
        topnet = next((rpn[s][p] for p in rpn[s] if "SHUNT" in (rpn[s][p] or "")), None)
        lsfet = next((rf for rf, pn in net_nodes.get(topnet, []) if rf.startswith("Q") and pn == "S"), None)
        roles[s] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                    "parent": lsfet or motor_of.get(topnet), "parent_pin": "S" if lsfet else "1",
                    "relation": "source-shunt", "max_distance_mm": 2,
                    "same_layer_as_parent": True, "loop_member": True, "kelvin_sense": True}
    # Gate resistors (15R): between driver out and a FET gate net. Parent = the FET
    # whose gate pin shares the resistor's gate-side net — spreads the 6 gate-R to
    # the 6 FETs (≤5mm from gate per R23) instead of piling on the driver.
    for g in [r for r in ch1 if val[r] == "15R"]:
        gatefet = None
        for p, net in rpn[g].items():
            fet = next((rf for rf, pn in net_nodes.get(net, [])
                        if val.get(rf) == "BSC014N06NS" and pn == "G"), None)
            if fet:
                gatefet = fet
                break
        roles[g] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                    "parent": gatefet or DRV, "parent_pin": "G" if gatefet else "1",
                    "relation": "gate-r", "max_distance_mm": 5, "same_layer_as_parent": True}
    # Gate driver: cluster anchor near the phase-A motor pad cluster.
    roles[DRV] = {"tier": 2, "role": "cluster-anchor", "subsystem": "CH1",
                  "parent": "TP20", "parent_pin": "1", "relation": "gate-driver",
                  "max_distance_mm": 8, "same_layer_as_parent": True}
    # MCU: zone-anchored centre-east of CH1 so its ~13 decoupling caps + logic ICs
    # ring it with room (driver+FETs occupy the west motor-pad column; piling MCU
    # on the driver overflowed the west). SPI to driver stays short via the gate-R
    # chain; exact MCU↔DRV distance flagged to master (methodology says ≤5mm).
    roles[MCU] = {"tier": 3, "role": "cluster-anchor", "subsystem": "CH1",
                  "zone_hint": [26.0, 66.0]}
    # INA186 (current sense): parent = its phase shunt (shares SHUNT net).
    for ina in [r for r in ch1 if val[r] == "INA186A3IDCKR"]:
        snet = next((rpn[ina][p] for p in rpn[ina] if "SHUNT" in (rpn[ina][p] or "")), None)
        shunt = next((rf for rf, pn in net_nodes.get(snet, []) if val.get(rf) == "0.2mR"), None)
        roles[ina] = {"tier": 3, "role": "cluster-member", "subsystem": "CH1",
                      "parent": shunt or DRV, "parent_pin": "1",
                      "relation": "ina-near-shunt", "max_distance_mm": 5,
                      "same_layer_as_parent": True}
    # LM393 comparator near MCU; 74LVC1G08 OR near MCU.
    for ref in [r for r in ch1 if val[r] in ("LM393", "74LVC1G08")]:
        roles[ref] = {"tier": 3, "role": "cluster-member", "subsystem": "CH1",
                      "parent": MCU, "parent_pin": "1", "relation": "logic-near-mcu",
                      "max_distance_mm": 8, "same_layer_as_parent": True}
    # Everything else (caps, clamp Z/pulldown, TVS, BEMF dividers, LEDs, NTC, BAT54,
    # OTP dividers): parent = the in-CH1 IC/FET/shunt it shares a non-power net with,
    # nearest by net; fallback parent = MCU. Decoupling rule (≤3mm) for caps.
    POWER = {"GND", "+3V3", "+3V3A", "+5V", "+VMOTOR", "VMOTOR_CH", "+V5", "+V9", ""}
    placed = set(roles)
    # Process fewest-pins-first (and devices before caps): a 2-pin BEMF/filter
    # divider R is roled before the 2-pin cap on its node, so the cap then finds
    # the divider (most-specific parent) instead of falling back to the MCU.
    auto_order = sorted(ch1 - placed,
                        key=lambda x: (len(rpn[x]), x.startswith("C"),
                                       int(re.search(r"\d+", x).group())))
    for ref in auto_order:
        if ref.startswith(("TP",)):  # SWD/BOOT/motor TPs are Tier-1 anchors
            continue
        # Parent = the most-SPECIFIC already-roled component on a shared signal
        # (non-power) net: fewest pins wins, so a 2-pin BEMF/filter divider R beats
        # the 32-pin MCU that touches every signal. Tie-break prefers a device
        # (R/Q/U) over another cap. This routes BEMF caps to R60-65, filter caps to
        # their local node, instead of all piling on J18.
        cands = []
        for p, net in rpn[ref].items():
            if net in POWER:
                continue
            for rf, pn in net_nodes.get(net, []):
                if rf in roles and rf != ref:
                    cands.append(rf)
        parent = min(cands, key=lambda rf: (len(rpn[rf]), rf.startswith("C"))) if cands else None
        is_cap = ref.startswith("C")
        roles[ref] = {"tier": 3, "role": "decoupling" if is_cap else "cluster-member",
                      "subsystem": "CH1", "parent": parent or MCU, "parent_pin": "1",
                      "relation": "auto", "max_distance_mm": 3 if is_cap else 5,
                      "same_layer_as_parent": True}
    return roles


def emit(roles):
    def fmt(d):
        keys = ["tier", "role", "subsystem", "parent", "parent_pin", "relation",
                "max_distance_mm", "same_layer_as_parent", "loop_member", "kelvin_sense"]
        parts = []
        for k in keys:
            if k in d:
                v = d[k]
                v = "true" if v is True else ("false" if v is False else
                                              (f'"{v}"' if isinstance(v, str) else v))
                parts.append(f"{k}: {v}")
        return "{" + ", ".join(parts) + "}"
    print("  # ==== CH1 (Stage 2 template) — derive_ch1_roles.py from netlist 2026-05-26 ====")
    for ref in sorted(roles, key=lambda x: (x[0], int(re.search(r"\d+", x).group()))):
        print(f"  {ref}: {fmt(roles[ref])}")


if __name__ == "__main__":
    rs = derive()
    print(f"# CH1 roles derived: {len(rs)}", file=sys.stderr)
    emit(rs)
