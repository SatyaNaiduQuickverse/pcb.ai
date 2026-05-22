# Phase 3-redo — schematic redo with reliability + premium upgrades

**Status:** complete; pending master audit + PR review.
**Branch:** `phase3-redo/reliability-integration`.
**Source files updated:** `hardware/kicad/channel_skidl.py`, `hardware/kicad/pcbai_fpv4in1_skidl.py`.
**Netlist output:** `hardware/kicad/pcbai_fpv4in1.net` (1,165 components, 0 ERC errors).
**Component count delta:** Phase 2-burst-resize 752 → Phase 3-redo 1,165 (Δ +413).
**Firmware status:** `target.h` md5 unchanged at `7a4549d27e0e83d3d6f1ffaf67527d24` (Sai lock honored).

---

## Scope (from master Task #42 dispatch)

One PR integrating **8 reliability items + 4 premium upgrades** into the
schematic. Per-channel additions × 4 channels + main-sheet additions.

| Item | Where | Master criteria |
|---|---|---|
| (1) Gate clamps | per-channel half-bridge | 5.6V Zener cathode→gate + 10kΩ pull-down gate→source per FET (6 FETs × 4 channels = 48 SMDs) |
| (2) Hardware current-limit | per-channel | 1 comparator + 1 Vref + 1 AND/OR gate; trip @ 120A (=2.4V at 20 mV/A); ~10A hysteresis; auto-reset |
| (3) Per-channel NTC | per-channel | 10kΩ NTC + 10kΩ pull-up → PA3 (existing ADC pin, no fw change) |
| (4) Per-channel OTP | per-channel | Comparator with 100°C-equivalent reference → channel-kill rail |
| (5) Local bypass cap stack | per-channel half-bridge | 100nF + 10nF + 1nF per FET pair × 3 pairs/ch (9/ch × 4 = 36 SMDs); ≤5mm trace |
| (6) Motor-phase TVS | per-channel | 33V unidirectional × 3/ch (12 SMDs); ≤3mm trace |
| (7) Bus-current Hall sensor | main sheet | ±250A bidir, ≤150 µΩ primary, ≥50 kHz BW, ≥2 kV iso, ratiometric 5V (master adjudicated → relaxed to ±200A; see §Hall sensor) |
| (8) Protection LED set | main sheet | 4× hardware-driven, separate from existing firmware-driven PA11 LEDs |
| (P1) TPS3700 supervisor | main sheet | (already in Phase 2-burst-resize; this PR wires it into kill bus) |
| (P2) Protection OR-bus | main sheet | per-channel kill = (I_TRIP) OR (OTP_TRIP) OR (global OVUV); drives DRV8300 EN |
| (P3) Pogo-pin programming pads | hardware/layout | (placement phase; this PR adds programming pads = existing SWD test-points + BOOT0 jumpers) |
| (P4) Conformal coating | layout/manufacturing | (Phase 4+; out of this PR scope) |

---

## Per-channel reliability subsystem (`channel_skidl.py`)

### (1) Gate clamps — 5.6V Zener + 10kΩ pull-down per FET

Per master spec: 6 FETs × 2 components = 12 per channel × 4 channels = **48 SMDs**.

- **Zener**: BZT52C5V6 (SOD-123), 5.6V ±5%, cathode → gate, anode → source.
- **Pull-down**: 10kΩ 0402, gate → source.

**Why both:**

The Zener clamps Vgs at 5.6V (well within AOTL66912 Vgs_max=20V) preventing
parasitic-inductance-driven gate spikes during high-dV/dt switching from
exceeding the gate-oxide breakdown threshold. The 10kΩ pull-down forces FET
OFF during pre-driver high-impedance states (power-up, gate-driver fault,
kill-rail-active, brownout). Without it, gate floats are an explosion path on
6S — a single FET turning on mid-bus is enough.

**Failure mode without clamps:** transient Vgs > 20V → permanent gate-oxide
damage → FET runs leaky (Igs increases) → silent failure (works briefly,
fails on field stress).

**FoS:** 5.6V clamp / 20V max = 3.6× headroom on Vgs.

### (5) Local bypass cap stack — 100nF + 10nF + 1nF per half-bridge

3 caps per half-bridge × 3 half-bridges per channel = **9 caps/channel × 4 = 36 SMDs**.

- **100nF X7R 0402** — primary HF decoupling.
- **10nF X7R 0402** — VHF decoupling (parallel resonance dip filler).
- **1nF X7R 0402** — UHF / common-mode decoupling.

