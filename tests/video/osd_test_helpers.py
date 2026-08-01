"""
Shared utilities for OSD/video tests.

Provides a pure-Python OSDOverlay implementation that mirrors the Cython
overlay_controller.pyx logic exactly, allowing headless tests to run on any
platform without compiled extensions.
"""

import datetime
import math
import os
import sys
import types


# ---------------------------------------------------------------------------
# Pure-Python OSDOverlay for testing
# ---------------------------------------------------------------------------

_NAN = float('nan')


class OSDOverlay:
    """
    Pure-Python replica of cymbal.osd.overlay_controller.OSDOverlay.

    Implements the same public API and line-building logic as the Cython
    version so tests can validate OSD content deterministically.
    """

    def __init__(self, config=None, time_fn=None):
        self.enabled            = True
        self.font_scale         = 0.6
        self.font_thickness     = 1
        self._text_color        = (255, 255, 255)
        self._bg_color          = (0, 0, 0)
        self.background_alpha   = 0.5
        self.show_sbus_channels = False
        self.show_compass       = True
        self.compass_radius     = 45
        self.show_heading_tape  = True
        self.heading_tape_height_pct = 0.07
        self.heading_tape_width_pct = 0.25
        self.heading_tape_fov_deg = 30.0

        self._video_sink = None
        self._time_fn    = time_fn if time_fn is not None else datetime.datetime.utcnow

        self.lat            = _NAN
        self.lon            = _NAN
        self.alt_agl        = _NAN
        self.groundspeed_ms = _NAN
        self.address        = "No fix"
        self.fix_quality    = 0
        self.satellites     = 0
        self.sbus_channels  = []
        self.track_degrees  = _NAN
        self.camera_yaw_deg = _NAN

        if config is not None:
            self._apply_config(config)

    def _apply_config(self, config):
        self.enabled            = config.enabled
        self.font_scale         = config.font_scale
        self.font_thickness     = config.font_thickness
        self._text_color        = tuple(config.text_color)
        self._bg_color          = tuple(config.background_color)
        self.background_alpha   = config.background_alpha
        self.show_sbus_channels = config.show_sbus_channels
        self.show_compass       = config.show_compass
        self.compass_radius     = config.compass_radius
        # Heading tape fields (optional for backward compatibility)
        if hasattr(config, 'show_heading_tape'):
            self.show_heading_tape = config.show_heading_tape
        if hasattr(config, 'heading_tape_height_pct'):
            self.heading_tape_height_pct = config.heading_tape_height_pct
        if hasattr(config, 'heading_tape_width_pct'):
            self.heading_tape_width_pct = config.heading_tape_width_pct
        if hasattr(config, 'heading_tape_fov_deg'):
            self.heading_tape_fov_deg = config.heading_tape_fov_deg

    def initialize(self, video_sink=None):
        """Attach optional video sink. Returns True always in the test stub."""
        if video_sink is not None:
            self._video_sink = video_sink
        else:
            self._video_sink = _FakeHeadlessSink(capture=True)
            self._video_sink.initialize()
        return True

    def update_telemetry(
        self,
        lat, lon, alt_agl, groundspeed, address,
        fix_quality, satellites, sbus_channels,
        track_degrees, camera_yaw_deg,
    ):
        self.lat            = lat
        self.lon            = lon
        self.alt_agl        = alt_agl
        self.groundspeed_ms = groundspeed
        self.address        = address
        self.fix_quality    = fix_quality
        self.satellites     = satellites
        self.sbus_channels  = sbus_channels
        self.track_degrees  = track_degrees
        self.camera_yaw_deg = camera_yaw_deg

    def render_frame(self, frame):
        """
        Annotate a frame dict/array in-place and forward to the video sink.

        In the test stub, 'annotation' is done by setting frame['annotated']
        to True when frame is a dict.  For numpy arrays (when numpy is
        available) we write a non-zero pixel to indicate the OSD ran.
        """
        if not self.enabled or frame is None:
            return

        # Mark the frame so tests can detect that render_frame ran
        if isinstance(frame, dict):
            frame['annotated'] = True
            frame['lines']     = self._build_lines()
        else:
            # numpy array path
            try:
                frame[5, 5] = [255, 255, 255]  # white dot top-left
            except Exception:
                pass

        if self._video_sink is not None:
            self._video_sink.write_frame(frame)

    def _build_lines(self):
        lines = []

        # Timestamp via injected callable
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

        # Ground speed
        if not math.isnan(self.groundspeed_ms):
            lines.append(f"GndSpd: {self.groundspeed_ms:.1f} m/s")
        else:
            lines.append("GndSpd: --")

        # Fix quality
        fix_str = {0: "No fix", 1: "GPS", 2: "DGPS"}.get(self.fix_quality, "?")
        lines.append(f"Fix: {fix_str}  Sats: {self.satellites}")

        # SBUS debug
        if self.show_sbus_channels and self.sbus_channels:
            ch = list(self.sbus_channels)[:16]
            row1 = "  ".join(f"{v:4d}" for v in ch[:8])
            row2 = "  ".join(f"{v:4d}" for v in ch[8:])
            lines.append(f"SBUS[1-8]:  {row1}")
            lines.append(f"SBUS[9-16]: {row2}")

        return lines

    def close(self):
        if self._video_sink is not None:
            try:
                self._video_sink.close()
            except Exception:
                pass
            self._video_sink = None


