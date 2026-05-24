#!/bin/bash
# Fetch the 36 unique 3D models referenced by pcbai_fpv4in1.kicad_pcb
# from gitlab.com/kicad/libraries/kicad-packages3D@9.0.2
set -e
BASE_URL="https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/9.0.2"
DEST="/home/novatics64/escworker/local/kicad-packages3D"

MODELS=(
  "Capacitor_SMD.3dshapes/C_0402_1005Metric.step"
  "Capacitor_SMD.3dshapes/C_0603_1608Metric.step"
  "Capacitor_SMD.3dshapes/C_0805_2012Metric.step"
  "Capacitor_SMD.3dshapes/C_1206_3216Metric.step"
  "Capacitor_SMD.3dshapes/CP_Elec_10x14.3.step"
  "Capacitor_SMD.3dshapes/CP_Elec_6.3x7.7.step"
  "Connector_JST.3dshapes/JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal.step"
  "Connector_JST.3dshapes/JST_SH_SM08B-SRSS-TB_1x08-1MP_P1.00mm_Horizontal.step"
  "Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Vertical.step"
  "Diode_SMD.3dshapes/D_SMA.step"
  "Diode_SMD.3dshapes/D_SMB.step"
  "Diode_SMD.3dshapes/D_SOD-123.step"
  "Diode_SMD.3dshapes/D_SOD-323.step"
  "Fuse.3dshapes/Fuse_1206_3216Metric.step"
  "Inductor_SMD.3dshapes/L_0201_0603Metric.step"
  "Inductor_SMD.3dshapes/L_0805_2012Metric.step"
  "Inductor_SMD.3dshapes/L_Sunlord_MWSA0503S.step"
  "Inductor_SMD.3dshapes/L_Sunlord_MWSA0605S.step"
  "LED_SMD.3dshapes/LED_0603_1608Metric.step"
  "Package_DFN_QFN.3dshapes/DFN-10-1EP_3x3mm_P0.5mm_EP1.55x2.48mm.step"
  "Package_DFN_QFN.3dshapes/HVQFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm.step"
  "Package_DFN_QFN.3dshapes/QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm.step"
  "Package_DFN_QFN.3dshapes/W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm.step"
  "Package_SO.3dshapes/SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm.step"
  "Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.step"
  "Package_SON.3dshapes/WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-23-6.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-23-8.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-23.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-353_SC-70-5.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-363_SC-70-6.step"
  "Resistor_SMD.3dshapes/R_0402_1005Metric.step"
  "Resistor_SMD.3dshapes/R_0603_1608Metric.step"
  "Resistor_SMD.3dshapes/R_2512_6332Metric.step"
  "Resistor_THT.3dshapes/R_Axial_DIN0207_L6.3mm_D2.5mm_P5.08mm_Vertical.step"
  "Sensor_Current.3dshapes/Allegro_CB_PFF.step"
)

ok=0; fail=0
for m in "${MODELS[@]}"; do
  dir="$DEST/$(dirname "$m")"
  mkdir -p "$dir"
  url="$BASE_URL/$m?inline=false"
  if curl -sSL --fail -o "$DEST/$m" "$url" 2>/dev/null; then
    sz=$(stat -c %s "$DEST/$m")
    if [ "$sz" -gt 100 ]; then
      ok=$((ok+1))
      printf "  OK %5d bytes  %s\n" "$sz" "$m"
    else
      fail=$((fail+1))
      printf "  EMPTY (HTML err)  %s\n" "$m"
      rm -f "$DEST/$m"
    fi
  else
    fail=$((fail+1))
    printf "  FAIL  %s\n" "$m"
  fi
done
echo ""
echo "Total: $ok OK, $fail FAIL of ${#MODELS[@]}"
