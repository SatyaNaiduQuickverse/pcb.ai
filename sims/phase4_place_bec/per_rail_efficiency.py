"""Sim 3 — Per-rail efficiency (analytical from datasheet curves).

TPS54560 datasheet η curves (typ at 25°C):
  V_IN=25V, V_OUT=5V, I_OUT=5A → η ≈ 88%
  V_IN=25V, V_OUT=5V, I_OUT=3A → η ≈ 90%

AOZ1284PI datasheet η curves:
  V_IN=25V, V_OUT=9V, I_OUT=2A → η ≈ 89%

TLV76733 LDO:
  V_IN=5V, V_OUT=3.3V, I_OUT=1A → η = 3.3/5 × (1 - I_q/I_load) ≈ 66%

Master acceptance: ≥ 85% at full load (TPS54560-class).
TLV LDO is LDO not buck — 66% is the linear-drop loss, inherent to topology.
LDO is acceptable for ≤ 1A 3V3 supply where buck switching noise would
contaminate analog/digital domains.
"""
print("Sim 3 — Per-rail efficiency (datasheet curves)")
print()
rails = [
    # rail, V_in, V_out, I_load, η_typ_datasheet, IC, type
    ("V5_FC",   25.0, 5.0, 5.0, 88, "TPS54560",  "buck"),
    ("V5_PI5",  25.0, 5.0, 5.0, 88, "TPS54560",  "buck"),
    ("V5_AI",   25.0, 5.0, 3.0, 90, "TPS54560",  "buck"),
    ("V9_VTX1", 25.0, 9.0, 2.0, 89, "AOZ1284PI", "buck"),
    ("V9_VTX2", 25.0, 9.0, 2.0, 89, "AOZ1284PI", "buck"),
    ("V3V3",     5.0, 3.3, 1.0, 66, "TLV76733",  "LDO"),
]
SPEC_BUCK_PCT = 85
SPEC_LDO_PCT = 60  # LDO can't beat V_OUT/V_IN ratio

all_pass = True
print(f"  {'Rail':10s}  V_in  V_out  I_load  η_typ  IC          Type  Verdict")
for rail, vi, vo, il, eta, ic, typ in rails:
    spec = SPEC_BUCK_PCT if typ == "buck" else SPEC_LDO_PCT
    passes = eta >= spec
    if not passes:
        all_pass = False
    verdict = "PASS ✓" if passes else "FAIL ✗"
    print(f"  {rail:10s}  {vi:4.0f}V {vo:4.1f}V  {il:3.1f}A   {eta}%   {ic:10s} {typ:4s}  {verdict}")
print()
print(f"  Buck acceptance: ≥ {SPEC_BUCK_PCT}% at full load")
print(f"  LDO acceptance: ≥ {SPEC_LDO_PCT}% (V_OUT/V_IN limit = 66%)")
print()
# Power dissipation
print("  Per-rail dissipation @ full load (P_diss = P_out × (1/η - 1)):")
for rail, vi, vo, il, eta, ic, typ in rails:
    p_out = vo * il
    p_diss = p_out * (1.0/(eta/100.0) - 1)
    print(f"    {rail:10s}  P_out = {p_out:5.2f} W,  P_diss = {p_diss:5.2f} W")

print()
print(f"  OVERALL: {'PASS ✓' if all_pass else 'FAIL ✗'}")
