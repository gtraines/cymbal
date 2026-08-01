"""
Tests for OSDOverlay._build_aircraft_lines() — the text-box content.

Verifies correct rows are generated for known telemetry,
the injected timestamp is used, fix/no-fix branching, and
SBUS channel rows.  All altitude and speed values are displayed
in Imperial units (feet, mph) as of the OSD refactor.
"""

import math
import unittest

from tests.video.osd_test_helpers import (
    load_osd_module, make_osd, fixed_time, fill_telemetry,
    _M_TO_FT, _MS_TO_MPH,
)


class TestOSDTextBoxLines(unittest.TestCase):

    def _osd(self, **kwargs):
        osd, sink = make_osd(time_fn=fixed_time("17:42:03 UTC"), **kwargs)
        return osd

    # ------------------------------------------------------------------
    # Aircraft panel header
    # ------------------------------------------------------------------

    def test_aircraft_panel_header_present(self):
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_aircraft_lines()
        self.assertIn("AIRCRAFT", lines[0])

    # ------------------------------------------------------------------
    # Datetime panel (bottom-left, separate from aircraft panel)
    # ------------------------------------------------------------------

    def test_datetime_panel_contains_utc(self):
        osd = self._osd()
        fill_telemetry(osd)
        dt_lines = osd._build_datetime_lines()
        self.assertIn("17:42:03 UTC", dt_lines[0])

    def test_datetime_panel_includes_date(self):
        osd = self._osd()
        fill_telemetry(osd)
        dt_lines = osd._build_datetime_lines()
        self.assertIn("2000-01-01", dt_lines[0])

    def test_datetime_panel_local_line_present(self):
        osd = self._osd()
        osd.local_timezone = "America/Phoenix"
        osd._resolve_timezone()
        fill_telemetry(osd)
        dt_lines = osd._build_datetime_lines()
        self.assertEqual(len(dt_lines), 2)
        self.assertIn("MST", dt_lines[1])
        self.assertIn("10:42:03", dt_lines[1])

    def test_datetime_panel_utc_only_when_no_tz(self):
        osd = self._osd()
        osd.local_timezone = ""
        osd._resolve_timezone()
        fill_telemetry(osd)
        dt_lines = osd._build_datetime_lines()
        self.assertEqual(len(dt_lines), 1)

    def test_aircraft_panel_has_no_timestamps(self):
        """Timestamps must NOT appear in the aircraft panel lines."""
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_aircraft_lines()
        self.assertFalse(any("UTC" in l for l in lines),
                         "UTC timestamp should be in datetime panel, not aircraft panel")
        self.assertFalse(any("MST" in l for l in lines))

    # ------------------------------------------------------------------
    # Address row (index 1 now — no timestamps in aircraft panel)
    # ------------------------------------------------------------------

    def test_address_row_present(self):
        osd = self._osd()
        fill_telemetry(osd, address="1234 E Main St, Mesa, AZ 85201")
        lines = osd._build_aircraft_lines()
        self.assertIn("1234 E Main St", lines[1])

    def test_unknown_address_fallback(self):
        osd = self._osd()
        fill_telemetry(osd, address="")
        lines = osd._build_aircraft_lines()
        self.assertEqual(lines[1], "Unknown address")

    # ------------------------------------------------------------------
    # GPS position row (index 2)
    # ------------------------------------------------------------------

    def test_gps_row_with_fix(self):
        osd = self._osd()
        fill_telemetry(osd, lat=33.41520, lon=-111.83150)
        lines = osd._build_aircraft_lines()
        gps_row = lines[2]
        self.assertIn("33.41520", gps_row)
        self.assertIn("-111.83150", gps_row)

    def test_gps_row_no_fix(self):
        osd = self._osd()
        fill_telemetry(osd, lat=float('nan'), lon=float('nan'))
        lines = osd._build_aircraft_lines()
        self.assertIn("No fix", lines[2])

    # ------------------------------------------------------------------
    # Altitude AGL row — Imperial (feet) (index 3)
    # ------------------------------------------------------------------

    def test_alt_agl_row_in_feet(self):
        osd = self._osd()
        fill_telemetry(osd, alt_agl=152.3)
        lines = osd._build_aircraft_lines()
        expected_ft = f"{152.3 * _M_TO_FT:.0f}"
        self.assertIn(expected_ft, lines[3])
        self.assertIn("ft", lines[3])
        self.assertNotIn(" m", lines[3])

    def test_alt_msl_row_in_feet(self):
        osd = self._osd()
        fill_telemetry(osd, alt_msl=450.0)
        lines = osd._build_aircraft_lines()
        expected_ft = f"{450.0 * _M_TO_FT:.0f}"
        self.assertIn(expected_ft, lines[3])

    def test_alt_agl_row_missing(self):
        osd = self._osd()
        fill_telemetry(osd, alt_agl=float('nan'))
        lines = osd._build_aircraft_lines()
        self.assertIn("--", lines[3])

    # ------------------------------------------------------------------
    # Ground speed row — Imperial (mph) + True label (index 4)
    # ------------------------------------------------------------------

    def test_groundspeed_row_in_mph(self):
        osd = self._osd()
        fill_telemetry(osd, groundspeed=28.4)
        lines = osd._build_aircraft_lines()
        expected_mph = f"{28.4 * _MS_TO_MPH:.1f}"
        self.assertIn(expected_mph, lines[4])
        self.assertIn("mph", lines[4])
        self.assertNotIn("m/s", lines[4])

    def test_groundspeed_row_has_true_label(self):
        osd = self._osd()
        fill_telemetry(osd, groundspeed=20.0)
        lines = osd._build_aircraft_lines()
        self.assertIn("True", lines[4])

    def test_groundspeed_row_missing(self):
        osd = self._osd()
        fill_telemetry(osd, groundspeed=float('nan'))
        lines = osd._build_aircraft_lines()
        self.assertIn("--", lines[4])

    # ------------------------------------------------------------------
    # Fix quality / satellites row (index 5)
    # ------------------------------------------------------------------

    def test_fix_quality_gps(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=1, satellites=9)
        lines = osd._build_aircraft_lines()
        self.assertIn("GPS", lines[5])
        self.assertIn("9", lines[5])

    def test_fix_quality_dgps(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=2, satellites=11)
        lines = osd._build_aircraft_lines()
        self.assertIn("DGPS", lines[5])

    def test_fix_quality_no_fix(self):
        osd = self._osd()
        fill_telemetry(osd, fix_quality=0, satellites=0)
        lines = osd._build_aircraft_lines()
        self.assertIn("No fix", lines[5])

    # ------------------------------------------------------------------
    # SBUS channel rows (optional)
    # ------------------------------------------------------------------

    def test_sbus_rows_absent_by_default(self):
        osd = self._osd()
        fill_telemetry(osd, sbus_channels=list(range(16)))
        lines = osd._build_aircraft_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 0)

    def test_sbus_rows_present_when_enabled(self):
        mod = load_osd_module()

        class _Cfg:
            enabled = True; font_scale = 0.65; font_thickness = 2
            text_color = [255, 255, 255]; background_color = [0, 0, 0]
            background_alpha = 0.5; show_sbus_channels = True
            show_compass = True; compass_radius = 45

        osd = mod.OSDOverlay(config=_Cfg(), time_fn=fixed_time())
        osd._video_sink = None
        fill_telemetry(osd, sbus_channels=[992] * 16)
        lines = osd._build_aircraft_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 2)
        self.assertIn("SBUS[1-8]", sbus_rows[0])
        self.assertIn("SBUS[9-16]", sbus_rows[1])

    def test_sbus_rows_absent_when_channels_empty(self):
        mod = load_osd_module()

        class _Cfg:
            enabled = True; font_scale = 0.65; font_thickness = 2
            text_color = [255, 255, 255]; background_color = [0, 0, 0]
            background_alpha = 0.5; show_sbus_channels = True
            show_compass = True; compass_radius = 45

        osd = mod.OSDOverlay(config=_Cfg(), time_fn=fixed_time())
        osd._video_sink = None
        fill_telemetry(osd, sbus_channels=[])
        lines = osd._build_aircraft_lines()
        sbus_rows = [l for l in lines if "SBUS" in l]
        self.assertEqual(len(sbus_rows), 0)

    # ------------------------------------------------------------------
    # Backward-compat alias
    # ------------------------------------------------------------------

    def test_build_lines_alias_returns_aircraft_lines(self):
        osd = self._osd()
        fill_telemetry(osd)
        self.assertEqual(osd._build_lines(), osd._build_aircraft_lines())

    # ------------------------------------------------------------------
    # Minimum line count (header + addr + GPS + alt + spd + fix = 6)
    # ------------------------------------------------------------------

    def test_minimum_six_base_rows(self):
        osd = self._osd()
        fill_telemetry(osd)
        lines = osd._build_aircraft_lines()
        self.assertGreaterEqual(len(lines), 6)


if __name__ == '__main__':
    unittest.main()