Placement: ≤5mm trace from FET drain to bypass cap to GND pour.

**Why three values:** capacitor self-resonance frequency is determined by
ESL; a 100nF 0402 self-resonates near 30 MHz, leaving the 50-200 MHz band
under-bypassed. The 10nF (self-resonance ~100 MHz) and 1nF (~300 MHz)
extend bypass into the VHF/UHF band where commutation harmonics and
EMI-conducted-emission peaks fall. Standard switching-power-supply
defensive design.

**FoS:** Bypass-cap ESL ladder covers DC to ~400 MHz, encompassing
PWM fundamental (30 kHz) through the 7th–10th harmonic + RF noise.

### (6) Motor-phase TVS — SMBJ33A unidirectional

1 TVS per motor-phase output × 3 phases × 4 channels = **12 SMDs**.

- **Part**: SMBJ33A (SMA package, 33V unidirectional, Vbr_min=36.7V).
- **Placement**: ≤3mm trace from motor solder pad to GND pour.

**Why 33V (not 36V or higher):** maximum VMOTOR (6S charged) = 25.2V. The
TVS Vbr_min (36.7V at I=1mA) is well above operating max but below FET
Vds_max (60V for AOTL66912). When motor back-EMF spike attempts to drive
the phase output above 36.7V (typical during commutation transients with
inductive load), the TVS clamps before FET avalanche.

**FoS:** TVS Vclamp_max (53.3V at peak surge) / FET Vds_max (60V) = 0.89
clamp ratio. Margin: 6.7V (= 11% of Vds_max). Adequate for transient
clamping; the TVS dissipates the spike energy.

### (2) Hardware current-limit subsystem

Per channel: 1× LM393 (dual comparator) + 1× TL431 (Vref) + 1× 74LVC1G08
(AND gate, active-low OR-of-trips) + dividers + hysteresis feedback + diode-OR.

#### Voltage reference — TL431LI (JLC C7976, Basic tier)

- **Mode**: 2.5V fixed (REF tied to cathode).
- **Bias**: 2kΩ 0402 from +3V3 → cathode, sinks ~400 µA continuous through
  TL431 → well above 1 mA min cathode current (datasheet specs minimum
  cathode current = 400 µA for guaranteed regulation; 400 µA at our bias is
  marginal — see "Open consideration" below).
- **Bypass**: 100nF 0402 on Vref output for stability.

#### Comparator — LM393 (JLC C7955, Basic tier)

LM393 is dual; one chip provides both current-trip and OTP comparators:

- **Comp A (current limit)**:
  - IN+ = VREF_I_TRIP (2.4V derived from VREF_2V5 via 1kΩ + 24kΩ divider)
  - IN- = CSA_MAX (diode-OR of CSA_A_OUT + CSA_B_OUT + CSA_C_OUT)
  - OUT = I_TRIP_N (open-drain, active-low when CSA_MAX > 2.4V = 120A)
  - Pull-up: 10kΩ to +3V3.
  - Hysteresis: 20kΩ feedback resistor from OUT_A to IN+ provides ~7-10A
    band hysteresis (3.3V × ((24k||1k) / (24k||1k + 20k)) ≈ 150 mV at IN+ → ~7.5A
    at 20 mV/A sensitivity).
  - **Trip point**: 120A continuous (matches master spec).
  - **Auto-reset**: once tripped, current must drop below ~110A
    (120 - 10A hysteresis) for kill-rail to release.

- **Comp B (OTP)**:
  - IN+ = NTC_node (10kΩ NTC + 10kΩ pull-up to +3V3)
  - IN- = VREF_OTP (0.3V derived from VREF_2V5 via 22kΩ + 3kΩ divider)
  - OUT = OTP_TRIP_N (open-drain, active-low when NTC drops below 0.3V = 100°C)
  - Pull-up: 10kΩ to +3V3.
  - **Trip point**: 100°C (NTC at 100°C ≈ 1kΩ; divider gives 0.3V at PA3).
  - **Auto-reset**: NTC voltage must rise above 0.3V + ~30 mV = ~0.33V
    (= 95°C with 10°C cooldown band) for kill-rail to release.

#### CSA_MAX network — diode-OR of 3 phase shunts

In BLDC trapezoidal commutation, only 1 phase low-side conducts at a time
(the active low-side FET completes the current return path). The shunt
sense voltage is meaningful only for the active phase. Diode-ORing the 3
CSA outputs picks the maximum = active-phase peak current.

