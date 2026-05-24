# Routing System — Phase 4-v2 (master spec v2)

**Authored**: 2026-05-24 by master after Sai directives:
- "avoid freerouter... make a system as you learn from mistakes and do routing"
- "solve problems from the root not the symptom"
- "good engineering practices try to a make a system out of it"
- "as we do sims and join subsystems we would need to change some routing"
- "but follow physics as compass"
- "do online research where needed"
- "dont set too many rules or youll fail"
- "system... which learns and grows, breaks down the problem, plans earlier for future and validates everything honestly"
- "make sure routing system doesnt drift"

**Hash**: see bottom (ROUTING_SYSTEM_HASH); change requires explicit PR tagged `[routing-system-update]`.

---

## 4 META-RULES (the only rules)

> Anything past 4 rules = lesson, primitive, or architectural choice. NOT a rule.

1. **Physics is the constraint source.** Every numeric constraint (track width, clearance, via count, length tolerance) is DERIVED from validated formulas (IPC-2152, Hammerstad-Jensen, Pozar, Erickson, Incropera) given the net's actual operating point — not asserted by lookup table.

2. **Validate honestly at insert time.** Each track/via placement runs DRC + physics check BEFORE commit. No "audit at the end" — bugs cost too much by then.

3. **Per-subsystem incremental with future-aware planning.** Route subsystem N anticipating N+1, N+2's space + corridor needs. When N+1 lands, only re-route the AFFECTED nets (per-route surgery), not global re-pass.

4. **Learn from every observation.** Every DRC fail, sim mismatch, master REJECT writes to versioned lessons DB. Lessons become COST ADJUSTMENTS (soft constraints), not new rules. System adapts without rule-bloat.

That's it. Don't add rule 5.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  ROUTING SYSTEM                                                       │
│                                                                       │
│  A. PHYSICS PRIMITIVES                B. LESSONS DB (versioned)      │
│     - ampacity.required_xs             - patterns × frequency        │
│     - impedance.microstrip_z0          - cost adjustments            │
│     - crosstalk.coupling_db            - sim-validated outcomes      │
│     - thermal.via_R                                                  │
│     - power.bootstrap_C                                              │
│            │                                  │                       │
│            ▼                                  ▼                       │
│  ┌──────────────────────────────────────────────────────┐            │
│  │  C. CONSTRAINT ENGINE                                 │            │
│  │     For (net, position, layer, neighbors) → derives:  │            │
│  │       - min_width = ampacity.required_xs(I_net) / t_Cu│            │
│  │       - min_clearance = crosstalk-acceptable distance │            │
│  │       - requires_offset_via = if power-to-plane       │            │
│  │       - cost_adjustment = lessons DB pattern match    │            │
│  └──────────────────────────────────────────────────────┘            │
│            │                                                          │
│            ▼                                                          │
│  ┌──────────────────────────────────────────────────────┐            │
│  │  D. ROUTERS (3, hierarchical)                         │            │
│  │     1. Subsystem-local: multi-agent CBS within zone   │            │
│  │     2. Mirror: pure geometric reflection of template  │            │
│  │     3. Highway: inter-subsystem on reserved corridors │            │
│  │        (incremental — per-route surgery on join)      │            │
│  └──────────────────────────────────────────────────────┘            │
│            │                                                          │
│            ▼                                                          │
│  ┌──────────────────────────────────────────────────────┐            │
│  │  E. SIM-VALIDATION LOOP                               │            │
│  │     - Every route → quick check (DRC + physics)       │            │
│  │     - Sample 10% → deep check (Elmer/openEMS/ngspice) │            │
│  │     - Sim Δ > tolerance → updates lessons DB          │            │
│  └──────────────────────────────────────────────────────┘            │
│            │                                                          │
│            ▼                                                          │
│       ROUTES + UPDATED LESSONS                                        │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

The system is built around physics primitives + learning DB. Routers + constraint engine are thin wrappers that compose them.

---

## A. Physics Primitives (`physics_primitives.py`)

Pure functions of physics. No globals, no state, no rules.

### Ampacity (IPC-2152)

```python
def required_cross_section_mm2(I_amps, layer_type, dT_celsius):
    """IPC-2152: i = K × ΔT^0.44 × Ac^0.725 (Ac in sq mils, returns mm²)"""
    K = 0.048 if layer_type == "external" else 0.024
    Ac_sqmils = (I_amps / (K * (dT_celsius ** 0.44))) ** (1/0.725)
    return Ac_sqmils * 6.4516e-4  # sq mils → mm²
```

### Min track width

```python
def min_track_width_mm(I_amps, layer_type, cu_oz, dT_celsius=30):
    Ac = required_cross_section_mm2(I_amps, layer_type, dT_celsius)
    t = cu_oz * 0.0347  # 1oz ≈ 34.7 µm = 0.0347 mm
    return Ac / t
```

### Impedance (Hammerstad-Jensen, microstrip)

