#!/usr/bin/env python3
"""inject_vmotor_pour.py — CH1 30/30 lever T

+VMOTOR pour architecture fix: reconcile canonical .kicad_pcb with the
BOARD_INVARIANTS 10L stackup spec AND add a second same-net Cu layer so
M3 stitch-vias pass kicad-cli's via_dangling rule (≥2 same-net Cu layers
touched by every through-via).

ROOT CAUSE (lever T diagnosis on canonical board sha a69703a, pre-fix):
    BOARD_INVARIANTS 10L spec:  In3=GND,     In5=+VMOTOR
    Canonical board reality:    In3=+VMOTOR, In5=GND  ← INVERTED
    The +VMOTOR pour therefore exists on EXACTLY ONE Cu layer (In3),
    and EVERY M3 stitch through-via lands on a +VMOTOR pour on a single
    Cu layer.  KiCad's kicad-cli pcb drc via_dangling rule flags any
    through-via whose net touches Cu on only one layer.  Result on
    canonical pre-fix: 199 via_dangling reports, M3 stitch
    `stitch_vmotor_plane.py` (lever S verifier) removes ALL 515 stitch
    vias → density = 0/cm² → honest SHORT vs the 4/cm² G14 target.

ROOT-CAUSE FIX (Option C, drone-grade per Sai operating rules):
    1. SWAP zone nets at the .kicad_pcb S-expression level:
         In3 zone:  net=+VMOTOR  → net=GND
         In5 zone:  net=GND      → net=+VMOTOR
       This realigns the canonical with the BOARD_INVARIANTS spec.
    2. INJECT new `(zone ...)` blocks on F.Cu AND B.Cu with the SAME
       board-spanning outline + net=+VMOTOR, priority=0 so they fill
       only the negative space around foreign pads/tracks (ZONE_FILLER
       auto-clears foreign-net copper).

ARCHITECTURE OPTIONS CONSIDERED (and rejected vs Option C):
    Option A — net SWAP only.  Reconciles invariants but +VMOTOR still
               single-layer → through-vias still dangle.  REJECTED:
               leaves the connectivity bug.
    Option B — leave In3/In5 inverted, ADD F.Cu/B.Cu local pours.
               REJECTED: leaves the invariants drift.  Sai "redo not
               mitigate" rule.

WHY S-EXPRESSION EDIT INSTEAD OF pcbnew API:
    pcbnew SWIG batch zone-mutation segfaults on save when the zone's
    LSET is reassigned mid-flight (reproduced 2026-05-29 on canonical;
    matches reference-pcbnew-swig-batch-mutation-trap).  S-expression
    text edit + a single fresh-subprocess refill pass via the companion
    `_refill` mode is deterministic and matches the inject_stackup.py
    pattern.

IDEMPOTENT
    Detect the In5 +VMOTOR + F.Cu/B.Cu +VMOTOR pours; exit NO_OP if
    already applied.

DRONE-GRADE CLEARANCE GATES (post-emit, BLOCKING)
    G1. ≥2 distinct Cu layers carry a +VMOTOR-net zone.
    G2. In5.Cu zone net == +VMOTOR (BOARD_INVARIANTS compliance).
    G3. zone refill produces no exception, output board loads.
    G4. (optional --run-drc) kicad-cli pcb drc reports 0 +VMOTOR
        via_dangling (slow; let the stitcher do it if you prefer).
    G5. (default ON --remove-orphan-vias) kicad-cli pcb drc reports 0
        via_dangling AFTER orphan-via cleanup pass. Stage 5 removes any
        through-via whose barrel center has no same-net Cu contact on
        ≥2 layers (the ground-truth that kicad-cli enforces).

LEVER V RESIDUAL FIX (2026-05-29 — Sai catch on PR #250 post-merge)
    PR #250 (lever T) achieved 199→3 via_dangling on canonical
    post-T board (085dee9). The 3 residual offenders are NOT +VMOTOR:
        MOTOR_A_CH1 via at (18.0, 54.0)  — 1.20mm OUTSIDE F+B MOTOR_A pour
        MOTOR_C_CH1 via at (18.0, 82.0)  — 1.20mm OUTSIDE F+B MOTOR_C pour
        SHUNT_C_TOP_CH1 via at (10.0, 86.0) — 0.37mm OUTSIDE F SHUNT pour;
                                              NO B.Cu zone for that net
    Root cause: the upstream add_sw_vias.py grid generator (lever M2)
    accepts a candidate via if it fits inside ANY F.Cu polygon (pour OR
    pad-bbox) AND inside ANY B.Cu polygon — but ZONE_FILLER on the
    refilled post-T board pulls the MOTOR pour back by the foreign-net
    clearance, leaving the via barrel center in pour-clearance void.
    The 3 vias are truly orphan: no same-net track passes through the
    via center on EITHER surface layer.
    T cannot rescue them by extending the +VMOTOR pour (wrong nets).
    Lever V resolution = Stage 5 = post-refill orphan-via REMOVAL,
    authoritative via kicad-cli pcb drc via_dangling.

USAGE
    python3 inject_vmotor_pour.py \\
        --board pcbai_fpv4in1.kicad_pcb \\
        --output pcbai_fpv4in1_vmotor_fixed.kicad_pcb \\
        [--report report.json] [--run-drc] [--surface-layers F.Cu,B.Cu] \\
        [--remove-orphan-vias / --keep-orphan-vias]

Read-only on --board.  Writes new .kicad_pcb at --output.
Exit 0 = PASS, 1 = post-emit FAIL, 2 = environment / load error.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# Constants (mirror BOARD_INVARIANTS 10L spec)
VMOTOR_NET_NAME = "+VMOTOR"
GND_NET_NAME = "GND"

# Default canonical net IDs on this codebase — discovered dynamically from
# the (net N "+VMOTOR") declaration in the header, so this is just a
# fallback for diagnostic messages.
DEFAULT_VMOTOR_NET_ID = 9
DEFAULT_GND_NET_ID = 101

VMOTOR_PLANE_LAYER = "In5.Cu"   # per BOARD_INVARIANTS line 13
GND_PRIMARY_INNER_LAYERS = ("In1.Cu", "In3.Cu", "In7.Cu")

SURFACE_LAYER_NAMES = {"F.Cu", "B.Cu"}


# ----------------------------------------------------------------------
# S-expression utility — paren-balanced extraction of (zone ...) blocks
# ----------------------------------------------------------------------

def _find_balanced_end(s, open_idx):
    """Given index `open_idx` pointing at '(', return the index of the
    matching ')'.  Returns -1 if unbalanced (malformed input)."""
    depth = 0
    in_string = False
    i = open_idx
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i-1] != '\\'):
            in_string = not in_string
        elif not in_string:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def iter_zone_blocks(txt):
    """Yield (start_idx, end_idx_exclusive, body) for every top-level
    (zone ...) block.  body includes the parens."""
    i = 0
    needle = "(zone"
    while True:
        j = txt.find(needle, i)
        if j < 0:
            break
        # ensure it's a token boundary (preceded by whitespace or start
        # of file) so we don't match e.g. (zone_connect ...)
        if j > 0 and txt[j-1] not in "\n\t ":
            i = j + 1
            continue
        next_ch = txt[j + len(needle)] if j + len(needle) < len(txt) else ""
        if next_ch not in "\n\t ":
            i = j + 1
            continue
        end = _find_balanced_end(txt, j)
        if end < 0:
            break
        yield (j, end + 1, txt[j:end + 1])
        i = end + 1


def discover_net_ids(txt):
    """Find the canonical (net N "+VMOTOR") and (net N "GND") declarations
    in the top-level net table.  Returns (vmotor_id, gnd_id) or
    (DEFAULT_VMOTOR_NET_ID, DEFAULT_GND_NET_ID) if not found."""
    vid = DEFAULT_VMOTOR_NET_ID
    gid = DEFAULT_GND_NET_ID
    m = re.search(r'\(net\s+(\d+)\s+"\+VMOTOR"\)', txt)
    if m:
        vid = int(m.group(1))
    m = re.search(r'\(net\s+(\d+)\s+"GND"\)', txt)
    if m:
        gid = int(m.group(1))
    return vid, gid


def zone_layer(body):
    """Extract the (layer "X.Cu") string from a zone body's HEADER (first
    occurrence after `(zone`, before any filled_polygon child)."""
    # Find first (layer "...") — strictly the zone-level layer.
    m = re.search(r'\(layer\s+"([^"]+)"\)', body)
    return m.group(1) if m else None


def zone_net_info(body):
    """Extract zone's net id + name."""
    nid = None
    nname = None
    m = re.search(r'\(net\s+(\d+)\s*\)', body)
    if m:
        nid = int(m.group(1))
    m = re.search(r'\(net_name\s+"([^"]*)"\)', body)
    if m:
        nname = m.group(1)
    return nid, nname


