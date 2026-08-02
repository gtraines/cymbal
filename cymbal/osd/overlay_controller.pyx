"""
On-Screen Display Overlay

Annotates video frames (numpy arrays) with flight telemetry using OpenCV
drawing primitives. Designed to work headlessly — it operates on frame
buffers without requiring a display or GUI server.

Library choice: OpenCV (cv2) drawing primitives.
  - Already a project dependency (opencv-python-headless).
  - cv2.putText() and cv2.rectangle() are fast in-place operations on numpy
    arrays with negligible CPU overhead (<1ms per frame at 640×480).
  - Alternatives (pygame, PIL) would add a separate dependency and a heavier
    rendering pipeline; cv2 keeps everything in one library.

Layout:
  Top-left  — Aircraft panel (position, altitude in ft, speed in mph, fix).
  Top-center — Scrolling heading tape (bright green), camera heading box.
  Top-right  — Compass widget (aircraft symbol + camera arrow, north-up).
  Center     — Crosshair (bright green) with center gap.
  Bottom-right — Target panel (magenta), shown only when a POI is locked.

Units:
  All internal values and IPC messages stay in SI (metres, m/s).
  Display conversions happen only inside _build_aircraft_lines() and
  _build_target_lines() using the module-level _M_TO_FT / _MS_TO_MPH constants.

Usage:
    osd = OSDOverlay(config.osd)
    osd.initialize()
    osd.update_telemetry(lat, lon, alt_agl, groundspeed, address,
                         fix_quality, satellites, sbus_channels,
                         track_degrees, camera_yaw_deg, alt_msl=alt_msl)
    osd.update_target(poi_locked, poi_lat, poi_lon, poi_alt_msl,
                      slant_range_m, poi_address)
    # In camera loop:
    osd.render_frame(frame)   # annotates frame in-place
    osd.close()
"""

import datetime
import logging
import math
import os as _os_mod
import re as _re_mod

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger(__name__)

# OpenCV font
_FONT = None  # set in initialize() once cv2 is available

_NAN = float('nan')

# Unit conversion factors (SI → Imperial, display-only)
_M_TO_FT   = 3.28084
_MS_TO_MPH = 2.23694

# OSD colour palette (BGR)
_WHITE   = (255, 255, 255)
_BLACK   = (0,   0,   0)
_GREEN   = (0,   255, 0)    # heading tape, crosshair
_MAGENTA = (255, 0,   255)  # target panel
_YELLOW  = (0,   215, 255)  # compass N label, camera arrow

# ---------------------------------------------------------------------------
# Aircraft SVG silhouette — loaded from cymbal/osd/a0.svg at import time.
#
# _AIRCRAFT_POLYGON is a list of (nx, ny) normalized coords where:
#   nx ∈ [-1, 1]  : lateral (positive = starboard/right)
#   ny ∈ [-1, 1]  : longitudinal (positive = aft, negative = forward/nose)
#
# Rendering body-frame mapping (same _rot convention used below):
#   dx = -ny * radius   (forward = negative ny)
#   dy =  nx * radius   (starboard = positive nx)
#
# IMPORTANT: generate_osd_mockup.py must use the SAME SVG and mapping.
#            Run tools/generate_osd_mockup.py after any SVG change.
# ---------------------------------------------------------------------------

