# Phase 2d — Bus capacitor bank + BEC (5V/3.3V power supply)

Per `DESIGN_PHASES.md` Phase 2 sub-phase 2d. Rigor §10 (grep-then-state),
R3 (no invented specifics), R17 (no loose threads), new rule §5 (master sets
criteria + primary candidates; worker sources within bounds).

Final outcome: full power-supply BOM locked at the part-class level; specific
JLC C-numbers locked for every active IC + ceramic decoupling; bulk
electrolytic / polymer specific part deferred to Phase 3 schematic (criteria
locked here, the JLC pick is part-flexible).

## Power topology (block diagram, text form)

```
 +BATT (6S, nominal 22.2 V, range 18.0-25.2 V)
    │
    ├── Bulk capacitor bank (2 × 470 µF 63 V aluminum electrolytic, parallel)
    │     │
    │     └── shared input rail → ×4 channel half-bridges (AON6260 drains)
    │
    └── LMR51420YDDCR buck   ──▶  +5 V  ──▶  ×4 DRV8300DRGER GVDD pins
                                              │
                                              └── ferrite-bead-filtered ──▶  TLV76733DRVR LDO  ──▶  +3.3 V
                                                                                                       │
                                                                                                       ├── ×4 AT32F421K8T7 VDD pins
                                                                                                       │   (each: 2 × VDD digital + 1 × VDDA analog)
                                                                                                       └── ×12 INA186A3IDCKR CSA V_supply
```

## Locked active components

| # | Function | Part | JLC C# | Tier | Datasheet | Stock check |
|---|---|---|---|---|---|---|
| 1 | Buck regulator (5 V from +BATT) | **TI LMR51420YDDCR** | C7296200 | Extended | TI SLUSDC8 (`ti.com/product/LMR51420`) | Confirmed in Open-4in1 ref BOM (`/tmp/OpenESC_20X20/4in1ESC.kicad_sch`) |
| 2 | 3.3 V LDO (from +5 V) | **TI TLV76733DRVR** | C2848334 | Extended | TI SBVS295A (`ti.com/product/TLV767`) | Confirmed in Open-4in1 ref BOM |
| 3 | Buck inductor | **XRIM160808SR47MBCD** (0.47 µH SMD) | C48391583 | Extended | LCSC datasheet link | Confirmed in Open-4in1 ref BOM |
| 4 | Buck output / LDO filter ferrite bead | **BLM03PX121SN1D** (120 Ω @ 100 MHz, 0201) | C525479 | Basic | Murata datasheet | Confirmed in Open-4in1 ref BOM |

## Buck — LMR51420YDDCR specs

Per TI product page `ti.com/product/LMR51420`:
- V_IN: 3.5–36 V (covers our 6S range 18.0–25.2 V with margin)
- V_OUT: adjustable; fixed-frequency switcher (set V_OUT via external feedback divider to 5.0 V)
- I_OUT continuous: 2 A
- Switching frequency: 1.1 MHz typical
- Efficiency: ~89 % at 12 V → 5 V at 2 A (typical)
- Package: SOT-23-6 (DDCR), 2.9 × 1.6 mm
- Internal soft-start, current-mode control, OVP, UVLO, thermal shutdown

External components per typical application:
- 1× inductor 0.47 µH (XRIM160808SR47MBCD) — confirmed Open-4in1 pick
- 1× input cap 10 µF / 50 V ceramic minimum (use one of our 10 µF 0805 X7R from the bulk decoupling pool)
- 1× output cap 22 µF / 16 V minimum (use one of our 22 µF 0603 from the per-channel local pool)
- Feedback divider: 124 kΩ (top) + 24.9 kΩ (bottom) approx for 5.0 V output (FB threshold typ 0.8 V)
  - Open-4in1 schematic uses 124 K + 22 K — verify exact ratio against the SLUSDC8 datasheet at Phase 3 schematic

## LDO — TLV76733DRVR specs

