# CH1 30/30 (M2) — `add_sw_vias.py` design + validation

**Tool**: `hardware/kicad/scripts/add_sw_vias.py`
**Branch**: `ch1-3030-M2-sw-via-adder`
**Purpose**: dedicated SW-VIA FIELD ADDER tool to close `docs/CH1_DRONE_RELIABILITY_SWEEP_2026-05-28.md` Finding #1 (MOTOR_*_CH1 SW-node ampacity shortfall at 5/5/6 vs ≥150 needed).
**Mode of delivery**: master-domain ENGINE; worker invokes on its own branch
board for the actual route. This PR commits the tool + validation results;
the worker's canonical `.kicad_pcb` is NOT modified.

---

## Design

### Per-via class + ampacity model

| Geometry | Drill | Pad | Cont (A/via) | Burst (A/via) | Reference |
|---|---|---|---|---|---|
| through-via (1oz Cu plating) | 0.3 mm | 0.6 mm | 1.0 | 3.0 | IPC-2152 + Brooks "PCB Currents" + `audit_via_current_capacity.py` |

For MOTOR_*_CH1 at 100 A cont × 1.5 FoS → **150 A required** → **≥150 vias**
per phase (theoretical). PR #239 (reliability sweep) Finding #1 set the
loop-L planned-fit floor at **≥16/phase** and the ampacity-FoS target at
**≥50/phase** (also in `docs/BILATERAL_PLACEMENT.md` line 68).

### Algorithm (5 phases)

1. **Inventory** the input board:
   * existing vias + footprint drills + mounting holes (board-wide drill set);
   * per-net SW-node copper as a *union* of {filled-zone outlines on F.Cu, F.Cu pads on the net} ∪ {same on B.Cu};
   * per-layer foreign-net copper (tracks + pads as points-with-radius; filled zones as polygons).
2. **Candidate grid** at configurable pitch (default 0.5 mm; 0.1 mm for
   thorough sweep) across the bbox-union of F + B SW copper.
3. **Per-candidate filter**:
   * **dangle-F**: pad disk (radius PAD/2) must fit entirely inside ≥1 F.Cu MOTOR shape (any zone OR pad);
   * **dangle-B**: same on B.Cu;
   * **hole-to-hole** ≥ 0.20 mm to every existing drill (edge-to-edge: `distance(centers) − (drill_a/2 + drill_b/2)`);
   * **foreign-copper clearance** ≥ 0.20 mm to every foreign track + pad on every traversed layer (10L stackup: F, In1–In8, B). For foreign zones we accept "via inside foreign pour" because KiCad's pour re-fill auto-clears around the new via (zone-anti-pad semantics); we only reject when the via sits AT the zone EDGE such that the auto-clear would clip the zone outline.
4. **Greedy add** up to `target_count`, ordering accepted candidates by
   widest hole-to-hole margin first (safer-first), and enforcing
   inter-new-via spacing ≥ `drill + h2h` so newly added vias don't violate
   each other.
5. **Output** modified `.kicad_pcb` (with new `PCB_VIA` objects via
   `pcbnew.Board.Add`), plus JSON report with:
   * funnel counts (total / pass_dangle / pass_h2h / pass_foreign / chosen),
   * per-class rejection counts,
   * per-added-via inset margins + hole-to-hole margin,
   * feasibility verdict (`MET` / `LOOP_L_OK_AMPACITY_PARTIAL` / `INFEASIBLE_AT_TARGET`),
   * **`unlock_actions`** — actionable shopping list when target infeasible (worker reads this to know which copper to expand).

### R19 symmetry

Per `[[reference-r19-loop-vs-trace-symmetry]]` 2026-05-26 OQ-019:
R19/OQ-017 binding is COMMUTATION LOOP-L SYMMETRY, not identical trace
polylines. For SW-vias that means: every via added on phase A is mirrored
TO phase B + C at the IDENTICAL TRANSLATION-OFFSET from the per-phase
HS-FET-drain centroid (Q5.9 → Q7.9 → Q9.9 in CH1, spaced ~13 mm in y).
Implementation in `project_to_other_phases()` + `validate_projected()`:

