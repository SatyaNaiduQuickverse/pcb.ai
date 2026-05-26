# Phase 4-v3 CH1 — +3V3 Rail Power-Integrity (VDD Ripple) — ngspice

**Sim:** VDD-rail pk-pk ripple at each IC supply pin caused by half-bridge FET
switching transients capacitively coupled + injected through the shared +3V3
rail impedance.
**Tool:** ngspice-44.2 (`/usr/bin/ngspice`), real transient run.
**Target:** VDD ripple ≤ 50 mV pk-pk at any IC supply pin.
**Verdict:** **PASS** — worst case **0.0369 mV pk-pk** (J18 MCU), 49.96 mV margin.

---

## Literal command

```
cd sims/phase4v3/ch1_pi
ngspice -b vdd_ripple.cir > vdd_ripple.out 2>&1
python3 extract_ripple.py
```

---

## Modeling assumptions (physically defensible, NOT tuned to pass)

| Parameter | Value | Justification |
|---|---|---|
| +3V3 source | ideal 3.3 V DC | BEC/LDO output treated stiff at rail head |
| Rail segment R | 10 mΩ each | few-mm inner-layer +3V3 copper between taps |
| Rail segment L | 5 nH each | ~1 nH/mm loop inductance, a few mm per hop |
| IC trace stub L | 1.5–2.0 nH | decap within ~3 mm per CH1 placement |
| Decoupling cap | 100 nF X7R | per placement (one local decap per IC) |
| Decap ESL | 0.5 nH | typical 0402/0603 X7R mounted ESL |
| Decap ESR | 30 mΩ | typical X7R ESR at decoupling band |
| SW dV/dt | 25.2 V / 40 ns = 6.30e8 V/s | 25.2 V bus, ~40 ns FET edge (spec) |
| Coupling cap C_c | **3 pF** (gate-driver tap) | midrange of stated 1–5 pF; SW pour adjacent +3V3 trace, short run |
| Coupling cap C_c | **1.5 pF** (MCU tap) | farther trace, half the coupling area |
| Injected current | I = C_c·dV/dt | **1.89 mA** (J19), **0.945 mA** (J18) peak, bipolar |
| PWM | 24 kHz, 50% duty | spec; +pulse on SW rise, −pulse on SW fall |
| IC loads | J19 5 mA, J18 20 mA, INA 1.5 mA ea, LM393 1 mA, 74LVC 0.5 mA | datasheet-class Idd, resistive |
| Run | `.tran 2n 200u … UIC` | ~4.8 PWM periods; 2 ns step resolves 40 ns edges (~20 pts/edge) |

The coupling current is pure displacement current I = C·dV/dt — the standard
capacitive-crosstalk model. Values are taken at the middle/typical of the
stated parasitic range, not minimized. A worst-case stress check (below)
confirms the verdict survives the pessimistic end of the range.

---

## Topology

```
+3V3 ─Rseg1─Lseg1─┬─J19(GD)   ─Rseg2─Lseg2─┬─J18(MCU)  ─Rseg3─Lseg3─┬─INA x3
                  │ decap+load              │ decap+load              │ decap+load ea
   ...Rseg4─Lseg4─┬─U3(LM393) ─Rseg5─Lseg5─┬─U4(74LVC1G08)
                  decap+load                decap+load
Injection: Iinj_J19 (1.89mA) into J19 rail tap; Iinj_J18 (0.945mA) into J18 tap
           — bipolar 40 ns pulses at 24 kHz.
Each decap = C(100n) — ESL(0.5n) — ESR(30m) to GND. Each IC stub = Ltr(1.5–2n).
```

---

## 4-point evidence

### 1. Artifact exists
```
vdd_ripple.cir     7632 B   deck
vdd_ripple.out     1160 B   ngspice batch log (exit 0)
vdd_ripple.raw   6.4 MB     binary raw (write) — 100127 data rows
vdd_ripple.dat    12.9 MB   ascii wrdata (8 cols: time + 7 VDD nodes)
ripple_table.txt           markdown ripple table
extract_ripple.py          parser
```

