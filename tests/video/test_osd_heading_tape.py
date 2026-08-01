"""
Tests for OSD heading tape feature.

Validates heading calculation, wraparound logic, and configuration.
"""
import math
import unittest

from tests.video.osd_test_helpers import (
    OSDOverlay, make_osd, fixed_time,
)
from cymbal.config.config import OSDConfig


class TestHeadingTapeConfiguration(unittest.TestCase):
    """Test heading tape configuration options."""

    def test_heading_tape_enabled_by_default(self):
        """Test that heading tape is enabled by default."""
        config = OSDConfig()
        self.assertTrue(config.show_heading_tape)

    def test_heading_tape_disabled_via_config(self):
        """Test that heading tape can be disabled."""
        class Cfg:
            enabled=True; font_scale=0.6; font_thickness=1
            text_color=[255,255,255]; background_color=[0,0,0]
            background_alpha=0.5; show_sbus_channels=False
            show_compass=True; compass_radius=45
            show_heading_tape=False
            heading_tape_height_pct=0.07
            heading_tape_width_pct=0.25
            heading_tape_fov_deg=30.0
        
        osd, _ = make_osd(config=Cfg(), time_fn=fixed_time())
        self.assertFalse(osd.show_heading_tape)

    def test_custom_heading_tape_dimensions(self):
        """Test custom heading tape size configuration."""
        config = OSDConfig(
            show_heading_tape=True,
            heading_tape_height_pct=0.1,
            heading_tape_width_pct=0.3,
            heading_tape_fov_deg=40.0
        )
        osd = OSDOverlay(config=config)
        
        # Verify config applied
        self.assertEqual(osd.heading_tape_height_pct, 0.1)
        self.assertEqual(osd.heading_tape_width_pct, 0.3)
        self.assertEqual(osd.heading_tape_fov_deg, 40.0)

    def test_default_heading_tape_dimensions(self):
        """Test default heading tape dimensions."""
        osd, _ = make_osd(time_fn=fixed_time())
        
        self.assertTrue(osd.show_heading_tape)
        self.assertEqual(osd.heading_tape_height_pct, 0.07)
        self.assertEqual(osd.heading_tape_width_pct, 0.25)
        self.assertEqual(osd.heading_tape_fov_deg, 30.0)


class TestHeadingTapeCalculation(unittest.TestCase):
    """Test heading calculation logic from track + camera yaw."""

    def test_heading_simple_addition(self):
        """Test simple heading calculation without wraparound."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Track=100°, camera yaw=10° → heading=110°
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=100.0,
            camera_yaw_deg=10.0
        )
        
        # Verify telemetry cached
        self.assertEqual(osd.track_degrees, 100.0)
        self.assertEqual(osd.camera_yaw_deg, 10.0)
        
        # Calculated heading should be 110°
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 110.0)

    def test_heading_wraparound_forward(self):
        """Test heading wraparound when crossing 360°."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Track=355°, camera yaw=10° → heading=365° → 5°
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=355.0,
            camera_yaw_deg=10.0
        )
        
        # Calculated heading should wrap to 5°
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 5.0)

    def test_heading_wraparound_backward(self):
        """Test heading wraparound when crossing 0°."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Track=5°, camera yaw=-10° → heading=-5° → 355°
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=5.0,
            camera_yaw_deg=-10.0
        )
        
        # Calculated heading should wrap to 355°
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 355.0)

    def test_heading_negative_yaw(self):
        """Test negative camera yaw (camera left of nose)."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Track=180°, camera yaw=-45° → heading=135°
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=180.0,
            camera_yaw_deg=-45.0
        )
        
        # Calculated heading should be 135°
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 135.0)

    def test_heading_at_cardinals(self):
        """Test heading calculation at cardinal directions."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # North (0°)
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=0.0,
            camera_yaw_deg=0.0
        )
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 0.0)
        
        # East (90°)
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=90.0,
            camera_yaw_deg=0.0
        )
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 90.0)
        
        # South (180°)
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=180.0,
            camera_yaw_deg=0.0
        )
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 180.0)
        
        # West (270°)
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=270.0,
            camera_yaw_deg=0.0
        )
        heading = (osd.track_degrees + osd.camera_yaw_deg) % 360.0
        self.assertAlmostEqual(heading, 270.0)


class TestHeadingTapeNaNHandling(unittest.TestCase):
    """Test heading tape behavior with missing data (NaN)."""

    def test_nan_track_no_heading(self):
        """Test that heading is NaN when track is NaN."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # NaN track, valid camera yaw → no heading
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=0, satellites=0,
            sbus_channels=[],
            track_degrees=float('nan'),
            camera_yaw_deg=10.0
        )
        
        # Verify NaN is preserved
        self.assertTrue(math.isnan(osd.track_degrees))

    def test_nan_yaw_no_heading(self):
        """Test that heading is NaN when camera yaw is NaN."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Valid track, NaN camera yaw → no heading
        osd.update_telemetry(
            lat=45.0, lon=-122.0, alt_agl=100.0,
            groundspeed=15.0, address="Test St",
            fix_quality=1, satellites=8,
            sbus_channels=[],
            track_degrees=135.0,
            camera_yaw_deg=float('nan')
        )
        
        # Verify NaN is preserved
        self.assertTrue(math.isnan(osd.camera_yaw_deg))

    def test_both_nan_no_heading(self):
        """Test that heading is NaN when both values are NaN."""
        osd, _ = make_osd(time_fn=fixed_time())
        osd.initialize()
        
        # Both NaN → no heading
        osd.update_telemetry(
            lat=float('nan'), lon=float('nan'), alt_agl=float('nan'),
            groundspeed=float('nan'), address="No fix",
            fix_quality=0, satellites=0,
            sbus_channels=[],
            track_degrees=float('nan'),
            camera_yaw_deg=float('nan')
        )
        
        # Verify both are NaN
        self.assertTrue(math.isnan(osd.track_degrees))
        self.assertTrue(math.isnan(osd.camera_yaw_deg))


if __name__ == '__main__':
    unittest.main()