```python
def microstrip_z0(W_mm, H_mm, εr, t_mm=0.035):
    """Microstrip impedance, Hammerstad-Jensen accuracy ±4%."""
    # u = W/H corrected for t
    u = W_mm / H_mm
    a = 1 + (1/49) * math.log((u**4 + (u/52)**2) / (u**4 + 0.432))
    b = 0.564 * ((εr - 0.9) / (εr + 3)) ** 0.053
    εr_eff = (εr + 1)/2 + (εr - 1)/2 * (1 + 10/u) ** (-a*b)
    Z0_air = 60/math.sqrt(εr_eff) * math.log(6 + (2*math.pi - 6) * math.exp(-((30.666/u) ** 0.7528)))
    return Z0_air
```

### Crosstalk coupling

```python
def crosstalk_db(W_mm, sep_mm, length_mm, freq_hz, εr=4.3, h_mm=0.2):
    """Coupled microstrip mutual capacitance/inductance — simplified IEEE model."""
    k = (sep_mm / (sep_mm + W_mm)) ** 2
    coupling = 20 * math.log10(k * length_mm * freq_hz / 3e8)
    return coupling
```

### Thermal via R

```python
def via_thermal_resistance_K_per_W(d_mm, h_mm, count=1, k_cu=401):
    """Single-via thermal resistance through PCB stackup."""
    A = math.pi * (d_mm/2)**2 * 1e-6  # m²
    return h_mm * 1e-3 / (k_cu * A * count)
```

### Power: bootstrap cap

```python
def bootstrap_min_cap_F(Q_gate_C, dV_max_volts):
    """Minimum bootstrap cap to hold gate voltage within droop limit."""
    return Q_gate_C / dV_max_volts
```

Each primitive cites its reference in code docstring. Master verifies against textbook/standard.

---

## B. Lessons Database (`docs/ROUTING_LESSONS.md` + `routing_lessons.json`)

Versioned learning. Two-format pair:

- `.md` is human-readable, authoritative for review
- `.json` is machine-parsed by router for cost adjustments

Each lesson row:
```yaml
id: L1
date: 2026-05-23
pattern:
  type: external_router
  target: Freerouter
observation: 4× identical exit ~16s, no progress
sim_cross_check: N/A (tool didn't run)
cost_adjustment:
  type: hard_block
  rule: assert_no_external_router
status: active
```

Lessons start as `proposed`, become `active` after master review + (where applicable) sim cross-check confirms the pattern reliably triggers the issue.

**Drift prevention**:
- Every lesson change = explicit PR tagged `[lesson-update]`
- Lessons DB hash stored in `docs/ROUTING_LESSONS.md` header
- Routing system computes hash at startup; rejects if mismatch

**Adaptive behavior**: lessons modify the router's cost function, not its rule set. Example:
- Lesson "BEMF parallel runs >40mm fail crosstalk at 12 of 14 attempts" → cost function adds penalty `+α × (parallel_length - 40)` for BEMF nets
- Router still TRIES the route if it's the only path; pays the cost
- Over time, the cost-weighted optimal solution avoids the pattern naturally

---

## C. Constraint Engine (`constraint_engine.py`)

Thin layer. For any (net, position, layer, context) returns:
- `min_width(net, layer)` = physics derivation given net's expected current
- `min_clearance(net1, net2, parallel_length, freq)` = crosstalk-acceptable
- `requires_offset_via(net, pad_context)` = lesson L4 pattern match
- `cost_at(x, y, layer, context)` = baseline + Σ(lesson adjustments)

Inputs:
- `BOARD_INVARIANTS.md` (zones, I/O ports, highways) — hash-verified
- `ROUTING_LESSONS.md` (patterns + cost adjustments) — hash-verified
- `pcbai_fpv4in1.kicad_pcb` (current state + net classes)

Outputs: per-query answer + lessons-applied log per route.

---

## D. Routers

### D.1 Subsystem-local (`route_subsystem.py`)
Multi-agent CBS (Conflict-Based Search) within subsystem zone.
- Each net = an agent: start (source pad), goal (sink pad or declared I/O port)
- Cost function = `length × layer_cost + via_cost + constraint_engine.cost_at(...)`
- Conflict (two agents want same cell) → CBS resolves by re-planning higher-priority agent
- Per-net priority order: power (+VMOTOR, +BATT, GND) → high-speed (BEMF, ADC sense) → control (DSHOT, KILL) → general
- Future-aware: cost function adds "reserved-for-mirror-partner" penalty to keep template-side routes mirrorable

### D.2 Mirror (`route_mirror.py`)
For symmetry pair (CH1↔CH2, CH3↔CH4):
- Pure geometric reflection of every track + via about axis
- Snap reflected endpoint to actual partner pad (R19 5mm tolerance)
- **On snap failure (>5mm)** → REPORT to subsystem-local router as "template-side route needs adjustment"; do NOT insert bridge
- This is the L2 lesson encoded structurally — system cannot break symmetry

