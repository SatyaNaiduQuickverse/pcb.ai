# Master Thinking Pathway — design-space scratchpad

**Per Sai 2026-05-26:** *"whenever working is working and you are a bit free put your time in thinking about these factors you can make a thinking pathway it will help us explore more"*

This is a living scratchpad for master-level **exploration** when execution is in worker's hands. Each entry is an idea, design question, or research note — not a commitment. Entries graduate to formal PRs (with audit gates + tests) when they prove their value.

The pathway has 3 lanes:
1. **OUTWARD** — new dimensions / techniques we don't currently cover
2. **INWARD** — improvements to our own process, methodology, audit suite
3. **OPEN QUESTIONS** — physics/engineering questions that need experiment or sim

---

## Entry 001 — 2026-05-26 — Grid-based placement (Sai-prompted)

### Sai's framing
*"things are parametric so why dont you try to fit things like in a grid manner it could get so easier i think you are trying to fit stuff like anywhere you think might be right.. like you can make a graph paper and place stuff exactly on it and we can have traces from there too.. you'll know how many traces each of them get and if parallel components are there how many traces they may need.. its like making a city.. you try to keep the most connected stuff together and nearer.. ofcourse you also have to think about the physics which could interfere"*

### Where this connects
Current state: `parametric_placement.py` outputs floating-point coords (Q5 at x=8.4, y=53.0). Worker's `bring_selected` does spiral search around those anchors. Components end up at arbitrary float coordinates. Routing happens later, having to thread traces through whatever space remains.

Sai's alternative: place ON a discrete grid (e.g. 0.5mm or 1mm cell). Every component snaps to grid intersections. Then:
- Trace routing follows grid lines (Manhattan)
- Trace count per grid row/column is countable BEFORE routing → "trace budget per region"
- Net connectivity graph → "connected stuff stays together" (HPWL minimization)
- Physics constraints layered (EMC distance, thermal, signal integrity)
- The city analogy: highways (HV power) on wide grid rows, streets (signals) on narrow rows, city blocks (component clusters), districts (subsystem zones)

### Conceptual model
```
Grid: 100×100 mm board, 1mm cell → 100×100 grid cells per layer × 2 layers
                                = 20,000 cells total (or 80,000 at 0.5mm)
Each cell can be:
  - OCCUPIED by component bbox
  - RESERVED for routing channel
  - FREE (headroom)
  - HIGHWAY (reserved corridor)
  - KEEPOUT (mount hole drill etc)

Net = (set of pins) where pin = (component, pad-number, cell)
Net's "trace budget" = sum of (pin count) - 1 (= minimum trace segments to connect)

Placement quality function (city analogy):
  HPWL(net) = (x_max - x_min) + (y_max - y_min) of net's pins  → minimize sum
  density(region) = occupied cells / total cells  → ≤ budget (55%)
  trace_count(row) = number of nets crossing this row's edge  → ≤ row routing capacity (e.g. 8 traces/mm)
  physics_violations: ∑ pairs (a, b) where |a-b| < min_distance(a.type, b.type)
```

### Pros (going OUTWARD)
- **Routing predictability**: knowing trace count per row at placement time avoids "oh, no room for the BEMF traces" surprises at routing phase
- **Auditability**: grid cells are countable, visualizable as ASCII art / image
- **Reproducibility**: snap-to-grid means tiny parameter changes don't shuffle every coord
- **Composability**: per-subsystem grid layouts are simple to compose / mirror / rotate
- **Manhattan routing**: routes follow grid lines → easy length match, easy diff-pair, easy via grid alignment
- **Compatible with parametric engine**: grid cell size is a parameter (`GRID_CELL_MM`); component anchors snap

### Cons / constraints
- **Existing footprints have non-grid pin pitches** (e.g. SOT-23 = 0.95mm pin pitch, QFN-32 = 0.4mm). Component's center can be on grid but its pins won't be.
  - Resolution: grid is for placement ANCHORS + routing channels, not component internal pins. Pins are footprint-relative.
- **Some constraints are sub-grid** (HS↔LS 3.6mm offset, decoupling cap ≤3mm). Need fractional grid (0.1mm) for those?
  - Resolution: 2-level grid — coarse 1mm for placement, fine 0.1mm for offsets.