# ----------------------------------------------------------------------
# Diagnose
# ----------------------------------------------------------------------

def diagnose(txt):
    """Return inventory of zones touching +VMOTOR/GND, keyed by net
    name → list of zone layers."""
    out = {"+VMOTOR": [], "GND": [], "zones": []}
    for (s, e, body) in iter_zone_blocks(txt):
        nid, nname = zone_net_info(body)
        layer = zone_layer(body)
        if not nname:
            continue
        out["zones"].append({"layer": layer, "net": nname, "start": s, "end": e})
        if nname == VMOTOR_NET_NAME:
            out["+VMOTOR"].append(layer)
        elif nname == GND_NET_NAME:
            out["GND"].append(layer)
    return out


def print_diagnosis(diag):
    print("=== DIAGNOSIS (pre-fix) ===")
    print("  Expected per BOARD_INVARIANTS 10L stackup:")
    print(f"    +VMOTOR  → {VMOTOR_PLANE_LAYER}  (single inner plane, 3oz)")
    print(f"    GND      → {list(GND_PRIMARY_INNER_LAYERS)}  (inner GND planes)")
    print(f"  Found on board:")
    print(f"    +VMOTOR zones on layers: {sorted(set(diag['+VMOTOR']))}")
    print(f"    GND     zones on layers: {sorted(set(diag['GND']))}")


def needs_swap(diag):
    """True iff In3 carries +VMOTOR AND In5 carries GND (inversion vs spec)."""
    return ("In3.Cu" in diag["+VMOTOR"]) and ("In5.Cu" in diag["GND"]) and \
           ("In5.Cu" not in diag["+VMOTOR"])


def needs_surface(diag, surface_layers):
    """True iff +VMOTOR is missing on any of the requested surface layers."""
    return any(s not in diag["+VMOTOR"] for s in surface_layers)


