#!/usr/bin/env python3
"""render_net_connectivity_graph.py — Sai 2026-05-26 "city planning" viz.

Builds the netlist's component-connectivity graph (nodes=components, edges=
shared nets with weight=count of shared nets) and renders as a force-directed
layout. Compares the "social network" of components to their actual physical
placement — surfaces gaps where highly-connected components ended up far apart
(routing hard, signal integrity poor).

Auto-generates on every placement PR (wired in master_pre_merge.sh as a
render-only step, not BLOCKING — visual review by master).

Per Sai 2026-05-26 idea #2 — "Build as audit".
"""
import os, sys, math, json
from collections import defaultdict

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); return 1
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
    except ImportError:
        print("FAIL — matplotlib not available", file=sys.stderr); return 1

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/board-render/latest/net_graph.png"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0

    # Build connectivity graph
    fps = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x, y = pos.x/mm, pos.y/mm
        if x < -5 or x > 200 or y < -5 or y > 200: continue
        fps[ref] = (x, y, fp)

    # Edges: for each net, all pairs of components on that net get +1 edge weight
    edges = defaultdict(int)
    net_components = defaultdict(set)
    for ref, (x, y, fp) in fps.items():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net and "unconnected" not in net.lower() and not net.startswith("Net-"):
                net_components[net].add(ref)
    for net, comps in net_components.items():
        comps = sorted(comps)
        if len(comps) > 8: continue  # GND/+VMOTOR mega-nets skew the graph — skip
        for i in range(len(comps)):
            for j in range(i+1, len(comps)):
                edges[(comps[i], comps[j])] += 1

    # Compute neighbor count + total weight per node
    weight_per_node = defaultdict(int)
    for (a, b), w in edges.items():
        weight_per_node[a] += w
        weight_per_node[b] += w

    # Render: physical layout (top) vs distance-vs-connection scatter (bottom)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10), dpi=100)
    fig.patch.set_facecolor("#0b0d10")

    # ───── Left: physical layout with edges colored by weight ─────
    ax1.set_xlim(-3, 103); ax1.set_ylim(103, -3)
    ax1.set_aspect("equal")
    ax1.set_facecolor("#101418")
    ax1.set_title(f"Physical placement + net-shared edges (line thickness ∝ shared net count)\n"
        f"{len(fps)} components · {len(edges)} component-pair edges · {len(net_components)} nets",
        color="#5ce28c", fontsize=11)
    ax1.add_patch(patches.Rectangle((0, 0), 100, 100, lw=1, ec="#5ce28c", fc="none"))
    # Draw edges first (background)
    for (a, b), w in edges.items():
        if a not in fps or b not in fps: continue
        x0, y0, _ = fps[a]; x1, y1, _ = fps[b]
        ax1.plot([x0, x1], [y0, y1], color="#5cb8ff", alpha=min(0.05 + w*0.05, 0.5),
                 linewidth=min(0.3 + w*0.15, 1.5))
    # Draw nodes
    for ref, (x, y, _) in fps.items():
        w = weight_per_node.get(ref, 0)
        size = 1.0 + min(w * 0.15, 3.0)
        color = "#ffaa66" if w > 8 else ("#5ce28c" if w > 3 else "#888")
        ax1.add_patch(patches.Circle((x, y), size, fc=color, ec="#fff", lw=0.3))
        if w > 6:
            ax1.text(x, y-2, ref, fontsize=4.5, color="#fff", ha="center")

    # ───── Right: distance histogram (physical vs net-shared) ─────
    distances = []
    for (a, b), w in edges.items():
        if a not in fps or b not in fps: continue
        x0, y0, _ = fps[a]; x1, y1, _ = fps[b]
        d = math.sqrt((x0-x1)**2 + (y0-y1)**2)
        distances.append((d, w))

    if distances:
        d_arr = [d for d, w in distances]
        w_arr = [w for d, w in distances]
        ax2.scatter(d_arr, w_arr, alpha=0.4, s=15, c="#5cb8ff")
        ax2.set_xlabel("physical distance (mm)", color="#dfe3e8")
        ax2.set_ylabel("# nets shared (edge weight)", color="#dfe3e8")
        ax2.set_facecolor("#101418")
        ax2.tick_params(colors="#888")
        ax2.set_title("Edge weight vs physical distance\n"
            "(high weight + high distance = routing-hard; should be top-left)",
            color="#5ce28c", fontsize=11)
        ax2.grid(True, color="#222", alpha=0.5)
        # Highlight worst (highly-connected but far apart)
        for d, w in distances:
            if w >= 3 and d > 50:
                ax2.scatter([d], [w], c="#ff5c5c", s=40, zorder=5)
        ax2.axvline(50, color="#ff8866", ls="--", alpha=0.5, label="50mm — likely routing-hard")
        ax2.axhline(3, color="#ffaa66", ls="--", alpha=0.5, label="3+ nets shared — strong coupling")
        ax2.legend(loc="upper right", facecolor="#1a1f26", edgecolor="#444", labelcolor="#dfe3e8")

    # Worst offenders summary
    worst = sorted([(d, w, a, b) for (a, b), w in edges.items()
                    if a in fps and b in fps
                    for d in [math.sqrt((fps[a][0]-fps[b][0])**2 + (fps[a][1]-fps[b][1])**2)]
                    if w >= 3 and d > 40], key=lambda x: -x[0])[:10]

    if worst:
        text = "Top routing-hard pairs (high net-share + far apart):\n"
        for d, w, a, b in worst[:8]:
            text += f"  {a}↔{b}: {w} nets, {d:.1f}mm\n"
        fig.text(0.02, 0.02, text, fontsize=7, color="#ffaa88",
                 verticalalignment='bottom', family='monospace')

    fig.suptitle("Net Connectivity Graph — Sai 2026-05-26 'city planning' viz",
        color="#5ce28c", fontsize=13, fontweight='bold', y=0.98)
    fig.tight_layout(rect=[0,0.08,1,0.95])
    fig.savefig(out_path, facecolor="#0b0d10", dpi=100)
    print(f"wrote {out_path} ({len(fps)} nodes, {len(edges)} edges)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
