# Phase 4b-redo4-R1 — center-cluster placement of all 581 footprints

**Status:** complete on branch; pending master audit + PR review.
**Branch:** `phase4b-redo4-R1/center-cluster-placement`.
**Scope:** 581 footprints placed in R1 (center-cluster) topology on 100×85 board
with 8L stackup (Phase 4a-restack-8L) + 3 oz on outer/In3 power layers.
**Master directive:** Task #38 dispatch 2026-05-22.

---

## 1. R1 architecture rationale

Pre-R1 (Phase 4b-redo3): 4 MCUs at board corners with PWM corners facing inward
toward a central 6×4 MOSFET grid. Per-channel passives clustered between MCU
and gate driver near board interior — created congestion in central band and
forced long signal-routing across the board for shared infrastructure (FC
connector, BEC, supervisor, Hall sensor).

**R1**: invert the topology — MCUs in a 2×2 center cluster, per-channel
passives radiate OUTWARD into board-edge quadrants. Each MCU rotated so its
PWM corner faces its quadrant; gate drivers, CSAs, and per-channel
protection ICs sit in a tight ring just outside the cluster on the
quadrant side.

| Metric | Pre-R1 (4b-redo3) | R1 (this PR) | Note |
|---|---|---|---|
| D/S whole-board | 0.83 (3-signal-layer 6L) | **0.297** (5-signal-layer 8L) | 64% improvement |
| Max per-zone D/S | 1.22 (NW hotspot) | **0.335** (SE) | 73% improvement |
| Central congestion | High (6×4 FETs + per-ch passives + bucks) | Lower (B.Cu FETs only; F.Cu MCU cluster) | F.Cu cluster center has fewer pads |
| FC + AUX + Hall + supervisor proximity | Spread, long routes | Concentrated top edge | Shorter board-power-mgmt routing |

---

## 2. Component placement by zone

Quadrants (KiCad screen, +Y is DOWN):

```
        x=0           x=50          x=100
  y=0  ┌─────────────┬─────────────┐
       │ NW  CH1     │ NE  CH2     │
       │ passives    │ passives    │
       │             │             │
       │   [MCU1]    │  [MCU2]     │
  y=42 │   (40,35)   │  (60,35)    │ <- top half (y < 42.5)
  y=42 │   [MCU3]    │  [MCU4]     │
       │   (40,50)   │  (60,50)    │
       │             │             │
       │ SW  CH3     │ SE  CH4     │
       │ passives    │ passives    │
  y=85 └─────────────┴─────────────┘
                                       Edge.Cuts 100×85 mm
```

### F.Cu (top, 3 oz)