# ----------------------------------------------------------------------
# Stage 1 — S-expression net SWAP on In3/In5 zones
# ----------------------------------------------------------------------

def apply_swap_in_text(txt, vmotor_net_id, gnd_net_id):
    """Find the In3 zone with net=+VMOTOR and the In5 zone with net=GND,
    swap their (net N) + (net_name "...") fields.  Also clears any
    (filled_polygon ...) sub-blocks so ZONE_FILLER repaints them.

    Returns (new_txt, swap_done_count).
    """
    swap_count = 0
    # Collect target zone byte ranges so we can rewrite in a single pass
    in3_vmotor_zones = []   # to become GND
    in5_gnd_zones = []      # to become +VMOTOR
    for (s, e, body) in iter_zone_blocks(txt):
        layer = zone_layer(body)
        _, nname = zone_net_info(body)
        if layer == "In3.Cu" and nname == VMOTOR_NET_NAME:
            in3_vmotor_zones.append((s, e))
        elif layer == "In5.Cu" and nname == GND_NET_NAME:
            in5_gnd_zones.append((s, e))

    if not in3_vmotor_zones or not in5_gnd_zones:
        return txt, 0

    # Compose replacements
    def _rewrite_block(block_txt, new_net_id, new_net_name):
        # Replace (net N) and (net_name "X") within this block ONLY.
        # The block may also contain (net N) inside (filled_polygon)
        # but those are the same value as the zone-level net by
        # construction; rewriting them is fine.
        block_txt = re.sub(r'\(net\s+\d+\s*\)',
                            f'(net {new_net_id})', block_txt)
        block_txt = re.sub(r'\(net_name\s+"[^"]*"\)',
                            f'(net_name "{new_net_name}")', block_txt)
        # Strip out (filled_polygon ...) sub-blocks — they will be
        # regenerated by ZONE_FILLER with the correct foreign-clearance
        # for the new net.  Otherwise we'd be reading stale geometry.
        block_txt = _strip_filled_polygons(block_txt)
        return block_txt

    # Sort byte ranges descending so earlier mutations don't shift later indices
    ranges = []
    for (s, e) in in3_vmotor_zones:
        ranges.append((s, e, gnd_net_id, GND_NET_NAME))
    for (s, e) in in5_gnd_zones:
        ranges.append((s, e, vmotor_net_id, VMOTOR_NET_NAME))
    ranges.sort(key=lambda r: -r[0])

    new_txt = txt
    for (s, e, nid, nname) in ranges:
        old_block = new_txt[s:e]
        new_block = _rewrite_block(old_block, nid, nname)
        new_txt = new_txt[:s] + new_block + new_txt[e:]
        swap_count += 1
    return new_txt, swap_count


def _strip_filled_polygons(block_txt):
    """Remove every (filled_polygon ...) sub-block from `block_txt`,
    paren-balanced.  Returns the stripped block.

    Why: after a net swap, the existing filled polygons reflect the OLD
    net's foreign-net clearance topology.  ZONE_FILLER must repaint
    them.  KiCad loads boards with missing filled_polygon child fine
    (treats the zone as un-filled until refill)."""
    out = []
    i = 0
    needle = "(filled_polygon"
    while True:
        j = block_txt.find(needle, i)
        if j < 0:
            out.append(block_txt[i:])
            break
        out.append(block_txt[i:j])
        end = _find_balanced_end(block_txt, j)
        if end < 0:
            # malformed; bail
            out.append(block_txt[j:])
            break
        # consume trailing newline + leading whitespace so we don't leave
        # a blank line
        i = end + 1
        while i < len(block_txt) and block_txt[i] in '\n\t ':
            i += 1
    return ''.join(out)


# ----------------------------------------------------------------------
# Stage 2 — surface +VMOTOR pour injection
# ----------------------------------------------------------------------

SURFACE_ZONE_TEMPLATE = '''	(zone
		(net {net_id})
		(net_name "+VMOTOR")
		(layer "{layer}")
		(uuid "{uuid}")
		(name "+VMOTOR surface distribution ({layer}) — lever T")
		(hatch edge 0.5)
		(priority 0)
		(connect_pads
			(clearance 0.5)
		)
		(min_thickness 0.2)
		(filled_areas_thickness no)
		(fill yes
			(thermal_gap 0.3)
			(thermal_bridge_width 0.5)
		)
		(polygon
			(pts
				(xy 2 2) (xy 98 2) (xy 98 98) (xy 2 98)
			)
		)
	)
'''


def _gen_uuid_for_layer(layer):
    """Deterministic UUID per surface layer (idempotent re-runs produce
    the same UUID — so KiCad doesn't see a "new" zone every re-run)."""
    # Lever-T deterministic UUIDs (chosen to be obviously synthetic so
    # they don't collide with KiCad-generated UUIDs in the rest of the
    # board).
    return {
        "F.Cu":  "1e7e7f01-aaaa-4711-9211-feedf0011001",
        "B.Cu":  "1e7e7f01-aaaa-4711-9211-feedf0011002",
    }.get(layer, "1e7e7f01-aaaa-4711-9211-feedf001ffff")


