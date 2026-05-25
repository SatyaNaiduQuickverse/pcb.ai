# Gate Inventory — comprehensive catalog of audit gates

Per Sai 2026-05-26: "review where have you forget to put gates and checks
across every part and process we cant keep doing this". This doc is the
META-SSoT for ALL gates the master enforces. Every gate gap is a future
Sai-eye-catch waiting to happen. Build the gate BEFORE the error.

| ✅ = built + validated | 🟡 = built, not wired | 🔴 = missing — must build |

## A. Placement gates

| Gate | Status | Script | What it catches |
|---|---|---|---|
| G1 anchor positions vs lockfile | ✅ | audit_anchor_positions | drift from immovable mech positions |
| G2 zone contract (park-then-bring) | ✅ | audit_zone_contract | ghost components from prior placement |
| G3 switching loop area | ✅ | audit_loop_area | Erickson ≤50mm² target violations |
| G4 decoupling R25 | ✅ | audit_decoupling | IC.VDD pin without cap ≤3mm same-layer |
| G5 layout compliance (11 sub-checks) | ✅ | audit_layout_compliance | off-board, pad-overlap, passive anchoring, mount-hole keepout, symmetry, silk-on-pad, quadrant balance, etc |
| G6 master invariants (5 sub-checks) | ✅ | master_audit_invariants | hash drift, zone, port, highway, symmetry-partner |
| G16 **connector symmetry** | 🟡 | audit_connector_symmetry | non-symmetric connector placement (Sai-eye-caught 2026-05-26 J12@25/J14@50) |
| G17 **edge keepout** | 🟡 | audit_edge_keepout | components closer than 3-5mm to board edge (Sai-#5 J14@y90 catch) |
| G_PP1 polarity marker visible | 🔴 | TODO | LED/diode/electrolytic anode-mark visible top-side |
| G_PP2 pick-place reachability | 🔴 | TODO | tall component blocks adjacent placement head access |
| G_PP3 silk size readability | 🔴 | TODO | refdes text <1mm height fails JLC SMT pick |
| G_PP4 component rotation aligned | 🔴 | TODO | same-class components rotation-aligned for DFM uniformity |
| G_PP5 hand-solder TP access | 🔴 | TODO | TPs blocked by adjacent ≥3mm tall component |
| G_PP6 HV creepage clearance | 🔴 | TODO | ≥27 V_motor needs ≥0.6mm trace+pad creepage (IPC-2221 B-grade) |
| G_PP7 mating connector cable swing | 🔴 | TODO | JST/XT30 has cable-swing radius — adjacent components must clear |

## B. Routing gates (mostly post-Stage-2)

| Gate | Status | Script | What it catches |
|---|---|---|---|
| G7 audit_routing (6 sub-checks) | ✅ | audit_routing | basic routing DRC + plane islands + power-stitching |
| G12 diff pair length match | ✅ | audit_diff_pair_match | pair spread > tolerance |
| G13 Kelvin shunt routing | ✅ | audit_kelvin_shunt_routing | tap-not-at-centroid + length-match + separation |
| G14 via stitching density | ✅ | audit_via_stitching_density | PDN ≥4 vias/cm² for ampacity |
| G15 length match (highway) | ✅ | audit_length_match | per-group track length spread |
| G_R1 differential Z0 impedance | 🔴 | TODO | DP routing on inner layer with correct trace width for 100Ω |
| G_R2 stub length at high freq | 🔴 | TODO | unterminated stubs >1/10 λ on clocks |
| G_R3 return-path microstrip integrity | 🔴 | TODO | trace crossing reference-plane gap |
| G_R4 crosstalk aggressor-victim spacing | 🔴 | TODO | high-dV/dt traces too close to analog |
| G_R5 via current capacity | 🔴 | TODO | drill+annular vs net current per IPC-2152 |
| G_R6 antenna structure prevention | 🔴 | TODO | long unterminated stubs that radiate |

## C. Factor-of-Safety (FoS) gates — Sai 2026-05-26 mandate

| Gate | Status | Script | FoS rule |
|---|---|---|---|
| G_FoS1 thermal T_J | 🔴 | TODO audit_fos_thermal | T_J ≤ T_J_max × (1 − 0.25) = 75°C for Si MOSFETs (industry std 25% FoS) |
| G_FoS2 trace ampacity | 🔴 | TODO audit_fos_current | trace-width-rated ampacity ≥ I_load × 1.5 (50% FoS continuous, 100% transient) |
| G_FoS3 cap voltage derating | 🔴 | TODO audit_fos_voltage | electrolytic cap V_rated ≥ V_max × 1.4 (industry 40% derating) ceramic ≥ 1.5× for X7R |
| G_FoS4 cap ripple current | 🔴 | TODO audit_fos_ripple | cap I_ripple_rated ≥ I_RMS × 1.5 (links OQ-006 R17) |
| G_FoS5 connector pin current | 🔴 | TODO audit_fos_pin_current | per-pin rating × pin count ≥ I_load × 1.5 |
| G_FoS6 via current density | 🔴 | TODO audit_fos_via_current | sum(via_amp_capacity) ≥ I_load × 1.5 |

## D. Lockfile + metadata gates

| Gate | Status | Script | What it catches |
|---|---|---|---|
| G_L1 lockfile completeness | 🔴 | TODO audit_lockfile_completeness | every netlist J/H/FID/TP has lockfile entry (catches drop-outs) |
| G_L2 lockfile-fp library match | 🔴 | TODO audit_fp_library_match | every lockfile footprint exists in fp lib (catches typos before kinet2pcb) |
| G_L3 lockfile hash matches doc | ✅ | (compute_board_invariant_hash) | drift detection |
| G_L4 [invariant-change] PR tag | 🔴 | TODO github-check | lockfile diff requires PR-title tag |

## E. Manufacturing (JLC DFM) gates

| Gate | Status | Script | Rule |
|---|---|---|---|
| G_M1 min trace width 0.1mm | 🔴 | TODO audit_min_track | JLC SMT capability |
| G_M2 min via drill 0.3mm | 🔴 | TODO audit_min_via | JLC SMT capability |
| G_M3 min annular ring 0.15mm | 🔴 | TODO audit_min_annular | JLC SMT capability |
| G_M4 LCSC stock + part-number presence | 🔴 | TODO audit_bom_lcsc_stock | every BOM line has stocked LCSC part |
| G_M5 assembly drawing complete | 🔴 | TODO audit_assembly_drawing | rotations + polarity marks + 0,0 reference |
| G_M6 panelization fit | 🔴 | TODO audit_panel_fit | board ≤ JLC max panel × N |

## F. Sim execution + result gates (R18)

| Gate | Status | Script | What it catches |
|---|---|---|---|
| G_S1 sim 4-point execution proof | ✅ | (R18 in PR body) | result file + mtime + extract script + literal exec cmd |
| G_S2 mesh validity pre-run | 🔴 | TODO audit_mesh_validity | Elmer mesh non-degenerate before solve |
| G_S3 result physical-plausibility | 🔴 | TODO audit_result_sanity | T_J in Kelvin not Celsius; current in Amps not nA |

## G. Vision + manual gates

| Gate | Status | Script | What |
|---|---|---|---|
| G11 vision check render set | ✅ | render_pr_visual | 6/6 artifacts present + master inspects |
| G_V1 silk readability inspection | 🔴 | manual checklist | render-zoom on silk |
| G_V2 3D fit + clearance manual | 🔴 | manual checklist | iso view of every cluster |

## H. Process + documentation gates

| Gate | Status | Script | What |
|---|---|---|---|
| G9 target.h md5 lock | ✅ | (md5 in master_pre_merge) | firmware contract drift |
| G10 verify_spec_diff R20 | ✅ | verify_spec_diff | mirror geometry CH1↔CH2/3/4 |
| G_D1 OPEN_QUESTIONS.md sync | 🔴 | TODO audit_open_questions | every CL-xxx referenced in code has doc entry |
| G_D2 memory file index sync | 🔴 | TODO audit_memory_index | every memory file has MEMORY.md row |
| G_D3 audit-validation row sync | 🔴 | TODO audit_validation_index | every audit_*.py has truth-table row |
| G_D4 R-rule three-artifact check | ✅ | audit_meta.py | every R-rule has fix-script + audit-fn + master-verified |

## Build priority (catches likely in Stage 2 CH1)

**MUST land before Stage 2 CH1 PR**:
1. G16 connector symmetry — wire to master_pre_merge
2. G17 edge keepout — wire to master_pre_merge
3. G_FoS1 thermal T_J 25% FoS — applies to existing baseline + each new sim
4. G_FoS2 trace ampacity 50% FoS — channel switching nets
5. G_FoS3 cap voltage derating — bulk caps + decoupling
6. G_FoS4 cap ripple current — closes OQ-006 R17 indirectly
7. G_L1 lockfile completeness — catches future drop-outs early
8. G_M4 LCSC stock check — pre-fab BOM sanity

**Stage 2+ targets**:
- G_R1-G_R6 routing gates (Tier 2-5 work)
- G_PP1-G_PP7 placement-quality gates (Sai-eye-catch class)

**Pre-fab targets**:
- G_M1-G_M6 manufacturing gates
- G_S2-G_S3 sim quality gates

## Rule for new gates

Per R32 sureshot + this directive: ANY rule we follow mentally MUST become a
codified gate before any board change relies on it. No "I'll add the gate
after I make the mistake". If a rule is real, it has a gate.

Every gate must have:
1. Script `audit_*.py` in `hardware/kicad/scripts/`
2. Synthetic ground-truth test in `tests/build_validation_board*.py`
3. Row in `docs/AUDIT_VALIDATION.md` results table
4. Wired into `master_pre_merge.sh`
5. Row in this `GATE_INVENTORY.md`
