"""
Unit tests for GPSSensor NMEA parsing logic.

These tests exercise the sentence parsing methods directly using mock
pynmea2-style objects, so they run without serial hardware or pynmea2.
"""

import math
import sys
import types
import unittest


# ---------------------------------------------------------------------------
# Minimal pynmea2 stub so tests run without the library installed.
# ---------------------------------------------------------------------------

def _make_pynmea2_stub():
    mod = types.ModuleType("pynmea2")

    class ParseError(Exception):
        pass

    def parse(line):
        raise ParseError("stub — not used in unit tests")

    mod.ParseError = ParseError
    mod.parse = parse
    return mod


if "pynmea2" not in sys.modules:
    sys.modules["pynmea2"] = _make_pynmea2_stub()

# Stub serial so GPSSensor can be imported without pyserial
if "serial" not in sys.modules:
    serial_mod = types.ModuleType("serial")
    serial_mod.Serial = object
    serial_mod.EIGHTBITS = 8
    serial_mod.PARITY_NONE = "N"
    serial_mod.STOPBITS_ONE = 1
    sys.modules["serial"] = serial_mod


# ---------------------------------------------------------------------------
# Build minimal sentence stubs that mirror pynmea2 message attribute layout.
# ---------------------------------------------------------------------------

class _GGAMsg:
    sentence_type = "GGA"

    def __init__(self, qual, lat, lon, alt, num_sats, hdop):
        self.gps_qual = str(qual)
        self.latitude = lat
        self.longitude = lon
        self.altitude = alt
        self.num_sats = str(num_sats)
        self.horizontal_dil = str(hdop)


class _VTGMsg:
    sentence_type = "VTG"

    def __init__(self, speed_kmph, true_track):
        self.spd_over_grnd_kmph = str(speed_kmph) if speed_kmph is not None else None
        self.true_track = str(true_track) if true_track is not None else None


class _RMCMsg:
    sentence_type = "RMC"

    def __init__(self, status, lat, lon, speed_kts, course):
        self.status = status
        self.latitude = lat
        self.longitude = lon
        self.spd_over_grnd = str(speed_kts) if speed_kts is not None else None
        self.true_course = str(course) if course is not None else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGPSSensorParseGGA(unittest.TestCase):

    def _make_sensor(self):
        from cymbal.sensors.gps_sensor import GPSSensor
        return GPSSensor(terrain_db=None)

    def test_valid_fix_updates_position(self):
        sensor = self._make_sensor()
        msg = _GGAMsg(qual=1, lat=33.4152, lon=-111.8315, alt=355.0,
                      num_sats=8, hdop=1.2)
        result = sensor._parse_gga(msg)
        self.assertTrue(result)
        self.assertAlmostEqual(sensor.latitude, 33.4152, places=4)
        self.assertAlmostEqual(sensor.longitude, -111.8315, places=4)
        self.assertAlmostEqual(sensor.altitude_msl, 355.0, places=1)
        self.assertTrue(sensor.has_fix)
        self.assertEqual(sensor.fix_quality, 1)
        self.assertEqual(sensor.satellites, 8)
        self.assertAlmostEqual(sensor.hdop, 1.2, places=1)

    def test_no_fix_clears_has_fix(self):
        sensor = self._make_sensor()
        # First get a fix
        msg = _GGAMsg(qual=1, lat=33.4, lon=-111.8, alt=350.0, num_sats=6, hdop=1.5)
        sensor._parse_gga(msg)
        # Then lose fix
        msg_nf = _GGAMsg(qual=0, lat=0.0, lon=0.0, alt=0.0, num_sats=0, hdop=0.0)
        sensor._parse_gga(msg_nf)
        self.assertFalse(sensor.has_fix)
        self.assertEqual(sensor.fix_quality, 0)

    def test_agl_is_nan_without_terrain_db(self):
        sensor = self._make_sensor()
        msg = _GGAMsg(qual=1, lat=33.4, lon=-111.8, alt=350.0, num_sats=6, hdop=1.5)
        sensor._parse_gga(msg)
        self.assertTrue(math.isnan(sensor.altitude_agl))

    def test_agl_computed_when_terrain_db_provided(self):
        class _FakeTerrainDB:
            def get_elevation(self, lat, lon):
                return 330.0  # terrain at 330 m MSL

        from cymbal.sensors.gps_sensor import GPSSensor
        sensor = GPSSensor(terrain_db=_FakeTerrainDB())
        sensor.use_terrain_db = True
        msg = _GGAMsg(qual=1, lat=33.4, lon=-111.8, alt=370.0, num_sats=8, hdop=1.0)
        sensor._parse_gga(msg)
        self.assertAlmostEqual(sensor.altitude_agl, 40.0, places=1)

    def test_agl_nan_when_terrain_miss(self):
        class _MissingTerrainDB:
            def get_elevation(self, lat, lon):
                return float('nan')

        from cymbal.sensors.gps_sensor import GPSSensor
        sensor = GPSSensor(terrain_db=_MissingTerrainDB())
        sensor.use_terrain_db = True
        msg = _GGAMsg(qual=1, lat=33.4, lon=-111.8, alt=370.0, num_sats=8, hdop=1.0)
        sensor._parse_gga(msg)
        self.assertTrue(math.isnan(sensor.altitude_agl))


class TestGPSSensorParseVTG(unittest.TestCase):

    def _make_sensor(self):
        from cymbal.sensors.gps_sensor import GPSSensor
        return GPSSensor()

    def test_speed_converted_to_ms(self):
        sensor = self._make_sensor()
        msg = _VTGMsg(speed_kmph=72.0, true_track=45.0)
        result = sensor._parse_vtg(msg)
        self.assertTrue(result)
        self.assertAlmostEqual(sensor.groundspeed_ms, 20.0, places=1)
        self.assertAlmostEqual(sensor.track_degrees, 45.0, places=1)

    def test_none_speed_does_not_raise(self):
        sensor = self._make_sensor()
        msg = _VTGMsg(speed_kmph=None, true_track=None)
        # Should not raise; returns True if no exception
        sensor._parse_vtg(msg)

    def test_zero_speed(self):
        sensor = self._make_sensor()
        msg = _VTGMsg(speed_kmph=0.0, true_track=0.0)
        sensor._parse_vtg(msg)
        self.assertAlmostEqual(sensor.groundspeed_ms, 0.0, places=3)


class TestGPSSensorParseRMC(unittest.TestCase):

    def _make_sensor(self):
        from cymbal.sensors.gps_sensor import GPSSensor
        return GPSSensor()

    def test_active_rmc_updates_speed(self):
        sensor = self._make_sensor()
        msg = _RMCMsg(status='A', lat=33.4, lon=-111.8, speed_kts=10.0, course=90.0)
        result = sensor._parse_rmc(msg)
        self.assertTrue(result)
        # 10 knots * 0.514444 ≈ 5.144 m/s
        self.assertAlmostEqual(sensor.groundspeed_ms, 5.144, places=2)
        self.assertAlmostEqual(sensor.track_degrees, 90.0, places=1)

    def test_void_rmc_skipped(self):
        sensor = self._make_sensor()
        msg = _RMCMsg(status='V', lat=33.4, lon=-111.8, speed_kts=5.0, course=45.0)
        result = sensor._parse_rmc(msg)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
