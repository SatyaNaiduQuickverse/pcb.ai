# Deep Research — Routing Methodology to Ground a Mature Routing Engine

**Date**: 2026-05-28
**Trigger**: Greedy cooperative maze router (`route_subsystem_cooperative.py` v1→v8, PathFinder-style) capped CH1 signal routing at 24/30. It routed nets in arbitrary MST/fail-count order, consumed the J18/J19 QFN escape-via room with early nets, and left 6 nets with no escape that does not short neighbors. Diagnosis (`MASTER_COOP_ROUTER.md` §"Known limitations" #1; `DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE` diagnosis correction; `[[reference-qfn-pin-escape-bottleneck]]`): **greedy detailed routing with NO global planning phase fails on dense escape.**
**Sai directive**: deep literature/textbook pass to ground a strong, mature, generalizable routing ENGINE before it touches the real board. READ-ONLY research.
**Scope note**: This is a literature-synthesis research doc (genre = `DEEP_RESEARCH_*`), not a plan/methodology doc. It does NOT duplicate `ROUTING_METHODOLOGY.md` (our 6-tier constraint-driven SSoT) or `MASTER_COOP_ROUTER.md` (the current tool's spec). It grounds the *next* engine; the architecture section maps onto those existing docs explicitly.

---

## 0. Executive summary (the recommended architecture in 10 lines)

1. Adopt the canonical **two-phase paradigm**: a GLOBAL routing phase (capacity/congestion planning on a coarse region graph) feeding a DETAILED routing phase (exact geometry inside each region). Our v1→v8 router has *only* a detailed phase — that is the root cause of corner-painting.
2. The global phase models the board as a **routing-resource graph** with **edge capacities** (tracks/vias a region or boundary can carry) and computes **congestion = demand/supply** BEFORE any geometry is committed. Overflow is detected and resolved by rip-up/reroute at the cheap global level, not the expensive detailed level.
3. For fine-pitch ICs (J18 QFN-32, J19 HVQFN-24) add an **escape pre-check**: compute escape *demand vs supply* per pin-ring side and prove routable-or-infeasible up front. Infeasible → escalate to HDI/placement BEFORE routing, never after.
4. Plan **topology first** (rubber-band/sketch model: which net is left/right of which, net ordering around obstacles), geometrize after. This is Ritchey's "topology before geometry," now made algorithmic.
5. **A\* / maze search belongs ONLY in the detailed phase**, on bounded, congestion-bounded sub-problems handed down by the global phase — never as the global mechanism. Best practice: bound the search region, cap expansions, and never let one net's A\* see the whole board.
6. **Negotiated congestion (PathFinder)** is the convergence engine for the detailed phase *inside a region* and for resolving residual global overflow — it is genuinely good but it is NOT a substitute for global planning. We mis-used it as the whole router.
7. **SURESHOT** (deterministic, bounded, provable) components: left-edge channel routing on acyclic VCG; escape demand/supply counting; layer-assignment via interval/constraint graphs; ILP/SAT ordered-escape on bounded pin sets. Use these for the cases where they apply.
8. **HEURISTIC** (good, not provable) components: net ordering, negotiated-congestion convergence, rubber-band topology refinement, global maze ripup. Use these where sureshot does not reach, but gate them with audits + a known-ground-truth test suite.
9. **Validate component-by-component** against a **difficulty-graded synthetic suite** (6 hard cases below, each with KNOWN routable-or-infeasible ground truth), moderate→hard, before the engine touches the real board.
10. Honest gap: classical VLSI theory assumes 2-layer Manhattan channels and uniform grids; our problem is 10-layer + HDI micro-via + 100A planes + SI/thermal hard constraints + genuine geometric infeasibility at QFN pitch. The *paradigm* transfers cleanly; specific *algorithms* (left-edge, river routing) apply only to sub-regions. The engine must be a paradigm port, not an algorithm copy.

---

## 1. The two-phase paradigm: GLOBAL routing → DETAILED routing

### 1.1 The architecture (chronology)

The canonical VLSI routing flow (Sherwani Ch. 7–11; Sait & Youssef Ch. 5; Kahng/Lienig/Markov/Hu *VLSI Physical Design: From Graph Partitioning to Timing Closure* Ch. 5–6) is:

```
  netlist + placement
        │
        ▼
  [GLOBAL ROUTING]   — coarse. Assign each net to a SEQUENCE OF REGIONS.
        │              Region graph w/ edge CAPACITIES. Objective: route all
        │              nets s.t. no edge demand > capacity (no OVERFLOW),
        │              minimize wirelength/congestion/timing. NO exact geometry.
        ▼
  [LAYER ASSIGNMENT]  — (sometimes folded into global) assign each global
        │              segment to a physical layer; minimize vias + respect
        │              preferred-direction layers.
        ▼
  [DETAILED ROUTING]  — exact. Inside each region/channel, assign each net to
        │              specific TRACKS + VIAS. Honors design rules. THIS is
        │              where maze/A* lives, bounded to the region.
        ▼
  routed layout → DRC
```

The defining property: **global routing decides WHERE (which regions), detailed routing decides EXACTLY HOW (which tracks).** Global routing never draws a track; it allocates *capacity*. Detailed routing never re-plans regions; it fills the plan it was handed.

### 1.2 Why this prevents the greedy-corner-painting we hit

Our v1→v8 router is **pure detailed routing with no global phase**: it builds an MST per net, runs per-edge A\* on the full 3D cell grid, commits, then routes the next net. Each early net's committed escape tracks/vias become hard obstacles that consume the J18/J19 pin-ring via room. By the time the 25th–30th net is attempted, the escape supply is exhausted — the router has, with no global view, spent a shared scarce resource on whichever nets happened to come first (sorted by fail_count then priority — an *arbitrary order with respect to the resource contention*).

A global phase fixes this at the cheap level:

- It models the J18 south pin-ring escape as a single **capacity-limited resource** (N escape slots). It sees that *all* the channel's south-edge nets demand that resource and that demand > supply BEFORE committing a single track.
- **Overflow is detected globally**, where rerouting a net costs flipping a region assignment (microseconds), not ripping committed copper and re-running A\* (the expensive thing our router does, 97 rips / 45 iters per `MASTER_COOP_ROUTER` v4 results).
- It can **reserve** escape slots for the hardest nets (most-constrained-first; §7) instead of letting greedy order grab them.
- If global demand exceeds global supply *and no region reassignment helps*, the problem is **provably infeasible at this placement/stackup** — the engine reports that up front (escalate HDI/placement) rather than plateauing at 24/30 after burning compute.

This is exactly the lesson in `MASTER_COOP_ROUTER` §"Known limitations" #1 ("greedy MST + per-edge A\* doesn't reserve via slots across siblings") and the diagnosis correction in `DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE` — restated in the canonical vocabulary: **we are missing the global routing phase and its capacity model.**

### 1.3 How capacity / congestion is modeled (the routing graph)

Three standard global-routing graph models (Sherwani Ch. 7; Kahng Ch. 5):

| Model | Nodes | Edges | Capacity = | Best for |
|---|---|---|---|---|
| **Grid graph (gcell / global-cell)** | Uniform tiles ("gcells", "buckets") over the board | Adjacency between tiles | # tracks crossing the tile boundary (= boundary_length / (wire_pitch)) per layer | General area routing; the ISPD-contest standard |
| **Channel-intersection graph** | Channels (rectangular routing regions between cell rows) + their intersections (switchboxes) | Channel-to-channel adjacency | # tracks the channel cross-section supports | Structured / row-based layouts |
| **Checkerboard / coarse region graph** | Coarse rectangular regions | Region adjacency | aggregate track budget | Hierarchical / very large designs |

**Capacity** of an edge = how many wires can cross it = (geometric width available) ÷ (wire pitch = trace width + clearance), summed over layers available in the preferred direction.
**Demand** of an edge = number of nets routed across it by the current global solution.
**Overflow** of an edge = max(0, demand − capacity). **Total Overflow (TOF)** and **Max Overflow (MOF)** are the canonical global-routing quality metrics (ISPD 2008 global routing contest: TOF is the primary rank metric, MOF the tie-breaker — a router with more overflow is *strictly inferior regardless of wirelength/runtime*). **Congestion** = demand/capacity (≥1.0 ⇒ overflow).

For our board this maps directly:
- Coarse gcells over the 100×100mm board, per signal layer (In2/In4/In6/In8 + F.Cu/B.Cu fanout). GND planes In1/In3/In7 and +VMOTOR In5 are *not* routing layers — they are reference/power and excluded from the routing-resource graph (matches `MASTER_COOP_ROUTER` SKIP_NET_PATTERNS).
- Each subsystem zone (`BOARD_INVARIANTS` CH1 = x0–35,y50–89) is a natural coarse region.
- The **highway reservations** (`BOARD_INVARIANTS` §Highway: +BATT/GND spine, BEMF return centerline, etc.) become **zero-capacity edges for foreign nets** in the global graph — a clean, declarative way to enforce them that our current router only enforces implicitly.
- The J18/J19 pin-ring is a **special high-demand region** flagged for the escape pre-check (§4).

---

## 2. Channel routing & switchbox routing

A **channel** is a rectangular routing region with terminals on two opposite sides (top/bottom); a **switchbox** has terminals on all four sides. These are the classical *detailed*-routing sub-problems once global routing has assigned nets to regions. Even though our board is not a row-of-cells layout, the channel formalism gives us the **deterministic "highways" vocabulary** Sai wants — and the corridors between our component clusters ARE channels.

### 2.1 The left-edge algorithm (SURESHOT when VCG is acyclic)

Reference: Hashimoto & Stevens 1971; Sherwani Ch. 8; Sait & Youssef Ch. 6.

The **left-edge algorithm (LEA)** assigns horizontal net segments to tracks in a channel:
1. Sort nets by the left endpoint (left edge) of their horizontal span.
2. Treat each net's horizontal extent as an **interval**. Greedily pack non-overlapping intervals into the minimum number of **tracks** (this is exact interval-graph coloring — provably optimal track count for the horizontal constraints alone).

This is a **SURESHOT primitive**: interval-graph coloring is polynomial and optimal. It gives the minimum channel height (track count) ignoring vertical constraints.

### 2.2 Vertical & horizontal constraint graphs

Two constraint systems govern a channel:

- **Horizontal Constraint Graph (HCG)**: nodes = nets; an (undirected) edge between two nets whose horizontal spans **overlap in some column** ⇒ they cannot share a track. The minimum number of tracks ≥ the maximum clique of the HCG = the channel **density** (the max number of nets crossing any single column = a hard lower bound on tracks).
- **Vertical Constraint Graph (VCG)**: nodes = nets; a **directed** edge net_A → net_B if in some column, A's terminal is on top and B's terminal is on bottom ⇒ A's horizontal segment must be in a track *above* B's (else their vertical pin connections would cross/short). The VCG encodes the up/down ordering forced by terminal positions.

### 2.3 The cyclic-conflict problem (the routability boundary)

**If the VCG has a cycle, the channel is NOT routable in a single dogleg-free pass.** A 2-cycle (A→B and B→A in different columns) means A must be both above and below B — geometrically impossible without splitting a net across tracks. This is the precise, *deterministic* statement of "this region is over-constrained."

This is the formal analogue of our QFN escape failure: when too many nets with conflicting required orderings must escape the same edge, the constraint graph has cycles / the density exceeds track supply, and **no detailed router can win** — the fix is upstream (dogleg, reorder, more tracks, or placement change), exactly what a global/escape pre-check would have flagged.

### 2.4 Dogleg routing (the cycle-breaker)

Reference: Deutsch 1976 (the "dogleg" algorithm); Sherwani Ch. 8.

A **dogleg** splits a net's horizontal segment across two tracks joined by a vertical jog, so the net can be *above* B in one column and *below* B in another — **breaking a VCG cycle** and reducing track count. Cost: an extra via/jog per dogleg. This is the channel-routing equivalent of our HDI via-in-pad move: spend a via to relieve a topological impossibility.

### 2.5 Switchbox routing & the merge problem

A **switchbox** (4-sided fixed region) is harder: no free dimension to grow, terminals fixed on all four sides. Routability is not guaranteed even with doglegs; switchbox routers (e.g. BEAVER, greedy + rip-up) are heuristic. The **merge/cyclic-conflict problem**: when channels join at switchboxes, the routing order of channels matters (you cannot route a channel whose terminals depend on an un-routed neighbor). Standard fix: a **channel ordering** derived from the channel-intersection graph (route L-shaped/T-shaped junctions in dependency order; for cyclic junction dependencies, use switchbox routing at the junction).

**Relevance to us**: our corridors (e.g. the J18 south edge → BEMF/CSA filter wall corridor) are switchbox-like — fixed on multiple sides by component clusters and highway reservations. This explains why they are genuinely hard: switchbox routability is not guaranteed, and the literature says so explicitly.

---

## 3. Topological / rubber-band / sketch routing ("plan first")

Reference: Dai, Dayan & Staepelaere, "Topological routing in SURF: generating a rubber-band sketch" (IEEE/ICCAD); Tal Dayan PhD "Rubber-Band Based Topological Router"; commercial: Cadence Specctra/Allegro topology router, Mentor/Siemens, Altium *Situs*, Eremex *TopoR*.

### 3.1 The idea: topology before geometry, made algorithmic

A **rubber-band sketch (RBS)** is a canonical representation of *planar topological routing* where each wire is modeled as an elastic band stretched between its endpoints, free to slide around obstacles (pins/vias) but **not to cross other bands or pass through pins**. The RBS captures only **topology**: which side of each obstacle each wire passes, and the left/right *ordering* of wires in every gap — NOT exact coordinates.

The flow:
1. **Topological routing**: decide each net's homotopy class — which obstacles it goes left vs right of, and the ordering of nets through each "door" (gap between two obstacles). This is the algorithmic form of Ritchey's "pick topology before geometry." Routability is checked topologically (planarity + capacity through each door) *before* any geometry exists.
2. **Geometrization / "spread"**: pull the rubber bands taut (shortest path within the fixed topology) and convert to actual track geometry, honoring design rules. If a door is over-full, the sketch is provably infeasible and you reorder/add a layer *before* drawing.

The "shove" / "push-and-shove" routers (KiCad's interactive router, Allegro) are the *interactive* cousin: existing wires elastically move aside to admit a new one, preserving topology. The Situs autorouter explicitly composes multiple engines (memory, pattern, wavefront, **shape-based push-and-shove**, power/ground) — i.e. topology + bounded maze, not one monolithic maze.

### 3.2 Why this is the missing layer in our engine

Our router commits *geometry* (exact tracks) net-by-net and so locks in topology implicitly and irreversibly in greedy order. A topological phase would:
- Decide the *ordering* of the J18 south-edge escapes (net 1 leftmost, net 2 next, …) as a planning step, check the door capacity, and only then geometrize.
- Make net ordering a first-class decision (§7) rather than an emergent side effect of MST + fail_count.
- Allow "shove" instead of "rip-and-fully-reroute" — a later net nudges an earlier net's track sideways within the same topology, cheaper and less destructive than our rip-up.

**Maps to our docs**: this is the algorithmic backbone for `ROUTING_METHODOLOGY` §2 ("Per-net topology decisions — topology before geometry"), which currently records topology as a hand-authored YAML table. A topological router would *compute and verify* that table's feasibility.

---

## 4. Escape routing + pin/via assignment (the J18/J19 problem)

Reference: academic ordered-escape literature — Yan & Wong (SAT-based / "Ordered escape routing based on Boolean satisfiability"); network-flow + ILP formulations (Min-Cost Multi-Commodity Flow, MC-MCF; the multilayer multi-capacity ordered escape work, ISQED'24); the dual-node network-flow ILP we already cited (PMC8056246, ~99.9% routability); MDPI genetic-algorithm ordered escape under non-crossing + single-capacity constraints. Practitioner: Altium/NWES BGA escape guides.

### 4.1 The problem decomposed (chronology)

Escape routing = get every pin of a dense IC (BGA/QFN) out to the component boundary so area routing can take over. Canonical decomposition (matches the search-result "three steps: partition multi-pin nets → via assignment → layer routing"):

1. **Pin → boundary escape (local)**: route each pin to the package boundary, typically with a **dog-bone fanout** (short stub + via) or **via-in-pad** (via under the pad, HDI).
2. **Via assignment**: choose which via slot each escaping net uses. At 0.5mm pitch this is the scarce resource (our exact bottleneck).
3. **Boundary → destination (global)**: ordinary area routing from the boundary onward.

**Ordered escape**: when pin order around the boundary must be preserved (e.g. a bus, or to prevent crossings), the escape *sequence* is a constraint. **Non-crossing** escapes on a single layer force a specific order; violating it requires a layer change (a via).

### 4.2 Computing escape FEASIBILITY up front (demand vs supply) — the SURESHOT pre-check

This is the single highest-value thing to add, and it is *deterministic counting*, not search:

For each escape side (the four edges of J18, the four of J19), per signal layer:
- **Supply** = number of routing tracks that can cross that boundary segment = (boundary length) ÷ (track pitch = trace width + clearance), per available layer; plus via-slot supply = number of via sites that fit in the fanout band at via keep-out spacing.
- **Demand** = number of nets that must escape across that side (from the netlist + which side each pin faces).
- **Feasibility**: if demand > supply on every layer combination, escape is **infeasible without** (a) more layers reaching that side, (b) HDI via-in-pad to reclaim fanout-band area, or (c) placement change to redistribute pins across sides.

The classical "tracks-between-pads" check is the micro version (already in `MASTER_COOP_ROUTER` §"Pad model": at 0.5mm pitch with 0.25×0.88mm pads, halo 0.305mm > half-gap ⇒ **no trace fits between adjacent pads** ⇒ escape MUST be perpendicular ⇒ dog-bone or via-in-pad). The escape pre-check aggregates this into a per-side demand/supply ledger and yields a **routable / infeasible** verdict *before* routing — which is precisely what would have told us at the *start* that 24/30 was the cap and HDI was needed, instead of discovering it after v1→v8.

### 4.3 When it is genuinely infeasible (and the escalation order)

If the pre-check says infeasible, the canonical escalation (and our empirical finding) is:

1. **HDI via-in-pad** — reclaims the dog-bone fanout band (this was THE operative fix for J18/J19 per `DEEP_RESEARCH_2026-05-26` diagnosis correction). Removes the stub, frees pin-ring room. *Right tool for pin-escape-density saturation.*
2. **Placement change** — redistribute pins across package sides / rotate the IC so the high-demand nets face a low-demand edge.
3. **Package change** — QFN-32 → LQFP-48 (more boundary length per pin, coarser pitch) for future SKUs (`DEEP_RESEARCH_2026-05-26` solution E).
4. **More layers** — ONLY helps if the failure is channel congestion *downstream of* a feasible escape, NOT if the pins can't escape the ring (the `[[reference-qfn-pin-escape-bottleneck]]` / diagnosis-correction distinction — binding rule: classify escape-density vs channel-capacity by single-net isolation test BEFORE escalating layers).

### 4.4 Optimal escape: ILP / SAT (SURESHOT-but-bounded)

For a *bounded* pin set, ILP (MC-MCF network flow) and SAT formulations **guarantee** an optimal/feasible ordered escape or a certificate of infeasibility — genuinely sureshot for small instances, but they "frequently cause time violations as the number of variables increases" (search result), so they must be applied to **bounded sub-problems** (one IC's one side), exactly the scope the global phase would hand down. This is the high-value `route_*_ilp.py` investment flagged in `DEEP_RESEARCH_2026-05-26` solution F — now correctly scoped: ILP on the bounded escape, not the whole board.

---

## 5. Bus / river routing + length matching

Reference: Sherwani Ch. 9 (river routing); Howard Johnson *High-Speed Digital Design* Ch. on terminations/skew + *High-Speed Signal Propagation* Ch. 12 (length matching, fly-by); Bogatin *SI Simplified* (timing/skew).

- **River routing** (SURESHOT): a set of nets between two parallel boundaries with the **same left-to-right order on both sides and no crossings** can be routed in a single layer with a deterministic, provably-minimum-area algorithm (planar, monotone — pure nested intervals). It is the cleanest "highway" case. Applies when net order is preserved end-to-end (e.g. a bus from connector to MCU with matching pin order).
- **Bus routing**: parallel net groups (address/data buses) routed as a bundle with uniform spacing. The 3W rule and crosstalk budget (§9) set the spacing.
- **Length matching / matched-length serpentine**: when nets in a group must arrive within a skew tolerance, slack is added as **serpentine (accordion) trace** to the short nets. *When*: source-synchronous buses, differential pairs (intra-pair skew), and any group where edge-rate × skew > timing budget. *How*: route to the topology first, measure the longest net, add tuned meanders to the others within the spacing budget (meander spacing ≥ trace width to avoid self-coupling — Johnson). **Fly-by + matched length** is the modern bus topology (vs. star) to control reflections.

**Relevance to us** (per `ROUTING_METHODOLOGY` Tier 5): DShot/TLM per-channel ±2mm match, BEMF differential ±0.5mm match. These are length-matching *constraints*, not bus-routing problems (our nets are mostly point-to-point, not wide buses) — so we need the **length-match-as-constraint** machinery (measure + serpentine), not full river/bus routing. River routing applies if/where the S6→CHn command bus runs as an ordered group.

---

## 6. Layer assignment & via minimization

Reference: Sherwani Ch. 10; Kahng Ch. 5–6 (layer assignment); constrained layer assignment via interval/conflict graphs.

- **Constrained layer assignment (CLA)**: assign each global wire segment to a physical layer such that (a) preferred-direction rules hold (one layer mostly-horizontal, the next mostly-vertical — the standard HV discipline), (b) overlapping same-direction segments go on different layers, (c) **via count is minimized** (each layer change = a via = an impedance discontinuity + a reliability/area cost). This is solvable as graph coloring / min-cost flow on the layer-conflict graph; the unconstrained version is polynomial, the via-minimizing version is the optimization.
- **Via minimization** (constrained via minimization, CVM): given a topology, minimize layer changes. NP-hard in general but well-approximated; strongly coupled to layer assignment.

**Relevance to us**: our layer roles are *pre-assigned by spec* (`BOARD_INVARIANTS` stackup + `MASTER_COOP_ROUTER` v5 LAYER_PREF table: BEMF→In4, PWM/CSA→In2, control→In8, SW→In6). That is a **fixed layer assignment** — good for SI/EMI determinism, but it means our "layer assignment phase" is *constraint enforcement*, not free optimization. The engine should treat the LAYER_PREF table as hard/soft constraints fed into the global phase, and minimize vias *within* those constraints. Note `MASTER_COOP_ROUTER` v2's hard lesson: a layer change = a **through-via that intersects every copper layer**, so via assignment MUST do full-stack obstacle validation (the +46-shorts bug). Via minimization is therefore also a *correctness* lever, not just cost.

---

## 7. Net ordering & negotiated congestion

### 7.1 Net-ordering heuristics (HEURISTIC — flagged)

Reference: Sherwani Ch. 7 (order dependence of maze routing); Sait & Youssef. Sequential routers are **order-dependent**: the net routed first gets the best resources. Common orderings (all heuristics, none provable-optimal):

- **Criticality-first**: route timing/SI-critical nets first (they get the cleanest paths). For us: PWM gate-drive, BEMF, current-sense (the hard-constraint nets, §9).
- **Most-constrained-first** (a.k.a. fewest-options-first): route the nets with the fewest feasible routes first (the J18 escapes) so the easy nets fill around them. This is the direct antidote to our bug — our fail_count ordering only promotes a net *after* it has already failed; most-constrained-first promotes it *before*.
- **Shortest-first**: route short nets first (they rarely block; cheap wins). Good for the easy majority, bad if it starves the hard minority — which is what we observed.
- **Criticality- + congestion-aware ordering**: combine.

**Key insight**: net ordering is a *band-aid for the absence of a global phase*. With a true global phase, order matters far less because capacity is reserved up front. Order remains a tie-breaker, not the main mechanism.

### 7.2 PathFinder negotiated congestion (HEURISTIC but robust; McMurchie-Ebeling 1995)

The algorithm we already use (correctly, as far as it goes — `MASTER_COOP_ROUTER` is a faithful PathFinder port):
- Allow nets to **share** routing resources initially (over-subscribe).
- Each resource node has cost = `b(n) · (1 + h(n)) · p(n)` style: a base cost, a **history** term `h` that accumulates each iteration a node stays congested, and a **present-congestion** term `p` that scales with the number of nets currently using the node.
- Iterate: rip up all nets, reroute each on the current cost landscape, bump history on still-congested nodes, raise the present-congestion penalty. Nets that need a contested resource most (no good alternative) keep it; others **negotiate** onto detours. Converges to a legal solution if one exists in the resource graph.

**Where it genuinely helps**: resolving congestion when alternatives EXIST but greedy order picked badly — it re-distributes nets across available slack. This is real and valuable; it is why FPGA routers and our v2–v8 use it.

**Where it does NOT help (and global planning is the real fix)**: when there is **no slack** — when demand truly exceeds supply (the J18 escape). PathFinder will iterate, raise penalties, oscillate, and **plateau** (our 24/30) because it cannot manufacture capacity that does not exist. It is a *congestion redistributor*, not a *capacity planner*. Running it without a global capacity model = trying to negotiate a resource shortage by raising prices when the resource is simply absent. The fix is the global phase + escape pre-check that detect the shortage and escalate (HDI/placement) *before* negotiation.

**Refined role in the new engine**: PathFinder is the *detailed-phase convergence engine inside each global region*, and the residual-overflow resolver — applied to bounded problems the global phase certified as *feasible*. Never the top-level mechanism.

---

## 8. Where A\* / maze search fits

Reference: Lee 1961 (maze/wave propagation — guarantees shortest path on a grid if one exists); Hightower 1969 (line-search — faster, not guaranteed shortest); Hart-Nilsson-Raphael 1968 (A\* = Lee + admissible heuristic, far fewer expansions).

**Confirmed**: A\*/maze belongs in the **DETAILED phase only**, on bounded clear sub-problems, NEVER as the global mechanism.

Why never global:
- Maze search has **no capacity awareness** — it finds *a* shortest path for *one* net against current obstacles, blind to what later nets need. Run net-by-net (our router), it is the textbook **order-dependent greedy** failure mode (Sherwani explicitly warns maze routing is order-dependent and benefits from global pre-planning).
- Its cost is per-net path search; running it on the whole 3D board grid for every net is both slow (our 200s / 97-rips) and myopic.

Best practice for limiting it (the "minimal A\*" discipline):
1. **Bound the search region** to the global-routing region (gcell box) handed down — never the whole board. (Standard in modern detailed routers: A\* is confined to a "routing window.")
2. **Cap expansions** (expansion budget) — if A\* blows the budget, the region is over-constrained ⇒ kick back to the global phase, do not thrash.
3. **Use the global congestion map as the A\* cost field** (PathFinder present+history) so detailed A\* is congestion-aware *within* its region.
4. **Pre-assign via slots** for sibling escapes before per-net A\* (the explicit fix in `MASTER_COOP_ROUTER` §"Known limitations" #1 "multi-net joint A\*"), so siblings don't fight over the same via.
5. Keep the 8-connected + axis-cell-passable diagonal discipline + post-collapse Bresenham validation we already have (`MASTER_COOP_ROUTER` limitations #4) — that part is correct.

So: our A\* implementation is fine *as a detailed-phase primitive*. The defect is that we let it BE the router. Demote it.

---

## 9. PCB SI rules-of-thumb (GUIDANCE — flagged heuristics) and which become HARD constraints for us

Reference: Howard Johnson *High-Speed Digital Design* + *High-Speed Signal Propagation*; Eric Bogatin *Signal & Power Integrity Simplified*; Lee Ritchey *Right the First Time*; Henry Ott *EMC Engineering*. **These are rules-of-thumb / guidance, not physical law** — they are conservative simplifications of field behavior. The hardness for *us* depends on edge rate and net class.

| Rule of thumb | What it says (heuristic) | Physical basis | HARD constraint for our nets? |
|---|---|---|---|
| **Return-path adjacency** | Every signal needs a continuous reference plane on an adjacent layer; return current flows directly under the trace above ~tens of kHz | Return current follows the path of least *impedance* (inductance), not least resistance — it hugs the signal at HF | **HARD** for PWM gate-drive (30–50ns edges → significant HF content), BEMF (high-Z, noise-sensitive), current-sense (analog). Already in `ROUTING_METHODOLOGY` ref_layer per class. |
| **Reference-plane continuity** | Never route a signal across a gap/split in its reference plane | A plane split forces return current to detour → loop area → EMI + crosstalk | **HARD** for the same critical nets. Our GND planes In1/In3/In7 are continuous by design; rule = don't let a critical signal cross from referencing one plane to another without a stitching cap/via. `ROUTING_METHODOLOGY` antipattern #2. |
| **3W rule** | Center-to-center spacing ≥ 3× trace width keeps crosstalk ~ −20dB | Crosstalk falls with spacing; 3W is a ~1% coupling heuristic | **SOFT/GUIDANCE** generally; tighten to HARD for BEMF-near-SW-node and current-sense-near-PWM (analog sense lines next to switching). Crosstalk ∝ parallel-run-length × 1/spacing². |
| **20H rule** | Pull power plane edge back 20× dielectric height from board edge | Reduces fringing/edge radiation | **SOFT/GUIDANCE** — EMC nicety, not routability. Note for +VMOTOR In5 plane. Disputed effectiveness in literature; low priority. |
| **Crosstalk vs parallel-length & spacing** | Coupling ∝ coupled length and 1/spacing; keep aggressor/victim parallel runs short & spaced | NEXT/FEXT mutual L & C | **HARD budget** for current-sense / BEMF vs PWM & SW node. Drives layer assignment (put analog sense on a layer shielded from switching) — already `ROUTING_METHODOLOGY` Tier-4. |
| **Stub / via discontinuity** | Minimize stubs; vias add ~tens of pH–nH + capacitance → reflections | Stub = unterminated transmission line; via = impedance bump | **HARD** for the commutation loop (tight loop, `ROUTING_METHODOLOGY` Tier-2, ≤50mm²) and decoupling (ESL — via-in-pad if needed). SOFT for slow control nets. |
| **Length-match tolerance** | Match lengths within a fraction of the rise time × velocity | Skew budget | **HARD** as specified: DShot/TLM ±2mm, BEMF diff ±0.5mm. |
| **Commutation loop area** | Keep the power-switching loop physically tiny | di/dt × loop-L = switch-node ringing & EMI | **HARD** — placement gate G3 + `ROUTING_METHODOLOGY` Tier-2; measured 0.1953nH/phase (STEP-6). This is the most physics-load-bearing constraint on the board. |

**The hard-constraint set for the engine** (these must become routing-graph constraints, not post-hoc DRC): commutation-loop containment, gate-drive return adjacency, current-sense Kelvin + shielding, BEMF differential match + shielding, plane-continuity for all critical nets. The rest are weighted soft objectives. This is consistent with `ROUTING_METHODOLOGY` Tier ordering — the engine should *consume* that tier table as its constraint priority.

---

## 10. Validation / test-case design — difficulty-graded synthetic suite

### 10.1 What the literature uses as hard cases

- **ISPD global-routing contests (2008, 2011)**: the canonical congestion benchmarks; ranked by **Total Overflow then Max Overflow** (a router with *any* overflow is inferior regardless of wirelength). The hard property: congestion deliberately exceeds capacity in regions ⇒ forces detours / exposes capacity-blindness.
- **ISPD detailed-routing contests (2018, 2019)**: initial detailed routing from given route guides, *with advanced design rules* (min-area, end-of-line, cut spacing) — the hard property is rule-correctness under congestion, and explicitly "route guides cannot be assumed overflow-free."
- **Channel-routing classics**: **Deutsch's difficult example** (the canonical hard channel — high density + long VCG chains); **cyclic-VCG channels** (provably unroutable without doglegs).
- **Escape-routing instances**: dense BGA/QFN with demand≈supply (the boundary of feasibility) and ordered-escape with forced non-crossing.

These confirm Sai's requirement: the bar is *demand-meets-or-exceeds-supply* and *known ground truth*, not toys.

### 10.2 Recommended difficulty-graded suite (6+ hard cases, each with KNOWN ground truth)

Each case is a small synthetic `.kicad_pcb` (or board-state fixture) with a **proven** routable/infeasible verdict, so we can validate engine components independently. Build moderate→hard. Ground truth is provable by construction (we set capacity vs demand).

| # | Case | Construction | Ground truth | Validates |
|---|---|---|---|---|
| **T1 — Moderate channel** | 2-layer channel, ~10 nets, density = tracks available, **acyclic VCG** | Built so left-edge packs exactly into available tracks | **ROUTABLE** (provable: acyclic VCG + density ≤ tracks) | Left-edge / detailed channel fill; baseline sanity |
| **T2 — Cyclic-VCG channel** | Same channel, terminals arranged to create a VCG **2-cycle** | A→B and B→A forced | **INFEASIBLE without dogleg**; ROUTABLE with one dogleg | Cycle detection; dogleg insertion; "report infeasible, don't thrash" |
| **T3 — Congested corridor (greedy trap)** | A corridor where the *globally optimal* assignment routes net X the "long way" so net Y (most-constrained) gets the short slot; greedy shortest-first puts X short and **strands Y** | Capacity = exactly enough iff X detours | **ROUTABLE only with global planning / most-constrained-first**; greedy fails | Global phase + net-ordering; *directly reproduces our 24/30 bug in miniature* |
| **T4 — QFN escape at feasibility boundary** | QFN-32-like pin ring, demand = supply exactly on one side (no via-in-pad) | tracks-between-pads = 0, dog-bone slots = exactly N nets | **ROUTABLE iff escape pre-check assigns via slots correctly; INFEASIBLE if one extra net added** | Escape pre-check (demand/supply ledger); via-slot pre-assignment; the J18/J19 case |
| **T5 — Genuinely infeasible escape** | T4 + one extra net beyond supply, no HDI allowed | demand = supply + 1 | **INFEASIBLE** (must be *reported as infeasible up front*, then ROUTABLE once HDI via-in-pad enabled) | The escalation logic: detect infeasibility → recommend HDI, NOT plateau-after-burning-compute |
| **T6 — Forced-crossing / layer-assignment** | Two nets that MUST cross; single layer infeasible | crossing is topologically forced | **INFEASIBLE on 1 layer; ROUTABLE with 1 via to 2nd layer** | Layer assignment + via minimization; correct via insertion (full-stack obstacle check) |
| **T7 — Negotiated-congestion redistribution** | Region with slack: a naive order over-subscribes one node, but a feasible legal solution exists by redistributing | 2 nets, 2 equal-cost paths, naive picks same | **ROUTABLE** — PathFinder must converge by negotiation | PathFinder history/present-cost convergence (vs. plateau) |
| **T8 — Plane-split / return-path trap** | A critical net whose shortest path crosses a plane split; a longer path stays over a continuous reference | split present | **ROUTABLE only if engine treats plane-continuity as a HARD constraint** (rejects the short path) | SI hard-constraint enforcement in the cost field (§9) |
| **T9 (stretch) — Multilayer ordered-escape** | QFN with nets requiring ordered escape across 2 layers + length-match group | construct so only one layer/order assignment works | **ROUTABLE with one specific layer+order assignment** | Full pipeline: escape + layer assignment + ordering + length-match together |

**Grading**: T1, T7 moderate (single-mechanism). T2, T6, T8 medium (a constraint that breaks the naive approach). T3, T4, T5 hard (reproduce our actual failure class at known feasibility boundaries). T9 stretch (full-pipeline integration). **Each MUST have its verdict proven by construction**, so a component that passes T1–T9 is validated against ground truth, not against "looks routed."

**Discipline**: build the suite FIRST, validate each engine component against it, and only then point the engine at the real board — matching `[[feedback-sureshot-over-sota]]` (verifiability + bounded failure) and the sim-execution-gate discipline (verdicts reproducible from a fixture, not "trust me").

---

## 11. SURESHOT vs HEURISTIC ledger (Sai values sureshot)

| Component | Class | Why |
|---|---|---|
| Left-edge channel routing on **acyclic** VCG | **SURESHOT** | Interval-graph coloring = polynomial, optimal track count; cycle ⇒ provably unroutable (deterministic verdict) |
| Escape demand/supply pre-check | **SURESHOT** | Pure counting (boundary÷pitch, via-slot count vs net demand); yields a *proof* of routable/infeasible per side |
| River routing (order-preserving, no-cross) | **SURESHOT** | Provably minimum-area planar algorithm |
| Layer assignment (unconstrained) | **SURESHOT** | Polynomial graph coloring on conflict graph |
| ILP / SAT ordered escape on **bounded** pin set | **SURESHOT-but-bounded** | Optimal or infeasibility certificate — but only tractable on small instances (must bound scope) |
| Cyclic-VCG detection, density lower bound | **SURESHOT** | Graph cycle detection; max-clique-as-density lower bound is exact |
| Constrained via minimization | **HEURISTIC** (well-approximated) | NP-hard in general |
| Net ordering (criticality/most-constrained/shortest-first) | **HEURISTIC** | No optimality guarantee; order-dependent |
| PathFinder negotiated congestion | **HEURISTIC (robust)** | Converges *if a solution exists in the resource graph*; can plateau when no slack; not a capacity planner |
| Rubber-band topology refinement / shove | **HEURISTIC** | Topology planning heuristic; geometrization is the deterministic part |
| Global maze rip-up & reroute | **HEURISTIC** | Order- and parameter-dependent |
| Detailed A\* in a bounded region | **SURESHOT path / HEURISTIC overall** | A\* finds shortest path if one exists in the *given* region; but per-net greedy across nets is heuristic |

**Engine design implication**: lead with the SURESHOT components (escape pre-check, channel/left-edge where channels exist, layer-assignment constraint check, density/VCG verdicts) to get *provable* statements (routable / infeasible / needs-HDI) BEFORE invoking any heuristic. Use heuristics (PathFinder, A\*, ordering, shove) only inside scopes the sureshot layer certified feasible, and gate every heuristic with the T1–T9 ground-truth suite. This is the structural answer to "no more 24/30 surprises."

---

## 12. Recommended engine architecture (grounded in the above)

```
                 ┌────────────────────────────────────────────────────────────┐
                 │  INPUT: placed .kicad_pcb + routing_topology.yaml            │
                 │         (ROUTING_METHODOLOGY tiers + per-net constraints)    │
                 └───────────────────────────┬────────────────────────────────┘
                                             ▼
   PHASE A — CONSTRAINT & CAPACITY MODEL (SURESHOT, deterministic)
     • Build routing-resource graph: gcells per signal layer (In2/In4/In6/In8/F/B),
       subsystem zones as coarse regions, highways = zero-capacity foreign edges.
     • Compute per-edge CAPACITY (boundary÷pitch per layer) and net DEMAND.
     • ESCAPE PRE-CHECK per fine-pitch IC side (J18/J19): demand vs supply ledger.
         → emit verdict: ROUTABLE | NEEDS-HDI | NEEDS-PLACEMENT-CHANGE | INFEASIBLE
         → if not ROUTABLE, STOP and report (escalate per §4.3) — do NOT route blind.
     • Ingest SI hard constraints (§9) as graph constraints (plane-continuity =
       forbidden edges across splits; return-adjacency = layer pinning).
                                             ▼
   PHASE B — TOPOLOGICAL / GLOBAL PLAN (SURESHOT verdicts + HEURISTIC refine)
     • Decide region sequence per net (global routing) honoring capacity; detect
       OVERFLOW; resolve at region level (cheap), NOT by ripping copper.
     • Rubber-band sketch: decide net ORDER through each door/escape side; verify
       door capacity + planarity BEFORE geometry.  (= topology before geometry)
     • Net ordering = most-constrained-first / criticality-first as TIE-BREAK only.
     • Pre-assign via slots for sibling escapes (multi-net joint, the v8 gap fix).
     • Layer assignment under fixed LAYER_PREF table; minimize vias.
         → emit: per-net region path + layer + via slots + ordering, all CERTIFIED
           feasible by capacity. If a region overflows and no reassignment fixes it,
           kick back to Phase A escape-escalation.
                                             ▼
   PHASE C — DETAILED ROUTING (bounded HEURISTIC, our existing strength, demoted)
     • Per region (bounded box from Phase B), fill exact tracks:
         - channel-like regions: left-edge + dogleg (SURESHOT where VCG acyclic)
         - free-form regions: A* CONFINED to the region, using Phase-B congestion
           map as cost field, expansion-capped; PathFinder negotiated-congestion
           for residual within-region contention.
         - "shove" existing tracks within fixed topology rather than full rip-up.
     • Length-match: measure group, add serpentine to short nets within spacing.
     • Full-stack via obstacle validation on EVERY via (the v2 +46-shorts lesson).
                                             ▼
   PHASE D — VERIFY (existing gates)
     • audit_routing.py per-tier (ROUTING_METHODOLOGY §6) + DRC + per-net 1-island
       union-find + symmetry diff (R19) + sim per tier (Tier 1 PDN … Tier 6 bulk).
```

Mapping to existing assets (no duplication):
- **`route_subsystem_cooperative.py`** (v8) = a correct **Phase C** detailed-router primitive. Keep it. Demote it from "the router" to "the region filler." Its PathFinder core, full-stack via validation, layer-pref bias, `--no-rip-routed`, and MST-completion safety net all carry forward.
- **`ROUTING_METHODOLOGY.md`** 6 tiers + topology YAML = the **constraint priority** Phases A/B consume.
- **`BOARD_INVARIANTS.md`** zones/highways/HDI whitelist = Phase A's region + capacity + escape inputs.
- **NEW work** = Phase A (capacity model + escape pre-check) and Phase B (global plan + topology/ordering + via-slot pre-assignment). This is the missing two-thirds of a mature router.

---

## 13. Honest gaps — where the theory does not cleanly apply to our 10L/HDI/100A-ESC

1. **Classical channel/river routing assumes 2-layer Manhattan + uniform grid + cells-in-rows.** Our board is 10-layer, mixed-direction, component-cluster layout. The channel *formalism* (VCG/HCG, density, dogleg) applies to our corridors as an analysis lens and to specific sub-regions, but we cannot run a textbook channel router on the whole board. The **paradigm** (global→detailed, capacity, topology-first) ports cleanly; the **specific algorithms** apply only to sub-regions.
2. **HDI micro-via / via-in-pad is barely in the classic VLSI literature** (which assumes through/full-stack vias). Our via-assignment and full-stack obstacle model (`MASTER_COOP_ROUTER` v2/v6/v7) is more specialized than the textbooks — the +46-shorts and the v6 HDI-short bugs show the literature doesn't pre-warn you that a "via" pierces all 10 layers. Engine must keep our hard-won full-stack via discipline; theory won't supply it.
3. **100A power planes are not "nets" in the routing sense.** +VMOTOR (In5, 3oz), GND planes, +BATT spine are PDN, governed by ampacity (IPC-2152), IR-drop, and loop-area — not track-capacity. Classical routing graphs don't model these; we correctly exclude them (SKIP_NET_PATTERNS) and handle them as Tier-1 PDN first. The routing engine's capacity model is for *signal* layers only.
4. **SI constraints are HARD here, weighted-soft in EDA literature.** Most academic routers optimize wirelength/overflow with timing as a soft objective. For us, commutation-loop area, gate-drive return-path, and current-sense shielding are *correctness* constraints (a "routed" board that violates them fails in hardware). The engine must treat them as graph-hard constraints, not cost terms — a stance the generic literature does not take.
5. **Genuine geometric infeasibility at QFN-0.5mm pitch.** No router — sureshot or heuristic — can route what doesn't fit. The honest contribution of theory here is *detecting and proving* infeasibility early (escape pre-check) and naming the escalation (HDI/placement/package), NOT making it routable. This is the central correction from `DEEP_RESEARCH_2026-05-26`: the engine's job at the wall is a *correct verdict + escalation*, not a heroic route.
6. **Pi memory budget** (`[[feedback-pi-shared-system-protect]]`): full-board global routing graph at fine gcell resolution may exceed the 15GB Pi. Phase A/B must be subsystem-scoped (per `[[feedback-pi-bounded-subsystem-scope]]`); full-board global routing is a Phase-7 x86 op. The global *phase* can run at coarse gcells on the Pi (cheap); only fine detailed A\* is memory-heavy.
7. **Symmetry (R19/OQ-019)**: classical routers don't preserve N-instance geometric symmetry. Our CH1→CH2/3/4 mirror requirement means the engine should route CH1 then *transform*, not re-route each channel independently — a constraint outside standard routing theory, already handled by `route_mirror_ch1_to_ch234.py`. The global plan must be mirror-consistent.

---

## 14. References

**Textbooks**
1. N. Sherwani, *Algorithms for VLSI Physical Design Automation*, 3rd ed. (Kluwer, 1999) — Ch. 7 global routing, Ch. 8 channel routing (left-edge, dogleg, VCG/HCG), Ch. 9 river routing, Ch. 10 layer assignment.
2. S. Sait & H. Youssef, *VLSI Physical Design Automation: Theory and Practice* (World Scientific, 1999) — Ch. 5 global, Ch. 6 detailed routing.
3. A. Kahng, J. Lienig, I. Markov, J. Hu, *VLSI Physical Design: From Graph Partitioning to Timing Closure* (Springer, 2011) — Ch. 5 global routing (grid graph, capacity, overflow), Ch. 6 detailed routing.
4. Lee Ritchey, *Right the First Time* Vol. 1–2 (Speeding Edge) — topology-before-geometry; routability-driven pin assignment (Vol. 2 Ch. 22).
5. Howard Johnson & Martin Graham, *High-Speed Digital Design* (1993) and *High-Speed Signal Propagation* (2003) — return paths, crosstalk, length matching (HSSP Ch. 12), routing within footprints (HSSP Ch. 13.7).
6. Eric Bogatin, *Signal and Power Integrity — Simplified*, 3rd ed. (2018) — return-path, decoupling/ESL, fine-pitch routing (Ch. 9.5).
7. Henry Ott, *Electromagnetic Compatibility Engineering* (Wiley, 2009) — return-path control, plane continuity.

**Foundational algorithms**
8. C. Y. Lee, "An Algorithm for Path Connections and Its Applications," IRE Trans. EC, 1961 — maze/wave routing.
9. D. Hightower, "A Solution to Line-Routing Problems on the Continuous Plane," DAC 1969 — line-search.
10. P. Hart, N. Nilsson, B. Raphael, "A Formal Basis for the Heuristic Determination of Minimum Cost Paths," IEEE SSC, 1968 — A\*.
11. A. Hashimoto & J. Stevens, "Wire Routing by Optimizing Channel Assignment within Large Apertures," DAC 1971 — left-edge algorithm.
12. D. Deutsch, "A Dogleg Channel Router," DAC 1976 — doglegs / cycle breaking.
13. L. McMurchie & C. Ebeling, "PathFinder: A Negotiation-Based Performance-Driven Router for FPGAs," FPGA 1995 — negotiated congestion. https://www.cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf

**Topological / rubber-band**
14. W. Dai, R. Dayan, D. Staepelaere, "Topological routing in SURF: generating a rubber-band sketch," DAC/ICCAD. https://ieeexplore.ieee.org/document/979685
15. T. Dayan, *Rubber-Band Based Topological Router* (PhD, UCSC).
16. Eremex *TopoR* (commercial topological router, Specctra/DSN import). https://t.eremex.com/
17. Altium, "Automated PCB Routing with the Situs Topological Autorouter." https://resources.altium.com/p/automated-pcb-routing-with-situs-topological-autorouter

**Escape routing**
18. T. Yan & M. Wong, "Ordered escape routing based on Boolean satisfiability," ASP-DAC. https://www.researchgate.net/publication/4327316_Ordered_escape_routing_based_on_Boolean_satisfiability
19. "Ordered escape routing using network flow and optimization model," IEEE. https://ieeexplore.ieee.org/document/7081209/
20. "Multilayer Multi-capacity ORdered Escape Routing via Bus decomposition," ISQED 2024. https://numbda.cs.tsinghua.edu.cn/papers/isqed24_2.pdf
21. Dual-node Network-flow ILP for PCB escape routing (~99.9% routability), 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/
22. "A Genetic Algorithm-Based Optimization Method for Ordered Escape Routing in BGA PCBs," MDPI Applied Sciences, 2026. https://www.mdpi.com/2076-3417/16/4/2010
23. Altium, "Which BGA Pad and Fanout Strategy is Right for Your PCB?"; NW Engineering, "BGA Escape Routing with Impedance Control in HDI PCBs."

**Benchmarks**
24. ISPD 2008 Global Routing Contest (TOF/MOF metrics). http://www.ispd.cc/contests/08/ispd08rc.html
25. ISPD 2011 Routability-Driven Placement Contest. http://www.ispd.cc/contests/11/ispd2011_contest.html
26. ISPD 2018/2019 Initial Detailed Routing Contests (advanced rules). http://www.ispd.cc/contests/18/index.htm
27. C. J. Alpert et al., "The ISPD global routing benchmark suite."

**Internal (this codebase)**
28. `docs/ROUTING_METHODOLOGY.md` — 6-tier constraint-driven SSoT (the constraint priority the engine consumes).
29. `docs/MASTER_COOP_ROUTER.md` — current PathFinder detailed-router (v1→v8); the Phase-C primitive to keep + demote.
30. `docs/DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md` — escape-density vs layer-capacity diagnosis correction.
31. `docs/BOARD_INVARIANTS.md` — zones/highways/stackup/HDI whitelist (Phase-A inputs).
32. `[[reference-qfn-pin-escape-bottleneck]]`, `[[reference-cascading-escape-needs-negotiated-routing]]`, `[[reference-kicad-dsn-export-drops-inner-layers]]`, `[[feedback-sureshot-over-sota]]`, `[[feedback-build-routing-system-not-freerouter]]`, `[[feedback-pi-bounded-subsystem-scope]]`.

## Per locked rulebook
- `[[feedback-online-research-when-needed]]` — textbooks + academic papers + current web corroboration.
- `[[feedback-physics-as-compass]]` — every constraint derived from physics (capacity, return-path, loop-L, crosstalk).
- `[[feedback-sureshot-over-sota]]` — explicit SURESHOT-vs-HEURISTIC ledger (§11); lead with provable components.
- `[[feedback-edit-existing-dont-write-new]]` — RESEARCH-genre doc (dated, like the 2026-05-26 J18/J19 one); does NOT duplicate ROUTING_METHODOLOGY (plan) or MASTER_COOP_ROUTER (tool spec); maps onto them explicitly (§12).
- `[[feedback-system-learns-minimal-rules]]` — minimal sureshot primitives + bounded heuristics + ground-truth test loop, not a heavy rule set.
- `[[feedback-sim-execution-gate]]` discipline applied to routing: §10 suite gives reproducible, ground-truth verdicts before the engine touches the real board.
