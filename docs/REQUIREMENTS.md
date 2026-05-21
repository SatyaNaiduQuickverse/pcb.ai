# pcb.ai — project requirements

The contract documents for both product lines. Per **Rule 2 — contracts before
code (and schematic)**, every specification that crosses a system boundary
(power, motor wires, comms, mechanical, fab process) is locked here before
the corresponding phase opens. Changes go through PRs against this file.

Cross-references: `CLAUDE.md` §2 (project identity), `docs/DESIGN_PHASES.md`
(phase model), `docs/ENGINEERING_RIGOR.md` (non-negotiables), `docs/PCB_PLAYBOOK.md`
(toolchain + traps), `docs/OPEN_QUESTIONS.md` (decisions + pending).

---

## §fpv-4in1 — FPV 4-in-1 ESC (PRIORITY 1)

### Mission

Four-channel integrated electronic speed controller for FPV multirotor drones
(racing / freestyle / cinematic). Open-source AM32 firmware on our hardware.
Hardware design + reliability + brand are the IP; firmware is community-owned.

### Power

| Item | Spec |
|---|---|
| Input voltage | 6S LiPo / Li-ion (4.2 V × 6 = 25.2 V full; LVC at 3.5 V × 6 = 21 V) |
| Channels | 4 |
| Continuous current / channel | **70 A** |
| Peak / burst current / channel | TBD at Phase 2 from MOSFET selection + thermal sim; target ≥ 1.5 × continuous |
| Bus capacitance | Sized at Phase 2 from ripple analysis (ngspice + datasheet ripple-current rating) |
| Power topology | Single shared input rail → 4 × 3-phase half-bridges; independent low-side current shunts per phase per channel (12 shunts total) per AM32 hw-target convention |

### Comms

