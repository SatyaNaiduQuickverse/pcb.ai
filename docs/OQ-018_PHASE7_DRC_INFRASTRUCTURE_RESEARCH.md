# OQ-018 Resolution Research — Phase 7 Full-Board DRC Infrastructure

**Date**: 2026-05-26
**Status**: SAI-DECISION research doc (queued in /tmp/sai-queue.md as OQ-018)
**Context**: Worker proved kicad-cli pcb drc OOM-killed on 15GB Pi after 107min CPU. Full-board DRC infeasible on current hardware. Per §8 #2 Pi-bounded subsystem-scope rule, current Phase 4-v3 STEP 4-6 use subsystem-scoped DRC (works). Phase 7 fab submission requires WHOLE-BOARD DRC pass.

## Options researched

### Option 1: External x86 workstation (RECOMMENDED)

**Spec needed for full-board DRC** (extrapolating from Pi OOM):
- CPU: any modern x86_64 (Intel Core i5+, AMD Ryzen 5+) — DRC is single-threaded mostly
- RAM: **64GB minimum** (15GB Pi died at 107min; 4× headroom for safety)
- Disk: 100GB free (KiCad install + working dir + cache)
- OS: Linux (Ubuntu 22.04 LTS) — same toolchain as Pi
- Network: tailscale for shared access with main repo

**Cost**:
- **New mini-PC**: Intel NUC 13 Pro Core i7 32GB → $700-900 (need to bump to 64GB DIMM = +$150 = ~$1000)
- **Used Dell/HP workstation**: 64GB DDR4 + Xeon E5 → $400-600 used market
- **Cloud VM** (alternative): AWS c6i.4xlarge (64GB) = $0.68/hr = ~$16/run for typical DRC; could be cheaper at <100 DRC runs/year
- **Best balance**: used workstation $400-600 + dedicated to fab-prep, runs alongside Pi

**Pros**:
- Deterministic, reproducible (same KiCad version everywhere)
- One-time CAPEX, $0 OPEX (no cloud bills)
- Future-proof for HV60 SKU + bigger designs
- Independent of network latency
- Per [[feedback-sureshot-over-sota]]: physical machine = sureshot

**Cons**:
- CAPEX $400-1000
- Need to set up + maintain
- Single-point-of-failure for fab-prep (mitigated by Pi as backup for non-DRC work)

### Option 2: Cloud KiCad DRC service

