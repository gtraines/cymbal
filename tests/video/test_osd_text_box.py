"""
Tests for OSDOverlay._build_lines() — the text-box content.

Verifies correct rows are generated for known telemetry,
the injected timestamp is used, fix/no-fix branching, and
SBUS channel rows.
"""

import math
import unittest

from tests.video.osd_test_helpers import (
    load_osd_module, make_osd, fixed_time, fill_telemetry,
)


class TestOSDTextBoxLines(unittest.TestCase):

    def _osd(self, **kwargs):
        osd, sink = make_osd(time_fn=fixed_time("17:42:03 UTC"), **kwargs)
        return osd

    # ------------------------------------------------------------------
    # Timestamp
    # ------------------------------------------------------------------

    def test_timestamp_uses_injected_time(self):
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_lines()
        self.assertEqual(lines[0], "17:42:03 UTC")

    def test_timestamp_default_format(self):
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_lines()
        # Must end with " UTC"
        self.assertTrue(lines[0].endswith(" UTC"), lines[0])
        # Must have HH:MM:SS
        parts = lines[0].split(" ")[0].split(":")
        self.assertEqual(len(parts), 3)

    # ------------------------------------------------------------------
    # Address row
    # ------------------------------------------------------------------

    def test_address_row_present(self):
        osd = self._osd()
        fill_telemetry(osd, address="1234 E Main St, Mesa, AZ 85201")
        lines = osd._build_lines()
        self.assertIn("1234 E Main St", lines[1])

    def test_unknown_address_fallback(self):
        osd = self._osd()
        fill_telemetry(osd, address="")
        lines = osd._build_lines()
        self.assertEqual(lines[1], "Unknown address")

    # ------------------------------------------------------------------
    # GPS position row
    # ------------------------------------------------------------------

    def test_gps_row_with_fix(self):
        osd = self._osd()
        fill_telemetry(osd, lat=33.41520, lon=-111.83150)
        lines = osd._build_lines()
        gps_row = lines[2]
        self.assertIn("33.41520", gps_row)
        self.assertIn("-111.83150", gps_row)

    def test_gps_row_no_fix(self):
        osd = self._osd()
        fill_telemetry(osd, lat=float('nan'), lon=float('nan'))
        lines = osd._build_lines()
        self.assertIn("No fix", lines[2])

    # ------------------------------------------------------------------
    # Altitude AGL row
    # ------------------------------------------------------------------

    def test_alt_agl_row_with_value(self):
        osd = self._osd()
        fill_telemetry(osd, alt_agl=152.3)
        lines = osd._build_lines()
        self.assertIn("152.3", lines[3])
        self.assertIn("m", lines[3])

    def test_alt_agl_row_missing(self):
        osd = self._osd()
        fill_telemetry(osd, alt_agl=float('nan'))
        lines = osd._build_lines()
        self.assertIn("--", lines[3])

    # ------------------------------------------------------------------
    # Ground speed row
    # ------------------------------------------------------------------

    def test_groundspeed_row_with_value(self):
        osd = self._osd()
        fill_telemetry(osd, groundspeed=28.4)
        lines = osd._build_lines()
        self.assertIn("28.4", lines[4])

    def test_groundspeed_row_missing(self):
        osd = self._osd()
        fill_telemetry(osd, groundspeed=float('nan'))
        lines = osd._build_lines()
        self.assertIn("--", lines[4])

    # ------------------------------------------------------------------
    # Fix quality / satellites row
    # ------------------------------------------------------------------

    def test_fix_quality_gps(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=1, satellites=9)
        lines = osd._build_lines()
        self.assertIn("GPS", lines[5])
        self.assertIn("9", lines[5])

    def test_fix_quality_dgps(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=2, satellites=11)
        lines = osd._build_lines()
        self.assertIn("DGPS", lines[5])

    def test_fix_quality_no_fix(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=0, satellites=0)
        lines = osd._build_lines()
        self.assertIn("No fix", lines[5])

    # ------------------------------------------------------------------
    # SBUS channel rows (optional)
    # ------------------------------------------------------------------

    def test_sbus_rows_absent_by_default(self):
        osd = self._osd()
        fill_telemetry(osd, sbus_channels=list(range(16)))
        lines = osd._build_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 0)

    def test_sbus_rows_present_when_enabled(self):
        mod = load_osd_module()

        class _Cfg:
            enabled = True; font_scale = 0.6; font_thickness = 1
            text_color = [255, 255, 255]; background_color = [0, 0, 0]
            background_alpha = 0.5; show_sbus_channels = True
            show_compass = True; compass_radius = 45

        osd = mod.OSDOverlay(config=_Cfg(), time_fn=fixed_time())
        osd._video_sink = None
        fill_telemetry(osd, sbus_channels=[992] * 16)
        lines = osd._build_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 2)
        self.assertIn("SBUS[1-8]", sbus_rows[0])
        self.assertIn("SBUS[9-16]", sbus_rows[1])

    def test_sbus_rows_absent_when_channels_empty(self):
        mod = load_osd_module()

        class _Cfg:
            enabled = True; font_scale = 0.6; font_thickness = 1
            text_color = [255, 255, 255]; background_color = [0, 0, 0]
            background_alpha = 0.5; show_sbus_channels = True
            show_compass = True; compass_radius = 45

        osd = mod.OSDOverlay(config=_Cfg(), time_fn=fixed_time())
        osd._video_sink = None
        fill_telemetry(osd, sbus_channels=[])
        lines = osd._build_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 0)

    # ------------------------------------------------------------------
    # Minimum line count
    # ------------------------------------------------------------------

    def test_minimum_six_base_rows(self):
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_lines()
        # timestamp, address, GPS, alt, speed, fix = 6 rows minimum
        self.assertGreaterEqual(len(lines), 6)


if __name__ == '__main__':
    unittest.main()