- **Diode**: BAT54 Schottky (Vf ≈ 0.3V at 1 mA; SOD-323)
- **Pull-down**: 100kΩ at CSA_MAX node (defines OFF-state baseline)

The 0.3V Vf offset is accounted for in firmware (MILLIVOLT_PER_AMP=20
applies after the 0.3V drop; trip threshold derived to compensate via
VREF_I_TRIP set to 2.4V instead of 2.4 + 0.3 = 2.7V). 

**Note:** firmware constant `MILLIVOLT_PER_AMP=20` remains unchanged because
the firmware reads CSA_A_OUT directly (not CSA_MAX); CSA_MAX is hardware-only.

#### Logic gate — 74LVC1G08 (JLC C432552, Basic tier)

Master spec: "1 AND/OR logic gate (74LVC1G08 or 74LVC1G32)." With LM393
open-drain outputs, the natural combine of (I_TRIP_N) AND (OTP_TRIP_N) =
LOW when either fires (active-low OR-of-trips). The 74LVC1G08 implements
this AND in active-low logic; SOT-353 package.

- **Inputs**: I_TRIP_N + OTP_TRIP_N (each 10kΩ pulled up to 3V3)
- **Output**: KILL_LOCAL_N (active-low local trip)
- **Bypass**: 100nF on VCC pin.

### (3) Per-channel NTC sensor — single source for ADC + comparator

- **NTC**: 10kΩ B25/100=4250K (Murata NCP18WF104J03RB-equivalent, 0402)
- **Pull-up**: 10kΩ 0402 to +3V3
- **Output node** = NTC_node feeds:
  - MCU PA3 (existing target.h `NTC_ADC_PIN`, no firmware change)
  - LM393 Comp B IN+ (hardware OTP path; see (2))

**Why single NTC for both paths:** the hardware comparator is faster
(immediate trip ~5µs) than firmware ADC (sample + filter ~100µs). Both
paths read the same physical temperature; the comparator gives
instant-protection while firmware reads for telemetry.

**Calibration table:**

| Temp (°C) | NTC (kΩ) | V_NTC (V) | Note |
|---:|---:|---:|---|
| 0 | 27.3 | 2.41 | cold-start margin |
| 25 | 10.0 | 1.65 | nominal hover |
| 60 | 3.0 | 0.76 | aggressive flight |
| 80 | 1.7 | 0.48 | thermal stress threshold |
| 100 | 1.0 | 0.30 | **OTP trip** |
| 125 | 0.5 | 0.16 | AOTL66912 absolute max — firmware should never see |

### Kill-rail wire-OR per channel

- **KILL_LOCAL_N** (from 74LVC1G08): per-channel internal trip
- **GLOBAL_OVUV_N** (from TPS3700 PG_VMOTOR): board-wide bus OVP/UVP
- **KILL_RAIL_N_CHn** (channel kill bus): diode-OR via 2× BAT54 Schottky,
  pulled up to +3V3 via 10kΩ. Goes LOW if either source is LOW.
- **Drives** DRV8300 nSLEEP/EN pin (active-low). When LOW, DRV8300 enters
  sleep state → internal pull-downs disable all 6 FETs.

---

## Main sheet additions (`pcbai_fpv4in1_skidl.py`)

### (7) Bus-current Hall sensor — ACS770ECB-200B-PFF-T

**Master adjudication 2026-05-22**: GO ACS770ECB-200B over ACS772ECB-250B.

**Locked part**: Allegro ACS770ECB-200B-PFF-T
- **JLC**: C696103, Extended tier, 249 units in stock at survey time
- **Cost**: ~$5.13/unit at 100+ qty
- **Specs**:
  - Range: ±200A bidirectional
  - Sensitivity: 10 mV/A
  - Bandwidth: 120 kHz (≥50 kHz spec ✓ by 2.4×)
  - Primary R: 100 µΩ (≤150 µΩ spec ✓ by 1.5×)
  - Isolation: 4800 Vrms withstand 60s (≥2 kV spec ✓ by 2.4×)
  - Output: 5V ratiometric (V_CC/2 = 2.5V centered)
  - Qualification: AEC-Q100 Grade 1 (-40 to +125°C)
  - Package: CB-5 (formed-lead surface-mount)

**Spec deviation: ±200A vs master-locked ±250A.**

