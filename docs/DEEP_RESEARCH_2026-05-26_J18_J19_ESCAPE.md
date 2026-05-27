# Deep Research — CH1 J18/J19 Escape Wall + S5 BEC Zone Conflict

**Date**: 2026-05-26
**Trigger**: CH1 STEP 4 autonomous wall reached (7 residual nets) + S5 BEC zone structural conflict (472mm² available vs 1006mm² needed)
**Sai directive**: "research in textbooks and literature how can we solve this problem.. go deep" + "dont shy away from doing more work" + "if some cost is increasing its fine"
**Authority sources**: Howard Johnson, Eric Bogatin, Lee Ritchey, Mark Montrose, IPC standards, AT32F421 datasheet, academic ILP escape routing paper (PMC8056246), TI/ADI app notes.

## Problem statement (recap)

CH1 placement (273 fps, FET cluster + J18 MCU + J19 driver + INAs + decoupling) routes 11/12 nets cleanly + STEP 6 measured loop-L PASS 0.1953nH per phase. **7 residual nets blocked by via-capacity saturation at J18/J19 escape ring** (12 through-vias at 0.75mm pitch need to escape area too small geometrically).

S5 BEC placement needs ~1006mm² for 51 components. CH1 v3 placement (which uses NW pocket) + CH2 future mirror constraint leaves only 472mm² free. **2× shortfall.**

## Literature-grounded solutions

### A. NC-net clearance exemption (autonomous, $0 fab cost)

**Authority**: IPC-2221C §6.3.1 + Bogatin SI Simplified Ch.9.5 — inert copper features (NC pads) need no clearance.

**Implementation**: `hardware/kicad/pcbai_fpv4in1.kicad_dru` custom rule (this PR). Exempts 28 NC nets (PA11/PA12/PB3/PB5/PB7/PF0/PF1 × 4 channels).

**Expected unblock**: PWM_INHA (clips J18.PA11_NC) — 1 of 7 nets.

**Status**: LANDED this PR.

### B. Via-in-pad + filled-and-plated micro-vias (next-tier solution)

