#!/usr/bin/env python3
"""fix_fet_netlist_drop.py — repair kinet2pcb silent-drop on FET footprints.

SKiDL .net uses symbolic pin names G/D/S (from Device:Q_NMOS symbol). The
assigned footprints (TO-263-3_TabPin2, W-PDFN-8-1EP_6x5mm) have numeric pad
names. kinet2pcb couldn't bridge them → Q1-Q28 imported with all pads at net="".

Fix: parse .net → build (ref, symbolic_pin) → net_name. For each Q-ref
footprint, look up nets by symbolic pin and assign to the correct physical
pads via standard package mapping.

Standard pin maps:
  TO-263-3_TabPin2 (AOTL66912, Q5-Q28):
    G → pad "1"
    D → pad "2" (both instances — lead + tab)
    S → pad "3"
  W-PDFN-8-1EP_6x5mm (BSC014N06NS, Q1-Q4):
    G → pad "4"
    S → pads "1", "2", "3"
    D → pads "5", "6", "7", "8", and the unnamed exposed pad (EP)

The 4 unnamed (pad.GetName()=='') pads on TO-263 are courtyard/keep-out
artifacts — leave as no-net.

Per master directive PR-A4-integrate Path B amendment 4.
"""
import pcbnew
import re
import sys
from pathlib import Path

NET_FILE = Path("hardware/kicad/pcbai_fpv4in1.net")
PCB_FILE = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Symbolic-pin → list of physical pad numbers
PIN_MAP_TO263 = {"G": ["1"], "D": ["2"], "S": ["3"]}
PIN_MAP_PDFN8 = {"G": ["4"], "S": ["1", "2", "3"], "D": ["5", "6", "7", "8"]}


def parse_netlist():
    """Parse .net → {(ref, symbolic_pin): net_name}."""
    txt = NET_FILE.read_text()
    mapping = {}
    current_net = None
    last_ref = None
    in_net_block = False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("(net"):
            current_net = None
            in_net_block = True
            continue
        if not in_net_block:
            continue
        m = re.match(r'\(name\s*"([^"]+)"\)$', s)
        if m and current_net is None:
            current_net = m.group(1)
            continue
        m = re.match(r'\(ref\s*"([^"]+)"\)', s)
        if m:
            last_ref = m.group(1)
            continue
        m = re.match(r'\(pin\s*"([^"]+)"\)', s)
        if m and last_ref and current_net:
            mapping[(last_ref, m.group(1))] = current_net
            last_ref = None
    return mapping


def main():
    netlist = parse_netlist()
    print(f"Parsed netlist: {len(netlist)} ref-pin mappings")

    board = pcbnew.LoadBoard(PCB_FILE)

    # Index existing nets in board by name
    board_nets = {}
    for net in board.GetNetInfo().NetsByName().values():
        board_nets[net.GetNetname()] = net

    fixed_pads = 0
    created_nets = 0
    fets_touched = set()

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith("Q"):
            continue
        fp_name = str(fp.GetFPID().GetLibItemName())
        if "TO-263" in fp_name:
            pin_map = PIN_MAP_TO263
        elif "PDFN-8" in fp_name:
            pin_map = PIN_MAP_PDFN8
        else:
            continue  # unrecognised — skip

        # Verify it's actually unnetted (avoid double-applying)
        if any(p.GetNet().GetNetname() for p in fp.Pads()):
            continue

        applied_any = False
        for symbolic_pin, pad_numbers in pin_map.items():
            net_name = netlist.get((ref, symbolic_pin))
            if not net_name:
                continue
            # Get-or-create net
            net_obj = board_nets.get(net_name)
            if net_obj is None:
                net_obj = pcbnew.NETINFO_ITEM(board, net_name)
                board.Add(net_obj)
                board_nets[net_name] = net_obj
                created_nets += 1
            # Assign to each physical pad
            for pad in fp.Pads():
                if pad.GetNumber() in pad_numbers:
                    pad.SetNet(net_obj)
                    fixed_pads += 1
                    applied_any = True
        if applied_any:
            fets_touched.add(ref)

    print(f"Fixed {fixed_pads} pads across {len(fets_touched)} FETs")
    print(f"Created {created_nets} new net objects")
    print(f"FETs touched: {sorted(fets_touched, key=lambda r: (len(r), r))}")

    pcbnew.Refresh()
    board.Save(PCB_FILE)
    print(f"Saved {PCB_FILE}")


if __name__ == "__main__":
    main()