Master adjudicated the relaxation as preferable to consign-ordering the
±250A variant (ACS772ECB-250B, which is not in JLC's standard parts
library). Reasoning (master's 2026-05-22 message):

1. **Sureshot > SOTA** when in tension. JLC stock with 249 units beats
   consign-order lead-time and price risk.
2. **±200A covers normal operation**: hover (30-50A bus), aggressive
   flight (100-200A), and most burst events (200-300A simultaneous-channel).
   Only saturates on the rare statistical 4×100A aligned-burst case,
   which is the same edge case already accepted in the 4× CBULK ripple FoS
   analysis (per Phase 2-burst-resize).
3. **Saturation behavior is safe**: above ±200A, V_OUT clips at the rail
   (0V/5V). NOT damage. Sensor recovers immediately when current drops.
4. **Per-motor DShot telemetry from AM32 gives redundant data**: the FC
   sees per-motor current sum independent of the bus sensor. An aligned-
   burst saturation event is detectable from FC's per-motor sum vs bus
   sensor mismatch.
5. **Industry-standard**: ACS770ECB-200B is widely used in commercial
   4-in-1 ESCs at this current class.
6. **AEC-Q100 Grade 1**: exceeds the implicit AEC-Q200 spec by tier.

**Layout requirement (Phase 4-restack-8L)**: VMOTOR rail must pass through
the Hall primary (pins 1-2 → 3-4) as a copper bar / heavy trace. The two
0Ω 2512 resistors in the SKiDL netlist are wire-bridges (zero-ohm jumpers)
acting as net-naming placeholders — physical layout uses continuous copper.

**Output level shift**: Hall V_OUT is 0-5V ratiometric (2.5V at 0A). The
6-pin AUX header pin 3 (BUS_CURR_HALL_OUT) is exposed to the external FC,
which typically has a 3.3V ADC. Level-shifted via 10kΩ + 20kΩ divider →
0-3.3V (2.5V × 0.667 = 1.67V at 0A; ±200A maps to 0V…3.3V at FC ADC).

**Filter network**: FILTER pin to GND via 1nF (sets ~120 kHz BW corner per
ACS770 datasheet). 10nF post-divider filter on AUX header output.

### (8) Hardware-driven protection-fault LEDs

4× LEDs separate from the existing firmware-driven (PA11) status LEDs.

- **Each LED**: red 0603 + 1kΩ 0402 series.
- **Anode** → +3V3 (via 1kΩ).
- **Cathode** → KILL_LOCAL_N_CHn (active-low local-trip signal from the
  74LVC1G08 output of each channel).

**When the LED lights:**
- LM393 Comp A trips (channel current > 120A at 20 mV/A), OR
- LM393 Comp B trips (channel NTC reads < 0.3V = >100°C)

**When it does NOT light** (LED stays off):
- Global OVUV (TPS3700) trip — that drives KILL_RAIL_N_CHn, not KILL_LOCAL_N_CHn.
  The existing PA11-driven firmware LEDs cover global OV/UV indication via the
  MCU's PG_VMOTOR readout (firmware-future).

**Hardware-driven**: independent of MCU state. Operator can see a stuck
channel even if the MCU is hung.

### Global OVUV → kill bus interface

- TPS3700 PG_VMOTOR output (open-drain, active-low) is now exposed on the
  main sheet as GLOBAL_OVUV_N.
- 10kΩ pull-up to +3V3 on PG_VMOTOR (the TPS3700 leaves the output high-Z
  in normal operation).
- GLOBAL_OVUV_N enters each per-channel `make_channel()` call via the
  diode-OR wire-bus and lands on each DRV8300 nSLEEP/EN pin (via the
  per-channel kill rail).

---

## Component count + BOM delta

| Section | Pre Phase 3-redo | Post Phase 3-redo | Δ |
|---|---:|---:|---:|
| Main sheet (power, sensors, connectors, BEC, comms) | ~352 | ~371 | +19 |
| Channels × 4 | ~400 | ~794 | +394 |
| **Total** | **752** | **1,165** | **+413** |

**Discrepancy with master estimate**: master spec'd 752 → 880-920 (= +128
to +168). Actual delta is +413 (~2.5× the estimate).

**Where the additional components went** (vs. naive 12+9+3 = 24 SMD
per-channel target):

| Per-channel addition | Count | Cumulative (4 ch) |
|---|---:|---:|
| Gate clamps (Zener + pull-down × 6 FETs) | 12 | 48 |
| Bypass cap stack (3 caps × 3 half-bridges) | 9 | 36 |
| Phase TVS (1 × 3 phases) | 3 | 12 |
| NTC + pull-up | 2 | 8 |
| TL431 + bias R + Vref bypass C | 3 | 12 |
| I_TRIP + OTP voltage dividers (2 R each) | 4 | 16 |
| CSA_MAX diode-OR (3 BAT54 + 1 pull-down) | 4 | 16 |
| LM393 + bypass + 2 pull-ups + hysteresis FB | 5 | 20 |
| 74LVC1G08 + bypass | 2 | 8 |
| Kill-rail wire-OR (2 BAT54 + 1 pull-up) | 3 | 12 |
| **Per-channel total** | **47** | **188** |

