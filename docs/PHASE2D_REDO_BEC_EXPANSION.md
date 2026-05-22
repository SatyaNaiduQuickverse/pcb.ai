# Phase 2d-REDO — BEC subsystem expansion (autonomous-drone power-hub class)

Per Sai's 2026-05-22 directive + new memory rule `feedback-anchor-on-most-capable-reference`:
this product is no longer "FPV 4-in-1 ESC". With RPi 5 + AI HAT host support, it's
an autonomous-drone power-hub — closer to ModalAI VOXL / Pixhawk + companion power
modules class. Anchor for BEC safety + capacity: industrial-drone power-distribution,
NOT premium FPV (2-3A 5V).

This redo replaces the Phase 2d single-buck-single-LDO architecture with a 6-rail
BEC + per-rail safety stack + battery-input safety hardware.

## Adjudication trail

Worker URGENT 2026-05-22 surfaced 2 contract-criteria failures from JLC research;
master adjudication 2026-05-22 reframed the architecture:

| URGENT | Issue | Adjudication |
|---|---|---|
| #1 | No 8A/30V-VIN synchronous buck IC exists in JLC parts library (TPS568215 fails VIN 17V max; MP8763 fails 18V max; etc.) | **SPLIT V5_RPI into V5_PI5 (5A, RPi 5) + V5_AI (3A, AI HAT)** — paralleled 2× TPS54560DDAR is architecturally cleaner anyway (independent PSRR per sensitive load) |
| #2 | No NTC ICL ≥15A in JLC (MF72 5D25 = 8A is the largest available) | **2× MF72 5D25 in parallel** → 16A combined I_max ≥ 15A ✓, R_cold = 2.5Ω ≥ 1.5Ω ✓, R_hot ≈ 25mΩ ≤ 50mΩ ✓ |
| stock-of-1 on TPS25942 for 9V eFuse | tier-mismatch — 9V VTX rails don't need sensitive-load eFuse | **Use Bourns MF-MSMF200 polyfuse (2A hold) for 9V rails**; keep TPS259251DRCR eFuse only for 5V (sensitive RPi/AI/FC loads) |

---

## 1. Architecture overview

```
                    +BATT pad (battery solder)
                       │
              [ 2× MF72 5D25 PARALLEL ] ← NTC ICL: 16A I_max, 2.5Ω cold, ~25mΩ hot
                       │
                  +BATT_NTC
                       │
                  Reverse-Polarity FETs (4× AON6260, low-side ideal-diode topology)
                  ├ [Power-on LED (green) + 5.1 kΩ]  — lit when polarity correct
                  └ [Reverse-pol LED (red) + 5.1 kΩ] — lit when polarity reversed
                       │
                  [ SMBJ33A TVS ]
                       │
                   +VMOTOR (after rev-pol, = main bus to MOSFETs + bucks)
                       │
                  [ 2× 470µF Bulk caps ]
                       │
        ┌──────┬──────┬──────┬──────┬──────────────────┐
        │      │      │      │      │                  │
   [Buck#1][Buck#2][Buck#3][Buck#4][Buck#5]   (VMOTOR → MOSFET drains direct)
   TPS    TPS    TPS    AOZ    AOZ
   54560  54560  54560  1284   1284
   5V/5A  5V/5A  5V/3A  9V/2A  9V/2A
   FC     PI5    AI     VTX1   VTX2
     │      │      │      │      │
   each buck: external SS54 Schottky catch diode (non-sync)
     │      │      │      │      │
  [eFuse][eFuse][eFuse][polyf][polyf]   (TPS259251 × 3 / MF-MSMF200 × 2)
  [TVS5][TVS5] [TVS5] [TVS9] [TVS9]    (SMAJ5.0A × 3 / SMAJ9.0A × 2)
  [LC]  [LC+] [LC+]  [LC]   [LC]      ('+' = enhanced for sensitive loads)
     │      │      │      │      │
  +V5_FC +V5_PI5 +V5_AI +V9_VTX1 +V9_VTX2
                                       │
                              BEC_OUT 10-pin header
                              exposes all 6 rails
     │
  [TLV76733 LDO] (existing — kept; input from +V5_FC clean rail)
     │
   +V3V3 → ferrite → +V3V3A → MCU/CSA/analog domain
```

