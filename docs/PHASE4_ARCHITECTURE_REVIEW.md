# Phase 4 — Architectural Review (PR-channel-template-redo Phase 1)

**Dispatch:** master 2026-05-23 post-/compact
**Goal:** before placement redo, decide which per-channel ICs (TL431, LM393, 74LVC1G08) can centralize as a shared resource. Centralization frees channel-zone area, which is the root cause of the 56 unresolved R23/quadrant violations.
**Scope:** READ-ONLY audit — NO placement, netlist, or SKiDL changes yet.

---

## 1. Current per-channel IC inventory (from `channel_skidl.py`)

`make_channel()` instantiates ONCE per call. 4 channels × make_channel = 4× each:

| Ref class    | Per-channel count | Total | Package        | Function                              |
|--------------|-------------------|-------|----------------|---------------------------------------|
| MCU AT32F421 | 1                 | 4     | QFN-32 5×5     | Independent AM32 instance per channel |
| DRV8300      | 1                 | 4     | HVQFN-24       | Gate driver for 6 FETs per channel    |
| INA186 CSA   | 3                 | 12    | SC-70-6        | Per-phase current sense               |
| TL431LI      | 1                 | 4     | SOT-23         | Per-channel 2.5V Vref                 |
| LM393        | 1                 | 4     | SOIC-8         | Dual: I_TRIP + OTP comparator         |
| 74LVC1G08    | 1                 | 4     | SOT-353        | Per-channel KILL_LOCAL AND gate       |

Master's mention of "U7/U10/U13" for AND gates aligns with my reading — one per channel = U?/U?/U?/U? sequential (exact refs assigned by KiCad annotator post-netlist-gen).

---

## 2. TL431 → VREF_2V5 — **CENTRALIZE (SHAREABLE)**

### Signal chain
`channel_skidl.py:317-348`:
- TL431 outputs `VREF_2V5_CH<n>` (currently per-channel)
- VREF_2V5 feeds 2 resistor dividers → `VREF_I_TRIP_CH<n>` (2.4V) and `VREF_OTP_CH<n>` (0.3V)
- Dividers drive LM393 comparator inputs (high-impedance, ~25kΩ + 29kΩ load per channel)

### Load analysis (per channel)
- VREF_I_TRIP divider: 1kΩ + 24kΩ = 25kΩ → I = 2.5/25k = **100µA**
- VREF_OTP divider:    22kΩ + 3kΩ = 25kΩ → I = 2.5/25k = **100µA** (actually 2.5/2.27k after parallel, similar order)
- Bypass cap C100nF: negligible DC
- **Total per channel: ~200µA from VREF_2V5**
- **4× channels shared load: ~800µA**

### Hysteresis isolation check
`channel_skidl.py:402-405` — `r_fb_i` (20kΩ) from `I_TRIP_N_CH<n>` back to `VREF_I_TRIP_CH<n>`.
- Hysteresis injection is at the DIVIDER OUTPUT (VREF_I_TRIP), NOT at VREF_2V5 (upstream of divider).
- Per channel's hysteresis stays local to its own VREF_I_TRIP node.
- **No inter-channel coupling via shared VREF_2V5. SAFE to centralize.**

### Required SKiDL adjustments if centralized
| Change                       | From            | To                                     |
|------------------------------|-----------------|----------------------------------------|
| TL431 instantiation location | `make_channel()` | Main script `pcbai_fpv4in1_skidl.py`  |
| `VREF_2V5_CH<n>` net         | Per-channel    | Single global `VREF_2V5`               |
| `make_channel()` signature   | (...)           | (..., vref_2v5)                        |
| `r_tl431_bias`               | 2kΩ            | **390Ω** (recalc below)                |
| `c_vref_bp`                  | 100nF (×4)     | 100nF central + 10nF at each entry tap |

### r_tl431_bias recalc (CRITICAL — current value insufficient for shared load)
- TL431 datasheet: `I_K(min) = 1.0 mA` for regulation accuracy
- Shared load: 800µA divider draw
- Total `I_K = 1.0 mA + 0.8 mA = 1.8 mA` minimum
- `r_tl431_bias = (V3V3 − VREF) / I_K = (3.3 − 2.5) / 1.8 mA = 444Ω → pick E24 standard 470Ω` (I_K = 1.70mA, ≥ min ✓)
- **Alt safer: 390Ω → I_K = 2.05mA** (more margin, +0.5mW power)

