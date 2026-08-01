#!/usr/bin/env python3
"""
Generate a visual mockup of the Cymbal OSD layout.

Creates a PNG image showing how the OSD elements appear overlaid on video.
Requires: pillow (pip install pillow)

Usage:
    python tools/generate_osd_mockup.py

Output:
    docs/osd_mockup.png - Visual representation of OSD layout

Elements rendered:
  - Aircraft panel (top-left, white)  : header, UTC + local date-timestamps,
      address, lat/lon, Alt AGL / GPS Alt (ft), GndSpd (mph, True), fix/sats
  - Heading tape (top-center, green)  : scrolling °, cardinals, chevron, box
  - Compass widget (top-right)        : aircraft outline symbol, N/E/S/W labels,
      camera-aim arrow (yellow), Trk/Cam labels
  - Crosshair (center, green)         : four-arm reticle with center gap
  - Target panel (bottom-right, magenta) : lat/lon, elevation ft MSL,
      slant range ft, address — shown when POI is locked
"""

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow not installed")
    print("Install with: pip install pillow")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Colour palette (RGB for Pillow — note: OSD uses BGR for OpenCV)
# ---------------------------------------------------------------------------
WHITE   = (255, 255, 255)
BLACK   = (0,   0,   0)
GREEN   = (0,   255, 0)     # heading tape, crosshair
MAGENTA = (255, 0,   255)   # target panel
YELLOW  = (255, 215, 0)     # compass N label, camera arrow
GRAY    = (180, 180, 180)   # compass ring


def draw_rounded_rectangle(draw, xy, radius, fill, outline=None, width=1):
    """Draw a rectangle with rounded corners."""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)
    draw.ellipse([x1, y1, x1 + 2*radius, y1 + 2*radius], fill=fill, outline=outline, width=width)
    draw.ellipse([x2 - 2*radius, y1, x2, y1 + 2*radius], fill=fill, outline=outline, width=width)
    draw.ellipse([x1, y2 - 2*radius, x1 + 2*radius, y2], fill=fill, outline=outline, width=width)
    draw.ellipse([x2 - 2*radius, y2 - 2*radius, x2, y2], fill=fill, outline=outline, width=width)


def draw_text_shadowed(draw, pos, text, font, color, shadow_offset=1):
    """Draw text with a black shadow for readability over video."""
    x, y = pos
    draw.text((x + shadow_offset, y + shadow_offset), text, fill=BLACK, font=font)
    draw.text((x, y), text, fill=color, font=font)


