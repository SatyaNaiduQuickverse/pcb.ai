# Routing Engine — Build + Validation Plan (DESIGN, for review)

**Date**: 2026-05-28
**Genre**: build + validation plan (companion to the methodology SSoT).
**Status**: DESIGN review artifact. Reviewed by Sai + master BEFORE any engine
algorithm code is written. This doc contains the executive architecture summary,
the T1–T9 validation suite, the component build+validate sequence, the
SURESHOT/HEURISTIC inventory, and the honest-gaps list. **Methodology details
are NOT duplicated here — they live in `docs/ROUTING_METHODOLOGY.md` §0b
(Phases A/B/C), §5b (geometry policy), §5c (FoS-everywhere table).** This doc
points to that SSoT.

**Trigger**: CH1 signal routing plateaued at 24/30 because our cooperative
router (`docs/MASTER_COOP_ROUTER.md` v1→v8) is pure detailed routing with no
global capacity phase (`docs/DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md`).
This plan grounds the mature engine that fixes the root cause, and the
ground-truth test suite that gates every component before it touches the board.

**Do NOT duplicate**: methodology → ROUTING_METHODOLOGY.md; the current tool
spec → MASTER_COOP_ROUTER.md; the literature synthesis →
DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md; zones/highways/stackup/HDI →
BOARD_INVARIANTS.md; lessons → ROUTING_LESSONS.md (L10–L12 added this PR).

---

## 1. Executive architecture summary (one paragraph)

The engine adopts the canonical two-phase VLSI paradigm and adds it as the
missing front-end to our existing detailed router. **Phase A** (SURESHOT,
deterministic counting) builds a routing-resource capacity graph and a per-IC-side
escape demand/supply ledger and emits a verdict — ROUTABLE / NEEDS-HDI /
NEEDS-PLACEMENT-CHANGE / INFEASIBLE — *up front*, before any geometry; if not
ROUTABLE it STOPS and escalates rather than plateauing after burning compute.
**Phase B** (generic graph; SURESHOT verdicts + bounded HEURISTIC refine) plans
nets onto corridors with capacity headroom (FoS-on-process: doors/corridors
filled ≤75–80%, never 100% — the root-cause fix for corner-painting), treats
DOORS (corridor cross-sections = the BOARD_INVARIANTS I/O ports + interior
channel mouths) as first-class objects, orders nets through each door
(topology-before-geometry), and pre-assigns via slots. **Phase C** (the existing
`route_subsystem_cooperative.py`, demoted to region filler) fills exact tracks
inside each globally-planned, capacity-certified region; A* lives ONLY here,
bounded and expansion-capped. Geometry is octilinear-by-default with teardrops
everywhere and sim-driven local fillets on high-current corners (no global
chamfer rule). Real physics sims (proxy analytical inner loop; openEMS/Elmer/
ngspice as the only binding verdict, gated by the sim-execution-gate) inform net
ordering, complexity spend, and HDI escalation. Everything is gated against the
T1–T9 ground-truth suite before the engine touches CH1, and CH1 is the
graduation exam (CH2/3/4 are pure mirror transforms).

For the full methodology, see ROUTING_METHODOLOGY.md §0b/§5b/§5c.

---

## 2. T1–T9 validation suite (difficulty-graded, KNOWN ground truth)

Each case is a small synthetic `.kicad_pcb` (or board-state fixture) whose
routable/infeasible verdict is **provable by construction** (we set capacity vs
demand). Build moderate→hard. No toy cases — the bar is *demand-meets-or-exceeds-
supply* and *known ground truth* (matching the ISPD contest discipline: any
overflow is strictly inferior; Deutsch's-difficult-example-class hardness;
demand≈supply escape boundaries). Each engine component must pass its T-cases
against ground truth — not against "looks routed" — before integration.

