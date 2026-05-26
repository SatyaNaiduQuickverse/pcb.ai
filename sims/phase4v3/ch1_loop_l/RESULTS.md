# CH1 HS-LS Commutation Loop Inductance — Phase 4-v3 (placement stage)

**Symptom / question:** Does the bilateral HS-on-F.Cu / LS-on-B.Cu topology
(`docs/BILATERAL_PLACEMENT.md`) actually deliver the ≤2 nH HS-LS commutation loop
it is designed for, on the as-placed CH1 board, for all 3 phases?

**Stage:** PLACEMENT-ONLY. The board has **0 routed tracks and 0 vias** (verified
below). Per dispatch, this is the *placement-stage loop estimate*, computed from
real FET + pad XY + board thickness + the *planned* SW-node via cluster. Final value
is confirmed post-route in STEP 6.

---

## 4-point evidence

**(d) Literal command**
```
cd /home/novatics64/escworker/pcb.ai/sims/phase4v3/ch1_loop_l
python3 loop_extract.py
```

**(a) Output artifact:** `loop_l_table.csv` (committed alongside this doc).

**(b) Artifact mtime > input/script mtime:**
```
loop_extract.py   mtime 2026-05-26 10:36:26
loop_l_table.csv  mtime 2026-05-26 10:36:32   (after the script -> produced by this run)
```

**(c) Reported numbers come from extract-script run against THAT artifact** — the
table below is `loop_l_table.csv` verbatim:

| phase | HS | LS | loop_area_mm² | n_sw_vias | L_loop_nH | margin_to_2nH |
|---|---|---|---|---|---|---|
| A | Q5 | Q6  | 26.933 | 16 | **13.5578** | −11.5578 |
| B | Q7 | Q8  | 26.933 | 16 | **13.5578** | −11.5578 |
| C | Q9 | Q10 | 26.932 | 16 | **13.5578** | −11.5578 |

---

## Geometry pulled from the board (`/tmp/ch1_152.kicad_pcb`)

Board (from `general/thickness`): **8-layer, 1.600 mm** total. Stackup order
(`docs/BOARD_INVARIANTS.md`): F.Cu / In1=GND / In2 / In3=+VMOTOR / In4 / In5=GND /
In6 / B.Cu. **The dielectric thicknesses between layers are NOT defined** — there is
no `stackup` block in the board and no spec in the repo; they are set at fab.

FET package = `W-PDFN-8-1EP_6x5mm` (PDFN, 3×3 mm exposed pad). Per-phase the HS-FET
sits on F.Cu, the LS-FET on B.Cu. Pad-net mapping (Phase A, representative — B/C are
pure 13 mm-pitch translations of A, Rule 19):

| FET | layer | center XY (mm) | SW-node pads (`MOTOR_A_CH1`) | source pads |
|---|---|---|---|---|
| Q5 (HS) | F.Cu | (8.400, 53.000) | EP pad9 (8.40,53.00) + pads1-3 at x=5.55, y=51.1–53.6 | VMOTOR_CH pads5-8 at x=11.25 |
| Q6 (LS) | B.Cu | (8.400, 58.400) | pads5-8 at x=5.55, y=56.5–60.3 | SHUNT_A_TOP_CH1 pads1-3 at x=11.25 |

| phase | HS@F.Cu | LS@B.Cu | HS pkg-center Y | LS pkg-center Y | ΔY |
|---|---|---|---|---|---|
| A | Q5 (8.4,53.0) | Q6 (8.4,58.4) | 53.0 | 58.4 | 5.40 |
| B | Q7 (8.4,66.0) | Q8 (8.4,71.4) | 66.0 | 71.4 | 5.40 |
| C | Q9 (8.4,79.0) | Q10 (8.4,84.4) | 79.0 | 84.4 | 5.40 |

VMOTOR bypass caps: **C66** (29.98/29.02, B.Cu), **C67** (32.98/32.02, B.Cu),
net `VMOTOR_CH` / `GND`. Motor pads (SW test points): TP19 (15,53), TP20 (15,66),
TP21 (15,79), all F.Cu.

**Loop dimensions extracted per phase (identical for A/B/C):**
- SW lateral run `l` = HS-SW-pad centroid (6.26, y) → LS-SW-pad centroid (5.55, y+5.88)
  = **5.919 mm**.
- SW→source span `w` (drain-side x=5.55 → VMOTOR/shunt-side x=11.25) = **4.987 mm**.
- XY-projected enclosed loop area = **26.93 mm²** (well within the G3 ≤50 mm² gate,
  but loop *area* ≠ loop *inductance* once the return plane is accounted for).
- Planned SW-node via cluster: **16 vias** fitting the SW-pad cluster at 0.6 mm pitch
  (0.3 mm drill), clamped to ½ of the 50-via/pair budget (BILATERAL line 68).