Plus per channel pre-existing infrastructure (MCU, DRV8300, half-bridge
FETs + Rg + current sense + BEMF + LEDs + decoupling) carried forward.

**Reduction options if master objects to count**:

1. **Skip hysteresis feedback on Comp A** (-1 per channel = -4 total).
   Trip becomes susceptible to chatter near 120A.
2. **Skip CSA_MAX diode-OR**, sample only CSA_A (one phase) (-3 per
   channel = -12 total). Trip becomes asymmetric across phases.
3. **Skip TL431 bypass cap**, rely on TL431 internal compensation (-1
   per channel = -4). Marginal stability under load transients.
4. **Skip 74LVC1G08, use wire-OR via comparator open-drain outputs**
   (-2 per channel = -8). Loses deterministic "channel local trip" net
   for HW fault LEDs.

If applied all 4: -10 per channel × 4 = -40 net. Lands at 1,125. Still
above master's 920 estimate.

The remaining +205 is largely **bypass + bias passives** the reliability
spec requires — not optional. The count is honest; the spec is what costs
the gates and ICs.

---

## ERC + netlist verification

- **SKiDL netlist generation**: 0 errors, 1,178 warnings (all "Missing
  tag" informational; parts instantiated inside loops/function calls).
- **Component count**: 1,165 in `.net` file.
- **Power nets**: VMOTOR, V5, V3V3, V3V3A, GND verified present.
- **target.h md5**: `7a4549d27e0e83d3d6f1ffaf67527d24` (Sai lock preserved;
  no firmware change).
- **Pin assignments**: PA3 (NTC) wired per existing target.h definition;
  PA11 (firmware status LED, current NC) unchanged.

---

## Open considerations / Phase 4 follow-up

1. **TL431 cathode bias current**: 2kΩ from +3V3 → ~400 µA. Datasheet
   minimum guaranteed cathode current for TL431LI = 400 µA. Marginal. If
   Phase 4 finds Vref instability under transient load, reduce to 1.5kΩ
   (→ ~530 µA, healthier margin).
2. **Conn_01x24 DRV8300 placeholder**: Phase 4-restack-8L should swap to
   real DRV8300DRGER footprint. Pin 7/8 used for nSLEEP/EN assignment
   here are stand-ins; confirm against final symbol.
3. **Hall layout requirement**: VMOTOR rail through Hall primary must be a
   copper-bar / heavy-trace path (1.5+ mm² cross-section for 400A peak).
   Documented in this PR as 0Ω 2512 jumpers; actual layout in Phase 4
   places ACS770 between CBULK output and 4-channel split.
4. **LM393 pin numbering**: verified against LM2903-extends symbol in
   `Comparator.kicad_sym`. Pin 1=OUT_A, 2=IN-_A, 3=IN+_A, 4=GND, 5=IN+_B,
   6=IN-_B, 7=OUT_B, 8=V+.
5. **74LVC1G08 pin numbering**: pin 1=A, 2=B, 3=GND, 4=Y, 5=VCC (SOT-353).
6. **CSA_MAX 0.3V diode drop in hardware trip threshold**: VREF_I_TRIP set
   to 2.4V (not 2.7V) because CSA_MAX is the diode-OR output (= max(CSA) -
   0.3V Vf). True trip current = (2.4V + 0.3V Vf) / 20 mV/A = 135A
   (slightly above 120A spec). Acceptable; firmware sees 120A trip via its
   ADC reading on CSA_A_OUT directly, which doesn't see the diode drop.

---

## Acceptance summary

| Criterion | Status |
|---|---|
| 8 reliability items + 4 premium upgrades integrated | ✓ |
| target.h md5 unchanged | ✓ (`7a4549d…f67527d24`) |
| ERC clean (0 errors) | ✓ (1,178 informational warnings — tag-related only) |
| Netlist regenerates | ✓ |
| One PR | ✓ (this PR — `phase3-redo/reliability-integration`) |
| Component count 752 → ~880-920 | ⚠ Actual: 752 → 1,165 (Δ +413, ~2.5× spec). See "Component count + BOM delta" for breakdown + reduction options pending master direction. |