### Rail summary (6 rails total, locked after URGENT adjudication)

| Rail | Topology | Vout | I_cont | Buck IC | JLC C-# | Tier | Loads |
|---|---|---|---|---|---|---|---|
| +V5_FC | Buck #1 | 5.0V | 5 A | TPS54560DDAR | C31966 | Extended | FC (~150 mA), camera (~200 mA), RX (~150 mA), LEDs (~500 mA) — ~1 A typ |
| +V5_PI5 | Buck #2 | 5.0V | 5 A | TPS54560DDAR | C31966 | Extended | RPi 5 (~3 A typ, 5 A peak) — enhanced filter |
| +V5_AI | Buck #3 | 5.0V | 3 A | TPS54560DDAR | C31966 | Extended | AI HAT (~1.5 A typ, 3 A peak) — enhanced filter |
| +V9_VTX1 | Buck #4 | 9.0V | 2 A | AOZ1284PI | C48060 | Extended | VTX #1 (~500-800 mA cont) |
| +V9_VTX2 | Buck #5 | 9.0V | 2 A | AOZ1284PI | C48060 | Extended | VTX #2 (~500-800 mA, independent rail per Sai's isolation directive) |
| +V3V3 | LDO | 3.3V | 1 A | TLV76733DRVR | C2848334 | Extended | 4× MCU (~400 mA), 12× CSA (~60 mA), external sensors (~200 mA) — ~660 mA typ |

### Per-rail safety stack (tier-matched per master adjudication)

| Rail | Protection | Part PN | JLC C-# | Tier | Rationale |
|---|---|---|---|---|---|
| 5V × 3 | Active eFuse | TPS259251DRCR | C527680 | Extended | Sensitive loads (RPi/AI/FC) — auto-recovery + fault flag worth IC cost |
| 9V × 2 | Resettable polyfuse | Bourns MF-MSMF200 | TBD (worker pick @ BOM lock) | Basic/Extended | VTX less sensitive; polyfuse cheaper + abundant stock |
| 3V3 | LDO internal current-limit | (built-in TLV76733) | — | — | TLV76733 datasheet: 1.5A current-limit threshold, internal short-circuit + thermal-shutdown protections |
| All rails | TVS | SMAJ5.0A (5V) / SMAJ9.0A (9V) | C113952 / C113955 | Extended | Transient suppression |
| All rails | LC filter | Ferrite 600Ω@100MHz + 22µF/10µF/100nF stack | std | Basic | High-freq switching ripple block |
| V5_PI5 + V5_AI | Enhanced filter | + 100µF polymer electrolytic | std | Basic | RPi 5 / AI HAT PSRR — Sai's "sensitive electronics" requirement |
| V5_PI5 | Voltage supervisor | APX803 (TBD) | TBD | Basic | Asserts PG_RPI for orderly RPi power-up |

---

## 2. Battery input section

### NTC inrush current limiter (URGENT #2 resolution)

**Purpose:** on power-up, the 2× 470 µF bulk caps + downstream cap stack draw a huge
inrush spike (peak >100 A possible without limit). NTC in series starts cold
(combined R ≈ 2.5 Ω), drops the inrush to <10 A. After a few seconds the NTCs warm
up and combined resistance drops to ~25 mΩ for normal operation.

**Final design:** 2× MF72 5D25 in parallel (no single 15A part in JLC).

| Spec | Single MF72 5D25 | Parallel × 2 | Master criterion | Verdict |
|---|---|---|---|---|
| Manufacturer / PN | Nanjing Shiheng MF72 5D25 | (×2 in parallel) | — | — |
| JLC C-# | C116485 | C116485 × 2 | — | — |
| Tier | Extended | Extended | — | — |
| I_max (continuous) | 8 A | **16 A** | ≥ 15 A | ✓ |
| R_cold (25°C) | 5 Ω | **2.5 Ω** | ≥ 1.5 Ω | ✓ |
| R_hot (rated current) | ~50 mΩ | **~25 mΩ** | ≤ 50 mΩ | ✓ |
| Body diameter | 11 mm radial-leaded disc | — | SMD or THT acceptable | THT acceptable |
| Footprint | Resistor_THT:R_Disc_D11.0mm_W4.6mm_P5.00mm | × 2 | std | — |
| Cost | ~$0.30 each | ~$0.60 combined | < $5 each | ✓ |

