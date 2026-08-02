#!/usr/bin/env python3
"""
Generate a visual mockup of the Cymbal OSD layout.

Creates a PNG image showing how the OSD elements appear overlaid on video.
Requires: pillow (pip install pillow)

Usage:
    python tools/generate_osd_mockup.py
    python tools/generate_osd_mockup.py -W 1280 -H 720   # HD (default)
    python tools/generate_osd_mockup.py -W 640  -H 480   # SD

Output:
    docs/osd_mockup.png - Visual representation of OSD layout

Elements rendered (matching overlay_controller.pyx exactly):
  Top-left   : Aircraft panel (white) — header, address, lat/lon,
                Alt AGL / GPS Alt (ft), GndSpd (mph, True), fix/sats
  Top-center : Scrolling heading tape (green) — ticks, cardinals, chevron, box
  Top-right  : Compass widget — aircraft HSI symbol, N/E/S/W, camera arrow
  Center     : Crosshair (green, four-arm with gap)
  Bot-left   : Datetime panel (white) — UTC + local date-timestamps
  Bot-right  : Target panel (magenta) — lat/lon, elevation, slant range, address

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
SYNC WARNING — this file must stay in sync with overlay_controller.pyx:
  - Aircraft HSI symbol: geometry and _rot formula
      See: cymbal/osd/overlay_controller.pyx  _draw_compass_widget()
  - Heading tape: dimensions, tick spacing, box size
      See: cymbal/osd/overlay_controller.pyx  _draw_heading_tape()
  - Crosshair: arm length, gap, line thickness
      See: cymbal/osd/overlay_controller.pyx  _draw_crosshair()
  - Panel content: aircraft/target/datetime line format
      See: cymbal/osd/overlay_controller.pyx  _build_*_lines()
After changing overlay_controller.pyx, re-run this tool and commit the PNG.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow not installed. Install with: pip install pillow")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Colour constants (RGB for Pillow — note OSD uses BGR for OpenCV)
# ---------------------------------------------------------------------------
WHITE   = (255, 255, 255)
BLACK   = (0,   0,   0)
GREEN   = (0,   230, 0)
MAGENTA = (255, 0,   255)
YELLOW  = (255, 200, 0)
GRAY    = (180, 180, 180)
DARK_BG = (0,   0,   0,   155)   # RGBA semi-transparent background


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def load_fonts(size_med=15, size_sm=12, size_xs=10):
    """Try to load a monospace font; fall back to PIL default."""
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for fp in candidates:
        try:
            return (
                ImageFont.truetype(fp, size_med),
                ImageFont.truetype(fp, size_sm),
                ImageFont.truetype(fp, size_xs),
            )
        except Exception:
            pass
    d = ImageFont.load_default()
    return d, d, d


def tw(draw, text, font):
    """Return pixel width of text."""
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def th(draw, text, font):
    """Return pixel height of text."""
    b = draw.textbbox((0, 0), text, font=font)
    return b[3] - b[1]


def put_text(draw, x, y, text, font, color):
    """Draw text with a black shadow (+1,+1) for video-readability."""
    draw.text((x + 1, y + 1), text, fill=BLACK, font=font)
    draw.text((x, y), text, fill=color, font=font)


def draw_panel_bg(draw, x, y, w, h, radius=4):
    """Draw a semi-transparent rounded-rect panel background."""
    r = radius
    draw.rectangle([x + r, y, x + w - r, y + h], fill=DARK_BG)
    draw.rectangle([x, y + r, x + w, y + h - r], fill=DARK_BG)
    for cx, cy in [(x, y), (x + w - 2*r, y),
                   (x, y + h - 2*r), (x + w - 2*r, y + h - 2*r)]:
        draw.ellipse([cx, cy, cx + 2*r, cy + 2*r], fill=DARK_BG)


def draw_rect_outline(draw, x1, y1, x2, y2, color, width=2):
    """Draw a rectangle outline with a thicker black shadow behind it."""
    draw.rectangle([x1 - 1, y1 - 1, x2 + 1, y2 + 1], outline=BLACK, width=width + 2)
    draw.rectangle([x1, y1, x2, y2], outline=color, width=width)


def put_text(draw, x, y, text, font, color):
    """Draw text with a doubled black shadow offset for video readability."""
    draw.text((x + 1, y + 1), text, fill=BLACK, font=font)
    draw.text((x + 1, y + 1), text, fill=BLACK, font=font)  # draw twice = denser shadow
    draw.text((x, y), text, fill=color, font=font)


# ---------------------------------------------------------------------------
# OSD element renderers
# ---------------------------------------------------------------------------

def draw_aircraft_panel(draw, x, y, lines, font, lh, pad):
    max_w = max(tw(draw, l, font) for l in lines)
    panel_h = len(lines) * lh + pad * 2
    draw_panel_bg(draw, x - pad, y - lh, max_w + pad * 2, panel_h + lh)
    for line in lines:
        put_text(draw, x, y, line, font, WHITE)
        y += lh


def draw_target_panel(draw, width, height, lines, font, lh, pad):
    max_w = max(tw(draw, l, font) for l in lines)
    panel_w = max_w + pad * 2
    panel_h = len(lines) * lh + pad * 2
    x = width  - panel_w - 12
    y = height - panel_h - 12
    draw_panel_bg(draw, x - pad, y - pad, panel_w, panel_h)
    for line in lines:
        put_text(draw, x, y, line, font, MAGENTA)
        y += lh


def draw_crosshair(draw, cx, cy, arm=36, gap=9):
    """Four-arm crosshair — arm and gap match overlay_controller.pyx _draw_crosshair."""
    for p1, p2 in [
        ((cx - arm - gap, cy), (cx - gap, cy)),
        ((cx + gap, cy),       (cx + arm + gap, cy)),
        ((cx, cy - arm - gap), (cx, cy - gap)),
        ((cx, cy + gap),       (cx, cy + arm + gap)),
    ]:
        draw.line([p1[0], p1[1], p2[0], p2[1]], fill=BLACK, width=6)
    for p1, p2 in [
        ((cx - arm - gap, cy), (cx - gap, cy)),
        ((cx + gap, cy),       (cx + arm + gap, cy)),
        ((cx, cy - arm - gap), (cx, cy - gap)),
        ((cx, cy + gap),       (cx, cy + arm + gap)),
    ]:
        draw.line([p1[0], p1[1], p2[0], p2[1]], fill=GREEN, width=3)


def draw_heading_tape(draw, cx, y, tape_w, tape_h, heading_deg,
                      fov=30.0, font_sm=None, font_xs=None):
    """Green scrolling heading tape centered at cx."""
    tape_x = cx - tape_w // 2
    deg_per_px = fov / tape_w
    tick_top = y + 3
    long_h = max(12, tape_h // 3)
    short_h = max(6, tape_h // 6)

    # Background + border
    draw.rectangle([tape_x, y, tape_x + tape_w, y + tape_h], fill=DARK_BG)
    draw_rect_outline(draw, tape_x, y, tape_x + tape_w, y + tape_h, GREEN, 2)

    for deg in range(int(heading_deg - fov/2 - 1), int(heading_deg + fov/2 + 2)):
        nd = deg % 360
        offset = nd - heading_deg
        if offset > 180:  offset -= 360
        if offset < -180: offset += 360
        if abs(offset) > fov / 2:
            continue
        xp = int(cx + offset / deg_per_px)
        if xp < tape_x or xp > tape_x + tape_w:
            continue

        if nd % 5 == 0:
            draw.line([xp + 1, tick_top + 1, xp + 1, tick_top + long_h + 1],
                      fill=BLACK, width=2)
            draw.line([xp, tick_top, xp, tick_top + long_h], fill=GREEN, width=2)
            lbl = f"{nd:03d}"
            lw = tw(draw, lbl, font_xs)
            lh2 = th(draw, lbl, font_xs)
            lx = xp - lw // 2
            ly = tick_top + long_h + 2
            put_text(draw, lx, ly, lbl, font_xs, GREEN)
            card = {0: "N", 90: "E", 180: "S", 270: "W"}.get(nd)
            if card:
                put_text(draw, xp - lw // 2, ly + lh2 + 2, card, font_xs, GREEN)
        else:
            draw.line([xp + 1, tick_top + 1, xp + 1, tick_top + short_h + 1],
                      fill=BLACK, width=1)
            draw.line([xp, tick_top, xp, tick_top + short_h], fill=GREEN, width=1)

    # Center chevron
    chev_y = y + tape_h - 2
    chev_s = max(7, tape_h // 5)
    draw.polygon([(cx, chev_y), (cx - chev_s, chev_y - chev_s),
                  (cx + chev_s, chev_y - chev_s)], fill=BLACK)
    draw.polygon([(cx, chev_y - 1), (cx - chev_s + 1, chev_y - chev_s + 1),
                  (cx + chev_s - 1, chev_y - chev_s + 1)], fill=GREEN)

    # Heading value box (below tape, larger padding)
    hdg_str = f"{int(heading_deg) % 360:03d}\u00b0"
    bx = draw.textbbox((0, 0), hdg_str, font=font_sm)
    box_w = bx[2] - bx[0] + 18
    box_h = bx[3] - bx[1] + 12
    bx1 = cx - box_w // 2
    by1 = y + tape_h + 3
    draw.rectangle([bx1, by1, bx1 + box_w, by1 + box_h], fill=DARK_BG)
    draw_rect_outline(draw, bx1, by1, bx1 + box_w, by1 + box_h, GREEN, 2)
    put_text(draw, bx1 + 9, by1 + 5, hdg_str, font_sm, GREEN)


def draw_compass(draw, ccx, ccy, cr, track_deg, cam_yaw,
                 font_med, font_sm, font_xs):
    """
    Compass widget: HSI-style aircraft silhouette + camera arrow + N/E/S/W labels.

    SYNC: geometry and _rot formula must match overlay_controller.pyx
          _draw_compass_widget() exactly.

    Body-frame convention for rot(dx, dy):
      dx > 0 = forward (nose/heading direction on screen)
      dy > 0 = starboard (right wing)
    Verification at track_deg=0: rot(+r,0) -> (ccx, ccy-r) = north/up  OK
    Drawing order: ring -> cardinals -> aircraft -> camera arrow (on top).
    """

    # Background disc
    draw.ellipse([ccx - cr - 14, ccy - cr - 14,
                  ccx + cr + 14, ccy + cr + 14], fill=DARK_BG)

    # Ring — shadow then fill (thicker)
    draw.ellipse([ccx - cr - 1, ccy - cr - 1, ccx + cr + 1, ccy + cr + 1],
                 outline=BLACK, width=5)
    draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr], outline=GRAY, width=3)

    # Cardinal ticks + labels
    for angle, lbl, color, bold in [
        (0,   "N", YELLOW, True),
        (90,  "E", GRAY,   False),
        (180, "S", GRAY,   False),
        (270, "W", GRAY,   False),
    ]:
        rad = math.radians(angle)
        ir = cr - 9
        # Shadow tick
        draw.line([int(ccx + ir * math.sin(rad)), int(ccy - ir * math.cos(rad)),
                   int(ccx + cr * math.sin(rad)), int(ccy - cr * math.cos(rad))],
                  fill=BLACK, width=5)
        # Coloured tick
        draw.line([int(ccx + ir * math.sin(rad)), int(ccy - ir * math.cos(rad)),
                   int(ccx + cr * math.sin(rad)), int(ccy - cr * math.cos(rad))],
                  fill=GRAY, width=3)
        font = font_med if bold else font_sm
        tx = int(ccx + (cr + 14) * math.sin(rad))
        ty = int(ccy - (cr + 14) * math.cos(rad))
        lw2 = tw(draw, lbl, font)
        lh2 = th(draw, lbl, font)
        put_text(draw, tx - lw2 // 2, ty - lh2 // 2, lbl, font, color)

    # -------------------------------------------------------------------------
    # HSI-style aircraft silhouette
    # SYNC with overlay_controller.pyx _draw_compass_widget():
    #   rot(dx=fwd, dy=stbd) — same formula as _rot() in the Cython file
    # -------------------------------------------------------------------------
    tr = math.radians(track_deg)
    st = math.sin(tr)
    ct2 = math.cos(tr)

    def rot(dx, dy):
        """Body-frame (dx=fwd, dy=stbd) -> screen coords. Matches Cython _rot."""
        return (int(ccx + dx * st + dy * ct2),
                int(ccy - dx * ct2 + dy * st))

    # Correct geometry (dx=forward, dy=starboard):
    nose_tip = rot( int(cr * 0.78),  0)
    nose_l   = rot( int(cr * 0.50), -int(cr * 0.09))
    nose_r   = rot( int(cr * 0.50),  int(cr * 0.09))
    fus_top  = rot( int(cr * 0.50),  0)
    fus_bot  = rot(-int(cr * 0.60),  0)
    wing_fwd = rot( int(cr * 0.05),  0)
    wl       = rot(-int(cr * 0.18), -int(cr * 0.70))
    wr       = rot(-int(cr * 0.18),  int(cr * 0.70))
    stab_l   = rot(-int(cr * 0.52), -int(cr * 0.25))
    stab_r   = rot(-int(cr * 0.52),  int(cr * 0.25))

    segs = [
        (fus_top, fus_bot),
        (wing_fwd, wl),
        (wing_fwd, wr),
        (stab_l, stab_r),
    ]

    # Shadow pass (black, thick)
    for a, b in segs:
        draw.line([a[0]+1, a[1]+1, b[0]+1, b[1]+1], fill=BLACK, width=6)
    draw.polygon([nose_tip, nose_l, nose_r], fill=BLACK, outline=BLACK)

    # Fill pass (white, thinner)
    for a, b in segs:
        draw.line([a[0], a[1], b[0], b[1]], fill=WHITE, width=3)
    draw.polygon([nose_tip, nose_l, nose_r], fill=WHITE, outline=WHITE)

    # Center pivot dot
    draw.ellipse([ccx-5, ccy-5, ccx+5, ccy+5], fill=BLACK)
    draw.ellipse([ccx-4, ccy-4, ccx+4, ccy+4], fill=WHITE)

    # -------------------------------------------------------------------------
    # Camera aim arrow — drawn LAST so it is always on top
    # -------------------------------------------------------------------------
    cam_rad = math.radians(track_deg + cam_yaw)
    cam_len = int(cr * 0.65)
    cax = int(ccx + cam_len * math.sin(cam_rad))
    cay = int(ccy - cam_len * math.cos(cam_rad))

    draw.line([ccx+1, ccy+1, cax+1, cay+1], fill=BLACK, width=6)
    draw.line([ccx, ccy, cax, cay], fill=YELLOW, width=3)

    for delta in [150, -150]:
        ha = math.radians(delta)
        hx = int(cax + 11 * math.sin(cam_rad + ha))
        hy = int(cay - 11 * math.cos(cam_rad + ha))
        draw.line([cax+1, cay+1, hx+1, hy+1], fill=BLACK, width=6)
        draw.line([cax, cay, hx, hy], fill=YELLOW, width=3)

    # Labels (left-aligned below disc)
    lbl_x = ccx - cr
    lbl_y = ccy + cr + 16
    put_text(draw, lbl_x, lbl_y,      f"Trk:{track_deg:05.1f} (True)", font_sm, WHITE)
    put_text(draw, lbl_x, lbl_y + 16, f"Cam:+{cam_yaw:05.1f}",         font_sm, YELLOW)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def create_osd_mockup(output_path="docs/osd_mockup.png", width=1280, height=720):
    """Create a full OSD layout mockup at the given resolution."""

    img  = Image.new('RGB', (width, height), color='#4a7ba7')
    draw = ImageDraw.Draw(img, 'RGBA')

    # Background: sky gradient + ground strip
    for y in range(height):
        a = int(30 * y / height)
        draw.rectangle([0, y, width, y + 1], fill=(70, 100, 130, a))
    for i in range(30):
        y_off = int(height * 0.62 + i * 18)
        if y_off < height:
            draw.rectangle([0, y_off, width, y_off + 10], fill=(55, 85, 65, 35))

    # Scale fonts to resolution (base at 1280x720), +10% bump for legibility
    scale = min(width / 1280, height / 720)
    font_med, font_sm, font_xs = load_fonts(
        size_med=max(12, int(18 * scale)),   # was 16
        size_sm =max(10, int(15 * scale)),   # was 13
        size_xs =max(9,  int(12 * scale)),   # was 11
    )

    lh  = max(20, int(25 * scale))   # line height (was 22)
    pad = max(7,  int(10 * scale))   # panel padding (was 9)

    # -------------------------------------------------------------------------
    # AIRCRAFT PANEL — top-left (no timestamps here)
    # -------------------------------------------------------------------------
    aircraft_lines = [
        "\u2500\u2500 AIRCRAFT \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "123 Main St, Phoenix AZ",
        "Lat: 33.44827  Lon: -112.07400",
        "Alt AGL: 499 ft  GPS Alt: 1476 ft",
        "GndSpd: 63.8 mph  (True)",
        "Fix: DGPS  Sats: 12",
    ]
    draw_aircraft_panel(draw, 12, 12 + lh, aircraft_lines, font_med, lh, pad)

    # -------------------------------------------------------------------------
    # DATETIME PANEL — bottom-left
    # -------------------------------------------------------------------------
    datetime_lines = [
        "2026-08-01 17:23:45 UTC",
        "2026-08-01 10:23:45 MST",
    ]
    max_dt_w = max(tw(draw, l, font_med) for l in datetime_lines)
    dt_panel_h = len(datetime_lines) * lh + pad * 2
    dt_x = 12
    dt_y = height - dt_panel_h - 12
    draw_panel_bg(draw, dt_x - pad, dt_y - pad, max_dt_w + pad * 2, dt_panel_h)
    ty_dt = dt_y
    for line in datetime_lines:
        put_text(draw, dt_x, ty_dt, line, font_med, WHITE)
        ty_dt += lh

    # -------------------------------------------------------------------------
    # HEADING TAPE — top-center
    # -------------------------------------------------------------------------
    tape_h = max(28, int(height * 0.07))
    tape_w = max(220, int(width  * 0.30))
    tape_y = max(8,   int(height * 0.02))
    tape_cx = width // 2
    draw_heading_tape(draw, tape_cx, tape_y, tape_w, tape_h,
                      heading_deg=135.0, fov=30.0,
                      font_sm=font_sm, font_xs=font_xs)

    # -------------------------------------------------------------------------
    # COMPASS WIDGET — top-right (moved inward to avoid clipping)
    # -------------------------------------------------------------------------
    cr  = max(52, int(min(width, height) * 0.08))   # +10% from 0.07
    ccx = width - cr - 90      # leave room for labels below
    ccy = cr + 22
    draw_compass(draw, ccx, ccy, cr,
                 track_deg=45.0, cam_yaw=15.0,
                 font_med=font_med, font_sm=font_sm, font_xs=font_xs)

    # -------------------------------------------------------------------------
    # CROSSHAIR — frame center (arm/gap match overlay_controller.pyx values)
    # -------------------------------------------------------------------------
    arm = max(28, int(min(width, height) * 0.045))
    gap = max(8,  int(min(width, height) * 0.014))
    draw_crosshair(draw, width // 2, height // 2, arm=arm, gap=gap)

    # -------------------------------------------------------------------------
    # TARGET PANEL — bottom-right
    # -------------------------------------------------------------------------
    target_lines = [
        "\u2500\u2500 TARGET \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "Lat: 33.39100  Lon: -111.81900",
        "Elev: 1247 ft MSL",
        "Slant Range: 2340 ft",
        "456 W Desert Ave, Mesa AZ",
    ]
    draw_target_panel(draw, width, height, target_lines, font_med, lh, pad)

    # -------------------------------------------------------------------------
    # Watermark
    # -------------------------------------------------------------------------
    wm = "CYMBAL OSD Layout Preview"
    ww = tw(draw, wm, font_sm)
    draw.text(((width - ww) // 2, height - lh - 4), wm,
              fill=(180, 180, 180), font=font_sm)

    # -------------------------------------------------------------------------
    # Save
    # -------------------------------------------------------------------------
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, 'PNG')
    print(f"[OK] OSD mockup saved to: {out}  ({width}x{height})")
    print("     Elements: aircraft panel, heading tape (green), compass (aircraft symbol),")
    print("               crosshair (green), target panel (magenta)")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate Cymbal OSD layout mockup')
    parser.add_argument('-o', '--output', default='docs/osd_mockup.png')
    parser.add_argument('-W', '--width',  type=int, default=1280)
    parser.add_argument('-H', '--height', type=int, default=720)
    args = parser.parse_args()

    create_osd_mockup(args.output, args.width, args.height)
