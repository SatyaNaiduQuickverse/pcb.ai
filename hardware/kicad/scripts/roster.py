#!/usr/bin/env python3
"""roster.py — Phase 4-v3 component→subsystem SSOT (position-INDEPENDENT).

Per Sai PARK-THEN-BRING-IN REDO directive (2026-05-24): the root cause of the
9-PR ghost accumulation was classifying components by BOARD POSITION (zone
fall-through in get_chN_refs / place_subsystem_*). Position-based ownership is
circular — a component's zone decides its subsystem, but its subsystem decides
its zone. This module breaks the circularity: every component's owning subsystem
is derived ONLY from the schematic SSOT (the SKiDL-generated netlist), never from
where it currently sits on the board.

Authoritative signals, in priority order, all from pcbai_fpv4in1.net:
  1. SKiDL source file: comps from channel_skidl.py belong to a CHANNEL; comps
     from pcbai_fpv4in1_skidl.py (main sheet) belong to a central subsystem
     UNLESS they carry a per-channel tag (status LEDs, per-channel test points).
  2. Channel instance (CH1-4):
       a. a net name containing CHn (single match), else
       b. CHn in the component description, else
       c. instantiation order — SKiDL emits the 4 channel instances in order
          CH1,CH2,CH3,CH4, so within one (file:line) the ascending ref number
          maps to CH1<CH2<CH3<CH4. Verified zero-mismatch against all 30
          fully-CHn-tagged source lines (see PARK_AND_BRING_REDO.md §roster).
  3. Central subsystem (main sheet, no CHn): an explicit, reviewed line→subsystem
     table (MAIN_LINE_SUBSYS). The table is VALIDATED to cover every main-sheet
     source line — an unmapped line is a hard error, not a silent default.

Fixed mechanical geometry (FID*, H*) is NOT in the netlist; it is never parked
and never owned by a subsystem PR.

Usage:
  python3 roster.py                 # validate + print summary
  python3 roster.py --json OUT.json # write manifest
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

NET = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.net")

# Main-sheet source line → central subsystem. Derived from the SKiDL source
# structure (function/section boundaries in pcbai_fpv4in1_skidl.py). Reviewed
# table, NOT a heuristic — every main-sheet line must appear here or roster.py
# fails loudly. Per-channel main-sheet items (status LEDs, motor/SWD test points)
# are NOT here; they resolve to their channel via the CHn tag (see PERCHAN_LINES).
MAIN_LINE_SUBSYS = {
    # S1 battery input: XT30 pad, NTC inrush, input TVS, gate Zener, reverse-
    # polarity FET bank, battery-present / reverse-polarity status LEDs.
    59: "S1", 69: "S1", 72: "S1", 79: "S1", 85: "S1", 87: "S1",
    102: "S1", 143: "S1", 146: "S1", 161: "S1", 164: "S1",
    # S2 bulk caps: 4× EEHZS1V471P polymer.
    122: "S2", 125: "S2", 128: "S2", 131: "S2",
    # S5 BEC: 5× buck_stage (IC+Cin+L+Dcatch+Cbst+Cout+Rfb) and the V5/V9
    # safety_stack (eFuse, ILIM-R, polyfuse, TVS, ferrite, output caps).
    193: "S5", 199: "S5", 204: "S5", 209: "S5", 216: "S5", 223: "S5",
    228: "S5", 233: "S5", 235: "S5",
    271: "S5", 283: "S5", 290: "S5", 302: "S5", 308: "S5", 314: "S5",
    316: "S5", 318: "S5", 326: "S5", 329: "S5",
    # S3 supervisor + central Hall: V5 supervisor, VMOTOR window-comparator +
    # divider, ACS770 bus-current Hall + support, VBAT_SENSE divider, TL431
    # central 2V5 reference, central TLM pull-up.
    408: "S3", 467: "S3", 470: "S3", 478: "S3", 490: "S3", 502: "S3",
    569: "S3", 593: "S3", 598: "S3", 603: "S3", 617: "S3", 622: "S3",
    627: "S3", 637: "S3", 646: "S3", 794: "S3", 797: "S3", 800: "S3",
    823: "S3", 843: "S3", 849: "S3", 854: "S3", 862: "S3",
    # S6 connectors + edge I/O: BEC solder pads, AUX header, FC-rail LDO+filter,
    # FC DShot header, USBLC6 ESD arrays, status LED.
    431: "S6", 435: "S6", 453: "S6", 660: "S6", 672: "S6", 676: "S6",
    681: "S6", 692: "S6", 696: "S6", 698: "S6", 714: "S6", 737: "S6",
    747: "S6", 756: "S6", 773: "S6", 775: "S6",
}

# Main-sheet source lines whose parts are per-channel (resolve to CH1-4, not a
# central subsystem). Status LEDs (KILL_FW / FAULT_HW) and per-channel test
# points (motor phase, SWD, status). Ownership = channel; the channel PR brings
# them. NOTE master/Sai: their placement *zone* (channel cluster vs connector
# edge) is a placement-policy call flagged in PARK_AND_BRING_REDO.md §open.
PERCHAN_LINES = {512, 515, 531, 534, 907, 912, 914}

CHANNEL_FILE = "channel_skidl.py"
FIXED_RE = re.compile(r"^(FID|H)\d+$")


def parse_netlist(path=NET):
    """Return list of dicts: ref, file, line, value, desc, chn_nets(set)."""
    txt = path.read_text()
    comp_sec = txt[txt.find("(components"):txt.find("(libparts")]
    comps = {}
    for b in re.split(r"\(comp\s+", comp_sec)[1:]:
        ref = re.search(r'\(ref "([^"]+)"', b)
        if not ref:
            continue
        ref = ref.group(1)
        sl = re.search(r'SKiDL Line"\)\s*"([^"]+)"', b)
        val = re.search(r'\(value "([^"]*)"', b)
        desc = re.search(r'\(description "([^"]*)"', b)
        sfile, sline = ("", None)
        if sl:
            sfile, _, ln = sl.group(1).partition(":")
            sline = int(ln) if ln.isdigit() else None
        comps[ref] = {
            "ref": ref, "file": sfile, "line": sline,
            "value": val.group(1) if val else "",
            "desc": desc.group(1) if desc else "",
            "chn_nets": set(),
        }
    # nets: collect CHn membership per ref
    netsec = txt[txt.find("(nets"):]
    for nb in re.split(r"\(net\b", netsec)[1:]:
        nm = re.search(r'\(name "([^"]*)"', nb)
        if not nm:
            continue
        m = re.search(r"CH([1-4])", nm.group(1))
        if not m:
            continue
        ch = "CH" + m.group(1)
        for rr in re.findall(r'\(ref "([^"]+)"', nb):
            if rr in comps:
                comps[rr]["chn_nets"].add(ch)
    return comps


def _chn_from_tags(c):
    """CHn from a single net tag, else from description; else None."""
    if len(c["chn_nets"]) == 1:
        return next(iter(c["chn_nets"]))
    m = re.search(r"CH([1-4])", c["desc"])
    return "CH" + m.group(1) if m else None


def derive_roster(comps):
    """ref -> subsystem ('CH1'..'CH4','S1','S2','S3','S5','S6').

    Raises ValueError on any unmapped main-sheet line or ambiguous channel
    instance — the partition must be total and unambiguous.
    """
    roster = {}
    # Pass 1: tag-based (net or description). Covers channel comps and
    # per-channel main-sheet comps that carry a CHn signal.
    need_order = defaultdict(list)   # (file,line) -> [refs] needing order fallback
    for ref, c in comps.items():
        is_channel = (c["file"] == CHANNEL_FILE) or (c["line"] in PERCHAN_LINES)
        if is_channel:
            ch = _chn_from_tags(c)
            if ch:
                roster[ref] = ch
            else:
                need_order[(c["file"], c["line"])].append(ref)
        # central subsystems handled in pass 3
    # Pass 2: instantiation-order fallback for tagless channel comps.
    # SKiDL runs each channel() call to completion before the next, so within
    # one (file,line) the refs form 4 contiguous ascending blocks CH1..CH4. A
    # line may emit k parts per channel (e.g. two 100nF caps) → block size k.
    for (f, ln), refs in need_order.items():
        n = len(refs)
        if n % 4 != 0:
            raise ValueError(
                f"channel source {f}:{ln} has {n} tagless instances "
                f"(not divisible by 4 channels): {sorted(refs)}")
        k = n // 4
        ordered = sorted(refs, key=_refnum)
        for i, ch in enumerate(["CH1", "CH2", "CH3", "CH4"]):
            for ref in ordered[i * k:(i + 1) * k]:
                roster[ref] = ch
    # Pass 3: central subsystems from the reviewed line table.
    for ref, c in comps.items():
        if ref in roster:
            continue
        if c["file"] == CHANNEL_FILE:
            continue  # already handled
        sub = MAIN_LINE_SUBSYS.get(c["line"])
        if sub is None:
            raise ValueError(
                f"main-sheet line {c['line']} ({ref}, {c['value']!r}) "
                f"not in MAIN_LINE_SUBSYS — add it (do not default).")
        roster[ref] = sub
    return roster


def _refnum(ref):
    m = re.match(r"[A-Za-z]+(\d+)", ref)
    return int(m.group(1)) if m else 0


def validate(comps, roster):
    """Assert the partition is total + consistent. Returns per-subsystem counts."""
    errs = []
    for ref in comps:
        if ref not in roster:
            errs.append(f"unassigned: {ref}")
    counts = defaultdict(int)
    for ref, sub in roster.items():
        counts[sub] += 1
    # Channels must have equal rosters (symmetry precondition, R19).
    ch_counts = {k: v for k, v in counts.items() if k.startswith("CH")}
    if len(set(ch_counts.values())) > 1:
        errs.append(f"channel rosters unequal: {ch_counts}")
    return dict(sorted(counts.items())), errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write manifest JSON to this path")
    args = ap.parse_args()

    comps = parse_netlist()
    roster = derive_roster(comps)
    counts, errs = validate(comps, roster)

    print(f"netlist components: {len(comps)}")
    print(f"assigned:           {len(roster)}")
    print("per-subsystem counts:")
    for sub, n in counts.items():
        print(f"  {sub}: {n}")
    print(f"channel total: {sum(v for k,v in counts.items() if k.startswith('CH'))}")
    print(f"central total: {sum(v for k,v in counts.items() if not k.startswith('CH'))}")
    if errs:
        print("\nVALIDATION ERRORS:")
        for e in errs:
            print(f"  {e}")
        return 1
    print("\nVALIDATION: OK (total partition, channels equal)")

    if args.json:
        manifest = {
            "source": "pcbai_fpv4in1.net (SKiDL netlist)",
            "method": "position-independent: skidl-file + CHn-tag + ref-order + main-line-table",
            "counts": counts,
            "roster": {r: roster[r] for r in sorted(roster, key=lambda x: (x[0], _refnum(x)))},
        }
        Path(args.json).write_text(json.dumps(manifest, indent=2))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
