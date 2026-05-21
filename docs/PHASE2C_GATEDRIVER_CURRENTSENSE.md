# Phase 2c — Gate driver + current sense + close DEAD_TIME / MILLIVOLT_PER_AMP

Per `DESIGN_PHASES.md` Phase 2 sub-phase 2c. Rigor §10 (grep-then-state),
R3 (no invented specifics), R17 (no loose threads).

Final outcome: both AM32 placeholders closed; gate driver + CSA + shunt locked
with documented part-compat flexibility for fab-time supplier substitution.

## Locked picks

| Subsystem | Primary part | JLC | Alternate (footprint-compatible at PCB level) |
|---|---|---|---|
| 3-phase gate driver | **TI DRV8300DRGER** | C3655801 (Extended, 497 stock, $0.61 @ 1pc / $0.39 @ 1k+) | Fortior FD6288Q (JLC C328453 / JSMSEMI C7466367) |
| Current-sense amplifier | **TI INA186A3IDCKR** (100 V/V gain, SC-70-6) | C-number verification deferred to Phase 3 schematic — see open items |
| Shunt resistor (per phase, ×12 per board) | **0.2 mΩ ±1 % 1 W low-inductance** (Vishay WSLP or equivalent class) | Specific JLC C-number verified at Phase 3 |

## DRV8300DRGER — datasheet capture (TI SLVSFG5D Rev D, March 2022)

| Item | Spec | Source |
|---|---|---|
| Part | DRV8300DRGER | TI doc cover, page 1 |
| Package | 24-Pin VQFN (RGE), 4.00 × 4.00 mm | Device Comparison Table, page 3 |
| Bootstrap diode | Integrated (D suffix) | Device Comparison Table |
| GLx polarity | Non-Inverted or Inverted (MODE pin selectable) | page 3 |
| Dead-time | **Variable** via DT pin resistor: 150 / 215 / 280 ns (DT floating or to GND); up to 1500-2600 ns (400 kΩ to GND) | EC table page 8, t_DEAD |
| V_GVDD (gate driver supply) | recommended 5–20 V | Rec Operating Cond., page 6 |
| V_BST (bootstrap) | rec 5–20 V | page 6 |
| t_PD (input → output prop delay) | 70 / 125 / 180 ns (min / typ / max) | EC table page 8 |
| t_PD_match (per phase) | -30 / ±4 / 30 ns | EC table page 8 |
| t_PD_match (phase-to-phase) | -30 / ±4 / 30 ns | EC table page 8 |
| t_R, t_F (rise/fall, C_LOAD=1 nF) | 10/24/50 ns rise; 5/12/30 ns fall | EC table page 8 |
| I_DRIVEP_HS (HS peak source) | 400 / 750 / 1200 mA | EC table page 8 |
| I_DRIVEN_HS (HS peak sink) | 850 / 1500 / 2100 mA | EC table page 8 |
| I_DRIVEP_LS (LS peak source) | 400 / 750 / 1200 mA | EC table page 8 |
| I_DRIVEN_LS (LS peak sink) | 850 / 1500 / 2100 mA | EC table page 8 |
| t_PW_MIN (min input pulse width) | 40 / 70 / 150 ns | EC table page 8 |
| V_GVDDUV (UVLO rising) | 4.45 / 4.6 / 4.7 V | EC table page 8 |
| V_BSTUV (Bootstrap UVLO rising) | 3.6 / 4.2 / 4.8 V | EC table page 9 |
| V_BOOTD (Bootstrap diode V_F @ 100 mA) | 2 / 2.3 / 3.1 V | EC table page 8 |
| R_BOOTD (Bootstrap dynamic R) | 11 / 15 / 25 Ω | EC table page 8 |
| Cross-conduction prevention | "Built-in" (Features bullet, page 1) | page 1 |
| T_J operating | -40 to +150 °C | Rec Op Cond, page 6/7 |