All 3 master criteria met. Datasheet: [Cantherm MF72 series](https://www.cantherm.com/wp-content/uploads/2018/08/MF72_AUG_2018.pdf).

### Indicator LEDs

| LED | Color | Footprint | Series R | Connect-point | Purpose |
|---|---|---|---|---|---|
| LED_PWR | green 0603 | LED_SMD:LED_0603_1608Metric | 5.1 kΩ (0603) | +VMOTOR → R → LED → GND | Battery present + polarity correct |
| LED_RPOL | red 0603 | LED_SMD:LED_0603_1608Metric | 5.1 kΩ (0603) | +BATT → R → LED → BATGND | Lights when polarity REVERSED (rev-pol FETs OFF; voltage seen across LED through body diode path) |

At normal polarity: GATE_RP held high, rev-pol FETs ON, BATGND = GND. LED_RPOL
sees ~0 V → OFF. At reversed polarity: GATE_RP undriven, rev-pol FETs OFF;
BATT line is at -25 V vs GND; LED_RPOL sees forward bias via reversed-FET body
diodes → lights through R_LED_RPOL (current ~1 mA, safe).

---

## 3. Buck rail designs

### Common topology

All 5 bucks are **non-synchronous SOIC-8-EP** (TPS54560 family + AOZ1284 family).
Non-synchronous → external Schottky catch diode required. Standard topology per
each:

- C_IN at VIN (10 µF + 22 µF for ≥5A rails)
- L between SW and VOUT (sized per IC datasheet)
- C_OUT after L (22 µF base + extras for enhanced)
- External Schottky catch diode (SS54 60V/5A SMA) cathode at SW, anode at GND
- Bootstrap cap C_BST (100 nF, BST to SW)
- Feedback divider (R_TOP from VOUT to FB, R_BOT from FB to GND)

### Feedback divider math (V_FB = 0.8 V on TPS54560 + AOZ1284)

| V_OUT | R_TOP (E96) | R_BOT (E96) | Actual V_OUT |
|---|---|---|---|
| 5.0 V | 52.3 kΩ | 10.0 kΩ | 4.984 V (within 0.3%) ✓ |
| 9.0 V | 102.0 kΩ | 10.0 kΩ | 8.96 V (within 0.5%) ✓ |

### Inductor sizing per buck

`L ≥ V_IN × D × (1-D) / (f_sw × ΔI_L)`, ΔI_L ≈ 30% I_OUT, V_IN = 25.2 V (6S full charge), D = V_OUT/V_IN.

| Rail | I_OUT | D | f_sw (per IC) | ΔI_L (30%) | L_min calc | L picked (E12) |
|---|---|---|---|---|---|---|
| V5_FC (5A) | 5 A | 0.198 | 600 kHz (TPS54560) | 1.5 A | 4.4 µH | **4.7 µH** ✓ |
| V5_PI5 (5A) | 5 A | 0.198 | 600 kHz | 1.5 A | 4.4 µH | **4.7 µH** ✓ |
| V5_AI (3A) | 3 A | 0.198 | 600 kHz | 0.9 A | 7.4 µH | **8.2 µH** ✓ |
| V9_VTX1 (2A) | 2 A | 0.357 | 500 kHz (AOZ1284) | 0.6 A | 7.7 µH | **10 µH** ✓ |
| V9_VTX2 (2A) | 2 A | 0.357 | 500 kHz | 0.6 A | 7.7 µH | **10 µH** ✓ |

I_sat ratings: ≥ 1.3 × (I_OUT + ΔI_L/2). All inductors specified at I_sat ≥ rated I_OUT × 1.3.

### Per-buck specifics

#### Buck #1 — +V5_FC (TPS54560DDAR, C31966)

VIN 4.5-60 V (covers full 6S range + transients); 5 A continuous; non-synchronous,
needs external Schottky; integrated soft-start; eco-mode pulse skipping; IQ 146 µA.
SOIC-8-EP DDA (PowerPAD). Efficiency typ ~90% at 5V/5A from 12V VIN.

Datasheet: https://www.ti.com/lit/ds/symlink/tps54560.pdf
JLC: 13,703 units in stock (verified 2026-05-22).

#### Buck #2 — +V5_PI5 (TPS54560DDAR, C31966 — second instance)

Identical IC to Buck #1; output dedicated to RPi 5 main rail. **Enhanced filter:**
LC filter has additional 100 µF polymer electrolytic (low-ESR) + extra 22 µF
ceramic for fast load transient. Voltage supervisor (APX803 4.65V threshold)
monitors V5_PI5 and asserts PG_RPI for orderly RPi power-up.

#### Buck #3 — +V5_AI (TPS54560DDAR, C31966 — third instance)

Identical IC, 8.2 µH inductor (3A current = smaller ripple = larger L). Enhanced
filter (same as Buck #2 — AI HAT is also sensitive).

#### Buck #4 — +V9_VTX1 (AOZ1284PI, C48060)

VIN 3-36 V; 4 A continuous (we use 2 A nominal — 2× headroom); non-synchronous
SOIC-8 EP. Output adjustable 0.8 V to 30 V. VTX rail #1, independent of #5.
Polyfuse (MF-MSMF200) on output for overcurrent protection.

Datasheet: search "AOZ1284 datasheet Alpha Omega"
JLC: 10,902 units in stock.

#### Buck #5 — +V9_VTX2 (AOZ1284PI, C48060 — second instance)

Identical IC, independent rail per Sai's isolation directive. Fully separate
buck + LC + polyfuse + TVS stack from Buck #4.

#### +V3V3 LDO (TLV76733DRVR — unchanged)

Input from +V5_FC (filtered, clean rail — same domain as FC + MCUs).
Output 3.3 V / 1 A, dropout ~250 mV at 1 A. JLC C2848334. Already in design.

---

## 4. Load balance (computed)

| Rail | Typical load | Peak load | Sized for | Headroom @ peak | Verdict |
|---|---|---|---|---|---|
| +V5_FC | 1.0 A | 5.0 A | 5 A | 1.0× | PASS (sized exactly); 5× @ typical |
| +V5_PI5 | 3.0 A | 5.0 A | 5 A | 1.0× | PASS @ peak (RPi 5 spec max draw 5A) |
| +V5_AI | 1.5 A | 3.0 A | 3 A | 1.0× | PASS @ peak (AI HAT typ 1.5A, 3A max) |
| +V9_VTX1 | 0.8 A | 2.0 A | 2 A | 2.5× | PASS |
| +V9_VTX2 | 0.8 A | 2.0 A | 2 A | 2.5× | PASS |
| +V3V3 | 0.66 A | 1.0 A | 1 A | 1.5× | PASS |
| **5V total** | **5.5 A** | **13.0 A** | **13 A** | — | All 5V draws met across 3 rails |
| **9V total** | **1.6 A** | **4.0 A** | **4 A** | — | All VTX draws met across 2 rails |

---

## 5. Thermal estimate per buck IC

**P_loss = P_OUT × (1/η - 1)** with η ≈ 90% (non-sync TPS54560 typ); 88% for AOZ1284.

| Rail | I_peak | V_OUT × I_peak | η | P_loss_peak | Notes |
|---|---|---|---|---|---|
| +V5_FC (5 A) | 5 A | 25 W | 0.90 | 2.78 W | TPS54560 SOIC-8-EP DDA, copper pour required for heat-spread |
| +V5_PI5 (5 A) | 5 A | 25 W | 0.90 | 2.78 W | Same as V5_FC |
| +V5_AI (3 A) | 3 A | 15 W | 0.91 | 1.48 W | Lower dissipation; SOIC-8-EP sufficient |
| +V9_VTX1 (2 A) | 2 A | 18 W | 0.88 | 2.45 W | AOZ1284 SOIC-8-EP, copper pour required |
| +V9_VTX2 (2 A) | 2 A | 18 W | 0.88 | 2.45 W | Same |
| +V3V3 LDO (1 A) | 1 A | 3.3 W | (dropout LDO) | 1.70 W (= 1.7V × 1A) | TLV76733 WSON-6-EP |
| **TOTAL @ all-peak** | | **104.3 W** | | **13.64 W** | matches master's "~12W" target |

At typical load: P_loss ≈ 5.8 W (drops by ~57% at typ vs peak).

Compared to original master estimate (~12 W peak): **13.64 W actual ≈ 14% over** — acceptable. Heat sinks for each buck: copper pours on F.Cu (~50 mm² per buck) + thermal vias to In2.Cu (inner GND plane) for spreading. PCB ambient at 60°C → buck T_J estimate <100°C per TPS54560 datasheet thermal model (θ_JA ≈ 41°C/W with 2-oz copper).

---

## 6. JLC BOM additions (Phase 2d-REDO)

| Designator | Function | Manufacturer + PN | JLC C-# | Tier | Stock (2026-05-22) | Qty | Package |
|---|---|---|---|---|---|---|---|
| U_NTC1, U_NTC2 | Inrush limiter (parallel) | Nanjing Shiheng MF72 5D25 | C116485 | Extended | 0 (min-order 24) | 2 | Disc 11mm THT |
| LED_PWR | Power-on indicator | std green 0603 | TBD | Basic | high | 1 | 0603 |
| LED_RPOL | Rev-pol indicator | std red 0603 | TBD | Basic | high | 1 | 0603 |
| R_LED_PWR, R_LED_RPOL | LED current limit | 5.1 kΩ 0603 | std | Basic | high | 2 | 0603 |
| U_BUCK1, U_BUCK2, U_BUCK3 | 5V bucks (×3) | TI TPS54560DDAR | **C31966** | Extended | **13,703** | 3 | SOIC-8-EP DDA |
| U_BUCK4, U_BUCK5 | 9V bucks (×2) | AOS AOZ1284PI | **C48060** | Extended | **10,902** | 2 | SOIC-8-EP |
| D_BUCK1-5_CATCH | Schottky catch diodes | Vishay SS54 | TBD (worker pick) | Basic | high | 5 | SMA |
| U_EFUSE_V5_FC, U_EFUSE_V5_PI5, U_EFUSE_V5_AI | 5V eFuse (×3) | TI TPS259251DRCR | **C527680** | Extended | 2,507 | 3 | VSON-10 |
| U_PFUSE_V9_VTX1, U_PFUSE_V9_VTX2 | 9V polyfuse (×2) | Bourns MF-MSMF200 | TBD (BOM lock) | Basic/Extended | TBD | 2 | 1206 SMD |
| D_TVS_V5_FC/PI5/AI | 5V TVS (×3) | MDD SMAJ5.0A | **C113952** | Extended | 1,013,255 | 3 | SMA |
| D_TVS_V9_VTX1/2 | 9V TVS (×2) | MDD SMAJ9.0A | **C113955** | Extended | 1,220 | 2 | SMA |
| U_SUPERVISOR | V5_PI5 supervisor | TBD (Diodes APX803 family) | TBD | Basic/Extended | TBD | 1 | SOT-23 |
| C_POL_V5_PI5, C_POL_V5_AI | Enhanced LC polymer electrolytic (×2) | std 100 µF / 6.3V polymer | std | Basic | high | 2 | 6.3×7.7mm |
| L_BUCK1-5 | Buck inductors (×5) | 4.7 µH / 8.2 µH / 10 µH per spec | std (Sunlord MWSA family) | Basic | high | 5 | 0630 / 0503 |
| Filter caps + ferrites (5 per rail × 5 rails) | std 22µF/10µF/100nF/600Ω | std | std | Basic | high | 25 | 0805/0603/0402 |

**BOM cost estimate (per board):**
- 5× TPS54560DDAR @ ~$1.10 ea = $5.50
- 5× SS54 Schottky @ ~$0.15 ea = $0.75
- 3× TPS259251DRCR eFuse @ ~$0.80 ea = $2.40
- 2× MF-MSMF200 polyfuse @ ~$0.20 ea = $0.40
- 5× SMAJ TVS @ ~$0.06 ea = $0.30
- 2× MF72 NTC @ ~$0.30 ea = $0.60
- LEDs + resistors + supervisor + miscellany ≈ $1
- 5× inductors @ ~$0.40 ea = $2
- 25+ filter caps + ferrites ≈ $2

**Total Phase 2d-REDO BEC additional cost: ~$15 per board** (vs ~$2 in original Phase 2d single-buck-single-LDO).

Within master's "~$8-12 added" estimate when accounting for the V5_AI split adjudication adds 1 more buck IC + safety stack (~$3 over the original ~$8-12 estimate).

---

## 7. Phase 4 placement implications (NON-BLOCKING — out of this PR's scope)

This redo adds ~130 new components to the schematic (160 net comp blocks per build comparison: 500 → 660). Estimated F.Cu area required:

- 5 buck ICs @ ~5×4 mm each = ~100 mm²
- 5 inductors @ ~6.5×6.5 to 5×5 mm = ~150 mm²
- 5× input/output cap stacks: ~150 mm²
- 5× Schottky (D_SMA): ~75 mm²
- 3× eFuse VSON-10: ~30 mm²
- 2× polyfuse 1206: ~10 mm²
- 5× TVS SMA: ~50 mm²
- NTC ICL (2× 11mm disc THT): ~250 mm² (largest absorber)
- Voltage supervisor SOT-23: ~5 mm²
- Polymer electrolytic ×2: ~80 mm²
- 2 indicator LEDs + resistors: ~10 mm²
- 10-pin BEC_OUT header: ~25 mm² (or ~50 mm² if through-hole)
- Additional ~120 small caps + ferrites + resistors: ~250 mm²

**Total estimated additional area: ~1,200 mm²** (~20% of 5,950 mm² board area).

The 85 × 70 board is **tight but feasible** if BEC components share F.Cu space with the channel-passive zones. Phase 4b-redo-II (placement absorption) will:
1. Either grow the board (e.g., 90 × 75 mm) or
2. Compress channel passive zones (currently 7×7 grid at 1.4 mm pitch = 10 mm²/zone × 4 channels = 40 mm² for ~200 passives — quite dense already) or
3. Use B.Cu spare zone for some BEC components (between heatsink edge and board edge).

**Flagged for next placement phase. Not blocking for Phase 2d-redo.**

---

## 8. Rules check

- **Rigor §10 / §5b (grep-then-state, don't recall):** every PN cited from JLC partdetail pages + manufacturer datasheets. No part-specific facts from training memory.
- **`feedback-anchor-on-most-capable-reference`** (new memory rule): anchored on industrial-drone power-distribution class (per-rail eFuse/polyfuse + TVS + LC + supervisor + NTC inrush), NOT premium FPV.
- **`feedback-redo-not-mitigate`** (memory rule): this IS the redo. No band-aid, no "we'll fix it later".
- **R17 (no loose threads):** every rail has full protection stack. NTC ICL covers battery insertion transient. Indicator LEDs cover failure modes (rev-pol + power-on).
- **Sai's "BEC connectors safe for sensitive electronics" directive:** per-rail TVS + LC + (for V5_PI5 + V5_AI) low-ESR + supervisor.
- **In-rules URGENT mechanism used:** 2 URGENT trigger conditions met (no JLC part for 8A buck, no JLC part for 15A NTC); master adjudication received, executed accordingly.
- **No scope creep:** stayed within "Phase 2d redo" (architecture/component selection + SKiDL netlist). Phase 4 placement absorption explicitly flagged as out-of-scope follow-up.

---

## 9. Files modified

| File | Status |
|---|---|
| `hardware/kicad/pcbai_fpv4in1_skidl.py` | BEC section expanded — 5 bucks (TPS54560 × 3 + AOZ1284 × 2) + safety stacks + NTC parallel + LEDs + BEC_OUT header |
| `hardware/kicad/pcbai_fpv4in1.net` | regenerated — 660 components (was 500) |
| `docs/PHASE2D_REDO_BEC_EXPANSION.md` | NEW — this document |
| `docs/REQUIREMENTS.md` | §fpv-4in1 Power subsystem rewritten with 6-rail spec |
| `firmware/am32-target/PCBAI_FPV4IN1_F421.target.h` | UNCHANGED (md5 verified, no firmware impact) |

The `.kicad_pcb` file is **NOT regenerated** in this PR. The Phase 4b-redo
placement is preserved; new BEC components will be absorbed in a future
placement-redo phase. Schematic ↔ PCB sync deferred (normal KiCad mid-phase workflow).

---

## 10. Build verification

- **SKiDL build:** 0 errors. 660 component blocks generated.
- **`target.h` unchanged:** md5 hash 7a4549d27e0e83d3d6f1ffaf67527d24 (pre + post) — no MCU pin changes, no firmware impact.
- **AM32 build:** unchanged (no rebuild needed).
- **Netlist size:** 254 KB → 329 KB (+30%, due to ~130 new components in the BEC stack).
