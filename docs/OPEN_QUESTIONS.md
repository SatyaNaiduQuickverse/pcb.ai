# Open questions + decisions log

Decisions the project owner has not yet made (open) and decisions already made
with their rationale (closed). Per `CLAUDE.md` Rule 8: each entry carries
options (≥ 2), a recommendation, trade-offs, and the date raised. Closed
entries also record the choice + why, and the rejected options + why.

Cross-reference: locked specs live in `docs/REQUIREMENTS.md`; this file logs
*how we got there*.

---

## Closed — decisions made

### CL-001 — Target fab + DRC ruleset

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **JLCPCB SMT**
- **Options considered**:
  - JLCPCB SMT — cheap, fast turnaround, broad assembly library
  - PCBWay — more part-source flexibility, slightly higher cost
  - Industrial fab (Sierra Circuits, domestic Indian fab) — tighter tolerances, much higher cost + lead time
- **Rationale**: Sai's call. JLCPCB SMT is the standard for proto + production small-batch in this segment; their published capability spec becomes the authoritative DRC ruleset for every SKU (per Playbook §Manufacturability). Motor-control part availability against JLC assembly library checked at each SKU's Phase 2; parts not in library get sourced externally + hand-soldered or trigger a part-swap at Phase 2.
- **Trade-offs**: Some specific high-voltage motor-control MOSFETs may not be in JLC's basic library and require an "extended" part fee or hand-assembly. Acceptable.

### CL-002 — Firmware base for FPV 4-in-1 ESC (PL1)

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **AM32 (GPLv3)**
- **Options considered**:
  - **AM32** (GPLv3, open-source, no licensing fee) — modern 32-bit, supports STM32G071 / AT32F421 / others
  - **BLHeli_32** (closed source, paid commercial license) — *ruled out*: license issuance was shut down in May 2024 due to Ukraine war / export regulations; not available for new products
  - **Bluejay** (GPLv3, 8-bit BLHeli_S successor) — works but generation behind; only relevant if we picked an EFM8 8-bit MCU, which we are not
  - **Roll-our-own** — pointless given AM32 maturity + same-license obligation
- **Rationale**: AM32 is the de facto open standard for 32-bit FPV ESCs in 2026. GPLv3 obligations (publish source of any modifications shipped) are *fine for the FPV market* — every brand ships AM32 today; the IP is in the hardware design, not the firmware. We author a hardware-target file for our board and contribute it back to the AM32 repo per copyleft.
- **Trade-offs**: Cannot make a proprietary closed-source fork of AM32. Acceptable for FPV market norm.

### CL-003 — Firmware base for HV60 commercial FOC family (PL2)

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **STM32 X-CUBE-MCSDK on STM32G4**
- **Options considered**:
  - **STM32 X-CUBE-MCSDK** — ST's reference FOC stack. Free for STM32 use (not GPL). Motor Control Workbench (GUI) for config + tuning. Reference drone-ESC design exists (STEVAL-ESC001V1, sensorless FOC three-shunt + active braking)
  - **VESC port** (GPLv3) — *ruled out*: GPL is viral; we'd have to publish our hardware-specific tuning + IP, which kills the closed-commercial reliability play
  - **Roll-our-own FOC from scratch** — *ruled out*: weeks of bench tuning of observer gains, current loops, startup transitions, fault thresholds. Sim cannot validate (Rigor §4); risk too high for a commercial reliability product
  - **TI MotorWare / InstaSPIN** — *not considered seriously*: would lock us into TI silicon which fragments our two-product-line MCU strategy
- **Rationale**: HV60 family is closed-commercial. X-CUBE-MCSDK is ST's mature, production-grade reference for exactly this use case. STM32G4 family is the motor-control-optimized successor to F303 (used in STEVAL-ESC001V1).
- **Trade-offs**: STM32 lock-in across the HV60 family. Fine — we'd have picked STM32 anyway.

### CL-004 — Drop 3S support across all SKUs

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **No 3S support**
- **Rationale**: No commercial FOC drone ESC in 2026 supports 3S (verified via market research: T-Motor Alpha lineup, Hobbywing XRotor Pro lineup all start at 4-6S). FOC computational + thermal overhead doesn't pay off below 4S; 3S is hobby class where six-step ESCs dominate. Designing 3S support would force lower-V_DS MOSFET options and adds a buck regulator that works to 9 V — cost and complexity without market demand.
- **Trade-offs**: Excludes hobby-class entry segment. Acceptable per "commercial reliability + commercial-volume FPV" positioning.

### CL-005 — Product-line sequencing — FPV 4-in-1 first, HV60 family second

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **FPV 4-in-1 first**
- **Options considered**:
  - **(A)** HV60 family first, then FPV 4-in-1
  - **(B)** Parallel — both product lines simultaneously (2 × engineering bandwidth)
  - **(C)** FPV 4-in-1 first, then HV60 family
