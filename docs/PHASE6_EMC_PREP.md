# Phase 6-EMC-prep — EMC pre-compliance scope (4-channel FPV ESC)

**Status**: doc-prep (orthogonal to Phase 5b routing decision); 2026-05-24.
**Driver**: 4 PWM gate-driver channels + 5 buck switching regulators on a
6S 25.2 V board create significant broadband emissions. Pre-compliance
de-risks formal certification by catching issues at bring-up, not at the
EMC chamber.

## 1. Why this matters

PCBAI FPV 4-in-1 EMC threat surface:

| Source | Fundamental | Harmonic content | Coupling |
|---|---|---|---|
| 4× DRV8300 gate drivers | 24-48 kHz PWM per channel | Significant up to ~50 MHz (rise/fall ≤ 50 ns) | Gate loop → motor wire radiates |
| 5× buck regulators (BEC, V5, V9, V3.3) | 600 kHz - 2 MHz SW freq | Square edges → harmonics into VHF (200-500 MHz) | SW node → bulk-cap loop area |
| Motor phase output | 8 kHz - 32 kHz drive | Strong harmonics (dI/dt at FET commutation) | Motor wires = ~25 cm antenna |
| MCU + DRV digital | 8 - 120 MHz clocks | Clock harmonics + return-path EMI | Bottom-plane / trace coupling |
| Hall ACS770 (susceptible) | DC + low-freq | Susceptible to ≥1 MHz noise | Pickup through Vout filter |

Without mitigation, emissions can exceed FCC Class B by 20+ dB at 30-200 MHz.
Pre-compliance with near-field probe + lab spectrum analyzer surfaces these
during bring-up.

## 2. Reference standards

### 2.1 FCC (US) — likely required for commercial sale

- **FCC Part 15 Subpart B** — Unintentional Radiators (this product, no Tx)
- **Class B** (residential limits — applies if marketed for consumer hobby use)
  - Conducted emissions: 150 kHz - 30 MHz, AV/QP limits
  - Radiated emissions: 30 MHz - 1 GHz, 3 m or 10 m antenna distance
  - Limit at 30-88 MHz: 40 dBμV/m (Q-peak) @ 3 m
  - Limit at 88-216 MHz: 43.5 dBμV/m
  - Limit at 216-960 MHz: 46 dBμV/m
