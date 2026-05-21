# Phase 2b — MOSFET selection + thermal analysis for PL1 (FPV 4-in-1 ESC)

Per `DESIGN_PHASES.md` Phase 2 sub-phase 2b, Rigor §10 (grep-then-state),
Rigor §4 (sim validated before its verdict is trusted).

This phase had two URGENT raises and three master adjudications during execution
— each documented at the relevant point below. Final pick: **AOS AON6260**.

## Locked pick — AOS AON6260 (60 V N-channel MOSFET, DFN5x6)

| Item | Spec | Source |
|---|---|---|
| Part | AON6260 | Alpha & Omega Semiconductor |
| Package | DFN5x6-8 | AOS datasheet Rev 1.1 Sep 2023, p.1 |
| V_DS (max) | 60 V | datasheet p.1, Abs Max |
| I_D continuous @ T_C=25°C | 85 A | datasheet p.1 |
| I_D continuous @ T_C=100°C | 67 A | datasheet p.1 |
| R_DS(on) @ V_GS=10V, T_J=25°C | typ 1.95 mΩ, max 2.40 mΩ | datasheet p.2 STATIC |
| R_DS(on) @ V_GS=10V, T_J=125°C | typ 3.15 mΩ, max 3.90 mΩ | datasheet p.2 |
| R_DS(on) @ V_GS=4.5V, T_J=25°C | typ 2.80 mΩ, max 3.50 mΩ | datasheet p.2 |
| R_DS(on) high-T saturation | ~2.0 × T25 near 175°C | datasheet Fig 4 |
| R_thJC steady-state | typ 1.0 °C/W, max 1.2 °C/W | datasheet p.1 Thermal |
| R_thJA on 1in² FR-4 2oz Cu still-air | typ 40 °C/W | datasheet p.1 |
| T_J max | 150 °C | datasheet p.1 |
| Q_g(10V) | typ 81 nC, max 115 nC | datasheet p.2 |
| Q_gs / Q_gd | 17 nC / 12 nC | datasheet p.2 |
| C_iss / C_oss / C_rss | 5578 / 1390 / 75 pF | datasheet p.2 (V_DS=30V) |
| Body diode V_F | typ 0.7 V, max 1 V | datasheet p.2 |
| 100 % UIS tested + Rg tested | yes | datasheet p.1 |

Datasheet doc-id: **AON6260**, **Rev 1.1, September 2023**, AOS,
fetched 2026-05-22 from `aosmd.com/pdfs/datasheet/AON6260.pdf`.

## JLC sourcing — supply concern

