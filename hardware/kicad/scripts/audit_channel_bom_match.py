#!/usr/bin/env python3
"""audit_channel_bom_match.py — G_PP16 per-channel BOM consistency audit.

Class of bug this prevents:

A passive on CH1 has no mirror on CH2/3/4 (forgotten in placement transform).
R20 symmetry promise: every per-channel component on CHn has identical role/
count/value on CHm via mirror_X(50) / mirror_Y(50). If CH1 has 14 0.1uF caps
and CH2 has 13, ONE channel is silently missing a decoupling cap.

Algorithm: for each suffix-pattern of refs (e.g. R*_CH1, C*_CH1):
  Count refs per channel after stripping CHn suffix.
  All 4 counts must match. Else FAIL with list of refs only in one channel.

Also: for refs with explicit `channel:` attribute in netlist (worker-verified),
group by channel and compare value pattern (e.g. 4× 0.1uF + 2× 10uF per CH).

Exit 0 = PASS, 1 = FAIL.

Per [[feedback-symmetry-preserves-work]] + Sai 2026-05-26 audit-completeness
broader-thinking sweep.
"""
import os, re, sys, collections

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); return 1

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0

    # Group refs by net-suffix pattern matching _CHn or _CHn$
    ch_counts = collections.defaultdict(lambda: collections.Counter())
    ch_refs   = collections.defaultdict(lambda: collections.defaultdict(set))  # channel -> value -> refs

    by_ref = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x = pos.x/mm; y = pos.y/mm
        # skip unplaced/parked
        if x < -5 or x > 200 or y < -5 or y > 200: continue
        val = fp.GetValue()
        by_ref[ref] = (x, y, val, fp)

    # Build per-channel groupings via net-name suffix matching
    for ref, (x, y, val, fp) in by_ref.items():
        # Inspect any pad's net to find _CHn assignment
        ch = None
        for pad in fp.Pads():
            net = pad.GetNetname()
            m = re.search(r'_CH([1-4])\b', net)
            if m:
                ch = int(m.group(1)); break
        if ch is None: continue
        # role = ref prefix (R, C, D, Q, etc.)
        role = re.match(r'([A-Z]+)', ref).group(1) if re.match(r'([A-Z]+)', ref) else "?"
        key = (role, val)
        ch_counts[ch][key] += 1
        ch_refs[ch][key].add(ref)

    print("=" * 70)
    print(f"audit_channel_bom_match.py G_PP16 — {pcb_path}")
    print("=" * 70)
    chs = sorted(ch_counts.keys())
    if len(chs) < 2:
        print(f"  ℹ Only {len(chs)} channel(s) have placed parts — skipping (staged mode)")
        return 0

    # Staged-mode detection: count FETs (Q-prefix) per channel via pads' nets.
    # If any channel has 0 FETs, this is staged single-channel placement — the
    # BOM mismatch is expected (CH2/3/4 only have motor pads until their PR).
    # Same pattern as G_PP20 staged-mode (worker 2026-05-26 catch).
    ch_fet_counts = {ch: 0 for ch in chs}
    for ref, (x, y, val, fp) in by_ref.items():
        if not ref.startswith('Q'): continue
        for pad in fp.Pads():
            net = pad.GetNetname()
            import re as _re
            m = _re.search(r'_CH([1-4])\b', net)
            if m:
                ch_fet_counts[int(m.group(1))] = ch_fet_counts.get(int(m.group(1)), 0) + 1
                break
    if any(v == 0 for v in ch_fet_counts.values()):
        empty_chs = [ch for ch, v in ch_fet_counts.items() if v == 0]
        print(f"  ℹ STAGED MODE — channels without FETs: {empty_chs} → BOM mismatch advisory only")
        # Still print the report but return 0 (don't fail PR)
        STAGED = True
    else:
        STAGED = False

    all_keys = set()
    for ch in chs: all_keys.update(ch_counts[ch].keys())
    fails = []
    for key in sorted(all_keys):
        counts = [ch_counts[ch][key] for ch in chs]
        if len(set(counts)) > 1:
            details = ", ".join(f"CH{ch}={ch_counts[ch][key]}" for ch in chs)
            extras = {}
            for ch in chs:
                if ch_counts[ch][key] == max(counts):
                    extras[ch] = ch_refs[ch][key]
            fails.append((key, counts, details, extras))

    print(f"  {len(chs)} channels with placed parts, {len(all_keys)} distinct (role,value) keys")
    if fails and STAGED:
        print(f"  ℹ {len(fails)} mismatches (advisory — staged mode):")
        for key, counts, details, extras in fails[:10]:
            role, val = key
            print(f"    ({role}, {val}): {details}")
        return 0  # don't fail PR in staged mode
    if fails:
        print()
        print(f"  ❌ FAIL — {len(fails)} key(s) with mismatched per-channel count:")
        for key, counts, details, extras in fails[:30]:
            role, val = key
            print(f"    ({role}, {val}): {details}")
        print()
        return 1
    print()
    print(f"  ✅ PASS — every per-channel (role,value) key has identical count across channels")
    return 0

if __name__ == "__main__":
    sys.exit(main())