| Item | Spec |
|---|---|
| Input protocol | DShot 300, DShot 600 (auto-detect by AM32) |
| Bidirectional | Yes — RPM telemetry back to FC |
| Configuration | AM32 BLHeli-passthrough via FC (Betaflight / INAV / ArduPilot compatible) |
| CAN / UART / SBUS | Not in scope (FPV doesn't require) |

### MCU

| Item | Spec |
|---|---|
| Family | STM32G071 *or* AT32F421 |
| Pick gating | Phase 2 — JLCPCB assembly library coverage *and* AM32 hardware-target file availability (per Rigor §10, pull both fresh, not from memory) |
| Class | 32-bit Cortex-M0+, AM32-supported |
| Pin count | ≥ 32 pins (4 PWM × 3 phases + 4 current sense × 3 phases + 4 DShot inputs + comms / config / debug) |

### MOSFETs

| Item | Spec |
|---|---|
| Voltage class (V_DS) | ≥ 60 V (covers 25.2 V bus + motor back-EMF + factor-of-safety per playbook §Routing) |
| Continuous I_D | ≥ 120 A at T_J = 100 °C (50 % derating headroom over the 70 A continuous spec) |
| R_DS(on) target | ≤ 2.0 mΩ at 25 °C; ≤ 3.5 mΩ at 125 °C |
| Package | Single-FET PDFN5×6 or DFN8×8 class (dual-package avoided at this current for thermal isolation) |
| Specific part | TBD at Phase 2 against JLC library |

### Gate drivers

| Item | Spec |
|---|---|
| Topology | Half-bridge integrated, 4 × 3-phase = 12 driver channels total |
| Reference family | TI DRV83xx (DRV8300 / DRV8307 / DRV8323 — final pick at Phase 2) |
| Shoot-through protection | Required (independent per channel) |
| Dead-time | Per AM32 hardware-target convention (typically 0.5 – 1.5 µs) |

### Protection

- TVS diodes on input rail (per channel + bulk)
- HW overcurrent comparator (independent of firmware); target trip < 1 µs
- UVLO at MCU regulator level
- Reverse-polarity protection on input (P-MOSFET ideal-diode topology or fuse + Schottky)
- Per-phase low-side shunt monitoring (AM32 standard)

### Mechanical

- **Form factor NOT pre-constrained.** Phase 2.5 converges via:
  - Thermal sim: minimum board area for 4 × 70 A continuous at JLC stack-up + nominal prop-wash airflow
  - Layout sim: minimum routing density at JLC trace/space + via rules
  - Output: the larger of {physics-required area, nearest standard FPV stack pattern}
- **Stack-up**: 6-layer per playbook §Routing (signals on the two outer layers, four inner solid planes). Confirmed at Phase 4 placement.
- **Connectors**: TBD at Phase 2 (motor wires typically direct-solder pads; FC connector standard 8-pin JST-SH or similar)
- **Mounting**: Bolt pattern matches the converged form factor's standard once Phase 2.5 lands

### Fab + assembly

| Item | Spec |
|---|---|
| Fab | JLCPCB |
| DRC ruleset | JLCPCB's published capability spec (authoritative; per Playbook §Manufacturability — pull fresh per Rigor §10) |
| Assembly | JLCPCB SMT (production); BOM constrained to JLC parts library (basic + extended) or pre-flagged as hand-solder |
| Surface finish | ENIG (gold) for fine-pitch and corrosion resistance |
| Stack-up | JLC 6-layer standard (Phase 4 confirms specific layer thicknesses for impedance) |

### Validation regime — sim-heavy, single-fab-iteration target

Each sim is **validated against a canonical reference** per Rigor §4 before its
verdict is trusted. Sim alone never declares a subsystem done — Rigor §4 +
Playbook §Simulation.

**Required sims** (each per Phase 6 with PR-disposition if failing):

| Sim | Tool | Verdict |
|---|---|---|
| Thermal | Elmer FEM | MOSFET T_J ≤ 100 °C at 70 A continuous per channel, nominal + hot (50 °C) ambient |
| Power electronics | ngspice / LTspice | Switching waveforms, dead-time, ringing within snubber-designed envelope, dV/dt |
| SI / impedance | scikit-rf + Hammerstad-Jensen analytical | DShot trace impedance within spec, return-path continuity |
| 3D EM | OpenEMS | Switching-node antenna behavior; gate-drive parasitic inductance bounded |
| Power integrity | ngspice + transient profile | Rail droop ≤ X % at peak switching; bus-cap ripple within rating |
| Manufacturability | KiCad DRC against JLC rules + JLC parts library cross-check | Zero violations; all parts in-library or flagged hand-solder |

**Required bench** (single fab iteration, ~1–2 weeks integration sprint):

| Bench item | Purpose |
|---|---|
| Continuity check | Multimeter on every rail before first power-up |
| Power-up smoke test | Current-limited bench supply; watch for shoot-through / inrush failure |
| Gate-drive scope verification | Oscilloscope on switching nodes — verify dead-time, ringing within sim envelope |
| AM32 hw-target compile + flash | Our hardware-target file builds; flashes; boots |
| Motor spin (low duty) | 3S bench supply, single small motor per channel — basic commutation works |
| DShot communication | Verified against a Betaflight / INAV / ArduPilot FC |
| Sustained thermal calibration | 4 × 70 A continuous, IR camera + thermocouples; compare measured T_J to Elmer FEM verdict (Rigor §4 validation step) |

**Dropped vs. HV60 (FPV market norm):**

- No HALT (Highly Accelerated Life Test)
- No EMC pre-compliance certification (FPV is amateur / unlicensed)
- No formal MTBF claim
- No motor-parameter auto-ID validation regime (AM32 doesn't ship that feature)
- No sensorless observer tuning (AM32 is six-step / Bluejay-sinusoidal, not FOC)

---

## §hv60-family — HV60 commercial FOC family (PRIORITY 2 — stub)

> Filled at Phase 2.x of HV60 work, after FPV 4-in-1 is in fab.
> Outline locked here so future-us can pick this up cleanly.

### Locked outline

- **SKUs in build order**: ESC-HV60 (6–12S, 60 A cont., 100 A peak) → ESC-LV40 (4–6S, 40 A) → ESC-HV100 (6–12S, 100 A cont., 200 A peak) → future ESC-UHV (12–24S) → future integrated propulsion (motor + ESC)
- **MCU**: STM32G4 family across all SKUs (specific part per SKU, picked at each SKU's Phase 2)
- **Firmware base**: STM32 X-CUBE-MCSDK (free-for-STM32 license, not GPL)
- **Control**: true FOC, sensorless, plug-and-play motor auto-ID
- **Comms**: DShot 300/600 + CAN-FD + UART telemetry
- **IP rating**: IP55 baseline, IP67 optional per SKU
- **Reliability**: see §reliability-spec below
- **Fab**: JLCPCB SMT (same DRC ruleset as PL1)
- **Topology**: singular per-motor (one ESC per motor)
- **Use cases**: industrial mapping, inspection, payload, cargo, agri, delivery, defense

### Open at start of PL2

- Specific motor target per SKU (KV, pole count, prop class) → sets observer bandwidth
- Form factor (stack-mounted vs. arm-mounted)
- Cooling envelope (forced air, heatsink, conduction)
- Lab / bench access for the heavier validation regime (HALT, EMC)
- Ship target

---

## §reliability-spec — HV60 family factor-of-safety standard

The HV60 family is reliability-positioned. The PL1 FPV 4-in-1 does **not** carry
these obligations (FPV market norm). Locked principles for the HV60 line:

| # | Standard |
|---|---|
| 1 | MOSFET I_D derated to ≤ 60 % of datasheet rating at worst-case bus voltage + 25 °C ambient |
| 2 | MOSFET T_J ≤ 100 °C at continuous spec current (target, not 150 °C absolute max) |
| 3 | Bus capacitor ripple current ≤ 60 % of datasheet rated |
| 4 | Bus capacitor voltage derated ≥ 30 % over worst-case bus |
| 5 | HW overcurrent comparator (independent of firmware) — fast fault trip < 1 µs |
| 6 | Gate-drive shoot-through protection (independent per channel) |
| 7 | UVLO + OVLO at rail level |
| 8 | ESD protection on all external pins |
| 9 | IP55 conformal coating across line; IP67 optional per SKU |
| 10 | Burn-in test on every production unit before ship |
| 11 | HALT (Highly Accelerated Life Test) per new SKU before launch |
| 12 | Field-return MTBF target — set in conjunction with the project owner when HV60 work begins |

Modifying any of these requires a PR to this file with technical justification
and owner approval — same posture as `ENGINEERING_RIGOR.md`.

---

## Cross-doc references

- Rules: `CLAUDE.md` §3 (dev rules), §5 (working with owner), §6 (workflow)
- Rigor non-negotiables: `docs/ENGINEERING_RIGOR.md`
- Phase model: `docs/DESIGN_PHASES.md`
- Toolchain + hard-won lessons: `docs/PCB_PLAYBOOK.md`
- Master/worker protocol: `docs/MASTER_WORKER_PROTOCOL.md`
- Decisions + open items: `docs/OPEN_QUESTIONS.md`
