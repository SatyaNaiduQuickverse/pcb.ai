# Sim Methodology — per-tier physics-driven validation

**Single source of truth.** All sim scripts and PR reviews follow this.

Hash: SIM_METHODOLOGY_HASH = (TBD)

---

## 0. Principle

Per `[[feedback-physics-as-compass]]` + `[[feedback-sim-execution-gate]]` + `[[feedback-sureshot-over-sota]]`:

> Physics is the compass. Every claim needs a sim. Every sim needs 4-point evidence (R18).
> Lumped/analytical OK only as cross-check; FEM/FDTD/transient is truth.

---

## 1. The 4-point sim execution gate (R18, NEVER waive)

Per `[[feedback-sim-execution-gate]]`:

Every sim PR (or PR claiming sim evidence) must include:

| # | Evidence | What |
|---|---|---|
| 1 | **Result file in repo** | `.result` / `.vtu` / `.raw` / `.h5` / `.s2p` committed |
| 2 | **mtime > input mtime** | `stat result.dat` > `stat sim_input.sif` proves sim ran post-input |
| 3 | **Extract script output** | Numerical result derived from `extract_*.py` parsing result file, NOT copy-pasted |
| 4 | **Literal exec command in PR doc** | The exact bash/python command that ran the sim |

Master verifies all 4. Any missing → REJECT PR.

---

## 2. Sim tools (locked, per Phase 0)

Per `[[reference-am32-dead-time-units]]`, `[[reference-sim-claimed-not-executed]]`:

| Tool | Use case | Output type |
|---|---|---|
| **Elmer FEM** | Thermal (steady-state and transient), mechanical stress | `.vtu`, `.result` |
| **ngspice** | Electrical transient (SPICE), AC analysis, noise margin | `.raw` (`.option GEAR + RELTOL=5e-3` for convergence per `[[reference-pr98-ngspice-convergence]]`) |
| **openEMS** | EM near-field (EMI radiation, crosstalk), 3D FDTD | `.h5` |
| **scikit-rf** | S-parameter, PDN impedance Z-vs-freq, RF | `.s2p` + python plot |
| **physics_primitives.py** | IPC-2221 ampacity, Hammerstad-Jensen Z0, Pozar stripline, Erickson buck ripple | analytical cross-check |
| **KiCad DRC** | Manufacturing rule check | DRC report |

NO analytical handwave for primary validation. Analytical is cross-check only.

---

## 3. Per-tier sim list (placement + routing tiers)

### Placement Tier 1 (mechanical anchors)
- **No sim** (geometric only)
- DRC for mount-hole keep-out

### Placement Tier 2 (switching clusters)
- **Switching loop area** (geometric from layout extract) → cross-check with analytical L = μ₀·A/2π·ln(s/r)
- **Thermal local Elmer** for FET cluster temp rise at 100A burst (target T_J ≤ 90°C per spec)
- Output: loop area mm², T_J,cluster °C

### Placement Tier 3 (CH1 template)
- **Decoupling impedance** scikit-rf Z-vs-freq per IC.VDD vs target (target: |Z| < 10mΩ below 100MHz)
- **Analog noise margin** ngspice (shunt sense path: shunt → INA → MCU ADC) — measure noise V_rms at MCU input, target SNR ≥40dB

### Placement Tier 4 (mirrors)
- **Symmetry diff geometric** (existing `check_symmetry_partner_diff`)
- **Cumulative thermal Elmer** for 4-channel temp distribution at 100A burst per channel (target T_J ≤ 100°C per CH4 worst-case spec; current Phase 5c baseline 82.99°C)

### Placement Tier 5 (central + edge)
- **Full-board thermal Elmer** @ 100A burst all 4 channels (target T_J ≤ 100°C, T_max,board ≤ 110°C)
- **BEC rail IR-drop** ngspice DC analysis on +3V3/+5V/+9V trunks (target ΔV ≤2% per rail at peak load)

### Routing Tier 1 (PDN)
- **DC IR drop ngspice** on +VMOTOR plane with 280A burst — target ΔV ≤1% (4V tolerance on 14.8V batt)
- **AC PDN impedance** scikit-rf Z-vs-freq vs target curve — target |Z| < 100mΩ below switching freq
- **Thermal local Elmer** on plane regions where current density >5A/mm²

### Routing Tier 2 (switching loops, routed)
- **Transient ringing ngspice** with parasitic L from extracted layout — target overshoot ≤20% of Vds rating
- **Near-field EMI openEMS** around switching cluster — target |E| < threshold (TBD per Phase 6 EMC plan)

### Routing Tier 3 (decoupling routed)
- **Z-vs-freq scikit-rf** with via stub L from layout — target meets Tier 3 placement target with ≤10% degradation
- **Self-resonance** check — caps SRF brackets noise freq

### Routing Tier 4 (critical analog routed)
- **Crosstalk openEMS** from switching to analog traces — target induced noise <10% of signal level
- **Noise margin ngspice** with extracted parasitic — target SNR ≥40dB (degraded from Tier 3 placement target if needed)

### Routing Tier 5 (signal highways routed)
- **TDR ngspice** or skrf — Z discontinuity ≤10% along trace
- **Eye diagram ngspice** with DShot edge rates (10ns) — target eye opening ≥60% UI
- **Length match** geometric verification ±2mm per CH group
- **Reflection coefficient** at branches ≤0.1