* for each via chosen on phase A, project to B + C via the per-phase origin offset;
* re-validate each projection against the target-phase board state (drill walk + foreign copper + dangling) — drop the via on ALL three phases if it fails on ANY phase (per the rules: "if a mirror position is infeasible on one phase, drop that via on ALL three phases to preserve symmetry");
* commit the surviving positions on all 3 phases simultaneously.

Final R19-symmetric count is reported as `r19_symmetric_count` in the
JSON report. Δ per-phase = 0 by construction.

---

## Validation on worker's canonical `phase4v3-stage1-ch1-on-10L` board

READ-ONLY. Synthetic copies in `/tmp/`. No worker-branch mutation.

### Run 1 — MOTOR_A_CH1, target 50, pitch 0.1mm, single-phase

```
SW copper F.Cu shapes: 17 | B.Cu shapes: 14
candidate grid: 23744
candidate funnel: pass_dangle=61 | pass_h2h=0 | pass_foreign=0 = 0 accepted
rejections: dangle-F=21896, dangle-B=1787, hole2hole=61
chosen: 0 / target 50 → INFEASIBLE_AT_TARGET
```

### Run 2 — R19-symmetric (A, B, C all 50-target)

```
A: pass_dangle=61, pass_h2h=0 — 0 vias added
B: projected 0/0 (nothing to project)
C: projected 0/0 (nothing to project)
R19-symmetric final: 0/0/0
```

### Run 3 — MOTOR_B_CH1, single, 50-target

```
candidate grid: 26040
funnel: pass_dangle=0 (B.Cu zone is just 1.1mm×0.81mm — geometrically smaller than A)
chosen: 0
```

### Run 4 — MOTOR_C_CH1, single, 50-target

```
candidate grid: 48923
funnel: pass_dangle=0
chosen: 0
```

### Verdict — geometric infeasibility on canonical board

The canonical 5/5/6 existing SW vias at ~0.8 mm pitch SATURATE the
F∩B-MOTOR-copper region on each phase under the 0.20 mm hole-to-hole rule.
**No additional through-vias fit** without one of:

1. **EXPAND B.Cu MOTOR_X copper** — worker adds a B.Cu pour on each phase
   matching the F.Cu motor-pad envelope (e.g. TP19 4 × 4 mm area on
   MOTOR_A); the tool's diagnostic correctly identifies this as the
   dominant blocker (`dangle-B` rejection class) — see synthetic test below.
2. **RELOCATE existing vias** — current cluster at (6.6–7.4, 54.4–55.0)
   for MOTOR_A is at the 0.20 mm-hole-to-hole packing limit; spreading
   them to a larger envelope (or using HDI microvia 0.10/0.25 in a
   whitelist-class) re-opens positions.
3. **EXPAND F.Cu MOTOR copper** — relocate VMOTOR_CH passives out of
   the F.Cu MOTOR pour to remove cutouts.

The tool reports these three actions in `unlock_actions[]` for any
infeasible run.

### Sanity test on a synthetic B.Cu expansion

Added a 4 × 4 mm B.Cu MOTOR_A_CH1 pour over the TP19 motor-pad area
synthetically (PyCBnew `ZONE` + `ZONE_FILLER.Fill`), to confirm the
tool's diagnosis is mechanistic-correct:

```
SW copper F.Cu shapes: 17 | B.Cu shapes: 15  (+1 added pour)
candidate funnel: pass_dangle=95 | pass_h2h=34 | pass_foreign=31 = 31 accepted
chosen: 3 / target 50 (greedy with 0.5mm new-via pitch — relaxable)
post-add count: MOTOR_A_CH1 = 8 vias (vs 5 canonical)
```

