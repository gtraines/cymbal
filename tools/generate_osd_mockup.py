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
import os
import re
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
# Aircraft SVG polygon (same loader as overlay_controller.pyx)
# ---------------------------------------------------------------------------

def _load_aircraft_svg(svg_path=None):
    """Load a0.svg and return normalized polygon [(nx, ny)] or None."""
    if svg_path is None:
        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'cymbal', 'osd', 'a0.svg')
    try:
        with open(svg_path) as f:
            svg = f.read()
    except Exception:
        return None

    pm = re.search(r'<path[^>]+>', svg, re.DOTALL)
    if not pm:
        return None
    dm = re.search(r'\sd="([^"]+)"', pm.group(0), re.DOTALL)
    if not dm:
        return None
    path_d = dm.group(1)

    tm = re.search(r'transform="matrix\(([^)]+)\)"', svg)
    if not tm:
        return None
    ta, tb, tc, td, te, tf = [float(v) for v in tm.group(1).split(',')]

    def samp(p0, p1, p2, p3, n=8):
        pts = []
        for i in range(n + 1):
            t = i / n; mt = 1 - t
            pts.append((
                mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
                mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1],
            ))
        return pts

    toks = re.findall(r'[MLCZz]|[+-]?(?:\d+\.?\d*|\.\d+)', path_d)
    raw = []; cur = (0.0, 0.0); i = 0; cmd = None
    while i < len(toks):
        tk = toks[i]
        if tk in ('M', 'L', 'C', 'Z', 'z'):
            cmd = tk; i += 1; continue
        if cmd == 'M':
            cur = (float(toks[i]), float(toks[i+1])); raw.append(cur); i += 2
        elif cmd == 'L':
            cur = (float(toks[i]), float(toks[i+1])); raw.append(cur); i += 2
        elif cmd == 'C':
            p1 = (float(toks[i]),   float(toks[i+1]))
            p2 = (float(toks[i+2]), float(toks[i+3]))
            p3 = (float(toks[i+4]), float(toks[i+5]))
            raw.extend(samp(cur, p1, p2, p3, n=8)[1:]); cur = p3; i += 6
        else:
            i += 1

    if not raw:
        return None
    tx = [(ta*x + tc*y + te, tb*x + td*y + tf) for x, y in raw]
    return [((px - 100.0) / 100.0, (py - 100.0) / 100.0) for px, py in tx]


