# Phase 2.5 — Footprint / fit reality check

Per `DESIGN_PHASES.md` Phase 2.5: "A cheap placement-only sketch to confirm
everything physically fits the intended form factor before schematic decisions
cascade. Acceptance: fit confirmed plausible."

Rigor §10: every package dimension cited from the part's datasheet (Phases
2a–2e PRs link the underlying datasheets).

## TL;DR

**Form factor: 50 × 50 mm**, double-sided assembly, 4× M3 mounts on 40 × 40 mm
Betaflight stack pattern, top-side aluminum heatsink ~46 × 32 mm covering the
B.Cu MOSFET cluster.

Worker's pick (only candidate that meets the ≥ 15 % per-side routing margin):
- **40 × 40 mm — REJECTED** (B.Cu overflows by 26 % before routing).
- **30 × 60 mm — REJECTED** (B.Cu overflows by 12 % before routing).
- **50 × 50 mm — PASSES** (F.Cu 64 % margin, B.Cu 19 % margin — meets the ≥ 15 %
  per-side criterion).
- 60 × 60 mm — comfortable (75 % / 44 %) but overkill; only viable as a fallback
  if Phase 4 placement uncovers blockers we didn't model.

## Component area budget (re-derived per Rigor §10)

Output of `sims/phase2_5_fit/area_budget.py` (every dimension pulled from the
part's datasheet, cited in the script's comment column):

| Part | Qty | w × h mm | Each mm² | Total mm² | Side |
|---|---|---|---|---|---|
| AON6260 phase MOSFETs | 24 | 5.0 × 6.0 | 30.0 | **720.0** | B |
| AON6260 reverse-pol parallel | 4 | 5.0 × 6.0 | 30.0 | 120.0 | B |
| Shunt 0.2 mΩ 2512 | 12 | 6.3 × 3.2 | 20.2 | 241.9 | B |
| Bulk cap 470 µF 63 V | 2 | 12.5 × 13.5 | 168.75 | **337.5** | B |
| SMBJ33A TVS | 1 | 4.3 × 3.4 | 14.6 | 14.6 | B |
| LMR51420YDDCR buck | 1 | 2.9 × 1.6 | 4.6 | 4.6 | B |
| XRIM160808SR47MBCD inductor | 1 | 1.6 × 0.8 | 1.3 | 1.3 | B |
| AT32F421K8T7 LQFP-32 | 4 | 9.0 × 9.0 | 81.0 | **324.0** | F |
| DRV8300DRGER VQFN-24 | 4 | 4.0 × 4.0 | 16.0 | 64.0 | F |
| INA186A3IDCKR SC-70-6 | 12 | 2.0 × 2.1 | 4.2 | 50.4 | F |
| TLV76733DRVR WSON-6 | 1 | 2.0 × 2.0 | 4.0 | 4.0 | F |
| JST SM08B-SRSS-TB | 1 | 8.0 × 3.4 | 27.2 | 27.2 | F |
| USBLC6-2SC6 ESD | 3 | 2.9 × 2.8 | 8.1 | 24.4 | F |
| Decoupling — VDD 100nF 0402 | 8 | 1.0 × 0.5 | 0.5 | 4.0 | F |
| Decoupling — VDDA 100nF 0402 | 4 | 1.0 × 0.5 | 0.5 | 2.0 | F |
| Decoupling — VDD 10µF 0805 | 4 | 2.0 × 1.25 | 2.5 | 10.0 | F |
| Decoupling — VDDA 1µF 0402 | 4 | 1.0 × 0.5 | 0.5 | 2.0 | F |
| Decoupling — VDDA ferrite 0201 | 4 | 0.6 × 0.3 | 0.18 | 0.7 | F |
| Driver 10µF 0805 | 4 | 2.0 × 1.25 | 2.5 | 10.0 | F |
| Driver 100nF 0402 | 4 | 1.0 × 0.5 | 0.5 | 2.0 | F |
| Bootstrap 100nF 0402 | 12 | 1.0 × 0.5 | 0.5 | 6.0 | F |
| Channel local 22µF 0603 | 4 | 1.6 × 0.8 | 1.28 | 5.1 | F |
| LED 0603 | 5 | 1.6 × 0.8 | 1.28 | 6.4 | F |
| LED R 0402 | 5 | 1.0 × 0.5 | 0.5 | 2.5 | F |
| Motor pads (3 mm dia) | 12 | π·1.5² | 7.07 | 84.8 | F |
| SWD pads (1 mm dia) | 12 | π·0.5² | 0.79 | 9.4 | F |

