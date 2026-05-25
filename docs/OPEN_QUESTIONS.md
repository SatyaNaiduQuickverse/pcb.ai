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
