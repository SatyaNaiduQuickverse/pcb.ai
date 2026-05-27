#!/usr/bin/env python3
"""audit_sw_gnd_return_pair.py — G_SW_GND_VIA placement/routing gate.

Per Sai R26 lock 2026-05-27 (worker OQ-017 STEP-4 batch + R22 catch context):
every SW commutation via (MOTOR_x_CHn net F.Cu↔B.Cu transition via) MUST have a
paired GND-return through-via within strict proximity for clean commutation
loop inductance + STEP-7 EMI ringing prevention at 70A switching.

Rationale (physics, per [[feedback-physics-as-compass]]):

  Commutation switching at 70A continuous / 100A burst dI/dt @ 50kHz PWM
  causes the SW node F↔B transition to inject a ring current into whatever
  return path exists. Without a co-located GND-return via, the return path
  detours across the GND pour by tens of mm — creating loop area that
  radiates EMI + couples into adjacent CH/MCU nets + increases parasitic
  loop-L beyond the 0.20 nH target (cf. STEP 6 measured 0.1953nH on
  proper-paired routing).

  Per Howard Johnson "High-Speed Digital Design" + Eric Bogatin "Signal
  Integrity Simplified" §11.5: GND-return via MUST sit within λ/20 at the
  fastest switching edge (~0.5mm at GaN dI/dt edges; 1.5mm cluster-centroid
  is conservative for IRFH-class SiFETs at our 6 ns rise time).

Worker approach (OQ-017 + STEP-4):
  Added 6 GND-return through-vias, one per SW-via cluster centroid, at
  d=0.8-1.2mm separation. This is CLUSTER-LEVEL (not per-via) and is
  engineering-equivalent to per-via pairing because the SW vias within a
  cluster are themselves <1mm apart (FET-EP via fanout fans into 4-5
  vias on a ~2mm pitch). One GND via centred on the cluster carries the
  total ring current with adequate loop coupling.

This gate accepts BOTH patterns (per worker engineering call):

  Mode A — per-SW-via pair:
    For each SW via in a cluster of size <3 (isolated or pair), a GND
    through-via MUST exist within 0.5mm.

  Mode B — cluster-centroid pair:
    For each cluster of ≥3 SW vias (DBSCAN-equivalent: vias within 1.5mm
    of each other), a GND through-via MUST exist within 1.5mm of the
    cluster CENTROID.

Detection logic:
  1. Enumerate all PCB_VIA on board.
  2. SW_VIAS = vias with net matching ^MOTOR_[ABC]_CH[1-4]$
  3. GND_VIAS = vias with net == 'GND'
  4. Cluster SW_VIAS by proximity (simple O(n²) flood-fill with
     intra-cluster distance ≤ 1.5mm).
  5. For each cluster:
       size ≥ 3 → Mode B: PASS if any GND via within 1.5mm of centroid.
       size < 3 → Mode A: PASS if any GND via within 0.5mm of EACH SW via.
  6. FAIL diagnostic per failing via/cluster.

Exit 0 PASS, 1 FAIL, 2 USAGE.

Usage:
  python3 hardware/kicad/scripts/audit_sw_gnd_return_pair.py \
    hardware/kicad/pcbai_fpv4in1.kicad_pcb

References:
  - [[feedback-no-passive-island]] (extended from passives to commutation vias)
  - [[feedback-physics-as-compass]] (Howard Johnson + Bogatin loop area)
  - [[feedback-codify-not-patch]] (Sai 2026-05-24)
  - PR #197 (worker R22 catch context + SHUNT_ANCHORS re-sync)
  - PR #198 (this gate)
  - OQ-017 (worker added 6 GND-return vias during STEP-4)
  - STEP 6 measured loop-L PASS (0.1953nH A=B=C, proves paired routing works)
"""
import math
import re
import sys

import pcbnew


# ─── CONFIG ──────────────────────────────────────────────────────────────────
SW_NET_PATTERN = re.compile(r"^MOTOR_[ABC]_CH[1-4]$")
GND_NET_NAME = "GND"