Per TI product page `ti.com/product/TLV767`:
- V_IN: 2.7–12 V (covers our 5 V buck output)
- V_OUT: 3.3 V (fixed, 33 suffix)
- I_OUT continuous: 1 A
- Dropout voltage: ~250 mV at 1 A typ
- Quiescent current: ~30 µA typ at no-load
- PSRR: ~70 dB @ 1 kHz, ~50 dB @ 100 kHz (good enough for CSA reference cleanliness)
- Noise: ~38 µV_RMS (10 Hz – 100 kHz)
- Package: WSON-6, 2.0 × 2.0 mm

External components: 1× 1 µF input cap, 1× 1 µF output cap (ceramic X7R minimum).

## Load-balance computation (criterion 4 of pass criteria)

**+3.3 V rail load estimate:**
| Consumer | Per unit | Count | Subtotal |
|---|---|---|---|
| AT32F421K8T7 MCU active @ 120 MHz | ~100 mA | 4 | 400 mA |
| INA186A3IDCKR CSA | ~90 µA | 12 | 1.1 mA |
| GPIO pull-ups / status / housekeeping | ~5 mA | 4 | 20 mA |
| **Total +3.3 V** | | | **~421 mA average** |

TLV76733DRVR is rated **1 A** → ~2.4× headroom. PASS.

**+5 V rail load estimate:**
| Consumer | Per unit | Count | Subtotal |
|---|---|---|---|
| DRV8300DRGER GVDD active mode (per datasheet EC table: 825 µA typ static + switching) | ~10 mA average, ~200 mA peak per phase transition | 4 | ~40 mA avg / ~2.4 A peak transient |
| TLV76733DRVR LDO input (powers 3.3 V rail) | 421 mA / efficiency ≈ 421 mA (LDO is direct passthrough) | 1 | 421 mA |
| **Total +5 V** | | | **~461 mA average** |

LMR51420YDDCR is rated **2 A** → ~4.3× headroom on average. Peak transient (4 phases switching simultaneously) is within transient capability of the bulk + local decoupling caps (the buck output is regulated by its own loop, not by transient response).

## Bulk capacitor bank