def _load_aircraft_svg():
    """Parse cymbal/osd/a0.svg → normalized polygon [(nx, ny), ...]."""
    try:
        svg_path = _os_mod.path.join(
            _os_mod.path.dirname(_os_mod.path.abspath(__file__)), 'a0.svg')
        with open(svg_path) as _f:
            _svg = _f.read()
    except Exception:
        return None

    _path_m = _re_mod.search(r'<path[^>]+>', _svg, _re_mod.DOTALL)
    if not _path_m:
        return None
    _d_m = _re_mod.search(r'\sd="([^"]+)"', _path_m.group(0), _re_mod.DOTALL)
    if not _d_m:
        return None
    _path_d = _d_m.group(1)

    _t_m = _re_mod.search(r'transform="matrix\(([^)]+)\)"', _svg)
    if not _t_m:
        return None
    _ta, _tb, _tc, _td, _te, _tf = [float(v) for v in _t_m.group(1).split(',')]

    def _samp(p0, p1, p2, p3, n=8):
        pts = []
        for _i in range(n + 1):
            _t = _i / n; _mt = 1 - _t
            pts.append((
                _mt**3*p0[0] + 3*_mt**2*_t*p1[0] + 3*_mt*_t**2*p2[0] + _t**3*p3[0],
                _mt**3*p0[1] + 3*_mt**2*_t*p1[1] + 3*_mt*_t**2*p2[1] + _t**3*p3[1],
            ))
        return pts

    _toks = _re_mod.findall(r'[MLCZz]|[+-]?(?:\d+\.?\d*|\.\d+)', _path_d)
    _raw = []; _cur = (0.0, 0.0); _i = 0; _cmd = None
    while _i < len(_toks):
        _tk = _toks[_i]
        if _tk in ('M', 'L', 'C', 'Z', 'z'):
            _cmd = _tk; _i += 1; continue
        if _cmd == 'M':
            _cur = (float(_toks[_i]), float(_toks[_i+1]))
            _raw.append(_cur); _i += 2
        elif _cmd == 'L':
            _cur = (float(_toks[_i]), float(_toks[_i+1]))
            _raw.append(_cur); _i += 2
        elif _cmd == 'C':
            _p1 = (float(_toks[_i]),   float(_toks[_i+1]))
            _p2 = (float(_toks[_i+2]), float(_toks[_i+3]))
            _p3 = (float(_toks[_i+4]), float(_toks[_i+5]))
            _raw.extend(_samp(_cur, _p1, _p2, _p3, n=8)[1:])
            _cur = _p3; _i += 6
        else:
            _i += 1

    if not _raw:
        return None

    _tx = [(_ta*x + _tc*y + _te, _tb*x + _td*y + _tf) for x, y in _raw]
    return [((px - 100.0) / 100.0, (py - 100.0) / 100.0) for px, py in _tx]


_AIRCRAFT_POLYGON = _load_aircraft_svg()