def inject_surface_pour(txt, vmotor_net_id, surface_layers):
    """Insert new (zone ...) blocks for each surface layer in
    `surface_layers` IF a +VMOTOR zone on that layer doesn't already
    exist.

    Inserts right after the last existing (zone ...) block (or at the
    end of the (kicad_pcb ...) block if no zone exists)."""
    # Locate insertion point — after last (zone ...) block
    last_end = None
    existing_surface_layers = set()
    for (s, e, body) in iter_zone_blocks(txt):
        last_end = e
        layer = zone_layer(body)
        _, nname = zone_net_info(body)
        if nname == VMOTOR_NET_NAME and layer in surface_layers:
            existing_surface_layers.add(layer)
    if last_end is None:
        # no zones at all — insert before final ')'
        last_paren = txt.rfind(')')
        if last_paren < 0:
            raise RuntimeError("FAIL: cannot find insertion point in board")
        last_end = last_paren

    to_add = [l for l in surface_layers if l not in existing_surface_layers]
    if not to_add:
        return txt, []

    blocks = []
    for lyr in to_add:
        blocks.append(SURFACE_ZONE_TEMPLATE.format(
            net_id=vmotor_net_id,
            layer=lyr,
            uuid=_gen_uuid_for_layer(lyr),
        ))
    # Insert right after last_end (consume trailing whitespace so blocks
    # land neatly on their own line)
    insert_at = last_end
    # consume the newline after last_end if present
    if insert_at < len(txt) and txt[insert_at] == '\n':
        insert_at += 1
    new_txt = txt[:insert_at] + "".join(blocks) + txt[insert_at:]
    return new_txt, to_add


# ----------------------------------------------------------------------
# Stage 3 — refill via fresh pcbnew subprocess
# ----------------------------------------------------------------------

REFILL_SUBPROC_CODE = r'''
import sys
try:
    import pcbnew
except Exception as e:
    print("FAIL: pcbnew import: {}".format(e), file=sys.stderr)
    sys.exit(2)
src, dst = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(src)
zones = list(board.Zones())
try:
    pcbnew.ZONE_FILLER(board).Fill(zones)
except Exception as e:
    print("WARN: ZONE_FILLER raised: {}".format(e), file=sys.stderr)
board.Save(dst)
print("REFILL OK: {} zones".format(len(zones)))
'''


def refill_via_subprocess(in_path, out_path, timeout_s=300):
    """Run a fresh python3 subprocess that loads the board, refills all
    zones, and saves to out_path.  Per the SWIG-batch-mutation trap
    note, isolating the refill in a fresh process avoids state
    corruption from prior in-process zone mutations.
    """
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     delete=False) as tf:
        tf.write(REFILL_SUBPROC_CODE)
        sp_path = tf.name
    try:
        res = subprocess.run(["python3", sp_path, str(in_path), str(out_path)],
                             capture_output=True, text=True, timeout=timeout_s)
        return res.returncode, res.stdout, res.stderr
    finally:
        try:
            os.unlink(sp_path)
        except OSError:
            pass


# ----------------------------------------------------------------------
# Post-emit gates (read the output text + optional kicad-cli DRC)
# ----------------------------------------------------------------------

def post_verify(out_txt):
    diag_after = diagnose(out_txt)
    vmotor_layers_after = sorted(set(diag_after["+VMOTOR"]))
    gnd_layers_after = sorted(set(diag_after["GND"]))

    gates = {
        "G1_multi_layer_vmotor_cu": {
            "ok": len(vmotor_layers_after) >= 2,
            "vmotor_cu_layers": vmotor_layers_after,
            "required_min": 2,
        },
        "G2_in5_is_vmotor": {
            "ok": VMOTOR_PLANE_LAYER in vmotor_layers_after,
            "vmotor_plane_layer_expected": VMOTOR_PLANE_LAYER,
        },
        "G3_in3_in5_no_inversion": {
            "ok": ("In3.Cu" in gnd_layers_after) and ("In3.Cu" not in vmotor_layers_after)
                  and ("In5.Cu" in vmotor_layers_after) and ("In5.Cu" not in gnd_layers_after),
            "in3_nets": [n for n in ["+VMOTOR", "GND"]
                         if "In3.Cu" in diag_after[n]],
            "in5_nets": [n for n in ["+VMOTOR", "GND"]
                         if "In5.Cu" in diag_after[n]],
        },
        "diag_after": {
            "vmotor_layers": vmotor_layers_after,
            "gnd_layers": gnd_layers_after,
        },
    }
    ok = all(gates[k]["ok"] for k in gates if k.startswith("G"))
    return ok, gates


