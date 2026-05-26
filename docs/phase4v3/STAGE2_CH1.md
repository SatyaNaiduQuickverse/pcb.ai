# Phase 4-v3 Stage 2 — CH1 (channel template)

**Branch**: `phase4v3-stage2-ch1`. Builds on Stage 0 (S6) + Stage 1 (anchors).
Brings the 99 CH1 components from the parking grid into the CH1 zone, layer-aware
(HS-FET F.Cu / LS-FET B.Cu beneath, per Sai option-a), and locks CH1 as the
template that CH2/CH3/CH4 mirror in Stages 3–5.

## What this PR does

- Brings CH1 to **99/99 placed** (anchor + role engine, 0 grid, 0 unplaced).
- Establishes the **west/east sub-zone split** (master 2026-05-26): west FET strip
  (x0–22) holds the 3 half-bridge phases as **R20-identical 12mm-pitch geometric
  copies**; east control strip (x22–35) holds MCU(J18) + DRV(J19) + INA + the
  +3V3 decoupling. CH1 is the locked template; CH2=mirror_X, CH3/CH4=mirror_Y/X.
- Adds the role-based placement engine + per-phase transform (below) to
  `place_subsystem.py` + `derive_ch1_roles.py`; CH1 roles in `routing_topology.yaml`.
- No netlist / schematic / target.h change (md5 `7a4549d27e0e83d3d6f1ffaf67527d24`
  unchanged).

## Per-phase R20 transform (the channel-template core)

The 3 phases must be **identical geometric copies** (Sai symmetry-preserves-work /
R20) so the channel composes for sims + mirrors cleanly. Implementation
(`replicate_phases` + `bring_selected`):
- Place ONE reference phase's west switching cell (HS+LS FET, shunt, gate-R,
  clamp, VMOTOR bypass) via the role engine in the replication-safe sub-zone, then
  snap phases B/C onto it translated by the 12mm motor-pad pitch — *not* an
  independent ring-search per phase (which gave a 21.6mm non-uniform row pitch).
- **HS-FET left-offset** (≥6.5mm −X of its motor pad): the B.Cu LS FET stacked
  beneath must clear the motor pad's both-layer thru-via field, and a −X offset
  keeps the cluster at pad-Y so the replicated phase-C copy stays clear of the
  zone top edge.
- **East-control-first ordering**: the east strip (MCU/DRV/INA) is placed before
  the reference phase, so the FET cluster — and its replicated copies — avoid the
  driver/MCU instead of landing on them.
- Result: HS FETs at exact 12mm Y-pitch (56/68/80), G5 SYMMETRY + QUADRANT pass.

## Root-cause log (per Sai R: Symptom / Fix / Root cause / Prevention)

### 1. G4 — U3/U4 reported undecoupled
- **Symptom**: G4 flagged U3.8 / U4.5 (+3V3) with no cap ≤3mm.
- **Fix**: `derive_ch1_roles.py` assigns each bypass cap to the IC it was
  *authored* for, using SKiDL creation order (a bypass cap is instantiated right
  after its IC). C79→U3, C80→U4, C51/C52→J18. G4 passes with **no schematic add**.
- **Root cause**: the decoupling-by-rail pass round-robin'd caps across a shared
  rail's VDD pins by net order, reassigning C79/C80 (the real U3/U4 bypass caps)
  to other pins.
- **Prevention**: intent (SKiDL order) drives decoupling ownership, never net order.
- **Latent (logged OQ-009, not this PR)**: the 3 INAs (J20-22) have no V+ bypass
  cap in the schematic; invisible to G4 (INAs use Connector_Generic footprints
  with unnamed pins). For a future schem rev.

### 2. G5 — 18 pad-overlaps under the MCU
- **Symptom**: 18 different-net pad overlaps, all J18.33 (MCU exposed pad) vs
  B.Cu parts.
- **Fix**: `_layers(fp)` — a footprint blocks whichever copper sides its *pads*
  occupy; `fits()` rejects accordingly. Pad-overlaps 18 → 0.
- **Root cause**: the placer modeled the MCU as F.Cu-only, but its exposed-pad
  thermal field (F land + B land + 9 thru vias) occupies B.Cu too, so B.Cu clamps
  were placed under it.
- **Prevention**: layer presence (pad layer set), not mounted side, drives collision.

### 3. G5 — parts drifted into the motor-pad keep-out
- **Symptom**: non-motor parts inside the motor-TP 2mm keep-out.
- **Fix**: motor-keepout enforcement in `fits()` (`_MOTOR_ADJ_NET_RE`); non-motor-
  adjacent parts must clear motor TP pads + 2mm. Regex is the netlist-verified
  single source shared with the G5 audit. 5 drifted parts (C54/C55/C58/R44/D37)
  moved out.
- **Root cause**: the placer had no motor keep-out, so aux caps filled gaps next
  to high-current pads.
- **Prevention**: placer ↔ audit share one motor-exempt regex.

### 4. S6 save regression (caught during CH1 work)
- **Symptom**: "brought 11" but 0 S6 on-board / G2 NOT-BROUGHT for all S6.
- **Fix**: decoupling caps ring from the VDD pin with a body-diag fallback radius
  (nearest-first → ≤3mm when room exists, but an over-subscribed pin still seats);
  surplus rail caps → cluster-aux; pure-power caps auto-parent to a roled FET on
  their rail, never the MCU.
- **Root cause**: the bring step does not save on any "no slot", so one
  unplaceable cap silently dropped the whole subsystem's placement.
- **Prevention**: a single tight constraint must not be able to drop an entire
  subsystem; nearest-first + generous fallback keeps both G4 optimality and
  convergence.

## Gate status (master_pre_merge.sh --staged S6,CH1)

_Filled at push time once the 3 master-side items land (G2 S6/J14 zone decision,
G5 VMOTOR regex line 452, G_PP6 same-component skip). CH1 placement itself: G1,
G3, G4, G5(overlaps), G6, G8, G16, G17, all FoS/PP/M/R/sim gates green; G11 render
set complete._

## Dependency note

Requires merged master #122 (mechanical revamp + G_PP6/G16 refines) + #123
(motor-exempt regex). The CH1 template is locked here; CH2=mirror_X(50),
CH3=mirror_Y(50), CH4=mirror_X(50) follow in Stages 3–5.
