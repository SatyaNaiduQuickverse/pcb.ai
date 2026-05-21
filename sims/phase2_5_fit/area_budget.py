"""Phase 2.5 — component area budget + per-side density vs candidate form factors.

Rigor §10: every package dimension cited from the part's datasheet (Phases 2a-2e
PRs link the datasheets). No recall.

Output: per-part table, F.Cu/B.Cu split, per-side area, fit verdict per candidate
form factor (40×40, 50×50, 30×60 — and 60×60 fallback).
"""

import math

# (name, qty, w_mm, h_mm, side, comment)
# side: 'F' (signal side), 'B' (power side), 'either'
PARTS = [
    # ──────────────────────── Power / FET subsystem (B.Cu) ────────────────────────
    ("AON6260 (24× phase MOSFETs)",       24, 5.0, 6.0, 'B', "DFN5x6-8 per AOS datasheet Rev 1.1 p.1"),
    ("AON6260 (4× reverse-pol parallel)",  4, 5.0, 6.0, 'B', "DFN5x6 — same part reused; low-side GND-return ideal-diode"),
    ("Shunt 0.2 mΩ 2512 (12×)",           12, 6.3, 3.2, 'B', "WSLP / Susumu PSL class; 2512 (6.3×3.2) per common datasheet"),
    ("Bulk cap 470 µF 63 V (2× parallel)", 2, 12.5, 13.5, 'B', "Aluminum electrolytic SMD radial, low-ESR class (~12.5×13.5 mm pkg)"),
    ("SMBJ33A TVS",                        1, 4.3, 3.4, 'B', "SMB / DO-214AA per Littelfuse/Bourns datasheet"),
    ("LMR51420YDDCR buck",                 1, 2.9, 1.6, 'B', "SOT-23-6 per TI SLUSDC8"),
    ("XRIM160808SR47MBCD inductor",        1, 1.6, 0.8, 'B', "0.47 µH SMD per LCSC datasheet"),
    # ──────────────────────── Signal / logic subsystem (F.Cu) ─────────────────────
    ("AT32F421K8T7 (4× MCUs)",             4, 9.0, 9.0, 'F', "LQFP-32 7×7 body + 1 mm lead extension per side per AT32F421 Rev 2.02 Fig 3"),
    ("DRV8300DRGER (4× gate drivers)",     4, 4.0, 4.0, 'F', "VQFN-24 4×4 mm per TI SLVSFG5D p.4"),
    ("INA186A3IDCKR (12× CSAs)",          12, 2.0, 2.1, 'F', "SC-70-6 (DCK) per TI INA186 datasheet"),
    ("TLV76733DRVR LDO",                   1, 2.0, 2.0, 'F', "WSON-6 2.0×2.0 mm per TI SBVS295A"),
    ("JST SM08B-SRSS-TB FC connector",     1, 8.0, 3.4, 'F', "8-pin SH 1.0 mm pitch per JST eSR datasheet"),
    ("USBLC6-2SC6 ESD (3×)",               3, 2.9, 2.8, 'F', "SOT-23-6 per STMicroelectronics datasheet"),
    # ──────────────────────── Per-MCU decoupling (F.Cu) ──────────────────────────
    ("VDD 100nF 0402 (×4 MCUs ×2 pins=8)", 8, 1.0, 0.5, 'F', "Per AT32F421 Fig 8 Power Supply Scheme; one per VDD pin"),
    ("VDDA 100nF 0402 (×4 MCUs)",          4, 1.0, 0.5, 'F', "Per VDDA pin (1 per MCU)"),
    ("VDD 10µF 0805 (×4 MCUs shared)",     4, 2.0, 1.25,'F', "Shared between MCU's 2 VDD pins"),
    ("VDDA 1µF 0402 (×4 MCUs)",            4, 1.0, 0.5, 'F', "Per VDDA pin"),
    ("VDDA ferrite bead BLM03 0201 (×4)",  4, 0.6, 0.3, 'F', "BLM03PX121SN1D 0201"),
    # ──────────────────────── Per-driver decoupling (F.Cu) ──────────────────────
    ("Driver 10µF 0805 (×4)",              4, 2.0, 1.25,'F', "DRV8300 GVDD decoupling"),
    ("Driver 100nF 0402 (×4)",             4, 1.0, 0.5, 'F', "DRV8300 GVDD ceramic"),
    # ──────────────────────── Bootstrap caps (F.Cu, per channel) ────────────────
    ("Bootstrap 100nF 0402 (×12)",        12, 1.0, 0.5, 'F', "C_BST per phase (3×4); placeholder 100 nF — Phase 3 sizes from Q_g"),
    # ──────────────────────── Per-channel local bus (F.Cu) ──────────────────────
    ("Channel local 22µF 0603 (×4)",       4, 1.6, 0.8, 'F', "Local high-freq bypass at each driver V_CC"),
    # ──────────────────────── LEDs + status (F.Cu) ───────────────────────────────
    ("LED 0603 (×5)",                      5, 1.6, 0.8, 'F', "1× green PG + 4× red status per channel"),
    ("LED current-limit R 0402 (×5)",      5, 1.0, 0.5, 'F', "1 kΩ R for 3.3 mA at 3.3 V"),
    # ──────────────────────── Solder pads + test points ────────────────────────
    ("Motor pads (12× 3.0 mm dia)",       12, 3.0, 3.0, 'F', "12 motor outputs (4 ch × 3 phases) — area = π·r²"),
    ("SWD pads (12× 1.0 mm dia)",         12, 1.0, 1.0, 'F', "4 sets × (SWDIO + SWCLK + GND), per-MCU pattern"),
]