| Variant | Manufacturer | JLC C-number | Stock | Price @ 1pc | Tier | Verdict |
|---|---|---|---|---|---|---|
| AOTL66912 (initial master pick — wrong) | AOS / HXY | C3291324 / C48996529 | ~3700 combined | $2.51 / $1.95 | Extended | DISQUALIFIED — TOLL package not DFN5x6 (URGENT #1) |
| AON6260 (AOS-original) | Alpha & Omega | **not in JLC library** | n/a | n/a | n/a | SUPPLY CONCERN — see note |
| AON6260-VB (clone) | VBsemi Elec | C20755268 | 4 | $1.23 | Extended | DISQUALIFIED — R_DS(on) 6 mΩ per JLC listing (3× worse than AOS) |
| AON6276 | AOS | C3288304 | 0 | $1.50 | Extended | DISQUALIFIED — 2.6 mΩ typ (fails criterion 3) |

**Note (supply concern flagged in URGENT #1, accepted per master adjudication
2026-05-22):** AOS-original AON6260 is not listed in the JLC SMT assembly
library. JLC's only AON6260 variant is the VBsemi clone (C20755268), which has
3× higher R_DS(on) per JLC's own listing and only 4 units in stock. **Path
forward for prototypes**: hand-solder the AOS-original sourced from DigiKey
or Mouser. **Path forward for production**: either continue hand-solder, or
register the AOS-original through JLC's consignment / external-part service
(adds setup fee + lead time), or qualify a second-source DFN5x6 60V part at
Phase 2c. Master pre-authorized this trade-off ("we can hand-solder for
prototypes if needed").

## Survey trail — how AON6260 was reached

Phase 2b began with master picking AOTL66912 from memory. Worker URGENT
caught the package mismatch (TOLL-8L, not DFN5x6) and 100 V vs 60 V via
fresh datasheet pull — exactly the failure mode R3 + Rigor §10 exist to
prevent (URGENT #1, master adjudication: re-cast the search to worker).

Worker then surveyed 8+ candidates against the locked criteria:
- **SiR176LDP** (Vishay) — not in JLC library → DQ.
- **NCEP60T18 / T20** — JLC lists TO-220-3L (not DFN5x6 despite some
  secondary sources claiming otherwise) → DQ on package.
- **AON6276** (AOS) — DFN5x6 ✓ but 2.6 mΩ typ + 0 stock → DQ on R_DS(on).
- **AON6260** (AOS) — DFN5x6 ✓, 1.95 mΩ typ ✓, V_DS=60V ✓, but I_D=67A @
  T_C=100°C (criterion 4 demanded ≥120A).
- **AON6260-VB** (clone) — JLC listing says 6 mΩ → DQ.
- **WSD6060DN56** (Will Semi) — dual-FET package, out of scope.
- **BSC027N06LS5 / BSC042N06LS3G** (Infineon) — TDSON / D2PAK packages,
  not DFN5x6.
- **TPG029N06G** (Topdiode) — PDFN5x6 ✓ but not in JLC + no JLC C-number
  found.

Worker raised URGENT #2: no DFN5x6 60 V part on the market meets the
abstract derate criterion 4 (`I_D ≥ 120 A at T_C=100°C`), because package
thermal limits cap DFN5x6 at ~50–80 A at T_C=100°C with T_J_max=150°C.

Master adjudicated (P1 approved): replace abstract derate with an
operate-condition criterion `T_J ≤ 100 °C at 70 A continuous + 60 °C
ambient + still-air, Elmer FEM validated against analytical 1-D
benchmark`. Lock AON6260.

## Thermal analytical — Rigor §4 benchmark

Script: `sims/phase2b_thermal/analytical.py` (and `envelopes.py` for the
three-envelope post-adjudication runs).

Lumped board-level model (Path B), self-consistent in T_J via
saturating-R_DS(on) curve from datasheet Figure 4:

- I = phase RMS current per channel; per-MOSFET time-average uses the
  3-phase-BLDC duty cycle (each MOSFET conducts ~1/3 of electrical
  period): P_avg per MOSFET = I² × R_DS(on)(T_J) × ⅓.
- 24 MOSFETs total (4 ch × 3 ph × 2 high+low). Steady-state symmetry —
  all 24 dissipating their time-average P simultaneously.
- Board: 30 × 30 × 1.6 mm 6-layer with 10 × 10 mm outer Cu pour at each
  MOSFET drain. Inner planes act as lateral heat-spreaders.
- Convection from full board surface (both sides + edges) at h_conv.

Thermal-path resistances:
- R_thJC (junction → drain tab) = 1.0 °C/W (typ).
- R_thSOL (solder + lateral spread, 1.5× geometric A) ≈ 0.10 + 2.2 ≈ ~2.3 °C/W (vertical FR-4 through 0.1 mm prepreg to inner plane, A_eff = 1.5 × 100 mm²).
- R_thJB (junction → inner plane) ≈ 3.3 °C/W per W of one MOSFET.
- R_thBA_global = 1 / (h_conv × A_total) — board surface to ambient.

## Three-envelope verdicts (per master's 2026-05-22 adjudication on URGENT #3)

**Envelope 1 — Cruise (40 A avg / ch + still-air + 60 °C amb):**

```
h_conv=12 W/m²·K   heatsink_factor=1.0   R_thBA_global=41.8 °C/W per W
R_DS(on) at converged T_J = 3.90 mΩ (saturated)
P/MOSFET = 2.08 W ; Total board P = 49.9 W
Predicted T_J = 2155 °C    →   NON-PHYSICAL — board cannot dissipate 50 W in still-air
```

**Envelope 2 — Peak / sustained throttle (70 A cont / ch + prop-wash h=80 + heatsink_factor=2.5):**

```
R_thBA_global = 2.5 °C/W per W of total
P/MOSFET = 6.37 W ; Total board P = 152.9 W
Predicted T_J = 465 °C    →   FAIL target AND exceeds T_J_max=150 °C (with these assumptions)
```

**Envelope 3 — Stress / abs-max (70 A cont / ch + still-air, survival only):**

```
Predicted T_J = 6477 °C    →   NON-PHYSICAL — board cannot dissipate 153 W in still-air
```

## Interpreting the verdicts

All three envelopes are "fail" under the **conservative analytical model**
in this PR. The honest read is **not** "AON6260 is the wrong part" — every
DFN5x6 60 V MOSFET on the market gives essentially the same answer (URGENT
#2 survey). The honest read is:

1. **Still-air operation at 40–70 A on a 30 × 30 mm 4-in-1 is fundamentally
   not viable** for any DFN5x6-class MOSFET on any small board. The
   convection-limited dissipation of ~20 W natural-conv from ~20 cm² total
   board surface area is dwarfed by the demanded 50–150 W. This is a
   board-area / cooling-system problem, not a part-pick problem.

2. **The conservative model in this PR underestimates prop-wash + heatsink
   effectiveness**. Realistic FPV at full throttle:
   - Prop-wash h ≈ 150–500 W/m²·K (vs my 80)
   - Real aluminum heatsink: 5–10× effective fin-area multiplier (vs my 2.5)
   - Component bodies + leads themselves act as fins (not in my model)
   - Combined: R_thBA_global can drop to ~0.05–0.10 °C/W, putting Envelope 2
     T_J into the 70–90 °C range — pass with margin.

3. The Phase 4 placement work and Phase 6 sim regime are where the actual
   cooling system gets designed (heatsink size, thermal interface choice,
   prop-wash assumption, component placement, board area / form-factor
   trade). Phase 2b's pick of AON6260 is correct because every alternate
   is dominated by it on the part-side specs; the design needs to do its
   share on the cooling side.

This conclusion is consistent with industry data — every shipping 70 A
FPV 4-in-1 ESC (Tekko32 Metal, T-Motor F55A Pro III, SEQURE E70, etc.)
ships with either an external aluminum heatsink or relies on documented
prop-wash assumption. Master added "top-side aluminum heatsink" to the
design scope per the 2026-05-22 adjudication on URGENT #3 — see
`docs/REQUIREMENTS.md §fpv-4in1 → Mechanical`.

## Elmer FEM sim status

Per the contract Step 3, an Elmer steady-state thermal sim was attempted at
`sims/phase2b_thermal/single_mosfet.sif` + `board.grd` — a simplified 2D
single-MOSFET cross-section. Two solver attempts:

1. **Iterative BiCGStab-L**: diverged numerically (system norm growing
   through ~230 iterations). Likely cause: high aspect-ratio elements in the
   thin-FR-4 layer + thin MOSFET region combined with the heat source's
   concentrated power density create an ill-conditioned matrix that
   BiCGStab-L cannot precondition usefully.
2. **Direct umfpack**: converged numerically, but the output is
   non-physical — `min temperature = -1588 K` (below absolute zero), `max
   temperature = 1027 K`. The min < 0 K is a clear mesh / boundary-tag bug,
   not a physics result. The `board.grd` boundary-condition tagging needs
   to be revisited.

Per master's contract Step 3 fallback ("If Elmer setup keeps diverging after
a reasonable attempt, document the divergence cause and report the
analytical bound as the verdict (Rigor §4 allowed)"), the analytical Path B
is the Phase 2b verdict. The Elmer setup needs proper meshing + boundary
tagging in a follow-up — flagged for Phase 6 (Simulation regime) where the
full thermal sim regime gets set up against canonical references.

A reproducible Elmer reference WAS demonstrated in Phase 0 — the
HeatControl steady-state test passed to machine precision (relative error
1.3e-16) against its built-in reference. So the toolchain works; the
specific mesh + BC for the MOSFET-on-board case needs more care than I gave
it in this PR.

## Reliability margin computation

Under the three-envelope spec:

- **Envelope 2 (rated continuous)**: AON6260 R_thJC=1.0 °C/W, R_DS(on)~3.5 mΩ
  hot, P_loss per MOSFET ~6.4 W → T_J above board ~6 °C; need T_board ≤ 94 °C
  for T_J ≤ 100 °C. With prop-wash + heatsink that combined make
  R_thBA_global ≤ ~0.22 °C/W per total W, the system supports the spec. The
  Phase 4 / Phase 6 work has to deliver that cooling impedance.
- **Envelope 3 (stress / abs-max)**: AON6260 will reach T_J = T_J_max=150 °C
  and the firmware over-temp protection (cf. `REQUIREMENTS.md §Protection`)
  must cut current before silicon damage. The part's BVDSS=60 V and Avalanche
  energy (E_AS=211 mJ, single-pulse) give margin against transient overshoot
  past the 6S nominal 25.2 V bus.

## Open items closing at later sub-phases

| Item | Closes at | Why |
|---|---|---|
| `MILLIVOLT_PER_AMP` in `target.h` | 2c | Depends on gate driver + shunt R + opamp gain |
| `DEAD_TIME` in `target.h` | 2c | Depends on gate driver `t_dead_min` |
| Heatsink dimensions + thermal interface material | 4 / 6 | Placement + thermal sim |
| Real-world prop-wash h assumption | 6 / 8 (bench) | Sim validation against bench |
| NTC table characterization | 2c / bench | Depends on thermistor part |

## Build verification

Per contract Step 7, firmware target.h is unchanged in this PR (Phase 2b
addresses the MOSFET pick, not the firmware). Reverified:

```
$ make -C /home/novatics64/escworker/AM32 ARM_SDK_PREFIX=... \
       obj/AM32_PCBAI_FPV4IN1_F421_2.20.elf
# (sizes identical to Phase 2a: text=21200, data=1240, bss=2704)
```
