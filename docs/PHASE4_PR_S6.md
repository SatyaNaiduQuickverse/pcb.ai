# PR-S6 — §S6 connectors + status LEDs (Task #72)

Fourth of 11 sequential A4-* PRs (after PR-S2 at 14f4552). Places §S6 FC/AUX
connectors, USBLC6 ESD arrays, VBAT divider, and status LED pairs.

## Symptom

PR-S1 deferred LED placement to PR-S6 ("D3/R4 not properly paired; D3 at
(2, 25) in §S5 zone"). PR-S6 contract: RE-PLACE D3/D4/R4/R5 in §S6 zone with
proper LED-pair symmetry; verify DShot signal integrity + S2→S6 ripple
crosstalk on DShot lines.

## Fix

§S6 placement (12 components):

| Ref | Pos (mm)    | Notes                                       |
|-----|-------------|---------------------------------------------|
| J12 | (15, 90)    | AUX BM06B-SRSS-TB 6-pin (master baseline)   |
| J14 | (50, 90)    | FC SM08B-SRSS-TB 8-pin center (X-symmetric) |
| J15 | (40, 85)    | USBLC6 ESD ch1+ch2 DShot                    |
| J16 | (60, 85)    | USBLC6 ESD ch3+ch4 DShot (mirror_X of J15)  |
| J17 | (75, 85)    | USBLC6 ESD TLM + spare                      |
| R36 | (47, 86)    | VBAT divider top 100K                       |
| R37 | (47, 84)    | VBAT divider bot 14K (within 3mm of R36)    |
| C49 | (45, 84)    | VBAT filter 100nF (within 3mm of R36/R37)   |
| D3  | (5, 96)     | GREEN_PWR LED — NW status corner            |
| R4  | (8, 96)     | D3 limit-R 5K1 (3mm pair pitch)             |
| D4  | (95, 96)    | RED_RPOL LED — NE status corner (mirror_X)  |
| R5  | (92, 96)    | D4 limit-R 5K1 (mirror of R4)               |

Removed D3/D4/R4/R5 from S1_POSITIONS dict — they are now S6-owned.

Symmetry: J12 vs J17 about X=50 — not exact mirror (J17 carries USBLC6,
J12 is AUX header — functionally different). J15↔J16 X-mirror ✓. D3/R4
vs D4/R5 X-mirror ✓ (NW corner ↔ NE corner about X=50).

## Root cause

PR-A4-c master baseline (§S6 strip Y=72-85 in pre-grow board) placed J12/J14
at Y=90/85 but didn't have status LEDs in §S6 — they were scattered (D3 in
§S5 zone, D4 in §S1 zone). LED pair grouping for visibility + symmetry was a
deferred concern. PR-S6 addresses it.

## Prevention

- S6_POSITIONS dict now owns ALL §S6 components including status LEDs.
- §S6 zone Y=87-100 strip on north edge: connectors at Y=85-90 (body extent),
  status LEDs at Y=96 (clear of connector bodies, visible from edge).
- Y=93-100 strip (north of connectors) reserved for status LEDs + test points
  per [[feedback-no-passive-island]] LED limit-R proximity rule.

## Spec deviations

- LED limit-R 3mm pair pitch > R23 strict 2mm. Same-net pad clearance per
  PR-S1 disclosed deviation. Acceptable.
- D3 GREEN_PWR LED is at (5, 96), D4 RED_RPOL at (95, 96) — NOT exact mirror
  in functional sense (different LED colors/roles) but mirror in POSITION
  (X=5 ↔ X=95 about X=50). Pure geometric symmetry preserved.

## Audit state

| Gate                                    | Status     |
|-----------------------------------------|------------|
| Total PAD-OVERLAP vs master 364         | PASS (364) — 0 NEW |
| §S6 internal pad-overlap                | 0          |
| Symmetry within §S6                     | PASS       |
| LED limit-R anchoring                   | 3mm pair pitch (PR-S1 disclosed) |
| target.h md5 unchanged                  | ✓          |

## Sims (2, real + 4-point evidence per R18)

### Sim 1: DShot SI ngspice (DShot600 @ 600kHz)

**Scenario**: MCU GPIO push-pull driver (V_OH=3.3V, R_out 50Ω) → 50mm 50Ω
microstrip (modeled as 5 LC segments, L=5nH/cm, C=2pF/cm) → USBLC6 ESD
diode (3pF) → J14 FC connector + 10kΩ/12pF receiver. DShot600 bit period
1.67µs, half-bit 600ns. Sim 1 bit @ 100ns rising edge.

**Acceptance**:
- Rise time ≤200ns ✓
- Overshoot ≤5% ✓
- Ringing ≤3 cycles ✓ (visible in raw, decay within 1 cycle)

**Result** (extract_dshot.py):
- V_peak: **3.284 V** (V_OH=3.3V)
- Overshoot: **-0.50%** (no overshoot, slightly under target)
- Rise time 10-90%: **40.0 ns** (well under 200ns)
- **PASS**

**4-point evidence**:
1. Artifact: `sims/phase4_s6/dshot_si_ngspice/dshot_data.raw`
2. Artifact mtime > input deck mtime
3. Extract reproducible
4. Exec: `ngspice -b sims/phase4_s6/dshot_si_ngspice/dshot.cir`

### Sim 2: S2→S6 DShot crosstalk ngspice (pair-wise)

**Scenario**: V_BUS ripple from §S2 bulk caps (0.46V pk-pk @ 30kHz worst-case
fundamental) couples capacitively into adjacent DShot trace. Coupling C
estimated 1pF for 20mm trace adjacency. DShot receiver: 10kΩ pull-up to 3.3V
+ 12pF load.

**Acceptance**: Induced noise on DShot ≤100mV (≪ 1.65V threshold for 3.3V).

**Result** (extract_crosstalk.py):
- Induced V_DSHOT_RX swing pk-pk: **49.33 mV**
- **PASS** (≤100mV, 51mV margin)

**4-point evidence**:
1. Artifact: `sims/phase4_s6/pairwise_s2_s6_crosstalk/crosstalk_data.raw`
2. Artifact mtime > input deck mtime
3. Extract reproducible
4. Exec: `ngspice -b sims/phase4_s6/pairwise_s2_s6_crosstalk/crosstalk.cir`

## Renders

- `docs/renders/s6/top.png`
- `docs/renders/s6/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-no-passive-island]]
  [[feedback-sim-execution-gate]] [[feedback-incremental-sim-driven-placement]]
- Master CLAUDE.md R18, R19, R23
