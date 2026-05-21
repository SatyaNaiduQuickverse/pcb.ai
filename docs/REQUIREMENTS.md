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
| Family | **AT32F421K8T7** (Artery) — closed at Phase 1 per OQ-006 |
| Class | 32-bit Cortex-M4 @ 120 MHz, 64 KB Flash, 16 KB SRAM, LQFP-32 |
| Firmware-per-MCU | AM32 single-motor build (`PCBAI_FPV4IN1_F421`) — same `.elf` flashed to each MCU on the 4-in-1 board |
| Pin count | ≥ 32 pins per MCU (3 PWM × 1 phase set + 1 current sense + 1 voltage sense + 1 DShot in + 1 telemetry out + comms / config / debug). NOTE: requires architectural cross-check — see open thread in Phase 1 PR description |
| Phase 2 lock-ins | Pin assignments, exact part SKU (-T7 LQFP-32 vs -U7 QFN-32), and the `K8` `.ld` script (vs the default `x6` 32 KB script AM32 ships) |

### MOSFETs

| Item | Spec |
|---|---|
| Specific part | **AOS AON6260** (closed at Phase 2b — see `docs/PHASE2B_MOSFET.md`) |
| Package | DFN5x6-8 (single-FET; dual-package avoided for thermal isolation) |
| Voltage class (V_DS) | ≥ 60 V (covers 25.2 V bus + motor back-EMF + factor-of-safety per playbook §Routing) — AON6260 = 60 V |
| Continuous I_D rating (datasheet) | ≥ 80 A at T_C = 25 °C (sanity floor; sim is the real gate) — AON6260 = 85 A |
| R_DS(on) | ≤ 2.0 mΩ typ @ V_GS = 10 V — AON6260 = 1.95 mΩ typ / 2.4 mΩ max |
| **Operating thermal target** | T_J ≤ 100 °C at 70 A continuous per phase, 60 °C ambient, still-air, JLC stack-up with reasonable cu pour, Elmer FEM validated against analytical 1-D — **operate-condition criterion** |
| Sourcing note | AOS-original AON6260 not in JLC SMT library. Prototype: hand-solder from DigiKey/Mouser. Production: consignment via JLC or qualify a second-source DFN5x6 60V part at Phase 2c |