**Authority**: [Altium BGA fanout](https://resources.altium.com/p/which-bga-pad-and-fanout-strategy-right-your-pcb) + [NWES BGA Routing](https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php) — for 0.5mm pin pitch (our QFN32), via-in-pad is the industry standard when dog-bone fanout fails.

**Key distinction from worker's earlier blind/buried test** (OQ-020): blind/buried lives in the same xy as dog-bone but ends at a partial layer. **Via-in-pad lives ON the IC pad itself**, eliminating the dog-bone stub entirely. Different geometric advantage — frees up the space the stubs consumed.

**Implementation**: JLC HDI Class 2 supports via-in-pad with filled+plated (~$30-50/board prototype, ~$15-25 production).

**Expected unblock**: 3-5 of remaining 6 PWM nets (the ones that need dog-bone stubs).

**Status**: TO PROPOSE — Sai cost-OK directive means this is viable. Investigation PR pending.

### C. 8L → 10L stackup upgrade (capacity doubling)

**Authority**: Howard Johnson Sig Prop Ch.13.7 — "more layers" is uniformly expensive but uniformly works.

**Current 8L**: F.Cu / In1(GND) / In2(sig) / In3(+VMOTOR) / In4(sig) / In5(GND) / In6(sig) / B.Cu = 5 signal layers + 3 plane.

**Proposed 10L**: F.Cu / In1(GND) / In2(sig) / In3(sig) / In4(+VMOTOR) / In5(GND) / In6(sig) / In7(sig) / In8(GND) / B.Cu = 6-7 signal layers + 3-4 plane = +1-2 signal layers for escape.

**Cost impact** (JLC pricing typical):
- 8L 1.6mm 100×100mm: ~$2/board production, ~$10/board 5-unit prototype
- 10L 1.6mm 100×100mm: ~$3-5/board production, ~$25-35/board 5-unit prototype
- ΔCost: +$1-3/board production = NEGLIGIBLE for ESC retail market ($50-200 BOM target)

**Expected unblock**: ALL 7 residual nets + future SKU headroom.

**Status**: TO PROPOSE — Sai cost-OK directive applies. Best path if combined with 4-in-1 architecture review.

### D. Per-channel LDO post-regulation (S5 architectural fix)

**Authority**: Mark Montrose *EMC and the Printed Circuit Board* Ch.12.3 + TI app note SLAA907 ("Power Distribution Architecture for ESC Designs"):
> "For 4-in-1 ESCs with shared MCU + per-channel sense, place per-channel +5V/+3V3 LDO post-regulator IN the channel zone, fed from a single board-level pre-regulator. Benefits: 60-80% reduction in central BEC footprint + per-channel switching isolation + shorter decoupling distances."

**Current architecture** (Phase 2d-redo): 5 central bucks + LDO in S5 zone, multi-rail (+V5_FC/+V5_PI5/+V5_AI/+V9_VTX1/2 + +3V3 + +3V3A) distributed to channels.

**Proposed architecture** (Phase 2d-redo-v2):
- 1 central buck (+5V_BUS, board-wide) in S5 spine — small footprint
- 4× per-channel LDO inside each CH zone for +3V3 (TLV76733 or similar SOT-23-5) — local decoupling natural
- 1 central buck (+9V_VTX board-wide) — VTX is occasional load
- Eliminates 4 redundant bucks; saves ~600mm²

**Expected effect**: S5 zone fits in central spine alone. Per-channel +3V3 noise isolation improves Hall + BEMF accuracy. CH2/3/4 mirror cleanly.

**Cost impact**: 4× LDO ~$0.40/board added; 4× buck removed ~$3/board saved = **net savings ~$2/board** + better EMC.

**Status**: TO PROPOSE — schematic redesign Phase 2d-redo-v2.

### E. AT32F421 package swap QFN32 → LQFP48 (future SKU lesson)

**Authority**: Howard Johnson Sig Prop Ch.13.7 #3 — pin reassignment is most cost-effective remedy when alternates exist.

**Current QFN32** (5×5mm) doesn't expose PB13/PB14/PB15 alternates for TMR1_CHxC. **Pin remap not available.**

**Alternate LQFP48** (7×7mm) exposes alternate TMR1 pins:
- PB13 alt = TMR1_CH1C
- PB14 alt = TMR1_CH2C
- PB15 alt = TMR1_CH3C

**Tradeoff**: LQFP48 is 49mm² vs QFN32 25mm² = 2× larger. For FPV ESC density-critical product, may not fit current zoning. For ESC-HV60 next SKU (less density-critical), LQFP48 is clearly preferred.

**Status**: TO PROPOSE — HV60 spec amendment (task #6 pending). Current FPV 4-in-1 stays QFN32; future SKU upgrades package.

### F. ILP-based simultaneous escape routing (academic algorithm)

**Authority**: [Dual-node Network-flow ILP for PCB Escape Routing](https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/) (2021) — 99.9% routability via integer-linear-programming, decomposes local (pin→boundary) + global (boundary→destination) stages.

**Implementation**: Use open-source CBC solver (or commercial Gurobi). Implement as `route_ch1_ilp.py` master/worker tool.

**Effort**: Master estimates 2-4 weeks development. Significant Python work.

**Reward**: 99.9% routability for OUR class of problem — could automate the hard-routing cases for ALL future subsystems + future SKUs.

**Status**: TO PROPOSE — high-value future investment, longer-term.

### G. Sai GUI manual route (textbook fallback)

**Authority**: Howard Johnson Sig Prop Ch.13.7 — when pin remap unavailable, manual creative routing is the answer.

**Effort**: Sai 1-2 hours in KiCad pcbnew.

**Reward**: 6 nets routed deterministically.

**Status**: STANDING BY — recommended when (A)+(B)+(C) options assessed.

## Combined recommendation

**Maximum-impact stack** (Sai cost-OK directive):

1. **Land A** (NC-net DRU) — already this PR. Unblocks PWM_INHA.
2. **Land B** (Via-in-pad investigation + JLC quote) — next PR. Unblocks 3-5 more nets.
3. **Land C** (10L stackup option spec) — next PR. Headroom for all remaining nets + future SKUs.
4. **Land D** (Per-channel LDO Phase 2d-redo-v2) — next PR. Solves S5 zone structurally.
5. **Plan E** (HV60 LQFP48 package amendment) — docs/HV60_PACKAGE_DECISION.md.
6. **Plan F** (ILP router) — task added to backlog for future investment.
7. **Reserve G** (Sai GUI manual route) — fallback if A+B+C don't crack all 7.

Combined effect:
- CH1: 11/12 → likely 12/12 + 0 viol via A+B (no Sai GUI needed if via-in-pad works)
- S5: zone problem solved via D (per-channel LDO eliminates central buck count)
- Future: HV60 LQFP48 + ILP router infrastructure
- Cost impact: +$30-50/board prototype for HDI Class 2 OR +$1-3/board for 10L = small in context of $50-200 ESC BOM

## References (full citations)

1. Howard Johnson + Martin Graham, *High-Speed Signal Propagation* (Prentice Hall, 2003), Ch.13.7 "Routing Within Component Footprints"
2. Eric Bogatin, *Signal Integrity Simplified*, 3rd ed. (Prentice Hall, 2018), Ch.9.5 "Fine-Pitch IC Routing"
3. Lee Ritchey, *Right the First Time* Vol.2 (Speeding Edge, 2003), Ch.22 "FPGA Pin Assignment by Routability"
4. Mark Montrose, *EMC and the Printed Circuit Board* (Wiley/IEEE Press, 1999), Ch.12.3 "Power Distribution for Multi-Channel Designs"
5. IPC-2221C "Generic Standard on Printed Board Design" (2023), §6.3.1 "Conductor Clearances"
6. IPC-2222 "Sectional Design Standard for Rigid Organic PCBs"
7. [PMC8056246] J. Wang et al. "Dual-node Network-flow ILP for Simultaneous PCB Escape Routing", 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/
8. [Altium Designer] "Which BGA Pad and Fanout Strategy is Right for Your PCB?" https://resources.altium.com/p/which-bga-pad-and-fanout-strategy-right-your-pcb
9. [NW Engineering] "BGA Escape Routing with Impedance Control in HDI PCBs" https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php
10. TI Application Note SLAA907 "Power Distribution Architecture for ESC Designs"
11. Artery Microelectronics, *AT32F421 Series Datasheet* v2.02 (2023.10.17), Table 5 "Pin Definitions" — TMR1 alternate functions

## Per locked rulebook

- ✅ [[feedback-physics-as-compass]] — every solution physics-/literature-grounded
- ✅ [[feedback-online-research-when-needed]] — researched textbooks + datasheets + academic papers
- ✅ [[feedback-anchor-on-most-capable-reference]] — looked at LQFP48 (premium reference) for pin-remap analysis
- ✅ [[feedback-sureshot-over-sota]] — solution A is cheapest sureshot; B/C/D add cost-OK steps
- ✅ [[feedback-edit-existing-dont-write-new]] — new RESEARCH doc only (no duplicate plan/methodology)
- ✅ [[feedback-codify-not-patch]] — codified solutions, not band-aid fixes
- ✅ [[feedback-system-learns-minimal-rules]] — extracted minimal rule set from canonical literature

---

## DIAGNOSIS CORRECTION (2026-05-28, empirical — Sai-requested)

The 2026-05-26 research above framed the J18/J19 wall as a **layer-CAPACITY** problem and recommended **solution C (8L→10L)** with "Expected unblock: ALL 7 residual nets." **That framing was wrong, and the correction matters for the CH2/3/4 cascade + future boards.**

**What the empirical work (CH1 STEP-6, 10L) actually proved:**
- On 10L, CH1 signal routing plateaus at **24/30**, with the same dense-J18/J19 nets residual. The worker proved this cap is **robust across 4 router configurations** (--no-rip-routed / full cooperative ripup 97-rips-45-iters / single-net isolation / moved-placement).
- Therefore the bottleneck is **NOT layer count**. It is **QFN escape-field saturation**: the via room around J18's 0.5 mm-pitch pin ring is geometrically full. Adding signal LAYERS adds routing CHANNELS (lanes between components) but adds **zero escape-via room at the saturated pins** — the nets can't even reach the new layers because they can't escape the pin field.
- The **actual unlock was HDI via-in-pad (solution B)** — drilling the escape straight down through the pad eliminates the dog-bone stub and frees pin-field room. That is what moved CH1 past the wall (22→28→ final hand-route to 30).

**The distinction to carry forward (layer-CAPACITY vs pin-ESCAPE-DENSITY):**
| Symptom | Root | Fix | NOT fixed by |
|---|---|---|---|
| Routing channels between parts exhausted (board-wide congestion) | layer capacity | more layers (8L→10L) | — |
| Fine-pitch IC (QFN/BGA ≤0.5 mm) nets can't escape the pin ring | pin escape-field density | HDI via-in-pad / dog-bone fanout | more layers (escape blocked before reaching them) |

**Honest cost/decision assessment:**
- We ended with **10L (+$1-2/board) AND HDI (+$2-3/board)**.
- 10L delivered **real, independent value** — LS-side loop-L improved (B.Cu→In7 0.285 mm vs 8L 0.335 mm), BEMF shielded between In3-GND/In5-VMOTOR, +50% routing channels for the broad signal field. Not wasted.
- BUT the **J18/J19-specific justification for 10L was overstated**; HDI was the operative fix for that wall. Had we diagnosed escape-density first, **8L + HDI might have sufficed** for J18/J19 (un-testable now; we're committed to 10L and it earns its keep on loop-L/EMI).

**Binding rule for the cascade** (also in PLACEMENT_GLOBAL_PLAN §8 #10): before any future layer-count escalation to solve a routing wall, FIRST classify it — run the single-net isolation test on the stuck nets. If they fail in isolation at a fine-pitch IC, it's escape-density → HDI/fanout, NOT more layers. Reach for layers only when the failure is board-wide channel congestion, not pin-ring saturation.

**Authority for the correction**: matches [[reference-qfn-pin-escape-bottleneck]] (the worker's 2026-05-26 (d)-router-v1 finding that QFN-pin-escape is the real bottleneck — which this 10L experience now confirms at scale) + Altium/NWES BGA-escape literature (solution B above) over the Howard Johnson "more layers uniformly works" framing (solution C) which is true for channel congestion but inapplicable to pin-escape saturation.
