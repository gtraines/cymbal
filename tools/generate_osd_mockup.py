#!/usr/bin/env python3
"""
Generate a visual mockup of the Cymbal OSD layout.

Creates a PNG image showing how the OSD elements appear overlaid on video.
Requires: pillow (pip install pillow)

Usage:
    python tools/generate_osd_mockup.py
    
Output:
    docs/osd_mockup.png - Visual representation of OSD layout
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow not installed")
    print("Install with: pip install pillow")
    sys.exit(1)


def draw_rounded_rectangle(draw, xy, radius, fill, outline=None, width=1):
    """Draw a rectangle with rounded corners."""
    x1, y1, x2, y2 = xy
    
    # Draw main rectangles
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)
    
    # Draw corner circles
    draw.ellipse([x1, y1, x1 + 2*radius, y1 + 2*radius], fill=fill, outline=outline, width=width)
    draw.ellipse([x2 - 2*radius, y1, x2, y1 + 2*radius], fill=fill, outline=outline, width=width)
    draw.ellipse([x1, y2 - 2*radius, x1 + 2*radius, y2], fill=fill, outline=outline, width=width)
    draw.ellipse([x2 - 2*radius, y2 - 2*radius, x2, y2], fill=fill, outline=outline, width=width)


def create_osd_mockup(output_path="docs/osd_mockup.png", width=640, height=480):
    """
    Create a visual mockup of the OSD layout.
    
    Args:
        output_path: Where to save the output PNG
        width: Frame width in pixels
        height: Frame height in pixels
    """
    
    # Create base image with a simulated aerial view background
    img = Image.new('RGB', (width, height), color='#4a7ba7')
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # Add a subtle gradient to simulate sky/ground
    for y in range(height):
        alpha = int(30 * (y / height))
        draw.rectangle([0, y, width, y+1], fill=(70, 100, 130, alpha))
    
    # Add "terrain" pattern for realism
    for i in range(20):
        y_offset = int(height * 0.6 + i * 15)
        if y_offset < height:
            draw.rectangle([0, y_offset, width, y_offset+8], 
                          fill=(60, 90, 70, 40))
    
    # Load or create a simple font
    try:
        # Try to load a system monospace font
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 11)
    except:
        # Fallback to default font
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # ========================================================================
    # TEXT INFO BOX (Top-left)
    # ========================================================================
    
    text_x = 10
    text_y = 10
    line_height = 22
    padding = 8
    
    # Text content
    text_lines = [
        "17:23:45 UTC",
        "123 Main St, Phoenix AZ",
        "Lat: 33.44827  Lon: -112.07400",
        "Alt AGL: 152.3 m",
        "GndSpd: 28.5 m/s",
        "Fix: DGPS  Sats: 12",
    ]
    
    # Measure text box size
    max_width = 0
    for line in text_lines:
        bbox = draw.textbbox((0, 0), line, font=font_medium)
        line_width = bbox[2] - bbox[0]
        max_width = max(max_width, line_width)
    
    box_height = len(text_lines) * line_height + padding * 2
    box_width = max_width + padding * 2
    
    # Draw semi-transparent background
    draw_rounded_rectangle(
        draw,
        [text_x - padding, text_y - padding, 
         text_x + max_width + padding, text_y + box_height - padding],
        radius=4,
        fill=(0, 0, 0, 140),  # Semi-transparent black
    )
    
    # Draw text lines
    current_y = text_y
    for line in text_lines:
        draw.text((text_x, current_y), line, fill='white', font=font_medium)
        current_y += line_height
    
    # ========================================================================
    # COMPASS WIDGET (Top-right)
    # ========================================================================
    
    compass_radius = 45
    cx = width - compass_radius - 15
    cy = compass_radius + 15
    
    # Background disc
    draw.ellipse(
        [cx - compass_radius - 12, cy - compass_radius - 12,
         cx + compass_radius + 12, cy + compass_radius + 12],
        fill=(0, 0, 0, 140)
    )
    
    # Outer ring
    ring_color = (180, 180, 180)
    draw.ellipse(
        [cx - compass_radius, cy - compass_radius,
         cx + compass_radius, cy + compass_radius],
        outline=ring_color,
        width=2
    )
    
    # Cardinal marks (N, E, S, W)
    import math
    cardinal_angles = [0, 90, 180, 270]  # N, E, S, W
    cardinal_labels = ['N', 'E', 'S', 'W']
    
    for angle, label in zip(cardinal_angles, cardinal_labels):
        rad = math.radians(angle)
        
        # Tick marks
        inner_r = compass_radius - 5
        outer_r = compass_radius
        
        ix = int(cx + inner_r * math.sin(rad))
        iy = int(cy - inner_r * math.cos(rad))
        ox = int(cx + outer_r * math.sin(rad))
        oy = int(cy - outer_r * math.cos(rad))
        
        draw.line([ix, iy, ox, oy], fill=ring_color, width=2)
        
        # North label
        if label == 'N':
            tx = int(cx + (outer_r + 12) * math.sin(rad))
            ty = int(cy - (outer_r + 12) * math.cos(rad))
            bbox = draw.textbbox((0, 0), label, font=font_small)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            draw.text((tx - text_width//2, ty - text_height//2), 
                     label, fill=ring_color, font=font_small)
    
    # Aircraft track arrow (white, pointing NE at 45°)
    track_deg = 45
    track_rad = math.radians(track_deg)
    arrow_len = int(compass_radius * 0.82)
    
    ax = int(cx + arrow_len * math.sin(track_rad))
    ay = int(cy - arrow_len * math.cos(track_rad))
    
    # Main arrow line
    draw.line([cx, cy, ax, ay], fill='white', width=3)
    
    # Arrow head
    head_len = 8
    head_angle = 25
    angle1 = track_rad + math.radians(180 - head_angle)
    angle2 = track_rad + math.radians(180 + head_angle)
    
    hx1 = int(ax + head_len * math.sin(angle1))
    hy1 = int(ay - head_len * math.cos(angle1))
    hx2 = int(ax + head_len * math.sin(angle2))
    hy2 = int(ay - head_len * math.cos(angle2))
    
    draw.polygon([ax, ay, hx1, hy1, hx2, hy2], fill='white')
    
    # Camera aim arrow (yellow/cyan, offset +15° from track)
    cam_yaw = 15
    cam_deg = track_deg + cam_yaw
    cam_rad = math.radians(cam_deg)
    cam_len = int(compass_radius * 0.62)
    
    cax = int(cx + cam_len * math.sin(cam_rad))
    cay = int(cy - cam_len * math.cos(cam_rad))
    
    cam_color = (255, 255, 0)  # Yellow
    draw.line([cx, cy, cax, cay], fill=cam_color, width=2)
    
    # Camera arrow head
    cam_head_len = 7
    angle1 = cam_rad + math.radians(180 - head_angle)
    angle2 = cam_rad + math.radians(180 + head_angle)
    
    chx1 = int(cax + cam_head_len * math.sin(angle1))
    chy1 = int(cay - cam_head_len * math.cos(angle1))
    chx2 = int(cax + cam_head_len * math.sin(angle2))
    chy2 = int(cay - cam_head_len * math.cos(angle2))
    
    draw.polygon([cax, cay, chx1, chy1, chx2, chy2], fill=cam_color)
    
    # Labels below compass
    label_y = cy + compass_radius + 16
    label_x = cx - compass_radius
    
    draw.text((label_x, label_y), "Trk:045.0", fill='white', font=font_small)
    label_y += 14
    draw.text((label_x, label_y), "Cam:+15.0", fill=cam_color, font=font_small)
    
    # ========================================================================
    # Add title/watermark
    # ========================================================================
    
    title_text = "CYMBAL OSD Layout Preview"
    bbox = draw.textbbox((0, 0), title_text, font=font_medium)
    title_width = bbox[2] - bbox[0]
    title_x = (width - title_width) // 2
    title_y = height - 30
    
    draw.text((title_x, title_y), title_text, fill=(200, 200, 200), font=font_medium)
    
    # ========================================================================
    # Save image
    # ========================================================================
    
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    img.save(output_path, 'PNG')
    print(f"✓ OSD mockup saved to: {output_path}")
    print(f"  Resolution: {width}×{height}")
    print(f"  Elements: Text info box (top-left), Compass widget (top-right)")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate Cymbal OSD layout mockup')
    parser.add_argument('-o', '--output', default='docs/osd_mockup.png',
                       help='Output PNG file path (default: docs/osd_mockup.png)')
    parser.add_argument('-W', '--width', type=int, default=640,
                       help='Frame width (default: 640)')
    parser.add_argument('-H', '--height', type=int, default=480,
                       help='Frame height (default: 480)')
    
    args = parser.parse_args()
    
    create_osd_mockup(args.output, args.width, args.height)
