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

Compass widget:
  A small circle rendered in the top-right corner of the frame shows:
  - White arrow: aircraft travel direction (GPS ground track, north-up).
  - Yellow arrow: absolute camera aim direction (track + camera yaw).
  - "N" label and cardinal tick marks on the ring.
  - Text labels Trk/Cam below the ring.

Usage:
    osd = OSDOverlay(config.osd)
    osd.initialize()
    osd.update_telemetry(lat, lon, alt_agl, groundspeed, address,
                         fix_quality, satellites, sbus_channels,
                         track_degrees, camera_yaw_deg)
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

_NAN = float('nan')


cdef class OSDOverlay:
    """
    Telemetry OSD that annotates numpy video frames using OpenCV.

    All public fields are updated by update_telemetry(); render_frame()
    draws the cached values onto a frame buffer.  Both methods are safe to
    call from the same thread without locking.

    Args:
        config:   OSDConfig dataclass instance, or None for defaults.
        time_fn:  Callable returning a datetime.datetime for the timestamp
                  row.  Defaults to datetime.datetime.utcnow.  Override in
                  tests for deterministic output.
    """

    def __init__(self, config=None, time_fn=None):
        self.enabled = True
        self.font_scale = 0.6
        self.font_thickness = 1
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

        self.lat = _NAN
        self.lon = _NAN
        self.alt_agl = _NAN
        self.groundspeed_ms = _NAN
        self.address = "No fix"
        self.fix_quality = 0
        self.satellites = 0
        self.sbus_channels = []
        self.track_degrees = _NAN
        self.camera_yaw_deg = _NAN

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
                                double camera_yaw_deg):
        """
        Cache the latest telemetry for the next render_frame() call.

        Args:
            lat:           Latitude in decimal degrees (NaN if no fix).
            lon:           Longitude in decimal degrees (NaN if no fix).
            alt_agl:       Altitude above ground level in meters (NaN if unknown).
            groundspeed:   Ground speed in m/s (NaN if unknown).
            address:       Nearest street address string.
            fix_quality:   GPS fix quality (0=none, 1=GPS, 2=DGPS).
            satellites:    Number of satellites in use.
            sbus_channels: Sequence of 18 raw SBUS channel values for debug display.
            track_degrees: GPS ground track in degrees from north, clockwise (NaN if unknown).
            camera_yaw_deg: Camera yaw offset from aircraft nose in degrees
                            (positive = right, negative = left; NaN if unknown).
        """
        self.lat = lat
        self.lon = lon
        self.alt_agl = alt_agl
        self.groundspeed_ms = groundspeed
        self.address = address
        self.fix_quality = fix_quality
        self.satellites = satellites
        self.sbus_channels = sbus_channels
        self.track_degrees = track_degrees
        self.camera_yaw_deg = camera_yaw_deg

    cpdef void render_frame(self, object frame):
        """
        Annotate a video frame in-place with cached telemetry.

        Args:
            frame: A numpy ndarray (H × W × 3, uint8, BGR) from a camera.
                   If None, this method returns immediately.
        """
        cdef list lines
        cdef int x, y, fh, fw, cx, cy
        cdef double camera_heading

        if not self.enabled or cv2 is None or frame is None:
            return

        x = 10
        y = 30
        lines = self._build_lines()
        self._draw_text_box(frame, lines, x, y)

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

        # Draw heading tape if enabled and data available
        if self.show_heading_tape:
            # Compute absolute camera heading from track + yaw
            camera_heading = _NAN
            if not math.isnan(self.track_degrees) and not math.isnan(self.camera_yaw_deg):
                camera_heading = (self.track_degrees + self.camera_yaw_deg) % 360.0
            
            if not math.isnan(camera_heading):
                self._draw_heading_tape(frame, camera_heading)

        # Forward to the attached video sink (HeadlessSink by default)
        if self._video_sink is not None:
            self._video_sink.write_frame(frame)

    def _build_lines(self):
        """Assemble the list of text lines to display."""
        lines = []

        # Timestamp — use injected callable for testability
        ts = self._time_fn().strftime("%H:%M:%S UTC")
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

    cdef void _draw_compass_widget(self, object frame, int cx, int cy,
                                   int radius, double track_deg,
                                   double camera_yaw_deg):
        """
        Draw the compass widget: a ring with aircraft-track and camera-aim arrows.

        The compass is north-up (geographic).
        - White arrow: GPS ground track (where the aircraft is flying).
        - Yellow arrow: absolute camera aim direction (track + camera_yaw_deg).
        Both arrows are suppressed when the relevant value is NaN.

        Args:
            frame:          BGR numpy frame (modified in-place).
            cx, cy:         Centre pixel of the compass circle.
            radius:         Outer radius of the compass ring in pixels.
            track_deg:      GPS ground track (degrees from north, clockwise).
                            NaN → white arrow suppressed, ring dims.
            camera_yaw_deg: Camera yaw offset from nose (degrees, + = right).
                            NaN → yellow arrow suppressed.
        """
        cdef double pi = math.pi
        cdef double track_rad, cam_abs_rad
        cdef int ax, ay, cax, cay, ix, iy, ox, oy, tx, ty
        cdef int inner_r, outer_r, arrow_len, cam_len
        cdef bint have_track, have_cam
        cdef object bg_overlay
        cdef double card_rad
        cdef int i

        have_track = not math.isnan(track_deg)
        have_cam   = have_track and not math.isnan(camera_yaw_deg)

        # ------------------------------------------------------------------
        # Semi-transparent background disc
        # ------------------------------------------------------------------
        bg_overlay = frame.copy()
        cv2.circle(bg_overlay, (cx, cy), radius + 12, (0, 0, 0), -1)
        cv2.addWeighted(bg_overlay, 0.55, frame, 0.45, 0, frame)

        # ------------------------------------------------------------------
        # Compass ring colour: bright when we have a fix, dimmed otherwise
        # ------------------------------------------------------------------
        ring_color = (180, 180, 180) if have_track else (80, 80, 80)
        cv2.circle(frame, (cx, cy), radius, ring_color, 1, cv2.LINE_AA)

        # ------------------------------------------------------------------
        # Cardinal tick marks (N / E / S / W)  and "N" label
        # ------------------------------------------------------------------
        cardinal_angles = [0.0, 90.0, 180.0, 270.0]
        cardinal_labels = ["N", None, None, None]

        for i in range(4):
            card_rad = cardinal_angles[i] * pi / 180.0
            s = math.sin(card_rad)
            c = math.cos(card_rad)
            inner_r = radius - 5
            outer_r = radius
            ix = int(cx + inner_r * s)
            iy = int(cy - inner_r * c)
            ox = int(cx + outer_r * s)
            oy = int(cy - outer_r * c)
            cv2.line(frame, (ix, iy), (ox, oy), ring_color, 2, cv2.LINE_AA)

            if cardinal_labels[i] is not None:
                tx = int(cx + (outer_r + 8) * s) - 4
                ty = int(cy - (outer_r + 8) * c) + 4
                cv2.putText(frame, "N", (tx, ty),
                            _FONT, 0.38, ring_color, 1, cv2.LINE_AA)

        # ------------------------------------------------------------------
        # Aircraft travel direction arrow  (white)
        # ------------------------------------------------------------------
        if have_track:
            track_rad = track_deg * pi / 180.0
            arrow_len = int(radius * 0.82)
            ax = int(cx + arrow_len * math.sin(track_rad))
            ay = int(cy - arrow_len * math.cos(track_rad))
            cv2.arrowedLine(
                frame, (cx, cy), (ax, ay),
                (255, 255, 255), 2, cv2.LINE_AA, tipLength=0.28,
            )

        # ------------------------------------------------------------------
        # Camera aim direction arrow  (yellow = (0, 255, 255) in BGR)
        # ------------------------------------------------------------------
        if have_cam:
            cam_abs_deg = track_deg + camera_yaw_deg
            cam_abs_rad = cam_abs_deg * pi / 180.0
            cam_len = int(radius * 0.62)
            cax = int(cx + cam_len * math.sin(cam_abs_rad))
            cay = int(cy - cam_len * math.cos(cam_abs_rad))
            cv2.arrowedLine(
                frame, (cx, cy), (cax, cay),
                (0, 255, 255), 2, cv2.LINE_AA, tipLength=0.33,
            )

        # ------------------------------------------------------------------
        # Text labels below the ring
        # ------------------------------------------------------------------
        label_y = cy + radius + 16
        label_x = cx - radius

        if have_track:
            trk_str = f"Trk:{track_deg:05.1f}"
            cv2.putText(frame, trk_str, (label_x, label_y),
                        _FONT, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
            label_y += 16

        if have_cam:
            sign = "+" if camera_yaw_deg >= 0 else ""
            cam_str = f"Cam:{sign}{camera_yaw_deg:05.1f}"
            cv2.putText(frame, cam_str, (label_x, label_y),
                        _FONT, 0.40, (0, 255, 255), 1, cv2.LINE_AA)

    cdef void _draw_heading_tape(self, object frame, double camera_heading_deg):
        """
        Draw horizontal scrolling heading tape at top center.
        
        Shows camera absolute heading with ±15° field of view (configurable).
        Displays tick marks, numerical labels, and cardinal directions.
        
        Args:
            frame: BGR numpy array (H × W × 3)
            camera_heading_deg: Absolute camera heading in degrees (0-360)
        """
        cdef int frame_height = frame.shape[0]
        cdef int frame_width = frame.shape[1]
        
        # Calculate tape dimensions
        cdef int tape_height = int(frame_height * self.heading_tape_height_pct)
        cdef int tape_width = int(frame_width * self.heading_tape_width_pct)
        cdef int tape_x = (frame_width - tape_width) // 2
        cdef int tape_y = int(frame_height * 0.02)
        
        # Ensure minimum size
        if tape_height < 20 or tape_width < 100:
            return
        
        # Draw semi-transparent background
        cdef object overlay = frame.copy()
        cv2.rectangle(overlay, (tape_x, tape_y),
                     (tape_x + tape_width, tape_y + tape_height),
                     self._bg_color, -1)
        cv2.addWeighted(overlay, self.background_alpha, frame, 1.0 - self.background_alpha,
                       0, frame)
        
        # Draw border
        cv2.rectangle(frame, (tape_x, tape_y),
                     (tape_x + tape_width, tape_y + tape_height),
                     self._text_color, 1)
        
        # Calculate degree range
        cdef double half_fov = self.heading_tape_fov_deg / 2.0
        cdef double degrees_per_pixel = self.heading_tape_fov_deg / float(tape_width)
        cdef int tape_center_x = tape_x + tape_width // 2
        
        # Tick mark dimensions
        cdef int tick_y_top = tape_y + 2
        cdef int short_tick_height = 5
        cdef int long_tick_height = 10
        cdef int tick_y_short = tick_y_top + short_tick_height
        cdef int tick_y_long = tick_y_top + long_tick_height
        
        # Draw tick marks and labels
        cdef int deg
        cdef double angular_offset
        cdef int x_pos
        cdef str label_text
        cdef int text_width, text_height
        cdef int text_x, text_y
        cdef object text_size
        cdef int baseline
        
        # Iterate through visible degree range
        cdef int min_deg = int(camera_heading_deg - half_fov - 1)
        cdef int max_deg = int(camera_heading_deg + half_fov + 2)
        
        for deg in range(min_deg, max_deg + 1):
            # Normalize to 0-359
            normalized_deg = deg % 360
            
            # Calculate angular offset from camera heading (shortest path)
            angular_offset = normalized_deg - camera_heading_deg
            if angular_offset > 180:
                angular_offset -= 360
            elif angular_offset < -180:
                angular_offset += 360
            
            # Skip if outside visible range
            if abs(angular_offset) > half_fov:
                continue
            
            # Calculate x position
            x_pos = int(tape_center_x + angular_offset / degrees_per_pixel)
            
            # Skip if outside tape bounds
            if x_pos < tape_x or x_pos > tape_x + tape_width:
                continue
            
            # Draw tick marks
            if normalized_deg % 5 == 0:
                # Long tick every 5 degrees
                cv2.line(frame, (x_pos, tick_y_top), (x_pos, tick_y_long),
                        self._text_color, 1)
                
                # Add numerical label
                label_text = f"{normalized_deg:03d}"
                text_size = cv2.getTextSize(label_text, _FONT, 0.35, 1)
                text_width = text_size[0][0]
                text_height = text_size[0][1]
                text_x = x_pos - text_width // 2
                text_y = tick_y_long + text_height + 2
                
                cv2.putText(frame, label_text, (text_x, text_y),
                           _FONT, 0.35, self._text_color, 1, cv2.LINE_AA)
                
                # Add cardinal direction label if applicable
                if normalized_deg == 0:
                    cv2.putText(frame, "N", (x_pos - 4, text_y + 14),
                               _FONT, 0.35, self._text_color, 1, cv2.LINE_AA)
                elif normalized_deg == 90:
                    cv2.putText(frame, "E", (x_pos - 3, text_y + 14),
                               _FONT, 0.35, self._text_color, 1, cv2.LINE_AA)
                elif normalized_deg == 180:
                    cv2.putText(frame, "S", (x_pos - 3, text_y + 14),
                               _FONT, 0.35, self._text_color, 1, cv2.LINE_AA)
                elif normalized_deg == 270:
                    cv2.putText(frame, "W", (x_pos - 5, text_y + 14),
                               _FONT, 0.35, self._text_color, 1, cv2.LINE_AA)
            else:
                # Short tick every 1 degree
                cv2.line(frame, (x_pos, tick_y_top), (x_pos, tick_y_short),
                        self._text_color, 1)
        
        # Draw center chevron (downward pointing triangle)
        cdef int chevron_size = 6
        cdef int chevron_y = tape_y + tape_height - 2
        cdef object chevron_pts = [[tape_center_x, chevron_y],
                                   [tape_center_x - chevron_size, chevron_y - chevron_size],
                                   [tape_center_x + chevron_size, chevron_y - chevron_size]]
        import numpy as np
        cv2.fillPoly(frame, [np.array(chevron_pts, dtype=np.int32)], self._text_color)
        
        # Draw center heading value box
        cdef str heading_str = f"{int(camera_heading_deg) % 360:03d}\u00b0"
        text_size = cv2.getTextSize(heading_str, _FONT, 0.45, 1)
        cdef int box_width = text_size[0][0] + 8
        cdef int box_height = text_size[0][1] + 6
        cdef int box_x = tape_center_x - box_width // 2
        cdef int box_y = tape_y + tape_height + 2
        
        # Draw box background
        overlay = frame.copy()
        cv2.rectangle(overlay, (box_x, box_y),
                     (box_x + box_width, box_y + box_height),
                     self._bg_color, -1)
        cv2.addWeighted(overlay, self.background_alpha, frame, 1.0 - self.background_alpha,
                       0, frame)
        
        # Draw box border and text
        cv2.rectangle(frame, (box_x, box_y),
                     (box_x + box_width, box_y + box_height),
                     self._text_color, 1)
        cv2.putText(frame, heading_str,
                   (box_x + 4, box_y + box_height - 3),
                   _FONT, 0.45, self._text_color, 1, cv2.LINE_AA)

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