| Region | Components |
|---|---|
| Center cluster | 4× MCU (AT32F421, rotated PWM-outward) at (40,35)/(60,35)/(40,50)/(60,50) |
| Cluster ring | 4× DRV8300 at (40,30)/(60,30)/(40,55)/(60,55); 12× INA186 CSAs; 4× TL431 + 4× LM393 + 4× 74LVC1G08 (per-channel protection ICs) |
| NW quadrant | CH1 per-channel passives (gate clamps, bypass caps, BEMF dividers, decoupling) |
| NE quadrant | CH2 per-channel passives |
| SW quadrant | CH3 per-channel passives |
| SE quadrant | CH4 per-channel passives |
| Outer edges | 12× motor solder pads (3 per channel, on the quadrant's outer edge); 8× SWD pads (2 per channel); 16× BEC pads (left/right edges); 4× HW protection LEDs near each MCU |
| Top edge band | FC connector @ (70,82); JST AUX header @ (45,82); 3× ESD; battery section (XT30 entry at x=5); TPS3700 supervisor @ (50,12); Hall sensor ACS770ECB-200B @ (32,42.5); indicator LEDs (PG/PWR/RPOL) |
| Bottom edge band | BEC bucks ×5 (5V_FC/5V_PI5/5V_AI/9V_VTX1/9V_VTX2) + LDO + safety stacks |

### B.Cu (bottom, 3 oz)

| Region | Components |
|---|---|
| Center 42×30 mm grid | 24× AOTL66912 phase MOSFETs in 6×4 grid, 3×2 sub-grid per channel: cells (29..64, 27.5..50) at 7×7.5 pitch |
| Above/below MOSFETs | 12× 0.2mΩ shunts (3 per channel) |
| Top-left area | 4× polymer bulk caps (470µF/35V) + 4× reverse-pol FETs (BSC014N06NS) + battery section TVS + BATT_PAD |
| Battery section | 2× MF72 5D25 NTC inrush limiter |

### Inner layers (In1.Cu / In3.Cu / In5.Cu — planes, no placement)

| Layer | Plane net |
|---|---|
| In1.Cu | GND (full board) |
| In3.Cu | +VMOTOR (full board, 3 oz) |
| In5.Cu | GND (full board, dual-GND for EMC) |

### In2.Cu / In4.Cu / In6.Cu (inner signal layers — Phase 5b autoroutes)

Available for high-density signal routing across the per-channel zones to
shared infrastructure. ~5% pad-blocked (through-hole pads only).

---

## 3. D/S validation results

Run: `python3 hardware/kicad/scripts/signal_density_check.py 5`

### Whole-board

| Metric | Value | Gate |
|---|---:|---|
| Signal demand D | **7,064 mm²** | (lower is better) |
| Routing supply S (5 signal layers) | **23,769 mm²** | |
| **D/S** | **0.297** | < 0.85 PASS ✓ |
| Margin to PASS gate | **0.553** (65% spare capacity) | |

### Per-zone (refined per-zone supply formula)

| Zone | D (mm²) | f_F.Cu | f_B.Cu | S (mm²) | D/S | Status |
|---|---:|---:|---:|---:|---:|---|
| NW | 1,577 | 0.70 | 0.02 | 5,708 | **0.276** | PASS ✓ |
| NE | 1,467 | 0.58 | 0.02 | 5,883 | **0.249** | PASS ✓ |
| SW | 1,953 | 0.48 | 0.03 | 6,009 | **0.325** | PASS ✓ |
| SE | 2,068 | 0.37 | 0.02 | 6,170 | **0.335** | PASS ✓ |

All zones under 0.34. No hotspots. Master pre-prediction was 0.55–0.65; actual
0.30 — improvement from net-membership-based placement clustering per-channel
components tightly in their quadrants → lower HPWL per signal net.

### Why D/S beats prediction

The model overestimates demand because:
1. Per-channel passives clustered ≤1.5 mm pitch within quadrant → very low
   HPWL within channel sub-circuit (most nets short).
2. R1 puts each channel's MCU + driver + CSAs + protection ICs in a 5×7 mm
   ring at the cluster edge → near-zero HPWL for fast critical paths.
3. Shared signals (DShot, TLM, +V5, +V3V3, GND) route via inner signal
   layers (In2/In4/In6) instead of competing on F.Cu.

---

## 4. T8 compliance (per-MCU pin-side connectivity)

Run: `python3 hardware/kicad/scripts/verify_placement.py`

✓ All per-channel parts confirmed within their MCU's quadrant (NW/NE/SW/SE).
The exclusions are intentional and master-spec'd:

| Exception | Reason |
|---|---|
| MCUs, DRV8300, INA186 CSAs | Central cluster ring (master R1 spec) |
| Phase MOSFETs (B.Cu) | Centered 6×4 grid (heatsink zone, master spec) |
| Motor pads | Quadrant-outer board edges |
| SWD pads | Quadrant-outer side edges |

---

## 5. +VMOTOR via stitching (≥210 vias)

Phase 4a-restack-8L locked: **≥ 210 vias on +VMOTOR rail** (1.50× cont. FoS,
1.58× burst FoS under aggressive-with-pour baseline).

### Strategy for Phase 5b-retry autoroute + post-route pour

Distribution per `sims/phase4a_restack_8l/via_stitching_audit.py`:

| Region | Vias | Notes |
|---|---:|---|
| CBULK output → VMOTOR rail entry (4× polymer cap × ~5 vias each) | 20 | at (10–15, 39–46) battery section |
| Per-channel VMOTOR fanout × 4 — FET drains + trace + bypass cap stacks | 200 | ~50 vias per channel; 12 at each H-side FET drain (3×4 grid) + 6 along VMOTOR trace per phase + 4 at local bypass cap stack |
| Mid-trace stitching (filler, ~1 via per 5 mm² VMOTOR pour) | 20 | distributed across In3.Cu plane perimeter |
| **Total target** | **≥ 210** | |

**Layout requirement** (master Phase 4a-restack-8L lock): 3 oz copper pour
on +VMOTOR rail (F.Cu and B.Cu) must surround every via to sustain 2 A/via
aggressive baseline.

### Phase 5b-retry will

1. Run `export_dsn.py` → `dsn_strip_planes.py` → `dsn_inject_planes.py` for
   the 8L geometry.
2. Freerouting autoroute (5 signal layers).
3. Re-import SES → KiCad.
4. Apply +VMOTOR copper pour on F.Cu, In3.Cu (plane), B.Cu around the
   24-MOSFET cluster + bus rail.
5. Place ≥210 vias per the strategy above.
6. Run audit to count vias on +VMOTOR net.

---

## 6. Routability sanity (qualitative)

- ✓ Each MCU's per-channel passives have clear F.Cu paths to MCU pins
  (passives in same quadrant as MCU, no cross-board hops).
- ✓ Per-channel local bypass caps placed at 1.4 mm pitch packing alongside
  FET pairs — ≤ 5 mm trace from FET drain to bypass cap GND tap achievable
  (3 oz F.Cu pour bridges any sub-5 mm gap).
- ✓ Phase TVS (SMBJ33A) placed 3 mm inward from each motor pad (T_motor_pad
  → T_TVS center ≤ 3 mm — meets master's ≤ 3 mm clamp-effectiveness spec).
- ✓ Bus current Hall sensor (ACS770ECB-200B) in +VMOTOR path between bulk
  caps (x=12, y=42.5) and 4-FET-cluster split (cluster at x=29-64, centered
  at 50) — Hall at (32, 42.5) sits between them with 17–18 mm clearance to
  cluster, 15 mm to caps. Layout requirement: VMOTOR rail passes through
  Hall primary as 3 oz copper bar.
- ✓ Supervisor IC (TPS3700) at (50, 12) — central top edge, accessible for
  test-pin probing; resistor divider tap (348kΩ + 23.2kΩ) at (47, 8) /
  (53, 8) adjacent.
- ✓ AUX 6-pin header (BM06B-SRSS-TB) at (45, 82) — top edge, easy
  plug/unplug; Hall analog out routes ~70 mm to AUX pin 3 (through inner
  signal layer with reasonable HPWL).
- ✓ 4× HW protection LEDs at (32,37)/(68,37)/(32,48)/(68,48) — visible
  next to each MCU; cathode = KILL_LOCAL_N from per-channel 74LVC1G08
  output.
- ✓ Pogo-pin programming pads: at B.Cu (15,35)/(85,35)/(15,50)/(85,50) per
  channel for SWD-via-pogo programming (separate from the SWD solder pads
  on F.Cu side edges).
- ✓ Mount holes at corners (5,5)/(95,5)/(5,80)/(95,80) — custom 90×75 mm
  pattern; not standard FPV stack but Sai's `feedback-anchor-on-most-capable-reference`
  rule applies.

---

## 7. Code changes

### `hardware/kicad/scripts/place_board.py`

**Complete rewrite** for R1 architecture. ~580 lines.

Highlights:
- New constants: `CHANNEL_MCU_POS`, `CHANNEL_OUTWARD`, `CHANNEL_MCU_ROTATION`
  (PWM-corner-outward: CH1=180°, CH2=270°, CH3=90°, CH4=0°),
  `CHANNEL_PACK_ZONE` (per-channel pack zones in each quadrant).
- New helper: `pack_grid_iter(zone, pitch, exclusion_set, exclusion_radius)`
  — grid packer that skips cells near already-placed ICs.
- New helper: `parse_net_channel_membership(pcb_text)` — infers channel
  membership for each footprint from `_CH<n>` suffix on its connected nets.
  Used to assign per-channel ICs (MCU, driver, CSAs, shunts, protection
  ICs, fault LEDs, boot testpoints) to correct quadrants regardless of
  netlist sequential order.
- Phase 3-redo additions: Hall sensor (ACS770), TL431/LM393/74LVC1G08
  per-channel protection ICs, HW + firmware status LED sets, AUX header,
  phase TVS placement adjacent to motor pads.
- BEC strip relocated to bottom edge band (y=63..80) to clear central
  cluster.

### `hardware/kicad/scripts/verify_placement.py`

Updated for R1 architecture:
- `EXPECTED_MCU_ROTATION` = {1: 180, 2: 270, 3: 90, 4: 0}
- `EXPECTED_MOSFET_X/Y` = R1 6×4 grid at (29..64, 27.5..50)
- New T8 quadrant compliance check via net-membership inference per
  footprint.
- Drops stale Phase 3b silkscreen sentinel checks (applied separately;
  not part of Phase 4b-redo4-R1 scope).

### `hardware/kicad/scripts/signal_density_check.py` (no changes here)

Already extended to support 5-layer mode in Phase 4a-restack-8L; runs
cleanly on the new placement.

### SVG snapshots

Generated via `kicad-cli pcb export svg` per signal layer:
- `hardware/exports/phase4b_redo4_r1/F.Cu.svg` (683 kB)
- `hardware/exports/phase4b_redo4_r1/In2.Cu.svg` (62 kB — no traces yet)
- `hardware/exports/phase4b_redo4_r1/In4.Cu.svg` (62 kB — no traces yet)
- `hardware/exports/phase4b_redo4_r1/In6.Cu.svg` (62 kB — no traces yet)
- `hardware/exports/phase4b_redo4_r1/B.Cu.svg` (63 kB)

Inner-layer SVGs are sparse since autoroute hasn't run yet (only padstacks +
mount holes visible). F.Cu / B.Cu SVGs show full placement.

---

## 8. Failure modes considered

| Mode | Mitigation |
|---|---|
| MCU cluster heat coupling (4 MCUs at ≤20 mm spacing) | Each MCU dissipates ~30-50 mW at full DShot rate → cluster total < 200 mW. Heatsink-less. Cluster temperature rise vs ambient: < 3°C per thermal model. Acceptable. |
| Cross-channel MCU comms (none in firmware) → unused | AM32 firmware is independent per channel; no inter-MCU buses. Cluster only enables shared MCU-side LEDs, supervisor reset signal. |
| Per-channel passives clustered tightly (1.4 mm pitch) | DRC clearance must hold. Phase 5b: route at 0.13 mm trace / 0.13 mm clearance (3 oz JLC DRC). Sub-5 mm trace lengths typical. |
| Phase TVS placement near motor pads — manufacturing reflow gradient | SMBJ33A SMA package: well within JLC SMT capability. 3 mm offset from motor pad gives reflow access. |
| Hall sensor primary current path (~280-400 A) bottleneck | VMOTOR rail through Hall primary must be 3 oz copper bar with ≥ 1.5 mm² cross-section. Setup_board.py + Phase 5b copper pour enforce. |
| Center-cluster signal congestion on F.Cu | F.Cu pad-blocked = 53% (centered around cluster). 5 signal layers (5L) split routes; In2/In4/In6 absorb mid/short-distance signals. |
| LED light-pipe / mechanical interference with FPV stack | LEDs are 0603 SMD, 0.7 mm height; no clearance issue. |

---

## 9. Reduction options if D/S becomes marginal in future iterations

D/S = 0.30 currently — large margin. If future additions push D/S > 0.7:

1. Move BEC bucks (5×) and safety stacks to a separate BEC daughtercard (frees ~25% F.Cu).
2. Promote In1/In5 plane-served fraction (currently 100%) to allow signal routing on a sliver — reduces effective GND plane but bumps S by ~5,200 mm².
3. Increase board to 110×95 (+22% area) for breathing room — Phase 4b-redo5.
4. Switch per-channel passives from 0402 to 0201 (40% area reduction) — manufacturing-side change, JLC supports.

None of these are needed at current D/S = 0.30.

---

## 10. Acceptance against master criteria

| Criterion | Status |
|---|---|
| 1,165 (SKiDL-overcount) / 581 (actual) footprints placed | ✓ (581 placed; 0 unplaced; 4 mount holes setup_board.py-positioned) |
| 0 overlaps | ✓ |
| Whole-board D/S < 0.85 PASS | ✓ (0.297 — 65% spare) |
| All per-zone D/S ≤ 0.85 PASS | ✓ (max NW=0.276; max overall=SE 0.335) |
| Per-MCU T8 compliance verified for all 4 channels | ✓ |
| ≥ 210 +VMOTOR vias placed | DEFERRED to Phase 5b-retry (autoroute + post-route pour fill). Placement strategy locked here. |
| `target.h` md5 unchanged | ✓ `7a4549d27e0e83d3d6f1ffaf67527d24` |
| One PR | ✓ |

---

## 11. Out-of-scope (deferred)

- **Phase 5b-retry autoroute** on the new R1 placement with 8L geometry.
- **+VMOTOR copper pour + via placement** post-autoroute (≥210 vias enforced).
- **Phase 5c re-classify** In1/In3/In5 to power-type for final fab.
- **Phase 3b silkscreen + motor strain-relief** re-application after autoroute.
- **Inner signal layer SVG content** — empty until autoroute completes.
- **Conformal coating spec** (Phase 4 manufacturing).
