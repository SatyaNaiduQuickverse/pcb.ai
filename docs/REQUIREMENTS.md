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
| Peak / burst current / channel | **100 A @ 10s pulse** (1.43× continuous; anchored on iFlight BLITZ E80 premium reference, top of 1.25-1.40× band — Sai delegation 2026-05-22, master adjudicated via sureshot-vs-SOTA rule). Supersedes Phase 2c/d use of "70A peak = continuous" (informal; now formalized) |
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
| Specific part (phase MOSFETs ×24) | **AOS AOTL66912** TOLL-8L (closed at Phase 4c-resume per Sai's Option C 2026-05-22 — see `docs/PHASE4C_RESUME_OPTIONC.md`). 100V over-spec, 1.4mΩ typ, **R_thJC = 0.2 °C/W** (5× better than DFN5x6), 269A @ T_C=100°C, JLC C3291324 |
| Specific part (reverse-pol ×4) | **AOS AON6260** DFN5x6-8 (Phase 2e adjudication — stays for low-side ideal-diode) |
| Package | TOLL-8L for phase (Sai's Option C, 2026-05-22 — thermal envelope requires it); DFN5x6 for reverse-pol |
| Voltage class (V_DS) | ≥ 60 V — AOTL66912 = 100V (over-spec, no margin penalty); AON6260 = 60 V |
| Continuous I_D rating (datasheet) | ≥ 200 A at T_C = 100°C — AOTL66912 = 269 A (well clear); AON6260 = 67 A (reverse-pol path, briefer load) |
| R_DS(on) | ≤ 2.0 mΩ typ @ V_GS = 10 V — AOTL66912 = 1.4 mΩ typ / 1.7 max; AON6260 = 1.95 mΩ typ |
| R_thJC (phase MOSFETs) | ≤ 0.3 °C/W — AOTL66912 = 0.2 typ / 0.3 max ✓ (the key reason for the Option C switch) |
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
| ADC range usage | **100 A burst × 20 mV/A = 2.0 V at AT32F421 ADC (61% of 3.3 V reference; 39% headroom — supersedes prior 70A-peak / 42% calc per CL-009 burst lock 2026-05-22)**. Continuous 70 A = 1.4 V / 42% remains the operating-state point. |
| Shunt dissipation | 0.2 mΩ × 70² A = 0.98 W per shunt continuous; **0.2 mΩ × 100² A = 2.0 W per shunt @ 10s burst (Phase 2-burst-resize verifies shunt pulse-energy rating)**; 11.7 W board-total continuous (Phase 6 thermal envelope) |

### Power supply subsystem

Closed at Phase 2d (original); expanded at Phase 2d-REDO (PR #16's successor) — see `docs/PHASE2D_REDO_BEC_EXPANSION.md` for the full 6-rail breakdown after `feedback-anchor-on-most-capable-reference` rule application. Architecture: autonomous-drone power-hub (RPi 5 + AI HAT host), NOT premium FPV class.

| Rail | Source | Part | JLC C# | Capability | Load |
|---|---|---|---|---|---|
| +BATT (6S, 18.0–25.2 V) | LiPo battery direct → 2× MF72 5D25 parallel NTC ICL → **4× Infineon BSC014N06NS rev-pol FETs** (Phase 2-burst-resize upgrade from AON6260; 1.45 mΩ each → 0.36 mΩ cluster, 680 A continuous capability) → **4× Panasonic EEHZS1V471P bulk caps** (Phase 2-burst-resize upgrade from 2× aluminum electrolytic; hybrid polymer-Al, 1880 µF total, 4A RMS each → 2× FoS over typical ripple per master amendment 2026-05-22) → SMBJ33A TVS | NTC: MF72 5D25; rev-pol: BSC014N06NS; bulk: EEHZS1V471P; TVS: SMBJ33A | C116485 × 2; **C113391** × 4; **C403803** × 4; existing | bus (16 A inrush ceiling) | 400 A peak board-total (4× 100A burst per channel) / 280 A cont (4×70A) |
| +V5_FC | TPS54560DDAR buck from +VMOTOR | TI buck SOIC-8-EP | **C31966** | 5 A @ VIN 12-30 V | ~1 A typ (FC + cam + RX + LEDs) |
| +V5_PI5 | TPS54560DDAR buck from +VMOTOR (independent rail per Sai's sensitive-electronics directive) | TI buck SOIC-8-EP | **C31966** | 5 A @ VIN 12-30 V | ~3 A typ, 5 A peak (RPi 5) |
| +V5_AI | TPS54560DDAR buck from +VMOTOR (independent rail — split from old V5_RPI per master adjudication URGENT #1 2026-05-22) | TI buck SOIC-8-EP | **C31966** | 3 A @ VIN 12-30 V | ~1.5 A typ, 3 A peak (AI HAT) |
| +V9_VTX1 | AOZ1284PI buck from +VMOTOR | AOS buck SOIC-8-EP | **C48060** | 2 A @ VIN 3-36 V | ~0.8 A typ (VTX #1) |
| +V9_VTX2 | AOZ1284PI buck from +VMOTOR (full-isolation from #1) | AOS buck SOIC-8-EP | **C48060** | 2 A @ VIN 3-36 V | ~0.8 A typ (VTX #2) |
| +V3V3 | TLV76733DRVR LDO from +V5_FC | TI LDO WSON-6 | C2848334 | 1 A | ~660 mA typ (4 MCUs + 12 CSAs + sensors) |

**Per-rail safety (tier-matched per master adjudication 2026-05-22):**
- 5V rails (sensitive RPi/AI/FC): TPS259251DRCR eFuse (C527680) on each + SMAJ5.0A TVS (C113952) + ferrite-LC filter
- 9V rails (VTX): Bourns MF-MSMF200 polyfuse (2A hold) + SMAJ9.0A TVS (C113955) + ferrite-LC filter
- 3V3: TLV76733 internal current-limit (no extra IC)
- V5_PI5 + V5_AI: enhanced LC filter (100 µF polymer electrolytic + multi-ceramic) + voltage supervisor IC

**Battery input:**
- 2× MF72 5D25 NTC ICL in parallel (C116485 × 2) → 16 A I_max, 2.5 Ω cold, ~25 mΩ hot
- Power-on green LED + reverse-polarity red LED (indicator hardware)
- Existing rev-pol stack (4× AON6260) + SMBJ33A TVS preserved

**BEC_OUT 10-pin AUX header** exposes all 6 rails + 3× GND for external loads.

**Total BEC peak dissipation:** 13.6 W (master's "~12W" target ≈ matches).

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

Closed at Phase 2e (original); refined at Phase 2e-REDO per Sai's 2026-05-22 solder-first directive — see `docs/PHASE2E_REDO_CONNECTORS.md`.

- **FC connector** (UNCHANGED): JST SM08B-SRSS-TB (JLC C160407) — Open-4in1 reference. Betaflight 4-in-1 8-pin pinout: 1=GND, 2=VBAT, 3=CURR, 4=TLM, 5-8=M4/M3/M2/M1.
- **BEC output — SOLDER PADS FIRST** (Phase 2e-REDO strategy):
  - 6 rail solder pad pairs, sized per current:
    - +V5_FC / +V5_PI5 / +V5_AI: D 4.0 mm pads (5A/5A/3A)
    - +V9_VTX1 / +V9_VTX2: D 3.0 mm pads (2A each)
    - +V3V3: D 2.5 mm pads (1A)
  - 4× standalone D 3.0 mm GND distribution pads spread across pad cluster.
  - Total: 16 BEC pad components.
- **Optional connector overlays** (Phase 3b-detail layout work, NOT in netlist):
  - +V5_FC, +V5_AI, +V9_VTX1, +V9_VTX2: JST SH 2-pin BM/SM02B (1.0 mm pitch, 1A per contact)
  - +V5_PI5: XT30 2-pin (30A rated, robust for sensitive RPi 5 load) — custom symbol needed in `components.kicad_sym`
  - +V3V3: pads-only (no connector — low current)
- **Motor pads** (UNCHANGED): 12 × 3.0 mm dia SMD pads (4 channels × 3 phases). Accommodates 20-26 AWG wire.
- **SWD per-MCU** (UNCHANGED): 4 × {SWDIO + SWCLK} = 8 test pads minimum. Per-MCU one-at-a-time flash (Open-4in1 pattern).
- **Silkscreen requirements**: per-pad +/- polarity markings + rail labels (+5V_FC, +5V_PI5, +5V_AI, +9V_VTX1, +9V_VTX2, +3.3V, GND). Forward-listed in `docs/PHASE2E_REDO_CONNECTORS.md` §3 for Phase 3b-detail application.

### Schematic (KiCad 9)

KiCad project at `hardware/kicad/pcbai_fpv4in1.kicad_pro`. Phase 3 split into three sub-phases per CLAUDE.md §6:

- **3a** (PR #9): main schematic sheet skeleton + canonical SKiDL netlist spec (`hardware/kicad/pcbai_fpv4in1_skidl.py`) + custom symbols library (`hardware/kicad/components.kicad_sym`). ERC 0 violations on skeleton files. See `docs/PHASE3A_MAIN_SCHEMATIC.md`.
- **3b** (PR #10): channel sub-sheet — `hardware/kicad/channel_skidl.py` `make_channel()` function. Captures MCU + DRV8300 + 6 AON6260 (3 half-bridges) + 3 shunts + 3 INA186 CSAs + 3 BEMF dividers (22 kΩ / 3.3 kΩ derived this phase) + bootstrap (1 µF) + DT pin R (40 kΩ → 200 ns) + all decoupling + status LED. SKiDL standalone run: 215 parts, 0 errors. See `docs/PHASE3B_CHANNEL_SCHEMATIC.md`.
- **3c** (PR #11): hierarchy instantiation × 4 + VBAT_SENSE divider (100 kΩ / 14 kΩ, ratio 8.14) + CURR_OUT decision (firmware-telemetry via TLM per Betaflight std). End-to-end SKiDL run: 249 components, 211 nets, 0 errors. kinet2pcb consumed → `hardware/kicad/pcbai_fpv4in1.kicad_pcb` (992 KB) ready for Phase 4 placement. See `docs/PHASE3C_HIERARCHY_ERC.md`.
- **3c**: hierarchical instances × 4 + full ERC + netlist export.

Phase 4 (placement) renders the visual schematic in the KiCad GUI against the Phase 3a-3c canonical netlist spec.

### Status indicators

- 1 × Power-good LED (green 0603, 1 kΩ current limit).
- 4 × Per-channel status LED (red 0603, 1 kΩ current limit, GPIO from free MCU pin pool per Phase 2a).

### Mechanical

Closed at Phase 2.5 — see `docs/PHASE2_5_FITCHECK.md`.

- **Form factor**: **100 × 85 mm rectangular** (re-locked at Phase 4b-REDO3 per master adjudication 2026-05-22 — signal-density D/S gate failed at 90×75; need bigger board + In3.Cu signal-promotion for autoroutability). Size history: 50×50 (initial) → 85×70 (4c-resume Option C, TOLL MOSFETs) → 90×75 (4b-REDO2, BEC absorption) → **100×85 (this phase, signal-density relief; +25.9% area, F.Cu pad-blocked fraction 49% vs 62% at 90×75)**. Master-locked D/S signal-density gate at 0.85 — current placement passes with In3.Cu signal-promoted (D/S = 0.83).
- **Mounting**: 4 × M3 holes at corners (5, 5), (80, 5), (5, 65), (80, 65) — 75 × 60 mm custom pattern (no standard FPV match; accepted at Phase 4c-resume since Sai's direction enables custom mount). Drone integrator picks mount-bracket / adapter plate.
- **Stack-up**: **8-layer** per Phase 4a-restack-8L master directive 2026-05-22 — locked at Phase 4a-restack-8L (Task #37, PR #27):
  - F.Cu (3 oz) — signal (signal-side + high-current motor-phase traces + TOLL FET top pads + thermal face)
  - In1.Cu (1 oz) — GND plane (full board, return-path for F.Cu/In2 signals)
  - In2.Cu (1 oz) — signal (inner-routing #1)
  - In3.Cu (3 oz) — +VMOTOR plane (full board, heavy-copper for ≥280 A continuous / 400 A peak)
  - In4.Cu (1 oz) — signal (inner-routing #2)
  - In5.Cu (1 oz) — GND plane (dual-GND sandwich on +VMOTOR for EMC + return-path symmetry)
  - In6.Cu (1 oz) — signal (inner-routing #3)
  - B.Cu (3 oz) — signal (power-side + secondary high-current + TOLL FET drain pads + thermal face)

  5 signal layers (F, In2, In4, In6, B) + 3 plane layers (In1=GND, In3=+VMOTOR, In5=GND). Pre-Phase-4a-restack-8L stack was 6L; doubled signal-routing capacity to support +413 components from Phase 3-redo.
- **+VMOTOR via stitching**: **≥ 210 vias** on +VMOTOR rail (F.Cu ↔ In3.Cu ↔ B.Cu through-vias), master-locked at Phase 4a-restack-8L (Task #43, amended from initial 200 per Sai's 1.5× FoS requirement). Distribution: ~20 at CBULK→VMOTOR entry, ~200 across 4 channels (FET drains + trace + bypass cap stacks), ~20 mid-trace stitching. **Critical layout requirement**: 3 oz copper pour must surround every via on F.Cu and B.Cu to sustain 2 A/via aggressive baseline (1.50× cont. FoS, 1.58× burst FoS). Phase 4b-redo4-R1 places; Phase 5b-retry verifies post-autoroute.
- **Edge.Cuts outline**: 50.0 × 50.0 mm square. Edge.Cuts layer stroke 0.05 mm.
- **Placement** (Phase 4b PR #13 → Phase 4b-REDO PR #16 → Phase 4b-REDO2 this PR): 348 footprints total on 90×75 board. Per-MCU rotation preserved from 4b-REDO (CH1 θ=0°, CH2 θ=90°, CH3 θ=270°, CH4 θ=180°). FETs in 3×2 corner sub-grids (25×13 mm clusters per channel). Phase 4b-REDO2 absorbed: 5 bucks (TPS54560 ×3 + AOZ1284PI ×2) in middle band y=24..40, NTC ICL + indicator LEDs in battery section, 16 BEC solder pads on board edges, ~65 BEC supporting passives in lower-middle band y=44..56. Mount holes at corners (5,5)/(85,5)/(5,70)/(85,70). T7 verified. Heatsink zone unchanged — Phase 4c thermal verdict preserved (T_J 79.8°C @ Envelope 2). See `docs/PHASE4B_REDO2_PLACEMENT.md`.
- **F.Cu / B.Cu split**: F.Cu = signal side (4 MCUs, 4 drivers, 12 CSAs, buck+LDO, ESD, decoupling, LEDs, FC connector, motor pads, SWD pads); B.Cu = power side (24+4 MOSFETs, 12 shunts, 2 bulk caps, TVS, buck inductor).
- **Heatsink**: **80 × 55 mm Al6061-T6, 4 mm thick** (locked at Phase 4c-resume; PRESERVED at Phase 4b-REDO2 — MOSFET (x,y) on B.Cu unchanged, heatsink valid). Covers 24× TOLL 6×4 grid with 2 mm border. Finned with **10× area multiplier** (fin geometry: practical 25-30 mm tall fins at ~3 mm pitch). Silicone thermal pad 0.5 mm, 4 W/m·K conservative (datasheet 4-6 range). Mounted via M2 screws.
- **Edge.Cuts outline**: 100 × 85 mm rectangular. Edge.Cuts layer stroke 0.05 mm.
- **Mounting**: 4× M3 holes on custom **90 × 75 spacing pattern** (corners at (5,5), (95,5), (5,80), (95,80) on 100×85 board). No standard FPV-stack fit — commercial-product-class custom pattern per `feedback-anchor-on-most-capable-reference` rule.
- **Connectors / pads**: FC connector (JST SM08B-SRSS-TB) on F.Cu top edge, centered. 12 motor pads (3.0 mm dia) distributed 3-per-edge across all 4 board edges, one channel per edge. SWD pads on F.Cu left edge. 16 BEC solder pads (Phase 2e-REDO) on board edges per T7 accessibility (tentative allocation in `docs/PHASE2E_REDO_CONNECTORS.md` §5; final placement at Phase 4b-redo-II).
- **Z-axis budget**: 14-22 mm total board+heatsink+bulk-cap stack depending on bulk-cap placement (B.Cu preferred; F.Cu fallback). FPV stack compatibility needs a custom dual-standoff structure OR low-profile polymer bulk caps (~6 mm tall vs 13.5 mm aluminum electrolytic) — Phase 4 placement decides.
- **Mounting**: Bolt pattern matches the converged form factor's standard once Phase 2.5 lands

### Fab + assembly

| Item | Spec |
|---|---|
| Fab | JLCPCB |
| DRC ruleset | JLCPCB's published capability spec (authoritative; per Playbook §Manufacturability — pull fresh per Rigor §10) |
| Assembly | JLCPCB SMT (production); BOM constrained to JLC parts library (basic + extended) or pre-flagged as hand-solder |
| Surface finish | ENIG (gold) for fine-pitch and corrosion resistance |
| Stack-up | **JLC 8-layer standard** (Phase 4a-restack-8L); F.Cu / In3.Cu / B.Cu = 3 oz (heavy-copper for motor + bus current); 5 signal + 3 plane layers |

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

## §reliability-spec — PL1 FPV 4-in-1 (Phase 3b-detail additions)

The PL1 FPV 4-in-1 does **not** carry the full HV60 reliability obligations (FPV market
norm), but per `feedback-anchor-on-most-capable-reference` rule (RPi 5 + AI HAT
host = autonomous-drone power-hub class) the following PL1 commitments apply:

| # | PL1 Standard |
|---|---|
| 1 | **Conformal coating optional for indoor/clean FPV use; RECOMMENDED for sustained outdoor / wet-environment / dusty use.** Standard MG Chemicals 4223 acrylic or equivalent (silicone variant 422B for higher-temp). Apply post-assembly + post-bench-test. Coating breaks if rework needed — apply only after final QA. |
| 2 | All external pads carry silkscreen polarity markings + rail labels (Phase 3b-detail closes this gap). |
| 3 | 3× SMT fiducials per side for pick-and-place reference (Phase 3b-detail). |
| 4 | PCB rev marking on F.SilkS for revision traceability. |
| 5 | Manufacturer mark placeholder for end-user/integrator branding. |

## §reliability-spec — HV60 family factor-of-safety standard

The HV60 family is reliability-positioned. Locked principles for the HV60 line:

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