### Routing Tier 6 (bulk routed)
- DRC clean
- Visual review

### Cumulative (after each subsystem PR per Stage cycle Step 7)
- **Full-board thermal Elmer** with all routed power planes + tracks
- **Full-board EMI farfield openEMS** (Phase 6 EMC scope)
- **Ground bounce ngspice** with switching transients in CHn + measure noise at MCU GND pin
- **BEMF crosstalk openEMS** — switching CHn to BEMF refs other channels

---

## 4. Sim execution discipline

### Where sims live
- Inputs: `sims/<phase>/<subsystem>/<sim_type>/inputs/`
- Outputs: `sims/<phase>/<subsystem>/<sim_type>/results/`
- Extract scripts: `sims/<phase>/<subsystem>/<sim_type>/extract_*.py`
- Run scripts: `sims/<phase>/<subsystem>/<sim_type>/run.sh`

### Per-PR sim doc structure
Every sim PR includes a `SIM_REPORT.md` section with:
```
## Sim N — <type> on <subsystem>

**Tool**: <Elmer/ngspice/openEMS/scikit-rf>
**Inputs**: <list .sif/.cir/.xml + git hash>
**Run command**: <exact bash>
**Result file**: <path, mtime>
**Extract output**: <numerical result via extract_*.py>
**Target**: <number from SIM_METHODOLOGY.md>
**PASS/FAIL**: <determination + margin>
**Per-component breakdown**: <if cumulative, list per-CH/per-S>
```

### Cross-check (sureshot > SOTA)
For high-stakes results (final thermal, final EMI), run TWO independent sims:
- Primary: FEM/FDTD (Elmer / openEMS) — geometry-aware
- Cross-check: analytical (physics_primitives.py) — sanity check

If divergence >20%, investigate. Per `[[reference-averaging-masks-local-failure]]` — always per-component breakdown for cumulative.

---

## 5. Targets (cited)

### Thermal
| Metric | Target | Source |
|---|---|---|
| T_J,FET @ 100A burst | ≤90°C (10°C margin to 100°C limit) | TI CSD18540Q5B datasheet T_J,max |
| T_max,board | ≤110°C | FR4 derating, IPC-9701 |
| Temp rise via cluster | ≤30°C above ambient | Elmer Phase 4c baseline |

### Electrical (power)
| Metric | Target | Source |
|---|---|---|
| +VMOTOR IR drop @ 280A burst | ≤1% (≤150mV) | Erickson — keeps bus regulation tight |
| BEC rail IR drop @ peak load | ≤2% per rail | TPS54560 datasheet load reg |
| Switching overshoot on Vds | ≤20% of Vds rating | IRFR3711 100V FET → ≤120V overshoot |

### Electrical (signal)
| Metric | Target | Source |
|---|---|---|
| DShot eye opening | ≥60% UI | DShot 600 1.67µs UI, edge ~10ns |
| Z0 50Ω trace tolerance | ±5% | Hammerstad-Jensen + Polar Si9000 |
| Diff pair match | ±0.5mm | USB 2.0 / DDR practice |
| Decoupling |Z| <100MHz | ≤10mΩ | Bogatin Ch. 5 target |
| Crosstalk switching → analog | ≤10% signal level | Ott Ch. 9 |
| Ground bounce at MCU GND | ≤200mV peak | TTL noise budget |

### EMI (Phase 6 scope, preliminary targets)
| Metric | Target | Source |
|---|---|---|
| Radiated emissions 30MHz–1GHz | ≤CISPR 22 Class B | FPV use case civilian |
| Conducted emissions 150kHz–30MHz | ≤CISPR 22 Class B | same |

Phase 6 will lock these post-routing.

---

## 6. Sim cross-check vs Phase 5c baseline

Phase 5c final cumulative thermal sim gave T_J = 82.99°C @ 100A burst with prior placement. Phase 4-v3 REDO must NOT regress this. Specifically:

| Phase | T_J @ 100A burst | Status |
|---|---|---|
| Phase 4-v2 (current master, broken) | 82.99°C | Pre-REDO baseline |
| Phase 4-v3 Stage 2 (CH1 placed+routed) | TBD; must ≤90°C (CH1 alone less heat-coupled) | Target |
| Phase 4-v3 Stage 5 (all 4 channels) | TBD; must ≤100°C, ideally ≤90°C with improved loop layout | Target |
| Phase 4-v3 Stage 10 (full board) | TBD; must ≤100°C, ideally ≤83°C (preserve Phase 5c baseline) | Target |

If REDO regresses T_J: HALT, investigate (likely routing change effect), fix before next stage.

---

## 7. Master gate (every sim PR)

Master runs:
1. **4-point evidence check** (R18) — all 4 must be in PR
2. **Cross-check sim re-run** independently on master's clone (per `[[feedback-master-sim-cross-check]]`-class discipline)
3. **Per-component breakdown** present (per `[[reference-averaging-masks-local-failure]]`)
4. **Target met** with explicit margin reported
5. **No silent regression** vs prior baseline

All must PASS for PR approval.

---

SIM_METHODOLOGY_HASH = (placeholder; computed by `audit_routing_system.py --write` after lock)