Pin assignment (24-pin VQFN, top view per Figure 6-1 page 4):
1=INLA, 2=INLB, 3=INLC, 4=GVDD, 5=MODE, 6=GND, 7=NC, 8=NC, 9=GLC, 10=GLB,
11=GLA, 12=SHC, 13=GHC, 14=BSTC, 15=SHB, 16=GHB, 17=BSTB, 18=SHA, 19=GHA,
20=BSTA, 21=DT, 22=INHA, 23=INHB, 24=INHC. PowerPAD (EPAD) is the device
ground / thermal pad.

## FD6288Q — pin-compat verification

Fortior datasheet REV_1.3 (fortiortech.com), 24-lead QFN 4×4 mm. From the
datasheet pages I extracted (1–5 of 17), the pin diagram with numbered pins
was not in the first 5 pages. The Open-4in1-AM32-ESC reference (master's
Phase 2c contract context) claims pin-compat with DRV8300 — I have not
verified pin-by-pin from the FD6288Q datasheet text in this PR. **Verification
deferred to Phase 3 schematic capture** when both footprints will be laid
side-by-side in KiCad against the schematic netlist (any mismatch shows up as
a netlist mismatch).

Spec-side comparison (the parts must agree on input drive level + supply
range for footprint substitution to be electrically safe; full pin-by-pin
agreement is the layout question):

| Metric | DRV8300DRGER | FD6288Q | Compatible? |
|---|---|---|---|
| Package | VQFN-24, 4×4 mm | QFN-24, 4×4 mm | ✓ same outline |
| V_CC / V_GVDD range | 5–20 V | 5–20 V | ✓ |
| Logic input V_IH | 2.0 V (3.3 V / 5 V compatible) | 2.7 V (3.3 V / 5 V compatible) | ✓ both work on 3.3 V MCU outputs |
| t_PD prop delay | 70/125/180 ns | t_on 300/450 ns ; t_off 100/160 ns | ≠ but both have internal cross-conduction prevention |
| Internal dead-time | 150–2600 ns adjustable via DT pin | 100/200/300 ns fixed | ≠ but both enforce safe dead-time at gate output |
| Peak source | 400/750/1200 mA | 1.1/1.5/1.9 A | both adequate for AON6260 Q_g 81 nC |
| Peak sink | 850/1500/2100 mA | 1.3/1.8/2.3 A | both adequate |
| HS supply range | up to 100 V (DRV8300) | up to +250 V (FD6288Q) | both ≫ 25.2 V bus |

**Verdict from spec side**: footprint-level compatibility is plausible
(same package + supply range + drive class) but the pin assignments must
be verified at schematic-capture time in Phase 3. If they mismatch, this
PR's "DRV8300/FD6288Q pin-compat" promise breaks and we'd commit to one
specific part in the BOM (DRV8300DRGER, per master's primary pick). Flag.

## Current sense — INA186A3IDCKR + 0.2 mΩ shunt

Architecture: per-phase low-side shunt → INA186A3 CSA → MCU ADC. AM32
standard pattern (Open-4in1-AM32-ESC reference + SEQURE_4IN1 reference).

Per-MCU instance: 3 shunts + 3 CSAs (one per phase). Board total: 12 shunts +
12 CSAs across 4 channels.

| Item | Spec | Source |
|---|---|---|
| CSA part | TI INA186A3IDCKR | TI datasheet SBOS964A (linked from ti.com/product/INA186 — `/part-details/INA186A3IDCKR`) |
| CSA package | SC-70-6 (DCK), small footprint per CSA | TI product page |
| CSA gain | 100 V/V (A3 variant) | TI part number suffix convention |
| CSA V_supply | single 1.7–5.5 V (use 3.3 V rail) | TI datasheet |
| CSA V_CM range | -0.2 to +40 V (independent of supply) | TI datasheet |
| CSA JLC C-number | **deferred to Phase 3 schematic verification** — see open items | |

Shunt:

| Item | Spec | Source |
|---|---|---|
| Resistance | 0.2 mΩ ±1 % | Open-4in1-AM32-ESC reference; segment standard |
| Power rating | ≥ 1 W (continuous: 0.2 mΩ × 70² = 0.98 W) | computed |
| Topology | Low-inductance metal-foil shunt (Vishay WSLP / WSL2512 / equivalent) | industry standard for current-sense on switched-current paths |
| Specific JLC part | **deferred to Phase 3 schematic capture** — pick from JLC-stocked WSLP / KOA / Susumu / equivalent at that time | |
| Dissipation per shunt | 0.98 W at 70 A continuous (RMS) | I² × R |
| Total shunt dissipation per board | 12 × 0.98 = 11.7 W | computed; included in Phase 2b thermal envelope |

## MILLIVOLT_PER_AMP derivation

```
MILLIVOLT_PER_AMP = shunt[mΩ] × CSA_gain     [units: mV/A]
                  = 0.2 × 100
                  = 20 mV/A
```

Sanity check: 70 A peak current × 20 mV/A = 1.4 V at the AT32F421 ADC input,
which is 42 % of the 3.3 V ADC reference. Comfortable headroom both above
(no clipping until ~165 A) and below (noise-floor margin at low currents).

Locked in `firmware/am32-target/PCBAI_FPV4IN1_F421.target.h`:
```c
#define MILLIVOLT_PER_AMP 20
```

## DEAD_TIME derivation

**Critical units discovery (Rigor §10)**: AM32's `DEAD_TIME` #define is NOT
a value in nanoseconds. It's the raw 8-bit `DTG[7:0]` value written to
`TMR1->brk.dtc` (see `Mcu/f421/Src/peripherals.c:115`).

Per the AT32F421 reference manual / STM32 standard TMR1 dead-time generator
encoding, with the timer's APB2 clock = 120 MHz (set in
`Mcu/f421/Src/peripherals.c:55–68` via `crm_pll_config(CRM_PLL_SOURCE_HICK,
CRM_PLL_MULT_30)`) and default `CKD=00` (i.e. `T_DTS = T_CK_INT = 1/120 MHz
= 8.33 ns`):