- Authorization path: **SDoC** (Supplier's Declaration of Conformity) — labs
  test against limits, manufacturer self-declares.

### 2.2 CE (EU) — required for EU sale

- **EN 55032:2015+A11+A1** Class B (CISPR 32 multimedia / similar)
- **EN 55014-1** (household appliance EMC) — alternative for some classifications
- **EN 61000-6-3** (residential immunity) — companion immunity standard
- **EU Radio Equipment Directive (RED)** if the drone integrates wireless (not
  this PCB — receiver is on FC, not this ESC)

### 2.3 Drone-specific

- **EN 301 489** series — radio-equipment EMC; relevant if drone integrates
  this ESC with onboard Tx. **Out of scope** for ESC standalone.
- **DO-160G section 21** (RTCA airborne) — overkill for hobby FPV.
- **ASTM F3589** (sUAS unmanned aircraft EMC) — draft, monitor.

### 2.4 Decision needed

The certification scope is owner-decision (Q1-Q4 below). Default planning
assumption: **FCC Part 15 Subpart B Class B** for US market. CE conditional
on EU sales channel decision.

## 3. EMC-sensitive component inventory (this board)

| Ref(s) | Component | EMC role | Mitigation already present |
|---|---|---|---|
| J18, J23, J28, J33 | 4× DRV8300 gate driver QFN-32 | EMI source (gate loop dI/dt) | Bootstrap caps, gate-R per FET |
| J19, J24, J29, J34 | 4× DRV CH-DRV companion | EMI source | Same as DRVs |
| J2, J3, J4, J5, J6 | 5× buck regulators (varies) | EMI source (SW node) | Bulk caps + dedicated planes |
| L1-L5 | Buck inductors | EMI source (shielded preferred) | Shielded SMD inductors |
| U1 | ACS770 Hall current sensor | EMI **susceptible** | Filter cap, layout near sensor |
| J18, J23, J28, J33 | 4× MCU (AT32F421 or STM32G071) | EMI source (clock + GPIO toggle) | Decoupling caps, layer return |
| Q5-Q28 | 24× BSC014N06NS FETs | EMI source (commutation dI/dt) | Slew control via gate-R |
| C1-C4 | 4× polymer bulk caps | Loop-area mitigation | Phase 4 placement near FETs |
| 8L stackup | F.Cu / GND / In2 / +VMOTOR / In4 / GND / In6 / B.Cu | EMI return path | Continuous reference planes |

## 4. Pre-compliance test setup

### 4.1 Conducted emissions (150 kHz - 30 MHz)

**Setup**:
- Battery (Li-Po 6S, fully charged) → 50 µH LISN (Line Impedance Stabilization
  Network) → ESC under test → 4× motor loads (real or dummy)
- LISN output (50 Ω) → spectrum analyzer
- Faraday cage / shielded enclosure preferred but pre-compliance can run on
  RF-quiet bench

**Required gear**:

| Item | Spec | Pre-compliance cost | Cert-grade cost |
|---|---|---|---|
| Spectrum analyzer | 9 kHz - 1 GHz, RBW 1 kHz / 9 kHz / 120 kHz | Siglent SSA3015X+ ~$1500 | R&S FSV ~$30k |
| LISN | 50 µH, 50 Ω, DC-blocked | $250-$500 | $1k-$3k |
| LiPo battery + motors + props | 4× motor load | Use existing test rig | Same |
| Cables, attenuator (10 dB) | SMA, double-shielded | $50 | Same |

### 4.2 Radiated emissions (30 MHz - 1 GHz)

**Setup**:
- Near-field magnetic loop probe (1 cm - 3 cm loop) for diagnostics
- Far-field antenna (biconilog or similar) for certification — REQUIRES
  semi-anechoic chamber (rented at $500-$2k/day) OR full-anechoic for
  research-grade

**Pre-compliance shortcut**: near-field probe survey identifies hot-spot
frequencies + locations. Then formal chamber-test scope is narrowed.

**Required gear**:

| Item | Spec | Pre-compliance cost |
|---|---|---|
| Near-field probe set | H-field loop (10 mm, 25 mm), E-field 100 MHz - 1 GHz | TekBox TBPS01 ~$300 |
| Probe preamp | 30 dB, 30 MHz - 1 GHz | TBLNA-1 ~$200 |
| Spectrum analyzer (same as conducted) | 1 MHz - 1 GHz, RBW 120 kHz | (already listed) |
| GTEM cell / TEM cell (compact radiated test) | 0.5 m × 0.5 m × 1.5 m | Rent ~$300/day |

### 4.3 Pre-cert simulation (de-risk before chamber)

- **openEMS** (open-source 3D FDTD EM solver) for near-field simulation
- **CST Studio Suite** (Dassault) commercial — overkill for pre-compliance
- **FEKO** (Altair) — similar commercial scope

For PCBAI: simulate the 4× DRV PWM-loop current path + buck SW-node loop with
openEMS. Identify resonances and standing-wave hotspots. Sai R20 / R23 already
constrains loop-area-minimization via R23 passive anchoring.

**Doc-prep recommendation**: stand up openEMS simulation infrastructure
during Phase 6 (alongside this doc) but defer full sweep to bring-up
(Phase 8) when real measured data calibrates simulation.

## 5. Bring-up test plan (Phase 8 integration)

Per Phase 8 "bring-up" of `docs/DESIGN_PHASES.md`:

1. **Day 1: Static + low-power** — power up, validate +5 V / +3.3 V / +9 V
   rails clean (no noise > 50 mVpp). Bench oscilloscope.
2. **Day 2: Per-channel single-FET commutation** — single channel running a
   motor on a dyno. Near-field probe sweep at:
   - Each DRV (top + bottom)
   - Each buck SW node
   - Each gate loop (DRV → FET gate)
   - MCU body
   - Hall sensor area (susceptibility — inject noise at adjacent test point,
     observe Hall Vout)
3. **Day 3: All 4 channels** — full 4-motor running. Repeat near-field sweep,
   especially at PWM harmonics. Identify worst-case frequency for chamber.
4. **Day 4: Conducted emissions** — bench LISN test (no chamber). Compare
   measured spectrum to FCC Class B mask. Identify margin / failures.
5. **Day 5: Radiated emissions (compact TEM cell)** — 30 MHz - 1 GHz sweep.
   Pre-compliance dispositioning before paying for cert lab.
6. **Day 6: Formal chamber** — if pre-compliance shows ≥10 dB margin to
   limits, send to certified lab. If <10 dB margin, design iterate (add
   ferrites, change gate-R, re-route problem nets) before lab.

## 6. Mitigation already in design (Phase 4 + Phase 5b scope)

| Mitigation | Phase | Status |
|---|---|---|
| 4× power planes (GND × 2, +VMOTOR × 1, others) | Phase 4a stackup | ✅ |
| Bulk caps C1-C4 near FETs (low-loop-area) | Phase 4 placement | ✅ |
| Gate-R per FET (slew control) | Phase 4 channel template | ✅ |
| Bypass caps per IC (R25 same-side decoupling) | Phase 4 placement + R25 audit | ✅ |
| Hall sensor filter cap | Phase 4 S3 placement | ✅ |
| Shielded buck inductors | Phase 2D BOM | ✅ (per `docs/PHASE2D_POWER.md`) |
| Via stitching for power return | Phase 5b routing-final | 🔄 PENDING (Phase A done; final Sai decision pending) |
| **Common-mode chokes on motor outputs** | NOT IN SCOPE | ❌ deferred Phase 7.5 |
| **Ferrites on battery input** | NOT IN SCOPE | ❌ deferred Phase 7.5 |
| **Faraday cage / shield can** | NOT IN SCOPE | ❌ deferred Phase 7.5 |

**Deferred mitigations** (above) are likely needed for FCC Class B compliance
but are post-freeze rev decisions. They're called out so Phase 7a freeze
includes pad provisions for adding ferrites + chokes if pre-compliance
flags emissions excess.

## 7. Open questions for owner / Sai

| # | Question | Default if no answer |
|---|---|---|
| Q1 | Certification scope: FCC only? FCC + CE? Custom test plan? | FCC Class B SDoC |
| Q2 | Target market geography (US / EU / Asia / global)? | US (defines FCC priority) |
| Q3 | Self-certification (SDoC) or full lab cert with TUV/UL? | SDoC for initial release |
| Q4 | Pre-compliance budget for spectrum analyzer + LISN + near-field probes? | $2k-$3k for Siglent + TekBox |
| Q5 | Chamber rental — local lab partner identified? | Defer to bring-up; quote at that time |
| Q6 | Pad provisions for deferred mitigations (ferrites, chokes) at Phase 7a freeze? | YES — reserve 4× 1206 pad sites near battery input, 12× 0805 pad sites at motor outputs |
| Q7 | openEMS pre-cert sim infrastructure — set up in Phase 6 or defer to bring-up? | Defer to Phase 8 bring-up (need measured data to validate sim) |
| Q8 | EMC test data archival format — for traceability if customer asks? | CSV + screenshot per test point, committed to repo |

## 8. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| FCC radiated emissions exceed Class B at 30-200 MHz (PWM harmonics) | Cannot ship to US market | Pre-compliance sweep + design margin via gate-R / ferrites |
| Buck SW node radiates at 200-500 MHz (broadband interference) | Co-located radio (RX) jamming | Shielded inductors (done) + ferrite bead on switch node |
| Motor wires act as 25 cm antenna at PWM fundamental + 10× harmonic | Near-field exceeds limit at 1 m | Common-mode choke on motor outputs (deferred) |
| Hall sensor noise pickup from buck regulator | False current readings, control instability | Sensor filter cap (done) + spatial separation in placement (S3 zone) |
| EMC failure surfaces only at cert lab (not pre-compliance) | $5k-$10k retest fee + design re-spin | Pad provisions for ferrites/chokes at freeze → enable easy retrofit |
| Sai's design choice (e.g., gate-R value) trades EMC vs efficiency | Cannot meet both spec | Trade-off documented in Phase 8 bring-up data + Phase 7.5 iteration |

## 9. Integration into design phases

- **This document is doc-only Phase 6** (no PCB / fab impact)
- **Phase 7a freeze (per `docs/DESIGN_PHASES.md`)**: incorporate
  - Pad provisions for ferrites + chokes (Q6) — verify in fab files
  - EMC pre-compliance test plan documented in fab-ready package
- **Phase 8 bring-up** — per Section 5 above, 6-day test plan
- **Phase 9 reliability** — repeat EMC at +85°C / -40°C extremes if customer
  spec requires
- **Phase 7.5 optimization** — common-mode chokes + ferrites added if needed

## 10. Sourcing prep — pre-compliance gear

- Siglent SSA3015X+ spectrum analyzer: Newark #95Y7866 or Saelig direct
- TekBox TBPS01 near-field probe set: TekBox direct ~$300
- TekBox TBLNA-1 preamp: TekBox direct ~$200
- LISN (50 µH, 30 A capability): Solar Electronics 9252-50-R-24 ~$1500 or
  COM-POWER LI-125A
- Cables, attenuators, terminators: standard 50 Ω SMA, Pasternack / Mini-Circuits

**Total pre-compliance lab budget**: ~$2.5k - $3.5k (spectrum analyzer dominates).

## 11. Status

This is a **doc-prep snapshot** to surface EMC scope decisions before
Phase 7a freeze. The 8 open questions are decision points for owner + Sai.
No code, no PCB, no fab impact. Routing remains frozen pending Sai's
routing-tool decision.