- **Diagonal traces** (e.g. SW node from HS-FET drain to LS-FET drain via cluster) are not Manhattan. Grid would force orthogonal which adds 41% length penalty.
  - Resolution: allow diagonal via "primary grid corridor" reservations; trace count counts diagonals as 1.

### Cons (existing-framework integration)
- Worker's `bring_selected` does spiral connectivity-driven search — doesn't fit a "place on grid" paradigm directly. Would need a new placement script.
- Our 6 existing per-subsystem placement scripts would need migration to grid-aware versions.
- Lockfile YAML coords are already floats — would they switch to grid units?

### Implementation idea (seed)
`hardware/kicad/scripts/grid_placement.py`:
```python
@dataclass
class GridConfig:
    cell_mm: float = 1.0          # primary grid cell size
    fine_cell_mm: float = 0.1     # for sub-grid offsets
    board_grid_cells_x: int = 100 # = 100mm / 1mm
    board_grid_cells_y: int = 100

class GridCell:
    occupied_by: Optional[str] = None     # ref of component
    reserved_for: Optional[str] = None    # "routing", "highway", "keepout"
    traces_through_x: int = 0             # estimated horizontal trace count
    traces_through_y: int = 0             # vertical

def build_connectivity_graph(netlist) -> dict[str, set[str]]:
    """Returns {component_ref: set of neighbor refs via shared nets}."""

def hpwl(net, placement) -> float:
    """Half-perimeter wire length of net given component positions."""

def place_subsystem_on_grid(subsystem, components, p: BoardParameters, g: GridConfig):
    """Greedy or simulated-annealing placement that:
       1. Snaps each component to a grid cell
       2. Minimizes ∑ HPWL(net) over all nets in subsystem
       3. Respects forbidden zones (routing channels, mount holes, etc.)
       4. Respects density budget per cell-region
       5. Respects physics distance constraints
    """
```

### Open questions for grid placement
- Q1: Cell size — 1mm too coarse for fine-pitch ICs? Suggest 0.5mm primary, 0.05mm via grid.
- Q2: Should HS-FET ↔ LS-FET pairing remain explicit (3.6mm Y offset) or emerge from optimization?
- Q3: Trace routing capacity per row — derive from min trace width + clearance (0.2mm trace + 0.15mm clearance = 0.35mm per signal trace, so 1mm row fits ~2 signal traces)
- Q4: How to handle B.Cu placement — separate grid per layer, or paired (HS-LS) cells?
- Q5: Does grid help OR hurt sim-driven iteration? Snap-to-grid removes some fine optimization knobs.

### Next step (if pursued)
1. Build minimal `grid_placement.py` for one CH1 channel — proof of concept
2. Compare HPWL of grid placement vs current `bring_selected` placement
3. If grid wins on HPWL by >20% → graduate to full PR
4. Otherwise document why grid didn't help here (some classes of board favor connectivity-driven over grid)

---

## Entry 002 — 2026-05-26 — Connectivity-graph net visualization

### Idea
Before placing, build the netlist's connectivity graph (components as nodes, shared-net count as edge weight). Visualize as a force-directed graph layout. This gives Sai a top-down "social network" view of which components want to be neighbors.

### Why useful
Currently we place subsystem-by-subsystem, but inter-subsystem connections (e.g. S6 J14 FC → all 4 channel MCUs) aren't explicit in placement. A connectivity graph would surface:
- Components with many cross-subsystem connections (hubs)
- Components that are LEAF (only one connection — can sit anywhere)
- Tight clusters (likely want physical grouping)

### Implementation seed
```python
import networkx as nx
G = nx.Graph()
for net in netlist:
    pins = net.pins  # list of (component, pad)
    for i in range(len(pins)):
        for j in range(i+1, len(pins)):
            G.add_edge(pins[i].component, pins[j].component, weight=G.get_edge_data(...).get('weight', 0) + 1)
# nx.spring_layout(G, weight='weight') → force-directed coords
# Plot with matplotlib
```

### Connection to grid placement
The force-directed graph gives an initial "where does each component want to be relative to its neighbors" → seed for grid-snap placement.

---

## Entry 003 — 2026-05-26 — Sim-driven placement loop concrete design

### Recap from PLACEMENT_GLOBAL_PLAN.md §8
Methodology doc described it. Implementation hasn't started.