cdef class OSDOverlay:
    """
    Telemetry OSD that annotates numpy video frames using OpenCV.

    All public fields are updated by update_telemetry() / update_target();
    render_frame() draws the cached values onto a frame buffer.  Both
    methods are safe to call from the same thread without locking.

    Args:
        config:   OSDConfig dataclass instance, or None for defaults.
        time_fn:  Callable returning a datetime.datetime for the timestamp
                  row.  Defaults to datetime.datetime.utcnow.  Override in
                  tests for deterministic output.
    """

    def __init__(self, config=None, time_fn=None):
        self.enabled = True
        self.font_scale = 0.72          # bumped from 0.65 for legibility
        self.font_thickness = 2
        self._text_color = (255, 255, 255)
        self._bg_color = (0, 0, 0)
        self.background_alpha = 0.5
        self.show_sbus_channels = False
        self.show_compass = True
        self.compass_radius = 45
        self.show_heading_tape = True
        self.heading_tape_height_pct = 0.07
        self.heading_tape_width_pct = 0.25
        self.heading_tape_fov_deg = 30.0

        self._video_sink = None
        self._time_fn = time_fn if time_fn is not None else datetime.datetime.utcnow

        # Local timezone for second timestamp line
        self.local_timezone = "America/Phoenix"
        self._local_tz      = None
        self._resolve_timezone()

        # Aircraft telemetry
        self.lat = _NAN
        self.lon = _NAN
        self.alt_agl = _NAN
        self.alt_msl = _NAN
        self.groundspeed_ms = _NAN
        self.address = "No fix"
        self.fix_quality = 0
        self.satellites = 0
        self.sbus_channels = []
        self.track_degrees = _NAN
        self.camera_yaw_deg = _NAN

        # Target / POI
        self.poi_locked     = False
        self.poi_lat        = _NAN
        self.poi_lon        = _NAN
        self.poi_alt_msl    = _NAN
        self.slant_range_ft = _NAN
        self.poi_address    = ""

        if config is not None:
            self._apply_config(config)

    def _apply_config(self, config):
        self.enabled = config.enabled
        self.font_scale = config.font_scale
        self.font_thickness = config.font_thickness
        self._text_color = tuple(config.text_color)
        self._bg_color = tuple(config.background_color)
        self.background_alpha = config.background_alpha
        self.show_sbus_channels = config.show_sbus_channels
        self.show_compass = config.show_compass
        self.compass_radius = config.compass_radius
        self.show_heading_tape = config.show_heading_tape
        self.heading_tape_height_pct = config.heading_tape_height_pct
        self.heading_tape_width_pct = config.heading_tape_width_pct
        self.heading_tape_fov_deg = config.heading_tape_fov_deg
        if hasattr(config, 'local_timezone'):
            self.local_timezone = config.local_timezone
        self._resolve_timezone()

    def _resolve_timezone(self):
        """Resolve self.local_timezone to a ZoneInfo instance, or None on failure."""
        tz = self.local_timezone
        if not tz or tz.upper() == "UTC":
            self._local_tz = None
            return
        try:
            from zoneinfo import ZoneInfo
            self._local_tz = ZoneInfo(tz)
        except Exception as e:
            logger.warning(
                f"OSDOverlay: unknown timezone '{tz}' ({e}); showing UTC only"
            )
            self._local_tz = None

    cpdef bint initialize(self, object video_sink=None):
        """
        Verify OpenCV is available and (optionally) attach a video sink.

        Args:
            video_sink: Optional VideoSink instance.  Defaults to HeadlessSink.

        Returns:
            True if OpenCV is usable, False otherwise.
        """
        global _FONT
        if cv2 is None:
            logger.error("OpenCV (cv2) not available; install opencv-python-headless")
            self.enabled = False
            return False
        _FONT = cv2.FONT_HERSHEY_SIMPLEX

        # Attach sink — default to headless
        if video_sink is not None:
            self._video_sink = video_sink
        else:
            try:
                from cymbal.video.headless_sink import HeadlessSink
                self._video_sink = HeadlessSink()
                self._video_sink.initialize()
            except Exception:
                self._video_sink = None

        logger.info("OSDOverlay initialized")
        return True

    cpdef void update_telemetry(self, double lat, double lon, double alt_agl,
                                double groundspeed, str address,
                                int fix_quality, int satellites,
                                object sbus_channels,
                                double track_degrees,
                                double camera_yaw_deg,
                                double alt_msl=_NAN):
        """
        Cache the latest aircraft telemetry for the next render_frame() call.

        All float arguments use SI units (metres, m/s).  Imperial conversions
        happen only in the display layer (_build_aircraft_lines).

        Args:
            lat:            Latitude in decimal degrees (NaN if no fix).
            lon:            Longitude in decimal degrees (NaN if no fix).
            alt_agl:        Altitude above ground level, metres (NaN if unknown).
            groundspeed:    Ground speed, m/s (NaN if unknown).
            address:        Nearest street address string.
            fix_quality:    GPS fix quality (0=none, 1=GPS, 2=DGPS).
            satellites:     Number of satellites in use.
            sbus_channels:  Sequence of 18 raw SBUS channel values for debug display.
            track_degrees:  GPS ground track, degrees from north clockwise (NaN if unknown).
            camera_yaw_deg: Camera yaw offset from aircraft nose in degrees
                            (positive = right, negative = left; NaN if unknown).
            alt_msl:        Altitude above mean sea level, metres (NaN if unknown).
        """
        self.lat = lat
        self.lon = lon
        self.alt_agl = alt_agl
        self.alt_msl = alt_msl
        self.groundspeed_ms = groundspeed
        self.address = address
        self.fix_quality = fix_quality
        self.satellites = satellites
        self.sbus_channels = sbus_channels
        self.track_degrees = track_degrees
        self.camera_yaw_deg = camera_yaw_deg

    cpdef void update_target(self, bint poi_locked, double poi_lat, double poi_lon,
                             double poi_alt_msl, double slant_range_m,
                             str poi_address):
        """
        Cache the latest target/POI data for the next render_frame() call.

        Args:
            poi_locked:    True when a target is actively locked.
            poi_lat:       Target latitude, decimal degrees (NaN if not locked).
            poi_lon:       Target longitude, decimal degrees (NaN if not locked).
            poi_alt_msl:   Target terrain elevation, metres MSL (NaN if unknown).
            slant_range_m: 3D aircraft→target distance, metres (NaN if unknown).
            poi_address:   Nearest street address at the target location.
        """
        self.poi_locked     = poi_locked
        self.poi_lat        = poi_lat
        self.poi_lon        = poi_lon
        self.poi_alt_msl    = poi_alt_msl
        # Convert slant range to feet for display
        if not math.isnan(slant_range_m):
            self.slant_range_ft = slant_range_m * _M_TO_FT
        else:
            self.slant_range_ft = _NAN
        self.poi_address    = poi_address

    cpdef void render_frame(self, object frame):
        """
        Annotate a video frame in-place with cached telemetry.

        Args:
            frame: A numpy ndarray (H × W × 3, uint8, BGR) from a camera.
                   If None, this method returns immediately.
        """
        cdef int fh, fw, cx, cy
        cdef double camera_heading

        if not self.enabled or cv2 is None or frame is None:
            return

        # 1. Aircraft panel — top-left
        self._draw_text_box(frame, self._build_aircraft_lines(), 10, 30)

        # 2. Datetime panel — bottom-left
        self._draw_datetime_panel(frame)

        # 3. Target panel — bottom-right (only when POI is locked)
        if self.poi_locked:
            self._draw_target_panel(frame)

        # 3. Crosshair — frame center, bright green
        self._draw_crosshair(frame)

        # 4. Compass widget — top-right
        if self.show_compass:
            fh, fw = frame.shape[:2]
            cx = fw - self.compass_radius - 15
            cy = self.compass_radius + 15
            self._draw_compass_widget(
                frame, cx, cy,
                self.compass_radius,
                self.track_degrees,
                self.camera_yaw_deg,
            )

        # 5. Heading tape — top-center (green)
        if self.show_heading_tape:
            camera_heading = _NAN
            if not math.isnan(self.track_degrees) and not math.isnan(self.camera_yaw_deg):
                camera_heading = (self.track_degrees + self.camera_yaw_deg) % 360.0
            if not math.isnan(camera_heading):
                self._draw_heading_tape(frame, camera_heading)

        # Forward to the attached video sink
        if self._video_sink is not None:
            self._video_sink.write_frame(frame)

    def _build_aircraft_lines(self):
        """Assemble the aircraft panel text lines (Imperial units for display)."""
        lines = []

        # Panel header
        lines.append("\u2500\u2500 AIRCRAFT \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        # Address
        lines.append(self.address or "Unknown address")

        # GPS position
        if not math.isnan(self.lat) and not math.isnan(self.lon):
            lines.append(f"Lat: {self.lat:.5f}  Lon: {self.lon:.5f}")
        else:
            lines.append("GPS: No fix")

        # Altitude AGL in feet + GPS altitude MSL in feet
        agl_str = f"{self.alt_agl * _M_TO_FT:.0f} ft" if not math.isnan(self.alt_agl) else "--"
        msl_str = f"{self.alt_msl * _M_TO_FT:.0f} ft" if not math.isnan(self.alt_msl) else "--"
        lines.append(f"Alt AGL: {agl_str}  GPS Alt: {msl_str}")

        # Groundspeed in mph + heading type label
        if not math.isnan(self.groundspeed_ms):
            spd_mph = self.groundspeed_ms * _MS_TO_MPH
            lines.append(f"GndSpd: {spd_mph:.1f} mph  (True)")
        else:
            lines.append("GndSpd: --")

        # Fix quality
        fix_str = {0: "No fix", 1: "GPS", 2: "DGPS"}.get(self.fix_quality, "?")
        lines.append(f"Fix: {fix_str}  Sats: {self.satellites}")

        # SBUS debug channels
        if self.show_sbus_channels and self.sbus_channels:
            ch = list(self.sbus_channels)[:16]
            row1 = "  ".join(f"{v:4d}" for v in ch[:8])
            row2 = "  ".join(f"{v:4d}" for v in ch[8:])
            lines.append(f"SBUS[1-8]:  {row1}")
            lines.append(f"SBUS[9-16]: {row2}")

        return lines

    # Keep _build_lines as an alias for backward compatibility
    def _build_lines(self):
        return self._build_aircraft_lines()

    def _build_target_lines(self):
        """Assemble the target panel text lines (Imperial units for display)."""
        if not self.poi_locked:
            return []

        lines = []
        lines.append("\u2500\u2500 TARGET \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        if not math.isnan(self.poi_lat) and not math.isnan(self.poi_lon):
            lines.append(f"Lat: {self.poi_lat:.5f}  Lon: {self.poi_lon:.5f}")
        else:
            lines.append("Lat: --  Lon: --")

        if not math.isnan(self.poi_alt_msl):
            elev_ft = self.poi_alt_msl * _M_TO_FT
            lines.append(f"Elev: {elev_ft:.0f} ft MSL")
        else:
            lines.append("Elev: --")

        if not math.isnan(self.slant_range_ft):
            lines.append(f"Slant Range: {self.slant_range_ft:.0f} ft")
        else:
            lines.append("Slant Range: --")

        if self.poi_address:
            lines.append(self.poi_address)

        return lines

    cdef void _draw_text_box(self, object frame, list lines, int x, int y,
                             object text_color=None):
        """Draw a semi-transparent background box and then render text lines."""
        cdef int max_width, w, h, total_height, pad, lh, bx1, by1, bx2, by2, fh, fw, ty
        cdef object overlay
        cdef object color

        color = text_color if text_color is not None else self._text_color

        pad = 8
        lh = int(30 * self.font_scale)

        # Measure the widest line
        max_width = 0
        for line in lines:
            (w, h), _ = cv2.getTextSize(
                line, _FONT, self.font_scale, self.font_thickness
            )
            if w > max_width:
                max_width = w

        total_height = lh * len(lines) + pad * 2
        bx1 = x - pad
        by1 = y - lh
        bx2 = x + max_width + pad
        by2 = y + total_height

        # Clamp to frame bounds
        fh, fw = frame.shape[:2]
        bx1 = max(0, bx1); by1 = max(0, by1)
        bx2 = min(fw, bx2); by2 = min(fh, by2)

        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (bx1, by1), (bx2, by2),
            self._bg_color,
            -1,
        )
        cv2.addWeighted(
            overlay, self.background_alpha,
            frame, 1.0 - self.background_alpha,
            0, frame,
        )

        # Text lines with shadow
        ty = y
        for line in lines:
            self._put_text_shadowed(frame, line, x, ty,
                                    self.font_scale, color, self.font_thickness)
            ty += lh

    cdef void _put_text_shadowed(self, object frame, str text, int x, int y,
                                  double scale, object color, int thickness):
        """
        Draw text with a 1-pixel black shadow offset to (+1, +1), then draw
        the text in `color` at (x, y).  This prevents washout over bright video.
        """
        cv2.putText(frame, text, (x + 1, y + 1), _FONT, scale,
                    _BLACK, thickness + 2, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), _FONT, scale,
                    color, thickness, cv2.LINE_AA)

    cdef void _draw_crosshair(self, object frame):
        """
        Draw a bright-green crosshair at the center of the frame.

        A small gap around the center keeps the reticle clean.
        """
        cdef int fh = frame.shape[0]
        cdef int fw = frame.shape[1]
        cdef int cx = fw // 2
        cdef int cy = fh // 2
        cdef int arm = 26   # length of each arm
        cdef int gap = 8    # gap between center and start of each arm

        # Shadow pass
        cv2.line(frame, (cx - arm - gap, cy), (cx - gap, cy), _BLACK, 5, cv2.LINE_AA)
        cv2.line(frame, (cx + gap, cy), (cx + arm + gap, cy), _BLACK, 5, cv2.LINE_AA)
        cv2.line(frame, (cx, cy - arm - gap), (cx, cy - gap), _BLACK, 5, cv2.LINE_AA)
        cv2.line(frame, (cx, cy + gap), (cx, cy + arm + gap), _BLACK, 5, cv2.LINE_AA)

        # Green lines
        cv2.line(frame, (cx - arm - gap, cy), (cx - gap, cy), _GREEN, 3, cv2.LINE_AA)
        cv2.line(frame, (cx + gap, cy), (cx + arm + gap, cy), _GREEN, 3, cv2.LINE_AA)
        cv2.line(frame, (cx, cy - arm - gap), (cx, cy - gap), _GREEN, 3, cv2.LINE_AA)
        cv2.line(frame, (cx, cy + gap), (cx, cy + arm + gap), _GREEN, 3, cv2.LINE_AA)

    cdef void _draw_target_panel(self, object frame):
        """Draw the target/POI information panel at the bottom-right."""
        cdef int fh = frame.shape[0]
        cdef int fw = frame.shape[1]
        cdef list lines = self._build_target_lines()

        if not lines:
            return

        cdef int lh  = int(30 * self.font_scale)
        cdef int pad = 8

        # Measure panel width
        cdef int max_width = 0
        cdef int w, h
        for line in lines:
            (w, h), _ = cv2.getTextSize(line, _FONT, self.font_scale, self.font_thickness)
            if w > max_width:
                max_width = w

        cdef int panel_height = lh * len(lines) + pad * 2
        cdef int panel_width  = max_width + pad * 2

        # Bottom-right placement (10 px margin from edges)
        cdef int x = fw - panel_width - 10
        cdef int y = fh - panel_height - 10 + lh  # y is baseline of first line

        self._draw_text_box(frame, lines, x, y, text_color=_MAGENTA)

    cdef void _draw_datetime_panel(self, object frame):
        """
        Draw the UTC and local date-timestamp panel at the bottom-left.

        Shows:
          YYYY-MM-DD HH:MM:SS UTC
          YYYY-MM-DD HH:MM:SS MST   (only when local_timezone is configured)
        """
        cdef int fh = frame.shape[0]
        cdef int fw = frame.shape[1]

        lines = []
        utc_dt = self._time_fn()
        lines.append(utc_dt.strftime("%Y-%m-%d %H:%M:%S UTC"))

        if self._local_tz is not None:
            try:
                utc_aware = utc_dt.replace(tzinfo=datetime.timezone.utc)
                local_dt  = utc_aware.astimezone(self._local_tz)
                tz_abbr   = local_dt.strftime("%Z")
                lines.append(local_dt.strftime(f"%Y-%m-%d %H:%M:%S {tz_abbr}"))
            except Exception:
                pass

        cdef int lh  = int(30 * self.font_scale)
        cdef int pad = 8
        cdef int panel_height = lh * len(lines) + pad * 2

        # Bottom-left placement (10 px margin)
        cdef int x = 10
        cdef int y = fh - panel_height - 10 + lh

        self._draw_text_box(frame, lines, x, y)

    cdef void _draw_compass_widget(self, object frame, int cx, int cy,
                                   int radius, double track_deg,
                                   double camera_yaw_deg):
        """
        Draw the compass widget: a ring with aircraft symbol and camera-aim arrow.

        The compass is north-up (geographic).
        - White detailed aircraft outline: fuselage + wings + tail, oriented to
          GPS ground track direction.
        - Yellow arrow: absolute camera aim direction (track + camera_yaw_deg).
        - Prominent "N" label at top of ring.
        - Tick marks at N / E / S / W.
        - Text labels below: Trk (True) and Cam offset.

        Args:
            frame:          BGR numpy frame (modified in-place).
            cx, cy:         Centre pixel of the compass circle.
            radius:         Outer radius of the compass ring in pixels.
            track_deg:      GPS ground track (degrees from north, clockwise).
                            NaN → aircraft symbol suppressed, ring dims.
            camera_yaw_deg: Camera yaw offset from nose (degrees, + = right).
                            NaN → yellow arrow suppressed.
        """
        cdef double pi = math.pi
        cdef double track_rad, cam_abs_rad
        cdef int cax, cay, ix, iy, ox, oy, tx, ty
        cdef int inner_r, outer_r, cam_len
        cdef bint have_track, have_cam
        cdef object bg_overlay
        cdef double card_rad
        cdef int i

        have_track = not math.isnan(track_deg)
        have_cam   = have_track and not math.isnan(camera_yaw_deg)

        # Background disc
        bg_overlay = frame.copy()
        cv2.circle(bg_overlay, (cx, cy), radius + 14, _BLACK, -1)
        cv2.addWeighted(bg_overlay, 0.58, frame, 0.42, 0, frame)

        # Ring — brighter when fix available, thicker
        ring_color = (200, 200, 200) if have_track else (70, 70, 70)
        cv2.circle(frame, (cx, cy), radius, _BLACK,     4, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), radius, ring_color, 3, cv2.LINE_AA)

        # Cardinal tick marks + prominent "N" label
        cardinal_angles = [0.0, 90.0, 180.0, 270.0]
        cardinal_labels = ["N", "E", "S", "W"]
        for i in range(4):
            card_rad = cardinal_angles[i] * pi / 180.0
            s = math.sin(card_rad)
            c = math.cos(card_rad)
            inner_r = radius - 8
            outer_r = radius
            ix = int(cx + inner_r * s)
            iy = int(cy - inner_r * c)
            ox = int(cx + outer_r * s)
            oy = int(cy - outer_r * c)
            cv2.line(frame, (ix, iy), (ox, oy), _BLACK,     4, cv2.LINE_AA)
            cv2.line(frame, (ix, iy), (ox, oy), ring_color, 3, cv2.LINE_AA)

            lbl = cardinal_labels[i]
            lscale = 0.60 if i == 0 else 0.42
            lthick = 2    if i == 0 else 1
            lcolor = _YELLOW if i == 0 else ring_color
            tx = int(cx + (outer_r + 12) * s) - 5
            ty = int(cy - (outer_r + 12) * c) + 5
            self._put_text_shadowed(frame, lbl, tx, ty, lscale, lcolor, lthick)

        # Aircraft symbol from SVG (a0.svg), falling back to geometric lines
        if have_track:
            track_rad = track_deg * pi / 180.0
            sin_t = math.sin(track_rad)
            cos_t = math.cos(track_rad)

            def _rot(dx, dy):
                """Rotate body-frame (dx=fwd, dy=stbd) to screen coords."""
                return (int(cx + dx * sin_t + dy * cos_t),
                        int(cy - dx * cos_t + dy * sin_t))

            import numpy as _np_sym

            if _AIRCRAFT_POLYGON is not None:
                # Build screen polygon: SVG nx=stbd, ny=aft (nose at ny=-1)
                # Body-frame: dx=fwd=-ny, dy=stbd=nx
                pts = [_rot(int(-ny * radius), int(nx * radius))
                       for nx, ny in _AIRCRAFT_POLYGON]
                arr = _np_sym.array(pts, dtype=_np_sym.int32)
                # Black outline shadow, then white fill
                cv2.polylines(frame, [arr], True, _BLACK, 4, cv2.LINE_AA)
                cv2.fillPoly(frame, [arr], _WHITE)
            else:
                # Geometric fallback (if SVG unavailable)
                nose_tip = _rot( int(radius * 0.78),  0)
                nose_l   = _rot( int(radius * 0.50), -int(radius * 0.09))
                nose_r   = _rot( int(radius * 0.50),  int(radius * 0.09))
                fus_top  = _rot( int(radius * 0.50),  0)
                fus_bot  = _rot(-int(radius * 0.60),  0)
                wing_fwd = _rot( int(radius * 0.05),  0)
                wl       = _rot(-int(radius * 0.18), -int(radius * 0.70))
                wr       = _rot(-int(radius * 0.18),  int(radius * 0.70))
                stab_l   = _rot(-int(radius * 0.52), -int(radius * 0.25))
                stab_r   = _rot(-int(radius * 0.52),  int(radius * 0.25))
                segs = [(fus_top, fus_bot), (wing_fwd, wl),
                        (wing_fwd, wr), (stab_l, stab_r)]
                for a, b in segs:
                    cv2.line(frame, a, b, _BLACK, 5, cv2.LINE_AA)
                cv2.fillPoly(frame,
                             [_np_sym.array([nose_tip, nose_l, nose_r],
                                            dtype=_np_sym.int32)], _BLACK)
                for a, b in segs:
                    cv2.line(frame, a, b, _WHITE, 3, cv2.LINE_AA)
                cv2.fillPoly(frame,
                             [_np_sym.array([nose_tip, nose_l, nose_r],
                                            dtype=_np_sym.int32)], _WHITE)

            # Center pivot dot
            cv2.circle(frame, (cx, cy), 4, _BLACK, -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 3, _WHITE, -1, cv2.LINE_AA)

        # Camera aim arrow (yellow)
        if have_cam:
            cam_abs_deg = track_deg + camera_yaw_deg
            cam_abs_rad = cam_abs_deg * pi / 180.0
            cam_len = int(radius * 0.62)
            cax = int(cx + cam_len * math.sin(cam_abs_rad))
            cay = int(cy - cam_len * math.cos(cam_abs_rad))
            cv2.arrowedLine(frame, (cx, cy), (cax, cay),
                            _BLACK, 5, cv2.LINE_AA, tipLength=0.33)
            cv2.arrowedLine(frame, (cx, cy), (cax, cay),
                            _YELLOW, 3, cv2.LINE_AA, tipLength=0.33)

        # Text labels below the ring
        label_y = cy + radius + 18
        label_x = cx - radius

        if have_track:
            trk_str = f"Trk:{track_deg:05.1f} (True)"
            self._put_text_shadowed(frame, trk_str, label_x, label_y,
                                    0.38, _WHITE, 1)
            label_y += 15

        if have_cam:
            sign    = "+" if camera_yaw_deg >= 0 else ""
            cam_str = f"Cam:{sign}{camera_yaw_deg:05.1f}"
            self._put_text_shadowed(frame, cam_str, label_x, label_y,
                                    0.38, _YELLOW, 1)

    cdef void _draw_heading_tape(self, object frame, double camera_heading_deg):
        """
        Draw horizontal scrolling heading tape at top center (bright green).

        Shows camera absolute heading with ±half-FOV field of view.
        Tick marks, numerical labels, and cardinal directions are all green
        with black shadows.  The center heading box is larger to fit the text.

        Args:
            frame:               BGR numpy array (H × W × 3).
            camera_heading_deg:  Absolute camera heading in degrees (0–360).
        """
        cdef int frame_height = frame.shape[0]
        cdef int frame_width  = frame.shape[1]

        cdef int tape_height = int(frame_height * self.heading_tape_height_pct)
        cdef int tape_width  = int(frame_width  * self.heading_tape_width_pct)
        cdef int tape_x = (frame_width - tape_width) // 2
        cdef int tape_y = int(frame_height * 0.02)

        if tape_height < 20 or tape_width < 100:
            return

        # Semi-transparent background
        cdef object overlay = frame.copy()
        cv2.rectangle(overlay, (tape_x, tape_y),
                      (tape_x + tape_width, tape_y + tape_height),
                      self._bg_color, -1)
        cv2.addWeighted(overlay, self.background_alpha,
                        frame, 1.0 - self.background_alpha, 0, frame)

        # Green border with shadow
        cv2.rectangle(frame, (tape_x - 1, tape_y - 1),
                      (tape_x + tape_width + 1, tape_y + tape_height + 1),
                      _BLACK, 3)
        cv2.rectangle(frame, (tape_x, tape_y),
                      (tape_x + tape_width, tape_y + tape_height),
                      _GREEN, 2)

        cdef double half_fov         = self.heading_tape_fov_deg / 2.0
        cdef double degrees_per_pixel = self.heading_tape_fov_deg / float(tape_width)
        cdef int tape_center_x = tape_x + tape_width // 2

        cdef int tick_y_top    = tape_y + 3
        cdef int short_tick_h  = 5
        cdef int long_tick_h   = 12
        cdef int tick_y_short  = tick_y_top + short_tick_h
        cdef int tick_y_long   = tick_y_top + long_tick_h

        cdef int deg
        cdef double angular_offset
        cdef int x_pos
        cdef str label_text
        cdef int text_width, text_height
        cdef int text_x, text_y
        cdef object text_size

        cdef int min_deg = int(camera_heading_deg - half_fov - 1)
        cdef int max_deg = int(camera_heading_deg + half_fov + 2)

        for deg in range(min_deg, max_deg + 1):
            normalized_deg = deg % 360

            angular_offset = normalized_deg - camera_heading_deg
            if angular_offset > 180:
                angular_offset -= 360
            elif angular_offset < -180:
                angular_offset += 360

            if abs(angular_offset) > half_fov:
                continue

            x_pos = int(tape_center_x + angular_offset / degrees_per_pixel)
            if x_pos < tape_x or x_pos > tape_x + tape_width:
                continue

            if normalized_deg % 5 == 0:
                # Shadow then green tick
                cv2.line(frame, (x_pos + 1, tick_y_top + 1), (x_pos + 1, tick_y_long + 1),
                         _BLACK, 2)
                cv2.line(frame, (x_pos, tick_y_top), (x_pos, tick_y_long), _GREEN, 2)

                label_text = f"{normalized_deg:03d}"
                text_size  = cv2.getTextSize(label_text, _FONT, 0.40, 1)
                text_width  = text_size[0][0]
                text_height = text_size[0][1]
                text_x = x_pos - text_width // 2
                text_y = tick_y_long + text_height + 2
                self._put_text_shadowed(frame, label_text, text_x, text_y,
                                        0.40, _GREEN, 1)

                # Cardinal label
                cardinal = {0: "N", 90: "E", 180: "S", 270: "W"}.get(normalized_deg)
                if cardinal is not None:
                    self._put_text_shadowed(frame, cardinal,
                                            x_pos - 4, text_y + 14,
                                            0.45, _GREEN, 2)
            else:
                cv2.line(frame, (x_pos + 1, tick_y_top + 1), (x_pos + 1, tick_y_short + 1),
                         _BLACK, 1)
                cv2.line(frame, (x_pos, tick_y_top), (x_pos, tick_y_short), _GREEN, 1)

        # Center chevron (inverted triangle, green)
        cdef int chevron_size = 7
        cdef int chevron_y    = tape_y + tape_height - 2
        import numpy as _np
        chevron_pts = _np.array(
            [[tape_center_x, chevron_y],
             [tape_center_x - chevron_size, chevron_y - chevron_size],
             [tape_center_x + chevron_size, chevron_y - chevron_size]],
            dtype=_np.int32,
        )
        cv2.fillPoly(frame, [chevron_pts], _BLACK)
        # slightly smaller green fill on top
        inner_pts = _np.array(
            [[tape_center_x, chevron_y - 1],
             [tape_center_x - chevron_size + 1, chevron_y - chevron_size + 1],
             [tape_center_x + chevron_size - 1, chevron_y - chevron_size + 1]],
            dtype=_np.int32,
        )
        cv2.fillPoly(frame, [inner_pts], _GREEN)

        # Heading value box — wider/taller so the degree symbol fits
        cdef str heading_str = f"{int(camera_heading_deg) % 360:03d}\u00b0"
        text_size  = cv2.getTextSize(heading_str, _FONT, 0.50, 2)
        cdef int box_w = text_size[0][0] + 16
        cdef int box_h = text_size[0][1] + 10
        cdef int box_x = tape_center_x - box_w // 2
        cdef int box_y = tape_y + tape_height + 2

        overlay = frame.copy()
        cv2.rectangle(overlay, (box_x, box_y), (box_x + box_w, box_y + box_h),
                      self._bg_color, -1)
        cv2.addWeighted(overlay, self.background_alpha,
                        frame, 1.0 - self.background_alpha, 0, frame)
        # Black border shadow, then green border
        cv2.rectangle(frame, (box_x - 1, box_y - 1),
                      (box_x + box_w + 1, box_y + box_h + 1), _BLACK, 3)
        cv2.rectangle(frame, (box_x, box_y), (box_x + box_w, box_y + box_h), _GREEN, 2)
        self._put_text_shadowed(frame, heading_str,
                                box_x + 8, box_y + box_h - 4,
                                0.50, _GREEN, 2)

    cpdef void close(self):
        """Release OSD resources and close the attached video sink."""
        if self._video_sink is not None:
            try:
                self._video_sink.close()
            except Exception:
                pass
            self._video_sink = None
        logger.debug("OSDOverlay closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