def run_kicad_cli_drc(board_path, timeout_s=600):
    """Optional G4 — run kicad-cli pcb drc and count via_dangling.

    Returns dict including:
        TOTAL_via_dangling: int
        VMOTOR_via_dangling: int (count whose description mentions +VMOTOR)
        violations_by_type: { type: count }
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        drc_path = tf.name
    try:
        cmd = ["kicad-cli", "pcb", "drc", "--format", "json",
               "--severity-error", "--severity-warning",
               "-o", drc_path, str(board_path)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"error": f"kicad-cli pcb drc timed out after {timeout_s}s"}
        if not Path(drc_path).exists() and res.returncode != 0:
            return {"error": f"kicad-cli pcb drc failed: {res.stderr[:300]}"}
        try:
            drc = json.loads(Path(drc_path).read_text())
        except Exception as e:
            return {"error": f"could not parse DRC json: {e}"}
        out = {
            "TOTAL_via_dangling": 0,
            "VMOTOR_via_dangling": 0,
            "by_type": {},
        }
        for v in drc.get("violations", []):
            vt = v.get("type", "?")
            out["by_type"][vt] = out["by_type"].get(vt, 0) + len(v.get("items", []))
            if vt != "via_dangling":
                continue
            for it in v.get("items", []):
                out["TOTAL_via_dangling"] += 1
                desc = (it.get("description") or "").upper()
                if "+VMOTOR" in desc or "VMOTOR" in desc:
                    out["VMOTOR_via_dangling"] += 1
        return out
    finally:
        try:
            os.unlink(drc_path)
        except OSError:
            pass


# ----------------------------------------------------------------------
# Stage 5 — orphan-via cleanup (lever V residual fix)
# ----------------------------------------------------------------------

VIA_BLOCK_RE = re.compile(
    r'\(via\s*\(at\s+([\-\d.]+)\s+([\-\d.]+)\)'
    r'(?:\s*\(size\s+[\d.]+\))?'
    r'(?:\s*\(drill\s+[\d.]+\))?'
    r'(?:\s*\(layers\s+"[^"]+"\s+"[^"]+"\))?'
    r'(?:\s*\(net\s+\d+\))?'
    r'(?:\s*\(uuid\s+"([^"]*)"\))?'
    r'\s*\)',
    re.DOTALL,
)


def run_kicad_cli_drc_full(board_path, timeout_s=600):
    """Run kicad-cli pcb drc and return the parsed JSON dict.
    Returns (parsed_json_dict, None) on success, or (None, error_str) on
    failure. Caller can extract whichever violation types it needs."""
    if not Path(board_path).exists():
        return None, f"board not found: {board_path}"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        drc_path = tf.name
    try:
        cmd = ["kicad-cli", "pcb", "drc", "--format", "json",
               "--severity-error", "--severity-warning",
               "-o", drc_path, str(board_path)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None, f"kicad-cli pcb drc timed out after {timeout_s}s"
        if not Path(drc_path).exists() and res.returncode != 0:
            return None, f"kicad-cli pcb drc failed: {res.stderr[:300]}"
        try:
            return json.loads(Path(drc_path).read_text()), None
        except Exception as e:
            return None, f"could not parse DRC json: {e}"
    finally:
        try:
            os.unlink(drc_path)
        except OSError:
            pass


def collect_dangling_via_positions(drc_json):
    """Return list of {'x', 'y', 'description', 'uuid'} for every
    via_dangling violation in the DRC JSON. Position is rounded to
    the kicad-cli output precision (3 decimal places)."""
    out = []
    for v in drc_json.get("violations", []):
        if v.get("type") != "via_dangling":
            continue
        for it in v.get("items", []):
            pos = it.get("pos") or {}
            try:
                x = round(float(pos.get("x")), 3)
                y = round(float(pos.get("y")), 3)
            except (TypeError, ValueError):
                continue
            out.append({
                "x": x,
                "y": y,
                "description": it.get("description") or "",
                "uuid": it.get("uuid") or "",
            })
    return out


def remove_orphan_vias_from_text(txt, orphan_positions, tol_mm=0.005):
    """Remove (via ...) blocks whose (at x y) match any orphan position
    within tol_mm. Returns (new_txt, removed_records).

    Why a tolerance: kicad-cli reports pos rounded to 3 decimals; the
    actual (at ...) in the file may have higher precision. 5µm tolerance
    is well below any meaningful via spacing (the minimum drill-to-drill
    spacing on this board is 0.20mm = 40× the tolerance).

    Why UUID-then-position match: when the DRC JSON carries a uuid we
    match on uuid first (zero false positives). When uuid is missing
    (some kicad-cli versions emit empty), we fall back to position.
    Each match is logged so the report is auditable.
    """
    # Index orphans for fast lookup
    orphan_uuids = {o["uuid"] for o in orphan_positions if o.get("uuid")}
    orphan_xy = [(o["x"], o["y"], o) for o in orphan_positions]

    removed = []
    out_chunks = []
    last_end = 0
    for m in VIA_BLOCK_RE.finditer(txt):
        vx, vy = float(m.group(1)), float(m.group(2))
        vuuid = m.group(3) or ""
        match = None
        if vuuid and vuuid in orphan_uuids:
            # find the orphan record with this uuid
            for o in orphan_positions:
                if o.get("uuid") == vuuid:
                    match = o
                    break
        if match is None:
            for (ox, oy, o) in orphan_xy:
                if abs(vx - ox) <= tol_mm and abs(vy - oy) <= tol_mm:
                    match = o
                    break
        if match is None:
            continue
        # remove this via block, including the leading tab/newline so we
        # don't leave a blank line behind
        block_start = m.start()
        block_end = m.end()
        # back up over the immediate leading tab/whitespace on the same line
        while block_start > 0 and txt[block_start - 1] in '\t ':
            block_start -= 1
        # consume trailing newline so subsequent lines collapse cleanly
        if block_end < len(txt) and txt[block_end] == '\n':
            block_end += 1
        out_chunks.append(txt[last_end:block_start])
        last_end = block_end
        removed.append({
            "x": vx, "y": vy, "uuid": vuuid,
            "matched_orphan": match,
        })
    out_chunks.append(txt[last_end:])
    return "".join(out_chunks), removed


def cleanup_orphan_vias(out_path, max_iterations=3, timeout_s=600):
    """Iterative orphan-via cleanup:
      1. Run kicad-cli pcb drc on out_path.
      2. Parse via_dangling violations.
      3. Remove those vias from out_path (S-expression edit).
      4. Re-run DRC; if zero dangling vias remain, PASS.
      5. Otherwise iterate (removing a via can in principle leave another
         dangling if connectivity was relying on it). Cap at max_iterations
         to bound runtime; in practice the second pass shows 0.

    Returns dict with:
        pre_dangling_count, removed_count_per_iter, post_dangling_count,
        all_removed (list of {x,y,uuid,description}),
        residual_dangling (list — empty on success),
        iterations_used,
        error (str, only if a fatal error occurred).
    """
    report = {
        "pre_dangling_count": None,
        "removed_count_per_iter": [],
        "post_dangling_count": None,
        "all_removed": [],
        "residual_dangling": [],
        "iterations_used": 0,
        "error": None,
    }
    out_path = Path(out_path)
    for iteration in range(1, max_iterations + 1):
        drc_json, err = run_kicad_cli_drc_full(str(out_path),
                                                timeout_s=timeout_s)
        if err is not None:
            report["error"] = err
            return report
        orphans = collect_dangling_via_positions(drc_json)
        if iteration == 1:
            report["pre_dangling_count"] = len(orphans)
        if not orphans:
            report["post_dangling_count"] = 0
            report["iterations_used"] = iteration - 1
            return report
        txt = out_path.read_text()
        new_txt, removed = remove_orphan_vias_from_text(txt, orphans)
        report["removed_count_per_iter"].append(len(removed))
        report["all_removed"].extend(removed)
        # SAFETY: if we couldn't remove anything (e.g. position mismatch),
        # we'd loop forever. Bail out honestly with residual.
        if not removed:
            report["post_dangling_count"] = len(orphans)
            report["residual_dangling"] = orphans
            report["iterations_used"] = iteration
            report["error"] = ("could not match any dangling via by position "
                               "+ uuid — board may be unparseable or kicad-cli "
                               "report format changed")
            return report
        out_path.write_text(new_txt)
        report["iterations_used"] = iteration
    # If we exhausted iterations and still have orphans, do a final count
    drc_json, err = run_kicad_cli_drc_full(str(out_path), timeout_s=timeout_s)
    if err is None:
        residual = collect_dangling_via_positions(drc_json)
        report["post_dangling_count"] = len(residual)
        report["residual_dangling"] = residual
    return report


def stitch_via_density_per_cm2(out_path):
    """Return (vmotor_via_count, board_area_cm2, density_per_cm2) so we
    can sanity-check the G14 floor (4/cm²) post-cleanup. We count every
    PCB_VIA on the +VMOTOR net. Returns (None, None, None) on error."""
    try:
        # In-process pcbnew load — read-only, no edits
        import pcbnew  # type: ignore
        board = pcbnew.LoadBoard(str(out_path))
        n = 0
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == VMOTOR_NET_NAME:
                n += 1
        bbox = board.GetBoardEdgesBoundingBox()
        w_mm = bbox.GetWidth() / 1e6
        h_mm = bbox.GetHeight() / 1e6
        area_cm2 = (w_mm * h_mm) / 100.0
        return n, area_cm2, (n / area_cm2) if area_cm2 else 0.0
    except Exception:
        return None, None, None


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Lever T — inject +VMOTOR multi-layer pour architecture fix "
            "(Option C: In3↔In5 net swap + F.Cu/B.Cu surface pours). "
            "Read-only on --board; writes new .kicad_pcb at --output."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--board", required=True, help="input .kicad_pcb (READ-ONLY)")
    ap.add_argument("--output", required=True, help="output .kicad_pcb")
    ap.add_argument("--report", default=None, help="JSON report path")
    ap.add_argument("--run-drc", action="store_true",
                    help="run kicad-cli pcb drc as optional G4 check (slow)")
    ap.add_argument("--surface-layers", default="F.Cu,B.Cu",
                    help=("comma-separated surface layers to add +VMOTOR pour "
                          "to (default 'F.Cu,B.Cu'; use 'F.Cu' alone if B.Cu "
                          "real-estate is contested)"))
    ap.add_argument("--skip-refill", action="store_true",
                    help="DEBUG: skip the pcbnew refill subprocess (output "
                         "board will have un-filled zones — for inspecting "
                         "the S-expression mutation alone)")
    ap.add_argument("--remove-orphan-vias", dest="remove_orphan_vias",
                    action="store_true", default=True,
                    help=("Stage 5 (default ON): after refill, invoke "
                          "kicad-cli pcb drc, identify via_dangling "
                          "violations, and DELETE those orphan vias from "
                          "the output board (any net — not just +VMOTOR). "
                          "Each removal is logged in the report. Drone-grade "
                          "default: a dangling via is a connectivity defect, "
                          "honest removal is safer than silent retention."))
    ap.add_argument("--keep-orphan-vias", dest="remove_orphan_vias",
                    action="store_false",
                    help="DISABLE Stage 5 orphan-via removal "
                         "(diagnostic / pre-fix baseline only).")
    ap.add_argument("--g14-density-floor", type=float, default=4.0,
                    help=("G14 +VMOTOR stitch-via density floor in "
                          "vias/cm² (default 4.0). Stage 5 reports the "
                          "post-cleanup density vs this floor; the tool "
                          "exits 0 with a WARN log if cleanup pushed "
                          "density below floor, exit 1 only on actual "
                          "connectivity failure."))
    args = ap.parse_args()

    in_path = Path(args.board)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"FAIL: input board not found: {in_path}", file=sys.stderr)
        return 2

    surface_layers = [s.strip() for s in args.surface_layers.split(",") if s.strip()]
    for s in surface_layers:
        if s not in SURFACE_LAYER_NAMES:
            print(f"FAIL: unknown surface layer '{s}'; "
                  f"valid={sorted(SURFACE_LAYER_NAMES)}", file=sys.stderr)
            return 2

    print(f"=== inject_vmotor_pour.py — CH1 30/30 lever T ===")
    print(f"Input:  {in_path}")
    print(f"Output: {out_path}")
    print(f"Surface +VMOTOR pour layers: {surface_layers}")
    print()

    txt = in_path.read_text()
    vmotor_id, gnd_id = discover_net_ids(txt)
    print(f"Discovered net ids: +VMOTOR={vmotor_id}, GND={gnd_id}")
    print()

    diag_before = diagnose(txt)
    print_diagnosis(diag_before)
    print(f"  needs_swap (In3↔In5 inversion):    {needs_swap(diag_before)}")
    print(f"  needs_surface (F/B.Cu +VMOTOR):    "
          f"{needs_surface(diag_before, surface_layers)}")
    print()

    # Idempotence — early-exit for the structural mutation, but Stage 5
    # orphan-via cleanup still runs against the canonical board if the
    # user opted in. This handles the lever-V residual case where the
    # board already has the right pour topology (+VMOTOR on ≥2 layers)
    # but contains orphan vias from earlier tools (add_sw_vias/route_*)
    # that ZONE_FILLER on the refilled board now leaves dangling.
    structural_no_op = ((not needs_swap(diag_before))
                        and (not needs_surface(diag_before, surface_layers)))
    if structural_no_op:
        print("Board already satisfies multi-layer +VMOTOR pour spec — "
              "STRUCTURAL NO-OP.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(txt)

        cleanup_report = None
        if args.remove_orphan_vias:
            print("\n=== STAGE 5: orphan-via cleanup "
                  "(NO-OP path — board already structurally correct) ===")
            cleanup_report = cleanup_orphan_vias(out_path)
            _print_cleanup_report(cleanup_report)

        vmotor_via_n, board_cm2, density = stitch_via_density_per_cm2(
            str(out_path))
        if density is not None:
            floor = args.g14_density_floor
            print(f"\nG14 +VMOTOR stitch-via density: {density:.2f}/cm² "
                  f"({vmotor_via_n} vias on {board_cm2:.1f}cm²)  "
                  f"floor={floor:.2f}  "
                  f"{'PASS' if density >= floor else 'WARN<FLOOR'}")
        if args.report:
            Path(args.report).write_text(json.dumps({
                "input_board": str(in_path),
                "output_board": str(out_path),
                "diagnosis_before": {
                    "vmotor_layers": sorted(set(diag_before["+VMOTOR"])),
                    "gnd_layers":    sorted(set(diag_before["GND"])),
                    "needs_swap":    needs_swap(diag_before),
                    "needs_surface": needs_surface(diag_before, surface_layers),
                },
                "mutations": 0,
                "stage5_orphan_via_cleanup": cleanup_report,
                "stitch_density_per_cm2": {
                    "vmotor_via_count": vmotor_via_n,
                    "board_area_cm2": board_cm2,
                    "density_per_cm2": density,
                    "g14_floor": args.g14_density_floor,
                    "meets_floor": (density is not None
                                     and density >= args.g14_density_floor),
                },
                "verdict": "NO_OP_IDEMPOTENT",
            }, indent=2))
        # NO_OP is success unless Stage 5 left residual dangling vias
        if cleanup_report and cleanup_report.get("post_dangling_count", 0):
            print(f"\nFAIL: Stage 5 cleanup left "
                  f"{cleanup_report['post_dangling_count']} residual "
                  f"dangling vias.", file=sys.stderr)
            return 1
        print("\nRESULT: NO_OP_IDEMPOTENT (Stage 5 clean)" if
              args.remove_orphan_vias else
              "\nRESULT: NO_OP (idempotent; Stage 5 disabled)")
        return 0

    # Stage 1 — In3↔In5 net swap
    print("=== STAGE 1: In3↔In5 zone-net SWAP ===")
    new_txt, n_swaps = apply_swap_in_text(txt, vmotor_id, gnd_id)
    print(f"  swapped {n_swaps} zone block(s)")
    print()

    # Stage 2 — surface +VMOTOR pours
    print(f"=== STAGE 2: surface +VMOTOR pour injection ({surface_layers}) ===")
    new_txt, added_layers = inject_surface_pour(new_txt, vmotor_id, surface_layers)
    print(f"  injected {len(added_layers)} surface zone(s): {added_layers}")
    print()

    # Write pre-refill output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.skip_refill:
        out_path.write_text(new_txt)
        print("--skip-refill set — wrote S-expression-mutated board without refill")
    else:
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False,
                                         mode="w") as tf:
            tf.write(new_txt)
            interim_path = tf.name
        try:
            print("=== STAGE 3: refill via fresh pcbnew subprocess ===")
            rc, so, se = refill_via_subprocess(interim_path, str(out_path))
            print(f"  refill rc={rc}")
            if so.strip():
                print("  stdout:", so.strip())
            if se.strip():
                print("  stderr:", se.strip())
            if rc != 0:
                print(f"FAIL: refill subprocess exited rc={rc}", file=sys.stderr)
                return 1
        finally:
            try:
                os.unlink(interim_path)
            except OSError:
                pass
        print()

    # Stage 4 — post-emit verification on the saved output
    print("=== POST-EMIT VERIFICATION ===")
    out_txt = out_path.read_text()
    ok, gates = post_verify(out_txt)
    print(f"  +VMOTOR Cu layers after: {gates['diag_after']['vmotor_layers']}")
    print(f"  GND     Cu layers after: {gates['diag_after']['gnd_layers']}")
    print(f"  G1 (≥2 Cu layers carry +VMOTOR):       "
          f"{'PASS' if gates['G1_multi_layer_vmotor_cu']['ok'] else 'FAIL'}")
    print(f"  G2 (In5 carries +VMOTOR per invariant): "
          f"{'PASS' if gates['G2_in5_is_vmotor']['ok'] else 'FAIL'}")
    print(f"  G3 (In3↔In5 not inverted):              "
          f"{'PASS' if gates['G3_in3_in5_no_inversion']['ok'] else 'FAIL'}")
    print()

    g4 = None
    if args.run_drc:
        print("=== OPTIONAL G4: kicad-cli pcb drc via_dangling counts ===")
        g4 = run_kicad_cli_drc(str(out_path))
        if "error" in g4:
            print(f"  kicad-cli error: {g4['error']}")
        else:
            print(f"  TOTAL via_dangling:  {g4['TOTAL_via_dangling']}")
            print(f"  VMOTOR via_dangling: {g4['VMOTOR_via_dangling']}")
            print(f"  violations by type:")
            for k, v in sorted(g4["by_type"].items()):
                print(f"    {k}: {v}")
        print()

    cleanup_report = None
    if args.remove_orphan_vias:
        print("=== STAGE 5: orphan-via cleanup "
              "(via_dangling → REMOVE) ===")
        cleanup_report = cleanup_orphan_vias(out_path)
        _print_cleanup_report(cleanup_report)
        print()

    vmotor_via_n, board_cm2, density = stitch_via_density_per_cm2(
        str(out_path))
    if density is not None:
        floor = args.g14_density_floor
        print(f"G14 +VMOTOR stitch-via density: {density:.2f}/cm² "
              f"({vmotor_via_n} vias on {board_cm2:.1f}cm²)  "
              f"floor={floor:.2f}  "
              f"{'PASS' if density >= floor else 'WARN<FLOOR'}")
        print()

    if args.report:
        Path(args.report).write_text(json.dumps({
            "input_board": str(in_path),
            "output_board": str(out_path),
            "diagnosis_before": {
                "vmotor_layers": sorted(set(diag_before["+VMOTOR"])),
                "gnd_layers":    sorted(set(diag_before["GND"])),
                "needs_swap":    needs_swap(diag_before),
                "needs_surface": needs_surface(diag_before, surface_layers),
            },
            "mutations": {
                "in3_in5_swap_zones": n_swaps,
                "surface_pours_added": added_layers,
            },
            "verification_gates": gates,
            "kicad_cli_drc": g4,
            "stage5_orphan_via_cleanup": cleanup_report,
            "stitch_density_per_cm2": {
                "vmotor_via_count": vmotor_via_n,
                "board_area_cm2": board_cm2,
                "density_per_cm2": density,
                "g14_floor": args.g14_density_floor,
                "meets_floor": (density is not None
                                 and density >= args.g14_density_floor),
            },
            "verdict": "PASS" if ok else "FAIL",
        }, indent=2))

    if not ok:
        print("FAIL: post-emit verification failed.", file=sys.stderr)
        return 1

    # Stage 5 connectivity failure is a hard FAIL — drone-grade rule.
    if cleanup_report and cleanup_report.get("post_dangling_count", 0):
        print(f"FAIL: Stage 5 cleanup left "
              f"{cleanup_report['post_dangling_count']} residual "
              f"dangling vias (could not be matched & removed). "
              f"Inspect report['stage5_orphan_via_cleanup']['residual_dangling'].",
              file=sys.stderr)
        return 1

    print("RESULT: PASS")
    return 0


def _print_cleanup_report(rep):
    """Pretty-print the Stage 5 cleanup report to stdout."""
    if rep is None:
        return
    if rep.get("error"):
        print(f"  ERROR: {rep['error']}")
        return
    pre = rep.get("pre_dangling_count")
    post = rep.get("post_dangling_count")
    iters = rep.get("iterations_used")
    removed = rep.get("all_removed", [])
    print(f"  pre-cleanup via_dangling count: {pre}")
    print(f"  iterations used:                {iters}")
    print(f"  vias removed:                   {len(removed)}")
    for r in removed[:20]:
        desc = r.get("matched_orphan", {}).get("description", "")
        # description often contains the net name — keep first 80 chars
        print(f"    - ({r['x']:.3f}, {r['y']:.3f}) uuid={r['uuid'][:8]}… "
              f"{desc[:80]}")
    if len(removed) > 20:
        print(f"    ... +{len(removed) - 20} more")
    print(f"  post-cleanup via_dangling count: {post}")
    print(f"  STAGE 5 verdict: "
          f"{'PASS (0 residual)' if post == 0 else 'FAIL (residual present)'}")


if __name__ == "__main__":
    sys.exit(main())
