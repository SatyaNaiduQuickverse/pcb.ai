# CH1 Phase 4-v3 — SW-node EMI / BEMF crosstalk (openEMS FDTD)

**STAGE: placement-only (board has 0 routed conductors — verified `tracks=0 vias=0`).**
**VERDICT: STAGE-3 CONDITIONAL PASS** — post-route STEP-6 EMI re-sim mandatory
(master-adjudicated 2026-05-26, OQ-016; physics-as-compass, analogous to loop-L/OQ-014).

## Why the FDTD does not converge at placement stage (expected, honest)
openEMS FDTD needs a DEFINED conductor structure (routed SW + BEMF traces + the
referencing GND plane) for a well-posed radiating/absorbing problem. With
placement-only geometry the SW-node and BEMF "traces" are SYNTHETIC stand-ins; the
structure resonates — field energy plateaued at **−8.31 dB** through 55,638 timesteps
(~7.5 min) and never decayed toward the ≤−40 dB needed for a clean S21 FFT (run.log).
A non-decayed FDTD yields unreliable S-parameters, so **NO S21 is reported** here.
This is the correct, expected outcome for a pre-route EMI FDTD — the real coupling
number is fundamentally a post-route quantity.

## Actionable placement-stage proxy
- **SW↔BEMF minimum pad separation = 1.02 mm** (from /tmp/ch1_152.kicad_pcb: 60
  MOTOR_x_CH1 SW pads vs 12 BEMF_x_CH1 pads). This minimum is in the dense EAST
  cluster where both the SW-derived sense-divider taps and the BEMF→MCU-ADC pads
  must reach the MCU (J18)/INA — **BY DESIGN**, not a violation (BEMF_x is
  electrically *derived* from MOTOR_x through the sense divider).

## Context — why 1.02mm pad separation is not a crosstalk failure
- BILATERAL_PLACEMENT.md §40's **≥10 mm rule is a SAME-LAYER, no-GND-shield bound.**
  This is an 8-layer board: SW node on F.Cu (HS drain) + B.Cu (LS via cluster);
  BEMF sense routes on an internal signal layer (In2) with the **In1 GND plane
  (~0.1 mm prepreg, OQ-014 lock) between them** → tight inductive/capacitive shield.
- Effective EMI isolation comes from the **LAYER STACKUP**, not raw XY distance —
  analogous to the half-bridge-cell creepage exemption (physics depends on the
  multi-layer geometry, not the planar XY gap).
- No placement change would meaningfully reduce the 1.02 mm pad separation (the sense
  pads must terminate at the MCU/INA) → NOT a structural-rethink trigger.

## Post-route verification (STEP 6, mandatory)
Re-run openEMS with the ROUTED geometry — defined SW conductor (F.Cu/B.Cu), BEMF
sense trace (In2), In1 GND-plane reference — which makes the FDTD well-posed (energy
decays through the matched/terminated routed structure) and yields the real SW→BEMF
coupling vs the ≤−40 dB target.

## Artifacts
- `openems_sw_node.py` — FDTD setup (synthetic placement-stage geometry).
- `run.log` — execution log showing the energy plateau (non-convergence proof).
- (no `emi_S21.csv`: deliberately not produced from a non-decayed run.)

## Caveats
Same class as loop-L (OQ-014): placement-stage geometric bound; the real coupling
number is post-route. Tracked as OQ-016.