| # | Difficulty | What it tests | Construction | Ground truth | Pass criterion |
|---|---|---|---|---|---|
| **T1 — baseline-routable channel** | moderate | detailed channel fill / left-edge; baseline sanity | 2-layer channel, ~10 nets, density = tracks available, **acyclic VCG** | **ROUTABLE** (provable: acyclic VCG + density ≤ track supply) | all nets routed, 0 DRC, track count = left-edge optimum |
| **T2 — layer-assignment / cyclic VCG** | medium | VCG cycle detection; dogleg insertion; "report infeasible, don't thrash" | same channel, terminals arranged to force a VCG 2-cycle (A→B and B→A) | **INFEASIBLE dogleg-free; ROUTABLE with one dogleg** | engine detects the cycle, reports it, then resolves with exactly one dogleg/via |
| **T3 — saturated escape field (reproduces our trap)** | hard | global phase + most-constrained-first ordering; *miniature of the 24/30 bug* | corridor where the globally-optimal plan routes net X the long way so most-constrained net Y gets the short slot; capacity = exactly enough iff X detours | **ROUTABLE only with global planning / most-constrained-first; greedy shortest-first strands Y** | global plan completes all nets; greedy detailed-only reproduces the plateau (proves the global phase is the fix) |
| **T4 — greedy-trap channel** | hard | global plan beats greedy on a corridor where greedy paints into a corner | a channel where a locally-cheap first choice blocks a later mandatory net; a non-greedy global assignment succeeds | **ROUTABLE with global plan; greedy fails** | global plan routes 100%; greedy detailed-only fails ≥1 net |
| **T5 — forced crossings / net-ordering** | medium | net ordering through a door; topology-before-geometry | two+ nets that must cross; single-layer ordering is forced | **INFEASIBLE on 1 layer in wrong order; ROUTABLE with correct order + 1 via** | engine picks the order + inserts exactly the required via(s); no acute angles |
| **T6 — return-path / plane-split trap** | medium | SI hard-constraint enforcement in the cost field | a critical net whose shortest path crosses a plane split; a longer path stays over a continuous reference | **ROUTABLE only if plane-continuity is treated as a HARD constraint** (short path rejected) | engine refuses the split-crossing path, routes the continuous-reference path |
| **T7 — matched-bus-under-congestion** | hard | length-match + completion together (serpentine within spacing) under congestion | a small bus that must be length-matched to a skew tolerance in a congested region | **ROUTABLE with all nets length-matched within tolerance** | all routed + intra-group skew ≤ tolerance + meander spacing ≥ trace width (no self-coupling) |
| **T8 — river / topological** | medium | river routing (SURESHOT order-preserving) + rubber-band topology | nets with the same left-to-right order on both boundaries, no crossings | **ROUTABLE single-layer, provably minimum area** | river-routed planar, minimum area, 0 vias |
| **T9 — GENUINELY-INFEASIBLE honesty test** | stretch / hard | the escalation logic: detect infeasibility → STOP + escalate + emit demand-vs-supply proof | T4-style QFN escape + one net beyond supply, no HDI allowed | **INFEASIBLE — the only correct answer is STOP + escalate + emit the ledger; then ROUTABLE once HDI via-in-pad enabled** | engine emits INFEASIBLE verdict + demand-vs-supply proof, does NOT attempt a heroic route; re-runs ROUTABLE with HDI |

**Why these are genuinely hard** (Sai requires real difficulty): T3/T4/T9
reproduce our actual failure class at known feasibility boundaries (demand =
supply, or supply+1). T2/T5/T6 each break the naive single-approach. T7
combines two constraints (length-match + completion) that are easy alone and
hard together. T8 is the clean SURESHOT river case. T1 is the only "easy" one
and exists as a regression sanity floor.

**Discipline**: build the suite FIRST; validate each engine component against
it; only then point the engine at the real board. Ground-truth verdicts are
reproducible from the fixture + git SHA (sim-execution-gate discipline,
`[[feedback-sim-execution-gate]]` + `[[feedback-sureshot-over-sota]]`). The
T-fixtures themselves are NOT yet built — this is the design specifying them.

---

## 3. Component-by-component build + validate sequence

Each engine part passes its T-cases before integration. CH1 is the GRADUATION
exam — the engine does NOT touch the real board until all parts validate. CH1
stays FROZEN at the 24/30 checkpoint meanwhile (no regression risk to merged
work). Pi-memory bound: Phase A/B run at coarse gcells (cheap, Pi-resident);
fine detailed A* is the Phase-7 x86 op (`[[feedback-pi-bounded-subsystem-scope]]`).