# ---------------------------------------------------------------------------
# Minimal HeadlessSink for testing (no cymbal imports needed)
# ---------------------------------------------------------------------------

class _FakeHeadlessSink:
    def __init__(self, capture=False):
        self.capture     = capture
        self.frame_count = 0
        self.last_frame  = None
        self._initialized = False

    def initialize(self, width=640, height=480):
        self._initialized = True
        return True

    def write_frame(self, frame):
        if self.capture and frame is not None:
            self.last_frame  = frame
            self.frame_count += 1

    def close(self):
        self._initialized = False


# ---------------------------------------------------------------------------
# Public API used by tests
# ---------------------------------------------------------------------------

def load_osd_module():
    """Return a module-like namespace containing the test OSDOverlay."""
    ns = types.SimpleNamespace()
    ns.OSDOverlay = OSDOverlay
    return ns


def make_osd(config=None, time_fn=None, **kwargs):
    """Return (osd, sink) ready for testing."""
    osd  = OSDOverlay(config=config, time_fn=time_fn)
    sink = _FakeHeadlessSink(capture=True)
    osd.initialize(video_sink=sink)
    return osd, sink


def fixed_time(ts_str: str = "12:00:00 UTC"):
    """Return a time_fn that always yields the given HH:MM:SS UTC timestamp."""
    dt_str   = ts_str.replace(" UTC", "")
    fixed_dt = datetime.datetime.strptime(dt_str, "%H:%M:%S").replace(
        year=2000, month=1, day=1)
    return lambda: fixed_dt


def make_frame(width: int = 640, height: int = 480):
    """Create a black BGR numpy frame."""
    try:
        import numpy as np
        return np.zeros((height, width, 3), dtype='uint8')
    except ImportError:
        return {}   # fall back to dict for environments without numpy


def fill_telemetry(osd, **overrides):
    """Call osd.update_telemetry with sensible test defaults."""
    defaults = dict(
        lat=33.41520,
        lon=-111.83150,
        alt_agl=152.3,
        groundspeed=28.4,
        address="1234 E Main St, Mesa, AZ 85201",
        fix_quality=1,
        satellites=9,
        sbus_channels=[992] * 18,
        track_degrees=45.0,
        camera_yaw_deg=30.0,
    )
    defaults.update(overrides)
    osd.update_telemetry(**defaults)