- **Rationale** (Sai's call, well-reasoned): firmware testing for FOC requires knowledge + equipment we don't yet have; for FPV with open-source AM32 the firmware is community-validated and we only need a hardware-target file. Hardware can be sim-validated to high confidence pre-fab for FPV. The heavy reliability burden (HALT, EMC certification, MTBF claim) only applies to HV60 (commercial / costlier drones) and can be deferred until team + lab infrastructure exists. FPV-first validates JLCPCB pipeline, sim regime, team rhythm on lower-stakes hardware before tackling HV60.
- **Trade-offs**: FPV-first means the FOC + reliability work isn't validated on real silicon for ~3–4 months. Mitigated by the fact that HV60 launch is gated on lab buildout regardless. Parallel (option B) ruled out — classic split-focus failure mode at our bandwidth.

### CL-006 — FPV 4-in-1 voltage range — 6S only

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **6S only**
- **Options considered**: 6S only / 4–8S / 6–8S
- **Rationale**: Sai's call. 6S only is the dominant FPV power class (race + freestyle + cinematic mainstream). 8S would force 60 V MOSFETs and adds back-EMF spike risk; 4–8S adds buck-regulator complexity and dilutes thermal/copper design. Single-voltage tier gives us tighter component selection.
- **Trade-offs**: Excludes 8S X-class and 4S micro/whoop segments. Future SKUs (8S variant) can be added once 6S is shipping.

### CL-007 — FPV 4-in-1 continuous current — 70 A per channel

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **70 A continuous / channel**
- **Rationale**: Sai's call. Matches SEQURE E70 G2 / Blueson A2 segment (the modern 32-bit + AM32 generation, ~70 A continuous). Sits above the 50–60 A mainstream and below 80–100 A heavy-lift; broadest demand sweet spot for 6S.

### CL-008 — FPV 4-in-1 form factor — physics-driven, NOT pre-constrained

- **Raised**: 2026-05-21
- **Closed**: 2026-05-21 — **Sized via Phase 2.5 from thermal + layout sims**
- **Rationale**: Sai's call. "Let physics dictate". Phase 2.5 converges: minimum-board-area for 4 × 70 A continuous + JLC trace/space density → take the larger of {physics-required, nearest standard FPV stack pattern (20×20 / 30.5×30.5 / 40×40 / 60×60 family)}. Start large, iterate down across subsequent revisions.
- **Trade-offs**: First-rev board may be larger than direct competitors. Acceptable — Sai prioritizes margins via simulation confidence over first-rev compactness.

### CL-009 — FPV 4-in-1 burst current — 100 A @ 10s pulse

- **Raised**: 2026-05-22
- **Closed**: 2026-05-22 — **100 A burst @ 10s pulse per channel** (1.43× the 70 A continuous of CL-007)
- **Rationale**: Sai delegated to master, master adjudicated via sureshot-vs-SOTA rule. Anchored on iFlight BLITZ E80 = top of the premium-FPV 1.25–1.40× peak-to-continuous band. SOTA aggressive picks (1.5×+) carry validation risk; iFlight reference is field-proven on a comparable spec class. Sureshot wins.
- **Effect on plan**: Supersedes Phase 2c/d's informal use of "70 A peak" (which was peak=continuous). Phase 2-burst-resize is the engineering re-survey:
  - Bus caps ripple-current rating
  - F.Cu motor-phase trace ampacity (IPC-2152 at 100 A 10s pulse — may force 2 oz or 3 oz copper)
  - AON6260 rev-pol FET (67 A continuous max → 100 A burst exceeds — survey replacement ≥ 120 A continuous / ≥ 200 A pulse, 6S/30V class)
  - Current-sense path (20 mV/A × 100 A = 2.0 V at AT32F421 ADC — 61% of 3.3 V reference; previously 1.4 V / 42%)
- **Carry-forward**: AM32 firmware unchanged (rules out balance-lead telemetry / differential ADC / R3 single-MCU architectures); 4× MCU per-channel design preserved.

### OQ-006 — PL1 MCU family pick (closed)

- **Raised + Closed**: 2026-05-22
- **Question**: Which MCU family for the FPV 4-in-1 (PL1)? Per `REQUIREMENTS.md` §fpv-4in1, choices were STM32G071 OR AT32F421.
- **Options**:
  - **(A)** STM32G071CBT6 — ST mainline, 128 KB Flash, M0+ 64 MHz, LQFP-48, ~$3–5, AM32 29 targets
  - **(B)** AT32F421K8T7 — Artery, 64 KB Flash, M4 120 MHz, LQFP-32, ~$0.90, AM32 240 targets, JLC 9419 in stock
- **Pick**: **B (AT32F421K8T7)**.
- **Rationale**: AM32 community references 8× higher on f421 → more community-validated, sureshot per Sai's tiebreaker. M4 @ 120 MHz gives speed headroom for bidirectional DShot RPM filtering + telemetry. Cost advantage meaningful for commercial product. LQFP-32 fits 4-in-1 density. JLC stock confirmed.
- **Trade-off**: Artery clone, not ST mainline — supply chain has slightly more risk than STM32. Mitigation: AT32 has been shipping in volume since 2016, well-established; second-source qualification (e.g., MM32 or STM32G031 pin-compat option) added to a future Phase 2 sub-task if reliability data ever warrants it.
- **Resolution-gate**: closed; pin assignments and exact part SKU (-T7 vs -U7 package variants) confirmed at Phase 2 from final datasheet + JLC availability check.

---

## Open — pending owner input

### OQ-001 — Bench / lab access reality for validation

- **Raised**: 2026-05-21
- **Status**: Open
- **Question**: For the FPV 4-in-1 single-fab-iteration target, the minimum bench setup is: current-limited bench supply (≥ 30 V, ≥ 20 A), oscilloscope (≥ 100 MHz, 4-channel, with isolated probes for high-side measurements), DC current probe, a flight controller for DShot integration testing, and 4 × small test motors for spin-up. For HV60 family later: motor dyno, thermal chamber, EMC test-house partnership.
- **Options**:
  - (a) Sai has bench access — we plan around what's available
  - (b) No bench yet — we plan acquisition / partner-lab (university lab / EMC test house, ~$5–15K for FPV minimum + HALT/EMC bundle when HV60 hits)
  - (c) Bench partial — list what we have, what we'd need to acquire / borrow
- **Recommendation**: Sai answers; this drives whether bench validation happens in-house or via partner. Either is fine — the question is *which* and *when*.

### OQ-002 — FPV 4-in-1 ship target

- **Raised**: 2026-05-21
- **Closed**: 2026-05-22 — **No date target; quality flexes the schedule, not the reverse**
- **Sai's answer**: "we have time.. as much as we need.. quality matters a lot here."
- **Effect on plan**: full P3.5 reference audit + full P6 sim regime + P6.5 external review all in scope without time-pressure trade-offs. Wall-clock for the FPV 4-in-1 will be 4–6 months as estimated in the dev plan, possibly more if sim re-loops surface design changes (Rigor §6 — expected). The development pace is bounded by quality gates, not calendar deadlines.

### OQ-005 — Freerouting Java mismatch (CLOSED at Phase 5a)

- **Raised**: 2026-05-22. **Deferred**: 2026-05-22. **Closed**: 2026-05-22 — **Option A** executed.
- **Resolution**: Worker-local Adoptium Temurin JDK 25.0.2+10 installed at `/home/novatics64/escworker/local/jdk25/`; worker-local Freerouting v2.2.4 jar at `/home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar`. System Java 21 stays default; shared `/home/novatics64/local/freerouting/freerouting.jar` UNCHANGED (SHA256 + mtime verified pre/post). novapcb unaffected.
- **Finding during execution**: Worker's downloaded Freerouting v2.2.4 release jar has the IDENTICAL SHA256 (`f5ed374182900ccc78e473518bbb9f6b869f4a07159495f663a76f52bb10523b`) to the shared jar novapcb uses; both built with JDK 25.0.2+10 per manifest. Master's Phase 5a prep research ("v2.2.4 requires Java ≥ 21") was based on source-Java-level claims; the actual release BINARY needs Java 25 (class file v69). Master's adjudication on the Phase 5a URGENT (2026-05-22) re-confirmed Option A as the path forward.
- **Smoke tests**: Freerouting v2.2.4 starts cleanly on the worker-local JDK 25 (version line confirmed); 2-net DSN end-to-end smoke produced .ses output successfully. Toolchain ready for Phase 5b DSN routing.
- **Cross-project insight surfaced for Sai**: novapcb's shared jar is the same JDK-25-built binary; they must either have their own worker-local JDK 25, or be hitting this same incompat. Worth coordinating if it helps unblock novapcb's reported routing pain.
- **See**: `docs/PHASE5A_FREEROUTING_SETUP.md` for full execution record.

### OQ-003 — HV60 family ship target

- **Raised**: 2026-05-21
- **Status**: Deferred (raised after FPV 4-in-1 is in fab)
- **Question**: Target ship date for ESC-HV60 once we pick it up.
- **Recommendation**: Defer; set at the start of PL2.

### OQ-004 — Worker's working copy of pcb.ai

- **Raised**: 2026-05-21
- **Closed**: 2026-05-22 — **Option A** (worker clones into `/home/novatics64/escworker/pcb.ai`, branches per sub-phase per CLAUDE.md §6, pushes to GitHub, master reviews on GitHub)
- **Options considered**:
  - **(A)** Worker clones `github.com/SatyaNaiduQuickverse/pcb.ai` into `/home/novatics64/escworker/pcb.ai`; branches per sub-phase per CLAUDE.md §6 ("one sub-phase = one PR"); pushes to GitHub; master fetches + reviews + merges
  - **(B)** Worker has read-only access to master's clone at `/home/novatics64/novapcbmaster/pcb.ai` — no write workspace, defeats PR review boundary, CLAUDE.md autoload doesn't trigger
  - **(C)** Shared writable clone — concurrent-edit risk, defeats master/worker review model
- **Rationale**: Existing GitHub origin is the natural shared remote (no new infra). Standard PR workflow: branches per sub-phase, master reviews on GitHub. Setup is one `gh repo clone` away. Closed by Sai/master authorization in the Phase 0 task contract (2026-05-22).

---

### OQ-006 — C1-C4 bulk-cap ripple-current FoS verification

- **Raised**: 2026-05-25 (worker R17 catch during Phase 4-v3 REDO infra PR #101)
- **Status**: OPEN — to resolve at Stage 9 (S2 PR) via ngspice ripple sim
- **Context**: S2 BOM relock changed 4× 470µF (Panasonic, 4A RMS rated, prior FoS analysis) → 4× 150µF (Nichicon PCH1V151MCL1GS, datasheet ripple rating not yet sourced). Per-cap rated ripple at 100kHz / 105°C for the PCH1V151 must be confirmed before fab freeze.
- **Engineering**: 4-channel phase-staggered switching reduces bulk-cap RMS ripple by ~3-4× vs single-channel worst-case. Pure analytical estimate now would be pessimistic.
- **Resolution plan**: 
  1. Stage 9 S2 PR runs ngspice transient with routed +VMOTOR plane (real parasitics) and measures actual RMS ripple seen at C1-C4
  2. Source datasheet rated ripple for PCH1V151MCL1GS (Nichicon PCH series)
  3. Compute FoS = (4 × rated_per_cap_RMS_at_30kHz_105C) / measured_RMS
  4. PASS criterion: FoS ≥ 1.5×
- **If FAIL paths**: 
  - Swap to higher-rated polymer in same package
  - Add ceramic 1210 X7R array in parallel (option ε from PR #104 traceability table)
  - Re-derive at Stage 9 PR with new BOM
- **Blocker for**: fab freeze (Phase 9). NOT a blocker for Stage 0-8 PRs.
- **Owner**: master (ngspice cross-check) + worker (BOM swap if FAIL)

### OQ-007 — Multi-layer thermal sim re-validation post B.Cu LS-FETs

- **Raised**: 2026-05-26
- **Trigger**: Stage 2 CH1 adopted B.Cu backside LS-FET placement (Sai-anticipated call)
- **Question**: Does the Phase 4-v2 single-side thermal baseline (T_J cont=62.76°C, burst=82.99°C, recorded in `docs/THERMAL_BASELINE.md`) still apply to the multi-layer placement, or do we need a fresh Elmer sim with HS-top + LS-bottom geometry?
- **Expected impact**: MODEST improvement (heat spreads to both copper layers via thermal-via clusters under each FET) — directionally favourable, may relax burst-FoS pressure (currently 17.0% margin, exceeds 25% continuous standard but justified at 10% transient)
- **Resolution**: re-run Elmer FEM at Stage 10 (full board placed + routed) with multi-layer mesh. Compare against single-side baseline. If new T_J ≤ old T_J, baseline stands as conservative bound. If new T_J ≤ 65.5°C cont / ≤87°C burst (FoS limits), board passes.
- **Blocks**: fab freeze only

### OQ-008 — XT30 vs XT60/XT90 for 70A continuous battery input

- **Raised**: 2026-05-26 (caught by proactive gate G_FoS5 audit_fos_pin_current)
- **Trigger**: G_FoS5 FAIL on J1: XT30 30A continuous (AMASS datasheet) vs our 70A continuous load × 1.5 FoS = 105A required → XT30 undersized by ~3×.
- **Options**:
  - **(a) Upgrade J1 to XT60**: 60A cont, 130A burst — still ~70% short of 105A FoS but covers our continuous spec at 1× (industry-typical for FPV race ESCs)
  - **(b) Upgrade J1 to XT90**: 90A cont, 240A burst — meets FoS at 90A vs 105A required (87%), comfortable for spec headroom
  - **(c) Keep XT30 + reduce spec to 30A continuous**: makes FPV "60A class" not "70A+ class" — competitive setback
  - **(d) Dual XT30 input (paralleled)**: 60A combined — adds mech complexity (two cables), unusual
- **Recommendation**: option (b) XT90 — sureshot, comfortable FoS, no spec compromise. Phase-2 era XT30 selection was a too-conservative starter; production rev should go XT90.
- **Impact**: footprint change ([invariant-change] PR), BOM change (XT90 + corresponding battery lead), mech (XT90 body ~25×15×17mm vs XT30 ~12×8×8mm — larger footprint at edge but acceptable for our 100mm board)
- **Blocks**: fab freeze (must resolve before final BOM lock)

### OQ-008 — RESOLVED 2026-05-26 (Sai call: skip connector entirely, solder pads for wire)

Sai decision (verbatim): "you need to only give solder pad i will solder a wire to it.. which will be connected to a xt90"

Resolution: J1 XT30 connector REMOVED. Replaced with BAT_P + BAT_N solder pads
(custom footprint BatterySolderPad_5x5_THT2.0_HC: 5×5mm Cu both sides + 2mm THT
plated hole + 16-via grid, ~150A burst capacity per IPC-2152). External XT90
wire (10-12 AWG silicone) hand-soldered to pads at integration. Connector
spec problem dissolves: wire is the rated element (XT90 90A cont), not the
pad. G_FoS5 connector pin-current rule no longer applies to BAT_P/BAT_N.

Massive simplification:
  - BOM: one less line (no XT30 part)
  - Cable swing audit: no connector cable bend zone to clear
  - Pin-current FoS: N/A (wire-rated)
  - Mech: simpler enclosure (no connector cutout needed)

Lockfile updated [invariant-change]. Worker re-runs Stage 0 to land BAT pads.

### OQ-009 — INA186 (J20/J21/J22) V+ bypass cap gap (latent, future schem rev)

- **Raised**: 2026-05-26 (worker latent-finding during CH1 G4 debug)
- **Issue**: The 3 INA186 current-sense op-amps (J20/J21/J22 per channel) have NO V+ bypass cap on pin 4 / +3V3 input. Their only cap (c_csa) sits on the output net, not the supply pin. Per R25, every IC with V+ needs ≥1 decoupling cap ≤3mm same-layer.
- **Why G4 doesn't catch it**: INA footprints use Connector_Generic with unnamed pins (legacy SKiDL); G4 audit_decoupling scopes IC.VDD by pin NAME (matches "VDD", "VCC", "AVDD" patterns). Unnamed pins escape detection.
- **Impact**: at worst, slight INA noise / settling-time degradation. Not power-supply-rejection-ratio sensitive enough to be a CH1 PR blocker. Sai-acceptable for first fab; tighten in commercial rev.
- **Resolution**: NEXT schematic rev — add 3× 100nF X7R caps to J20.4 / J21.4 / J22.4 → GND, ≤3mm same-layer. Also extend G4 to handle Connector_Generic with pin-NUMBER convention (pin 4 = V+ on INA186).
- **Blocks**: nothing immediate (CH1 PR can proceed). Future commercial fab freeze should address.

### OQ-010 — B.Cu component-density vs F.Cu balance (post bilateral)

- **Raised**: 2026-05-26 (per docs/BILATERAL_PLACEMENT.md)
- **Question**: With S2 bulk caps + S5 BEC + LS-FETs + LS-decoupling + LEDs on B.Cu, does B.Cu density exceed F.Cu? If so, what gets pulled back to F.Cu?
- **Trigger**: Stage 9 (S2 + S5 brought) — measure per-side component bbox sum
- **Resolution rule**: if B.Cu density > 60%, pull status LEDs back to F.Cu (lowest electrical impact). If still >55%, revisit per-channel decoupling split.

### OQ-011 — Multi-layer thermal sim must include BEC heat sources

- **Raised**: 2026-05-26 (per docs/BILATERAL_PLACEMENT.md, extends OQ-007)
- **Question**: Phase 4-v2 thermal baseline was single-side, single-source (FETs only). With S5 BEC on B.Cu directly under MCU + S2 bulk caps on B.Cu under FETs, the multi-layer Stage 10 thermal sim must include all heat sources: FETs (per-channel × 4) + BEC bucks (5 rails, ~0.5W each at 80% efficiency) + LDO + bulk caps (ripple I²R).
- **Trigger**: Stage 10 Elmer FEM re-run (post all placement done)
- **Resolution**: build multi-layer Elmer mesh + apply all 4+5+1 = 10 heat sources; verify T_J ≤ 75°C continuous / 90°C burst FoS bounds hold; OQ-007 closes when met.

---

## OQ-014 — 8L stackup dielectric not locked (loop-L plane-reference dependency) — RESOLVED 2026-05-26

**Raised**: 2026-05-26 by worker CH1 STEP 3 loop-L sim.

**Symptom**: loop_extract.py reports PLACEMENT-STAGE L_loop = 13.56 nH free-space bound (FAIL vs 2 nH target). Plane-referenced model with adjacent In1.Cu GND plane gives 0.16–0.36 nH (PASS) but cannot be confirmed because **F.Cu→In1.Cu prepreg dielectric thickness `d` is not defined** in the .kicad_pcb or repo. JLC 8L default ranges 0.076–0.21 mm.

**Master decision (2026-05-26, per physics-as-compass + BILATERAL design intent)**:
- DO NOT trigger placement re-do. Placement geometry is correct (5.40mm HS-LS Y-offset = body-clear pair, 13mm phase pitch, sub-zone honored). The free-space bound is conservative; the real design model is plane-referenced per BILATERAL_PLACEMENT.md.
- LOCK stackup dielectric at d = 0.10 mm (mid-JLC-range, conservative) BEFORE Phase 5 routing begins. Update setup_board.py + BOARD_INVARIANTS.md stackup block.
- Per stage flow: loop-L is **STAGE-3 conditional PASS, stackup-lock pending**. Post-route re-sim in STEP 6 with locked stackup + routed plane-reference will give the final L_loop number.
- This is not a corner-cut: BILATERAL design assumed plane reference from day 1 (see BILATERAL_PLACEMENT.md §commutation loop). Worker's loop_extract.py free-space bound is a useful CONSERVATIVE upper bound but is not the design metric.

**Action items**:
- [x] Master 2026-05-26: locked 8L stackup dielectric (d=0.10mm F.Cu→In1.Cu prepreg + symmetric stackup) in BOARD_INVARIANTS.md per PR #162. .kicad_pcb (stackup) block addition deferred to Phase 7 fab-prep (cosmetic; doc-lock is what STEP 4 routing needs).
- [ ] Worker: add `loop_extract.py --routed` mode for post-route validation
- [ ] STEP 6 re-sim with locked stackup + routed plane reference (final number)
- [ ] Update parametric engine `ls_fet_y_offset_from_hs` 3.6 → 5.4mm (sync to actual placement; worker's flag) — separate small PR

**Sai review needed at return**: confirm acceptance of stackup-lock-pending decision OR override.


---

## OQ-015 — Phase-4-v2 thermal template carried 2 real bugs (worker-caught 2026-05-26)

**Raised**: 2026-05-26 by worker during CH1 STEP 3 thermal sim. The v2 thermal template (sims/phase4v2/ch1_thermal/ch1.sif + ch1_v1.sif and downstream sims using same template) was producing **non-physical 36,236°C** results — silently passing as "completed" because no audit gate validated physical plausibility against analytic check.

**Bugs found + fixed by worker in Phase 4-v3 CH1 thermal sim**:

1. **mesh.boundary parent-element columns were '0 0'** — Elmer never coupled the convective boundary condition → no heat left the block → temperature ran away. The mesh export from previous templates was incomplete; Elmer silently used adiabatic BC instead of the specified convective.

2. **Elmer Body-Force `Heat Source` unit confusion** — Elmer's Heat Source is **SPECIFIC power (W/kg)**, NOT volumetric W/m³. Template was specifying volumetric → Elmer multiplied by FR4 density (~1850 kg/m³) → over-drove the source by ×1850. Hence the absurd 36,236°C.

Both fixed in Phase 4-v3 CH1 thermal (worker validated against lumped + conduction analytic check).

**IMPLICATION (Sai-attention)**: Every prior thermal sim using the same template lineage is SUSPECT:
- Phase-4c (Task #22, #39) — Elmer thermal v3 on R1 + 8L
- Phase-4-CH1-replace-P12 (Task #64) — Elmer FEM v3
- Phase-5c full-board integration thermal — claimed 83°C; likely also affected by ×1850 over-drive  
- Any downstream sim referenced from sims/phase4_integrate/full_thermal/

**Master action (DECISION)**:
- ACCEPT CH1 thermal PASS (54.65°C continuous, 89.28°C burst — both <110°C target).
- LOG this OQ; mark Stage 10 full-board thermal re-run as MANDATORY with the 2 fixes applied + analytic-check validation.
- Make G_S3 sim-result-sanity gate stronger: include analytic-bound check that flags any T_J >5× ambient as suspect (catches density-factor bugs by class).
- Don't retroactively re-do Phase-2b/4c/Phase-5c PRs — they shipped on the assumption sims passed; data was wrong but conclusion (sim is "in spec") was hard to verify. CH1 STEP 3 thermal is the FIRST CORRECT thermal sim.

**Caveats on Phase 4-v3 CH1 thermal PASS** (worker-disclosed, master-accepted):
- CH1-ONLY model with heatsink External Temp pinned at 25°C
- At full-board burst 4×144.5W=578W, heatsink base + ambient WILL rise → 89.28°C burst margin (20.7°C) is OPTIMISTIC LOWER BOUND
- Real burst number requires full-board integration thermal at Stage 10
- Load-bearing BC: effective h=15000/5000 W/m²K (TIM-to-heatsink conduction, not free-conv 15/5 which diverges for isolated island). Option-b convention, master-approved.

**Sai-attention items at review**:
1. Confirm acceptance of thin 20.7°C burst margin at single-channel sim (full-board verifies)
2. Approve Stage 10 full-board thermal re-run as MANDATORY
3. Approve G_S3 strengthening to catch density-factor class bugs


---

## OQ-016 — EMI placement-stage geometric bound; real coupling is post-route

**Raised**: 2026-05-26 by worker CH1 STEP 3 EMI sim.

**Symptom**: openEMS FDTD on placement-only board (no routed SW/BEMF traces) doesn't converge — synthetic geometry has no defined conductor structure for FDTD to compute coupling. Worker correctly identified that EMI coupling, like loop-L (OQ-014), is FUNDAMENTALLY a post-route metric.

**Placement-stage actionable proxy**: SW(MOTOR_CH1)↔BEMF pad separation; worker measured min 1.02mm at MCU east cluster (target ≥10mm per BILATERAL §40).

**Master decision (2026-05-26, per [[feedback-physics-as-compass]] + analogous to OQ-014)**:
- DO NOT trigger placement re-do. 1.02mm pad-separation is BY DESIGN — both pad classes have to reach the MCU/INA in the dense east cluster.
- The 10mm rule from BILATERAL_PLACEMENT.md §40 is for SAME-LAYER trace routing without GND-plane shielding.
- Our multi-layer board provides:
  * SW node on F.Cu (HS drain) + B.Cu (LS via cluster)
  * BEMF traces on internal In2 signal layer (post-route)
  * In1 GND plane between them (~0.1mm prepreg) → tight inductive shielding
  → Effective EMI isolation comes from LAYER STACKUP, not XY pad distance
  → Analogous to HB-cell creepage exemption (physics depends on multi-layer geometry, not raw XY)

EMI marked **STAGE-3 conditional PASS, post-route STEP 6 EMI re-sim mandatory** with routed traces + GND plane reference for real coupling number.

**Action items**:
- [ ] Post-route STEP 6: openEMS FDTD with routed SW + BEMF + GND plane (real coupling number)
- [ ] During Phase 5 routing: enforce BEMF on In2 signal layer + dedicated GND plane reference (In1)
- [ ] Audit: extend G_PP6 / hv_creepage to flag SW↔BEMF same-layer routing (post-route gate)

**Sai-attention items at review**:
1. Confirm acceptance of EMI conditional PASS (1.02mm pad sep, layer-shielding rationale)
2. Approve post-route STEP 6 EMI re-sim mandatory


## OQ-017 — Inner-layer SW escape on In4 (CH1 routing geometry) — scope clarified by OQ-019 2026-05-26

**Raised**: 2026-05-26 by worker STEP 4 CH1 routing. Naive hand-route of SW node FAILS (32 clearance violations) because SW pads are at FET WEST column x=5.55, motor pad TP is at EAST x=15, with VMOTOR_CH drain + shunt pads at x=11.25 BETWEEN them — SW cannot escape east on F.Cu/B.Cu only without crossing opposite-polarity pads. Gate pad N$9 also in SW column.

**Master decision (2026-05-26, per [[feedback-physics-as-compass]])**:

Inner-layer SW escape ALLOWED — **layer must be In4.Cu, NOT In2.Cu**. Reasoning:

| Layer | Nearest GND ref | Distance | Risk |
|---|---|---|---|
| In2.Cu | In1 (core above) | 0.20 mm | Co-layer with BEMF per OQ-016 — defeats shield |
| In4.Cu | In5 (prepreg below) | 0.10 mm | No conflict; matches F.Cu→In1 stackup symmetry |

In4 chosen: (1) 0.10mm prepreg to In5 GND matches F.Cu→In1 0.10mm — stackup-symmetric loop-L per unit length; (2) preserves OQ-016 BEMF-on-In2 shielded by In1 GND; (3) In3 +VMOTOR plane above acts as capacitive shield (favorable since SW switches against VMOTOR — decoupling effect).

B.Cu LS pads ref'd by In5 at d=0.335mm (prepreg+In6+core) → effective bilateral d_avg ≈ 0.22mm → recomputed loop-L ~0.33nH per phase, still 6× headroom from 2nH target.

**Binding gates**:
- Measured loop-L on routed COPY ≤2nH per phase (geometric extract, not analytical) before promotion to canonical
- Each SW inner-layer transition via has ≥1 GND return via within 0.5mm (Bogatin/Johnson mutual-inductance cancellation rule)
- Phase A routed first; B+C are pure geometric transforms of A (symmetry, [[feedback-symmetry-preserves-work]])
- If measured loop-L >2nH: STRUCTURAL RETHINK = placement REDO (motor TP eastward OR VMOTOR_CH/shunt cluster westward of FET column). NOT band-aid trace re-route ([[feedback-redo-not-mitigate]]).

**CH2/3/4 implication**: bilateral CH1 SW-escape geometry inherits to all 4 channels via mirror transforms. If In4 escape is needed for CH1, it's needed for all 4. Flag in STEP 7 CH1 PR for master review whether template revision is needed before Stage 7-9 mirror PRs.

**Status**: ADJUDICATED — worker may proceed with In4 escape. Re-evaluate post-route on measured loop-L.

---

## OQ-018 — Phase 7 full-board DRC infrastructure (15GB Pi insufficient)

**Raised**: 2026-05-26 by worker during CH1 STEP 4 Freerouter verification. `kicad-cli pcb drc` hung 107min CPU then OOM-killed on 15GB Pi. Full-board GND+VMOTOR plane zones × 573 footprints × clearance checks exhausts available RAM during boolean intersection computation.

**Class lesson**: 15GB Pi is insufficient for full-board DRC on this design density. Subsystem-scope DRC (CH1 nets only) is feasible and CORRECT per §8 subsystem-PR methodology; full-board DRC is Phase 7 integration gate, not STEP 5 acceptance gate.

**Codified workaround (immediate, this session)**:
- PLACEMENT_GLOBAL_PLAN §8 addendum: "Pi-bounded operations (DRC, full-render, full-route) MUST be subsystem-scoped during Phase 4-v3 STEP 4-6. Full-board operations are Phase 7 gates only."
- audit_routing.py + audit_subsystem_scoped_drc.py (if needed) targets CH1-only.
- Memory: `feedback-pi-bounded-subsystem-scope` saved.

**Sai-decision pending (Phase 7 entry)**:
- Cloud DRC (KiCad on Anthropic cloud / cloud KiCad-server)?
- External x86 machine (rent/dedicated)?
- Skip pre-fab full-board DRC + rely on JLC fab DFM check (RISKY — JLC catches gross errors but not subtle clearance issues; rework cycle 5+ days per [[feedback-jlc-dfm-pre-fab-gate]])?

Recommend external x86 for Phase 7 — same toolchain, no cloud dependency, deterministic.

**Status**: BLOCKING for Phase 7 entry. Non-blocking for Phase 4-v3 STEP 4-6 (subsystem-scope sufficient).


## OQ-019 — R19 / OQ-017 SW-symmetry scope clarification (commutation loop vs trace polyline)

**Raised**: 2026-05-26 by worker STEP 4 CH1 routing — R19 pure-transform of per-phase routes was geometrically infeasible at 13mm phase pitch on this placement density. Per-phase routing footprint spans ~15mm in y, but phase pitch is 13mm → translating Phase-A routing +13mm overlaps neighbor band by ~2mm. Transform attempt caused +273 real inter-phase clearance overlaps. Worker correctly identified this as a binding rule that's over-constrained vs physics need + escalated rather than band-aiding ([[feedback-redo-not-mitigate]]).

**Master adjudication (2026-05-26)**:

R19 / OQ-017 SW-symmetry binding is re-scoped to **commutation loop symmetry**, not full SW-trace polyline identity.

| Scope | Required | Verification |
|---|---|---|
| FET-cluster placement geometry symmetric | YES | G_PP22 ([[PR #166]]) |
| SW commutation loop-L identical per phase | YES | measured ≤2nH + A=B=C to 4 decimals at FET-cluster |
| SW outward trace polyline identity | **NO** (re-scoped 2026-05-26) | n/a — Freerouter per-phase asymmetric OK |

**Physics rationale**:
- Loop-L is bounded by the COMMUTATION loop (HS-source → SW-via-cluster → LS-drain → GND return). The loop CLOSES at the FET cluster, BEFORE any SW trace extends outward.
- Symmetric commutation loop-L requires symmetric FET cluster + via cluster + GND-return discipline (all 3 satisfied by G_PP22 + parametric placement + worker's minimal-set return-via per OQ-017).
- SW outward trace polyline mismatch produces different per-phase switching transient + per-phase EMI signature, but:
  * 3-phase BLDC is SEQUENTIAL (not paralleled) — no current-sharing concern
  * BEMF blanking tolerates per-phase switching transient delta
  * EMI compliance is measured CUMULATIVELY at integrate stage (CE/FCC envelope), not per-phase

**Trade-off avoided**: widening hs_fet_row_pitch from 13 → 15mm would cost ~12% board area + propagate to CH2/3/4 (re-placement, re-sim, re-route) for sub-percent EMI/sim gain. Physics doesn't require it.

**Cross-channel symmetry PRESERVED**: CH2/3/4 mirror_X/mirror_Y of CH1 still works (4× saving). Bigger win preserved.

**Binding gate update**: STEP 6 measured loop-L per phase is the R19 numerical proof. A=B=C to 4 decimals at FET-cluster commutation loop = R19 satisfied regardless of asymmetric outward routing.

**Memory**: [[feedback-r19-loop-vs-trace-symmetry]] saved so this isn't re-litigated.

**Status**: RESOLVED — worker proceeds with clean Freerouter base (option a per worker recommendation).