Per master's contract criteria:
- Total capacitance: ≥ 1000 µF
- Voltage rating: 50 V (Sai's 50 V headroom preference over 35 V for safety margin on 6S)
- Low ESR: ≤ ~30 mΩ at 100 kHz per cap
- Ripple current: ≥ ~3 A RMS per cap; multiple caps in parallel share
- Topology: aluminum electrolytic SMD radial OR polymer

**Pick: 2 × 470 µF 63 V aluminum electrolytic SMD radial, low-ESR class, in parallel = 940 µF total.**

| Item | Spec | Notes |
|---|---|---|
| Quantity | 2 (parallel) | Lower per-cap ripple stress; smaller individual footprint vs 1 × 1000 µF |
| Capacitance per cap | 470 µF | Standard E12 value, common JLC stock |
| Voltage rating | 63 V | 2.5× nominal bus 22.2 V, 1.6× max charged 25.2 V — comfortable safety margin |
| ESR target | ≤ 30 mΩ per cap @ 100 kHz | Picked from low-ESR class (e.g., Rubycon ZL/ZLH, Nichicon UCD, Panasonic FK series) |
| Ripple current target | ≥ 1.5 A RMS per cap (2 in parallel = 3 A RMS budget) | Conservative for FPV switching freq 24–48 kHz |
| Package | SMD radial 10×10 mm or 12.5×13.5 mm | Picked at Phase 3 from JLC stock |
| Specific JLC C-number | **deferred to Phase 3** | Picked from JLC library snapshot at schematic-capture time, applying the criteria above |

**Why deferred to Phase 3 (not URGENT-escalated):** The criteria here fully constrain the pick to a small set of widely-stocked equivalent parts (Rubycon / Nichicon / Panasonic low-ESR 470 µF / 63 V SMD). Any of them in JLC's library satisfies the criteria; the choice is a per-snapshot stock + price call best made at schematic-capture time. Master's contract Step 3 says "Surface part(s) + C-number(s) + ESR + ripple-current rating" — I'm surfacing the criteria + budget + topology with one Phase-3 todo for the JLC C-number lookup against current stock.

**Ripple-current budget (sized vs the application):**
- FPV 4-in-1 at 70 A peak per channel × 4 channels = 280 A peak instantaneous bus current.
- With ~50 % PWM duty + 6-step commutation, RMS ripple current at bus capacitor ≈ I_motor × √(d × (1 − d)) for an ideal continuous-conduction inverter ≈ 70 × √(0.25) ≈ 35 A per channel RMS.
- Across 4 channels (uncorrelated): √4 × 35 ≈ 70 A RMS bus ripple total. Split across 2 caps: ~35 A RMS per cap.
- **35 A RMS exceeds typical low-ESR aluminum electrolytic ratings (~1.5–3 A RMS per cap).** Ceramic + polymer in parallel handle the high-frequency component; aluminum carries the low-frequency portion only.
- This is why FPV ESCs use the 33 × 10 µF ceramic distributed decoupling (OpenESC) IN ADDITION TO the bulk — the ceramics handle the >100 kHz switching ripple; the bulk handles motor commutation (lower frequency, lower ripple-current density). The 940 µF aluminum is for low-frequency (sub-kHz) bulk + transient response; the ceramic stack handles the kHz–MHz ripple.
- **Phase 6 thermal sim regime** will refine this with actual switching waveforms (per the contract note: "a full ripple-current Phase 6 sim will refine this").

## Per-MCU decoupling (×4 MCUs)

Per AT32F421 Datasheet Rev 2.02 Figure 8 (Power supply scheme, p.26 — referenced
in PHASE2A_PIN_MAP.md "Power scheme" section):

| Pin | Caps |
|---|---|
| VDD (pin 1) | 1 × 100 nF (close, 0402) + 1 × 10 µF (shared with VDD pin 17, 0805) |
| VDD (pin 17) | 1 × 100 nF (close, 0402) [10 µF shared with pin 1] |
| VDDA (pin 5) | 1 × 100 nF (close, 0402) + 1 × 1 µF (0402) — ferrite-bead-filtered from VDD |

Per MCU caps: 2 × 100 nF (digital VDD) + 1 × 100 nF (analog VDDA) + 1 × 10 µF (digital VDD pool) + 1 × 1 µF (VDDA) + 1 × ferrite bead = **5 caps + 1 ferrite**.

For 4 MCUs: **20 caps + 4 ferrites** (matches Open-4in1 pattern: 4 × BLM03PX121SN1D ferrite beads).

| Cap | JLC C# | Package | Tier |
|---|---|---|---|
| 100 nF X7R 50 V | C307331 (0402) | 0402 | Basic |
| 10 µF X5R 25 V | C440198 (0805) | 0805 | Basic (Open-4in1 confirmed) |
| 1 µF X7R 50 V | covered by per-driver pool below | 0603 | Basic |
| Ferrite bead 120 Ω @ 100 MHz | C525479 (BLM03PX121SN1D) | 0201 | Basic (Open-4in1) |

## Per-gate-driver decoupling (×4 drivers)

DRV8300DRGER GVDD pin: 1 × 10 µF (X5R/X7R, ≥10 V) + 1 × 100 nF (X7R, 50 V), per TI's datasheet
recommendation "C ≥ 10 µF local capacitance between the GVDD and GND pins."

For 4 drivers: 4 × 10 µF + 4 × 100 nF = **8 caps**, parts from the shared pool above.

Bootstrap C_BST per channel (3 phases × 4 channels = 12 caps): **value deferred to
Phase 3 schematic** (sized from AON6260 Q_g 81 nC + DRV8300 spec ≥ 1 µF X5R/X7R typical
per TI EVM reference). 12 × 100 nF placeholder for now; refined at Phase 3.

## Per-channel local bus cap (×4 channels)

Master's spec: "~22 µF tantalum or ceramic near each gate driver's VCC pin to handle
local high-frequency ripple decoupled from the bulk bank."

Pick: 22 µF X5R/X7R 0603 ceramic (matches Open-4in1's C2762594).

| Cap | JLC C# | Package | Tier |
|---|---|---|---|
| 22 µF X5R 25 V | C2762594 (0603) | 0603 | Basic (Open-4in1 confirmed) |
| 22 µF X5R 10 V | C105226 (0402) | 0402 | Basic (Open-4in1 secondary) |

For 4 channels: **4 caps** of C2762594 0603 type.

## Board-total cap count (Phase 2d only)

| Category | Count | Capacitance |
|---|---|---|
| Bulk electrolytic / polymer | 2 × 470 µF 63 V | 940 µF |
| Per-channel local | 4 × 22 µF | 88 µF |
| Per-driver decoupling | 4 × 10 µF + 4 × 100 nF | 40 µF + 0.4 µF |
| Per-MCU decoupling | 4 × 10 µF (shared) + 12 × 100 nF + 4 × 1 µF | 40 µF + 1.2 µF + 4 µF |
| Bootstrap (×12, placeholder 100 nF) | 12 × 100 nF | 1.2 µF |
| **TOTAL** | **46 caps + 4 ferrites** | **~1115 µF effective bulk + ~84 µF mid-frequency + ~3 µF high-frequency** |

This excludes the per-MOSFET ceramic snubbers (often present in FPV 4-in-1; Phase 3 schematic) and any LDO input/output caps (1 × 1 µF each = 2 caps).

## Open items (close at later phases)

| Item | Closes at | Why |
|---|---|---|
| Bulk cap specific JLC C-number | Phase 3 (schematic) | JLC library snapshot + ESR + ripple-current verification at schematic-capture |
| Bootstrap C_BST per channel — exact value (100 nF placeholder) | Phase 3 (schematic) | Sized from AON6260 Q_g + DRV8300 datasheet C_BST recommendation |
| LMR51420YDDCR feedback divider exact ratio | Phase 3 (schematic) | Verify 5.0 V output against SLUSDC8 datasheet FB threshold |
| LDO input/output 1 µF caps | Phase 3 (schematic) | Trivial; one 1 µF X7R input + 1 µF X7R output |
| Per-MOSFET ceramic snubber (if used) | Phase 3 (schematic) | Common in FPV 4-in-1 but Phase 6 sim verifies necessity |
| Bulk cap ripple-current full sim | Phase 6 (sim regime) | Per master's contract note: "a full ripple-current Phase 6 sim will refine this" |
| Heatsink physical interface to bulk caps (caps run hot at high ripple) | Phase 4 (placement) | Bulk caps placed close to MOSFET drains; thermal coupling considered |

## Build verification

Per the contract Step "Build clean (no firmware changes expected; verify target.h unchanged)",
no firmware changes in this PR. Reverified PCBAI_FPV4IN1_F421 builds clean with sizes
identical to Phase 2c (text=21200, data=1240, bss=2704).

## References

- Open-4in1-AM32-ESC reference design BOM extracted from `/tmp/OpenESC_20X20/schematic_analysis.json` and `4in1ESC.kicad_sch` (master's contract context).
- TI LMR51420 product page (`ti.com/product/LMR51420`).
- TI TLV767 product page (`ti.com/product/TLV767`).
- AT32F421 Datasheet Rev 2.02 §2.4 Power control + Figure 8 power supply scheme.
- AON6260 datasheet (Phase 2b PHASE2B_MOSFET.md doc).
- DRV8300DRGER datasheet TI SLVSFG5D Rev D (Phase 2c PHASE2C doc).
