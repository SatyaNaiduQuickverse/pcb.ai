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
    _nl = roster_mod.parse_netlist()
    ro = roster_mod.derive_roster(_nl)
    line = {r: _nl[r].get("line", 0) for r in _nl}   # SKiDL creation order = intent
    ch1 = {k for k, v in ro.items() if v == "CH1"}
    roles = {}  # ref -> dict

    DRV, MCU = "J19", "J18"
    motor_of = {"MOTOR_A_CH1": "TP19", "MOTOR_B_CH1": "TP20", "MOTOR_C_CH1": "TP21"}
    # FETs: HS has S on a MOTOR net (F.Cu, anchored to motor pad); LS has D on a
    # MOTOR net (B.Cu, directly beneath its HS partner — Sai opt-(a) + methodology
    # §Tier-2: same XY, opposite layer, SW-node stitched vias).
    fets = [r for r in ch1 if val[r] == "BSC014N06NS"]
    hs_of = {}  # MOTOR net -> HS FET ref
    for q in fets:
        if rpn[q].get("S") in motor_of:
            hs_of[rpn[q]["S"]] = q
    for q in fets:
        pins = rpn[q]
        mnet = next((pins[p] for p in pins if pins[p] in motor_of), None)
        is_hs = pins.get("S") in motor_of
        if is_hs:
            roles[q] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                        "parent": motor_of[mnet], "parent_pin": "1", "relation": "hs-fet",
                        "max_distance_mm": 7, "layer": "F.Cu", "loop_member": True}
        else:
            roles[q] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                        "parent": hs_of.get(mnet, motor_of[mnet]), "parent_pin": "D",
                        "relation": "ls-fet", "max_distance_mm": 1.5,  # ~same XY beneath HS
                        "layer": "B.Cu", "loop_member": True}
    # Shunts (0.2mR): SHUNT_x_TOP ↔ GND; parent = the LS FET whose S is that net.
    for s in [r for r in ch1 if val[r] == "0.2mR"]:
        topnet = next((rpn[s][p] for p in rpn[s] if "SHUNT" in (rpn[s][p] or "")), None)
        lsfet = next((rf for rf, pn in net_nodes.get(topnet, []) if rf.startswith("Q") and pn == "S"), None)
        roles[s] = {"tier": 2, "role": "cluster-member", "subsystem": "CH1",
                    "parent": lsfet or motor_of.get(topnet), "parent_pin": "S" if lsfet else "1",
                    "relation": "source-shunt", "max_distance_mm": 6,
                    "layer": "F.Cu",  # methodology: shunt F.Cu after LS-source via cluster
                    "loop_member": True, "kelvin_sense": True}
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

    # Decoupling-by-rail (R25/G4): a cap on {power-rail, GND} only (no signal net)
    # is decoupling — the flat netlist hides its IC, so trace it via the shared
    # power rail. Round-robin each rail's caps across that rail's IC VDD pins so
    # every VDD pin gets a cap ≤3mm same-side (master 2026-05-26 canonical fix).
    RAILS = {"+3V3", "+3V3A", "+5V", "+9V", "+VMOTOR", "VMOTOR_CH"}
    ic_set = [DRV, MCU] + [r for r in ch1 if val[r] in
              ("INA186A3IDCKR", "LM393", "74LVC1G08")]
    # Group each rail's VDD pins by IC, so a cap can be matched to the IC it was
    # AUTHORED to decouple (not an arbitrary round-robin pin on the shared rail).
    rail_ic_pins = defaultdict(lambda: defaultdict(list))  # rail -> ic -> [pins]
    for ic in ic_set:
        for pin, net in rpn[ic].items():
            if net in RAILS:
                rail_ic_pins[net][ic].append(pin)
    used = defaultdict(set)  # ic -> {pins already given a decoupling cap}
    for cap in sorted([r for r in ch1 if r.startswith("C") and r not in roles],
                      key=lambda x: line.get(x, 0)):
        nets = set(rpn[cap].values())
        rail = next((n for n in nets if n in RAILS), None)
        if not (rail and "GND" in nets and not (nets - {rail, "GND"})
                and rail_ic_pins.get(rail)):
            continue
        # INTENT by SKiDL line: a bypass cap is created right AFTER its IC, so the
        # owning IC is the rail-IC with the greatest line ≤ the cap's line. This
        # routes "LM393 bypass" → the LM393, "DRV bypass" → the driver, etc., and
        # crucially exposes ICs that have NO authored bypass cap (e.g. the INAs)
        # as genuinely-uncovered VDD pins rather than masking them by round-robin.
        ics = list(rail_ic_pins[rail].keys())
        cl = line.get(cap, 1e9)
        before = [ic for ic in ics if line.get(ic, 0) <= cl]
        owner = (max(before, key=lambda ic: line[ic]) if before
                 else min(ics, key=lambda ic: line.get(ic, 0)))
        free = [p for p in rail_ic_pins[rail][owner] if p not in used[owner]]
        if free:
            pin = free[0]; used[owner].add(pin)
            roles[cap] = {"tier": 3, "role": "decoupling", "subsystem": "CH1",
                          "parent": owner, "parent_pin": pin, "relation": "decoupling",
                          "max_distance_mm": 3, "same_layer_as_parent": True}
        else:
            # owner already fully decoupled — surplus cap is bulk/aux (no ≤3mm duty).
            roles[cap] = {"tier": 3, "role": "cluster-aux", "subsystem": "CH1",
                          "parent": owner, "relation": "bypass-bulk",
                          "same_layer_as_parent": True}

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
        # Motor-phase clamp/snubber diode: a diode whose ONLY signal net is a
        # MOTOR_x switching node (the other pin is GND/power) is owned by the
        # half-bridge that drives that node — anchor it to the LS FET it clamps
        # across (B.Cu side has room), NOT a sibling 2-pin gate-bypass diode.
        # Fewest-pins would otherwise chain D26->D24 etc. into the crowded gate
        # cluster (no slot). Gate-bypass diodes (2 signal nets: gate N$x + MOTOR)
        # are excluded by the len==1 test and fall through to their gate-R.
        sig_nets = {net for net in rpn[ref].values() if net and net not in POWER}
        mclamp_fet = None
        if (ref.startswith("D") and len(sig_nets) == 1
                and re.match(r"MOTOR_[ABC]_CH\d+$", next(iter(sig_nets)))):
            mnet = next(iter(sig_nets))
            qs = [rf for rf, pn in net_nodes.get(mnet, [])
                  if rf in roles and rf != ref and rf.startswith("Q")]
            ls = [q for q in qs if roles[q].get("layer") == "B.Cu"]
            mclamp_fet = (ls or qs)[0] if qs else None
        if mclamp_fet is not None:
            parent = mclamp_fet
        else:
            parent = min(cands, key=lambda rf: (len(rpn[rf]), rf.startswith("C"))) if cands else None
        if parent is None:
            # Pure-power cap (bulk/bypass on a power rail, no signal net): anchor to
            # a roled component sharing its NON-GND power net, preferring a FET on
            # that rail — VMOTOR bulk caps belong at the half-bridge, NOT dumped on
            # the MCU's belly pad (was causing J18 EP-pad overlaps).
            pc = []
            for p, net in rpn[ref].items():
                if net in ("GND", "GNDA") or net not in POWER:
                    continue
                for rf, pn in net_nodes.get(net, []):
                    if rf in roles and rf != ref:
                        pc.append(rf)
            if pc:
                parent = min(pc, key=lambda rf: (not rf.startswith("Q"), len(rpn[rf])))
        is_cap = ref.startswith("C")
        # A cap is TRUE decoupling only if it bypasses an IC on a power rail (R25:
        # ≤3mm same-side). Caps on a divider/diode/filter node (parent is a passive)
        # are cluster-aux — not in the switching loop, not IC-VDD — so they may
        # overflow to B.Cu / zone-fill and anchor loosely (master 2026-05-26).
        ICS = {DRV, MCU} | {r for r in ch1 if val[r] in
               ("INA186A3IDCKR", "LM393", "74LVC1G08")}
        on_power = any(rpn[ref].get(p) in POWER for p in rpn[ref])
        if is_cap and parent in ICS and on_power:
            roles[ref] = {"tier": 3, "role": "decoupling", "subsystem": "CH1",
                          "parent": parent, "parent_pin": "1", "relation": "decoupling",
                          "max_distance_mm": 3, "same_layer_as_parent": True}
        elif is_cap:
            roles[ref] = {"tier": 3, "role": "cluster-aux", "subsystem": "CH1",
                          "parent": parent or MCU, "parent_pin": "1", "relation": "aux-cap",
                          "max_distance_mm": 6, "same_layer_as_parent": True}
        else:
            roles[ref] = {"tier": 3, "role": "cluster-member", "subsystem": "CH1",
                          "parent": parent or MCU, "parent_pin": "1", "relation": "auto",
                          "max_distance_mm": 6, "same_layer_as_parent": True}
    return roles


def emit(roles):
    def fmt(d):
        keys = ["tier", "role", "subsystem", "parent", "parent_pin", "relation",
                "max_distance_mm", "layer", "same_layer_as_parent", "loop_member", "kelvin_sense"]
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