| Step | Component | Class | Validate against | Gate before next |
|---|---|---|---|---|
| 0 | T1–T9 fixtures (build the suite) | — | construction proof per case | each fixture's verdict re-derivable by hand |
| 1 | Geometry-primitive library + KiCad emitter | SURESHOT | self-tests vs analytic ground truth (length/clearance/radius); round-trip emit | all primitive self-tests PASS |
| 2 | Phase A capacity graph + escape pre-check | SURESHOT | T4, T9 (demand/supply ledger + verdict) | correct ROUTABLE/INFEASIBLE on T4/T9 |
| 3 | Cyclic-VCG / density / left-edge | SURESHOT | T1, T2, T8 | optimal track count on T1; cycle reported on T2; river minimum-area on T8 |
| 4 | Layer assignment + via minimization | SURESHOT (unconstrained) / HEURISTIC (via-min) | T5, T6 | correct via insertion T5; plane-continuity hard-constraint T6 |
| 5 | Phase B global plan + DOORS + net ordering | SURESHOT verdicts + HEURISTIC refine | T3, T4, T5 | global plan beats greedy on T3/T4; door ordering on T5; all doors ≤ headroom fill |
| 6 | Phase C integration (demote cooperative router) | bounded HEURISTIC | T7 + re-run T1–T6 end-to-end | length-match T7; no regression on T1–T6 |
| 7 | Sim-intelligence loop (proxy + strong-sim) | — | per-tier sim PASS (ROUTING_METHODOLOGY §7) | strong-sim binding verdicts via sim-execution-gate |
| 8 | **CH1 graduation** | — | full CH1 on the canonical board | all prior steps green; CH1 routes past 24/30 with 0 new shorts; then mirror CH2/3/4 |

The planned gates that bind these steps (FoS-meta, acute-angle-reject,
teardrop-coverage, door-capacity, escape-precheck) are inventoried in
`docs/RULES_MANIFEST.md` "Planned routing gates (not yet implemented)". They are
prose-only until their fix-script + audit-function artifacts exist (so the
declared-but-missing meta-check and the orphan-audit meta-check stay green).

---

## 4. SURESHOT / HEURISTIC inventory

Lead with SURESHOT (provable verdicts) BEFORE invoking any heuristic; gate every
heuristic with the T1–T9 ground-truth suite. (Condensed from
DEEP_RESEARCH_2026-05-28 §11; aligned with ROUTING_METHODOLOGY §0b split.)

| Component | Class | Why |
|---|---|---|
| Escape demand/supply pre-check | **SURESHOT** | pure counting (boundary÷pitch, via-slot count vs demand) → proof of routable/infeasible per side |
| Left-edge channel routing on **acyclic** VCG | **SURESHOT** | interval-graph coloring = polynomial, optimal track count |
| Cyclic-VCG detection / density lower bound | **SURESHOT** | graph cycle detection; max-clique-as-density is exact |
| River routing (order-preserving, no-cross) | **SURESHOT** | provably minimum-area planar (nested intervals) |
| Layer assignment (unconstrained) | **SURESHOT** | polynomial graph coloring on the conflict graph |
| Bounded ILP / SAT ordered escape | **SURESHOT-but-bounded** | optimal-or-infeasibility-certificate — tractable only on small instances (one IC, one side) |
| Geometry primitives (length/clearance/radius) | **SURESHOT** | closed-form geometry with self-tests vs analytic ground truth |
| Constrained via minimization | **HEURISTIC** (well-approximated) | NP-hard in general |
| Net ordering (most-constrained / criticality / shortest-first) | **HEURISTIC** | order-dependent, no optimality guarantee; tie-break once global capacity is reserved |
| PathFinder negotiated congestion (the cooperative router) | **HEURISTIC (robust)** | converges if a solution exists in the resource graph; plateaus when no slack (NOT a capacity planner) |
| Rubber-band topology refine / shove | **HEURISTIC** | topology-planning heuristic; geometrization is the deterministic part |
| Global maze rip-up & reroute | **HEURISTIC** | order- and parameter-dependent |
| Detailed A* in a bounded region | **SURESHOT path / HEURISTIC overall** | finds shortest path in the GIVEN region; per-net-greedy across nets is heuristic |

---

## 5. Honest gaps (where theory does not cleanly apply to our 10L/HDI/100A ESC)

Carried from DEEP_RESEARCH_2026-05-28 §13; not re-argued here, summarized so the
reviewer sees the limits the engine must respect:

1. **Classical channel/river theory ports as PARADIGM, not literal algorithm** —
   we are 10-layer mixed-direction cluster layout, not 2-layer Manhattan rows.
   The VCG/HCG/density/dogleg formalism is an analysis lens for our corridors
   and applies to specific sub-regions; we cannot run a textbook channel router
   on the whole board.
2. **HDI micro-via / via-in-pad is barely in the classic VLSI literature** —
   our full-stack-via discipline (the +46-shorts and v6 HDI-short lessons in
   MASTER_COOP_ROUTER) is MORE specialized than the textbooks, which assume
   through/full-stack vias. The engine keeps our hard-won full-stack via
   validation; theory will not supply it.
3. **SI constraints are HARD for us, weighted-soft in EDA tools** — commutation
   loop-L, gate-drive return adjacency, current-sense shielding are *correctness*
   constraints (a "routed" board violating them fails in hardware), so they are
   graph-hard constraints, not cost terms.
4. **Genuine geometric infeasibility at 0.5mm QFN pitch** — no router can route
   what does not fit. Theory's honest contribution is *detecting and proving*
   infeasibility early (escape pre-check) and naming the escalation
   (HDI/placement/package), NOT making it routable. The engine's job at the wall
   is a correct VERDICT + escalation, not a heroic route (the central
   DEEP_RESEARCH_2026-05-26 correction; T9 enforces it).
5. **Pi memory forces subsystem-scoped global routing** — coarse-gcell global on
   the Pi; fine detailed A* is the Phase-7 x86 op.
6. **R19 symmetry sits outside standard routing theory** — classical routers do
   not preserve N-instance geometric symmetry. CH1 routes, then transforms to
   CH2/3/4 (mirror_X/mirror_Y per BOARD_INVARIANTS); the global plan must be
   mirror-consistent.

---

## 6. References

Methodology + literature are fully cited in:
- `docs/ROUTING_METHODOLOGY.md` §0b/§5b/§5c (engine methodology + geometry + FoS).
- `docs/DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md` §14 (full textbook +
  paper + benchmark citation list: Sherwani; Sait & Youssef; Kahng/Lienig/
  Markov/Hu; Ritchey; Howard Johnson; Bogatin; Ott; Lee 1961; Hart-Nilsson-
  Raphael 1968; Hashimoto-Stevens 1971; Deutsch 1976; McMurchie-Ebeling 1995;
  Dai/Dayan SURF rubber-band; Yan-Wong SAT escape; dual-node network-flow ILP
  PMC8056246; ISPD 2008/2011/2018 contests).
- `docs/DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md` (escape-density vs
  layer-capacity decision table + 2026-05-28 diagnosis correction; IPC-2221C;
  Altium/NWES BGA escape).
- `docs/BOARD_INVARIANTS.md` (zones / I/O ports = board-edge doors / highways /
  10L stackup / HDI whitelist).
- FoS standards: IPC-2152 (ampacity), IPC-2221B (clearance/creepage), Brooks
  *PCB Currents* (via ampacity, current crowding), JEDEC (cap derating) — as
  implemented in `audit_fos_current.py`, `audit_fos_thermal.py`,
  `audit_fos_cap_voltage.py`, `audit_fos_cap_ripple.py`, `audit_fos_pin_current.py`,
  `audit_via_current_capacity.py`.

## Per locked rulebook

- `[[feedback-edit-existing-dont-write-new]]` — single dated companion doc
  (genre = build+validation plan); methodology goes into ROUTING_METHODOLOGY.md,
  not duplicated here.
- `[[feedback-sureshot-over-sota]]` — SURESHOT/HEURISTIC inventory (§4); lead
  with provable components; T1–T9 ground-truth gating.
- `[[feedback-sim-execution-gate]]` + `[[feedback-sim-artifact-must-be-canonical]]`
  — strong-sim is the only binding verdict; reproducible from fixture + SHA.
- `[[feedback-physics-as-compass]]` — every constraint physics-derived (capacity,
  return-path, loop-L, crosstalk, ampacity).
- `[[feedback-no-gui-session-autonomous-only]]` — at the wall, the answer is an
  autonomous correct verdict + escalation (HDI/placement/package/layers), never
  a manual GUI fallback.
- `[[feedback-symmetry-preserves-work]]` — CH1 template + mirror transforms.