### KEY GEOMETRIC FINDING (disclosed per Rule 21)
The HS and LS SW-pad clusters are **NOT XY-coincident** — they have a **2.86 mm Y-gap**
(HS-SW bottom edge y=53.63 vs LS-SW top edge y=56.49) and the package centers are
5.40 mm apart in Y. So the "directly beneath" stack is *offset*, not co-axial: the SW
current runs ~5.9 mm laterally along the SW node before/after the F.Cu→B.Cu via
transition. This lateral excursion — not the 1.6 mm through-board hop — dominates the
loop, and is why the free-space loop bound is large.

---

## Formulas (cited)

**(1) Single SW-via partial self-inductance** — Paul, *Inductance: Loop and Partial
Inductance* (Wiley 2010), Eq. 3.20 (same closed form TI SLUA672 uses for via L):
```
L_via = (μ₀/2π)·h·[ ln(2h/r) − 0.75 ]
```
with h = 1.6 mm (board thickness = via barrel), r = 0.15 mm (0.3 mm drill).
→ **L_via_single = 0.739 nH** (matches the dispatch's ~1 nH sanity check for
0.3 mm/1.6 mm). N parallel vias: `L_via_cluster = L_via_single / N` (no mutual-M
credit → conservative). With N=16 → **L_via_cluster = 0.046 nH**.

**(2) Free-space single-turn rectangular loop** — Grover, *Inductance Calculations*;
Paul §5 (the FastHenry rectangular-loop reference form):
```
L_rect = (μ₀/π)·[ −2(w+l) + 2√(w²+l²) − l·ln((l+√(w²+l²))/w)
                  − w·ln((w+√(w²+l²))/l) + l·ln(2l/a) + w·ln(2w/a) ]
```
with l=5.919 mm, w=4.987 mm, a (round-wire-equivalent radius of the 3 oz SW pad
strip, GMD approx a≈0.2235·(width+t)) = 0.113 mm.
→ **L_rect = 13.51 nH** (free-space, NO return-plane credit).

**Placement-stage (geometry-only) total:**
```
L_loop = L_via_cluster + L_rect = 0.046 + 13.51 = 13.56 nH   (worst case)
```

**(2b) Plane-referenced model** (parallel-plate, Paul §4) — the multilayer reality:
```
L_plane = μ₀·d·l / w
```
d = F.Cu→In1.Cu dielectric. **Undefined in the board**, so reported across the
documented JLC 8L/1.6 mm prepreg range d = 0.076…0.21 mm:
→ L_via_cluster + L_plane = **0.16 … 0.36 nH**. This would PASS, but cannot be
confirmed at placement stage (no plane reference routed, dielectric not locked).

---

## Verdict vs 2 nH target

| Model | basis | L_loop/phase | vs 2 nH |
|---|---|---|---|
| **Placement-stage, geometry-only (worst case)** | placed XY + 1.6 mm thickness only — all from board | **13.56 nH** | **FAIL (−11.6 nH)** |
| Plane-referenced (post-stackup-lock) | needs In1.Cu GND return + locked dielectric d | 0.16–0.36 nH | PASS *(unconfirmed)* |

**PLACEMENT-STAGE VERDICT: FAIL** for all 3 phases — **13.56 nH** under the only model
that depends solely on the placed geometry + board thickness (both pulled from the
board). The ≤2 nH BILATERAL target is **achievable ONLY IF** two things that do NOT
yet exist are added:
1. the SW-node commutation **return is referenced through the adjacent In1.Cu GND
   plane** (so the loop closes vertically through ~0.1 mm dielectric, not a ~6 mm
   air loop), which requires the **stackup dielectric to be locked** (it is not — no
   stackup block in the board), and
2. the **SW-node via cluster + plane-referenced traces are actually routed** (0 vias
   / 0 tracks today).

Both are **post-route / STEP 6** items. At placement stage, the geometry alone does
**not** guarantee ≤2 nH; it guarantees ~13.6 nH if routed naively without the inner
GND return.

### Why the loop is large at placement (root cause)
The HS/LS packages are offset 5.40 mm in Y (2.86 mm SW-pad gap), so the SW node has a
~5.9 mm lateral run. The bilateral topology's ≤2 nH claim assumes the loop closes
*vertically* through a tightly-coupled inner GND plane — true only once routed against
In1.Cu. Pure free-space geometry of the as-placed parts is ~13.6 nH.

### Recommendation (for STEP 6 / master)
- Lock the 8L stackup dielectric (define the `stackup` block; F.Cu→In1 prepreg
  thickness drives the real loop value) — this is the load-bearing unknown.
- At route time, place the ~16-via SW cluster in the SW-pad overlap and route the
  GND/shunt return directly over In1.Cu so the loop closes vertically.
- Re-run this script in `--routed` mode (TODO: add track-traced polygon) against the
  routed board to confirm the post-route ≤2 nH.
- Consider tightening the HS/LS Y-offset if the via cluster cannot bridge the 2.86 mm
  SW-pad gap with adequate copper.

## Spec deviations
None. Geometry read as-placed; the HS/LS Y-offset finding is a property of the placed
board, disclosed above, not a deviation introduced here.
