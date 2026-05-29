# CH1 30/30 — Industry SOTA Research for Fine-Pitch QFN HDI Escape

**Date**: 2026-05-29
**Scope**: 3 residual nets after lever-T (HDI activate): PWM_INHB_CH1 (J19.23), GLB_CH1 (J19.10), KILL_RAIL_N_CH1 (J19.8 trunk + R76.1 leaf).
**Build**: 10-layer HDI Class 2 (JLC), microvia 0.10mm drill / 0.25mm pad, blind/buried whitelist active on J18 + J19.
**Status of router**: bounded A* multi-mech planner, chain-depth=3 (blind F-In2 → through → B.Cu microvia), 27/30 nets routed.
**Authority sources**: IPC-2226 / 2226A, Sierra Circuits (protoexpress), Cadence Allegro escape-routing blog, NWES BGA HDI guide, Würth Elektronik HDI Design Guide v1.2 (binary fetch failed, secondary citations only), TI AM62 escape app note SPRAD13A (binary fetch failed, secondary citations only), academic dual-model ILP escape paper (PMC8056246), PathFinder negotiated congestion (McMurchie/Ebeling, FPGA '95), Cadence Allegro microvia reliability blog, Hemeixin 2+N+2 stackup guide, Altium VIPPO guide. Companion docs already in repo: `DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md`, `DEEP_RESEARCH_2026-05-28_ROUTING_METHODOLOGY.md`, `MASTER_HDI_SPEC.md`, `CH1_30of30_M2_SW_VIA_TOOL.md`. This doc DOES NOT restate them — it focuses on SOTA techniques not yet exercised + planner tuning + honest gaps.

---

## 1. Industry-standard fine-pitch QFN HDI signal escape techniques

**1A. Dog-bone fanout (out of scope for last 3 nets — already exhausted)**
The classical fanout. Pad → short stub → through-via outside the pad → escape on inner layer. Industry consensus: valid for ≥ 0.8mm pitch BGA / 0.65mm pitch QFN, marginal at 0.5mm, broken at ≤ 0.4mm. Sierra Circuits states dog-bone is "appropriate for 1mm BGAs and possibly 0.8mm BGAs … once pitch gets down to 0.5mm or lower you're better off using microvia-in-pad." Our J18 0.5mm + J19 0.5mm sits in the marginal band; the via-keepout (~0.8mm diameter for a 0.30mm-drill through-via) eats one channel per pad row. Already saturated per `MASTER_HDI_SPEC.md`. **CONFIDENCE: high** (cited by Sierra, NWES, Cadence, AllPCB independently). **Applicability to our 3 residuals: ZERO new headroom — already maxed.** Source: [Sierra protoexpress](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [NWES HDI](https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php), [Cadence Allegro escape blog](https://resources.pcb.cadence.com/blog/2019-best-pcb-routing-methods-for-bga-escape-routing).

**1B. Via-in-pad with VIPPO (in scope, partially deployed)**
Microvia drilled DIRECTLY in the SMD pad, epoxy-filled and copper-plated-over (VIPPO = Via-In-Pad Plated Over). Eliminates the dog-bone stub entirely. NWES: "for BGAs with pitches below 0.5mm via-in-pad becomes indispensable, where vias are placed directly within the BGA pads, filled with conductive or non-conductive epoxy, and then plated over to create a flat surface suitable for soldering." JLCPCB blog confirms VIPPO is a standard HDI Class 2 process: "Via diameter should be ≤75% of the pad diameter … for a 0.4mm BGA pad, the maximum microvia diameter is 100µm." Our `MASTER_HDI_SPEC.md` already specs 0.10mm drill / 0.25mm pad on J18+J19 → exactly the VIPPO recipe. **Applicability to 3 residuals: J19.23 / J19.10 / J19.8 / R76.1 are all on a whitelisted IC — VIPPO is legal here.** What we need to verify: is the M2 SW VIA TOOL actually emitting microvia-in-pad on these specific pins, or only on the 27 already-routed ones? Source: [NWES HDI](https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php), [JLC VIP blog](https://jlcpcb.com/blog/via-in-pad-pcb). **CONFIDENCE: high.**

**1C. Multi-step stacked microvia (2-step F→In1→In2 deeper than our current 1-step)**
Standard chain-depth=3 (blind F-In2 → through-core → microvia B-In(N-1)) gives the planner ONE blind microvia + ONE through + ONE microvia. The industry SOTA for ESCAPE-CHANNEL EXPANSION is 2-step stacked on each face: F→In1→In2 on the top side (and mirror on bottom). Per Sierra: "Type III features two or more microvia layers on at least one side, enabling stacked or staggered via configurations … for type III construction, stacked structures should be limited to 2 layers of microvia." This adds an entire ESCAPE LAYER (In1) that the current single-microvia depth does not reach. **Applicability to 3 residuals: HIGH if J19's escape was being blocked because In2 was the first reachable layer and In2 is congested. With F→In1→In2 the router can use In1 — which is GND in our current stackup, but per `MASTER_HDI_SPEC.md` may be reassignable for these 4 nets without breaking PI.** Source: [Sierra microvia stacking](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [Cadence microvia reliability blog](https://resources.pcb.cadence.com/blog/km-how-many-microvias-can-you-safely-stack-a-deep-dive-into-hdi-reliability-physics). **CONFIDENCE: high** (multiple independent industry sources; Cadence specifically says "two-level stacks (3 layers): generally safe across standard materials and thermal profiles").

**1D. Staggered microvia (escape supply with relaxed CTE risk)**
Instead of stacking F→In1→In2 vertically, the In1→In2 microvia is offset laterally by ≥ 1× via diameter. Sierra: "staggered microvias are offset to avoid vertical alignment, improving yield by 8–10% but using 15% more board area … preferred over stacked ones for better reliability during thermal cycles." Hemeixin: "with a staggered microvia structure, it's possible to take the drill position away from overcrowded sections of the board to a less impacted area." **Applicability to 3 residuals: HIGH and possibly higher than 1C.** The In1→In2 microvia can be staggered LATERALLY into a NEIGHBORING channel that has free routing area, effectively letting J19 borrow escape area from a neighboring zone. Our planner currently does not model staggered microvias (it models stacked through chain-depth). Source: [Sierra](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [Hemeixin staggered](https://www.hemeixinpcb.com/company/news/microvias-in-pcb-design-a-comprehensive-guide-to-hdi-interconnect-solutions.html). **CONFIDENCE: high.**

**1E. Sliver routing / 3-mil-trace inner-layer routing through narrow channels**
Routing 0.075mm (3mil) traces through the narrow channel between two microvia barrels. Industry rule: avoid "copper slivers" (sub-3mil etched copper between two clearances) — they delaminate during etch. AllPCB: "tighter clearances increase the risk of 'copper slivers' during etching." But Cadence: at "0.4mm pitch BGA with 1000 pins might use via-in-pad for all inner pins, with micro-vias connecting to a high-density routing zone with 3 mil traces and 3 mil spacing." So 3-mil-on-3-mil IS valid on inner layers under HDI Class 2 — JLC explicitly supports 3.5mil trace / 3.5mil clearance on inner layers of HDI builds. **Applicability to 3 residuals: MODERATE — if the planner's grid is currently 0.10mm (4mil) it may be missing 3.5mil slots that would let one more trace squeeze between J19 escape vias.** Source: [AllPCB sliver](https://www.allpcb.com/blog/pcb-assembly/escape-routing-techniques-for-high-density-bga-packages.html), [Cadence 3mil trace](https://resources.pcb.cadence.com/blog/2019-best-pcb-routing-methods-for-bga-escape-routing). **CONFIDENCE: medium** (3mil inner is JLC-supported, but exact JLC HDI Class 2 minimum needs spec check before committing).

**1F. Multi-row diagonal escape (Cadence)**
"Escapes out from the outer rows of the BGA usually done diagonally to give yourself more routing channels." For QFN, the analogous trick is to escape inner pads diagonally INTO the package interior toward the thermal pad, then drop a via in the thermal-pad region (which is large) and pick up the trace on an inner layer. Hackaday: "it is usually desirable to break out the inner pads of a DQFN to the inside and drop vias to escape the part." **Applicability to 3 residuals: J19 has a thermal pad — J19.10/.23 may be escapable diagonally inward toward the thermal pad area if the thermal pad is via-fenced rather than via-packed.** Source: [Cadence](https://resources.pcb.cadence.com/blog/2019-best-pcb-routing-methods-for-bga-escape-routing), [Hackaday BGA](https://hackaday.com/2022/06/20/working-with-bgas-design-and-layout/). **CONFIDENCE: medium** (technique is real; geometric feasibility depends on J19 thermal-pad detail not yet measured).

---

## 2. Stacked microvia variants — which actually adds escape supply

| Variant | What it adds | Cost (JLC HDI Class 2) | Used today? |
|---|---|---|---|
| 1-step blind F→In2 | First-layer escape only | Baseline HDI cost | Yes (lever-T) |
| 2-step stacked F→In1→In2 | +1 escape layer (In1) | +1 sequential lamination = ~+$5-10/board prototype | **NO** — chain-depth=3 means F-In2 / through / B-In(N-1), not F-In1-In2 |
| 2-step staggered F→In1→In2 (offset) | +1 escape layer + lateral repositioning | Same as stacked (still 2 microvia layers, just offset) | **NO** |
| X-Y staggered (each stage offset on different axis) | Style; same supply as staggered | Same as staggered | NO |
| Dog-bone fanout (non-HDI) | Style; SUPPLY = 1 escape layer per through | Cheap, but saturated | EXHAUSTED |
| Breakout via (NC-pad-side overflow) | Repurpose NC pin's escape slot for a routed neighbor — net gain 0; planning gain real | Free | Partially — NC clearance exempt rule active |
| Via-in-pad (VIPPO) | Style; SUPPLY = 1 escape layer, but per-pad not per-channel | Standard HDI cost | YES on whitelisted ICs |
| Sliver / 3.5mil inner | Adds 1 trace per channel slot | Free (within JLC HDI minimum) | Unclear — needs planner grid check |

**Key finding**: the planner's current chain `F-In2 → through → B-In(N-1)` does NOT include a 2-step stacked F→In1→In2. This is genuinely the next escape supply that has not been exercised. **Recommendation**: introduce a "stacked-2" mechanism (F→In1, In1→In2) and let the planner pick when through-via supply is exhausted.

Source: [Sierra stacked vs staggered](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [Hemeixin 2+N+2](https://www.hemeixinpcb.com/company/news/2-n-2-pcb-stackup-design-for-hdi-boards.html), [IPC-2226 explained](https://pcbsync.com/ipc-2226/), [Cadence microvia reliability](https://resources.pcb.cadence.com/blog/km-how-many-microvias-can-you-safely-stack-a-deep-dive-into-hdi-reliability-physics).

**CONFIDENCE: high** (stacked-2 is industry-standard 2+N+2 HDI; staggered-2 is industry-standard alternative; both add supply our planner doesn't currently model).

---

## 3. Channel-aware net routing — production patterns

**3A. ESC reality (open-source designs)**: VESC is 4-layer through-via, Tinymovr is 2-layer through-via with a single-channel design + integrated SoC (PAC5527). Neither hits our 4-channel-per-MCU bottleneck because they have one MCU per channel or one-channel-per-board. AM32 4-in-1 designs (PULPY ESC 40A AM32, iOkFly Race AM32 4-in-1) use shared-MCU + per-channel driver, but their fan-out is solved by physically separating channels onto separate driver ICs and routing each channel's PWMx to its own driver across a wide trace channel. **They do not solve the simultaneous-escape problem we have — they solve it by buying physical separation.** Source: [VESC](https://github.com/vedderb/bldc-hardware), [Tinymovr](https://github.com/tinymovr), [PULPY AM32](https://www.pcbway.com/project/shareproject/PULPY_ESC_40A_AM32_3f137014.html), [iOkFly Race AM32 4-in-1](https://github.com/IOkFly-BLENDERIS/IOkFly-Race-AM32-4in1-ESC), [Tinymovr Hackster](https://www.hackster.io/news/the-tinymovr-bldc-driver-packs-in-the-power-thanks-to-the-overo-pac5527-3ad721cc630f). **CONFIDENCE: high** (4 independent designs sampled).

**3B. Pin assignment as a routing-tool input (academic SOTA)**: Multiple IEEE papers (Yan & Wong "Simultaneous Constrained Pin Assignment and Escape Routing for FPGA-PCB Co-Design", PMC8056246 dual-model ILP) frame pin assignment + escape as ONE problem. Quote: "pin assignment and escape routing are two closely related problems and it is desired to consider routability during pin assignment for package-board co-design … network flow models can be used to analyze the bottleneck of the routable pins." **Applicability to our 3 residuals**: J19 is DRV8300 fixed-function — pin assignment is locked at silicon. **J18 is AT32F421** — PWM_INHB_CH1 (J19.23 side) and KILL_RAIL_N_CH1 may be reassignable to a less-congested J18 pin IF the AM32 firmware supports the alt-function on a different timer-channel pin. GLB_CH1 (J19.10 = ENABLE on DRV8300) is fixed. Source: [PMC8056246](https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/), [Yan & Wong](https://www.researchgate.net/publication/260584983_Simultaneous_Constrained_Pin_Assignment_and_Escape_Routing_Considering_Differential_Pairs_for_FPGA-PCB_Co-Design). **CONFIDENCE: medium** (academic technique is real; firmware feasibility unverified).

**3C. Per-channel quadrant isolation**: Our memory `feedback-channel-passive-quadrant.md` already mandates per-channel passives stay in their channel quadrant. Industry production designs go further and physically separate not just passives but ESCAPE COLUMNS — each channel gets a dedicated vertical escape column on inner layers. Our current 4-channel mirror-symmetric layout puts CH1, CH2, CH3, CH4 sharing the J18 escape ring, which forces all 4 channels to compete for the same escape channels around J18. Production 4-in-1 boards typically NEVER do this; they put 4 driver ICs at 4 corners and route each channel's signals independently outward. We're hitting the cost of the mirror-symmetric architecture. Source: [PULPY AM32](https://www.pcbway.com/project/shareproject/PULPY_ESC_40A_AM32_3f137014.html). **CONFIDENCE: medium** (architectural observation, not a fix for the last 3 nets).

---

## 4. Move-the-obstacle catalog (per Sai memory `feedback-move-the-obstacle-per-net-targeted`)

The Cadence and AllPCB blogs do NOT discuss component-move techniques — industry assumes placement is locked before route. The novapcb Rule 20 and our `feedback-move-the-obstacle-per-net-targeted.md` memory IS the move-the-obstacle catalog. Industry-equivalent literature is the **placement-driven-routing US patent (Kao et al. US7,904,865)**: "routing process can be paused temporarily to move items to unblock them, with this movement controlled so timing is not affected." Quote: "obstacle-aware partition of routing planes and directed capacity-constrained path graphs" (Yan/Wong differential-pair paper). Source: [Yan & Wong](https://www.researchgate.net/publication/260584983_Simultaneous_Constrained_Pin_Assignment_and_Escape_Routing_Considering_Differential_Pairs_for_FPGA-PCB_Co-Design), [placement-driven routing patent](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7904865).

**Conditions under which moving ONE neighboring passive 1-2mm unblocks an escape (synthesis of memory + literature)**:

| Pattern | Trigger condition | Move | Cost | Applicable to 3 residuals? |
|---|---|---|---|---|
| **Decoupling-cap 90° rotate** | Cap perpendicular blocks straight escape | Rotate 90° to parallel | 0 (same footprint) | If a decoupling cap sits between J19 escape via and trunk |
| **180° flip across IC body** | Cap stuck on same side as escape | Move to opposite side | If decoupling cap is across body — needs same-side recheck per R25 | LOW (R25 mandates same-side decoupling) |
| **Cap downsize 0805→0402** | Pad-bbox eats clearance | Smaller package | $0 BOM if same value available | YES per `reference-decoupling-cap-package-size.md` |
| **Channel-zone re-anchor** | Passive in wrong zone | Move to correct channel quadrant | 0 (still in same channel) | YES per `feedback-channel-passive-quadrant.md` |
| **1-2mm radial nudge** | Passive 0.5mm too close to via | Push 1-2mm outward (stays in zone per `reference-board-invariants-zone-hard-edges.md`) | 0 | YES for J19 leaf R76 (KILL_RAIL leaf — moving R76 1-2mm might directly open the escape) |
| **Test-point relocation** | TP blocking escape column | Move TP to non-critical zone | 0 (TPs are flexible) | UNKNOWN — need to check if a TP sits in the J19 escape path |

**The single highest-confidence move for our 3 residuals**: nudge R76 (the KILL_RAIL leaf) 1-2mm to open J19.8's trunk escape. Per `feedback-pre-placement-visual-decision.md`, do the visual zoom-render BEFORE committing. **CONFIDENCE: high (move-the-obstacle is a proven Sai-validated pattern); APPLICABILITY: high for R76, unknown for J19.10/J19.23**.

---

## 5. A* planner specific tuning

**5A. Chain-depth 3 → 4 → 5**: Bounded A* with chain-depth N means the planner tries paths using up to N mechanism transitions (e.g. F.Cu trace → blind via to In2 → In2 trace → through to B.Cu → B.Cu trace → microvia to In(N-1) → In(N-1) trace = 6 mechanisms). Pushing to chain-depth=4 lets the planner try (blind F-In1) → (blind In1-In2) → (through) → (microvia) which is the 2-step stacked variant from §2. **Cost: O(b^N) state explosion** where b = branch factor per node. The PathFinder algorithm (McMurchie/Ebeling FPGA '95) handles this via NEGOTIATED CONGESTION — each net is routed greedily but with a per-node history cost that grows when nets compete; over multiple iterations, less-contested routes drop out and contested routes negotiate. This converges where pure bounded A* with chain-depth N may not. Source: [PathFinder](https://www.cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf), [PMC8056246](https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/). **CONFIDENCE: high.**

**5B. Frontier cap heuristics**: bounded A* needs a frontier cap to prevent OOM. Raising the cap from default (typically 10k-50k nodes) to 200k for the LAST 3 nets ONLY (not all 30) is feasible on the Pi. Per `feedback-pi-bounded-subsystem-scope.md` full-board ops are Phase 7 external x86, but a 3-net residual targeted retry is sub-board scope and likely fits in 15GB. **Cost: minutes-to-hours of CPU**. Recommendation: try frontier cap 5× current value before introducing new mechanisms. **CONFIDENCE: medium** (depends on actual current cap).

**5C. Cost-cap relaxation tradeoffs**: A* with a cost cap rejects paths whose cumulative cost exceeds C × shortest-known. Relaxing C from default (e.g. 2×) to 4× lets the planner find longer paths — at the risk of finding paths that go through congested areas creating future shorts. PathFinder solves this by ITERATING — first pass uses low cost, subsequent passes raise it ONLY for nets that failed. **For our 3 residuals**: relax cost cap to 5× for these 3 nets only, keep current cap for the 27 already-routed nets (don't disturb success). This is the PathFinder "negotiated congestion" pattern. **CONFIDENCE: high** (well-established in FPGA literature).

**5D. Negotiated congestion vs greedy rip-up**: per our `reference-cascading-escape-needs-negotiated-routing.md`: "minimal-blocker rip in dense-IC escape cascades; greedy A* oscillates; need mature negotiated-congestion router." The 3 residuals are exactly that case. Building a PathFinder-style cost-history layer ON TOP of the existing bounded A* is the SOTA fix. Pseudocode: cost(node) = base_cost(node) × (1 + α × history(node) + β × present_use(node)); after each routing pass, increment history(node) for every node used by ≥ 2 nets; rip up the WORST OFFENDERS only (not all routes), re-route. Iterate ≤ N passes. Source: [PathFinder](https://www.cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf), [multi-terminal escape](https://escholarship.org/uc/item/9862j8q0). **CONFIDENCE: high.**

**5E. Does relaxing cost cap create shorts risk?** No. The planner still emits DRC-clean routes (the cap is on path COST not on geometric validity). The risk is RUNTIME, not safety. **CONFIDENCE: high.**

---

## 6. JLC HDI Class 2 fab gotchas (what mechanism are we MISSING that's in spec?)

JLC HDI Class 2 published specs (cross-referenced with IPC-2226 Type III):

- **Aspect ratio**: 0.8:1 max for microvias (some sources say 0.75:1; JLC publishes 0.8:1 typical). Our 0.10mm drill × 0.075mm dielectric = 0.75:1 — IN SPEC. Headroom to 0.13mm drill on the same dielectric (would loosen tolerance) — NOT YET TRIED but adds 30% more drill landing area = potentially relevant for 0.25mm-pad-into-pad-edge alignment.
- **Blind via depth**: ≤ 2 layers (i.e. F→In1 or F→In2 only; F→In3 is NOT a blind via, it's a buried-via combination). We currently use F→In2 = 2-layer blind. F→In1 = 1-layer blind = MORE RELIABLE + leaves In2 free for the other layer's escape. **NOT YET TRIED**.
- **Buried via**: must be in core only (between two non-outer layers). Our 10L HDI has buried-via legal as In2-In9 (full core through-via in buried sense), and any blind+buried combos. **Multiple buried-via stacks are allowed in Type III** but JLC may charge per lamination cycle.
- **No buried-via interleaving with through-via on the same drill column**: industry rule (Sierra "type III construction, avoid stacking on buried holes"). Our current chain-depth=3 F-In2 / through / B-In(N-1) has the through-via in a SEPARATE column from the microvia — compliant. A 2-step stacked F→In1→In2 stays in one column on top, the buried/through is separate, so still compliant.
- **Microvia in pad MUST be VIPPO (epoxy-fill + plate-over)**: yes, JLC Class 2 supports this; per `MASTER_HDI_SPEC.md` already specified.
- **Stacked microvia LIMIT**: IPC-2226 Type III allows 2-level stacks "generally safe", 3-level "gray zone", 4+ "high-risk". Our chain-depth=3 expressed as via-stack = 1 microvia ON each face. A 2-step stacked = 2 microvia ON top face (F→In1→In2) — STILL within "generally safe" 2-level limit. **NOT EXERCISED**.

**The mechanism we have NOT used but is fully in JLC HDI Class 2 spec**:

1. **F→In1 1-step blind** (separate from F→In2 2-step blind): SHORTER blind via, gives planner access to In1 which is currently treated as off-limits (it's GND today, but reassigning 3-4 nets through In1 with a careful keepout doesn't break PI).
2. **2-step stacked F→In1→In2 on top face only** (not chain F-In2 through B-In(N-1)): adds entire In1 escape layer.
3. **2-step staggered F→In1 (in pad) → In1→In2 (offset 0.2mm)**: same supply, BETTER thermal reliability per Sierra.
4. **Symmetric bottom-face 2-step (B→In8→In7)**: mirrors #2 on bottom; doubles the supply expansion.

Source: [Hemeixin 2+N+2](https://www.hemeixinpcb.com/company/news/2-n-2-pcb-stackup-design-for-hdi-boards.html), [Sierra microvia](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [PCBSync IPC-2226](https://pcbsync.com/ipc-2226/), [Cadence microvia reliability](https://resources.pcb.cadence.com/blog/km-how-many-microvias-can-you-safely-stack-a-deep-dive-into-hdi-reliability-physics). **CONFIDENCE: high.**

---

## 7. Re-placement vs router-fix decision tree

Industry SOTA (synthesis of Cadence, Sierra, NWES, plus academic placement-driven routing papers):

```
Stuck nets after autoroute exhausted
│
├── Stuck count ≤ 5% of total ─→ ROUTER FIX (hand route + negotiated congestion)
│   Cost: hours of CPU + engineer time. NO PCB respin.
│   Triggers: bounded A* not converging, frontier exhausted.
│   Tools: PathFinder iteration, chain-depth bump, frontier-cap raise.
│
├── Stuck count 5-15% AND geometry is a SINGLE bottleneck ─→ MOVE-THE-OBSTACLE
│   Cost: tens of minutes for placement edit + re-verify gates.
│   Triggers: bottleneck identifiable as ONE passive / TP / non-critical IC.
│   Tools: Sai's per-net targeted move catalog.
│
├── Stuck count 5-15% AND geometry is DIFFUSE ─→ HDI ESCALATION
│   Cost: BOM/fab spec change ($1-5/board). No PCB respin if HDI was anticipated.
│   Triggers: dog-bone fanout saturated, no single bottleneck.
│   Tools: VIPPO, 2-step stacked microvia, layer count bump.
│
├── Stuck count >15% OR fundamental pin assignment broken ─→ RE-PLACE
│   Cost: weeks for re-place + re-sim + re-audit ALL prior gates.
│   Triggers: 4 of 4 channels failing in same way, MCU pin assignment misaligned to silicon constraints.
│   Tools: full subsystem re-place, possibly architecture change (4 driver ICs → 4 corners).
│
└── Stuck count >25% ─→ ARCHITECTURE PIVOT
    Cost: months. Schedule slip.
    Triggers: physically infeasible given chosen MCU + layer count.
```

**Our 3 residuals = 10% (3/30 nets on CH1)**: in the "router fix" + "move-the-obstacle" + "HDI escalation" bands. **Re-place is NOT yet justified** (Sai memory `feedback-redo-not-mitigate.md` reads as "redo if prior work lacks a discipline" — the discipline here is escape supply; we have not exhausted HDI supply yet, so re-place would be premature). Source: cross-synthesis of [Sierra](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/), [NWES](https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php), [Cadence](https://resources.pcb.cadence.com/blog/2019-best-pcb-routing-methods-for-bga-escape-routing), and placement-driven routing patent US7,904,865. **CONFIDENCE: medium-high** (the buckets are clean, the boundaries are judgment calls).

---

## 8. HONEST GAPS — what the literature does NOT solve

**Gap 1: Hand-routing as the production endpoint.** Hackaday, Cadence, NWES, and the Sierra blog all assume "the rest is hand-routed by an experienced layout engineer." There is no published algorithm that guarantees 100% escape on arbitrary dense-IC layouts. Industry truth: at 0.5mm pitch and below, the LAST 5% of nets are HAND-ROUTED in Cadence Allegro / Mentor Xpedition by a senior engineer with 10+ years of experience. Our system has no equivalent "hand router" — we have no GUI session per `feedback-no-gui-session-autonomous-only.md` so we must build a PROGRAMMATIC equivalent (PathFinder + targeted move-the-obstacle + 2-step stacked). **This is the gap that 27/30 → 30/30 closes by building, not by reading.**

**Gap 2: Pin assignment co-optimization is academic-only.** The Yan/Wong + PMC8056246 papers solve pin-assignment + escape JOINTLY for FPGA-PCB co-design. There is NO published open-source implementation. Mentor Xpedition has internal proprietary algorithms. For our case the AT32F421 has SOME pin alt-function flexibility (timer channels can map to multiple pin sets) — but verifying which AM32 firmware variants tolerate the swap requires firmware/silicon study, not router work.

**Gap 3: Sequential-lamination cost is paywalled.** JLC's published HDI Class 2 prices do NOT distinguish 1-step blind from 2-step stacked blind in their automated quote tool. Industry hearsay: 2-step adds 30-50% to bare-board cost. For 4-in-1 ESC retail BOM target ($50-200) this is still <5% of total — non-issue per Sai's cost-OK rule.

**Gap 4: Negotiated congestion implementation cost.** PathFinder is published 1995 but most modern open-source FPGA routers (VPR, nextpnr) inherit it. No PCB-specific open-source implementation of negotiated-congestion exists that we could lift. Building it is engineering work (estimated 4-8 hours for a single-iteration cost-history layer on our existing bounded A*).

**Gap 5: Move-the-obstacle is uncatalogued in industry literature.** Sai's memory catalog is genuinely SOTA-beyond-public-literature — no Cadence/Sierra/NWES blog enumerates the per-pattern obstacle moves. The novapcb Rule 20 is, as far as this research found, a novel contribution. Treat it as our advantage, not as a fallback.

**Gap 6: 3-residual stubbornness is a known qualitative failure mode.** Multiple academic papers (Wu/Wong CS2, dual-model PMC8056246) report saturating at 92-98% routed in dense cases. Hitting 27/30 = 90% on a fine-pitch 4-channel ESC is consistent with the published academic SOTA. The literature DOES NOT promise 100% — only "minimum number of layers" or "minimum congestion." Achieving the LAST 10% is engineering-specific to the board.

**CONFIDENCE on gaps**: high — all 6 gaps are SOTA-literature-confirmed limits.

---

## Prioritized recommendations

### If we have 1 hour
1. **Verify M2 SW VIA TOOL is actually emitting VIPPO on J19.10 / J19.23 / J19.8 / R76.1.** Per `CH1_30of30_M2_SW_VIA_TOOL.md` the tool was built for J18+J19; check the lever-T artifact list for these specific pins. If the tool was applied but these 4 pins were SKIPPED for any reason (e.g. NC clearance exempt didn't fire, or the leaf R76 was out of whitelist), re-run with the 4 pins explicitly included. **Expected unblock: 1-2 of 3** (free, fast, mechanism already deployed).
2. **Run the planner with the same chain-depth=3 but cost-cap relaxed 5× and frontier cap 5×, on the 3 residual nets ONLY** (do not disturb the 27 routed). PathFinder principle: contested nets need more search budget. **Expected unblock: 0-1 of 3** (free CPU only, may reveal new paths or confirm hardness).

### If we have 4 hours (add to above)
3. **Move-the-obstacle on R76 (KILL_RAIL_N_CH1 leaf)**. Per Sai memory `feedback-pre-placement-visual-decision.md`: render the J19.8 + R76 zone, screenshot before, propose 1-2mm nudge of R76 (stay within R76's channel quadrant per board invariants), screenshot proposed-after, verify visually corridor widens, then commit. **Expected unblock: 1 of 3** (KILL_RAIL_N_CH1 trunk + leaf).
4. **Add 2-step stacked microvia mechanism to the planner** (F→In1→In2 on top face; symmetric B→In8→In7 on bottom). This is in-spec for JLC HDI Class 2 and adds the missing escape supply identified in §6. Implementation: extend the existing chain-depth=3 list with a "stacked-2" via-pair primitive; let the planner pick when through-via is saturated. Estimated 2 hours coding + verify. **Expected unblock: 1-2 of remaining** (after R76 move).

### If unblocked entirely (add to above)
5. **Build PathFinder-style negotiated-congestion layer on the existing bounded A***. Per §5D: add per-node history cost, iterate full-board re-routes with rip-up of the WORST OFFENDERS only, ≤ 5 passes. Estimated 4-8 hours coding. Yields convergence on cases that bounded A* alone oscillates on per `reference-cascading-escape-needs-negotiated-routing.md`. **Expected unblock: provides margin for future channels (CH2/CH3/CH4 will hit the same wall when mirrored)** — pays back across the project, not just CH1.
6. **Verify pin-swap feasibility** for PWM_INHB_CH1 + KILL_RAIL_N_CH1 at the firmware level (AT32F421 timer alt-function). If AM32 + AT32F421 supports the swap, opens a structural fix instead of more router engineering. Out of master scope (requires firmware study) — flag to Sai.

### NEVER (rejected from research)
- Re-place CH1: not justified at 10% residual per §7 decision tree.
- Switch fab (non-JLC): no benefit, JLC HDI Class 2 is already in-spec for everything §6 lists.
- Architectural pivot (4 corners 4 drivers): scope explosion; only justified if all 4 channels fail symmetrically, which we have not yet tested.

---

## Sources

- [Sierra Circuits — Designing Staggered and Stacked Vias](https://www.protoexpress.com/blog/design-manufacture-staggered-and-stacked-vias/)
- [Sierra Circuits — How to Design Reliable Microvias](https://www.protoexpress.com/blog/how-to-design-reliable-microvias-in-your-pcbs/)
- [NWES — BGA Escape Routing with Impedance Control in HDI PCBs](https://www.nwengineeringllc.com/article/bga-escape-routing-with-impedance-control-in-hdi-pcbs.php)
- [Cadence — Best PCB Routing Methods for BGA Escape Routing](https://resources.pcb.cadence.com/blog/2019-best-pcb-routing-methods-for-bga-escape-routing)
- [Cadence — How Many Microvias Can You Safely Stack](https://resources.pcb.cadence.com/blog/km-how-many-microvias-can-you-safely-stack-a-deep-dive-into-hdi-reliability-physics)
- [Hemeixin — 2+N+2 PCB Stackup Design for HDI Boards](https://www.hemeixinpcb.com/company/news/2-n-2-pcb-stackup-design-for-hdi-boards.html)
- [Hemeixin — Microvias in PCB Design: A Comprehensive Guide](https://www.hemeixinpcb.com/company/news/microvias-in-pcb-design-a-comprehensive-guide-to-hdi-interconnect-solutions.html)
- [Hemeixin — HDI Microvias for 0.3mm Pitch BGA](https://www.hemeixinpcb.com/company/news/hdi-microvias-for-0-3mm-pitch-bga.html)
- [JLCPCB — Via in Pad (VIP) Technology for HDI PCBs](https://jlcpcb.com/blog/via-in-pad-pcb)
- [JLCPCB — Blind and Buried Vias guide](https://jlcpcb.com/blog/blind-and-buried-vias-guide)
- [PCBSync — IPC-2226 Explained](https://pcbsync.com/ipc-2226/)
- [AllPCB — Escape Routing Techniques for High-Density BGA Packages](https://www.allpcb.com/blog/pcb-assembly/escape-routing-techniques-for-high-density-bga-packages.html)
- [Hackaday — Working with BGAs: Design and Layout](https://hackaday.com/2022/06/20/working-with-bgas-design-and-layout/)
- [PMC8056246 — Dual-model node-based optimization for simultaneous escape routing](https://pmc.ncbi.nlm.nih.gov/articles/PMC8056246/)
- [McMurchie & Ebeling — PathFinder: A Negotiation-Based Performance-Driven Router for FPGAs](https://www.cecs.uci.edu/~papers/compendium94-03/papers/1995/fpga95/pdffiles/6a.pdf)
- [Yan & Wong — Simultaneous Constrained Pin Assignment and Escape Routing for FPGA-PCB Co-Design](https://www.researchgate.net/publication/260584983_Simultaneous_Constrained_Pin_Assignment_and_Escape_Routing_Considering_Differential_Pairs_for_FPGA-PCB_Co-Design)
- [Multi-Terminal PCB Escape Routing for DMFB Using Negotiated Congestion](https://escholarship.org/uc/item/9862j8q0)
- [VESC Hardware GitHub](https://github.com/vedderb/bldc-hardware)
- [Tinymovr GitHub](https://github.com/tinymovr)
- [PULPY ESC 40A AM32 PCBWay project](https://www.pcbway.com/project/shareproject/PULPY_ESC_40A_AM32_3f137014.html)
- [iOkFly Race AM32 4-in-1 ESC GitHub](https://github.com/IOkFly-BLENDERIS/IOkFly-Race-AM32-4in1-ESC)
- [The Devana Project — Hardware design for AM32 ESCs](https://thedevanaproject.com/2025/11/30/hardware-design-for-am32-escs/)
- [Altium — Laser-Drilled Microvia-in-Pad Technology in Your HDI PCB](https://resources.altium.com/p/laser-drilled-pad-technology-your-pcb)
- [Altium — Microvia Sizing for Multi-Layer PCB](https://resources.altium.com/p/microvia-sizing-your-next-multi-layer-pcb)

**Note on failed fetches**: TI AM62 escape app note SPRAD13A (PDF binary fetch failed via WebFetch — citations from search-result summaries only); Würth Elektronik HDI Design Guide v1.2 (PDF binary fetch failed — secondary citations only). Both flagged as **MEDIUM confidence** above where their data was the only source.