Criterion revised 2026-05-22 from abstract T_C=100°C derating to operating-
condition T_J target — see Phase 2b PR rationale (PR #4) and the URGENT
trail in `docs/PHASE2B_MOSFET.md`.

#### Operating thermal envelopes (Phase 2b adjudication 2026-05-22)

| # | Envelope | Conditions | T_J target |
|---|---|---|---|
| 1 | Cruise | 40 A average / channel + still-air + 60 °C ambient | ≤ 100 °C |
| 2 | Peak / sustained throttle (rated continuous) | 70 A continuous / channel + prop-wash (h ≥ 80 W/m²·K) + heatsink | ≤ 100 °C |
| 3 | Stress / abs-max (survival) | 70 A continuous / channel + still-air | ≤ T_J_max = 150 °C (survives, not steady-state operation) |

### Gate drivers

| Item | Spec |
|---|---|
| Topology | Half-bridge integrated, 4 × 3-phase = 12 driver channels total |
| Specific part | **TI DRV8300DRGER** (primary, JLC C3655801) — closed at Phase 2c, see `docs/PHASE2C_GATEDRIVER_CURRENTSENSE.md` |
| Footprint-compat alternate | **Fortior FD6288Q** (JLC C328453) — same QFN-24 4×4 mm package + same drive class; pin-by-pin compat verified at Phase 3 schematic capture. Gives fab-time supplier flexibility. |
| Shoot-through protection | Required (built-in cross-conduction prevention in both DRV8300 and FD6288Q) |
| Dead-time (driver internal) | DRV8300: variable via DT pin resistor (150–2600 ns); FD6288Q: fixed 100–300 ns. Both ENFORCE dead-time at the MOSFET gate independent of MCU input timing. |
| Dead-time (AM32 MCU output) | **500 ns** (raw DTG register value 60 at 120 MHz TMR1 clock) — covers DRV8300 + FD6288Q substitution case with safety margin |

### Current sense

| Item | Spec |
|---|---|
| Architecture | Per-phase low-side shunt → CSA → MCU ADC (AM32 standard; matches Open-4in1-AM32-ESC reference) |
| Per-MCU instance | 3 shunts + 3 CSAs (one per phase); per board: 12 shunts + 12 CSAs across 4 channels |
| Shunt | 0.2 mΩ ±1 % 1 W low-inductance (Vishay WSLP / WSL2512 / equivalent class); specific JLC part picked at Phase 3 schematic |
| CSA part | **TI INA186A3IDCKR** (100 V/V gain, SC-70-6) — closed at Phase 2c; JLC C-number verified at Phase 3 schematic |
| Effective gain | 20 mV/A (`MILLIVOLT_PER_AMP = 20` in `firmware/am32-target/PCBAI_FPV4IN1_F421.target.h`) |
| ADC range usage | 70 A peak × 20 mV/A = 1.4 V at AT32F421 ADC (42 % of 3.3 V reference; comfortable headroom + noise floor) |
| Shunt dissipation | 0.2 mΩ × 70² A = 0.98 W per shunt; 11.7 W board-total (included in Phase 6 thermal envelope) |

### Power supply subsystem

Closed at Phase 2d — see `docs/PHASE2D_POWER.md` for the full part-by-part breakdown.

| Rail | Source | Part | JLC C# | Capability | Load (estimated) |
|---|---|---|---|---|---|
| +BATT (6S, 18.0–25.2 V) | LiPo battery direct | n/a | n/a | bus | 280 A peak / 70 A continuous per channel |
| +5 V | LMR51420YDDCR buck from +BATT | TI buck SOT-23-6 | C7296200 | 2 A @ V_in 3.5–36 V | ~461 mA average (drivers + LDO input) |
| +3.3 V | TLV76733DRVR LDO from +5 V | TI LDO WSON-6 | C2848334 | 1 A | ~421 mA average (4 MCUs + 12 CSAs) |

Bulk capacitance: **2 × 470 µF 63 V aluminum electrolytic SMD radial, low-ESR (≤ 30 mΩ at 100 kHz), ≥ 1.5 A RMS ripple per cap, parallel = 940 µF total bulk**. Specific JLC C-number picked at Phase 3 schematic against current stock; criteria fully constrain the pick.

Per-MCU decoupling: per AT32F421 datasheet Fig 8 — 2 × 100 nF (digital VDD) + 1 × 100 nF (analog VDDA) + 1 × 10 µF (digital VDD pool) + 1 × 1 µF (VDDA) + 1 × ferrite bead per MCU (×4 = 20 caps + 4 ferrites total).

Per-driver decoupling: 1 × 10 µF + 1 × 100 nF at GVDD (×4 = 8 caps). Bootstrap caps (3 × 12 = 12 placeholder 100 nF; value finalized at Phase 3).

Per-channel local bus: 22 µF X5R/X7R 0603 ceramic at each gate driver V_CC (×4).

### Protection

Closed at Phase 2e — see `docs/PHASE2E_CONNECTORS_PROTECTION.md`.

- **TVS on input rail**: SMBJ33A (33 V V_WM, 53.3 V V_C clamp — safely under AON6260 60 V V_DS_max with 6.7 V margin). Specific JLC C# at Phase 3.
- **Reverse-polarity**: 4 × AON6260 in parallel, low-side N-FET ideal-diode topology (reuses Phase 2b part). Effective R_DS(on) 0.49 mΩ across 4 FETs in parallel. Phase 3 schematic decides between this default and the AOTL66912 single-FET alternate based on board real-estate.
- **ESD on FC-side signals**: 3 × USBLC6-2SC6 (JLC C7519) covering 4 DShot + 1 TLM + 1 spare. C_io 3.5 pF max satisfies DShot 600 edge integrity.
- **HW overcurrent comparator**: independent of firmware; target trip < 1 µs (via AT32F421 internal CMP1 on PA0/PA4/PA5 BEMF pins, repurposed-during-fault — Phase 3 schematic + AM32 firmware-target work).
- **UVLO at MCU regulator level**: TLV76733DRVR has built-in UVLO; AT32F421 has internal V_LVR threshold 1.88 V typ (datasheet §5.3.3).
- **Per-phase low-side shunt monitoring**: per Phase 2c (AM32 standard).

### Connectors

Closed at Phase 2e — see `docs/PHASE2E_CONNECTORS_PROTECTION.md`.

- **FC connector**: JST SM08B-SRSS-TB (JLC C160407) — Open-4in1 reference. Betaflight 4-in-1 8-pin pinout: 1=GND, 2=VBAT, 3=CURR, 4=TLM, 5-8=M4/M3/M2/M1.
- **Motor pads**: 12 × 3.0 mm dia SMD pads (4 channels × 3 phases). Accommodates 20-26 AWG wire by user choice.
- **SWD per-MCU**: 4 × {SWDIO + SWCLK + GND} = 12 test pads minimum (NRST optional adds 4). Per-MCU one-at-a-time flash (Open-4in1 pattern).

### Status indicators

- 1 × Power-good LED (green 0603, 1 kΩ current limit).
- 4 × Per-channel status LED (red 0603, 1 kΩ current limit, GPIO from free MCU pin pool per Phase 2a).

### Mechanical

- **Form factor NOT pre-constrained.** Phase 2.5 converges via:
  - Thermal sim: minimum board area for 4 × 70 A continuous at JLC stack-up + nominal prop-wash airflow
  - Layout sim: minimum routing density at JLC trace/space + via rules
  - Output: the larger of {physics-required area, nearest standard FPV stack pattern}
- **Stack-up**: 6-layer per playbook §Routing (signals on the two outer layers, four inner solid planes). Confirmed at Phase 4 placement.
- **Connectors**: TBD at Phase 2 (motor wires typically direct-solder pads; FC connector standard 8-pin JST-SH or similar)
- **Heatsink** (added at Phase 2b 2026-05-22 per master adjudication on URGENT #3): Top-side aluminum heatsink with thermal interface pad to MOSFET tops. Sized at Phase 4 / Phase 6 thermal sim. **Required for Envelope 2 (70 A continuous prop-wash) thermal performance.**
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