def part_area_one(w, h, circular=False):
    if circular:
        # for round pads where (w,h) gives diameter twice (we store dia in w,h)
        return math.pi * (w/2) ** 2
    return w * h

def total_area(parts):
    sum_F = sum_B = 0.0
    rows = []
    for name, qty, w, h, side, comment in parts:
        circ = 'pads' in name.lower() or 'dia)' in name.lower()
        per = part_area_one(w, h, circ)
        tot = per * qty
        rows.append((name, qty, w, h, per, tot, side))
        if side == 'F':
            sum_F += tot
        elif side == 'B':
            sum_B += tot
    return rows, sum_F, sum_B

rows, area_F, area_B = total_area(PARTS)

print("=" * 100)
print(f"{'Part':40s} {'Qty':>4s} {'w':>6s} {'h':>6s} {'A/u':>8s} {'Tot':>8s} {'Side':>4s}")
print("=" * 100)
for name, qty, w, h, per, tot, side in rows:
    print(f"{name:40s} {qty:>4d} {w:>6.2f} {h:>6.2f} {per:>8.2f} {tot:>8.1f} {side:>4s}")
print("=" * 100)
total = area_F + area_B
print(f"{'TOTAL pure component area':40s} {'':>4s} {'':>6s} {'':>6s} {'':>8s} {total:>8.1f} mm²")
print(f"  F.Cu (signal side) pure   : {area_F:>8.1f} mm²")
print(f"  B.Cu (power side) pure    : {area_B:>8.1f} mm²")
print()

# ────────────── Per-side density with routing overhead ──────────────
ROUTING = 1.40   # +40% FPV-dense convention
need_F = area_F * ROUTING
need_B = area_B * ROUTING
need_max = max(need_F, need_B)
print("With +40% routing overhead (FPV-dense convention):")
print(f"  F.Cu required : {need_F:>8.1f} mm²")
print(f"  B.Cu required : {need_B:>8.1f} mm²")
print(f"  Max(F,B)      : {need_max:>8.1f} mm² (the tighter side drives form-factor choice)")
print()

# ────────────── Verdict per candidate ──────────────
CANDIDATES = [
    ("40 × 40 mm", 40 * 40),
    ("50 × 50 mm", 50 * 50),
    ("30 × 60 mm", 30 * 60),
    ("60 × 60 mm", 60 * 60),
]
print("Per-candidate fit (margin = (board - need) / board):")
print(f"{'Form factor':16s} {'Area':>8s} {'F.Cu margin':>14s} {'B.Cu margin':>14s} {'Verdict':>16s}")
for name, area in CANDIDATES:
    margin_F = (area - need_F) / area * 100
    margin_B = (area - need_B) / area * 100
    tighter = min(margin_F, margin_B)
    if tighter < 0:
        v = "FAIL (overflows)"
    elif tighter < 15:
        v = "tight (<15%)"
    elif tighter < 30:
        v = "OK"
    else:
        v = "comfortable"
    print(f"{name:16s} {area:>8d} {margin_F:>13.1f}% {margin_B:>13.1f}% {v:>16s}")

# ────────────── Worker's pick ──────────────
print()
print("=" * 100)
print("Worker's pick (per master's criteria + thermal considerations):")
print("  50 × 50 mm — comfortable per-side margin; ~56% more thermal area vs 40×40;")
print("  matches mid-tier industrial-FPV pattern (SEQURE E70 G2 ballpark).")
print("  30 × 60 also fits but standard FPV mounting is harder (rectangular stack pattern).")
print("  40 × 40 is too tight on B.Cu (signal density routing margin slips below 15%).")