```
DTG[7] = 0  ⇒  dead time = DTG[6:0] × T_DTS = N × 8.33 ns       (N ≤ 127)
DTG[7:6] = 10 ⇒  dead time = (64 + DTG[5:0]) × 2 × T_DTS         (N: 128–191)
DTG[7:5] = 110 ⇒ dead time = (32 + DTG[4:0]) × 8 × T_DTS         (N: 192–223)
DTG[7:5] = 111 ⇒ dead time = (32 + DTG[4:0]) × 16 × T_DTS        (N: 224–255)
```

So the existing AM32 targets actually configure:
- SEQURE_4IN1_F421 `DEAD_TIME 80` → 80 × 8.33 = **667 ns** (not 80 ns as
  master's contract assumed)
- TBS_6S_4IN1_F421 `DEAD_TIME 60` → 500 ns
- TBS_8S_4IN1_F421 `DEAD_TIME 30` → 250 ns
- AIRBEE_F421 `DEAD_TIME 22` → 183 ns

The contract's "DEAD_TIME=80 ≈ 80 ns" assumption was incorrect. Pattern goes
in worker memory: AM32 DEAD_TIME register value is raw DTG, not ns.

**Required dead-time for our DRV8300DRGER + AON6260 + FD6288Q-compatibility**:

The actual dead-time at the MOSFET gates is enforced by the gate driver's
internal cross-conduction prevention (both DRV8300 and FD6288Q have this),
plus any AM32-generated MCU-output dead-time. AM32's role is to ensure
non-overlapping inputs to the driver.

Worst-case minimum dead-time analysis (worker's call, sureshot margin):
- AON6260 turn-off time (`t_d_off + t_f`) ≈ 50 + 11.5 = 61.5 ns typ, ~92 ns
  conservative (datasheet doesn't give max, take 1.5× typ).
- Driver propagation skew: DRV8300 `t_PD_match` ±30 ns max; FD6288Q `MT`
  matching delay 30 ns max. Worst-case: 30 ns.
- Driver t_PD asymmetry (relevant if substituting between DRV8300 and
  FD6288Q at fab time): FD6288Q has `t_on=300 typ / t_off=100 typ` so
  asymmetry up to 200 ns. The driver's internal cross-conduction logic
  handles this at the gate, but the MCU input timing should still be
  conservative to satisfy the worst worst-case.
- Safety margin: 1.5× per master's contract.

Required AM32 DEAD_TIME (at MCU input pair, before driver):
- For DRV8300 path: ≈ 92 + 30 + safety = ~180 ns
- For FD6288Q path: ≈ 92 + 30 + 200 (asymmetry) + safety = ~480 ns

Picking DTG = 60 = **500 ns** at 120 MHz timer clock:
- Comfortably covers both driver paths.
- Matches TBS_6S_4IN1_F421 (which uses the same architecture pattern in the
  segment — sureshot per Sai's tiebreaker).
- Adds 80 % headroom over the minimum DRV8300 requirement and meets the
  FD6288Q substitution case.

Locked in target.h:
```c
#define DEAD_TIME 60   /* = 500 ns at 120 MHz TMR1 clock, DTG standard enc. */
```

## Reference cross-check (Rigor §10)

| Reference | Their config | Our value | Match? |
|---|---|---|---|
| SEQURE_4IN1_F421 (6S 4-in-1 AM32, datasheet at sequremall.com) | DEAD_TIME=80 → 667 ns; MILLIVOLT_PER_AMP=9 (their shunt × CSA combo) | DEAD_TIME=60 → 500 ns; MILLIVOLT_PER_AMP=20 | DEAD_TIME ours is tighter (faster MOSFET); MILLIVOLT_PER_AMP differs by their shunt/CSA pick |
| TBS_6S_4IN1_F421 (`Inc/targets.h` lines ~547) | DEAD_TIME=60 | DEAD_TIME=60 | ✓ exact match |
| Open-4in1-AM32-ESC reference design | DRV8300 + 0.2 mΩ + INA186 (per master's contract context) | DRV8300 + 0.2 mΩ + INA186 | ✓ matches |
| TBS_8S_4IN1_F421 | DEAD_TIME=30 → 250 ns | 60 → 500 ns | We're more conservative |

## Build verification (Phase 2c re-build)

```
$ make -C /home/novatics64/escworker/AM32 ARM_SDK_PREFIX=... \
       obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf
Memory region         Used Size  Region Size  %age Used
           FLASH:       22408 B        27 KB     81.05%
          EEPROM:          0 GB         1 KB      0.00%
       FILE_NAME:          32 B         32 B    100.00%
             RAM:        3936 B        15 KB     25.62%
```

`arm-none-eabi-size`: text=21200, data=1240, bss=2704, dec=25144 — **identical
to Phase 2a/2b** since only `#define` constants changed (no new code paths).
`-Werror -Wall -Wextra` clean.

## Open items (close at later phases)

| Item | Closes at | Why |
|---|---|---|
| FD6288Q pin-by-pin compat verification | Phase 3 (schematic) | Datasheet pages I extracted lacked the full pin table; KiCad netlist diff against both footprints settles it |
| INA186A3IDCKR JLC C-number confirmation | Phase 3 (schematic) | JLC listing returned generic page in this PR; visual confirmation at schematic-capture time |
| Specific 0.2 mΩ shunt part + JLC C-number | Phase 3 (schematic) | Picked from JLC-stocked WSLP / WSL2512 / KOA / Susumu against the JLC library snapshot at that time |
| Shunt thermal contribution to envelope | Phase 4/6 | 11.7 W board total from shunts feeds the Phase 6 thermal sim |
| Bootstrap C_BST cap value | Phase 3 (schematic) | Sized from AON6260 Q_g + DRV8300 spec (typ ≥ 1 µF X5R/X7R) |
| Driver V_GVDD source | Phase 2d (bus caps + BEC) | The 5–20 V gate-driver supply comes from the on-board BEC |
| DT pin resistor (for DRV8300 internal dead-time) | Phase 3 (schematic) | Pick to give 200-300 ns internal dead-time (40 kΩ → 200 ns typ per datasheet) |

## Open items NOT for later closure (this PR is the final spec)

- AM32 `DEAD_TIME` value (60 = 500 ns) — done.
- AM32 `MILLIVOLT_PER_AMP` value (20) — done.
- Gate driver pick (DRV8300DRGER primary, FD6288Q footprint alternate) — done.
- CSA family (INA186A3 100 V/V) — done.
- Shunt resistance (0.2 mΩ) — done.
