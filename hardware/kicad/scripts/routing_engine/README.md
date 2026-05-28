# routing_engine — T1–T9 ground-truth validation suite (Engine Step 0)

The **validation foundation** for pcb.ai's mature routing engine
(`docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` §2/§3). This package is the
difficulty-graded **T1–T9 ground-truth test suite** that EVERY engine component
must pass against KNOWN ground truth — *not* against "looks routed" — before it
touches the real board (CH1 is the graduation exam, design §3 Step 8).

**This Step-0 commit contains ONLY** the fixture format, the 9 fixtures, and the
solver-agnostic test runner. There is **NO router/engine algorithm code here**.
Engine components (Phase A capacity pre-check, cyclic-VCG/left-edge, layer
assignment, Phase B global plan, Phase C fill) register as *pluggable solvers*
against this suite in later steps.

Why this exists: CH1 signal routing plateaued at 24/30 because the cooperative
router is pure detailed routing with no global capacity phase. These fixtures
reproduce that failure class (T3/T4/T9) at real feasibility boundaries so the
fix is proven, not asserted.

---

## Files

| File | Role |
|---|---|
| `fixtures.py` | The fixture FORMAT (dataclasses) + the 9 T1–T9 fixtures + the closed-form math helpers (`interval_density`, `has_cycle`, `is_nested_river_order`, `_segments_cross`). |
| `run_suite.py` | The test-runner harness: `--self-check`, `--list`, and pluggable-`--solver` modes. |
| `README.md` | This file. |
| `__init__.py` | Package marker. |

Pure Python + stdlib. No KiCad/pcbnew, no numpy, no solver dependency. Pi-light.

---

## Fixture schema

A `Fixture` is a frozen dataclass (`fixtures.py`) with these fields. It is a
LIGHTWEIGHT ABSTRACT board-state (the design doc explicitly allows a
"board-state fixture"; Phases A/B operate on the abstract graph, not geometry),
keeping the ground truth hand-checkable and solver-agnostic.

| Field | Type | Meaning |
|---|---|---|
| `name`, `title`, `difficulty`, `tests` | str | identity + what engine capability it gates (design §3) |
| `layers` | tuple[`Layer`] | `Layer(name, role, plane_net)`; `role` ∈ {signal, plane}. Mirrors the 10L stackup (BOARD_INVARIANTS §Board geometry): 6 signal (F/In2/In4/In6/In8/B) + 4 plane (In1/In3/In7 GND, In5 +VMOTOR). Fixtures use a minimal subset. |
| `pins` | tuple[`Pin`] | `Pin(id, x_mm, y_mm, layer)` — terminals/pads. |
| `nets` | tuple[`Net`] | `Net(net_id, pin_ids, net_class, feasible_doors, match_group, skew_tol_mm)` — connectivity demand. `feasible_doors` declares which doors a net can use (the construction); `match_group`/`skew_tol_mm` for length-matched buses. |
| `doors` | tuple[`Door`] | `Door(id, x, y, width_mm, layers, capacity_tracks, passes)` — the SUPPLY. Mirrors BOARD_INVARIANTS §Subsystem I/O ports + §Highway reservations. `capacity_tracks = floor(width / track_pitch) × n_layers` (`Door.capacity_from_width`; track_pitch = trace_width + clearance, ROUTING_METHODOLOGY §0b Phase A item 1). |
| `obstacles` | tuple[`Obstacle`] | `Obstacle(id, x_min, y_min, x_max, y_max, kind, plane)` — `kind='body'` keep-out or `kind='plane_split'` (a GAP in a reference plane = return-path discontinuity, a HARD SI constraint). |
| `via_slots` | tuple[`ViaSlot`] | `ViaSlot(id, x, y, ic_side, hdi_only)` — escape via sites (HDI dog-bone fanout model, BOARD_INVARIANTS §HDI whitelist J18/J19). `hdi_only=True` slots exist only when HDI via-in-pad is enabled (the T9 escalation lever). |
| `ground_truth` | `GroundTruth` | `verdict` ∈ {ROUTABLE, INFEASIBLE, CONDITIONAL} + `metrics` (the provable optimum) + `witness` (encoded known solution) + `conditional_on`/`alt_verdict`/`alt_metrics`/`alt_witness` (the lever the verdict flips on). |
| `construction_proof` | str | the math proving the ground truth, re-derivable by hand. |