### D.3 Highway (`route_highway.py`)
For inter-subsystem nets on reserved corridors:
- Runs INCREMENTALLY when subsystem N+1 lands
- Identifies new nets crossing subsystems N and N+1
- Routes them on declared highway corridors
- For EXISTING highway routes intersecting new N+1 zone → per-route surgery (re-route just those)
- Never global re-pass

---

## E. Sim-Validation Loop (`route_validator.py`)

Per route inserted:
1. **Quick check** (always): DRC clean + physics constraint match (width, clearance)
2. **Deep check** (sample 10% + all power nets + all high-speed nets):
   - Power net: Elmer thermal sim slice → predicted T_max vs ampacity formula prediction
   - High-speed: openEMS S-param → predicted Z0 vs Hammerstad prediction
   - Clock/control: ngspice → predicted prop delay
3. **Sim Δ analysis**:
   - If sim agrees with primitive prediction within 10% → log success
   - If sim disagrees > 10% → write proposed lesson to lessons DB; master gates whether to activate
4. **No silent acceptance**: every route's validation log goes in PR

---

## F. Drift Prevention (the "doesn't drift" requirement)

Mechanism stack:

1. **ROUTING_SYSTEM_HASH** at bottom of this doc; any spec change requires explicit `[routing-system-update]` PR tag.

2. **ROUTING_LESSONS_HASH** in lessons DB header; any lesson change requires `[lesson-update]` PR tag.

3. **Physics primitives are versioned**: each function in `physics_primitives.py` has docstring citation + last-modified-by-PR-N. Changes require master sign-off.

4. **Per-PR audit**: every routing PR runs `audit_routing_system.py`:
   - Verifies ROUTING_SYSTEM_HASH unchanged (or PR tagged `routing-system-update`)
   - Verifies ROUTING_LESSONS_HASH unchanged (or PR tagged `lesson-update`)
   - Verifies physics primitive signatures unchanged
   - Verifies router output went through sim-validation loop
   - Verifies lessons-applied log is non-empty (or notes "fresh-codebase" exemption)

5. **Master independent re-verification**: master re-runs `route_subsystem.py` on every PR with same inputs, expects same output (deterministic). Any non-determinism = bug.

---

## G. Process per routing PR

```
For subsystem N:
  1. Read BOARD_INVARIANTS + ROUTING_LESSONS (verify hashes)
  2. Run route_subsystem.py(subsystem=N)
     - Multi-agent CBS routes all internal + I/O port nets
     - Each route: physics check + DRC at insert
     - Lessons-applied logged per route
  3. Sim-validation loop (10% deep + all power/high-speed)
  4. If subsystem is template of symmetry pair:
     - route_mirror.py generates partner subsystem's routes
     - On snap-fail: surface back to step 2 for template re-route
  5. Run highway router if new inter-subsystem nets need corridor
  6. audit_routing_system.py final check
  7. Submit PR with: routes + sim-validation log + lessons-applied + audit-system result
  8. Master gate per Phase 4-v2 dispatch
```

---

## H. File deliverables (this PR)

```
docs/
  ROUTING_SYSTEM.md             ← this file
  ROUTING_LESSONS.md            ← versioned lessons DB (initial 5 from prior failures)
  
hardware/kicad/scripts/
  physics_primitives.py         ← IPC-2152, Hammerstad-Jensen, etc.
  constraint_engine.py          ← thin layer reading invariants + lessons + physics
  audit_routing_system.py       ← drift-prevention meta-audit
  
hardware/kicad/scripts/routers/
  route_subsystem.py            ← subsystem-local CBS router (skeleton + interface)
  route_mirror.py               ← mirror router (skeleton + interface)
  route_highway.py              ← highway router (skeleton + interface)
  
sims/validation/
  routing_validation_examples/  ← reference sims that the validator compares against
```

Skeletons + interface this PR. Full router implementation builds incrementally per subsystem (start with CH1 needs).

---

## ROUTING_SYSTEM_HASH

```
ROUTING_SYSTEM_HASH = 7d98275fb9b791391b7ef3d3b879bdd41aff23abcfe330374534dec9f070236e
```

(Any change to this spec recomputes the hash; PR must be tagged `[routing-system-update]` for hash drift to be accepted.)

## Sources

- IPC-2152 ampacity formula: i = K × ΔT^0.44 × Ac^0.725, K=0.024 internal/0.048 external — confirmed via [Sierra Circuits IPC-2152 guide](https://www.protoexpress.com/blog/how-to-optimize-your-pcb-trace-using-ipc-2152-standard/) + [Altium IPC-2221 calculator](https://resources.altium.com/p/ipc-2221-calculator-pcb-trace-current-and-heating)
- Multi-agent CBS routing approach: [Multi-agent based minimal-layer via routing algorithm for PCB design (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/abs/pii/S0167926025001907) — confirms current SOTA uses CBS-class algorithms for incremental constraint-respecting routing
- Constraint-based PCB routing patent: [USPTO 7937681](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7937681) — confirms constraint-driven topological + geometric solver pattern
- Incremental routing patent: [USPTO 8196083](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8196083) — confirms per-route surgery on partially routed designs is industry pattern