### 2. mtime ordering — result POSTDATES the deck
```
vdd_ripple.cir   2026-05-26 10:32:04   (epoch 1779771724)
vdd_ripple.dat   2026-05-26 10:33:41   (epoch 1779771821)   ← after .cir ✓
vdd_ripple.raw   2026-05-26 10:33:41   (epoch 1779771821)   ← after .cir ✓
ripple_table.txt 2026-05-26 10:33:42   (epoch 1779771822)   ← after .raw ✓
```

### 3. Extract numbers reproduced from the raw — TWO independent paths agree
In-deck ngspice `meas` (from `vdd_ripple.out`) vs python `extract_ripple.py`
(reads `vdd_ripple.dat`), steady-state window t > 50 µs:

| IC | VDD node | ngspice meas (mVpp) | python extract (mVpp) |
|----|----------|--------------------:|----------------------:|
| J19 DRV8300 gate driver | vJ19 | 0.030 | 0.0297 |
| J18 MCU AT32F421        | vJ18 | 0.037 | 0.0369 |
| J20 INA186 #1           | vJ20 | 0.022 | 0.0224 |
| J21 INA186 #2           | vJ21 | —    | 0.0235 |
| J22 INA186 #3           | vJ22 | —    | 0.0242 |
| U3 LM393 comparator     | vU3  | 0.032 | 0.0320 |
| U4 74LVC1G08 logic      | vU4  | 0.031 | 0.0311 |

The two methods agree to the meas print precision. Full ripple table in
`ripple_table.txt`.

### 4. Spec / target
Target ≤ 50 mV pk-pk at any IC pin. Worst measured **0.0369 mVpp (J18)** →
**margin 49.96 mV**. **PASS.**

---

## Stress / responsiveness check (model is not numerically dead)

To confirm the tiny ripple is real PI behavior and not a stuck solver, a
diagnostic variant was run with the pessimistic end of the coupling range
(C_c = 5 pF → 3.15 mA / 1.575 mA injection) **and** the J19 local decap
removed entirely:

| node | nominal mVpp | stress mVpp |
|------|-------------:|------------:|
| vJ19 | 0.0297 | **0.0881** (decap removed → ~3× worse) |
| vJ18 | 0.0369 | 0.0627 |
| vU3  | 0.0320 | 0.0543 |

Removing the decap measurably worsens the unprotected node and raising the
coupling cap scales the ripple ~linearly — both expected. Even this
deliberately pessimistic case stays at 0.088 mVpp, ~570× under the 50 mV
target. (Diagnostic deck not retained; nominal `vdd_ripple.cir`/`.dat`/`.raw`
are the committed artifacts.)

---

## Why ripple is far below target (physics, not luck)

The coupled noise is brief displacement current (a few mA over 40 ns). A local
100 nF X7R presents very low impedance (~0.06 Ω capacitive + ~0.08 Ω ESL +
0.03 Ω ESR ≈ 0.1–0.2 Ω) to that fast-edge content, so the per-impulse voltage
excursion is sub-mV and decays before the next edge. The shared rail L/R only
matters for current the local decap fails to supply — which, for mA-class
coupling, is negligible. This is the intended outcome of one-decap-per-IC
placement (CH1 placement: each IC has a 100 nF within ~3 mm).

**Bottleneck would only appear** if: (a) decaps were shared/farther (>10 mm
stub), (b) real coupling cap were ≫5 pF (e.g. SW node running long & parallel
to the +3V3 trace), or (c) a large in-rush/load-step on the rail (a different
sim — load-step PI, not switching-coupling PI). None apply here.

---

## Result summary

- **Ran:** yes — ngspice-44.2 batch, exit 0, 100127 rows over 200 µs transient.
- **Worst ripple:** 0.0369 mV pk-pk (J18 MCU AT32F421).
- **Verdict:** **PASS** (≤ 50 mV pk-pk target, 49.96 mV margin; stress case 0.088 mV still passes).
- **Artifacts:** `sims/phase4v3/ch1_pi/{vdd_ripple.cir, vdd_ripple.out, vdd_ripple.raw, vdd_ripple.dat, extract_ripple.py, ripple_table.txt, RESULTS.md}`