### Design
```python
def sim_driven_place(subsystem: str, max_iterations: int = 20):
    coords = parametric_initial_placement(subsystem)
    history = []
    for iter in range(max_iterations):
        # Fast analytical proxies
        loop_area = compute_loop_area(coords)       # nH estimate
        decouple = compute_decoupling_distances(coords)  # mm
        hpwl = compute_total_hpwl(coords)            # mm

        # Score
        score = (loop_area * w_loop + decouple_violations(decouple) * w_dec +
                 hpwl * w_hpwl)
        history.append((iter, coords, score))

        if score < ACCEPTABLE_PROXY_SCORE:
            # Expensive FEM only when proxies say "in spec"
            T = run_elmer_thermal(coords)
            EMI = run_openems_emi(coords)
            if T < T_MAX and EMI < EMI_MAX:
                return coords  # converged
            # else: adjust + back to top

        # Adjust placement to reduce score
        coords = local_search(coords, current_violations)
    raise PlacementFailedError(history)
```

### Open questions for sim loop
- Q1: How to "adjust placement"? Random perturbation? Gradient via finite-difference?
- Q2: How to cache sim results for unchanged regions (avoid full re-sim each iter)?
- Q3: How long is each iteration acceptable (proxy ~1s, FEM ~60s, total target <1hr)?

---

## Entry 004 — 2026-05-26 — Audit suite gap items still queued (from MASTER_AUDIT_GAP_ANALYSIS_2026-05-26.md)

### OUTWARD (new dimensions, queued PR batches)
- G_PP12 3D through-board overlap (tall F.Cu cap + tall B.Cu cap at same XY)
- G_PP13 enclosure clearance (component height vs enclosure inner height)
- G_PP14 component vs highway (not just mount-hole-vs-highway)
- G_PP15 heatsink XY keep-clear (tall components within heatsink footprint break thermal contact)
- G_PP17 EMC isolation matrix (BEC↔Hall ≥15mm, BEC↔FET ≥10mm etc per BILATERAL §40)
- G_PP18 thermal forbidden pairs (BEC NOT under Hall per BILATERAL §50)

### INWARD (meta-audits)
- G_META2 exempt_list_documented (every EXEMPT_PAIRS entry has Sai-approved reason)
- G_META3 audit_self_test (every audit has known-good + known-bad fixture)
- G_META4 rule_to_audit_map (every R-rule declares its audit; sync check)
- G_META5 audit_coverage_declaration (every audit docstring declares what it doesn't check)

### Status
Plan documented in PR #139. Implementation queued. Will fire after CH1 stabilizes.

---

## Entry 005 — 2026-05-26 — "City planning" analogy applied to subsystem layout

### Sai's framing
*"its like making a city.. you try to keep the most connected stuff together and nearer"*

### Concrete mapping
| City | PCB |
|---|---|
| Highway | +VMOTOR plane (In3.Cu, 3oz), BAT_P/N feed |
| Street | Signal trace channel (1-2mm wide) |
| Alley | 0402 cap to IC pin (sub-mm) |
| District | Subsystem zone (CH1, S2, S5, ...) |
| City block | Sub-cluster (per-phase FET cell, per-IC decoupling group) |
| Train station | Connector (J14 FC, J12 AUX) |
| Power plant | Battery input + bulk caps + reverse-pol FETs (S1+S2+S3 chain) |
| Substation | BEC (S5 — voltage regulation for the district) |
| Residential | LEDs (low-power, low-priority) |
| Industrial zone | FET cluster (high heat, high power) |

### Useful insights
- Don't put residential next to industrial → don't put LEDs next to switching FETs
- Substation needs cooling → BEC away from heat-sensitive (Hall)
- Highway needs straight runs → +VMOTOR plane unobstructed
- Train stations need access → connectors at board edge

### Connection to placement
Adopt city-planning rules as audit gates:
- G_PP19 "highway clear" (already exists for routing channels)
- G_PP17 "industrial-residential separation" (= EMC distance)
- G_PP18 "substation cooling" (= thermal forbidden pairs)

---

## How to use this document

When master is monitoring (worker iterating) or otherwise idle:
1. Skim entries — find one with traction
2. Develop a sub-idea or research note
3. Validate against existing framework (subsystem PRs + audit gates + lockfile)
4. If promising, prototype + measure
5. If proves value, graduate to formal PR with audit gates

Entries can stay open for weeks. New entries get added at the bottom. Old entries get pruned when they graduate or are abandoned.

Per Sai: *"it will help us explore more"*.