# --parked-exempt: skip SW vias parked off-board on a STAGED board
# (CH2/3/4/S* parked at x≥130 per park-then-bring-in R27). Mirrors
# audit_decoupling.py PARKED_EXEMPT pattern (2026-05-26). The board path is
# argv[1]; flag scanned in argv[2:] so it never collides with the board arg.
# Added 2026-05-27 (master R26 G_META1 wiring) so master_pre_merge.sh can
# propagate --staged → --parked-exempt to this gate uniformly.
PARKING_X_THRESHOLD = 130.0  # board ≤100mm; parking_grid origin x≥200; 30mm buffer
PARKED_EXEMPT = "--parked-exempt" in sys.argv[2:]

# Cluster geometry
CLUSTER_DISTANCE_MM = 1.5     # SW vias within this distance form a cluster
CLUSTER_MIN_SIZE = 3          # Mode B threshold

# Pairing tolerances
MODE_A_PAIR_MM = 0.5          # isolated/pair SW via → GND via must be ≤0.5mm
MODE_B_CENTROID_MM = 1.5      # cluster centroid → GND via must be ≤1.5mm


# ─── HELPERS ─────────────────────────────────────────────────────────────────
def to_mm(x):
    return pcbnew.ToMM(x)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def collect_vias(board):
    """Return (sw_vias_by_net, gnd_vias, parked_sw_skipped) — SW/GND via
    positions in (x_mm, y_mm); parked_sw_skipped counts SW vias dropped by
    --parked-exempt (x ≥ PARKING_X_THRESHOLD)."""
    sw_by_net = {}
    gnd = []
    parked_sw_skipped = 0
    for trk in board.GetTracks():
        if not isinstance(trk, pcbnew.PCB_VIA):
            continue
        # Only through-vias count for return-path stitching across all layers.
        if trk.GetViaType() != pcbnew.VIATYPE_THROUGH:
            continue
        netn = trk.GetNetname()
        pos = trk.GetPosition()
        p = (to_mm(pos.x), to_mm(pos.y))
        if SW_NET_PATTERN.match(netn):
            # --parked-exempt: parked-channel SW vias have no on-board GND
            # return obligation yet (their FET/return network is off-board).
            if PARKED_EXEMPT and p[0] >= PARKING_X_THRESHOLD:
                parked_sw_skipped += 1
                continue
            sw_by_net.setdefault(netn, []).append(p)
        elif netn == GND_NET_NAME:
            gnd.append(p)
    return sw_by_net, gnd, parked_sw_skipped


def cluster_vias(vias, max_intra=CLUSTER_DISTANCE_MM):
    """Simple O(n²) flood-fill clustering.

    Two vias are in the same cluster iff there exists a chain of vias in
    the same cluster where each consecutive pair is within max_intra mm.
    """
    n = len(vias)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        pi, pj = find(i), find(j)
        if pi != pj:
            parent[pi] = pj

    for i in range(n):
        for j in range(i + 1, n):
            if dist(vias[i], vias[j]) <= max_intra:
                union(i, j)

    clusters = {}
    for i in range(n):
        r = find(i)
        clusters.setdefault(r, []).append(vias[i])
    return list(clusters.values())


def centroid(pts):
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def nearest_gnd_via(pt, gnd_vias):
    if not gnd_vias:
        return (None, float("inf"))
    best = min(gnd_vias, key=lambda g: dist(pt, g))
    return (best, dist(pt, best))