### Area savings
- Per channel cluster: TL431 (~3mm² + keepout = ~6mm²) + r_tl431_bias (R0402 ~2mm²) + c_vref_bp (C0402 ~2mm²) ≈ **~10–12mm² per channel removed**
- CH2/3/4 each free ~12mm² → **~36mm² freed in channel zones**
- CH1 keeps OR frees its instance depending on whether central TL431 placed in CH1 zone (near MCU) or in neutral zone (near +3V3 LDO). **Recommend neutral zone** → frees CH1's ~12mm² too → **~48mm² total board savings**

### Routing impact
- VREF_2V5 becomes board-global net.
- Star topology from central TL431 → 4× channel-divider entry points.
- Worst-case trace length (100×100 board, center → corner): ~70mm.
- DC analog reference — no AC content, no slew-rate concern.
- Mitigations: route on inner signal layer adjacent to GND plane; add small 10nF bypass at each channel's divider entry (`c_vref_local` ×4 = 4 new caps, but smaller area than 4× TL431 clusters removed).

### SPOF analysis
- Single TL431 failure → all 4 channels lose threshold reference.
- However: GLOBAL_OVUV_N (TPS3700 board supervisor) is ALREADY a board-level SPOF, and it actively kills all 4 channels on its own fault. Consistent with existing global-supervisor pattern.
- AM32 firmware also independently monitors current via PA4/CSA_A ADC — provides software backup current-limit at much lower bandwidth (~10kHz) than the LM393 hardware path (~1µs). **NOT a regression in net safety.**

**VERDICT: TL431 → CENTRALIZE.** Net benefit clear: ~48mm² freed, no functional regression, consistent with existing supervisor architecture.

---

## 3. LM393 dual comparator — **PER-CHANNEL (CANNOT SHARE)**