`CONDITIONAL` means the verdict flips on a NAMED lever: net **order** (T5),
**global-vs-greedy** (T3/T4), **plane-continuity hard constraint** (T6), or
**HDI** (T9). The base verdict + the lever-applied `alt_verdict` are both stored.

---

## Running

```bash
# 1. SELF-CHECK — re-derive every verdict from first principles, NO solver.
#    This is the trustworthiness gate: it must PASS on all 9 before any solver
#    is believed. It independently recomputes density / VCG cycles / demand-vs-
#    supply / segment-crossing / nested order / skew, asserts agreement with the
#    stored ground_truth, AND validates the encoded witness is a valid solution.
python3 hardware/kicad/scripts/routing_engine/run_suite.py --self-check

# 2. LIST — one line per case: verdict + key metric.
python3 hardware/kicad/scripts/routing_engine/run_suite.py --list

# 3. SOLVER — score a pluggable solver against ground truth (engine components
#    register here in later steps). NO solver ships in this commit.
python3 hardware/kicad/scripts/routing_engine/run_suite.py --solver mymod:solve
```

### Registering a solver

A solver is any callable `solve(fixture) -> dict`. Pass it as `module:callable`
to `--solver`. The returned dict reports the solver's findings; the harness
compares only the keys the case's ground truth defines and prints the delta.
Recognised keys (all optional):

```
verdict              "ROUTABLE" | "INFEASIBLE" | "CONDITIONAL"
optimal_track_count  int    (T1)
vcg_cyclic           bool   (T2)
min_doglegs          int    (T2 resolved)
routed_nets          int    (T3/T4/T9, under global planning)
vias_required        int    (T5)
direct_path_allowed  bool   (T6 — must be False)
achieved_skew_mm     float  (T7)
crossings            int    (T8)
overflow             int    (T9 — 0 only with HDI)
```

A solver passes a case when its `verdict` matches AND every metric it reports
matches ground truth within tolerance (1e-6). It "passes the suite" at 9/9.

---

## Per-case ground-truth table (so master can re-derive each by hand)

All numbers below are produced by `--self-check` recomputing them from the
fixture fields — no value is trusted from the stored `ground_truth` without an
independent re-derivation. Each cites its design-doc T-row + the standard.

