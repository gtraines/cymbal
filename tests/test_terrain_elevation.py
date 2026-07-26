"""
Unit tests for TerrainElevationDB.

These tests run without the srtm.py library by injecting a mock elevation
data object into the class internals.
"""

import math
import sys
import types
import unittest


class TestTerrainElevationDBInit(unittest.TestCase):

    def test_uninitialized_returns_nan(self):
        from cymbal.geo.terrain_elevation import TerrainElevationDB
        db = TerrainElevationDB()
        result = db.get_elevation(33.4, -111.8)
        self.assertTrue(math.isnan(result))

    def test_initialize_fails_gracefully_without_srtm(self):
        """If srtm.py raises on init, initialize() returns False without crashing."""
        from cymbal.geo.terrain_elevation import TerrainElevationDB
        db = TerrainElevationDB()
        # Pass a path that srtm.py would reject (the module may or may not be
        # installed; either way the /nonexistent path should cause a failure).
        result = db.initialize("/nonexistent/srtm/path")
        # Either False (srtm not installed or path rejected) or an initialized
        # instance (srtm IS installed but points at a valid but empty cache).
        # We only assert it doesn't raise.
        self.assertIsInstance(result, bool)

    def test_close_safe_when_not_initialized(self):
        from cymbal.geo.terrain_elevation import TerrainElevationDB
        db = TerrainElevationDB()
        db.close()  # should not raise
        self.assertFalse(db.is_initialized)


class TestTerrainElevationDBWithMock(unittest.TestCase):
    """
    Inject a mock elevation_data object to test the lookup logic without
    needing SRTM tile files.
    """

    def _make_db_with_mock(self, elev_value):
        from cymbal.geo.terrain_elevation import TerrainElevationDB

        class _MockElevData:
            def get_elevation(self, lat, lon):
                return elev_value

        db = TerrainElevationDB()
        db._elevation_data = _MockElevData()
        db.is_initialized = True
        return db

    def test_returns_elevation_float(self):
        db = self._make_db_with_mock(330.0)
        result = db.get_elevation(33.4, -111.8)
        self.assertAlmostEqual(result, 330.0, places=1)

    def test_returns_nan_when_mock_returns_none(self):
        db = self._make_db_with_mock(None)
        result = db.get_elevation(33.4, -111.8)
        self.assertTrue(math.isnan(result))

    def test_returns_nan_when_mock_raises(self):
        from cymbal.geo.terrain_elevation import TerrainElevationDB

        class _RaisingData:
            def get_elevation(self, lat, lon):
                raise IOError("tile read error")

        db = TerrainElevationDB()
        db._elevation_data = _RaisingData()
        db.is_initialized = True
        result = db.get_elevation(33.4, -111.8)
        self.assertTrue(math.isnan(result))

    def test_close_resets_state(self):
        db = self._make_db_with_mock(300.0)
        db.close()
        self.assertFalse(db.is_initialized)
        self.assertIsNone(db._elevation_data)
        # After close, queries should return NaN
        result = db.get_elevation(33.4, -111.8)
        self.assertTrue(math.isnan(result))


if __name__ == '__main__':
    unittest.main()
