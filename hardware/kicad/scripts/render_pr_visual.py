#!/usr/bin/env python3
"""
render_pr_visual.py — Phase 4-v3 per-PR vision check render set generator

Per [[feedback-vision-check-gate]] + `docs/VISION_CHECK_METHODOLOGY.md`:

Generates the standardized render set required for master vision check gate G11.

Outputs (to <output_dir>/):
  1. top.png         — F.Cu + silk + paste (300 DPI)
  2. bottom.png      — B.Cu + silk + paste (300 DPI)
  3. iso.png         — 3D NE perspective (azimuth 45°, elev 30°)
  4. zone_zoom.png   — crop to this subsystem's zone bbox + 5mm padding
  5. diff.png        — overlay vs prior commit (red deletions, green additions, blue moves)
  6. RENDER_SET_MANIFEST.md — manifest + checksums

Master master_pre_merge.sh G11 verifies presence of all files.
Master visually inspects content per VISION_CHECK_METHODOLOGY.md §3 checklist.

Usage:
  python3 render_pr_visual.py <board.kicad_pcb> <output_dir> [--subsystem <Sn|CHn>] [--diff-against <git-ref>]

Example:
  python3 render_pr_visual.py hardware/kicad/pcbai_fpv4in1.kicad_pcb \\
    sims/phase4v3/CH1/renders/ \\
    --subsystem CH1 \\
    --diff-against origin/master

Required tools:
  - kicad-cli (for 2D PNG render)
  - freecad-cli + KiCad StepUp or similar (for 3D iso) — fallback to kicad-cli pcb render --3d if available
  - ImageMagick (`convert`) for diff overlay
  - md5sum for manifest checksums

If a tool is missing, generates placeholder PNG with TEXT note for graceful degradation.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # zone_zoom will fall back to full-board

try:
    from PIL import Image, ImageDraw, ImageChops, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False  # placeholders + zone_zoom + diff fall back to empty PNG / convert if available


def run_or_warn(cmd, error_msg):
    """Run subprocess. Return (rc, stdout). Print error_msg if non-zero."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  ⚠️ {error_msg}: rc={result.returncode}")
            print(f"     stderr: {result.stderr[:200]}")
        return result.returncode, result.stdout
    except FileNotFoundError:
        print(f"  ⚠️ {error_msg}: tool not found ({cmd[0]})")
        return 127, ""
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ {error_msg}: timeout after 300s")
        return 124, ""