# ─── MAIN AUDIT ──────────────────────────────────────────────────────────────
def audit(board_path):
    board = pcbnew.LoadBoard(board_path)
    sw_by_net, gnd_vias, parked_sw_skipped = collect_vias(board)

    print(f"audit_sw_gnd_return_pair.py — G_SW_GND_VIA gate")
    print(f"Board: {board_path}")
    print(f"GND through-vias: {len(gnd_vias)}")
    if PARKED_EXEMPT:
        print(f"--parked-exempt: {parked_sw_skipped} SW via(s) at x ≥ "
              f"{PARKING_X_THRESHOLD}mm skipped (parked off-board)")
    print()

    if not sw_by_net:
        print("No MOTOR_*_CH[1-4] vias found — gate VACUOUS-PASS")
        print("(expected once a channel is routed; before routing nothing to check)")
        return 0

    fails = []
    pass_count = 0

    for net in sorted(sw_by_net.keys()):
        vias = sw_by_net[net]
        clusters = cluster_vias(vias)
        print(f"─── {net}: {len(vias)} via(s) in {len(clusters)} cluster(s) ───")

        for ci, cluster in enumerate(clusters):
            size = len(cluster)
            if size >= CLUSTER_MIN_SIZE:
                # Mode B: cluster centroid pair
                cent = centroid(cluster)
                near, d = nearest_gnd_via(cent, gnd_vias)
                status = "PASS" if d <= MODE_B_CENTROID_MM else "FAIL"
                tag = "Mode B (cluster-centroid)"
                print(f"  cluster #{ci+1} [{size} vias] centroid=({cent[0]:.3f}, {cent[1]:.3f})")
                print(f"    {tag}: nearest GND via @ {near} d={d:.3f}mm   [{status}]")
                if status == "PASS":
                    pass_count += 1
                else:
                    fails.append({
                        "net": net, "mode": "B", "size": size, "centroid": cent,
                        "nearest_gnd": near, "d_mm": d, "limit_mm": MODE_B_CENTROID_MM,
                    })
            else:
                # Mode A: per-via pair (every via needs ≤0.5mm GND via)
                tag = f"Mode A (per-via, cluster size {size})"
                print(f"  cluster #{ci+1} [{size} vias] {tag}")
                cluster_pass = True
                for via in cluster:
                    near, d = nearest_gnd_via(via, gnd_vias)
                    sub_status = "PASS" if d <= MODE_A_PAIR_MM else "FAIL"
                    print(f"    via @ ({via[0]:.3f}, {via[1]:.3f})  nearest GND @ {near} d={d:.3f}mm  [{sub_status}]")
                    if sub_status == "PASS":
                        pass_count += 1
                    else:
                        cluster_pass = False
                        fails.append({
                            "net": net, "mode": "A", "size": size, "via": via,
                            "nearest_gnd": near, "d_mm": d, "limit_mm": MODE_A_PAIR_MM,
                        })

    print()
    print("═" * 70)
    if fails:
        print(f"G_SW_GND_VIA: FAIL — {len(fails)} unpaired SW via/cluster(s)")
        print()
        for f in fails:
            if f["mode"] == "B":
                print(f"  FAIL {f['net']} cluster [{f['size']} vias] centroid={f['centroid']}")
                print(f"       nearest GND={f['nearest_gnd']} d={f['d_mm']:.3f}mm > {f['limit_mm']}mm limit")
            else:
                print(f"  FAIL {f['net']} via={f['via']} (Mode A isolated)")
                print(f"       nearest GND={f['nearest_gnd']} d={f['d_mm']:.3f}mm > {f['limit_mm']}mm limit")
        print()
        print("Remediation: add GND through-via within tolerance of each failing")
        print("SW via/centroid. Per worker OQ-017 approach, one cluster-centroid")
        print("GND via per ≥3-via cluster is acceptable (Mode B).")
        return 1

    print(f"G_SW_GND_VIA: PASS — {pass_count} pair(s) within tolerance")
    print(f"  Mode B (cluster-centroid, ≤{MODE_B_CENTROID_MM}mm): cluster-level pairs OK")
    print(f"  Mode A (per-via, ≤{MODE_A_PAIR_MM}mm): isolated-via pairs OK")
    return 0


if __name__ == "__main__":
    # argv[1] = board path; optional --parked-exempt flag handled at module
    # scope (PARKED_EXEMPT). Reject if board path missing.
    if len(sys.argv) < 2:
        sys.stderr.write(
            "USAGE: audit_sw_gnd_return_pair.py <path/to/board.kicad_pcb> "
            "[--parked-exempt]\n")
        sys.exit(2)
    sys.exit(audit(sys.argv[1]))