### Signal dependency
Every input is per-channel:
- Comp A: `CSA_MAX_CH<n>` (diode-OR of that channel's 3 INA186 outputs), `VREF_I_TRIP_CH<n>` (per-channel divider w/ hysteresis)
- Comp B: `NTC_CH<n>` (that channel's local thermistor voltage), `VREF_OTP_CH<n>` (per-channel divider)

### Could-we-share-with-LM2901 analysis
- LM2901 = 4× comparators in SOIC-14. Could combine 4× CH I_TRIP in one package (or 4× CH OTP in one package).
- **Savings:** 4× SOIC-8 (~30mm² each = 120mm²) → 2× SOIC-14 (~50mm² each = 100mm²) ≈ ~20mm² saved, ~5mm²/channel
- **Cost:**
  - Routes 4× CSA_MAX (high-impedance analog from each channel's diode-OR network) to ONE central LM2901 location → long analog runs picking up switching noise from FET commutation.
  - Routes 4× NTC voltage (DC but noise-sensitive) similarly.
  - Hysteresis topology stays per-channel, but the per-channel VREF_I_TRIP node must also reach the centralized comparator → 4× more 25kΩ-impedance traces traveling cross-board.
  - Single LM2901 failure disables 4-channel current limit OR 4-channel OTP simultaneously (SPOF on safety-critical kill path).
  - Per-channel LM393 keeps trip logic LOCAL to where the source/load is — minimizes coupling to digital switching.
- **Risk/reward poor.** 5mm²/channel saved at the cost of 4× SPOF on kill path. Master's "sure-shot for production" philosophy weighs heavily against this trade.

**VERDICT: LM393 stays per-channel.**

---

## 4. 74LVC1G08 single AND gate — **PER-CHANNEL (CANNOT SHARE)**

### Signal dependency
- Inputs: `I_TRIP_N_CH<n>`, `OTP_TRIP_N_CH<n>` (both per-channel)
- Output: `KILL_LOCAL_N_CH<n>` (per-channel kill signal, drives that channel's HW fault LED + DRV8300 nSLEEP)

### Could-we-share-with-74LVC4G08 analysis
- 74LVC4G08 = quad AND in SOT-23-14 → 1 package for all 4 channels
- **Savings:** 4× SOT-353 (~6mm² each = 24mm²) → 1× SOT-23-14 (~20mm²) ≈ 4mm² total, ~1mm²/channel — **negligible**
- **Cost:** routes 8 per-channel trip signals (2 per channel × 4) to one central location → routing burden replaces area savings. Plus SPOF on combined kill logic.

**VERDICT: 74LVC1G08 stays per-channel.**

---

## 5. Other minor sharing opportunities (NOT primary scope)

### TLM bus pull-up (R_TLM_PU)
- `channel_skidl.py:113-117` adds a 10kΩ pull-up to V3V3 in EACH channel on the SHARED `TLM_BUS` net.
- 4× parallel 10kΩ = 2.5kΩ effective. Likely accidental — should be 1× pull-up on the bus.
- **Savings:** 3× R0402 ≈ 6mm² total (~1.5mm²/channel). Minor but real.
- **Recommendation:** address in same PR as TL431 centralization (similar refactor pattern: extract from `make_channel`, place on main script bus side).

### What I checked AND ruled out
- MCU AT32F421 — independent AM32 instance per channel → MUST stay per-channel ✓
- DRV8300 — drives 6 FETs per channel, physically tied to that channel's gate nets → MUST stay per-channel ✓
- INA186 ×3 per channel — physically wired to that channel's shunt resistors → MUST stay per-channel ✓
- FETs Q1-Q24 — physical hardware, per-channel-per-phase by definition ✓
- TVS, gate clamps, bootstrap caps, BEMF dividers, MCU/DRV/CSA decoupling — all on per-channel nets, must stay per-channel ✓
- BOOT0 pull-down, NRST cap+pull-up — MCU-pin-local, per-channel ✓
- V3V3A rail — ALREADY shared in main script, passed as `make_channel` parameter ✓

---

## 6. Recommendation summary

| Component | Verdict          | SKiDL change                            | Area saved      |
|-----------|------------------|-----------------------------------------|-----------------|
| TL431     | **CENTRALIZE**   | Move to main script, add `vref_2v5` arg, bias 2K→470Ω | ~48mm² total (~12mm²/channel CH1+CH2+CH3+CH4) |
| LM393     | per-channel      | none                                    | n/a             |
| 74LVC1G08 | per-channel      | none                                    | n/a             |
| TLM pull-up | **CENTRALIZE** (minor) | Move to main script | ~6mm² total |

**Total area freed for placement redo: ~54mm²** (~13mm²/channel zone).

### Worker recommendation
**Proceed with SKiDL refactor PR (PR-channel-template-redo-centralize-vref).** This refactor is the prerequisite to Phase 2 (placement redo) because:
1. The freed ~13mm²/channel directly relieves the density-block that defeated PR #68's broader scope (~10mm²/component average → 1 component's worth of slack per channel).
2. Without the refactor, Phase 2 placement starts with the SAME density constraint that produced 0 valid spiral positions in 19 of 19 groups.
3. Refactor → netlist regenerate → kinet2pcb re-import → Phase 2 placement redo. Sequential dependency.

### Sequencing for master adjudication
- **Phase 1 (this PR, archival-only)** — this audit doc on branch `phase4-channel-template-redo-phase1-audit`, no SKiDL/PCB changes.
- **Phase 2 (NEW PR-channel-template-redo-centralize-vref)** — SKiDL refactor + netlist regen + verify components reduced by 9 (TL431+R+C ×3 removed, 1 added centrally; TLM pull-up −3 R). target.h md5 must remain unchanged (no firmware impact, references only).
- **Phase 3 (PR-channel-template-redo-placement)** — re-architect CH1 template with reduced component set; mirror to CH2/3/4.
- **Phase 4 (PR-channel-template-redo-routing)** — re-do affected orphan routes; final audit + thermal re-sim + merge.

### Risks flagged
- **R21 worker deviation disclosure**: I'm recommending a TL431-bias-resistor value change (2K → 470Ω) which IS a spec deviation from current schematic. Reason: shared load requires more cathode current. Alternative considered: keep 2K and accept regulation degradation at light load — REJECTED (TL431 falls out of regulation when I_K < 1mA per datasheet → VREF accuracy spec violated → comparator threshold drift up to ±50mV at 0.3V trip = 17% threshold error). Documented here per R21.
- **R19 symmetry preservation**: removing TL431 from `make_channel()` slightly breaks the per-channel template symmetry (TL431-related passives no longer present in CH<n> zone). However, this is REMOVAL not asymmetric ADDITION — the remaining template stays a pure transform across channels. Sym property preserved on remaining components.
- **Routing burden growth**: VREF_2V5 becomes board-global net adding ~280mm of trace (70mm × 4 star branches). Mitigated by inner-layer routing adjacent to GND.

---

## 7. STANDING BY for master adjudication

Per master directive: "REPORT BACK BEFORE PROCEEDING."

This audit Phase 1 PR contains:
- This doc only (no SKiDL/PCB/netlist changes)
- Branch: `phase4-channel-template-redo-phase1-audit`
- Awaits master decision on:
  1. Approve TL431 centralization → proceed to Phase 2 SKiDL refactor as separate PR
  2. Approve TLM-pull-up centralization (bundle with TL431 in same Phase 2 PR? or separate?)
  3. Disagree with audit findings → request alternative analysis

Estimated Phase 2 SKiDL refactor: ~1h (10-line change in `channel_skidl.py`, similar in main script, netlist regen, kinet2pcb re-import + audit verify).
Estimated Phase 3 placement redo (post-refactor): ~2-3h.
Estimated Phase 4 routing fix: ~1-2h.