| # | Verdict (→ lever) | Provable metric | One-line construction proof |
|---|---|---|---|
| **T1** baseline channel | ROUTABLE | optimal_track_count = **3** (= door supply) | Net spans n2,n3,n4 all cover column x∈[4,5] → local density = max interval overlap = **3**; VCG acyclic → left-edge achieves track count = density = 3 = supply. *(Hashimoto-Stevens 1971; Sherwani Ch.7)* |
| **T2** cyclic VCG | INFEASIBLE → ROUTABLE (1 dogleg) | min_doglegs = **1** | Terminals force VCG edges A→B (left col) AND B→A (right col) → directed 2-cycle → no consistent track order → infeasible dogleg-free; breaking 1 net (1 dogleg) drops one edge → acyclic → routable. *(Deutsch 1976; Sherwani Ch.7)* |
| **T3** saturated escape | CONDITIONAL → ROUTABLE (global) | greedy **1/2**, global **2/2**, short_slot_cap=**1** | Y reaches ONLY the short slot (cap 1); X reaches either. Greedy gives the cheap short slot to X → Y's lone resource gone → Y stranded. Global reserves short slot for Y, detours X → 2/2. *(the 24/30 trap; Sherwani order-dependence)* |
| **T4** greedy trap | CONDITIONAL → ROUTABLE (global) | greedy **2/3**, global **3/3**, supply=demand=**3** | Supply P=1,Q=2 (=3) = demand 3. M1 needs P only, M2 Q only, G either (P cheapest). Greedy G→P saturates P → mandatory M1 has no door → fail; unique global M1→P, M2→Q, G→Q → 3/3. *(greedy corner-paint)* |
| **T5** forced crossing | INFEASIBLE → ROUTABLE (1 via) | vias_required = **1**, signal_layers = **2** | A=(0,8)→(10,2) and B=(0,2)→(10,8) are an X; segments properly intersect → on ONE layer they short in EVERY order → infeasible single-layer; 1 via hops one net to a 2nd signal layer across the crossing → routable, 0 acute angles. *(topology-before-geometry; HCG)* |
| **T6** plane-split trap | CONDITIONAL → ROUTABLE (hard constraint) | direct_path_allowed = **False** | Direct y=5 path crosses the GND-plane split rect x∈[9,11],y∈[0,8] → return current discontinuity → HARD-reject; continuous detour (up to y=9, across, back) never enters the split → the answer. *(Ott; Howard Johnson; ROUTING_METHODOLOGY §9)* |
| **T7** matched bus | ROUTABLE | achieved_skew = **0.0** ≤ tol 0.2; bus_width=**3**=door_cap | Door cap = bus width 3 (congestion boundary). Base lengths 20.0/18.5/17.0 differ ≫ 0.20 tol; serpentine meander 0.0/1.5/3.0 equalises all to 20.0 → skew 0.0 ≤ tol; meander spacing 0.15 = trace width → no self-coupling. *(Howard Johnson skew)* |
| **T8** river | ROUTABLE | crossings=**0**, vias=**0**, min_tracks=**5**=N | Top order r1..r5 = bottom order r1..r5 (0 inversions) → N non-crossing rivers → planar single-layer, 0 vias; any vertical cut crossed by all N nets → N distinct tracks (lower bound), order-preserving route hits exactly N → provably minimum area. *(Sherwani river routing)* |
| **T9** infeasible honesty | INFEASIBLE → ROUTABLE (HDI) | overflow = **1** (no HDI) → **0** (HDI) | QFN south side: K=4 standard via slots (supply) vs K+1=5 escape nets (demand) → overflow = 5−4 = 1 > 0 → provably INFEASIBLE; correct deliverable = STOP + emit ledger + escalate, NOT a heroic route. HDI adds 1 slot → supply 5 = demand 5 → overflow 0 → ROUTABLE. *(the honesty test; DEEP_RESEARCH_2026-05-26 escape correction; Phase A ledger)* |

**Feasibility-boundary discipline** (design §2 "no toy cases"): every case sits
at demand = supply (T1, T4, T7, T8) or supply+1 (T9), or breaks the naive
single-approach (T2 cyclic, T5 crossing, T6 split), or reproduces the actual
greedy-failure class at the boundary (T3, T4). T1 is the only "easy" case and
exists as the regression sanity floor.

---

## Relationship to the meta-gates

These files are NOT named `audit_*.py` / `verify_*.py` and live in the
`routing_engine/` subdir, so they are correctly invisible to `audit_meta.py`
(non-recursive glob of `scripts/`) and `audit_meta_coverage.py` (G_META1, top-
level `audit_*`/`verify_*` only) — no orphan, no missing-artifact. Both meta
gates stay green. The planned engine gates (FoS-meta, acute-angle-reject,
door-capacity, escape-precheck) remain prose-only in `RULES_MANIFEST.md` until
their fix-script + audit-function artifacts exist (design §3 note).

## References

- `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` §2 (T1–T9 table) + §3 (build/gate sequence).
- `docs/ROUTING_METHODOLOGY.md` §0b (Phases A/B/C the engine consumes).
- `docs/BOARD_INVARIANTS.md` (doors = I/O ports + highways; 10L stackup; HDI whitelist).
- `docs/DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md` §14 (full literature: Sherwani; Hashimoto-Stevens 1971; Deutsch 1976; Sait & Youssef; Kahng/Lienig/Markov/Hu; Ott; Howard Johnson; ISPD contests).