def draw_panel(draw, lines, x, y, font, line_height, padding, text_color, measure_fn):
    """Draw a semi-transparent panel with text lines, returning bounding box."""
    max_w = max(measure_fn(draw, l, font) for l in lines) if lines else 80
    total_h = len(lines) * line_height + padding * 2
    bx1 = x - padding
    by1 = y - line_height
    bx2 = x + max_w + padding
    by2 = by1 + total_h + line_height

    draw_rounded_rectangle(draw, [bx1, by1, bx2, by2], radius=4,
                           fill=(0, 0, 0, 150))

    ty = y
    for line in lines:
        draw_text_shadowed(draw, (x, ty), line, font, text_color)
        ty += line_height

    return bx1, by1, bx2, by2


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def create_osd_mockup(output_path="docs/osd_mockup.png", width=640, height=480):
    """
    Create a visual mockup of the OSD layout matching overlay_controller.pyx.
    """
    # Base image — simulated aerial view
    img = Image.new('RGB', (width, height), color='#4a7ba7')
    draw = ImageDraw.Draw(img, 'RGBA')

    for y in range(height):
        alpha = int(30 * (y / height))
        draw.rectangle([0, y, width, y + 1], fill=(70, 100, 130, alpha))
    for i in range(20):
        y_off = int(height * 0.6 + i * 15)
        if y_off < height:
            draw.rectangle([0, y_off, width, y_off + 8], fill=(60, 90, 70, 40))

    # Fonts
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ]
    font_med = font_sm = font_xs = ImageFont.load_default()
    for fp in font_paths:
        try:
            font_med = ImageFont.truetype(fp, 14)
            font_sm  = ImageFont.truetype(fp, 11)
            font_xs  = ImageFont.truetype(fp, 10)
            break
        except Exception:
            pass

    line_h = 20
    pad    = 8

    # =========================================================================
    # AIRCRAFT PANEL — top-left, white
    # =========================================================================
    aircraft_lines = [
        "\u2500\u2500 AIRCRAFT \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "2026-08-01 17:23:45 UTC",
        "2026-08-01 10:23:45 MST",
        "123 Main St, Phoenix AZ",
        "Lat: 33.44827  Lon: -112.07400",
        "Alt AGL: 499 ft  GPS Alt: 1476 ft",
        "GndSpd: 63.8 mph  (True)",
        "Fix: DGPS  Sats: 12",
    ]

    draw_panel(draw, aircraft_lines, 10, 10 + line_h, font_med, line_h, pad,
               WHITE, text_width)

    # =========================================================================
    # HEADING TAPE — top-center, bright green
    # =========================================================================
    camera_heading = 135
    tape_h = int(height * 0.07)
    tape_w = int(width  * 0.25)
    tape_x = (width - tape_w) // 2
    tape_y = int(height * 0.02)

    # Background + green border with shadow
    draw.rectangle([tape_x, tape_y, tape_x + tape_w, tape_y + tape_h],
                   fill=(0, 0, 0, 140))
    draw.rectangle([tape_x - 1, tape_y - 1, tape_x + tape_w + 1, tape_y + tape_h + 1],
                   outline=BLACK, width=3)
    draw.rectangle([tape_x, tape_y, tape_x + tape_w, tape_y + tape_h],
                   outline=GREEN, width=2)

    fov_deg = 30.0
    deg_per_px = fov_deg / tape_w
    tape_cx = tape_x + tape_w // 2
    tick_top = tape_y + 3

    for deg in range(int(camera_heading - fov_deg/2 - 1),
                     int(camera_heading + fov_deg/2 + 2)):
        nd = deg % 360
        offset = nd - camera_heading
        if offset > 180:  offset -= 360
        if offset < -180: offset += 360
        if abs(offset) > fov_deg / 2:
            continue
        xp = int(tape_cx + offset / deg_per_px)
        if xp < tape_x or xp > tape_x + tape_w:
            continue

        if nd % 5 == 0:
            draw.line([xp + 1, tick_top + 1, xp + 1, tick_top + 13], fill=BLACK, width=2)
            draw.line([xp, tick_top, xp, tick_top + 12], fill=GREEN, width=2)
            lbl = f"{nd:03d}"
            bx = draw.textbbox((0, 0), lbl, font=font_xs)
            lw = bx[2] - bx[0]
            lh = bx[3] - bx[1]
            lx = xp - lw // 2
            ly = tick_top + 14
            draw_text_shadowed(draw, (lx, ly), lbl, font_xs, GREEN)
            card = {0: "N", 90: "E", 180: "S", 270: "W"}.get(nd)
            if card:
                draw_text_shadowed(draw, (xp - 4, ly + lh + 2), card, font_xs, GREEN)
        else:
            draw.line([xp + 1, tick_top + 1, xp + 1, tick_top + 6], fill=BLACK, width=1)
            draw.line([xp, tick_top, xp, tick_top + 5], fill=GREEN, width=1)

    # Chevron
    chev_y = tape_y + tape_h - 2
    chev_pts = [(tape_cx, chev_y),
                (tape_cx - 7, chev_y - 7),
                (tape_cx + 7, chev_y - 7)]
    draw.polygon(chev_pts, fill=BLACK)
    draw.polygon([(tape_cx, chev_y - 1),
                  (tape_cx - 6, chev_y - 7),
                  (tape_cx + 6, chev_y - 7)], fill=GREEN)

    # Heading box (larger, green border)
    hdg_str = f"{camera_heading:03d}\u00b0"
    hbx = draw.textbbox((0, 0), hdg_str, font=font_med)
    hbw = hbx[2] - hbx[0] + 16
    hbh = hbx[3] - hbx[1] + 10
    hbox_x = tape_cx - hbw // 2
    hbox_y = tape_y + tape_h + 2
    draw.rectangle([hbox_x, hbox_y, hbox_x + hbw, hbox_y + hbh],
                   fill=(0, 0, 0, 150))
    draw.rectangle([hbox_x - 1, hbox_y - 1, hbox_x + hbw + 1, hbox_y + hbh + 1],
                   outline=BLACK, width=3)
    draw.rectangle([hbox_x, hbox_y, hbox_x + hbw, hbox_y + hbh],
                   outline=GREEN, width=2)
    draw_text_shadowed(draw, (hbox_x + 8, hbox_y + 3), hdg_str, font_med, GREEN)

    # =========================================================================
    # COMPASS WIDGET — top-right
    # =========================================================================
    cr = 45   # compass radius
    ccx = width - cr - 15
    ccy = cr + 15

    # Background disc
    draw.ellipse([ccx - cr - 14, ccy - cr - 14, ccx + cr + 14, ccy + cr + 14],
                 fill=(0, 0, 0, 150))

    # Ring
    draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr],
                 outline=GRAY, width=2)

    # Cardinal ticks + labels
    card_info = [(0, "N", YELLOW, 12, True),
                 (90, "E", GRAY, 10, False),
                 (180, "S", GRAY, 10, False),
                 (270, "W", GRAY, 10, False)]
    for angle, lbl, col, fsize, bold in card_info:
        rad = math.radians(angle)
        ir = cr - 7
        ix = int(ccx + ir * math.sin(rad))
        iy = int(ccy - ir * math.cos(rad))
        ox = int(ccx + cr * math.sin(rad))
        oy = int(ccy - cr * math.cos(rad))
        draw.line([ix, iy, ox, oy], fill=GRAY, width=2)
        tx = int(ccx + (cr + 11) * math.sin(rad))
        ty = int(ccy - (cr + 11) * math.cos(rad))
        lf = font_med if bold else font_sm
        bx2 = draw.textbbox((0, 0), lbl, font=lf)
        lw = bx2[2] - bx2[0]; lh2 = bx2[3] - bx2[1]
        draw_text_shadowed(draw, (tx - lw // 2, ty - lh2 // 2), lbl, lf, col)

    # Aircraft symbol: fuselage + wings + tail (pointing NE = 45°)
    track_deg = 45.0
    tr = math.radians(track_deg)
    st = math.sin(tr); ct = math.cos(tr)

    def rot(dx, dy):
        return (int(ccx + dx * st + dy * ct),
                int(ccy - dx * ct + dy * st))

    fuselage_tip  = rot(0, -int(cr * 0.75))
    fuselage_tail = rot(0,  int(cr * 0.65))
    wing_mid      = rot(0,  int(cr * 0.05))
    wing_l        = rot(-int(cr * 0.72), int(cr * 0.22))
    wing_r        = rot( int(cr * 0.72), int(cr * 0.22))
    tail_l        = rot(-int(cr * 0.28), int(cr * 0.55))
    tail_r        = rot( int(cr * 0.28), int(cr * 0.55))

    for seg in [(fuselage_tip, fuselage_tail),
                (wing_mid, wing_l), (wing_mid, wing_r),
                (tail_l, tail_r)]:
        draw.line([seg[0][0], seg[0][1], seg[1][0], seg[1][1]], fill=BLACK, width=4)
    for seg in [(fuselage_tip, fuselage_tail),
                (wing_mid, wing_l), (wing_mid, wing_r),
                (tail_l, tail_r)]:
        draw.line([seg[0][0], seg[0][1], seg[1][0], seg[1][1]], fill=WHITE, width=2)

    # Camera aim arrow (yellow, track + 15°)
    cam_rad = math.radians(track_deg + 15)
    cam_len = int(cr * 0.62)
    cax = int(ccx + cam_len * math.sin(cam_rad))
    cay = int(ccy - cam_len * math.cos(cam_rad))
    draw.line([ccx, ccy, cax, cay], fill=BLACK, width=4)
    draw.line([ccx, ccy, cax, cay], fill=YELLOW, width=2)
    # arrowhead
    ha = 25
    for fill_c, lw in [(BLACK, 4), (YELLOW, 2)]:
        for ang in [cam_rad + math.radians(180 - ha), cam_rad + math.radians(180 + ha)]:
            hx = int(cax + 8 * math.sin(ang))
            hy = int(cay - 8 * math.cos(ang))
            draw.line([cax, cay, hx, hy], fill=fill_c, width=lw)

    # Labels
    lbl_y = ccy + cr + 18
    lbl_x = ccx - cr
    draw_text_shadowed(draw, (lbl_x, lbl_y),       "Trk:045.0 (True)", font_sm, WHITE)
    draw_text_shadowed(draw, (lbl_x, lbl_y + 14),  "Cam:+15.0",        font_sm, YELLOW)

    # =========================================================================
    # CROSSHAIR — center, bright green
    # =========================================================================
    fcx = width  // 2
    fcy = height // 2
    arm = 20
    gap = 6

    for (p1, p2) in [
        ((fcx - arm - gap, fcy), (fcx - gap,       fcy)),
        ((fcx + gap,       fcy), (fcx + arm + gap, fcy)),
        ((fcx, fcy - arm - gap), (fcx, fcy - gap)),
        ((fcx, fcy + gap),       (fcx, fcy + arm + gap)),
    ]:
        draw.line([p1[0], p1[1], p2[0], p2[1]], fill=BLACK, width=3)
    for (p1, p2) in [
        ((fcx - arm - gap, fcy), (fcx - gap,       fcy)),
        ((fcx + gap,       fcy), (fcx + arm + gap, fcy)),
        ((fcx, fcy - arm - gap), (fcx, fcy - gap)),
        ((fcx, fcy + gap),       (fcx, fcy + arm + gap)),
    ]:
        draw.line([p1[0], p1[1], p2[0], p2[1]], fill=GREEN, width=2)

    # =========================================================================
    # TARGET PANEL — bottom-right, magenta
    # =========================================================================
    target_lines = [
        "\u2500\u2500 TARGET \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "Lat: 33.39100  Lon: -111.81900",
        "Elev: 1247 ft MSL",
        "Slant Range: 2340 ft",
        "456 W Desert Ave, Mesa AZ",
    ]

    max_tgt_w = max(text_width(draw, l, font_med) for l in target_lines)
    tgt_panel_h = len(target_lines) * line_h + pad * 2
    tgt_x = width  - max_tgt_w - pad * 2 - 10
    tgt_y = height - tgt_panel_h - 10

    draw_rounded_rectangle(draw,
                           [tgt_x - pad, tgt_y - pad,
                            tgt_x + max_tgt_w + pad, tgt_y + tgt_panel_h],
                           radius=4, fill=(0, 0, 0, 150))
    ty2 = tgt_y
    for line in target_lines:
        draw_text_shadowed(draw, (tgt_x, ty2), line, font_med, MAGENTA)
        ty2 += line_h

    # =========================================================================
    # Watermark
    # =========================================================================
    wm = "CYMBAL OSD Layout Preview"
    wm_bbox = draw.textbbox((0, 0), wm, font=font_sm)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text(((width - wm_w) // 2, height - 20), wm,
              fill=(180, 180, 180), font=font_sm)

    # =========================================================================
    # Save
    # =========================================================================
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, 'PNG')

    print(f"[OK] OSD mockup saved to: {output_path}")
    print(f"  Resolution: {width}x{height}")
    print(f"  Elements: aircraft panel (top-left, white), heading tape (top-center, green),")
    print(f"            compass (top-right, aircraft symbol), crosshair (center, green),")
    print(f"            target panel (bottom-right, magenta)")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate Cymbal OSD layout mockup')
    parser.add_argument('-o', '--output', default='docs/osd_mockup.png',
                        help='Output PNG file path (default: docs/osd_mockup.png)')
    parser.add_argument('-W', '--width',  type=int, default=640,
                        help='Frame width  (default: 640)')
    parser.add_argument('-H', '--height', type=int, default=480,
                        help='Frame height (default: 480)')

    args = parser.parse_args()
    create_osd_mockup(args.output, args.width, args.height)