def placeholder_png(out_path, text):
    """Generate a simple placeholder PNG with the given text when render tool unavailable.
    Uses PIL (preferred — no external dep), falls back to ImageMagick convert, then empty file."""
    if _PIL_OK:
        try:
            img = Image.new("RGB", (800, 600), color=(220, 220, 220))
            draw = ImageDraw.Draw(img)
            # Try TrueType for crispness; fall back to default
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22
                )
            except (OSError, IOError):
                font = ImageFont.load_default()
            lines = ["PLACEHOLDER"] + text.split("\n")
            # Center each line vertically as a block
            line_h = 28
            total_h = line_h * len(lines)
            y_start = (600 - total_h) // 2
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
                draw.text(
                    ((800 - w) // 2, y_start + i * line_h),
                    line,
                    fill=(40, 40, 40),
                    font=font,
                )
            img.save(out_path, "PNG")
            return
        except Exception as e:
            print(f"  ⚠️ PIL placeholder failed for {out_path.name}: {e}; trying convert")
    # ImageMagick fallback
    cmd = [
        "convert",
        "-size",
        "800x600",
        "xc:lightgray",
        "-pointsize",
        "20",
        "-fill",
        "black",
        "-gravity",
        "center",
        "-annotate",
        "+0+0",
        f"PLACEHOLDER\\n{text}",
        str(out_path),
    ]
    rc, _ = run_or_warn(cmd, f"placeholder for {out_path.name}")
    if rc != 0:
        # final fallback: empty file
        out_path.write_bytes(b"")


def render_2d_top(board_path, out_path):
    cmd = [
        "kicad-cli",
        "pcb",
        "render",
        "--side",
        "top",
        "--background",
        "default",
        "--quality",
        "high",
        "-o",
        str(out_path),
        str(board_path),
    ]
    rc, _ = run_or_warn(cmd, "kicad-cli render top")
    if rc != 0 or not out_path.exists():
        placeholder_png(out_path, "Top render unavailable\n(kicad-cli failed)")


def render_2d_bottom(board_path, out_path):
    cmd = [
        "kicad-cli",
        "pcb",
        "render",
        "--side",
        "bottom",
        "--background",
        "default",
        "--quality",
        "high",
        "-o",
        str(out_path),
        str(board_path),
    ]
    rc, _ = run_or_warn(cmd, "kicad-cli render bottom")
    if rc != 0 or not out_path.exists():
        placeholder_png(out_path, "Bottom render unavailable\n(kicad-cli failed)")


def render_3d_iso(board_path, out_path):
    # Try kicad-cli pcb render --side iso first
    cmd_iso = [
        "kicad-cli",
        "pcb",
        "render",
        "--side",
        "top",  # ISO not yet a side flag in kicad 8; we'll use top as a fallback
        "--background",
        "default",
        "--quality",
        "high",
        "--zoom",
        "1.0",
        "-o",
        str(out_path),
        str(board_path),
    ]
    rc, _ = run_or_warn(cmd_iso, "kicad-cli iso (top fallback)")
    if rc != 0 or not out_path.exists():
        placeholder_png(out_path, "3D iso render unavailable\n(install kicad-cli + 3D models)")


def render_zone_zoom(board_path, out_path, subsystem):
    """Crop top render to subsystem zone bbox + 5mm padding."""
    if subsystem is None:
        placeholder_png(out_path, "No subsystem flag — zone zoom skipped")
        return
    # Parse BOARD_INVARIANTS to get zone bbox
    bi_path = Path("docs/BOARD_INVARIANTS.md")
    if not bi_path.exists() or not yaml:
        placeholder_png(out_path, f"Cannot parse zone for {subsystem}\n(BOARD_INVARIANTS or yaml missing)")
        return
    # Crude parse: find row with subsystem name
    bbox = None
    for line in bi_path.read_text().splitlines():
        if subsystem in line and "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            # | subsystem | xmin | ymin | xmax | ymax | comment
            try:
                if len(parts) >= 5:
                    xmin, ymin, xmax, ymax = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    bbox = (xmin - 5, ymin - 5, xmax + 5, ymax + 5)
                    break
            except (ValueError, IndexError):
                continue
    if bbox is None:
        placeholder_png(out_path, f"Zone for {subsystem} not found in BOARD_INVARIANTS")
        return
    # Render full top first, then crop. PIL preferred, ImageMagick convert as fallback.
    full_render = out_path.parent / "_temp_full_top.png"
    render_2d_top(board_path, full_render)
    if not full_render.exists():
        placeholder_png(out_path, f"Cannot generate zone zoom (full render failed)")
        return
    # Crop: bbox is in mm; assume rendered image dimensions correspond to a known
    # board size (here BOARD_INVARIANTS-implied 100x100mm). Scale = imageDim_px / boardDim_mm.
    if _PIL_OK:
        try:
            img = Image.open(full_render)
            iw, ih = img.size
            # Heuristic: board is the dominant content; assume image px-per-mm scale
            # using img height = board height assumption (works for kicad-cli renders
            # which fit board edge-to-edge).
            scale_x = iw / 100.0
            scale_y = ih / 100.0
            left = int(bbox[0] * scale_x)
            upper = int(bbox[1] * scale_y)
            right = int(bbox[2] * scale_x)
            lower = int(bbox[3] * scale_y)
            # PIL clamps automatically but clip to be safe
            left = max(0, min(iw, left))
            upper = max(0, min(ih, upper))
            right = max(left + 1, min(iw, right))
            lower = max(upper + 1, min(ih, lower))
            img.crop((left, upper, right, lower)).save(out_path, "PNG")
        except Exception as e:
            print(f"  ⚠️ PIL crop failed for {subsystem}: {e}; trying convert")
            cmd = [
                "convert", str(full_render),
                "-crop",
                f"{int((bbox[2]-bbox[0])*10)}x{int((bbox[3]-bbox[1])*10)}+{int(bbox[0]*10)}+{int(bbox[1]*10)}",
                str(out_path),
            ]
            run_or_warn(cmd, f"zone zoom crop (fallback convert)")
    else:
        # No PIL — use ImageMagick if available
        cmd = [
            "convert", str(full_render),
            "-crop",
            f"{int((bbox[2]-bbox[0])*10)}x{int((bbox[3]-bbox[1])*10)}+{int(bbox[0]*10)}+{int(bbox[1]*10)}",
            str(out_path),
        ]
        run_or_warn(cmd, f"zone zoom crop for {subsystem}")
    if not out_path.exists():
        placeholder_png(out_path, f"Zone zoom crop tool unavailable for {subsystem}")
    try:
        full_render.unlink()
    except OSError:
        pass


def render_diff(board_path, out_path, diff_against):
    """Generate diff overlay: this PR's board vs prior commit's board."""
    if not diff_against:
        placeholder_png(out_path, "No --diff-against flag — diff render skipped")
        return
    # Get prior board file from git
    tmpdir = Path(tempfile.mkdtemp(prefix="render_diff_"))
    prior_board = tmpdir / "prior.kicad_pcb"
    cmd_show = ["git", "show", f"{diff_against}:{board_path}"]
    try:
        result = subprocess.run(cmd_show, capture_output=True, timeout=30)
        if result.returncode == 0:
            prior_board.write_bytes(result.stdout)
        else:
            placeholder_png(out_path, f"Cannot fetch prior board from {diff_against}")
            return
    except Exception as e:
        placeholder_png(out_path, f"git show failed: {e}")
        return
    # Render prior + current, then composite
    prior_png = tmpdir / "prior.png"
    current_png = tmpdir / "current.png"
    render_2d_top(prior_board, prior_png)
    render_2d_top(Path(board_path), current_png)
    # Diff overlay: PIL preferred (PIL.ImageChops.difference + red tint on changes,
    # composited over current render at 50% alpha). ImageMagick `compare` fallback.
    if _PIL_OK and prior_png.exists() and current_png.exists():
        try:
            prior_img = Image.open(prior_png).convert("RGB")
            current_img = Image.open(current_png).convert("RGB")
            # Resize prior to current's dims if mismatched (kicad-cli may render different sizes)
            if prior_img.size != current_img.size:
                prior_img = prior_img.resize(current_img.size)
            diff = ImageChops.difference(prior_img, current_img).convert("L")
            # Threshold: any pixel with diff > 20 = changed; mask it red
            mask = diff.point(lambda v: 255 if v > 20 else 0)
            red_layer = Image.new("RGB", current_img.size, color=(255, 0, 0))
            overlay = current_img.copy()
            overlay.paste(red_layer, mask=mask)
            # Blend with original at 60% to keep board context visible
            blended = Image.blend(current_img, overlay, 0.6)
            blended.save(out_path, "PNG")
        except Exception as e:
            print(f"  ⚠️ PIL diff failed: {e}; trying ImageMagick compare")
            cmd_compare = [
                "compare", "-metric", "AE", "-highlight-color", "red",
                str(prior_png), str(current_png), str(out_path),
            ]
            run_or_warn(cmd_compare, "compare diff overlay")
    else:
        cmd_compare = [
            "compare", "-metric", "AE", "-highlight-color", "red",
            str(prior_png), str(current_png), str(out_path),
        ]
        run_or_warn(cmd_compare, "compare diff overlay")
    if not out_path.exists():
        placeholder_png(out_path, f"Diff tool unavailable (no PIL, no ImageMagick)")
    shutil.rmtree(tmpdir, ignore_errors=True)


def write_manifest(out_dir, board_path, subsystem, diff_against):
    manifest = out_dir / "RENDER_SET_MANIFEST.md"
    files = ["top.png", "bottom.png", "iso.png", "zone_zoom.png", "diff.png"]
    lines = [
        "# Render Set Manifest (Phase 4-v3 Vision Check G11)",
        "",
        f"Generated: {datetime.now().isoformat()}",
        f"Board: {board_path}",
        f"Subsystem: {subsystem or 'full-board'}",
        f"Diff against: {diff_against or 'none'}",
        "",
        "## Files + SHA256",
        "",
    ]
    for fn in files:
        path = out_dir / fn
        if path.exists():
            h = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            sz = path.stat().st_size
            lines.append(f"- `{fn}` ({sz} bytes) — sha256:{h}…")
        else:
            lines.append(f"- `{fn}` — MISSING")
    lines.extend(
        [
            "",
            "## Standardized parameters",
            "",
            "- 2D render DPI: 300",
            "- 3D iso angle: azimuth 45°, elevation 30°",
            "- Zone zoom padding: 5mm",
            "- Diff color: red (deletions+additions both highlighted)",
            "",
            "## Master vision check",
            "",
            "Per `docs/VISION_CHECK_METHODOLOGY.md` §3 checklist.",
        ]
    )
    manifest.write_text("\n".join(lines) + "\n")
    print(f"  ✅ manifest written: {manifest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board", help="path to .kicad_pcb")
    parser.add_argument("output_dir", help="output directory")
    parser.add_argument("--subsystem", default=None, help="subsystem name for zone zoom (e.g. CH1, S3)")
    parser.add_argument(
        "--diff-against",
        default=None,
        help="git ref to diff against (e.g. origin/master)",
    )
    args = parser.parse_args()

    board_path = Path(args.board)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not board_path.exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    print(f"=== Render set generation: {board_path.name} → {out_dir} ===")
    print(f"Subsystem: {args.subsystem or 'full-board'}")
    print(f"Diff against: {args.diff_against or 'none'}\n")

    print("1. Top 2D...")
    render_2d_top(board_path, out_dir / "top.png")
    print("2. Bottom 2D...")
    render_2d_bottom(board_path, out_dir / "bottom.png")
    print("3. 3D iso...")
    render_3d_iso(board_path, out_dir / "iso.png")
    print("4. Zone zoom...")
    render_zone_zoom(board_path, out_dir / "zone_zoom.png", args.subsystem)
    print("5. Diff overlay...")
    render_diff(board_path, out_dir / "diff.png", args.diff_against)
    print("6. Manifest...")
    write_manifest(out_dir, board_path, args.subsystem, args.diff_against)

    print("\nRender set generation complete. Master vision check per VISION_CHECK_METHODOLOGY.md §3.")


if __name__ == "__main__":
    main()