**Available options**:
- [KiCad official Docker](https://www.kicad.org/download/docker/) on cloud VM (AWS/GCP/Azure)
- [linuxserver/docker-kicad](https://hub.docker.com/r/linuxserver/kicad) — web-accessible via VNC
- [INTI-CMNB/kicad_auto](https://github.com/INTI-CMNB/kicad_auto) — CI/CD-oriented; runs DRC/ERC via headless kicad-cli

**Cost**:
- AWS c6i.4xlarge (16 vCPU, 32GB): $0.68/hr × ~30min/run = $0.34/run
- AWS c6i.8xlarge (16 vCPU, 64GB): $1.36/hr × ~30min/run = $0.68/run
- ~20-50 DRC runs total through to fab = $10-30 total CAPEX equiv

**Pros**:
- No upfront cost
- Scales to bigger machines if needed (96GB+ instances available)
- No physical hardware to maintain
- Per-run billing matches usage

**Cons**:
- Network upload board file (slow on residential)
- Reproducibility risk (KiCad version drift in cloud images)
- Recurring cost adds up over years
- Requires AWS/GCP account setup
- VM warm-start latency ~2-3 min per run
- Per [[feedback-sureshot-over-sota]]: cloud reliability less than physical

### Option 3: JLC online DRC (DFM check at fab)

**What it is**: JLC's order-flow includes automatic DFM check. Looks for issues that affect manufacturability (annular ring, copper-to-edge, drill, etc).

**Pros**:
- $0 explicit cost (included in fab order)
- Catches manufacturer-specific issues
- We've already learned about its scope per [[feedback-jlc-dfm-pre-fab-gate]]

**Cons**:
- **NOT a substitute for full KiCad DRC** — only checks JLC-specific manufacturability issues, NOT signal-integrity / clearance-class / impedance issues
- Per [[feedback-jlc-dfm-pre-fab-gate]]: prior 5-day rework cycle when relied on JLC-DFM-only
- Doesn't catch subtle clearance violations between non-fab-rule classes

**Verdict**: COMPLEMENTARY, not REPLACEMENT. Run KiCad DRC + JLC DFM both.

### Option 4: Subsystem-scoped DRC only (status quo + acceptance)

What §8 #2 already mandates for current Phase 4-v3 work. Per-subsystem DRC works on Pi.

**Pros**:
- $0 cost, no setup
- Already proven workflow

**Cons**:
- DOESN'T catch INTER-subsystem clearance violations (e.g., a CH1 net coming too close to S5 BEC route)
- Phase 7 fab submission really needs WHOLE-BOARD verification

**Verdict**: insufficient for Phase 7 alone.

## Recommendation

**OPTION 1 (external workstation) primary + OPTION 3 (JLC DFM) complementary**:

1. **Acquire used 64GB workstation** ($400-600 used Dell/HP) dedicated to Phase 7 fab-prep work
2. Install Ubuntu 22.04 + KiCad 9.0.x same as Pi
3. Set up tailscale for shared access
4. Phase 7 workflow: rsync canonical .kicad_pcb → workstation → kicad-cli pcb drc full-board → report
5. JLC DFM as second-pass verification at order time

**Why x86 over cloud**:
- Sureshot ($400-600 one-time, predictable)
- Per Sai's "cost OK" + "no corners cut": deterministic > pay-per-use
- Reusable for HV60 next-SKU
- No network upload risk

**Why NOT cloud**:
- Cumulative pay-per-use cost over project lifetime competitive with one-time CAPEX
- Reproducibility risk for fab-class verification
- Adds external dependency

## Sai-decision needed

- **(A) Used 64GB workstation** ($400-600 used; recommended)
- **(B) New mini-PC** (Intel NUC 13 Pro 64GB ~$1000; clean but more expensive)
- **(C) Cloud VM** ($10-30 total; no setup but reproducibility risk)
- **(D) Defer to JLC DFM only** (NOT recommended per [[feedback-jlc-dfm-pre-fab-gate]])

If you approve (A) or (B), I'll author the workstation setup spec (Ubuntu + KiCad + tailscale + shared-dir) + master/worker workflow integration. Cost cleared per "cost OK" directive.

## Implementation timeline (if approved)

- Week 1: acquire hardware, OS install, KiCad install, tailscale setup
- Week 2: integrate into master+worker workflow (rsync canonical → DRC report → back to repo)
- Week 3+: use for Phase 7 fab-prep on all SKUs

Doesn't block Phase 4-v3 work (worker continues on Pi); needed before fab submission.

## Per locked rulebook

- ✅ [[feedback-sureshot-over-sota]] — physical workstation > pay-per-use cloud
- ✅ [[feedback-online-research-when-needed]] — researched KiCad Docker + AWS pricing
- ✅ [[feedback-pi-bounded-subsystem-scope]] — explicitly cited as why we need this
- ✅ [[feedback-jlc-dfm-pre-fab-gate]] — JLC DFM stays complementary, not substitute
- ✅ Cost-OK directive cleared (per Sai 2026-05-26)

## Sources

- [KiCad official Docker images](https://www.kicad.org/download/docker/)
- [INTI-CMNB/kicad_auto on GitHub](https://github.com/INTI-CMNB/kicad_auto)
- AWS EC2 pricing reference (c6i instance class)
- Used workstation market (eBay/Newegg) Dell/HP Xeon spec class
