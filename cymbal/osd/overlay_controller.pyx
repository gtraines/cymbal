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

Usage:
    osd = OSDOverlay(config.osd)
    osd.initialize()
    osd.update_telemetry(lat, lon, alt_agl, groundspeed, address, ...)
    # In camera loop:
    osd.render_frame(frame)   # annotates frame in-place
    osd.close()
"""

import datetime
import logging
import math

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger(__name__)

# OpenCV font
_FONT = None  # set in initialize() once cv2 is available


cdef class OSDOverlay:
    """
    Telemetry OSD that annotates numpy video frames using OpenCV.

    All public fields are updated by update_telemetry(); render_frame()
    draws the cached values onto a frame buffer.  Both methods are safe to
    call from the same thread without locking.
    """

    def __init__(self, config=None):
        """
        Args:
            config: OSDConfig dataclass instance, or None for defaults.
        """
        self.enabled = True
        self.font_scale = 0.6
        self.font_thickness = 1
        self._text_color = (255, 255, 255)
        self._bg_color = (0, 0, 0)
        self.background_alpha = 0.5
        self.show_sbus_channels = False

        self.lat = float('nan')
        self.lon = float('nan')
        self.alt_agl = float('nan')
        self.groundspeed_ms = float('nan')
        self.address = "No fix"
        self.fix_quality = 0
        self.satellites = 0
        self.sbus_channels = []

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

    cpdef bint initialize(self):
        """
        Verify OpenCV is available.

        Returns:
            True if OpenCV is usable, False otherwise.
        """
        global _FONT
        if cv2 is None:
            logger.error("OpenCV (cv2) not available; install opencv-python-headless")
            self.enabled = False
            return False
        _FONT = cv2.FONT_HERSHEY_SIMPLEX
        logger.info("OSDOverlay initialized")
        return True

    cpdef void update_telemetry(self, double lat, double lon, double alt_agl,
                                double groundspeed, str address,
                                int fix_quality, int satellites,
                                object sbus_channels):
        """
        Cache the latest telemetry for the next render_frame() call.

        Args:
            lat:          Latitude in decimal degrees (NaN if no fix).
            lon:          Longitude in decimal degrees (NaN if no fix).
            alt_agl:      Altitude above ground level in meters (NaN if unknown).
            groundspeed:  Ground speed in m/s (NaN if unknown).
            address:      Nearest street address string.
            fix_quality:  GPS fix quality (0=none, 1=GPS, 2=DGPS).
            satellites:   Number of satellites in use.
            sbus_channels: Sequence of 18 raw SBUS channel values for debug display.
        """
        self.lat = lat
        self.lon = lon
        self.alt_agl = alt_agl
        self.groundspeed_ms = groundspeed
        self.address = address
        self.fix_quality = fix_quality
        self.satellites = satellites
        self.sbus_channels = sbus_channels

    cpdef void render_frame(self, object frame):
        """
        Annotate a video frame in-place with cached telemetry.

        Args:
            frame: A numpy ndarray (H × W × 3, uint8, BGR) from a camera.
                   If None, this method returns immediately.
        """
        cdef list lines
        cdef int x = 10
        cdef int y = 30

        if not self.enabled or cv2 is None or frame is None:
            return

        lines = self._build_lines()
        self._draw_text_box(frame, lines, x, y)

    def _build_lines(self):
        """Assemble the list of text lines to display."""
        lines = []

        # Timestamp
        ts = datetime.datetime.utcnow().strftime("%H:%M:%S UTC")
        lines.append(ts)

        # Address
        lines.append(self.address or "Unknown address")

        # GPS position
        if not math.isnan(self.lat) and not math.isnan(self.lon):
            lines.append(f"Lat: {self.lat:.5f}  Lon: {self.lon:.5f}")
        else:
            lines.append("GPS: No fix")

        # Altitude AGL
        if not math.isnan(self.alt_agl):
            lines.append(f"Alt AGL: {self.alt_agl:.1f} m")
        else:
            lines.append("Alt AGL: --")

        # Groundspeed
        if not math.isnan(self.groundspeed_ms):
            lines.append(f"GndSpd: {self.groundspeed_ms:.1f} m/s")
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

    cdef void _draw_text_box(self, object frame, list lines, int x, int y):
        """Draw a semi-transparent background box and then render text lines."""
        cdef int max_width, w, h, total_height, pad, lh, bx1, by1, bx2, by2, fh, fw, ty
        cdef object overlay

        pad = 6
        lh = int(28 * self.font_scale)

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
            -1,  # filled
        )
        cv2.addWeighted(
            overlay, self.background_alpha,
            frame, 1.0 - self.background_alpha,
            0, frame,
        )

        # Text lines
        ty = y
        for line in lines:
            cv2.putText(
                frame, line,
                (x, ty),
                _FONT,
                self.font_scale,
                self._text_color,
                self.font_thickness,
                cv2.LINE_AA,
            )
            ty += lh

    cpdef void close(self):
        """Release OSD resources."""
        logger.debug("OSDOverlay closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