_AIRCRAFT_POLYGON = _load_aircraft_svg()

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
    """Draw text with a full 8-direction black outline for readability over any background."""
    for ox, oy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
        draw.text((x + ox, y + oy), text, fill=BLACK, font=font)
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
    """Green scrolling heading tape centered at cx. SYNC: matches overlay_controller.pyx."""
    tape_x = cx - tape_w // 2
    deg_per_px = fov / tape_w
    tick_top = y + 3
    long_h = max(14, tape_h // 3)   # was 12, +15%
    short_h = max(6,  tape_h // 6)

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
            lw = tw(draw, lbl, font_sm)   # bump to font_sm (+15%)
            lh2 = th(draw, lbl, font_sm)
            lx = xp - lw // 2
            ly = tick_top + long_h + 2
            put_text(draw, lx, ly, lbl, font_sm, GREEN)
            card = {0: "N", 90: "E", 180: "S", 270: "W"}.get(nd)
            if card:
                put_text(draw, xp - lw // 2, ly + lh2 + 2, card, font_sm, GREEN)
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

    # Heading value box (font_med for +15%)
    hdg_str = f"{int(heading_deg) % 360:03d}\u00b0"
    bx = draw.textbbox((0, 0), hdg_str, font=font_sm)
    box_w = bx[2] - bx[0] + 20
    box_h = bx[3] - bx[1] + 14
    bx1 = cx - box_w // 2
    by1 = y + tape_h + 3
    draw.rectangle([bx1, by1, bx1 + box_w, by1 + box_h], fill=DARK_BG)
    draw_rect_outline(draw, bx1, by1, bx1 + box_w, by1 + box_h, GREEN, 2)
    put_text(draw, bx1 + 10, by1 + 6, hdg_str, font_sm, GREEN)


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
        (0,   "N", YELLOW, True),   # N larger (+15%: font_med)
        (90,  "E", GRAY,   True),   # E/S/W also use font_med for +15%
        (180, "S", GRAY,   True),
        (270, "W", GRAY,   True),
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
        # Inside ring: offset (outer_r - 16) keeps labels within the disc
        tx = int(ccx + (cr - 16) * math.sin(rad))
        ty = int(ccy - (cr - 16) * math.cos(rad))
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

    # -------------------------------------------------------------------------
    # Aircraft symbol from SVG (a0.svg) — same _rot and mapping as pyx.
    # SVG: nx=stbd (right), ny=aft (down), nose at ny≈-1.
    # Body-frame: dx=fwd=-ny, dy=stbd=nx
    # -------------------------------------------------------------------------
    if _AIRCRAFT_POLYGON:
        # Build screen polygon at 75% of radius (−25%)
        _ac_r = cr * 0.75
        pts = []
        for (nx, ny) in _AIRCRAFT_POLYGON:
            dx = -ny
            dy =  nx
            x = int(ccx + dx * _ac_r * st + dy * _ac_r * ct2)
            y = int(ccy - dx * _ac_r * ct2 + dy * _ac_r * st)
            pts.append((x, y))

        # Black outline (shadow), then white fill
        for i in range(len(pts)):
            p1 = pts[i]; p2 = pts[(i+1) % len(pts)]
            draw.line([p1, p2], fill=BLACK, width=4)
        draw.polygon(pts, fill=WHITE)
    else:
        # Geometric fallback
        segs = [
            (rot( int(cr*0.50), 0),          rot(-int(cr*0.60), 0)),
            (rot( int(cr*0.05), 0),          rot(-int(cr*0.18), -int(cr*0.70))),
            (rot( int(cr*0.05), 0),          rot(-int(cr*0.18),  int(cr*0.70))),
            (rot(-int(cr*0.52), -int(cr*0.25)), rot(-int(cr*0.52), int(cr*0.25))),
        ]
        nose_pts = [rot(int(cr*0.78),0), rot(int(cr*0.50),-int(cr*0.09)), rot(int(cr*0.50),int(cr*0.09))]
        for a, b in segs:
            draw.line([a, b], fill=BLACK, width=6)
        draw.polygon(nose_pts, fill=BLACK)
        for a, b in segs:
            draw.line([a, b], fill=WHITE, width=3)
        draw.polygon(nose_pts, fill=WHITE)

    # Center pivot dot (drawn over aircraft, under camera arrow)
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
    # AIRCRAFT PANEL — top-left (no timestamps here), all UPPERCASE
    # -------------------------------------------------------------------------
    aircraft_lines = [
        "\u2500\u2500 AIRCRAFT \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "123 MAIN ST, PHOENIX AZ",
        "LAT: 33.44827  LON: -112.07400",
        "ALT AGL: 499 FT  GPS ALT: 1476 FT",
        "GNDSPD: 63.8 MPH  (TRUE)",
        "FIX: DGPS  SATS: 12",
    ]
    draw_aircraft_panel(draw, 12, 12 + lh, aircraft_lines, font_med, lh, pad)

    # -------------------------------------------------------------------------
    # DATETIME PANEL — bottom-left, UPPERCASE
    # -------------------------------------------------------------------------
    datetime_lines = [
        "2026-08-02 17:23:45 UTC",
        "2026-08-02 10:23:45 MST",
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
    # HEADING TAPE — top-center (40% wide, +15% height)
    # -------------------------------------------------------------------------
    tape_h = max(32, int(height * 0.08))    # was 0.07, +15%
    tape_w = max(400, int(width  * 0.40))   # was 0.30, widened to 40%
    tape_y = max(8,   int(height * 0.02))
    tape_cx = width // 2
    draw_heading_tape(draw, tape_cx, tape_y, tape_w, tape_h,
                      heading_deg=135.0, fov=30.0,
                      font_sm=font_med, font_xs=font_sm)   # bumped up one level for +15%

    # -------------------------------------------------------------------------
    # COMPASS WIDGET — top-right (moved inward to avoid clipping)
    # -------------------------------------------------------------------------
    cr  = max(52, int(min(width, height) * 0.08))
    ccx = width - cr - 90
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
    # TARGET PANEL — bottom-right, UPPERCASE
    # -------------------------------------------------------------------------
    target_lines = [
        "\u2500\u2500 TARGET \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "LAT: 33.39100  LON: -111.81900",
        "ELEV: 1247 FT MSL",
        "SLANT RANGE: 2340 FT",
        "456 W DESERT AVE, MESA AZ",
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