When the B.Cu copper is expanded the way `unlock_actions` recommends, the
tool immediately starts adding vias. The 31 → 3 reduction is the greedy
spread pitch (default new_via_pitch_min = `drill + h2h` = 0.50 mm); tightening
new-via pitch via `--pitch` finds more.

### Loop-L extract on canonical-after-tool-no-op output

```
loop_extract.py /tmp/ch1_sw_via_A_v2.kicad_pcb
  Phase A: 5 vias → L_loop=0.2970 nH PASS
  Phase B: 5 vias → L_loop=0.2970 nH PASS
  Phase C: 6 vias → L_loop=0.2724 nH PASS
```

Identical to canonical (0 vias added → loop-L unchanged). No regression.

### audit_routing.py + audit_via_current_capacity.py on tool output

```
audit_via_current_capacity.py: FAIL × 6 (5/5/6 vias vs 150A required)
  — unchanged from canonical, the tool added 0 vias because of geometry.
audit_routing.py --subsystem CH1: 19 pre-existing failures (UNROUTED + TRACK-WIDTH)
  — identical to canonical baseline, tool causes ZERO regression.
```

No new audit failures introduced.

---

## Acceptance criteria status

| Criterion | Status on canonical | Notes |
|---|---|---|
| Per-phase ≥ 16 (loop-L floor) | **INFEASIBLE** (0 addable) | needs copper expansion per `unlock_actions` |
| Per-phase ≥ 50 (ampacity FoS) | **INFEASIBLE** | same |
| Phase counts symmetric Δ ≤ 1 | **MET** (5,5,6 — Δ=1) | R19 mode preserves symmetry strictly going forward |
| Hole-to-hole ≥ 0.20 mm to every drill | **ENFORCED** by tool filter | (none added so vacuous on this run) |
| Zero dangling vias | **ENFORCED** by tool filter | dangle-F + dangle-B gates |
| audit_via_current_capacity.py PASS | FAIL (5/5/6 < 150) | tool does not fabricate vias to make this pass — the geometry is the binding constraint |
| audit_routing.py PASS | unchanged (19 pre-existing FAILs) | no new failures |
| Loop-L per-phase symmetry | unchanged (0.297/0.297/0.272 nH, 8.5% Δ) | will close when worker expands copper + tool runs to add equal vias |
| Adversarial: report MAX-FEASIBLE + reason | **MET** | `funnel` + `rejected_summary` + `unlock_actions` |

---

## Honest disclosure

* The canonical board does **not** geometrically support ≥16 (let alone ≥50) SW vias per phase at 0.20 mm hole-to-hole with through-via geometry. The tool correctly reports zero added on the canonical board and emits the actionable `unlock_actions` shopping list (expand B.Cu MOTOR pour, relocate existing vias, expand F.Cu MOTOR pour).
* The synthetic B.Cu expansion test confirms the tool MECHANISTICALLY WORKS when geometry is sufficient: 0 → 31 accepted, 3 → 8 added (greedy 0.5 mm new-via pitch; raise to 0.10 mm to fit more).
* The 0-added result on canonical is a TRUE FINDING, not a tool bug. The worker's 30/30 final-route PR is the trigger to act on `unlock_actions`.
* This PR commits the tool only. The worker's `pcbai_fpv4in1.kicad_pcb` is read-only in this PR.

---

## Worker-action items (for 30/30 final-route PR)

1. Run `add_sw_vias.py --board <worker_board> --net MOTOR_A_CH1 --target-count 50 --symmetric-phases --output <out>` on the worker's branch board after expanding B.Cu MOTOR copper per the `unlock_actions` shopping list.
2. Re-fill all zones via `kicad-cli pcb refill` (or pcbnew `ZONE_FILLER.Fill`) on the output so anti-pads around the new vias are computed.
3. Re-run `audit_via_current_capacity.py` and `audit_routing.py` post-add to confirm PASS.
4. Re-extract `loop_extract.py` and confirm per-phase Δ ≤ 5 % (per OQ-019 acceptance criterion in PR #239).