**Totals (pure-component area):**
- F.Cu pure: **638.9 mm²**
- B.Cu pure: **1440.0 mm²**
- Combined: **2078.9 mm²** (consistent with master's ~2317 mm² estimate; the
  ~10 % gap is from passive-cap area I've consolidated under decoupling rows
  vs master's more granular roll-up).

**With +40 % routing overhead (FPV-dense convention):**
- F.Cu required: **894.5 mm²**
- B.Cu required: **2015.9 mm²** ← this is the constraining side

## Fit verdict per candidate form factor

| Form factor | Area (mm²) | F.Cu margin | B.Cu margin | Verdict |
|---|---|---|---|---|
| 40 × 40 mm | 1600 | +44.1 % | **−26.0 %** | **FAIL** — B.Cu overflows |
| 50 × 50 mm | 2500 | +64.2 % | **+19.4 %** | **OK** (≥ 15 % margin both sides) |
| 30 × 60 mm | 1800 | +50.3 % | **−12.0 %** | **FAIL** — B.Cu overflows |
| 60 × 60 mm | 3600 | +75.2 % | +44.0 % | comfortable but overkill |

**B.Cu is the constraining side** — the 24 phase MOSFETs (720 mm²) + 4
reverse-polarity FETs (120 mm²) + 12 shunts (242 mm²) + 2 bulk caps (337 mm²)
= 1419 mm² pure component, dwarfs the F.Cu signal-side 639 mm². This drives the
form-factor choice.

## F.Cu / B.Cu split rationale

**F.Cu (signal side, top):**
- 4× MCU (LQFP-32, 9×9 mm with leads)
- 4× gate drivers (VQFN-24, 4×4)
- 12× CSAs (SC-70-6)
- 1× buck IC + 1× LDO
- ESD arrays (3× SOT-23-6)
- All decoupling ceramic caps
- LEDs + status resistors
- FC connector at edge
- 12× motor solder pads at edge
- 12-16× SWD test pads

**B.Cu (power side, bottom):**
- 24× phase MOSFETs (AON6260 DFN5x6) in a 6×4 grid
- 12× shunt resistors (one row alongside MOSFETs)
- 2× bulk caps (470 µF 63 V, 12.5×13.5 mm packages, placed at edges)
- 4× reverse-polarity FETs (in series with GND return)
- 1× SMBJ33A TVS
- 1× buck inductor (small — could move to F.Cu if needed)

**Why this split:** the power-side B.Cu carries the high-current paths (MOSFETs
+ shunts + bulk + reverse-polarity) where wide copper pours and the heatsink
interface live. The signal-side F.Cu carries the low-current control logic +
analog measurement (CSAs at low side need short shunt-to-CSA traces — verify at
Phase 4 placement that the shunt-to-CSA distance stays minimal even across
F.Cu/B.Cu sides via direct via stitching). Industry convention for FPV 4-in-1s
of this current class (Tekko32 Metal, SEQURE E70, T-Motor F55A).

## Mounting + connector accessibility (Playbook trap T7)

- **4× M3 mounting holes on 40 × 40 mm Betaflight stack pattern** (3.2 mm dia
  clearance through-holes), one at each corner inside the 50 × 50 board (5 mm
  inset). M3 standoffs to FC + battery deck.
- **FC connector**: JST SM08B-SRSS-TB on the **top edge** of F.Cu, centered
  horizontally — accessible from the FC stack above. 8.0 × 3.4 mm body, side-
  entry receptacle. ✓ edge-accessible per T7.
- **Motor pads**: 3 pads per channel × 4 channels = 12 pads distributed along
  the 4 board edges (3 per edge, one edge per channel). Each pad is 3.0 mm dia
  SMD with 0.5 mm clear border. ≥ 1.0 mm pad-to-pad clearance for solderability.
  ✓ edge-accessible per T7.
- **SWD pads**: 4 sets along the left edge (12-16 pads total). Castellated-edge
  pattern preferred for jig-flash; final choice at Phase 4 placement. ✓
  edge-accessible per T7.

## Heatsink interface plan

- **Footprint on B.Cu**: covers the 6×4 MOSFET grid (42 × 28.5 mm pure FET area;
  + 2 mm border for thermal contact spreading) → **~46 × 32 mm aluminum block**.
- **Material**: 6061-T6 aluminum (sufficient k≈170 W/m·K), 3-5 mm thick (height
  budget below).
- **Thermal interface**: silicone thermal pad (e.g., Bergquist Gap Pad VOUS or
  3M 5519), 0.5 mm thick, 4-6 W/m·K thermal conductivity, ~1500 V isolation.
- **Mounting**: 4× M2 screws through PCB into tapped holes in the heatsink, or
  M2 standoffs + screws from F.Cu side. Phase 4 placement decides between
  through-PCB tap vs adhesive bond.
- **Heatsink → ambient**: top-side aluminum can be finned or flat depending on
  Phase 6 sim verdict. For the Envelope 2 thermal budget (Phase 2b
  `PHASE2B_MOSFET.md`), a finned heatsink with ~5× effective area multiplier
  is the working assumption.

## Z-axis (height) budget

| Layer | Component | Height (mm) |
|---|---|---|
| F.Cu — tallest | Bulk cap (if on F.Cu fallback) OR JST receptacle | 1.5–13.5 |
| F.Cu — typical | MCU / driver / IC | 1.0–1.7 |
| PCB | 6-layer FR-4 | 1.6 |
| B.Cu — typical | MOSFET DFN5x6 + shunts | 1.0–1.5 |
| B.Cu — bulk caps (preferred B.Cu placement) | 470 µF 63 V SMD radial | 13.5 |
| Thermal interface pad | silicone | 0.5 |
| Heatsink (over MOSFETs) | aluminum block + fins | 3–5 |

**Two layout options** (Phase 4 placement chooses):

- **Option A — Bulk caps on B.Cu** (preferred per F.Cu/B.Cu split table):
  total board+heatsink z-stack = 1.6 (PCB) + 13.5 (bulk caps on B.Cu near edge)
  + 0.5 (pad) + 5 (heatsink over MOSFETs only) = **~14.5–20.6 mm** depending
  on whether the heatsink covers caps too. Bulk caps placed at edges so they
  don't collide with heatsink.
- **Option B — Bulk caps on F.Cu** (if B.Cu MOSFET layout density requires
  it): total stack on F.Cu = 13.5 (cap) + 1.6 (PCB) + 1.5 (MOSFET on B.Cu) + 0.5
  (pad) + 5 (heatsink) = **22 mm**. More headroom on B.Cu for heatsink but
  taller F.Cu profile.

**FPV stack height compatibility**: typical FPV stacks allow 5-10 mm per
board level. Our 14-22 mm total z-stack at the ESC level requires either:
(a) custom dual-standoff structure between FC and ESC, OR
(b) low-profile aluminum-polymer bulk caps (e.g., Panasonic FP series ~6 mm
tall) — revisit Phase 2d bulk cap pick at Phase 4 if z-stack becomes blocker.

**Flagged for Phase 4 placement**: bulk-cap height is the chief z-axis driver.
Phase 4 decides between Option A/B + optionally swaps to low-profile polymer.

## Placement sketches

Generated by `sims/phase2_5_fit/placement_sketch.py`:

- `sims/phase2_5_fit/placement_F_Cu.png` — signal side (top): MCUs at corners,
  gate drivers adjacent, CSAs near each channel, FC connector on top edge,
  buck+LDO on right edge, motor pads on all 4 edges (red dots), SWD on left
  edge, ESD between FC and MCU cluster.
- `sims/phase2_5_fit/placement_B_Cu.png` — power side (bottom): 6×4 MOSFET
  grid centered (hatched heatsink footprint overlay), 12 shunts in a row along
  the GND-return path, 2 bulk caps at left/right edges, 4 reverse-polarity FETs
  in a row near the input edge, TVS at input.

These are placement-only diagrams — no traces, no exact pin assignments. The
goal per the playbook is the "cheap sketch" to confirm fit plausibility before
schematic decisions cascade. Real placement happens at Phase 4.

## What Phase 4 placement will refine

- Exact pin-by-pin orientation per part (current 2D blocks don't show pin 1).
- Routing channels between MOSFET clusters (signals + GND return).
- Shunt-to-CSA via stitching distance (analog noise sensitivity).
- Heatsink mounting hardware (through-PCB tap vs adhesive).
- Bulk cap final placement (B.Cu Option A default; F.Cu Option B if blocked).
- Solder mask + silkscreen + courtyard ratios.

## Verdict (per pass criteria)

- [x] Component footprint area verified: 2079 mm² total, 639 / 1440 mm² per side.
- [x] Form factor chosen + justified: **50 × 50 mm** (only candidate meeting
      ≥ 15 % per-side routing margin).
- [x] Heatsink interface specified: ~46 × 32 mm Al6061, 0.5 mm silicone pad,
      M2 mount.
- [x] Edge clearance + 4× M3 mounting holes on 40 mm Betaflight pattern.
- [x] Connector accessibility verified per T7 (FC on top edge, motor pads
      distributed on all 4 edges, SWD on left edge).
- [x] No obvious 3D collision (z-stack 14-22 mm; bulk-cap height flagged for
      Phase 4 review).
- [x] Build clean unchanged (firmware not touched; PCBAI_FPV4IN1_F421 still
      compiles at text=21200, data=1240, bss=2704).

## Items flagged for Phase 4 placement

| Item | Why |
|---|---|
| Bulk-cap height (13.5 mm aluminum vs ~6 mm polymer alternative) | z-axis budget driver if FPV stack constrains |
| Heatsink mounting: through-PCB tap vs adhesive | Mechanical reliability vs assembly time |
| MOSFET grid orientation (6×4 vs 4×6) | Routing density vs heatsink shape |
| Shunt-to-CSA cross-side via stitching | Analog noise floor |
| Per-channel MCU↔driver locality | DShot signal integrity (50 ns edges) |

## Items flagged for Phase 6 thermal sim

- Heatsink fin geometry (passive natural vs prop-wash forced).
- Bulk-cap dissipation in the per-channel local current-loop.
- Cross-side via stitching density vs thermal coupling F.Cu ↔ B.Cu.
- Real prop-wash h vs the 80 W/m²·K conservative envelope-2 assumption.
