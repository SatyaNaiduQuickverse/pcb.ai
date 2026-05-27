# MASTER_PARAMETRIC_DESYNC

**Lock date:** 2026-05-27
**Trigger:** PR #196 SHUNT_ANCHORS wrong-base catch (worker R22 verification)
**Memory:** `[[reference-parametric-placement-desync-trap]]`

---

## The Trap

`hardware/kicad/scripts/parametric_placement.py` is documented as the
"eagle's-eye SSoT for ALL placement coords." This is **half-true**:

| Aspect              | parametric_placement.py is SSoT?                |
|---------------------|--------------------------------------------------|
| Algorithm logic     | YES — mirror_x, mirror_y, cluster transforms     |
| Sub-zone definitions| YES — MOTOR/LOGIC splits, channel bounds         |
| Parameter relations | YES — pitch derivations, offset formulas         |
| **Numerical anchors** | **NO — STALE once placement is baked**        |

Once a subsystem PR merges its placement to `pcbai_fpv4in1.kicad_pcb`, the
**live `.kicad_pcb` becomes the coord-truth SSoT**, not the module.

Reason: incremental placement PRs (R1-transplant, manual nudges, per-Sai
visual-decision shifts, routing-driven micro-relief) all modify the live
board without back-propagating to the parametric module. The module would
need to re-derive from board-after-every-PR to stay in sync — which has
not been done, and is not on the critical path.

## Concrete Desync Example (PR #197 Trigger)

```
parametric_placement.ch_fet_anchors('CH1'):
  Q5  = (8.4, 53.0) approx       Q6  = (30.0, 54.0)
  Q7  = (8.4, 65.0) approx       Q8  = (30.0, 66.0)
  Q9  = (8.4, 77.0) approx       Q10 = (30.0, 78.0)

Live pcbai_fpv4in1.kicad_pcb (R1-transplant, validated):
  Q5  = (8.4, 53.0)  F.Cu rot=0   Q6  = (8.4, 58.4)  B.Cu rot=180
  Q7  = (8.4, 66.0)  F.Cu rot=0   Q8  = (8.4, 71.4)  B.Cu rot=180
  Q9  = (8.4, 79.0)  F.Cu rot=0   Q10 = (8.4, 84.4)  B.Cu rot=180
```

Row pitch differs (12mm vs 13mm), LS-FET column differs (30mm vs 8.4mm —
LS is cross-layer overlap of HS, not side-by-side), and LS rotation
differs (270° vs 180°).

A sub-agent computing SHUNT anchors **from the parametric module** placed
R57/58/59 at `(30.000, 56.962|68.962|80.962)` rotation 270° B.Cu — the
shunt body would have landed in the **east passive zone**, completely
disconnected from the LS-FET source pads it must overlap. Worker R22
caught the wrong base before any board damage.

## 3-Way Verification Pattern (Mandatory for Coord Work)

Before any PR that anchors components or computes geometric overlaps:

```
1. EXTRACT  — read coords from the live .kicad_pcb via pcbnew:
              fp = board.FindFootprintByReference(ref)
              pos = (ToMM(fp.GetPosition().x), ToMM(fp.GetPosition().y))
              rot = fp.GetOrientationDegrees()
              layer = board.GetLayerName(fp.GetLayer())

2. COMPUTE  — derive the new anchor purely from extracted coords + physics
              spec (e.g., +2.962mm Y-offset for shunt pad-1 alignment).
              DO NOT use parametric_placement.ch_*_anchors() numerical
              return values as input.

3. VERIFY   — after placement script runs, re-extract the new anchor from
              the live board and assert it matches the computed value
              within tolerance (≤0.05mm).
```

If the parametric module's algorithm is needed (mirror, transform,
sub-zone selection), use the **logic** but feed it **extracted** coords
as input, not the module's own numerical state.

## Codified Rules

- **R-DESYNC-1:** Any PR adding/updating anchor coords MUST cite the
  live-extraction script used to source the base coords. PR body MUST
  contain the exact `git show <branch>:<path>` or `LoadBoard(...)` call.
- **R-DESYNC-2:** Any PR consuming parametric_placement.py numerical
  output for absolute coordinate work (vs. for algorithmic transforms)
  is auto-REJECTED unless accompanied by a freshly-rebuilt parametric
  module re-derived from the live board.
- **R-DESYNC-3:** When parametric_placement.py is updated to a new
  validated base (future possibility), the desync warning header in
  the module is REMOVED and this doc is amended.

## Audit Gate Hook (Future Work)

`audit_parametric_compliance.py` (G_PP21) currently verifies that
subsystem placement scripts CONSUME the parametric engine. A future
extension G_PP21b should verify that consumed coords match the live
board within 0.5mm for already-merged subsystems — catching desync
introduction at PR-time rather than at sub-agent-mistake-time.

## References

- `[[reference-parametric-placement-desync-trap]]` (memory)
- `[[feedback-codify-not-patch]]` (Sai 2026-05-24)
- `[[feedback-sim-artifact-must-be-canonical]]` (Sai 2026-05-26)
- PR #196 (initial SHUNT_ANCHORS draft — wrong-base)
- PR #197 (SHUNT_ANCHORS re-sync + this doc)
- `hardware/kicad/scripts/parametric_placement.py` (DESYNC warning header)
- `hardware/kicad/scripts/place_subsystem_ch1_v3.py` SHUNT_ANCHORS dict
