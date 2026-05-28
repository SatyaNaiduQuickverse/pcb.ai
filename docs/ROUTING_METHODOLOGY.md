# Routing Methodology — 6-tier constraint-driven

**Single source of truth.** All routing scripts read from this.

**Hash**: see bottom (ROUTING_METHODOLOGY_HASH); change requires explicit PR tagged `[methodology-change]`.

---

## 0. Principle

Per Henry Ott *EMC Engineering*, Lee Ritchey *Right the First Time*, Eric Bogatin *SI/PI Simplified*, Howard Johnson *HSDD*:

> Routing is **PDN design** + **return-path control** + **per-class topology**.
> Find open space is the antipattern.
> Pick topology BEFORE drawing geometry; geometry implements topology.

Per `[[feedback-build-routing-system-not-freerouter]]` + `[[feedback-sureshot-over-sota]]`: this is a deterministic constraint-manager-style router, NOT Freerouter random search.

---

## 0b. Global→Detailed Architecture (Phases A/B/C) — the engine wrapper around the 6 tiers

> **Added 2026-05-28** per master locked decisions after the CH1 24/30 plateau diagnosis (`DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md`). This section is the **engine architecture**; §1–§9 below are its **detailed-phase ordering** (they describe Phase C's per-tier discipline). The two are reconciled, not competing: the 6 tiers are *what to route in what physics-priority order*; Phases A/B/C are *how the engine decides feasibility and region assignment before any geometry is drawn*. **The companion build+validation plan is `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` (T1–T9 suite + build sequence + SURESHOT/HEURISTIC ledger); this section is the methodology, that doc is the plan — no duplication.**

### Root cause being fixed

Per the canonical VLSI flow (Sherwani Ch. 7–11; Sait & Youssef Ch. 5; Kahng/Lienig/Markov/Hu *VLSI Physical Design* Ch. 5–6), routing is **GLOBAL routing** (assign nets to a sequence of capacity-limited regions; decide WHERE) → **DETAILED routing** (assign exact tracks/vias inside each region; decide HOW). Our v1→v8 cooperative router (`MASTER_COOP_ROUTER.md`) is **pure detailed routing with no global phase**: greedy MST + per-edge A*, committing geometry net-by-net. Early nets consume the shared scarce escape-via resource at J18/J19, and by net ~25 the supply is exhausted → the 24/30 plateau. This is the textbook order-dependent greedy failure mode (Sherwani: maze routing is order-dependent and needs global pre-planning). The engine adds the missing two-thirds.

### PHASE A — Capacity + Escape pre-check (NEW, SURESHOT, deterministic counting — not search)

Computed UP FRONT, before any geometry, on a routing-resource graph (gcells per signal layer In2/In4/In6/In8/F/B; GND In1/In3/In7 + +VMOTOR In5 excluded — they are reference/PDN, matching `SKIP_NET_PATTERNS`). Subsystem zones (`BOARD_INVARIANTS.md` §Subsystem zones) are coarse regions; highway reservations (`BOARD_INVARIANTS.md` §Highway reservations) are **zero-capacity edges for foreign nets**.

1. **Per-edge capacity** = (boundary length) ÷ (track pitch = trace width + clearance) summed over available layers in the preferred direction. **Demand** = nets the current plan routes across that edge. **Overflow** = max(0, demand − capacity). Metrics: Total Overflow / Max Overflow (ISPD-2008 convention — any overflow is strictly inferior regardless of wirelength).
2. **Per-IC-side pin-escape demand-vs-supply ledger** for every fine-pitch IC (`BOARD_INVARIANTS.md` HDI whitelist J18 QFN-32, J19 HVQFN-24, both 0.5mm pitch). Per package side, per signal layer:
   - **Supply** = boundary-segment÷track-pitch + via-slot count (via sites that fit the fanout band at via keep-out spacing).
   - **Demand** = nets that must escape that side (from netlist + pin-face assignment).
3. **Verdict** (deterministic, provable): `ROUTABLE` / `NEEDS-HDI` / `NEEDS-PLACEMENT-CHANGE` / `INFEASIBLE`. If not `ROUTABLE`, **STOP and report up front** — do NOT route blind. This is the gate that would have flagged "J18/J19 needs HDI" on day one instead of after v1→v8 (`DEEP_RESEARCH_2026-05-28` §1.2; `[[reference-qfn-pin-escape-bottleneck]]`).

**Escalation order when not ROUTABLE** (per `DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md` capacity-vs-escape-density decision table + 2026-05-28 diagnosis correction): (1) HDI via-in-pad — reclaims the dog-bone fanout band, the operative J18/J19 fix; (2) placement change — redistribute pins across sides; (3) package change (QFN-32→LQFP-48, future SKU); (4) more layers — **only** when failure is board-wide channel congestion, NOT pin-ring saturation. Binding classification rule: single-net isolation test on stuck nets first — fine-pitch-IC failure in isolation = escape density (HDI/fanout), board-wide congestion = layers. Grounding: BGA/QFN ordered-escape literature (Yan & Wong SAT; dual-node network-flow ILP, PMC8056246 ~99.9% routability; ISQED'24 multilayer ordered escape).

SI hard constraints (§9, the §0c-referenced hard-constraint set) enter Phase A as graph constraints, not post-hoc DRC: plane-continuity = forbidden edges across splits; return-adjacency = layer pinning.

### PHASE B — Global plan + DOORS + topology (NEW, generic graph)

A **generic graph** model (Sai-locked: build it generic from the start even if slower — `[[feedback-sureshot-over-sota]]` verifiability over speed). Nodes = pins / door-ports / via-sites / corridor-junctions. Edges = corridor supply (capacity) + net demand.

**DOORS are first-class objects** = corridor cross-sections, each declaring `{id, coord, width, layer-set, capacity, passes(net/net-group)}`:
- **Board-edge / inter-subsystem doors ARE the `BOARD_INVARIANTS.md` Subsystem I/O ports** (e.g. S6→CH1 at (17,82) 2mm; S2→CH1 +VMOTOR at (40,50) 4mm) — referenced, not redefined.
- **Interior doors** = channel mouths between component clusters + highway entries (`BOARD_INVARIANTS.md` Highway reservations).

The global router (Phase B):
1. Assigns nets to corridors **with capacity headroom** (never to 100% — see §F FoS-on-routing-process; the root-cause fix for the 24/30 corner-paint).
2. **Orders nets through each door** (net-ordering / topology-before-geometry, rubber-band / VCG style — Ritchey "topology before geometry" made algorithmic; Dai/Dayan SURF rubber-band sketch). Door capacity + planarity verified BEFORE geometry exists.
3. **Pre-assigns via slots** for sibling escapes (the `MASTER_COOP_ROUTER.md` "multi-net joint A*" gap-fix), so siblings don't fight over the same via.
4. **Layer assignment** under the fixed `LAYER_PREF` table (`MASTER_COOP_ROUTER.md` v5: BEMF→In4, PWM/CSA→In2, control→In8, SW→In6); minimize vias *within* those constraints (each layer change = full-stack through-via = SI discontinuity + the v2 +46-shorts hazard).

Parametric → cheap re-iteration + visible conflicts: overflow is resolved at region level (flip a region assignment, microseconds), NOT by ripping committed copper and re-running A* (the expensive thing v8 does — 97 rips / 45 iters). Emits per-net region path + layer + via slots + ordering, all CERTIFIED feasible by Phase A capacity. If a region overflows and no reassignment fixes it → kick back to Phase A escalation.

### PHASE C — Detailed fill (EXISTS — `route_subsystem_cooperative.py`, demoted)

The v8 PathFinder negotiated-congestion router (`MASTER_COOP_ROUTER.md`) is KEPT as the **detailed-phase primitive within a feasible region handed down by Phase B** — demoted from "the router" to "the region filler." Everything it does well carries forward: full-stack via validation (v2/v7), per-net-class layer-pref bias (v5), `--no-rip-routed` multi-pass preserve (v4), HDI via-in-pad on the J18/J19 whitelist (v6/v7), MST-completion safety net + union-find connectivity verify (v3). The §1–§9 tier ordering below governs Phase C's per-region discipline (Tier 1 PDN first … Tier 6 bulk last).

### A* usage (Sai-locked)

A* lives **ONLY in Phase C**, confined to the bounded region Phase B hands down, expansion-capped. NEVER the global mechanism (global A* = autorouter mess; maze search has no capacity awareness, is order-dependent — Lee 1961 / Hart-Nilsson-Raphael 1968; Sherwani warning). Discipline: (1) bound the search to the gcell box; (2) cap expansions — over-budget ⇒ kick back to Phase B, do not thrash; (3) use the Phase-B congestion map as the A* cost field; (4) consume Phase-B pre-assigned via slots; (5) keep the existing 8-connected + axis-cell-passable diagonal discipline + post-collapse Bresenham validation. Our A* is fine as a primitive; the defect was letting it BE the router.

### SURESHOT vs HEURISTIC split (Sai-locked, `[[feedback-sureshot-over-sota]]`)

**Lead with SURESHOT** (deterministic, provable): escape demand/supply pre-check; left-edge channel routing on acyclic VCG; river routing (order-preserving, no-cross); layer-assignment verdict; cyclic-VCG / density-lower-bound detection; bounded ILP/SAT escape (optimal-or-infeasibility-certificate on one IC's one side). **Gate HEURISTIC behind the T1–T9 ground-truth tests**: net ordering (most-constrained-first / criticality-first); PathFinder negotiated congestion; rubber-band topology refine / shove; global rip-up; constrained via minimization. The full ledger lives in `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` §SURESHOT/HEURISTIC inventory.

### SOTA via SIM-INTELLIGENCE (the differentiator)

Classical routers optimize abstract overflow counts with pure logic. OURS puts REAL physics sims in the decision loop — net ordering, where to spend geometric complexity, when to escalate to HDI, and congestion negotiation are all informed by actual SI / thermal / loop-L sim results (commutation loop-L 0.1953nH/phase, BEMF crosstalk, current-density). Two-tier:
- **Proxy-sim** (fast analytical inner loop): `physics_primitives.py` closed-form (IPC-2152 ampacity, Hammerstad-Jensen Z0, crosstalk_db, via thermal R) — cheap, drives the cost field and ordering. NOT a binding verdict.
- **STRONG-sim** (openEMS / Elmer / ngspice): the ONLY binding verdict, NO cutting. Gated by the existing **sim-execution-gate** (`[[feedback-sim-execution-gate]]`, R18): result-file present + mtime > input mtime + extract-script output + literal exec command + git-SHA-reproducible against the canonical board (`[[feedback-sim-artifact-must-be-canonical]]`). A proxy-sim disagreeing with a strong-sim by >tolerance writes a proposed lesson (`ROUTING_LESSONS.md`); the strong-sim governs.

### Anti-drift discipline (ported from the placement engine)

- **Parametric `RoutingParameters` SSoT + `routing_topology.yaml` lockfile**; live `.kicad_pcb` is the source of truth, NEVER module numbers (`[[reference-parametric-placement-desync-trap]]`), bridged by a compliance gate (the placement analogue is `audit_parametric_compliance.py`).
- **Routing RULES_MANIFEST 3-artifact contract** (fix script + audit gate + master-verified) per R29/R30.
- **Routing gate taxonomy by class**, reusing `master_pre_merge.sh`'s `run_gate` harness.
- **Two-sided meta-integrity**: named-gate-exists-on-disk (`audit_meta.py`) + every-gate-wired-or-deferred (`audit_meta_coverage.py`, G_META1).
- **Sim-execution + provenance + sanity gates** (`audit_sim_execution.py`, `audit_sim_artifact_provenance.py`, `audit_sim_result_sanity.py`).
- **CH1 is the route template; CH2/3/4 are PURE transforms** (mirror_X / mirror_Y per `BOARD_INVARIANTS.md` §Symmetry pairs + §mirror_primitive), never hand-laid (R19; `[[feedback-symmetry-preserves-work]]`; L2). The global plan must be mirror-consistent.

### PHASE C addendum — TARGETED RIPUP-REBUILD (CH1 30/30 lever J, 2026-05-28)

> **Added 2026-05-28** per master locked decisions after the cooperative router's 24-simultaneous-net cap diagnosis (worker empirical PR #227: 24-net plateau across 6 invocation strategies; BSTB add-on-top = 25/30 ceiling; 5 functionally-critical residuals: PWM_INHB, PWM_INLA, GLB, KILL_RAIL_N, SWDIO). Sai-approved with explicit guidance: "have strong validation and audit gates. we have rules system, you just need to add stuff there." This section EXTENDS Phase C (it does not replace it); the global ripup behaviour of `route_subsystem_cooperative.py` remains intact and is the default; targeted ripup is an OPT-IN escalation when global ripup has plateaued AND specific blocked nets are functionally critical.

**Root cause being addressed**. Cooperative PathFinder negotiates *redistribution when slack exists* but cannot manufacture capacity that is absent. When 24 nets all want the same J18/J19 escape via-slots and a 25th asks for a slot already consumed by a foreigner X that ALSO has alternate paths, global ripup keeps X in place (its total cost is low) and the 25th plateaus. Targeted ripup identifies X as the SPECIFIC conflict and surgically rips ONLY X, routing the blocked net on its preferred path, then re-routing X on its alternate. This is the lever-J insight: the global cost function never "sees" the asymmetry that X has slack while the blocked net does not.

**The 6-step algorithm** (binding; implemented in `hardware/kicad/scripts/targeted_ripup.py` + the `--enable-targeted-ripup` path in `route_subsystem_cooperative.py`):

1. **Corridor-conflict identification** — for blocked net N, compute its IDEAL path (clearance to placement obstacles ONLY, ignoring foreign copper). Walk the path. Identify foreign nets whose tracks/vias actually intersect the corridor — that set is the **conflict set**.
2. **Minimum-conflict-set selection** — choose smallest subset of the conflict set whose removal clears N. Heuristic (`rank_conflict_set_for_rip`): rank by ALTERNATIVE-RE-ROUTE COUNT proxy = priority class (low priority ⇒ many alternates ⇒ rip first); break ties by net criticality (debug > digital_bus > analog > motor > safety — rip debug first, protect safety). Frozen-banked-nets (R38) and nets with priority ≥ blocked-priority are EXCLUDED from the candidate set up front.
3. **Pre-ripup feasibility check** (Sai expansion 2026-05-28, the "no wasted rips" gate) — lightweight reachability (`feasibility_alt_reroute_count_proxy`): confirm each conflict-set net HAS an alternative re-route path. If any conflict-set net has zero alternatives, ABORT the ripup attempt for N (rolling back the candidate selection); we cannot fix N this way.
4. **Surgical rip → route N → re-route foreigners** — ATOMIC operation: rip ONLY the selected conflict subset, route N on its preferred path treating the ripped corridor as free, then re-route each ripped foreigner treating N as a fixed obstacle. Use the existing Phase-C primitives (`find_path_astar`, `path_to_segments`, per-class halo from lever F).
5. **Cascade-bounded recursion** — if a re-route of a ripped foreigner X requires its own rip of a tertiary net Z, allow ONCE (depth=2). Beyond → ABORT, full rollback. The provenance entry records `cascade_depth`; R37 / G_J2 enforces ≤ 2.
6. **Atomic commit / rollback** — all-or-nothing: SHORTS_post − SHORTS_pre ≤ 0 AND every ripped foreigner re-routes successfully, OR full rollback to pre-attempt state. Either outcome writes a provenance entry (R36) — silent abandonment forbidden.

**Net-criticality scoring** (the Sai expansion; SSoT in `targeted_ripup.NET_CRITICALITY`):

| Class | Priority | Examples | Role |
|---|---|---|---|
| SAFETY | 100 | `KILL_*`, `KILL_RAIL_N` | NEVER rip (only ROUTE FIRST); protect |
| MOTOR_CONTROL | 80 | `PWM_*`, `GL[ABC]`, `GH[ABC]`, `BST[ABC]`, `MOTOR_[ABC]` | Route early; rip-as-last-resort |
| ANALOG_SENSE | 70 | `BEMF_[ABC]`, `SHUNT_*`, `*_CURR_*`, `VREF*`, `I_TRIP_N` | Route early; analog noise margin |
| BULK_SIGNAL | 40 | default | Normal |
| DIGITAL_BUS | 50 | `DSHOT_*`, `TLM_*`, `*_RAIL_*` | Mid-tier |
| DEBUG | 20 | `SWDIO`, `SWCLK`, `SWO`, `TP*`, `BOOT0` | RIP FIRST; ample alternates |

Priority drives BOTH (a) net-processing order (high first — route safety + motor before debug) AND (b) rip ranking (low first — rip debug before motor; protect safety).

**Hard rules** (R36-R39 + G_J1-G_J5; full statements in `docs/RULES_MANIFEST.md`):

| Rule | One-liner | Audit |
|---|---|---|
| R36 | Every targeted-ripup commit logs blocked-net + conflict set + re-route mapping | G_J1 `audit_targeted_ripup_provenance.py` |
| R37 | Cascade depth ≤ 2 (rip→route→re-route allowed once; deeper aborts) | G_J2 `audit_ripup_cascade_depth.py` |
| R38 | Frozen-banked-nets (power planes, +BATT, validated BEC + per-channel power, KILL broadcasts) CANNOT be ripped | G_J3 `audit_frozen_banked_nets_preserved.py` |
| R39 | Phase-symmetric ripup → mirror across A+B+C peers OR explicitly log deviation with R19 loop-L verification | G_J4 `audit_symmetric_ripup_mirror.py` |
| R-J5 | SHORTS delta ≤ 0 across every commit (the v6/v7/F/I shorts-gate, carried forward) | G_J5 `audit_ripup_shorts_delta_zero.py` |

Plus the carrying-forward HARD RULES already in §0b: frozen-routes-set preserved (the `--no-rip-routed` discipline, carried forward), atomic commit, FoS preserved (re-routed nets keep clearances + annular + per-class halos per §5b/§5c), per-class halo applied to re-routes (lever F, the cooperative router shorts-gate fix).

**Where targeted ripup fits in the §0b/§5b/§5c discipline**:
- Phase A still gates feasibility up front. Targeted ripup is NOT a way to route an INFEASIBLE Phase A board; it's a way to break the 24-simultaneous cap inside an otherwise-feasible Phase C region.
- Geometry policy §5b is unchanged: targeted ripup emits the same octilinear-default + teardrops + sim-driven-fillet primitives.
- FoS §5c is unchanged: routed-process FoS (doors/corridors ≤ 75-80% fill) still applies; targeted ripup is the surgical lever inside that envelope, not a license to push it past 80%.

The companion fixture **T17** in `hardware/kicad/scripts/routing_engine/fixtures.py` proves the capability adds something real: a small synthetic case where global ripup converges at N-1 routed (a net N blocked by a specific foreign X that global cost-min keeps in place) BUT targeted ripup identifies X as the precise conflict, surgically rips X, routes N, re-routes X on an alt path → N/N achieved. T17's ground truth is provable by construction (the topology encodes the asymmetry); the adversarial "rip-everything" liar (rip all foreign, route N alone) FAILS T17 on the frozen-routes-preserved rule.

### Honest gaps (carried from `DEEP_RESEARCH_2026-05-28` §13)

Classical channel/river theory ports as PARADIGM not literal algorithm (we are 10L not row-based); HDI micro-via stacks are barely in VLSI literature (our full-stack-via discipline is MORE specialized than textbooks); SI constraints are HARD for us vs soft in EDA tools; genuine geometric infeasibility at 0.5mm QFN pitch where the right deliverable is a correct VERDICT not a heroic route; Pi memory forces subsystem-scoped global routing (`[[feedback-pi-bounded-subsystem-scope]]` — coarse-gcell global on Pi, fine detailed A* is the x86 Phase-7 op); R19 symmetry sits outside standard routing theory.

---

## 1. The 6 tiers (routing order, immutable)

Route every PR's nets in this strict tier order. Tier N+1 cannot start until Tier N audit + sim PASS.

### Tier 1 — PDN (Power Delivery Network) — *FIRST always*

Per Bogatin Ch. 7–10:

| Net | Strategy | Layer | Width |
|---|---|---|---|
| +VMOTOR | Plane + via grid stitching | In3.Cu (3oz copper, ampacity for 280A burst per IPC-2152) | plane |
| GND | Continuous plane (split only at clear analog/digital boundary if needed) | In1.Cu + In5.Cu | plane |
| +BATT trunk | Star from S1 (single source) | F.Cu over In1 GND reference | 2.5mm (40A continuous per IPC-2152) |
| +3V3 / +5V / +9V / +3V3A | Tree (per-rail trunk + stubs to loads) | In2.Cu / In4.Cu micro-planes or wide trunks | 1.5mm (10A typical) |

**Sim before Tier 2 starts**: DC IR drop (ngspice), AC PDN impedance Z-vs-freq (scikit-rf), thermal local for plane regions (Elmer).

### Tier 2 — Switching loops (per-channel local) — *physical, must be tight*

Per Erickson Ch. 23, TI SLUA868:

For each channel CHn:
- HS-FET drain → switching node → LS-FET source → shunt → GND return → bus cap → HS-FET drain
- Enclosed loop area < 50mm² (placement gate G3 already enforces; this verifies)
- Bootstrap loop: DRV BST pin → C_BST → SW node, ≤2mm
- Gate loop: DRV gate-out → R_G → MOSFET gate → MOSFET source → DRV gate-return, on same layer

**Sim**: switching transient ringing (ngspice with parasitic L extracted from layout); EMI near-field (openEMS local around switching cluster).

### Tier 3 — Decoupling — *R25 same-side, ≤3mm*

Per Bogatin Ch. 5:
- Each IC.VDD pin already has cap within 3mm same-layer (placement Tier 3 / G4 enforced)
- Router connects with shortest same-layer trace
- Via on cap pad to plane (if cap is connecting to plane via)

**Sim**: Z-vs-freq vs target (scikit-rf), self-resonance check.

### Tier 4 — Critical analog — *Kelvin + low-Z + matched*

Per Ralph Morrison *Grounding and Shielding*, Henry Ott Ch. 18:

| Net | Strategy |
|---|---|
| INA shunt sense (per CHn) | 4-wire Kelvin (not in current path); on layer adjacent to GND reference for noise shielding |
| BEMF refs (per phase, per CHn) | Differential pair, matched length ±0.5mm, on layer with clean GND ref |
| Hall ACS770 output | Single-ended analog, away from switching noise, shielded by GND on both sides |
| LM393 comparator inputs (per CHn) | Away from switching, short trace to MCU |

**Sim**: crosstalk to switching (openEMS); noise margin (ngspice with measured noise sources).

### Tier 5 — Signal highways — *controlled Z0 + length-matched*

Per Howard Johnson HSDD + Eric Bogatin SI:

| Net | Z0 | Length match | Layer | Topology |
|---|---|---|---|---|
| DShot_CHn (per channel) | 50Ω SE | per-CH match ±2mm | In2.Cu over In1 GND | Point-to-point S6 → CHn MCU |
| TLM_CHn (per channel) | 50Ω SE | per-CH match ±2mm | In2.Cu over In1 GND | Point-to-point CHn MCU → S6 |
| KILL_CHn (broadcast) | 50Ω SE | star preferred; daisy ok | In2.Cu | Star from S6 (or daisy CH1→CH2→CH3→CH4) |
| BUS_CURR_HALL_OUT | analog | — | In4.Cu over In5 GND | Star from S3 Hall → 4 CHn MCUs |

**Sim**: TDR for impedance discontinuity, eye diagram (ngspice transient with DShot edge rates), reflection coefficient at branches.

### Tier 6 — Bulk — *remaining signals*

| Net | Strategy |
|---|---|
| USB DP/DM (if used) | Differential pair 90Ω if reaches USB connector |
| Status LED control | Shortest manhattan, via minimization |
| Debug/SWD | Manhattan, length not critical |
| Pull-ups, BOOT0 | Standard signal |

**Sim**: DRC + visual only.

---

## 2. Per-net topology decisions (Ritchey "topology before geometry")

For each net class, topology chosen EXPLICITLY before drawing tracks. Stored in `docs/PHASE4V3_LOCKFILES/routing_topology.yaml`.

| Net class | Topology | Why |
|---|---|---|
| +VMOTOR | Plane + via grid | Lowest impedance, current spread |
| +BATT | Star from S1 | Single source, defined return |
| BEC rails (+3V3/+5V/+9V/+3V3A) | Tree (trunk + stubs) | Multiple loads, minimize voltage difference |
| GND | Continuous plane | Reference for all signals |
| DShot/TLM (per CHn) | Point-to-point | Single driver, single receiver |
| KILL | Star from S6 (preferred) | Lowest skew for safety-critical broadcast |
| BUS_CURR_HALL_OUT | Star (Hall → 4 MCUs) | One sensor, 4 readers |
| Shunt sense | Kelvin (4-wire) | Sense without IR-drop error |
| BEMF | Differential pair, matched | Common-mode rejection |
| Decoupling | Direct cap-to-VDD same-layer | Lowest ESL |
| Bulk signal | Manhattan shortest | Density-optimal |

---

## 3. Constraint per class (auto-enforced)

| Class | Width | Spacing | Z0 | Length match | Layer ref |
|---|---|---|---|---|---|
| +VMOTOR | plane | — | — | — | In3 3oz |
| +BATT | 2.5mm | 1mm | — | — | F.Cu over In1 GND |
| BEC trunks | 1.5mm | 0.5mm | — | — | In2/In4 |
| Decoupling | 0.5mm | 0.2mm | — | — | same as IC |
| DShot | 0.25mm | 0.25mm | 50Ω | per-CH match ±2mm | In2 over In1 GND |
| BEMF diff | 0.2mm | 0.15mm | 90Ω diff | matched ±0.5mm | In4 over In5 GND |
| Shunt sense | 0.25mm | 0.25mm | — | Kelvin | adjacent to current path on diff layer |
| Bulk signal | 0.25mm | 0.2mm | — | — | any signal layer |

These map to KiCad net classes; `audit_routing.py` enforces.

---

## 4. Symmetry preservation (per Tier 4 routing)

Per `[[feedback-symmetry-preserves-work]]`:

Route CH1 fully (Tiers 1–6), then mirror routes to CH2/3/4 via `route_mirror_ch1_to_ch234.py`:

```python
# Pure geometric transform on each track segment
for track in ch1_tracks:
    mirror_x = 2 * 50 - track.x
    mirror_y = track.y
    add_track_to_ch2(mirror_x, mirror_y, track.layer, track.width, track.net)
```

**Audit**: `audit_routing.py check_route_symmetry()` — per-channel track count + length spread ≤5%.

---

## 5. Antipatterns to avoid

Documented in Ott/Bogatin/Johnson, caught by audit gates:

1. **Find open space** (Freerouter style) — Use deterministic constraint-manager topology.
2. **Route across plane splits** — Return current jumps, EMI. Audit checks net stays over single reference plane.
3. **Signal over via field** — Impedance discontinuity. Audit checks via density along signal path.
4. **High-speed adjacent to switching** — Crosstalk. Spatial separation enforced by Tier order + layer assignment.
5. **Share return path digital/analog** — Ground bounce contaminates analog. Split GND only at clear boundary if needed (Ralph Morrison Ch. 4).
6. **Star ground with multi-MHz signal** — Inductive loop at center. Use plane for return below ~100kHz, controlled-impedance traces above.
7. **Right-angle traces at high speed** — Field discontinuity (minor effect at our edge rates but cosmetic discipline).
8. **Stub from main bus** — Reflection. For DShot/TLM use point-to-point or fly-by.
9. **Unbalanced differential pair** — Common-mode → radiation. Audit enforces length match + parallelism.
10. **Decoupling cap with long via stub** — ESL kills high-freq decoupling. Place cap pad with via-in-pad if needed.

---

## 5b. Geometry policy (Sai-locked 2026-05-28, honest physics)

The engine emits the **simplest manufacturable geometry that is electrically correct**, with targeted local enhancements only where physics demands. No cosmetic global rules.

| Policy | Decision | Physical basis / standard |
|---|---|---|
| **Global chamfer / curve rule** | **REJECTED** — no board-wide rounding/curving rule | Bloat for no benefit at our edge rates. The "90°-corner radiates" belief is a myth below GHz (Howard Johnson *HSDD*: the right-angle reflection/radiation effect is negligible for rise times above ~tens of ps; our PWM/DShot/BEMF nets are sub-MHz to low-MHz). |
| **DEFAULT geometry = OCTILINEAR (45°)** | All routing is H/V + 45° diagonal segments | Simplest manufacturable geometry; electrically fine for ~all our nets. By construction, octilinear **never creates an acute (<90°) interior angle.** |
| **Acute-angle GATE** | REJECT any interior angle <90° (trace-trace or trace-pad junction) | Acute angles trap etchant → acid-trap / over-etch manufacturing defect class (IPC-2221 §6.1 conductor geometry; standard DFM). |
| **TEARDROPS at every pad/via junction** | Mandatory teardrop fillet at each trace-to-pad and trace-to-via transition | The "round the pointed end" that genuinely helps: mechanical stress relief (drill breakout, thermal-cycle crack at the neck) + current-crowding relief at the trace-to-pad neck. IPC-standard targeted enhancement (IPC-7351 land patterns + IPC-2221 thermal-cycle reliability). |
| **LOCAL 45° chamfer / fillet** | HIGH-CURRENT corners ONLY, sim-driven | Applied where a current-density sim flags crowding (real effect on ~100A motor-phase traces — the inside corner of a sharp bend concentrates J; Brooks *PCB Currents*). NOT applied to signal corners. |

This policy is consumed by Phase C geometry emission and by hand touch-ups; both call the same geometry-primitive library (below).

### Geometry-primitive library (spec)

A small set of pure geometry constructors, each with a self-test vs analytic ground truth (length / clearance / radius), plus a KiCad emitter (PCB_TRACK + native PCB_ARC). The router AND hand touch-ups both call these — one set of validated primitives, no ad-hoc track math.

| Primitive | Signature intent | Self-test ground truth |
|---|---|---|
| `straight(p1, p2, w)` | one segment | length = ‖p2−p1‖ |
| `bend_45(corner, setback)` | 90° turn split into two 45° segments | each leg = setback; no acute angle |
| `arc(p1, p2, r)` | circular arc through endpoints, radius r | chord/sagitta vs r |
| `arc_tangent(...)` | arc tangent to two segments | tangency residual ≈ 0 |
| `chamfer(corner)` | 45° cut across a corner | cut leg geometry |
| `fillet(corner, r)` | rounded corner radius r | tangent radius = r |
| `teardrop(pad)` | teardrop fillet at pad neck | neck width ≥ trace width; IPC ratio |
| `taper(w1→w2)` | width transition | monotone width, no acute edge |
| `via_transition()` | track→via landing | annular + clearance preserved |
| KiCad emitter | primitives → PCB_TRACK + PCB_ARC | round-trip length match |

Implementation status: see `hardware/kicad/scripts/geometry_primitives.py` (stub signatures + docstrings + self-test, this PR) — design-stage, not wired into the engine yet.

---

## 5c. Factor of Safety everywhere (Sai-locked 2026-05-28, "very important — no cut-to-cut")

**THE design target is NEVER the raw limit.** Every physical quantity is sized to `limit ÷ FoS` (for ceilings) or `requirement × FoS` (for floors). This table is the routing FoS SSoT; it aligns with the already-implemented FoS gates (`audit_fos_current.py` G_FoS2, `audit_fos_thermal.py` G_FoS1, `audit_fos_cap_voltage.py` G_FoS3, `audit_fos_cap_ripple.py` G_FoS4, `audit_fos_pin_current.py` G_FoS5, `audit_via_current_capacity.py`) so routing inherits the same multipliers rather than inventing new ones.

| Quantity | Raw limit + source standard | FoS | Justification | Design target |
|---|---|---|---|---|
| **Trace width / ampacity (continuous)** | IPC-2152 ampacity nomograph (i = K·ΔT^0.44·Ac^0.725) | **1.5×** | 50% margin; industry standard for continuous load (matches G_FoS2) | width carries ≥ 1.5 × rated continuous current at ΔT budget |
| **Trace width / ampacity (burst)** | IPC-2152 | **1.2×** | 20% transient margin for short pulses (matches G_FoS2; e.g. +VMOTOR 280A burst) | width carries ≥ 1.2 × burst current |
| **Clearance / spacing ("no cut-to-cut")** | JLC fab min (0.0889mm/3.5mil std process) + IPC-2221B §6.3 voltage-derived spacing | **above fab min, never at it** | Routing to the exact fab minimum has zero manufacturing margin → over-etch/short risk. Target ≥ class spacing AND a margin above the fab floor. | spacing = max(IPC-2221B voltage-spacing, fab-min × headroom); never == fab-min |
| **Via current** | IPC-2152 + Brooks *PCB Currents* via ampacity | **1.5×** + extra vias | derate single-via capacity; spread current across ≥ ceil(I·1.5 / I_via) vias (matches `audit_via_current_capacity.py` FOS_VIA) | n_vias ≥ load × 1.5 / per-via capacity |
| **Annular ring & drill** | JLC std 0.10mm annular / 0.30mm drill; HDI 0.075mm/0.10mm (`BOARD_INVARIANTS.md` HDI spec) | **above fab min** | ring at fab min risks breakout on registration error | ring ≥ fab min + registration margin; HDI only on J18/J19 whitelist |
| **Impedance tolerance** | Hammerstad-Jensen Z0 (±4% model accuracy) + JLC controlled-Z ±10% process | **band, not point** | a single target W invites process drift outside spec | W chosen so Z0 stays within ±10% across the fab stack tolerance (50Ω SE / 90Ω diff per Tier 5) |
| **Loop-L margin** | commutation loop measured 0.1953nH/phase (STEP-6); ≤50mm² placement gate G3 | **margin below ringing threshold** | di/dt × L = switch-node ringing/EMI; design below the budget not at it | routed loop-L ≤ design budget with headroom; Tier-2 sim-verified |
| **Thermal rise margin** | Si MOSFET T_J reliability (T_J ≤ 75% T_J_max continuous, ≤90% burst) | **25% cont / 10% burst** | matches G_FoS1; junction never at rated max | trace/plane thermal contribution keeps T_J within FoS bound |
| **Voltage / creepage margin** | IPC-2221B creepage + JEDEC cap derating (V_rated ≥ V_max×1.4 elec/polymer, ×1.5 ceramic) | **1.4×–1.5×** | matches G_FoS3; clearance/creepage above the breakdown floor | creepage ≥ IPC-2221B for working voltage with margin |
| **Routing-process capacity (the root-cause fix)** | global planner door/corridor fill | **≤ 75–80% (never 100%)** | FoS on the routing process itself. Filling a corridor/door to 100% is the cut-to-cut that produced the 24/30 corner-paint — no slack for negotiated congestion or later nets. ISPD global-routing practice treats any overflow as failure; we add a headroom band below capacity. | door/corridor demand ≤ 0.75–0.80 × capacity at plan time |

**Planned FoS meta-gate** (described as planned; the script is NOT created this PR): a meta-check that every physical routing constraint **declares** a FoS, flagging any quantity sized to its raw limit (the G_META1 analogue for safety). It would parse `routing_topology.yaml` `factor_of_safety:` fields and fail if any physical quantity is present with no FoS declared. See `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` and the RULES_MANIFEST "Planned routing gates" subsection for the planned-gate inventory.

---

## 6. Audit gates per tier (extends existing `audit_routing.py`)

| Tier | Audit |
|---|---|
| 1 PDN | `check_plane_continuity()` (existing PLANE-ISLAND), `check_via_stitching_density()` (new for In3 +VMOTOR), `check_ir_drop()` (sim-driven) |
| 2 switching loops | `audit_loop_area.py` (placement) + `check_switching_loop_routing()` (new — verifies track stays in declared loop region) |
| 3 decoupling | `audit_decoupling.py` (placement) + `check_decoupling_via_length()` (new) |
| 4 critical analog | `check_kelvin_shunt_routing()` (new), `check_diff_pair_match()` (existing R19-style) |
| 5 signal highways | `check_track_width()` (existing per-class), `check_length_match()` (new per-CH ±2mm), `check_z0()` (Hammerstad-Jensen, existing in physics_primitives) |
| 6 bulk | `check_track_width()` minimum |

All called by `master_pre_merge.sh` per `[[feedback-master-gate-checklist]]`.

---

## 7. Sim verification per tier (per SIM_METHODOLOGY.md)

| Tier | Sim |
|---|---|
| 1 PDN | DC IR drop (ngspice), AC Z (scikit-rf), thermal local for plane regions (Elmer) |
| 2 switching loops | Transient ringing (ngspice + extracted L), near-field EMI (openEMS local) |
| 3 decoupling | Z-vs-freq vs target (scikit-rf), self-resonance check |
| 4 analog | Crosstalk to switching (openEMS), noise margin (ngspice) |
| 5 signal | TDR for impedance discontinuity, eye diagram (ngspice), reflection coefficient |
| 6 bulk | DRC + visual |

Sim FAIL → re-route (Step 6 of per-stage cycle in PHASE4V3_PLAN.md).

---

## 8. Topology lockfile (`docs/PHASE4V3_LOCKFILES/routing_topology.yaml`)

Per-net classification + per-component role. Schema:

```yaml
nets:
  +VMOTOR:
    tier: 1
    class: power-plane
    topology: plane-via-grid
    layer: In3.Cu
    width: plane
    constraint: ampacity 280A burst per IPC-2152
  
  DShot_CH1:
    tier: 5
    class: signal-highway
    topology: point-to-point
    source: J11.pin_DSHOT_CH1
    sink: U_MCU_CH1.pin_PWM_IN
    z0: 50
    layer: In2.Cu
    ref_layer: In1.Cu
    length_match_group: dshot_ch1234
    length_match_tolerance: 2mm
  
  # ... etc per net

components:
  C_VMOTOR_CH1:
    tier: 2
    role: cluster-member
    parent: Q_HS_CH1
    relation: bus-cap
    max_distance_mm: 5
    same_layer_as_parent: true
  
  C_DECOUP_U_DRV_CH1_VDD:
    tier: 3
    role: decoupling
    parent: U_DRV_CH1
    parent_pin: VDD
    max_distance_mm: 3
    same_layer_as_parent: true   # R25 enforced
  
  # ... etc per component
```

This is the SSoT for both placement (parent + max_distance) AND routing (tier + topology + constraints). One file, two consumers, no drift.

---

## 9. Master gate (every routing PR)

Master runs `master_pre_merge.sh`:
1. Tiers verified in order (Tier N+1 not allowed if Tier N FAIL)
2. `audit_routing.py` 6 checks
3. Per-tier sim PASS within threshold (SIM_METHODOLOGY.md)
4. `audit_routing_system.py` drift detection on methodology hashes
5. `master_audit_invariants.py` board invariants
6. Symmetry diff for mirrored channels

All must PASS on master HEAD post-merge.

---

## ROUTING_METHODOLOGY_HASH

```
ROUTING_METHODOLOGY_HASH = b8cfcc8d472e194cf2a70db161040df30dd3f7a1e89726a46c02aebd85674bc9
```
